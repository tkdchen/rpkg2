# pyrpkg - a Python library for RPM Packagers
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

import errno
import fnmatch
import git
import glob
import koji
import logging
import os
import posixpath
import pwd
import re
import rpm
import shutil
import six
import sys
import tempfile

from osbs.api import OSBS
from osbs.conf import Configuration
from six.moves import configparser
from six.moves import urllib

from pyrpkg.errors import HashtypeMixingError, rpkgError, rpkgAuthError, \
    UnknownTargetError
from .gitignore import GitIgnore
from pyrpkg.lookaside import CGILookasideCache
from pyrpkg.sources import SourcesFile
from pyrpkg.utils import cached_property, log_result

try:
    # Use gssapi to detect the Kerberos credential by default, even krbV is
    # still available too.
    import gssapi
except ImportError:
    gssapi = None

try:
    # This is for backwards compatibility in old version OS where gssapi is not
    # available.
    import krbV
except ImportError:
    krbV = None

if sys.version_info[0:2] >= (2, 5):
    import subprocess
else:
    # We need a subprocess that has check_call
    from kitchen.pycompat27 import subprocess


class NullHandler(logging.Handler):
    """Null logger to avoid spurious messages, add a handler in app code"""
    def emit(self, record):
        pass


h = NullHandler()
# This is our log object, clients of this library can use this object to
# define their own logging needs
log = logging.getLogger(__name__)
# Add the null handler
log.addHandler(h)


