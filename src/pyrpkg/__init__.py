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

import os
import sys
import shutil
import re
import pycurl
if sys.version_info[0:2] >= (2, 5):
    import subprocess
else:
    # We need a subprocess that has check_call
    from kitchen.pycompat27 import subprocess
import hashlib
import koji
import rpm
import logging
import git
import ConfigParser
import stat
import StringIO
import fnmatch
import cli
# Try to import krb, it's OK if it fails
try:
    import krbV
except ImportError:
    pass


# Define our own error class
class rpkgError(Exception):
    pass

# Setup our logger
# Null logger to avoid spurrious messages, add a handler in app code
class NullHandler(logging.Handler):
    def emit(self, record):
        pass

h = NullHandler()
# This is our log object, clients of this library can use this object to
# define their own logging needs
log = logging.getLogger("rpkg")
# Add the null handler
log.addHandler(h)

class Commands(object):
    """This is a class to hold all the commands that will be called
    by clients
    """

    def __init__(self, path, lookaside, lookasidehash, lookaside_cgi,
                 gitbaseurl, anongiturl, branchre, kojiconfig,
                 build_client, user=None, dist=None, target=None):
        """Init the object and some configuration details."""

        # Path to operate on, most often pwd
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
        self.kojiconfig = kojiconfig
        # The buildsys client to use
        self.build_client = build_client
        # A way to override the discovered "distribution"
        self.dist = dist
        # Set the default hashtype
        self.hashtype = 'sha256'
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
        # The rpm version of the cloned module
        self._ver = None
        self.log = log

    # Define properties here
    # Properties allow us to "lazy load" various attributes, which also means
    # that we can do clone actions without knowing things like the spec
    # file or rpm data.
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
                    'server' : 'http://localhost/kojihub',
                    'weburl' : 'http://localhost/koji',
                    'pkgurl' : 'http://localhost/packages',
                    'topdir' : '/mnt/koji',
                    'cert': '~/.koji/client.crt',
                    'ca': '~/.koji/clientca.crt',
                    'serverca': '~/.koji/serverca.crt',
                    'authtype': None,
                    'topurl': None
                    }
        # Process the configs in order, global, user, then any option passed
        try:
            f = open(self.kojiconfig)
        except IOError as e:
            self.log.debug("Could not read %s, using the default koji config values")

        else:
            with f:
                config = ConfigParser.ConfigParser()
                config.readfp(f)

            if config.has_section(os.path.basename(self.build_client)):
                for name, value in config.items(os.path.basename(
                                                self.build_client)):
                    if defaults.has_key(name):
                        defaults[name] = value
        # Expand out the directory options
        for name in ('topdir', 'cert', 'ca', 'serverca', 'topurl'):
            if defaults[name]:
                defaults[name] = os.path.expanduser(defaults[name])
        self.log.debug('Initiating a %s session to %s' %
                       (os.path.basename(self.build_client),
                        defaults['server']))
        try:
            if not anon:
                session_opts = {'user': self.user}
                self._kojisession = koji.ClientSession(defaults['server'],
                                                       session_opts)
            else:
                self._anon_kojisession = koji.ClientSession(defaults['server'])
        except:
            raise rpkgError('Could not initiate %s session' %
                            os.path.basename(self.build_client))
        # save the weburl and topurl for later use too
        self._kojiweburl = defaults['weburl']
        self._topurl = defaults['topurl']
        if not anon:
                # Default to ssl if not otherwise specified and we have
                # the cert
                if defaults['authtype'] == 'ssl' or \
                os.path.isfile(defaults['cert']) and \
                defaults['authtype'] is None:
                    self._kojisession.ssl_login(defaults['cert'],
                                                defaults['ca'],
                                                defaults['serverca'])
                # Or try password auth
                elif defaults['authtype'] == 'password' or \
                'user' in defaults and defaults['authtype'] is None:
                    self._kojisession.login()
                # Or try kerberos
                elif defaults['authtype'] == 'kerberos' or \
                self._has_krb_creds() and \
                defaults['authtype'] is None:
                    self._kojisession.krb_login()
                if not self._kojisession.logged_in:
                    raise rpkgError('Could not auth with koji as %s' %
                                    self.user)

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
            except TypeError, e:
                raise rpkgError('Repo in inconsistent state: %s' % e)
            try:
                merge = self.repo.git.config('--get',
                                             'branch.%s.merge' % localbranch)
            except git.GitCommandError, e:
                raise rpkgError('Unable to find remote branch.  Use --dist')
            # Trim off the refs/heads so that we're just working with
            # the branch name
            merge = merge.replace('refs/heads/', '')
            self._branch_merge = merge

    @property
    def commithash(self):
        """This property ensures the commit attribute"""

        if not self._commit:
            self.load_commit()
        return self._commit

    def load_commit(self):
        """Discover the latest commit to the package"""

        # Get the commit hash
        comobj = self.repo.iter_commits().next()
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

        self._localarch = subprocess.Popen(['rpm --eval %{_arch}'],
                       shell=True,
                       stdout=subprocess.PIPE).communicate()[0].strip('\n')

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
        return(self._module_name)

    def load_module_name(self):
        """Set the base package name from the spec."""

        # get the name
        cmd = ['rpm', '-q', '--qf', '%{NAME} ', '--specfile', self.spec]
        # Run the command
        self.log.debug('Running: %s' % ' '.join(cmd))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    cwd=self.path, stderr=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError, e:
            raise rpkgError(e)
        if error:
            if sys.stdout.isatty():
                sys.stderr.write(error)
            else:
                # Yes, we could wind up sending error output to stdout in the
                # case of no local tty, but I don't have a better way to do this.
                self.log.info(error)
        if proc.returncode:
            raise rpkgError('Could not parse the spec, exited %s' %
                              proc.returncode)
        self._module_name = output.split()[0]

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
        # we can split it later.  When ther eare sub packages, we get a
        # listing for each subpackage.  We only care about the first.
        cmd.extend(['-q', '--qf', '"%{NAME} %{VERSION} %{RELEASE}??"',
                    '--specfile', os.path.join(self.path, self.spec)])
        try:
            output, err = subprocess.Popen(' '.join(cmd), shell=True,
                                      stderr=subprocess.PIPE,
                                      stdout=subprocess.PIPE).communicate()
        except Exception, e:
            if err:
                self.log.error(err)
            raise rpkgError('Could not query n-v-r of %s: %s' % (self.module_name,
                                                                 e))
        if err:
            self.log.error(err)
        # Get just the output, then split it by ??, grab the first and split
        # again to get ver and rel
        (self._module_name,
         self._ver,
         self._rel) = output.split('??')[0].split()

    @property
    def repo(self):
        """This property ensures the repo attribute"""

        if not self._repo:
            self.load_repo()
        return(self._repo)

    def load_repo(self):
        """Create a repo object from our path"""

        self.log.debug('Creating repo object from %s' % self.path)
        try:
            self._repo = git.Repo(self.path)
        except git.InvalidGitRepositoryError:
            raise rpkgError('%s is not a valid repo' % self.path)

    @property
    def rpmdefines(self):
        """This property ensures the rpm defines"""

        if not self._rpmdefines:
            self.load_rpmdefines()
        return(self._rpmdefines)

    def load_rpmdefines(self):
        """Populate rpmdefines based on branch data"""

        # This is another function ripe for subclassing

        try:
            # This regex should find the 'rhel-5' or 'rhel-6.2' parts of the
            # branch name.  There should only be one of those, and all branches
            # should end in one.
            osver = re.search(r'rhel-\d.*$', self.branch_merge).group()
        except AttributeError:
            raise rpkgError('Could not find the base OS ver from branch name \
                             %s' % self.branch_merge)
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
        self._user = os.getlogin()

    @property
    def ver(self):
        """This property ensures the ver attribute"""
        if not self._ver:
            self.load_nameverrel()
        return(self._ver)

    # Define some helper functions, they start with _
    def _create_curl(self):
        """
        Common curl setup options used for all requests to lookaside.
        """
        curl = pycurl.Curl()

        curl.setopt(pycurl.URL, self.lookaside_cgi)

        return curl

    def _has_krb_creds(self):
        # This function is lifted from /usr/bin/koji
        if not sys.modules.has_key('krbV'):
            return False
        try:
            ctx = krbV.default_context()
            ccache = ctx.default_ccache()
            princ = ccache.principal()
            return True
        except krbV.Krb5Error:
            return False

    def _hash_file(self, file, hashtype):
        """Return the hash of a file given a hash type"""

        try:
            sum = hashlib.new(hashtype)
        except ValueError:
            raise rpkgError('Invalid hash type: %s' % hashtype)

        input = open(file, 'rb')
        # Loop through the file reading chunks at a time as to not
        # put the entire file in memory.  That would suck for DVDs
        while True:
            chunk = input.read(8192) # magic number!  Taking suggestions
            if not chunk:
                break # we're done with the file
            sum.update(chunk)
        input.close()
        return sum.hexdigest()

    def _run_command(self, cmd, shell=False, env=None, pipe=[], cwd=None):
        """Run the given command.

        Will determine if caller is on a real tty and if so stream to the tty

        Or else will run and log output.

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
                self.log.debug('Adding %s:%s to the environment' %
                               (item, env[item]))
                environ[item] = env[item]
        # Check if we're supposed to be on a shell.  If so, the command must
        # be a string, and not a list.
        command = cmd
        pipecmd = pipe
        if shell:
            command = ' '.join(cmd)
            pipecmd = ' '.join(pipe)
        # Check to see if we're on a real tty, if so, stream it baby!
        if sys.stdout.isatty():
            if pipe:
                self.log.debug('Running %s | %s directly on the tty' %
                               (' '.join(cmd), ' '.join(pipe)))
            else:
                self.log.debug('Running %s directly on the tty' %
                               ' '.join(cmd))
            try:
                if pipe:
                    # We're piping the stderr over too, which is probably a
                    # bad thing, but rpmbuild likes to put useful data on
                    # stderr, so....
                    proc = subprocess.Popen(command, env=environ,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, shell=shell,
                                            cwd=cwd)
                    subprocess.check_call(pipecmd, env=environ,
                                          stdout=sys.stdout,
                                          stderr=sys.stderr,
                                          stdin=proc.stdout,
                                          shell=shell,
                                          cwd=cwd)
                    (output, err) = proc.communicate()
                    if proc.returncode:
                        raise rpkgError('Non zero exit')
                else:
                    subprocess.check_call(command, env=environ, stdout=sys.stdout,
                                          stderr=sys.stderr, shell=shell,
                                          cwd=cwd)
            except (subprocess.CalledProcessError,
                    OSError), e:
                raise rpkgError(e)
            except KeyboardInterrupt:
                raise rpkgError()
        else:
            # Ok, we're not on a live tty, so pipe and log.
            if pipe:
                self.log.debug('Running %s | %s and logging output' %
                               (' '.join(cmd), ' '.join(pipe)))
            else:
                self.log.debug('Running %s and logging output' %
                               ' '.join(cmd))
            try:
                if pipe:
                    proc1 = subprocess.Popen(command, env=environ,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT,
                                             shell=shell,
                                             cwd=cwd)
                    proc = subprocess.Popen(pipecmd, env=environ,
                                             stdin=proc1.stdout,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, shell=shell,
                                             cwd=cwd)
                    output, error = proc.communicate()
                else:
                    proc = subprocess.Popen(command, env=environ,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, shell=shell,
                                            cwd=cwd)
                    output, error = proc.communicate()
            except OSError, e:
                raise rpkgError(e)
            self.log.info(output)
            if proc.returncode:
                raise rpkgError('Command %s returned code %s with error: %s' %
                                  (' '.join(cmd),
                                   proc.returncode,
                                   error))
        return

    def _verify_file(self, file, hash, hashtype):
        """Given a file, a hash of that file, and a hashtype, verify.

        Returns True if the file verifies, False otherwise

        """

        # get the hash
        sum = self._hash_file(file, hashtype)
        # now do the comparison
        if sum == hash:
            return True
        return False

    def _newer(self, file1, file2):
        """Compare the last modification time of the given files

        Returns True is file1 is newer than file2

        """

        return os.path.getmtime(file1) > os.path.getmtime(file2)

    def _do_curl(self, file_hash, file):
        """Use curl manually to upload a file"""

        cmd = ['curl', '--fail', '-o', '/dev/null', '--show-error',
        '--progress-bar', '-F', 'name=%s' % self.module_name, '-F',
        'md5sum=%s' % file_hash, '-F', 'file=@%s' % file,
        self.lookaside_cgi]
        self._run_command(cmd)

    def _get_build_arches_from_spec(self):
        """Given the path to an spec, retrieve the build arches

        """

        spec = os.path.join(self.path, self.spec)
        try:
            hdr = rpm.spec(spec)
        except Exception, er:
            raise rpkgError('%s is not a spec file' % spec)
        archlist = [ pkg.header['arch'] for pkg in hdr.packages]
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
        if 'noarch' not in excludearch and ('noarch' in buildarchs or \
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
            if int(re.search(r'\d', self.distval).group()) < 6:
                return('md5')
        except:
            # An error here is OK, don't bother the user.
            pass

        # Fall back to the default hash type
        return(self.hashtype)

    def _list_branches(self):
        """Returns a tuple of local and remote branch names"""

        self.log.debug('Listing refs')
        refs = self.repo.refs
        # Sort into local and remote branches
        remotes = []
        locals = []
        for ref in refs:
            if type(ref) == git.Head:
                self.log.debug('Found local branch %s' % ref.name)
                locals.append(ref.name)
            elif type(ref) == git.RemoteReference:
                if ref.remote_head == 'HEAD':
                    self.log.debug('Skipping remote branch alias HEAD')
                    continue # Not useful in this context
                self.log.debug('Found remote branch %s' % ref.name)
                remotes.append(ref.name)
        return (locals, remotes)

    def _srpmdetails(self, srpm):
        """Return a tuple of package name, package files, and upload files."""

        # This shouldn't change... often
        UPLOADEXTS = ['tar', 'gz', 'bz2', 'lzma', 'xz', 'Z', 'zip', 'tff',
                      'bin', 'tbz', 'tbz2', 'tgz', 'tlz', 'txz', 'pdf', 'rpm',
                      'jar', 'war', 'db', 'cpio', 'jisp', 'egg', 'gem']

        # get the name
        cmd = ['rpm', '-qp', '--nosignature', '--qf', '%{NAME}', srpm]
                # Run the command
        self.log.debug('Running: %s' % ' '.join(cmd))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError, e:
            raise rpkgError(e)
        name = output
        if error:
            raise rpkgError('Error querying srpm: %s' % error)

        # now get the files and upload files
        files = []
        uploadfiles = []
        cmd = ['rpm', '-qpl', srpm]
        self.log.debug('Running: %s' % ' '.join(cmd))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError, e:
            raise rpkgError(e)
        if error:
            raise rpkgError('Error querying srpm:' % error)
        # Doing a strip and split here as splitting on \n gets me an extra entry
        contents = output.strip().split('\n')
        # Cycle through the stuff and sort correctly by its extension
        for file in contents:
            if file.rsplit('.')[-1] in UPLOADEXTS:
                uploadfiles.append(file)
            else:
                files.append(file)

        return((name, files, uploadfiles))

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
        self._run_command(cmd)
        self.log.info('Tag \'%s\' was created' % tagname)

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
        # Run it!
        self._run_command(cmd, cwd=self.path)
        return

    def clone(self, module, path=None, branch=None, bare_dir=None, anon=False):
        """Clone a repo, optionally check out a specific branch.

        module is the name of the module to clone

        path is the basedir to perform the clone in

        branch is the name of a branch to checkout instead of <remote>/master

        bare_dir is the name of a directory to make a bare clone too if this is a
        bare clone. None otherwise.

        anon is whether or not to clone anonymously

        Logs the output and returns nothing.

        """

        if not path:
            path = self.path
        # construct the git url
        if anon:
            giturl = self.anongiturl % {'module': module}
        else:
            giturl = self.gitbaseurl % {'user': self.user, 'module': module}

        # Create the command
        cmd = ['git', 'clone']
        # do the clone
        if branch and bare_dir:
            raise rpkgError('Cannot combine bare cloning with a branch')
        elif branch:
            # For now we have to use switch branch
            self.log.debug('Checking out a specific branch %s' % giturl)
            cmd.extend(['-b', branch, giturl])
        elif bare_dir:
            self.log.debug('Cloning %s bare' % giturl)
            cmd.extend(['--bare', giturl, bare_dir])
        else:
            self.log.debug('Cloning %s' % giturl)
            cmd.extend([giturl])
        self._run_command(cmd, cwd=path)

        return

    def clone_with_dirs(self, module, anon=False):
        """Clone a repo old style with subdirs for each branch.

        module is the name of the module to clone

        gitargs is an option list of arguments to git clone

        """

        # Get the full path of, and git object for, our directory of branches
        top_path = os.path.join(self.path, module)
        top_git = git.Git(top_path)
        repo_path = os.path.join(top_path, 'rpkg.git')

        # construct the git url
        if anon:
            giturl = self.anongiturl % {'module': module}
        else:
            giturl = self.gitbaseurl % {'user': self.user, 'module': module}

        # Create our new top directory
        try:
            os.mkdir(top_path)
        except (OSError), e:
            raise rpkgError('Could not create directory for module %s: %s' %
                    (module, e))

        # Create a bare clone first. This gives us a good list of branches
        try:
            self.clone(module, top_path, bare_dir=repo_path, anon=anon)
        except Exception, e:
            # Clean out our directory
            shutil.rmtree(top_path)
            raise
        # Get the full path to, and a git object for, our new bare repo
        repo_git = git.Git(repo_path)

        # Get a branch listing
        branches = [x for x in repo_git.branch().split() if x != "*" and
                re.search(self.branchre, x)]

        for branch in branches:
            try:
                # Make a local clone for our branch
                top_git.clone("--branch", branch, repo_path, branch)

                # Set the origin correctly
                branch_path = os.path.join(top_path, branch)
                branch_git = git.Git(branch_path)
                branch_git.config("--replace-all", "remote.origin.url", giturl)
                # Bad use of "origin" here, need to fix this when more than one
                # remote is used.
            except (git.GitCommandError, OSError), e:
                raise rpkgError('Could not locally clone %s from %s: %s' %
                        (branch, repo_path, e))

        # We don't need this now. Ignore errors since keeping it does no harm
        shutil.rmtree(repo_path, ignore_errors=True)

    def commit(self, message=None, file=None, files=[]):
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
        if message:
            cmd.extend(['-m', message])
        elif file:
            # If we get a relative file name, prepend our path to it.
            if self.path and not file.startswith('/'):
                cmd.extend(['-F', os.path.abspath(os.path.join(self.path,
                                                               file))])
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

        cmd = ['git', 'tag', '-d', tagname]
        self._run_command(cmd, cwd=self.path)
        self.log.info ('Tag %s was deleted' % tagname)

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

    def get_latest_commit(self, module):
        """Discover the latest commit has for a given module and return it"""

        # This is stupid that I have to use subprocess :/
        url = self.anongiturl % {'module': module}
        # This cmd below only works to scratch build rawhide
        # We need something better for epel
        cmd = ['git', 'ls-remote', url, 'refs/heads/master']
        try :
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                                    stdout=subprocess.PIPE)
            output, error = proc.communicate()
        except OSError, e:
            raise rpkgError(e)
        if error:
            raise rpkgError('Got an error finding head for %s: %s' %
                              (module, error))
        # Return the hash sum
        return output.split()[0]

    def gitbuildhash(self, build):
        """Determine the git hash used to produce a particular N-V-R"""

        # Get the build data from the nvr
        bdata = self.anon_kojisession.getBuild(build)
        if not bdata:
            raise rpkgError('Unknown build: %s' % build)

        # Get the task data out of that build data
        taskinfo = self.anon_kojisession.getTaskRequest(bdata['task_id'])
        # taskinfo is a list of items, first item is the task url.
        # second is the build target.
        # Match a 40 char block of text on the url line, that'll be our hash
        try:
            hash = re.search(r'[0-9A-Za-z]{40}', taskinfo[0]).group(0)
        except AttributeError:
            raise rpkgError('Build %s did not use git' % build)
        return (hash)

    def import_srpm(self, srpm):
        """Import the contents of an srpm into a repo.

        srpm: File to import contents from

        This function will add/remove content to match the srpm,

        upload new files to the lookaside, and stage the changes.

        Returns a list of files to upload.

        """

        # see if the srpm even exists
        srpm = os.path.abspath(srpm)
        if not os.path.exists(srpm):
            raise rpkgError('File not found.')
        # bail if we're dirty
        if self.repo.is_dirty():
            raise rpkgError('There are uncommitted changes in your repo')
        # Get the details of the srpm
        name, files, uploadfiles = self._srpmdetails(srpm)

        # Need a way to make sure the srpm name matches the repo some how.

        # Get a list of files we're currently tracking
        ourfiles = self.repo.git.ls_files().split('\n')
        # Trim out sources and .gitignore
        try:
            ourfiles.remove('.gitignore')
            ourfiles.remove('sources')
        except ValueError:
            pass
        try:
            ourfiles.remove('sources')
        except ValueError:
            pass

        # Things work better if we're in our module directory
        oldpath = os.getcwd()
        os.chdir(self.path)

        # Look through our files and if it isn't in the new files, remove it.
        for file in ourfiles:
            if file not in files:
                self.log.info("Removing no longer used file: %s" % file)
                rv = self.repo.index.remove([file])
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
        rv = self.repo.index.add(files)
        # Return to the caller and let them take it from there.
        os.chdir(oldpath)
        return(uploadfiles)

    def list_tag(self, tagname=None):
        """Create a list of all tags in the repository which match a given tagname.

        if tagname == '*' all tags will been shown.

        """

        cmd = ['git', 'tag']
        cmd.extend(['-l'])
        if tagname and tagname != '*':
            cmd.extend([tagname])
        # make it so
        self._run_command(cmd)

    def new(self):
        """Return changes in a repo since the last tag"""

        # Find the latest tag
        tag = self.repo.git.describe('--tags', '--abbrev=0')
        # Now get the diff
        self.log.debug('Diffing from tag %s' % tag)
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
            self.log.debug('Running %s' % ' '.join(cmd))
            (output, errors) = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                cwd=self.path).communicate()
        except Exception, e:
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
            self.log.debug('Moving existing patch %s to %s~' % (outfile,
                                                                outfile))
            os.rename(os.path.join(self.path, outfile),
                      '%s~' % os.path.join(self.path, outfile))
            # Capture the lines preceeding the diff
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
        rv = self.repo.index.add([outfile])
        log.info('Created %s and added it to the index' % outfile)

    def pull(self, rebase=False, norebase=False):
        """Pull changes from the remote repository

        Optionally rebase current branch on top of remote branch

        Optionally override .git setting to always rebase

        """

        cmd = ['git', 'pull']
        if rebase:
            cmd.append('--rebase')
        if norebase:
            cmd.append('--no-rebase')
        self._run_command(cmd, cwd=self.path)
        return

    def push(self):
        """Push changes to the remote repository"""

        cmd = ['git', 'push']
        self._run_command(cmd, cwd=self.path)
        return

    def sources(self, outdir=None):
        """Download source files"""

        try:
            archives = open(os.path.join(self.path, 'sources'),
                            'r').readlines()
        except IOError, e:
            raise rpkgError('%s is not a valid repo: %s' % (self.path, e))
        # Default to putting the files where the module is
        if not outdir:
            outdir = self.path
        for archive in archives:
            try:
                # This strip / split is kind a ugly, but checksums shouldn't have
                # two spaces in them.  sources file might need more structure in the
                # future
                csum, file = archive.strip().split('  ', 1)
            except ValueError:
                raise rpkgError('Malformed sources file.')
            # See if we already have a valid copy downloaded
            outfile = os.path.join(outdir, file)
            if os.path.exists(outfile):
                if self._verify_file(outfile, csum, self.lookasidehash):
                    continue
            self.log.info("Downloading %s" % (file))
            url = '%s/%s/%s/%s/%s' % (self.lookaside, self.module_name,
                                      file.replace(' ', '%20'),
                                      csum, file.replace(' ', '%20'))
            # There is some code here for using pycurl, but for now,
            # just use subprocess
            #output = open(file, 'wb')
            #curl = pycurl.Curl()
            #curl.setopt(pycurl.URL, url)
            #curl.setopt(pycurl.FOLLOWLOCATION, 1)
            #curl.setopt(pycurl.MAXREDIRS, 5)
            #curl.setopt(pycurl.CONNECTTIMEOUT, 30)
            #curl.setopt(pycurl.TIMEOUT, 300)
            #curl.setopt(pycurl.WRITEDATA, output)
            #try:
            #    curl.perform()
            #except:
            #    print "Problems downloading %s" % url
            #    curl.close()
            #    output.close()
            #    return 1
            #curl.close()
            #output.close()
            # These options came from Makefile.common.
            # Probably need to support wget too
            command = ['curl', '-H', 'Pragma:', '-o', outfile, '-R', '-S', '--fail',
                       '--show-error', url]
            self._run_command(command)
            if not self._verify_file(outfile, csum, self.lookasidehash):
                raise rpkgError('%s failed checksum' % file)
        return

    def switch_branch(self, branch):
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
                            'too see details' % self.path)

        # Get our list of branches
        (locals, remotes) = self._list_branches()

        if not branch in locals:
            # We need to create a branch
            self.log.debug('No local branch found, creating a new one')
            totrack = None
            for remote in remotes:
                # bad use of "origin" here, will have to be fixed
                if remote.replace('origin/', '') == branch:
                    totrack = remote
                    break
            else:
                raise rpkgError('Unknown remote branch %s' % branch)
            try:
                self.log.info(self.repo.git.checkout('-b', branch, '--track',
                                                totrack))
            except: # this needs to be finer grained I think...
                raise rpkgError('Could not create branch %s' % branch)
        else:
            try:
                output = self.repo.git.checkout(branch)
                # The above shoudl have no output, but stash it anyway
                self.log.info("Switched to branch '%s'" % branch)
            except: # This needs to be finer grained I think...
                raise rpkgError('Could not check out %s' % branch)
        return

    def file_exists(self, pkg_name, filename, md5sum):
        """
        Return True if the given file exists in the lookaside cache, False
        if not.

        A rpkgError will be thrown if the request looks bad or something
        goes wrong. (i.e. the lookaside URL cannot be reached, or the package
        named does not exist)
        """

        # String buffer, used to receive output from the curl request:
        buf = StringIO.StringIO()

        # Setup the POST data for lookaside CGI request. The use of
        # 'filename' here appears to be what differentiates this
        # request from an actual file upload.
        post_data = [
                ('name', pkg_name),
                ('md5sum', md5sum),
                ('filename', filename)]

        curl = self._create_curl()
        curl.setopt(pycurl.WRITEFUNCTION, buf.write)
        curl.setopt(pycurl.HTTPPOST, post_data)

        try:
            curl.perform()
        except Exception, e:
            raise rpkgError('Lookaside failure: %s' % e)
        curl.close()
        output = buf.getvalue().strip()

        # Lookaside CGI script returns these strings depending on whether
        # or not the file exists:
        if output == "Available":
            return True
        if output == "Missing":
            return False

        # Something unexpected happened, will trigger if the lookaside URL
        # cannot be reached, the package named does not exist, and probably
        # some other scenarios as well.
        raise rpkgError("Error checking for %s at: %s" %
                (filename, self.lookaside_cgi))

    def upload_file(self, pkg_name, filepath, md5sum):
        """ Upload a file to the lookaside cache. """

        # Setup the POST data for lookaside CGI request. The use of
        # 'file' here appears to trigger the actual upload:
        post_data = [
                ('name', pkg_name),
                ('md5sum', md5sum),
                ('file', (pycurl.FORM_FILE, filepath))]

        curl = self._create_curl()
        curl.setopt(pycurl.HTTPPOST, post_data)

        try:
            curl.perform()
        except:
            raise rpkgError('Lookaside failure.')
        curl.close()

    def build(self, skip_tag=False, scratch=False, background=False,
              url=None, chain=None, arches=None, sets=False):
        """Initiate a build of the module.  Available options are:

        skip_tag: Skip the tag action after the build

        scratch: Perform a scratch build

        background: Perform the build with a low priority

        url: A url to an uploaded srpm to build from

        chain: A chain build set

        arches: A set of arches to limit the scratch build for

        sets: A boolean to let us know whether or not the chain has sets

        This function submits the task to koji and returns the taskID

        It is up to the client to wait or watch the task.
        """

        # Ensure the repo exists as well as repo data and site data
        # build up the command that a user would issue
        cmd = [self.build_client]
        # construct the url
        if not url:
            # We don't have a url, so build from the latest commit
            # Check to see if the tree is dirty
            if self.repo.is_dirty():
                raise rpkgError('%s has uncommitted changes.  Use git status '
                                'too see details' % self.path)
            # Need to check here to see if the local commit you want to build is
            # pushed or not
            branch = self.repo.active_branch
            try:
                remote = self.repo.git.config('--get',
                    'branch.%s.remote' % branch)

                merge = self.repo.git.config('--get',
                    'branch.%s.merge' % branch).replace('refs/heads', remote)
                if self.repo.git.rev_list('%s...%s' % (branch, merge)):
                    raise rpkgError('There are unpushed changes in your repo')
            except git.GitCommandError:
                raise rpkgError('You must provide a srpm or push your \
                                   changes to the remote repo.')
            url = self.anongiturl % {'module': self.module_name} + \
                '?#%s' % self.commithash
        # Check to see if the target is valid
        build_target = self.kojisession.getBuildTarget(self.target)
        if not build_target:
            raise rpkgError('Unknown build target: %s' % self.target)
        # see if the dest tag is locked
        dest_tag = self.kojisession.getTag(build_target['dest_tag_name'])
        if not dest_tag:
            raise rpkgError('Unknown destination tag %s' %
                              build_target['dest_tag_name'])
        if dest_tag['locked'] and not scratch:
            raise rpkgError('Destination tag %s is locked' % dest_tag['name'])
        # If we're chain building, make sure inheritance works
        if chain:
            cmd.append('chain-build')
            ancestors = self.kojisession.getFullInheritance(
                                                    build_target['build_tag'])
            if dest_tag['id'] not in [build_target['build_tag']] + \
            [ancestor['parent_id'] for ancestor in ancestors]:
                raise rpkgError('Packages in destination tag ' \
                                  '%(dest_tag_name)s are not inherited by' \
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
            priority = 5 # magic koji number :/
        if arches:
            if not scratch:
                raise rpkgError('Cannot override arches for non-scratch builds')
            cmd.append('--arch-override=%s' % ','.join(arches))
            opts['arch_override'] = ' '.join(arches)

        cmd.append(self.target)
        # see if this build has been done.  Does not check builds within
        # a chain
        if not scratch and not url.endswith('.src.rpm'):
            build = self.kojisession.getBuild(self.nvr)
            if build:
                if build['state'] == 1:
                    raise rpkgError('%s has already been built' %
                                      self.nvr)
        # Now submit the task and get the task_id to return
        # Handle the chain build version
        if chain:
            self.log.debug('Adding %s to the chain' % url)
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
            cmd.extend(' : '.join([' '.join(sets) for sets in chain]).split())
            self.log.info('Chain building %s + %s for %s' % (self.nvr,
                                                             chain[:-1],
                                                             self.target))
            self.log.debug('Building chain %s for %s with options %s and a '
                           'priority of %s' %
                           (chain, self.target, opts, priority))
            self.log.debug(' '.join(cmd))
            task_id = self.kojisession.chainBuild(chain, self.target, opts,
                                                  priority=priority)
        # Now handle the normal build
        else:
            cmd.append(url)
            if url.endswith('.src.rpm'):
                srpm = os.path.basename(url)
                self.log.info('Building %s for %s' % (srpm, self.target))
            else:
                self.log.info('Building %s for %s' % (self.nvr, self.target))
            self.log.debug('Building %s for %s with options %s and a priority '
                           'of %s' % (url, self.target, opts, priority))
            self.log.debug(' '.join(cmd))
            task_id = self.kojisession.build(url, self.target, opts,
                                             priority=priority)
        self.log.info('Created task: %s' % task_id)
        self.log.info('Task info: %s/taskinfo?taskID=%s' % (self.kojiweburl,
                                                            task_id))
        return task_id

    def clog(self):
        """Write the latest spec changelog entry to a clog file"""

        # This is a little ugly.  We want to find where %changelog starts,
        # then only deal with the content up to the first empty newline.
        # Then remove any lines that start with $ or %, and then replace
        # %% with %

        cloglines = []
        first = True
        spec = open(os.path.join(self.path, self.spec), 'r').readlines()
        for line in spec:
            if line.startswith('%changelog'):
                # Grab all the lines below changelog
                for line2 in spec[spec.index(line):]:
                    if line2.startswith('\n'):
                        break
                    if line2.startswith('$'):
                        continue
                    if line2.startswith('%'):
                        continue
                    if line2.startswith('*'):
                        # skip the email n/v/r line.  Redundant
                        continue
                    if first:
                        cloglines.append(line2.lstrip('- ').replace('%%', '%'))
                        cloglines.append("\n")
                        first = False
                    else:
                        cloglines.append(line2.replace('%%', '%'))

        # Now open the clog file and write out the lines
        clogfile = open(os.path.join(self.path, 'clog'), 'w')
        clogfile.writelines(cloglines)

    def compile(self, arch=None, short=False, builddir=None):
        """Run rpm -bc on a module

        optionally for a specific arch, or short-circuit it, or
        define an alternate builddir

        Logs the output and returns nothing
        """

        # Get the sources
        self.sources()
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
        cmd.extend(['-bc', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

    def giturl(self):
        """Return the git url that would be used for building"""

        url = self.anongiturl % {'module': self.module_name} + \
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

    def install(self, arch=None, short=False, builddir=None):
        """Run rpm -bi on a module

        optionally for a specific arch, short-circuit it, or
        define an alternative builddir

        Logs the output and returns nothing
        """

        # Get the sources
        self.sources()
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
            log.warn('No srpm found')

        # Get the possible built arches
        arches = self._get_build_arches_from_spec()
        rpms = []
        for arch in arches:
            if os.path.exists(os.path.join(self.path, arch)):
                # For each available arch folder, lists file and keep
                # those ending with .rpm
                rpms.extend([os.path.join(self.path, arch, file) for file in
                         os.listdir(os.path.join(self.path, arch))
                         if file.endswith('.rpm')])
        if not rpms:
            log.warn('No rpm found')
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
        self.sources()
        # build up the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        # This may need to get updated if we ever change our checksum default
        if hashtype:
            cmd.extend(["--define '_source_filedigest_algorithm %s'" %
                        hashtype,
                        "--define '_binary_filedigest_algorithm %s'" %
                        hashtype])
        if arch:
            cmd.extend(['--target', arch])
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
            raise rpkgError('Unknown build target: %s' % target)

        try:
            repoid = self.anon_kojisession.getRepo(
                                build_target['build_tag_name'])['id']
        except Exception, e:
            raise rpkgError('Could not find a valid build repo')

        # Generate the config
        config = koji.genMockConfig('%s-%s' % (target, arch), arch,
                                   distribution=self.disttag,
                                   tag_name=build_target['build_tag_name'],
                                   repoid=repoid,
                                   topurl=self.topurl)

        # Return the mess
        return(config)

    def mockbuild(self, mockargs=[], root=None, hashtype='sha256'):
        """Build the package in mock, using mockargs

        Log the output and returns nothing
        """

        # Make sure we have an srpm to run on
        self.srpm(hashtype=hashtype)

        # setup the command
        cmd = ['mock']
        cmd.extend(mockargs)
        if not root:
            root=self.mockconfig
        cmd.extend(['-r', root, '--resultdir',
                    os.path.join(self.path, "results_%s" % self.module_name,
                                 self.ver, self.rel),
                    '--rebuild', self.srpmname])
        # Run the command
        self._run_command(cmd)

    def upload(self, files, replace=False):
        """Upload source file(s) in the lookaside cache

        Can optionally replace the existing tracked sources
        """

        oldpath = os.getcwd()
        os.chdir(self.path)

        # Decide to overwrite or append to sources:
        if replace:
            sources = []
            sources_file = open('sources', 'w')
        else:
            sources = open('sources', 'r').readlines()
            sources_file = open('sources', 'a')

        # Will add new sources to .gitignore if they are not already there.
        gitignore = GitIgnore(os.path.join(self.path, '.gitignore'))

        uploaded = []
        for f in files:
            # TODO: Skip empty file needed?
            file_hash = self._hash_file(f, self.lookasidehash)
            self.log.info("Uploading: %s  %s" % (file_hash, f))
            file_basename = os.path.basename(f)
            if not "%s  %s\n" % (file_hash, file_basename) in sources:
                sources_file.write("%s  %s\n" % (file_hash, file_basename))

            # Add this file to .gitignore if it's not already there:
            if not gitignore.match(file_basename):
                gitignore.add('/%s' % file_basename)

            if self.file_exists(self.module_name, file_basename, file_hash):
                # Already uploaded, skip it:
                self.log.info("File already uploaded: %s" % file_basename)
            else:
                # Ensure the new file is readable:
                os.chmod(f, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                #lookaside.upload_file(self.module, f, file_hash)
                # For now don't use the pycurl upload function as it does
                # not produce any progress output.  Cheat and use curl
                # directly.
                self._do_curl(file_hash, f)
                uploaded.append(file_basename)

        sources_file.close()

        # Write .gitignore with the new sources if anything changed:
        gitignore.write()

        rv = self.repo.index.add(['sources', '.gitignore'])

        # Change back to original working dir:
        os.chdir(oldpath)

        # Log some info
        self.log.info('Uploaded and added to .gitignore: %s' %
                      ' '.join(uploaded))

    def prep(self, arch=None, builddir=None):
        """Run rpm -bp on a module

        optionally for a specific arch, or
        define an alternative builddir

        Logs the output and returns nothing
        """

        # Get the sources
        self.sources()
        # setup the rpm command
        cmd = ['rpmbuild']
        if builddir:
            # Tack on a new builddir to the end of the defines
            self.rpmdefines.append("--define '_builddir %s'" %
                                   os.path.abspath(builddir))
        cmd.extend(self.rpmdefines)
        if arch:
            cmd.extend(['--target', arch])
        cmd.extend(['--nodeps', '-bp', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

    def srpm(self, hashtype=None):
        """Create an srpm using hashtype from content in the module

        Requires sources already downloaded.
        """

        self.srpmname = os.path.join(self.path,
                            "%s-%s-%s.src.rpm" % (self.module_name,
                                                  self.ver, self.rel))
        # See if we need to build the srpm
        if os.path.exists(self.srpmname):
            self.log.debug('Srpm found, rewriting it.')

        cmd = ['rpmbuild']
        cmd.extend(self.rpmdefines)
        # Figure out which hashtype to use, if not provided one
        if not hashtype:
            # Try to determine the dist
            hashtype = self._guess_hashtype()
        # This may need to get updated if we ever change our checksum default
        if not hashtype == 'sha256':
            cmd.extend(["--define '_source_filedigest_algorithm %s'" % hashtype,
                    "--define '_binary_filedigest_algorithm %s'" % hashtype])
        cmd.extend(['--nodeps', '-bs', os.path.join(self.path, self.spec)])
        self._run_command(cmd, shell=True)

    def unused_patches(self):
        """Discover patches checked into source control that are not used

        Returns a list of unused patches, which may be empty.
        """

        # Create a list for unused patches
        unused = []
        # Get the content of spec into memory for fast searching
        spec = open(self.spec, 'r').read()
        # Get a list of files tracked in source control
        files = self.repo.git.ls_files('--exclude-standard').split()
        for file in files:
            # throw out non patches
            if not file.endswith('.patch'):
                continue
            if file not in spec:
                unused.append(file)
        return unused

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
        cmd.extend(['-bl', os.path.join(self.path, self.spec)])
        # Run the command
        self._run_command(cmd, shell=True)

class GitIgnore(object):
    """ Smaller wrapper for managing a .gitignore file and it's entries. """

    def __init__(self, path):
        """
        Create GitIgnore object for the given full path to a .gitignore file.

        File does not have to exist yet, and will be created if you write out
        any changes.
        """
        self.path = path

        # Lines of the .gitignore file, used to check if entries need to be added
        # or already exist.
        self.__lines = []
        if os.path.exists(self.path):
            gitignore_file = open(self.path, 'r')
            self.__lines = gitignore_file.readlines()
            gitignore_file.close()

        # Set to True if we end up making any modifications, used to
        # prevent unecessary writes.
        self.modified = False

    def add(self, line):
        """
        Add a line to .gitignore, but check if it's a duplicate first.
        """

        # Append a newline character if the given line didn't have one:
        if line[-1] != '\n':
            line = "%s\n" % line

        # Add this line if it doesn't already exist:
        if not line in self.__lines:
            self.__lines.append(line)
            self.modified = True

    def match(self, line):
        line = line.lstrip('/').rstrip('\n')
        for entry in self.__lines:
            entry = entry.lstrip('/').rstrip('\n')
            if fnmatch.fnmatch(line, entry):
                return True
        return False

    def write(self):
        """ Write the new .gitignore file if any modifications were made. """
        if self.modified:
            gitignore_file = open(self.path, 'w')
            for line in self.__lines:
                gitignore_file.write(line)
            gitignore_file.close()