class Commands(object):
    """This is a class to hold all the commands that will be called
    by clients
    """

    # This shouldn't change... often
    UPLOADEXTS = ['tar', 'gz', 'bz2', 'lzma', 'xz', 'Z', 'zip', 'tff',
                  'bin', 'tbz', 'tbz2', 'tgz', 'tlz', 'txz', 'pdf', 'rpm',
                  'jar', 'war', 'db', 'cpio', 'jisp', 'egg', 'gem', 'spkg',
                  'oxt', 'xpi']

    def __init__(self, path, lookaside, lookasidehash, lookaside_cgi,
                 gitbaseurl, anongiturl, branchre, kojiconfig,
                 build_client, user=None,
                 dist=None, target=None, quiet=False,
                 distgit_namespaced=False):
        """Init the object and some configuration details."""

        # Path to operate on, most often pwd
        self._path = None
        self.path = os.path.abspath(path)
        # The url of the lookaside for source archives
        self.lookaside = lookaside
        # The type of hash to use with the lookaside
        self.lookasidehash = lookasidehash
        # The CGI server for the lookaside
        self.lookaside_cgi = lookaside_cgi
        # The base URL of the git server
        self.gitbaseurl = gitbaseurl
        # The anonymous version of the git url
        self.anongiturl = anongiturl
        # The regex of branches we care about
        self.branchre = branchre
        # The location of the buildsys config file
        self.kojiconfig = os.path.expanduser(kojiconfig)
        # The buildsys client to use
        self.build_client = build_client
        # A way to override the discovered "distribution"
        self.dist = dist
        # Set the default hashtype
        self.hashtype = 'sha256'
        # Set an attribute for quiet or not
        self.quiet = quiet
        # Set place holders for properties
        # Anonymous buildsys session
        self._anon_kojisession = None
        # The upstream branch a downstream branch is tracking
        self._branch_merge = None
        # The latest commit
        self._commit = None
        # The disttag rpm value
        self._disttag = None
        # The distval rpm value
        self._distval = None
        # The distvar rpm value
        self._distvar = None
        # The rpm epoch of the cloned module
        self._epoch = None
        # An authenticated buildsys session
        self._kojisession = None
        # A web url of the buildsys server
        self._kojiweburl = None
        # The local arch to use in rpm building
        self._localarch = None
        # A property to load the mock config
        self._mockconfig = None
        # The name of the cloned module
        self._module_name = None
        # The distgit namespaced name of the cloned module
        self._ns_module_name = None
        # The name of the module from spec file
        self._module_name_spec = None
        # The rpm name-version-release of the cloned module
        self._nvr = None
        # The rpm release of the cloned module
        self._rel = None
        # The cloned repo object
        self._repo = None
        # The rpm defines used when calling rpm
        self._rpmdefines = None
        # The specfile in the cloned module
        self._spec = None
        # The build target within the buildsystem
        self._target = target
        # The top url to our build server
        self._topurl = None
        # The user to use or discover
        self._user = user
        # The password to use
        self._password = None
        # The alternate Koji user to run commands as
        self._runas = None
        # The rpm version of the cloned module
        self._ver = None
        self.log = log
        # Pushurl or url of remote of branch
        self._push_url = None
        # Name of remote determined from current clone
        self._branch_remote = None
        # Name of default remote to be used for new clone
        self.default_branch_remote = 'origin'
        # Default sources file output format type
        self.source_entry_type = 'old'
        # Set an attribute debug
        self.debug = False
        # Set an attribute verbose
        self.verbose = False
        # Config to set after cloning
        self.clone_config = None
        # Git namespacing for more than just rpm build artifacts
        self.distgit_namespaced = distgit_namespaced

    # Define properties here
    # Properties allow us to "lazy load" various attributes, which also means
    # that we can do clone actions without knowing things like the spec
    # file or rpm data.

    @cached_property
    def lookasidecache(self):
        """A helper to interact with the lookaside cache

        This is a pyrpkg.lookaside.CGILookasideCache instance, providing all
        the needed stuff to communicate with a Fedora-style lookaside cache.

        Downstream users of the pyrpkg API may override this property with
        their own, returning their own implementation of a lookaside cache
        helper object.
        """
        return CGILookasideCache(
            self.lookasidehash, self.lookaside, self.lookaside_cgi,
            client_cert=self.cert_file, ca_cert=self.ca_cert)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        if self._path != value:
            # Ensure all properties which depend on self.path will be
            # freshly loaded next time
            self._push_url = None
            self._branch_remote = None
            self._repo = None
            self._ns_module_name = None
        self._path = value

    @property
    def anon_kojisession(self):
        """This property ensures the anon kojisession attribute"""

        if not self._anon_kojisession:
            self.load_kojisession(anon=True)
        return self._anon_kojisession

    def load_kojisession(self, anon=False):
        """Initiate a koji session.

        The koji session can be logged in or anonymous
        """

        # Stealing a bunch of code from /usr/bin/koji here, too bad it isn't
        # in a more usable library form
        defaults = {
            'server': None,
            'topurl': 'http://localhost/kojiroot',
            'weburl': 'http://localhost/koji',
            'cert': '~/.koji/client.crt',
            'ca': '~/.koji/clientca.crt',
            'serverca': '~/.koji/serverca.crt',
            'authtype': None,
            'krbservice': None,
            'timeout': None,
            'keepalive': True,
            'max_retries': None,
            'retry_interval': None,
            'anon_retry': True,
            'offline_retry': None,
            'offline_retry_interval': None,
            'use_fast_upload': None,
            'debug': None,
            'debug_xmlrpc': None
            }

        # Process the configs in order, global, user, then any option passed
        config = configparser.ConfigParser()
        confs = [self.kojiconfig,
                 os.path.expanduser('~/.koji/config')]
        config.read(confs)

        if config.has_section(os.path.basename(self.build_client)):
            for name, value in config.items(os.path.basename(
                    self.build_client)):
                if name in defaults:
                    if name in ('keepalive', 'anon_retry', 'offline_retry',
                                'use_fast_upload',
                                'debug', 'debug_xmlrpc'):
                        defaults[name] = config.getboolean(
                            os.path.basename(self.build_client), name)
                    elif name in ('timeout', 'max_retries', 'retry_interval',
                                  'offline_retry_interval'):
                        defaults[name] = config.getint(
                            os.path.basename(self.build_client), name)
                    else:
                        defaults[name] = value
        if not defaults['server']:
            raise rpkgError('No server defined in: %s' % ', '.join(confs))
        # Expand out the directory options
        for name in ('cert', 'ca', 'serverca'):
            if defaults[name]:
                defaults[name] = os.path.expanduser(defaults[name])
        self.log.debug('Initiating a %s session to %s',
                       os.path.basename(self.build_client), defaults['server'])
        session_opts = {}
        for name in ('krbservice', 'timeout', 'keepalive',
                     'max_retries', 'retry_interval', 'anon_retry',
                     'offline_retry', 'offline_retry_interval',
                     'debug', 'debug_xmlrpc',
                     'use_fast_upload'):
            if defaults[name] is not None:
                session_opts[name] = defaults[name]
        try:
            if anon:
                self._anon_kojisession = koji.ClientSession(defaults['server'],
                                                            session_opts)
            else:
                self._kojisession = koji.ClientSession(defaults['server'],
                                                       session_opts)
        except:
            raise rpkgError('Could not initiate %s session' %
                            os.path.basename(self.build_client))
        # save the weburl and topurl for later use as well
        self._kojiweburl = defaults['weburl']
        self._topurl = defaults['topurl']
        if not anon:
            # Default to ssl if not otherwise specified and we have the cert
            if defaults['authtype'] == 'ssl' or \
                    os.path.isfile(defaults['cert']) and \
                    defaults['authtype'] is None:
                try:
                    self._kojisession.ssl_login(defaults['cert'],
                                                defaults['ca'],
                                                defaults['serverca'],
                                                proxyuser=self.runas)
                except koji.ssl.SSLCommon.SSL.Error as error:
                    for (_, _, ssl_reason) in error.message:
                        # Use heuristic. Some OpenSSL libs doesn't store error
                        # codes
                        if 'certificate revoked' in ssl_reason or \
                           'certificate expired' in ssl_reason:
                            self.log.info("Certificate is revoked or expired.")
                    raise rpkgAuthError('Could not auth with koji. Login '
                                        'failed: %s' % error)
            # Or try password auth
            elif defaults['authtype'] == 'password' or self.password \
                    and defaults['authtype'] is None:
                if self.runas:
                    raise rpkgError('--runas cannot be used with password auth')
                self._kojisession.opts['user'] = self.user
                self._kojisession.opts['password'] = self.password
                self._kojisession.login()
            # Or try kerberos
            elif defaults['authtype'] == 'kerberos' or self._has_krb_creds() \
                    and defaults['authtype'] is None:
                self._kojisession.krb_login(proxyuser=self.runas)
            if not self._kojisession.logged_in:
                raise rpkgError('Could not login to %s' % defaults['server'])

    @property
    def branch_merge(self):
        """This property ensures the branch attribute"""

        if not self._branch_merge:
            self.load_branch_merge()
        return(self._branch_merge)

    def load_branch_merge(self):
        """Find the remote tracking branch from the branch we're on.

        The goal of this function is to catch if we are on a branch we

        can make some assumptions about.  If there is no merge point

        then we raise and ask the user to specify.
        """

        if self.dist:
            self._branch_merge = self.dist
        else:
            try:
                localbranch = self.repo.active_branch.name
            except TypeError as e:
                raise rpkgError('Repo in inconsistent state: %s' % e)
            try:
                merge = self.repo.git.config('--get', 'branch.%s.merge' % localbranch)
            except git.GitCommandError as e:
                raise rpkgError('Unable to find remote branch.  Use --release')
            # Trim off the refs/heads so that we're just working with
            # the branch name
            merge = merge.replace('refs/heads/', '')
            self._branch_merge = merge

    @property
    def branch_remote(self):
        """This property ensures the branch_remote attribute"""

        if not self._branch_remote:
            self.load_branch_remote()
        return self._branch_remote

    def load_branch_remote(self):
        """Find the name of remote from branch we're on."""

        try:
            remote = self.repo.git.config('--get', 'branch.%s.remote'
                                          % self.branch_merge)
        except (git.GitCommandError, rpkgError) as e:
            remote = self.default_branch_remote
            self.log.debug("Could not determine the remote name: %s", str(e))
            self.log.debug("Falling back to default remote name '%s'", remote)

        self._branch_remote = remote

    @property
    def push_url(self):
        """This property ensures the push_url attribute"""

        if not self._push_url:
            self.load_push_url()
        return self._push_url

    def load_push_url(self):
        """Find the pushurl or url of remote of branch we're on."""
        try:
            url = self.repo.git.remote('get-url', '--push', self.branch_remote)
        except git.GitCommandError as e:
            try:
                url = self.repo.git.config(
                    '--get', 'remote.%s.pushurl' % self.branch_remote)
            except git.GitCommandError as e:
                try:
                    url = self.repo.git.config(
                        '--get', 'remote.%s.url' % self.branch_remote)
                except git.GitCommandError as e:
                    raise rpkgError('Unable to find remote push url: %s' % e)
        if isinstance(url, six.text_type):
            # GitPython >= 1.0 return unicode. It must be encoded to string.
            self._push_url = url
        else:
            self._push_url = url.decode('utf-8')

    @property
    def commithash(self):
        """This property ensures the commit attribute"""

        if not self._commit:
            self.load_commit()
        return self._commit

    def load_commit(self):
        """Discover the latest commit to the package"""

        # Get the commit hash
        comobj = six.next(self.repo.iter_commits())
        # Work around different versions of GitPython
        if hasattr(comobj, 'sha'):
            self._commit = comobj.sha
        else:
            self._commit = comobj.hexsha

    @property
    def disttag(self):
        """This property ensures the disttag attribute"""

        if not self._disttag:
            self.load_rpmdefines()
        return self._disttag

    @property
    def distval(self):
        """This property ensures the distval attribute"""

        if not self._distval:
            self.load_rpmdefines()
        return self._distval

    @property
    def distvar(self):
        """This property ensures the distvar attribute"""

        if not self._distvar:
            self.load_rpmdefines()
        return self._distvar

    @property
    def epoch(self):
        """This property ensures the epoch attribute"""

        if not self._epoch:
            self.load_nameverrel()
        return self._epoch

    @property
    def kojisession(self):
        """This property ensures the kojisession attribute"""

        if not self._kojisession:
            self.load_kojisession()
        return self._kojisession

    @property
    def kojiweburl(self):
        """This property ensures the kojiweburl attribute"""

        if not self._kojiweburl:
            self.load_kojisession()
        return self._kojiweburl

    @property
    def localarch(self):
        """This property ensures the module attribute"""

        if not self._localarch:
            self.load_localarch()
        return(self._localarch)

    def load_localarch(self):
        """Get the local arch as defined by rpm"""

        proc = subprocess.Popen(['rpm --eval %{_arch}'], shell=True,
                                stdout=subprocess.PIPE,
                                universal_newlines=True)
        self._localarch = proc.communicate()[0].strip('\n')

    @property
    def mockconfig(self):
        """This property ensures the mockconfig attribute"""

        if not self._mockconfig:
            self.load_mockconfig()
        return self._mockconfig

    @mockconfig.setter
    def mockconfig(self, config):
        self._mockconfig = config

    def load_mockconfig(self):
        """This sets the mockconfig attribute"""

        self._mockconfig = '%s-%s' % (self.target, self.localarch)

    @property
    def module_name(self):
        """This property ensures the module attribute"""

        if not self._module_name:
            self.load_module_name()
        return self._module_name

    @module_name.setter
    def module_name(self, module_name):
        self._module_name = module_name

    def load_module_name(self):
        """Loads a package module."""

        try:
            if self.push_url:
                parts = urllib.parse.urlparse(self.push_url)

                # FIXME
                # if self.distgit_namespaced:
                #     self._module_name = "/".join(parts.path.split("/")[-2:])
                module_name = posixpath.basename(parts.path)

                if module_name.endswith('.git'):
                    module_name = module_name[:-len('.git')]
                self._module_name = module_name
                return
        except rpkgError:
            self.log.warning('Failed to get module name from Git url or pushurl')

        self.load_nameverrel()
        if self._module_name_spec:
            self._module_name = self._module_name_spec
            return

        raise rpkgError('Could not find current module name.'
                        ' Use --module-name.')

    @property
    def ns_module_name(self):
        """This property ensures the module attribute"""

        if not self._ns_module_name:
            self.load_ns_module_name()
        return self._ns_module_name

    @ns_module_name.setter
    def ns_module_name(self, ns_module_name):
        self._ns_module_name = ns_module_name

    def _print_old_checkout_warning(self, module):
        self.log.warning('Your git configuration does not use a namespace.')
        self.log.warning('Consider updating your git configuration by running:')
        self.log.warning('  git remote set-url %s %s',
                         self.branch_remote, self._get_namespace_giturl(module))

    def load_ns_module_name(self):
        """Loads a package module."""

        try:
            if self.push_url:
                parts = urllib.parse.urlparse(self.push_url)

                if self.distgit_namespaced:
                    path_parts = [p for p in parts.path.split("/") if p]
                    if len(path_parts) == 1:
                        self._print_old_checkout_warning(path_parts[0])
                        path_parts.insert(0, "rpms")
                    ns_module_name = "/".join(path_parts[-2:])
                else:
                    ns_module_name = posixpath.basename(parts.path)

                if ns_module_name.endswith('.git'):
                    ns_module_name = ns_module_name[:-len('.git')]
                self._ns_module_name = ns_module_name
                return
        except rpkgError:
            self.log.warning('Failed to get ns_module_name from Git url or pushurl')

    @property
    def nvr(self):
        """This property ensures the nvr attribute"""

        if not self._nvr:
            self.load_nvr()
        return self._nvr

    def load_nvr(self):
        """This sets the nvr attribute"""

        self._nvr = '%s-%s-%s' % (self.module_name, self.ver, self.rel)

    @property
    def rel(self):
        """This property ensures the rel attribute"""
        if not self._rel:
            self.load_nameverrel()
        return(self._rel)

    def load_nameverrel(self):
        """Set the release of a package module."""

        cmd = ['rpm']
        cmd.extend(self.rpmdefines)
        # We make sure there is a space at the end of our query so that
        # we can split it later.  When there are subpackages, we get a
        # listing for each subpackage.  We only care about the first.
        cmd.extend(['-q', '--qf', '"%{NAME} %{EPOCH} %{VERSION} %{RELEASE}??"',
                    '--specfile', '"%s"' % os.path.join(self.path, self.spec)])
        joined_cmd = ' '.join(cmd)
        try:
            proc = subprocess.Popen(joined_cmd, shell=True,
                                    universal_newlines=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            output, err = proc.communicate()
        except Exception as e:
            if err:
                self.log.debug('Errors occoured while running following command to get N-V-R-E:')
                self.log.debug(joined_cmd)
                self.log.error(err)
            raise rpkgError('Could not query n-v-r of %s: %s'
                            % (self.module_name, e))
        if err:
            self.log.debug('Errors occoured while running following command to get N-V-R-E:')
            self.log.debug(joined_cmd)
            self.log.error(err)
        # Get just the output, then split it by ??, grab the first and split
        # again to get ver and rel
        first_line_output = output.split('??')[0]
        parts = first_line_output.split()
        if len(parts) != 4:
            raise rpkgError('Could not get n-v-r-e from %r'
                            % first_line_output)
        (self._module_name_spec,
         self._epoch,
         self._ver,
         self._rel) = parts

        # Most packages don't include a "Epoch: 0" line, in which case RPM
        # returns '(none)'
        if self._epoch == "(none)":
            self._epoch = "0"

    @property
    def repo(self):
        """This property ensures the repo attribute"""

        if not self._repo:
            self.load_repo()
        return(self._repo)

    def load_repo(self):
        """Create a repo object from our path"""

        self.log.debug('Creating repo object from %s', self.path)
        try:
            self._repo = git.Repo(self.path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            raise rpkgError('%s is not a valid repo' % self.path)

    @property
    def rpmdefines(self):
        """This property ensures the rpm defines"""

        if not self._rpmdefines:
            self.load_rpmdefines()
        return(self._rpmdefines)

    def load_rpmdefines(self):
        """Populate rpmdefines based on current active branch"""

        # This is another function ripe for subclassing

        try:
            # This regex should find the 'rhel-5' or 'rhel-6.2' parts of the
            # branch name.  There should only be one of those, and all branches
            # should end in one.
            osver = re.search(r'rhel-\d.*$', self.branch_merge).group()
        except AttributeError:
            raise rpkgError('Could not find the base OS ver from branch name'
                            ' %s. Consider using --release option' %
                            self.branch_merge)
        self._distvar, self._distval = osver.split('-')
        self._distval = self._distval.replace('.', '_')
        self._disttag = 'el%s' % self._distval
        self._rpmdefines = ["--define '_sourcedir %s'" % self.path,
                            "--define '_specdir %s'" % self.path,
                            "--define '_builddir %s'" % self.path,
                            "--define '_srcrpmdir %s'" % self.path,
                            "--define '_rpmdir %s'" % self.path,
                            "--define 'dist .%s'" % self._disttag,
                            "--define '%s %s'" % (self._distvar,
                                                  self._distval.split('_')[0]),
                            # int and float this to remove the decimal
                            "--define '%s 1'" % self._disttag]

    @property
    def spec(self):
        """This property ensures the module attribute"""

        if not self._spec:
            self.load_spec()
        return self._spec

    def load_spec(self):
        """This sets the spec attribute"""

        deadpackage = False

        # Get a list of files in the path we're looking at
        files = os.listdir(self.path)
        # Search the files for the first one that ends with ".spec"
        for f in files:
            if f.endswith('.spec') and not f.startswith('.'):
                self._spec = f
                return
            if f == 'dead.package':
                deadpackage = True
        if deadpackage:
            raise rpkgError('No spec file found. This package is retired')
        else:
            raise rpkgError('No spec file found.')

    @property
    def target(self):
        """This property ensures the target attribute"""

        if not self._target:
            self.load_target()
        return self._target

    def load_target(self):
        """This creates the target attribute based on branch merge"""

        # If a site has a different naming scheme, this would be where
        # a site would override
        self._target = '%s-candidate' % self.branch_merge

    @property
    def topurl(self):
        """This property ensures the topurl attribute"""

        if not self._topurl:
            # Assume anon here, whatever.
            self.load_kojisession(anon=True)
        return self._topurl

    @property
    def user(self):
        """This property ensures the user attribute"""

        if not self._user:
            self.load_user()
        return self._user

    def load_user(self):
        """This sets the user attribute"""

        # If a site figures out the user differently (like from ssl cert)
        # this is where you'd override and make that happen
        self._user = pwd.getpwuid(os.getuid())[0]

    @property
    def password(self):
        """This property ensures the password attribute"""

        return self._password

    @password.setter
    def password(self, password):
        self._password = password

    @property
    def runas(self):
        """This property ensures the runas attribute"""

        return self._runas

    @runas.setter
    def runas(self, runas):
        self._runas = runas

    @property
    def ver(self):
        """This property ensures the ver attribute"""
        if not self._ver:
            self.load_nameverrel()
        return(self._ver)

    @property
    def mock_results_dir(self):
        return os.path.join(self.path, "results_%s" % self.module_name,
                            self.ver, self.rel)

    @property
    def sources_filename(self):
        return os.path.join(self.path, 'sources')

    @property
    def osbs_config_filename(self):
        return os.path.join(self.path, '.osbs-repo-config')

    @property
    def cert_file(self):
        """A client-side certificate for SSL authentication

        Downstream users of the pyrpkg API should override this property if
        they actually need to use a client-side certificate.

        This defaults to None, which means no client-side certificate is used.
        """
        return None

    @property
    def ca_cert(self):
        """A CA certificate to authenticate the server in SSL connections

        Downstream users of the pyrpkg API should override this property if
        they actually need to use a CA certificate, usually because their
        lookaside cache is using HTTPS with a self-signed certificate.

        This defaults to None, which means the system CA bundle is used.
        """
        return None

    # Define some helper functions, they start with _
    def _has_krb_creds_by_gssapi(self):
        """Test if there is usable initialized Kerberos credential

        :return: True if credential is initialized and not expired. Otherwise, False is returned.
        :rtype: bool
        """
        try:
            cred = gssapi.creds.Credentials(usage='initiate')
        except gssapi.exceptions.GSSError:
            # GSSError is raised if credential cache is not initialized or has bad format.
            return False
        try:
            # We don't care about the value of attribute lifetime. Reading
            # lifetime is only for testing if credential is usable.
            cred.lifetime
        except gssapi.exceptions.ExpiredCredentialsError:
            return False
        return True

    def _has_krb_creds_by_krbv(self):
        """Test if there is usable initialized Kerberos credential

        :return: True if credential is initialized and not expired. Otherwise, False is returned.
        :rtype: bool
        """
        try:
            ctx = krbV.default_context()
            ccache = ctx.default_ccache()
            princ = ccache.principal()  # noqa
            return True
        except krbV.Krb5Error:
            return False

    def _has_krb_creds_default(self):
        """Kerberos authentication is disabled if neither gssapi nor krbV is available"""
        return False

    if gssapi:
        _has_krb_creds = _has_krb_creds_by_gssapi
    elif krbV:
        _has_krb_creds = _has_krb_creds_by_krbv
    else:
        _has_krb_creds = _has_krb_creds_default

    def _run_command(self, cmd, shell=False, env=None, pipe=[], cwd=None):
        """Run the given command.

        _run_command is able to run single command or two commands via pipe.
        Whatever the way to run the command, output to both stdout and stderr
        will not be captured and output to terminal directly, that is useful
        for caller to redirect.

        cmd is a list of the command and arguments

        shell is whether to run in a shell or not, defaults to False

        env is a dict of environment variables to use (if any)

        pipe is a command to pipe the output of cmd into

        cwd is the optional directory to run the command from

        Raises on error, or returns nothing.
        """

        # Process any environment variables.
        environ = os.environ
        if env:
            for item in env.keys():
                self.log.debug('Adding %s:%s to the environment', item, env[item])
                environ[item] = env[item]
        # Check if we're supposed to be on a shell.  If so, the command must
        # be a string, and not a list.
        command = cmd
        pipecmd = pipe
        if shell:
            command = ' '.join(cmd)
            pipecmd = ' '.join(pipe)

        if pipe:
            self.log.debug('Running: %s | %s', ' '.join(cmd), ' '.join(pipe))
        else:
            self.log.debug('Running: %s', ' '.join(cmd))

        try:
            if pipe:
                # We're piping the stderr over as well, which is probably a
                # bad thing, but rpmbuild likes to put useful data on
                # stderr, so....
                proc = subprocess.Popen(command, env=environ, shell=shell, cwd=cwd,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                subprocess.check_call(pipecmd, env=environ, shell=shell, cwd=cwd, stdin=proc.stdout)
            else:
                subprocess.check_call(command, env=environ, shell=shell, cwd=cwd)
        except (subprocess.CalledProcessError, OSError) as e:
            raise rpkgError(e)
        except KeyboardInterrupt:
            raise rpkgError('Command is terminated by user.')
        except Exception as e:
            raise rpkgError(e)

    def _newer(self, file1, file2):
        """Compare the last modification time of the given files

        Returns True is file1 is newer than file2

        """

        return os.path.getmtime(file1) > os.path.getmtime(file2)

    def _get_build_arches_from_spec(self):
        """Given the path to an spec, retrieve the build arches

        """

        spec = os.path.join(self.path, self.spec)
        try:
            hdr = rpm.spec(spec)
        except Exception:
            raise rpkgError('%s is not a spec file' % spec)
        archlist = [pkg.header['arch'] for pkg in hdr.packages]
        if not archlist:
            raise rpkgError('No compatible build arches found in %s' % spec)
        return archlist

    def _get_build_arches_from_srpm(self, srpm, arches):
        """Given the path to an srpm, determine the possible build arches

        Use supplied arches as a filter, only return compatible arches

        """

        archlist = arches
        hdr = koji.get_rpm_header(srpm)
        if hdr[rpm.RPMTAG_SOURCEPACKAGE] != 1:
            raise rpkgError('%s is not a source package.' % srpm)
        buildarchs = hdr[rpm.RPMTAG_BUILDARCHS]
        exclusivearch = hdr[rpm.RPMTAG_EXCLUSIVEARCH]
        excludearch = hdr[rpm.RPMTAG_EXCLUDEARCH]
        # Reduce by buildarchs
        if buildarchs:
            archlist = [a for a in archlist if a in buildarchs]
        # Reduce by exclusive arches
        if exclusivearch:
            archlist = [a for a in archlist if a in exclusivearch]
        # Reduce by exclude arch
        if excludearch:
            archlist = [a for a in archlist if a not in excludearch]
        # do the noarch thing
        if 'noarch' not in excludearch and ('noarch' in buildarchs or
                                            'noarch' in exclusivearch):
            archlist.append('noarch')
        # See if we have anything compatible.  Should we raise here?
        if not archlist:
            raise rpkgError('No compatible build arches found in %s' % srpm)
        return archlist

    def _guess_hashtype(self):
        """Attempt to figure out the hash type based on branch data"""

        # We may not be able to determine the rpmdefine, if so, fall back.
        try:
            # This works, except for the small range of Fedoras
            # between FC5 and FC12 or so.  Nobody builds for that old
            # anyway.
            if int(re.search(r'\d+', self.distval).group()) < 6:
                return('md5')
        except:
            # An error here is OK, don't bother the user.
            pass

        # Fall back to the default hash type
        return(self.hashtype)

    def _fetch_remotes(self):
        self.log.debug('Fetching remotes')
        for remote in self.repo.remotes:
            self.repo.git.fetch(remote)

    def _list_branches(self, fetch=True):
        """Returns a tuple of local and remote branch names"""

        if fetch:
            self._fetch_remotes()
        self.log.debug('Listing refs')
        refs = self.repo.refs
        # Sort into local and remote branches
        remotes = []
        locals = []
        for ref in refs:
            if type(ref) == git.Head:
                self.log.debug('Found local branch %s', ref.name)
                locals.append(ref.name)
            elif type(ref) == git.RemoteReference:
                if ref.remote_head == 'HEAD':
                    self.log.debug('Skipping remote branch alias HEAD')
                    continue  # Not useful in this context
                self.log.debug('Found remote branch %s', ref.name)
                remotes.append(ref.name)
        return (locals, remotes)

    def _srpmdetails(self, srpm):
        """Return a tuple of package name, package files, and upload files."""

        # get the name
        cmd = ['rpm', '-qp', '--nosignature', '--qf', '%{NAME}', srpm]
        # Run the command
        self.log.debug('Running: %s', ' '.join(cmd))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError as e:
            raise rpkgError(e)
        name = output
        if error:
            raise rpkgError('Error querying srpm: %s' % error)

        # now get the files and upload files
        files = []
        uploadfiles = []
        cmd = ['rpm', '-qpl', srpm]
        self.log.debug('Running: %s', ' '.join(cmd))
        env = dict(os.environ)
        env["LANG"] = "C"
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    env=env)
            output, error = proc.communicate()
        except OSError as e:
            raise rpkgError(e)
        # work around signed SRPMs, for these rpm -qpl might print a warning
        # like:
        # warning: foo-0.0.src.rpm Header V3 RSA/SHA256 Signature, key ID
        # fd431d51: NOKEY
        if error and not error.startswith("warning:") and "NOKEY" not in error:
            raise rpkgError('Error querying srpm: %s' % error)
        contents = output.strip().split('\n')
        # Cycle through the stuff and sort correctly by its extension
        for file in contents:
            if file.rsplit('.')[-1] in self.UPLOADEXTS:
                uploadfiles.append(file)
            else:
                files.append(file)

        return((name, files, uploadfiles))

    def _get_namespace_giturl(self, module):
        """Get the namespaced git url, if DistGit namespaces enabled

        Takes a module name

        Returns a string of giturl

        """

        if self.distgit_namespaced:
            if '/' in module:
                giturl = self.gitbaseurl % \
                    {'user': self.user, 'module': module}
            else:
                # Default to rpms namespace for backwards compat
                giturl = self.gitbaseurl % \
                    {'user': self.user, 'module': "rpms/%s" % module}
        else:
            giturl = self.gitbaseurl % \
                {'user': self.user, 'module': module}

        return giturl

    def _get_namespace_anongiturl(self, module):
        """Get the namespaced git url, if DistGit namespaces enabled

        Takes a module name

        Returns a string of giturl

        """

        if self.distgit_namespaced:
            if '/' in module:
                giturl = self.anongiturl % {'module': module}
            else:
                # Default to rpms namespace for backwards compat
                giturl = self.anongiturl % {'module': "rpms/%s" % module}
        else:
            giturl = self.anongiturl % {'module': module}

        return giturl

    def add_tag(self, tagname, force=False, message=None, file=None):
        """Add a git tag to the repository

        Takes a tagname

        Optionally can force the tag, include a message,
        or reference a message file.

        Runs the tag command and returns nothing

        """

        cmd = ['git', 'tag']
        cmd.extend(['-a'])
        # force tag creation, if tag already exists
        if force:
            cmd.extend(['-f'])
        # Description for the tag
        if message:
            cmd.extend(['-m', message])
        elif file:
            cmd.extend(['-F', os.path.abspath(file)])
        cmd.append(tagname)
        # make it so
        self._run_command(cmd, cwd=self.path)
        self.log.info('Tag \'%s\' was created', tagname)

    def clean(self, dry=False, useignore=True):
        """Clean a module checkout of untracked files.

        Can optionally perform a dry-run

        Can optionally not use the ignore rules

        Logs output and returns nothing

        """

        # setup the command, this could probably be done with some python api...
        cmd = ['git', 'clean', '-f', '-d']
        if dry:
            cmd.append('--dry-run')
        if not useignore:
            cmd.append('-x')
        if self.quiet:
            cmd.append('-q')
        # Run it!
        self._run_command(cmd, cwd=self.path)
        return

    def clone(self, module, path=None, branch=None, bare_dir=None,
              anon=False, target=None):
        """Clone a repo, optionally check out a specific branch.

        module is the name of the module to clone

        path is the basedir to perform the clone in

        branch is the name of a branch to checkout instead of <remote>/master

        bare_dir is the name of a directory to make a bare clone to, if this
        is a bare clone. None otherwise.

        anon is whether or not to clone anonymously

        target is the name of the folder in which to clone the repo

        Logs the output and returns nothing.

        """

        if not path:
            path = self.path
            self._push_url = None
            self._branch_remote = None
        # construct the git url
        if anon:
            giturl = self._get_namespace_anongiturl(module)
        else:
            giturl = self._get_namespace_giturl(module)

        # Create the command
        cmd = ['git', 'clone']
        if self.quiet:
            cmd.append('-q')
        # do the clone
        if branch and bare_dir:
            raise rpkgError('Cannot combine bare cloning with a branch')
        elif branch:
            # For now we have to use switch branch
            self.log.debug('Checking out a specific branch %s', giturl)
            cmd.extend(['-b', branch, giturl])
        elif bare_dir:
            self.log.debug('Cloning %s bare', giturl)
            cmd.extend(['--bare', giturl])
            if not target:
                cmd.append(bare_dir)
        else:
            self.log.debug('Cloning %s', giturl)
            cmd.extend([giturl])

        if not bare_dir:
            # --bare and --origin are incompatible
            cmd.extend(['--origin', self.default_branch_remote])

        if target:
            self.log.debug('Cloning into: %s', target)
            cmd.append(target)

        self._run_command(cmd, cwd=path)

        if self.clone_config:
            base_module = self.get_base_module(module)
            git_dir = target if target else bare_dir if bare_dir else base_module
            conf_git = git.Git(os.path.join(path, git_dir))
            self._clone_config(conf_git, module)

        return

    def get_base_module(self, module):
        # Handle namespaced modules
        # Example:
        #   module: docker/cockpit
        #       The path will just be os.path.join(path, "cockpit")
        if "/" in module:
            return module.split("/")[-1]
        return module

    def clone_with_dirs(self, module, anon=False, target=None):
        """Clone a repo old style with subdirs for each branch.

        module is the name of the module to clone

        gitargs is an option list of arguments to git clone

        """

        self._push_url = None
        self._branch_remote = None
        # Get the full path of, and git object for, our directory of branches
        top_path = os.path.join(self.path,
                                target or self.get_base_module(module))
        top_git = git.Git(top_path)
        repo_path = os.path.join(top_path, 'rpkg.git')

        # construct the git url
        if anon:
            giturl = self._get_namespace_anongiturl(module)
        else:
            giturl = self._get_namespace_giturl(module)

        # Create our new top directory
        try:
            os.mkdir(top_path)
        except OSError as e:
            raise rpkgError('Could not create directory for module %s: %s'
                            % (module, e))

        # Create a bare clone first. This gives us a good list of branches
        try:
            self.clone(module, top_path, bare_dir=repo_path, anon=anon)
        except Exception as e:
            # Clean out our directory
            shutil.rmtree(top_path)
            raise
        # Get the full path to, and a git object for, our new bare repo
        repo_git = git.Git(repo_path)

        # Get a branch listing
        branches = [x for x in repo_git.branch().split()
                    if x != "*" and re.search(self.branchre, x)]

        for branch in branches:
            try:
                # Make a local clone for our branch
                top_git.clone("--branch", branch,
                              "--origin", self.default_branch_remote,
                              repo_path, branch)

                # Set the origin correctly
                branch_path = os.path.join(top_path, branch)
                branch_git = git.Git(branch_path)
                branch_git.config("--replace-all",
                                  "remote.%s.url" % self.default_branch_remote,
                                  giturl)
            except (git.GitCommandError, OSError) as e:
                raise rpkgError('Could not locally clone %s from %s: %s'
                                % (branch, repo_path, e))

        # We don't need this now. Ignore errors since keeping it does no harm
        shutil.rmtree(repo_path, ignore_errors=True)

    def _clone_config(self, conf_git, module):
        clone_config = self.clone_config.strip() % {'module': module}
        for confline in clone_config.splitlines():
            if confline:
                conf_git.config(*confline.split())

    def commit(self, message=None, file=None, files=[], signoff=False):
        """Commit changes to a module (optionally found at path)

        Can take a message to use as the commit message

        a file to find the commit message within

        and a list of files to commit.

        Requires the caller be a real tty or a message passed.

        Logs the output and returns nothing.

        """

        # First lets see if we got a message or we're on a real tty:
        if not sys.stdin.isatty():
            if not message and not file:
                raise rpkgError('Must have a commit message or be on a real tty.')

        # construct the git command
        # We do this via subprocess because the git module is terrible.
        cmd = ['git', 'commit']
        if signoff:
            cmd.append('-s')
        if self.quiet:
            cmd.append('-q')
        if message:
            cmd.extend(['-m', message])
        elif file:
            # If we get a relative file name, prepend our path to it.
            if self.path and not file.startswith('/'):
                cmd.extend(['-F', os.path.abspath(os.path.join(self.path, file))])
            else:
                cmd.extend(['-F', os.path.abspath(file)])
        if not files:
            cmd.append('-a')
        else:
            cmd.extend(files)
        # make it so
        self._run_command(cmd, cwd=self.path)
        return

    def delete_tag(self, tagname):
        """Delete a git tag from the repository found at optional path"""

        try:
            self.repo.delete_tag(tagname)

        except git.GitCommandError as e:
            raise rpkgError(e)

        self.log.info('Tag %s was deleted', tagname)

    def diff(self, cached=False, files=[]):
        """Execute a git diff

        optionally diff the cached or staged changes

        Takes an optional list of files to diff relative to the module base
        directory

        Logs the output and returns nothing

        """

        # Things work better if we're in our module directory
        oldpath = os.getcwd()
        os.chdir(self.path)
        # build up the command
        cmd = ['git', 'diff']
        if cached:
            cmd.append('--cached')
        if files:
            cmd.extend(files)

        # Run it!
        self._run_command(cmd)
        # popd
        os.chdir(oldpath)
        return

    def get_latest_commit(self, module, branch):
        """Discover the latest commit has for a given module and return it"""

        # This is stupid that I have to use subprocess :/
        url = self._get_namespace_anongiturl(module)
        # This cmd below only works to scratch build rawhide
        # We need something better for epel
        cmd = ['git', 'ls-remote', url, 'refs/heads/%s' % branch]
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError as e:
            raise rpkgError(e)
        if error:
            raise rpkgError('Got an error finding %s head for %s: %s'
                            % (branch, module, error))
        # Return the hash sum
        if not output:
            raise rpkgError('Could not find remote branch %s for %s'
                            % (branch, module))
        return output.split()[0]

    def gitbuildhash(self, build):
        """Determine the git hash used to produce a particular N-V-R"""

        # Get the build data from the nvr
        self.log.debug('Getting task data from the build system')
        bdata = self.anon_kojisession.getBuild(build)
        if not bdata:
            raise rpkgError('Unknown build: %s' % build)

        # Get the task data out of that build data
        taskinfo = self.anon_kojisession.getTaskRequest(bdata['task_id'])
        # taskinfo is a list of items, first item is the task url.
        # second is the build target.
        # See if the build target starts with cvs or git
        hash = None
        buildsource = taskinfo[0]
        if buildsource.startswith('cvs://'):
            # snag everything after the last # mark
            cvstag = buildsource.rsplit('#')[-1]
            # Now read the remote repo to figure out the hash from the tag
            giturl = self._get_namespace_anongiturl(bdata['name'])
            cmd = ['git', 'ls-remote', '--tags', giturl, cvstag]
            self.log.debug('Querying git server for tag info')
            try:
                output = subprocess.check_output(cmd)
                hash = output.split()[0]
            except:
                # don't do anything here, we'll handle not having hash
                # later
                pass
        elif buildsource.startswith('git://'):
            # Match a 40 char block of text on the url line, that'll be
            # our hash
            hash = buildsource.rsplit('#')[-1]
        else:
            # Unknown build source
            raise rpkgError('Unhandled build source %s' % buildsource)
        if not hash:
            raise rpkgError('Could not find hash of build %s' % build)
        return (hash)

    def import_srpm(self, srpm):
        """Import the contents of an srpm into a repo.

        srpm: File to import contents from

        This function will add/remove content to match the srpm,

        upload new files to the lookaside, and stage the changes.

        Returns a list of files to upload.

        """
        # bail if we're dirty
        if self.repo.is_dirty():
            raise rpkgError('There are uncommitted changes in your repo')
        # see if the srpm even exists
        srpm = os.path.abspath(srpm)
        if not os.path.exists(srpm):
            raise rpkgError('File not found.')
        # Get the details of the srpm
        name, files, uploadfiles = self._srpmdetails(srpm)

        # Need a way to make sure the srpm name matches the repo some how.

        # Get a list of files we're currently tracking
        ourfiles = self.repo.git.ls_files().split('\n')
        if ourfiles == ['']:
            # Repository doesn't contain any files
            ourfiles = []
        else:
            # Trim out sources and .gitignore
            for file in ('.gitignore', 'sources'):
                try:
                    ourfiles.remove(file)
                except ValueError:
                    pass

        # Things work better if we're in our module directory
        oldpath = os.getcwd()
        os.chdir(self.path)

        # Look through our files and if it isn't in the new files, remove it.
        for file in ourfiles:
            if file not in files:
                self.log.info("Removing no longer used file: %s", file)
                self.repo.index.remove([file])
                os.remove(file)

        # Extract new files
        cmd = ['rpm2cpio', srpm]
        # We have to force cpio to copy out (u) because git messes with
        # timestamps
        cmd2 = ['cpio', '-iud', '--quiet']

        rpmcall = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        cpiocall = subprocess.Popen(cmd2, stdin=rpmcall.stdout)
        output, err = cpiocall.communicate()
        if output:
            self.log.debug(output)
        if err:
            os.chdir(oldpath)
            raise rpkgError("Got an error from rpm2cpio: %s" % err)

        # And finally add all the files we know about (and our stock files)
        for file in ('.gitignore', 'sources'):
            if not os.path.exists(file):
                # Create the file
                open(file, 'w').close()
            files.append(file)
        self.repo.index.add(files)
        # Return to the caller and let them take it from there.
        os.chdir(oldpath)
        return [os.path.join(self.path, file) for file in uploadfiles]

    def list_tag(self, tagname='*'):
        """List all tags in the repository which match a given tagname.

        The optional `tagname` argument may be a shell glob (it is matched
        with fnmatch).

        """
        if tagname is None:
            tagname = '*'

        tags = map(lambda t: t.name, self.repo.tags)

        if tagname != '*':
            tags = filter(lambda t: fnmatch.fnmatch(t, tagname), tags)

        for tag in tags:
            print(tag)

    def new(self):
        """Return changes in a repo since the last tag"""

        # Find the latest tag
        try:
            tag = self.repo.git.describe('--tags', '--abbrev=0')
        except git.exc.GitCommandError:
            raise rpkgError('Cannot get changes because there are no tags in this repo.')
        # Now get the diff
        self.log.debug('Diffing from tag %s', tag)
        return self.repo.git.diff('-M', tag)

    def patch(self, suffix, rediff=False):
        """Generate a patch from the expanded source and add it to index

        suffix: Look for files named with this suffix to diff
        rediff: optionally retain any comments in the patch file and rediff

        Will create a patch file named name-version-suffix.patch
        """

        # Create the outfile name based on arguments
        outfile = '%s-%s-%s.patch' % (self.module_name, self.ver, suffix)

        # If we want to rediff, the patch file has to already exist
        if rediff and not os.path.exists(os.path.join(self.path, outfile)):
            raise rpkgError('Patch file %s not found, unable to rediff' %
                            os.path.join(self.path, outfile))

        # See if there is a source dir to diff in
        if not os.path.isdir(os.path.join(self.path,
                                          '%s-%s' % (self.module_name,
                                                     self.ver))):
            raise rpkgError('Expanded source dir not found!')

        # Setup the command
        cmd = ['gendiff', '%s-%s' % (self.module_name, self.ver),
               '.%s' % suffix]

        # Try to run the command and capture the output
        try:
            self.log.debug('Running %s', ' '.join(cmd))
            (output, errors) = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                cwd=self.path).communicate()
        except Exception as e:
            raise rpkgError('Error running gendiff: %s' % e)

        # log any errors
        if errors:
            self.log.error(errors)

        # See if we got anything
        if not output:
            raise rpkgError('gendiff generated an empty patch!')

        # See if we are rediffing and handle the old patch file
        if rediff:
            oldpatch = open(os.path.join(self.path, outfile), 'r').readlines()
            # back up the old file
            self.log.debug('Moving existing patch %s to %s~', outfile, outfile)
            os.rename(os.path.join(self.path, outfile),
                      '%s~' % os.path.join(self.path, outfile))
            # Capture the lines preceding the diff
            newhead = []
            for line in oldpatch:
                if line.startswith('diff'):
                    break
                else:
                    newhead.append(line)

            log.debug('Saved from previous patch: \n%s' % ''.join(newhead))
            # Stuff the new head in front of the existing output
            output = ''.join(newhead) + output

        # Write out the patch
        open(os.path.join(self.path, outfile), 'w').write(output)

        # Add it to the index
        # Again this returns a blank line we want to keep quiet
        self.repo.index.add([outfile])
        log.info('Created %s and added it to the index' % outfile)

    def pull(self, rebase=False, norebase=False):
        """Pull changes from the remote repository

        Optionally rebase current branch on top of remote branch

        Optionally override .git setting to always rebase

        """

        cmd = ['git', 'pull']
        if self.quiet:
            cmd.append('-q')
        if rebase:
            cmd.append('--rebase')
        if norebase:
            cmd.append('--no-rebase')
        self._run_command(cmd, cwd=self.path)
        return

    def find_untracked_patches(self):
        """Find patches that are not tracked by git and sources both"""
        file_pattern = os.path.join(self.path, '*.patch')
        patches_in_repo = [os.path.basename(filename) for filename
                           in glob.glob(file_pattern)]

        git_tree = self.repo.head.commit.tree
        sources_file = SourcesFile(self.sources_filename,
                                   self.source_entry_type)

        patches_not_tracked = [
            patch for patch in patches_in_repo
            if patch not in git_tree and patch not in sources_file]

        return patches_not_tracked

    def push(self, force=False):
        """Push changes to the remote repository"""

        # see if our branch is tracking anything
        try:
            self.load_branch_merge()
        except:
            self.log.warning('Current branch cannot be pushed anywhere!')

        untracked_patches = self.find_untracked_patches()
        if untracked_patches:
            self.log.warning(
                'Patches %s %s not tracked within either git or sources',
                ', '.join(untracked_patches),
                'is' if len(untracked_patches) == 1 else 'are')

        cmd = ['git', 'push']
        if self.quiet:
            cmd.append('-q')
        self._run_command(cmd, cwd=self.path)

    def sources(self, outdir=None):
        """Download source files"""

        if not os.path.exists(self.sources_filename):
            self.log.info("sources file doesn't exist. Source files download skipped.")
            return

        # Default to putting the files where the module is
        if not outdir:
            outdir = self.path

        sourcesf = SourcesFile(self.sources_filename, self.source_entry_type)

        for entry in sourcesf.entries:
            outfile = os.path.join(outdir, entry.file)
            self.lookasidecache.download(
                self.module_name, entry.file, entry.hash, outfile,
                hashtype=entry.hashtype, branch=self.branch_merge)

    def switch_branch(self, branch, fetch=True):
        """Switch the working branch

        Will create a local branch if one doesn't already exist,
        based on <remote>/<branch>

        Logs output and returns nothing.
        """

        # Currently this just grabs the first matching branch name from
        # the first remote it finds.  When multiple remotes are in play
        # this needs to get smarter

        # See if the repo is dirty first
        if self.repo.is_dirty():
            raise rpkgError('%s has uncommitted changes.  Use git status '
                            'to see details' % self.path)

        # Get our list of branches
        (locals, remotes) = self._list_branches(fetch)

        if branch not in locals:
            # We need to create a branch
            self.log.debug('No local branch found, creating a new one')
            totrack = None
            full_branch = '%s/%s' % (self.branch_remote, branch)
            for remote in remotes:
                if remote == full_branch:
                    totrack = remote
                    break
            else:
                raise rpkgError('Unknown remote branch %s' % full_branch)
            try:
                self.log.info(self.repo.git.checkout('-b', branch, '--track', totrack))
            except Exception as err:
                # This needs to be finer grained I think...
                raise rpkgError('Could not create branch %s: %s'
                                % (branch, err))
        else:
            try:
                self.repo.git.checkout(branch)
                # The above should have no output, but stash it anyway
                self.log.info("Switched to branch '%s'", branch)
            except Exception as err:
                # This needs to be finer grained I think...
                raise rpkgError('Could not check out %s\n%s' % (branch,
                                                                err.stderr))
        return

    def check_repo(self, is_dirty=True, all_pushed=True):
        """Check various status of current repository

        :param bool is_dirty: Default to True. To check whether there is uncommitted changes.
        :param bool all_pushed: Default to True. To check whether all changes are pushed.
        :raises rpkgError: if any unexpected status is detected. For example,
            if changes are not committed yet.
        """
        if is_dirty:
            if self.repo.is_dirty():
                raise rpkgError('%s has uncommitted changes.  Use git status '
                                'to see details' % self.path)
        if all_pushed:
            branch = self.repo.active_branch
            remote = self.repo.git.config('--get', 'branch.%s.remote' % branch)
            merge = self.repo.git.config('--get', 'branch.%s.merge' % branch).replace('refs/heads',
                                                                                      remote)
            if self.repo.git.rev_list('%s...%s' % (merge, branch)):
                raise rpkgError('There are unpushed changes in your repo')

    def build(self, skip_tag=False, scratch=False, background=False,
              url=None, chain=None, arches=None, sets=False, nvr_check=True):
        """Initiate a build of the module.  Available options are:

        skip_tag: Skip the tag action after the build

        scratch: Perform a scratch build

        background: Perform the build with a low priority

        url: A url to an uploaded srpm to build from

        chain: A chain build set

        arches: A set of arches to limit the scratch build for

        sets: A boolean to let us know whether or not the chain has sets

        nvr_check: A boolean; locally construct NVR and submit a build only if
                   NVR doesn't exist in a build system

        This function submits the task to koji and returns the taskID

        It is up to the client to wait or watch the task.
        """

        # Ensure the repo exists as well as repo data and site data
        # build up the command that a user would issue
        cmd = [self.build_client]
        # construct the url
        if not url:
            # We don't have a url, so build from the latest commit
            # Check to see if the tree is dirty and if all local commits
            # are pushed
            self.check_repo()
            url = self._get_namespace_anongiturl(self.ns_module_name) + \
                '?#%s' % self.commithash
        # Check to see if the target is valid
        build_target = self.kojisession.getBuildTarget(self.target)
        if not build_target:
            raise rpkgError('Unknown build target: %s' % self.target)
        # see if the dest tag is locked
        dest_tag = self.kojisession.getTag(build_target['dest_tag_name'])
        if not dest_tag:
            raise rpkgError('Unknown destination tag %s'
                            % build_target['dest_tag_name'])
        if dest_tag['locked'] and not scratch:
            raise rpkgError('Destination tag %s is locked' % dest_tag['name'])
        # If we're chain building, make sure inheritance works
        if chain:
            cmd.append('chain-build')
            ancestors = self.kojisession.getFullInheritance(
                build_target['build_tag'])
            ancestors = [ancestor['parent_id'] for ancestor in ancestors]
            if dest_tag['id'] not in [build_target['build_tag']] + ancestors:
                raise rpkgError('Packages in destination tag '
                                '%(dest_tag_name)s are not inherited by'
                                'build tag %(build_tag_name)s' %
                                build_target)
        else:
            cmd.append('build')
        # define our dictionary for options
        opts = {}
        # Set a placeholder for the build priority
        priority = None
        if skip_tag:
            opts['skip_tag'] = True
            cmd.append('--skip-tag')
        if scratch:
            opts['scratch'] = True
            cmd.append('--scratch')
        if background:
            cmd.append('--background')
            priority = 5  # magic koji number :/
        if arches:
            if not scratch:
                raise rpkgError('Cannot override arches for non-scratch '
                                'builds')
            for arch in arches:
                if not re.match(r'^[0-9a-zA-Z_.]+$', arch):
                    raise rpkgError('Invalid architecture name: %s' % arch)
            cmd.append('--arch-override=%s' % ','.join(arches))
            opts['arch_override'] = ' '.join(arches)

        cmd.append(self.target)

        if url.endswith('.src.rpm'):
            srpm = os.path.basename(url)
            build_reference = srpm
        else:
            try:
                build_reference = self.nvr
            except rpkgError as error:
                self.log.warning(error)
                if nvr_check:
                    self.log.info('Note: You can skip NVR construction & NVR'
                                  ' check with --skip-nvr-check. See help for'
                                  ' more info.')
                    raise rpkgError('Cannot continue without properly constructed NVR.')
                else:
                    self.log.info('NVR checking will be skipped so I do not'
                                  ' care that I am not able to construct NVR.'
                                  '  I will refer this build by package name'
                                  ' in following messages.')
                    build_reference = self.module_name

        # see if this build has been done.  Does not check builds within
        # a chain
        if nvr_check and not scratch and not url.endswith('.src.rpm'):
            build = self.kojisession.getBuild(self.nvr)
            if build:
                if build['state'] == 1:
                    raise rpkgError('Package %s has already been built\n'
                                    'Note: You can skip this check with'
                                    ' --skip-nvr-check. See help for more'
                                    ' info.' % self.nvr)
        # Now submit the task and get the task_id to return
        # Handle the chain build version
        if chain:
            self.log.debug('Adding %s to the chain', url)
            # If we're dealing with build sets the behaviour of the last
            # package changes, and we add it to the last (potentially empty)
            # set.  Otherwise the last package just gets added to the end of
            # the chain.
            if sets:
                chain[-1].append(url)
            else:
                chain.append([url])
            # This next list comp is ugly, but it's how we properly get a :
            # put in between each build set
            cmd.extend(' : '.join([' '.join(build_sets) for build_sets in chain]).split())
            self.log.info('Chain building %s + %s for %s', build_reference, chain[:-1], self.target)
            self.log.debug('Building chain %s for %s with options %s and a priority of %s',
                           chain, self.target, opts, priority)
            self.log.debug(' '.join(cmd))
            task_id = self.kojisession.chainBuild(chain, self.target, opts, priority=priority)
        # Now handle the normal build
        else:
            cmd.append(url)
            self.log.info('Building %s for %s', build_reference, self.target)
            self.log.debug('Building %s for %s with options %s and a priority of %s',
                           url, self.target, opts, priority)
            self.log.debug(' '.join(cmd))
            task_id = self.kojisession.build(url, self.target, opts, priority=priority)
        self.log.info('Created task: %s', task_id)
        self.log.info('Task info: %s/taskinfo?taskID=%s', self.kojiweburl, task_id)
        return task_id

    def clog(self, raw=False):
        """Write the latest spec changelog entry to a clog file"""

        spec_file = os.path.join(self.path, self.spec)
        cmd = ['rpm', '-q', '--qf', '%{CHANGELOGTEXT}\n', '--specfile', spec_file]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        if proc.returncode > 0:
            raise rpkgError(stderr.strip())

        clog_lines = []
        buf = six.StringIO(stdout)
        for line in buf:
            if line == '\n' or line.startswith('$'):
                continue
            if line == '(none)\n':
                # (none) may appear as the last line in changelog got from SPEC
                # file. In some cases, e.g. there is only one changelog entry
                # in SPEC, no (none) line presents. Thus, when for loop ends, all
                # lines of changelog are handled.
                break
            if raw:
                clog_lines.append(line)
            else:
                clog_lines.append(line.replace('- ', '', 1))
        buf.close()

        # Now open the clog file and write out the lines
        with open(os.path.join(self.path, 'clog'), 'w') as clog:
            clog.writelines(clog_lines)

    def compile(self, arch=None, short=False, builddir=None, nocheck=False):
        """Run rpmbuild -bc on a module

        optionally for a specific arch, or short-circuit it, or
        define an alternate builddir

        Logs the output and returns nothing
        """

        # setup the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        if arch:
            cmd.extend(['--target', arch])
        if short:
            cmd.append('--short-circuit')
        if nocheck:
            cmd.append('--nocheck')
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['-bc', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

    def giturl(self):
        """Return the git url that would be used for building"""

        url = self._get_namespace_anongiturl(self.ns_module_name) + \
            '?#%s' % self.commithash
        return url

    def koji_upload(self, file, path, callback=None):
        """Upload a file to koji

        file is the file you wish to upload

        path is the relative path on the server to upload to

        callback is the progress callback to use, if any

        Returns nothing or raises
        """

        # See if we actually have a file
        if not os.path.exists(file):
            raise rpkgError('No such file: %s' % file)
        if not self.kojisession:
            raise rpkgError('No active %s session.' %
                            os.path.basename(self.build_client))
        # This should have a try and catch koji errors
        self.kojisession.uploadWrapper(file, path, callback=callback)

    def install(self, arch=None, short=False, builddir=None, nocheck=False):
        """Run rpm -bi on a module

        optionally for a specific arch, short-circuit it, or
        define an alternative builddir

        Logs the output and returns nothing
        """

        # setup the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        if arch:
            cmd.extend(['--target', arch])
        if short:
            cmd.append('--short-circuit')
        if nocheck:
            cmd.append('--nocheck')
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['-bi', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)
        return

    def lint(self, info=False, rpmlintconf=None):
        """Run rpmlint over a built srpm

        Log the output and returns nothing
        rpmlintconf is the name of the config file passed to rpmlint if
        specified by the command line argument.
        """

        # Check for srpm
        srpm = "%s-%s-%s.src.rpm" % (self.module_name, self.ver, self.rel)
        if not os.path.exists(os.path.join(self.path, srpm)):
            log.warning('No srpm found')

        # Get the possible built arches
        arches = self._get_build_arches_from_spec()
        rpms = []
        for arch in arches:
            if os.path.exists(os.path.join(self.path, arch)):
                # For each available arch folder, lists file and keep
                # those ending with .rpm
                rpms.extend([os.path.join(self.path, arch, file)
                             for file in os.listdir(os.path.join(self.path,
                                                    arch))
                             if file.endswith('.rpm')])
        if not rpms:
            log.warning('No rpm found')
        cmd = ['rpmlint']
        if info:
            cmd.extend(['-i'])
        if rpmlintconf:
            cmd.extend(["-f", os.path.join(self.path, rpmlintconf)])
        elif os.path.exists(os.path.join(self.path, ".rpmlint")):
            cmd.extend(["-f", os.path.join(self.path, ".rpmlint")])
        cmd.append(os.path.join(self.path, self.spec))
        if os.path.exists(os.path.join(self.path, srpm)):
            cmd.append(os.path.join(self.path, srpm))
        cmd.extend(rpms)
        # Run the command
        self._run_command(cmd, shell=True)

    def local(self, arch=None, hashtype=None, builddir=None):
        """rpmbuild locally for given arch.

        Takes arch to build for, and hashtype to build with.

        Writes output to a log file and logs it to the logger

        Returns the returncode from the build call
        """

        # This could really use a list of arches to build for and loop over
        # Get the sources
        # build up the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        # Figure out the hash type to use
        if not hashtype:
            # Try to determine the dist
            hashtype = self._guess_hashtype()
        # This may need to get updated if we ever change our checksum default
        if not hashtype == 'sha256':
            cmd.extend(["--define '_source_filedigest_algorithm %s'"
                        % hashtype,
                        "--define '_binary_filedigest_algorithm %s'"
                        % hashtype])
        if arch:
            cmd.extend(['--target', arch])
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['-ba', os.path.join(self.path, self.spec)])
        logfile = '.build-%s-%s.log' % (self.ver, self.rel)
        # Run the command
        self._run_command(cmd, shell=True, pipe=['tee', logfile])

    # Not to be confused with mockconfig the property
    def mock_config(self, target=None, arch=None):
        """Generate a mock config based on branch data.

        Can use option target and arch to override autodiscovery.
        Will return the mock config file text.
        """

        # Figure out some things about ourself.
        if not target:
            target = self.target
        if not arch:
            arch = self.localarch

        # Figure out if we have a valid build target
        build_target = self.anon_kojisession.getBuildTarget(target)
        if not build_target:
            raise rpkgError('Unknown build target: %s\n'
                            'Consider using the --target option' % target)

        try:
            repoid = self.anon_kojisession.getRepo(
                build_target['build_tag_name'])['id']
        except Exception:
            raise rpkgError('Could not find a valid build repo')

        # Generate the config
        config = koji.genMockConfig('%s-%s' % (target, arch), arch,
                                    distribution=self.disttag,
                                    tag_name=build_target['build_tag_name'],
                                    repoid=repoid,
                                    topurl=self.topurl)

        # Return the mess
        return(config)

    def _config_dir_other(self, config_dir, filenames=('site-defaults.cfg',
                                                       'logging.ini')):
        """Populates mock config directory with other necessary files

        If files are found in system config directory for mock they are copied
        to mock config directory defined as method's argument. Otherwise empty
        files are created."""
        for filename in filenames:
            system_filename = '/etc/mock/%s' % filename
            tmp_filename = os.path.join(config_dir, filename)
            if os.path.exists(system_filename):
                try:
                    shutil.copy2(system_filename, tmp_filename)
                except Exception as error:
                    raise rpkgError('Failed to create copy system config file'
                                    ' %s: %s' % (filename, error))
            else:
                try:
                    open(tmp_filename, 'w').close()
                except Exception as error:
                    raise rpkgError('Failed to create empty mock config'
                                    ' file %s: %s'
                                    % (tmp_filename, error))

    def _config_dir_basic(self, config_dir=None, root=None):
        """Setup directory with essential mock config

        If config directory doesn't exist it will be created. If temporary
        directory was created by this method and error occours during
        processing, temporary directory is removed. Otherwise it caller's
        responsibility to remove this directory.

        Returns used config directory"""
        if not root:
            root = self.mockconfig
        if not config_dir:
            my_config_dir = tempfile.mkdtemp(prefix="%s." % root,
                                             suffix='mockconfig')
            config_dir = my_config_dir
            self.log.debug('New mock config directory: %s', config_dir)
        else:
            my_config_dir = None

        try:
            config_content = self.mock_config()
        except rpkgError as error:
            self._cleanup_tmp_dir(my_config_dir)
            raise rpkgError('Could not generate config file: %s'
                            % error)

        config_file = os.path.join(config_dir, '%s.cfg' % root)
        try:
            open(config_file, 'wb').write(config_content)
        except IOError as error:
            self._cleanup_tmp_dir(my_config_dir)
            raise rpkgError('Could not write config file: %s' % error)

        return config_dir

    def _cleanup_tmp_dir(self, tmp_dir):
        """Tries to remove directory and ignores EEXIST error

        If occoured directory not exist error (EEXIST) it silently continue.
        Otherwise raise rpkgError exception."""
        if not tmp_dir:
            return
        try:
            shutil.rmtree(tmp_dir)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise rpkgError('Failed to remove temporary directory'
                                ' %s. Reason: %s.' % (tmp_dir, error))

    def mockbuild(self, mockargs=[], root=None, hashtype=None):
        """Build the package in mock, using mockargs

        Log the output and returns nothing
        """

        # Make sure we have an srpm to run on
        self.srpm(hashtype=hashtype)

        # setup the command
        cmd = ['mock']
        cmd.extend(mockargs)
        if self.quiet:
            cmd.append('--quiet')

        config_dir = None
        if not root:
            root = self.mockconfig
            chroot_cfg = '/etc/mock/%s.cfg' % root
            if not os.path.exists(chroot_cfg):
                self.log.debug('Mock config %s was not found. Going to'
                               ' request koji to create new one.', chroot_cfg)
                try:
                    config_dir = self._config_dir_basic(root=root)
                except rpkgError as error:
                    raise rpkgError('Failed to create mock config directory:'
                                    ' %s' % error)
                self.log.debug('Temporary mock config directory: %s', config_dir)
                try:
                    self._config_dir_other(config_dir)
                except rpkgError as error:
                    self._cleanup_tmp_dir(config_dir)
                    raise rpkgError('Failed to populate mock config directory:'
                                    ' %s' % error)
                cmd.extend(['--configdir', config_dir])

        cmd.extend(['-r', root, '--resultdir', self.mock_results_dir,
                    '--rebuild', self.srpmname])
        # Run the command
        try:
            self._run_command(cmd)
        finally:
            self.log.debug('Cleaning up mock temporary config directory: %s', config_dir)
            self._cleanup_tmp_dir(config_dir)

    def upload(self, files, replace=False):
        """Upload source file(s) in the lookaside cache

        Can optionally replace the existing tracked sources
        """

        sourcesf = SourcesFile(self.sources_filename, self.source_entry_type,
                               replace=replace)
        gitignore = GitIgnore(os.path.join(self.path, '.gitignore'))

        for f in files:
            # TODO: Skip empty file needed?
            file_hash = self.lookasidecache.hash_file(f)
            file_basename = os.path.basename(f)

            try:
                sourcesf.add_entry(self.lookasidehash, file_basename,
                                   file_hash)
            except HashtypeMixingError as e:
                msg = '\n'.join([
                    'Can not upload a new source file with a %(newhash)s '
                    'hash, as the "%(sources)s" file contains at least one '
                    'line with a %(existinghash)s hash.', '',
                    'Please redo the whole "%(sources)s" file using:',
                    '    `%(arg0)s new-sources file1 file2 ...`']) % {
                        'newhash': e.new_hashtype,
                        'existinghash': e.existing_hashtype,
                        'sources': self.sources_filename,
                        'arg0': sys.argv[0],
                    }
                raise rpkgError(msg)

            gitignore.add('/%s' % file_basename)
            self.lookasidecache.upload(self.module_name, f, file_hash)

        sourcesf.write()
        gitignore.write()

        self.repo.index.add(['sources', '.gitignore'])

    def prep(self, arch=None, builddir=None):
        """Run rpm -bp on a module

        optionally for a specific arch, or
        define an alternative builddir

        Logs the output and returns nothing
        """

        # setup the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        if arch:
            cmd.extend(['--target', arch])
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['--nodeps', '-bp', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

    def srpm(self, hashtype=None):
        """Create an srpm using hashtype from content in the module

        Requires sources already downloaded.
        """

        self.srpmname = os.path.join(self.path,
                                     "%s-%s-%s.src.rpm"
                                     % (self.module_name, self.ver, self.rel))

        # See if we need to build the srpm
        if os.path.exists(self.srpmname):
            self.log.debug('Srpm found, rewriting it.')

        cmd = ['rpmbuild']
        cmd.extend(self.rpmdefines)
        if self.quiet:
            cmd.append('--quiet')
        # Figure out which hashtype to use, if not provided one
        if not hashtype:
            # Try to determine the dist
            hashtype = self._guess_hashtype()
        # This may need to get updated if we ever change our checksum default
        if not hashtype == 'sha256':
            cmd.extend(["--define '_source_filedigest_algorithm %s'"
                        % hashtype,
                        "--define '_binary_filedigest_algorithm %s'"
                        % hashtype])
        cmd.extend(['--nodeps', '-bs', os.path.join(self.path, self.spec)])
        self._run_command(cmd, shell=True)

    def unused_patches(self):
        """Discover patches checked into source control that are not used

        Returns a list of unused patches, which may be empty.
        """

        # Create a list for unused patches
        unused = []
        # Get the content of spec into memory for fast searching
        with open(os.path.join(self.path, self.spec), 'r') as f:
            data = f.read()
        try:
            spec = data.decode('UTF-8')
        except UnicodeDecodeError as error:
            # when can't decode file, ignore chars and show warning
            spec = data.decode('UTF-8', 'ignore')
            line, offset = self._byte_offset_to_line_number(spec, error.start)
            self.log.warning("'%s' codec can't decode byte in position %d:%d : %s",
                             error.encoding, line, offset, error.reason)
        # Replace %{name} with the package name
        spec = spec.replace("%{name}", self.module_name)
        # Replace %{version} with the package version
        spec = spec.replace("%{version}", self.ver)

        # Get a list of files tracked in source control
        files = self.repo.git.ls_files('--exclude-standard').split()
        for file in files:
            # throw out non patches
            if not file.endswith(('.patch', '.diff')):
                continue
            if file not in spec:
                unused.append(file)
        return unused

    def _byte_offset_to_line_number(self, text, offset):
        """
        Convert byte offset (given by e.g. DecodeError) to human readable
        format (line number and char position)
        Return a list with line number and char offset
        """
        offset_inc = 0
        line_num = 1
        for line in text.split('\n'):
            if offset_inc + len(line) + 1 > offset:
                break
            else:
                offset_inc += len(line) + 1
                line_num += 1
        return [line_num, offset - offset_inc + 1]

    def verify_files(self, builddir=None):
        """Run rpmbuild -bl on a module to verify the %files section

        optionally define an alternate builddir
        """

        # setup the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        if self.quiet:
            cmd.append('--quiet')
        cmd.extend(['-bl', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

    def osbs_build(self, config_file, config_section, target_override=False,
                   yum_repourls=[], nowait=False):
        self.check_repo()
        os_conf = Configuration(conf_file=config_file, conf_section=config_section)
        build_conf = Configuration(conf_file=config_file, conf_section=config_section)
        osbs = OSBS(os_conf, build_conf)

        git_uri = re.sub(r"^git\+ssh", "git", self.push_url)
        git_uri = re.sub("^ssh", "git", git_uri)
        git_uri = re.sub("[^/]+@", "", git_uri)
        git_ref = self.commithash
        git_branch = self.branch_merge
        user = self.user
        component = self.module_name
        docker_target = self.target
        if not target_override:
            # Translate the build target into a docker target,
            # but only if --target wasn't specified on the command-line
            docker_target = '%s-docker-candidate' % self.target.split('-candidate')[0]

        build = osbs.create_build(
            git_uri=git_uri,
            git_ref=git_ref,
            git_branch=git_branch,
            user=user,
            component=component,
            target=docker_target,
            architecture="x86_64",
            yum_repourls=yum_repourls
        )
        build_id = build.build_id

        if nowait:
            self.log.info('Build submitted: %s', build_id)
            return

        print("Build submitted (%s), watching logs (feel free to interrupt)" % build_id)
        for line in osbs.get_build_logs(build_id, follow=True):
            print(line)
        build_response = osbs.wait_for_build_to_finish(build_id)
        if build_response.is_succeeded():
            repositories = build_response.get_repositories()
            if repositories:
                image_names = repositories.get("primary", []) + repositories.get("unique", [])
                print("You can pull the image with one of the following commands:")
                for image in image_names:
                    print("  docker pull %s" % image)
            else:
                raise RuntimeError(
                    "Build '%s' wasn't processed correctly. Please, report this." % build_id)
        else:
            raise RuntimeError("Build has failed.")

    def container_build_koji(self, target_override=False, opts={},
                             kojiconfig=None, build_client=None,
                             koji_task_watcher=None,
                             nowait=False):
        # check if repo is dirty and all commits are pushed
        self.check_repo()
        docker_target = self.target
        if not target_override:
            # Translate the build target into a docker target,
            # but only if --target wasn't specified on the command-line
            docker_target = '%s-docker-candidate' % self.target.split('-candidate')[0]

        koji_session_backup = (self.build_client, self.kojiconfig)
        (self.build_client, self.kojiconfig) = (build_client, kojiconfig)
        try:
            self.load_kojisession()
            if "buildContainer" not in self.kojisession.system.listMethods():
                raise RuntimeError("Kojihub instance does not support buildContainer")

            build_target = self.kojisession.getBuildTarget(docker_target)
            if not build_target:
                msg = "Unknown build target: %s" % docker_target
                self.log.error(msg)
                raise UnknownTargetError(msg)
            else:
                dest_tag = self.kojisession.getTag(build_target['dest_tag'])
                if not dest_tag:
                    self.log.error("Unknown destination tag: %s", build_target['dest_tag_name'])
                if dest_tag['locked'] and 'scratch' not in opts:
                    self.log.error("Destination tag %s is locked", dest_tag['name'])

            source = self._get_namespace_anongiturl(self.ns_module_name)
            source += "#%s" % self.commithash

            task_opts = {}
            for key in ('scratch', 'name', 'version', 'release',
                        'yum_repourls', 'git_branch'):
                if key in opts:
                    task_opts[key] = opts[key]
            priority = opts.get("priority", None)
            task_id = self.kojisession.buildContainer(source,
                                                      docker_target,
                                                      task_opts,
                                                      priority=priority)
            self.log.info('Created task: %s', task_id)
            self.log.info('Task info: %s/taskinfo?taskID=%s', self.kojiweburl, task_id)
            if not nowait:
                rv = koji_task_watcher(self.kojisession, [task_id])
                if rv == 0:
                    result = self.kojisession.getTaskResult(task_id)
                    try:
                        result["koji_builds"] = [
                            "%s/buildinfo?buildID=%s" % (self.kojiweburl,
                                                         build_id)
                            for build_id in result.get("koji_builds", [])]
                    except TypeError:
                        pass
                    log_result(self.log.info, result)

        finally:
            (self.build_client, self.kojiconfig) = koji_session_backup
            self.load_kojisession()

    def container_build_setup(self, get_autorebuild=None,
                              set_autorebuild=None):
        cfp = configparser.SafeConfigParser()
        if os.path.exists(self.osbs_config_filename):
            cfp.read(self.osbs_config_filename)

        if get_autorebuild is not None:
            if not cfp.has_option('autorebuild', 'enabled'):
                self.log.info('true')
            else:
                self.log.info('true' if cfp.getboolean('autorebuild', 'enabled') else 'false')
        elif set_autorebuild is not None:
            if not cfp.has_section('autorebuild'):
                cfp.add_section('autorebuild')

            cfp.set('autorebuild', 'enabled', set_autorebuild)
            with open(self.osbs_config_filename, 'w') as fp:
                cfp.write(fp)

            self.repo.index.add([self.osbs_config_filename])
            self.log.info("Config value changed, don't forget to commit %s file",
                          self.osbs_config_filename)
        else:
            self.log.info('Nothing to be done')

    def copr_build(self, project, srpm_name, nowait):
        cmd = ['copr-cli', 'build']
        if nowait:
            cmd.append('--nowait')
        cmd.extend([project, srpm_name])
        self._run_command(cmd)
