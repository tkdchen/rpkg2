# cli.py - a cli client class module
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.
#
# There are 6 functions derived from /usr/bin/koji which are licensed under
# LGPLv2.1.  See comments before those functions.

from __future__ import print_function
import argparse
import logging
import os
import pwd
import random
import string
import sys
import time

import koji_cli.lib
import pyrpkg.utils as utils
import six

from pyrpkg import rpkgError, log as rpkgLogger
from six.moves import configparser


def warning_deprecated_dist(value):
    """Warning deprecated of option dist"""
    rpkgLogger.warning('Deprecation warning: --dist is deprecated and will be '
                       'removed in future version. Use --release instead.')
    return value


class cliClient(object):
    """This is a client class for rpkg clients."""

    def __init__(self, config, name=None):
        """This requires a ConfigParser object

        Name of the app can optionally set, or discovered from exe name
        """

        self.config = config
        self._name = name
        # Define default name in child class
        # self.DEFAULT_CLI_NAME = None
        # Property holders, set to none
        self._cmd = None
        self._module = None
        # Setup the base argparser
        self.setup_argparser()
        # Add a subparser
        self.subparsers = self.parser.add_subparsers(
            title='Targets',
            description='These are valid commands you can ask %s to do'
                        % self.name)
        # Register all the commands
        self.setup_subparsers()

    @property
    def name(self):
        """Property used to identify prog name and key in config file"""

        if not self._name:
            self._name = self.get_name()
            assert self._name
        return(self._name)

    def get_name(self):
        name = os.path.basename(sys.argv[0])
        if not name or '__main__.py' in name:
            try:
                name = self.DEFAULT_CLI_NAME
            except AttributeError:
                # Ignore missing DEFAULT_CLI_NAME for backwards
                # compatibility
                pass
        if not name:
            # We don't have logger available yet
            raise rpkgError('Could not determine CLI name')
        return name

    # Define some properties here, for lazy loading
    @property
    def cmd(self):
        """This is a property for the command attribute"""

        if not self._cmd:
            self.load_cmd()
        return(self._cmd)

    def _get_bool_opt(self, opt, default=False):
        try:
            return self.config.getboolean(self.name, opt)
        except ValueError:
            raise rpkgError('%s option must be a boolean' % opt)
        except configparser.NoOptionError:
            return default

    def load_cmd(self):
        """This sets up the cmd object"""

        # Set target if we got it as an option
        target = None
        if hasattr(self.args, 'target') and self.args.target:
            target = self.args.target

        # load items from the config file
        items = dict(self.config.items(self.name, raw=True))

        dg_namespaced = self._get_bool_opt('distgit_namespaced')
        la_namespaced = self._get_bool_opt('lookaside_namespaced')

        # Read comma separated list of kerberos realms
        realms = [realm
                  for realm in items.get("kerberos_realms", '').split(',')
                  if realm]

        kojiconfig = None

        if self.config.has_option(self.name, 'kojiconfig'):
            kojiconfig = self.config.get(self.name, 'kojiconfig')
            koji_config_type = 'config'
            self.log.warning(
                'Deprecation warning: kojiconfig is deprecated. Instead, '
                'kojiprofile should be used.')

        # kojiprofile has higher priority to be used if both kojiconfig and
        # kojiprofile exist at same time.
        if self.config.has_option(self.name, 'kojiprofile'):
            kojiconfig = self.config.get(self.name, 'kojiprofile')
            koji_config_type = 'profile'

        if not kojiconfig:
            raise rpkgError('Missing kojiconfig and kojiprofile to load Koji '
                            'session. One of them must be specified.')

        # Create the cmd object
        self._cmd = self.site.Commands(self.args.path,
                                       items['lookaside'],
                                       items['lookasidehash'],
                                       items['lookaside_cgi'],
                                       items['gitbaseurl'],
                                       items['anongiturl'],
                                       items['branchre'],
                                       kojiconfig,
                                       items['build_client'],
                                       koji_config_type=koji_config_type,
                                       user=self.args.user,
                                       dist=self.args.dist or self.args.release,
                                       target=target,
                                       quiet=self.args.q,
                                       distgit_namespaced=dg_namespaced,
                                       realms=realms,
                                       lookaside_namespaced=la_namespaced
                                       )

        if self.args.module_name:
            # Module name was specified via argument
            if '/' not in self.args.module_name:
                self._cmd.module_name = self.args.module_name
                if dg_namespaced:
                    # No slash, assume rpms namespace
                    self._cmd.ns = 'rpms'
            else:
                self._cmd.ns, self._cmd.module_name = self.args.module_name.rsplit('/', 1)
        self._cmd.password = self.args.password
        self._cmd.runas = self.args.runas
        self._cmd.debug = self.args.debug
        self._cmd.verbose = self.args.v
        self._cmd.clone_config = items.get('clone_config')
        self._cmd.lookaside_request_params = items.get('lookaside_request_params')

    # This function loads the extra stuff once we figure out what site
    # we are
    def do_imports(self, site=None):
        """Import extra stuff not needed during build

        As a side effect method sets self.site with a loaded library.

        site option can be used to specify which library to load
        """

        # We do some imports here to be more flexible
        if not site:
            import pyrpkg
            self.site = pyrpkg
        else:
            try:
                __import__(site)
                self.site = sys.modules[site]
            except ImportError:
                raise Exception('Unknown site %s' % site)

    def setup_argparser(self):
        """Setup the argument parser and register some basic commands."""

        self.parser = argparse.ArgumentParser(
            prog=self.name,
            epilog='For detailed help pass --help to a target')
        # Add some basic arguments that should be used by all.
        # Add a config file
        self.parser.add_argument('--config', '-C',
                                 default=None,
                                 help='Specify a config file to use')
        group = self.parser.add_mutually_exclusive_group()
        group.add_argument('--release',
                           dest='release',
                           default=None,
                           help='Override the discovered release from current branch, '
                                'which is used to determine the build target and value of '
                                'dist macro. Generally, release is the name of a branch '
                                'created in your package repository. --release is an alias '
                                'of --dist, hence --release should be used instead.')
        # Allow forcing the dist value
        group.add_argument('--dist',
                           default=None,
                           type=warning_deprecated_dist,
                           help='Deprecated. Use --release instead. You can use --dist '
                                'for a while for backward-compatibility. It will be disabled'
                                ' in future version.')
        # Allow forcing the package name
        self.parser.add_argument('--module-name',
                                 help=('Override the module name. Otherwise'
                                       ' it is discovered from: Git push URL'
                                       ' or Git URL (last part of path with'
                                       ' .git extension removed) or from name'
                                       ' macro in spec file. In that order.')
                                 )
        # Override the  discovered user name
        self.parser.add_argument('--user', default=None,
                                 help='Override the discovered user name')
        # If using password auth
        self.parser.add_argument('--password', default=None,
                                 help='Password for Koji login')
        # Run Koji commands as a user other then the one you have
        # credentials for (requires configuration on the Koji hub)
        self.parser.add_argument('--runas', default=None,
                                 help='Run Koji commands as a different user')
        # Let the user define a path to work in rather than cwd
        self.parser.add_argument('--path', default=None,
                                 type=utils.u,
                                 help='Define the directory to work in '
                                 '(defaults to cwd)')
        # Verbosity
        self.parser.add_argument('--verbose', '-v', dest='v',
                                 action='store_true',
                                 help='Run with verbose debug output')
        self.parser.add_argument('--debug', '-d', dest='debug',
                                 action='store_true',
                                 help='Run with debug output')
        self.parser.add_argument('-q', action='store_true',
                                 help='Run quietly only displaying errors')

    def setup_subparsers(self):
        """Setup basic subparsers that all clients should use"""

        # Setup some basic shared subparsers

        # help command
        self.register_help()

        # Add a common parsers
        self.register_build_common()
        self.register_rpm_common()

        # Other targets
        self.register_build()
        self.register_chainbuild()
        self.register_clean()
        self.register_clog()
        self.register_clone()
        self.register_copr_build()
        self.register_commit()
        self.register_compile()
        self.register_container_build()
        self.register_container_build_setup()
        self.register_diff()
        self.register_gimmespec()
        self.register_gitbuildhash()
        self.register_giturl()
        self.register_import_srpm()
        self.register_install()
        self.register_lint()
        self.register_local()
        self.register_mockbuild()
        self.register_mock_config()
        self.register_module_build()
        self.register_module_build_cancel()
        self.register_module_build_info()
        self.register_module_local_build()
        self.register_module_build_watch()
        self.register_module_overview()
        self.register_new()
        self.register_new_sources()
        self.register_patch()
        self.register_prep()
        self.register_pull()
        self.register_push()
        self.register_scratch_build()
        self.register_sources()
        self.register_srpm()
        self.register_switch_branch()
        self.register_tag()
        self.register_unused_patches()
        self.register_upload()
        self.register_verify_files()
        self.register_verrel()

    # All the register functions go here.
    def register_help(self):
        """Register the help command."""

        help_parser = self.subparsers.add_parser('help', help='Show usage')
        help_parser.set_defaults(command=self.parser.print_help)

    # Setup a couple common parsers to save code duplication
    def register_build_common(self):
        """Create a common build parser to use in other commands"""

        self.build_parser_common = argparse.ArgumentParser(
            'build_common', add_help=False)
        self.build_parser_common.add_argument(
            '--arches', nargs='*', help='Build for specific arches')
        self.build_parser_common.add_argument(
            '--md5', action='store_const', const='md5', default=None,
            dest='hash', help='Use md5 checksums (for older rpm hosts)')
        self.build_parser_common.add_argument(
            '--nowait', action='store_true', default=False,
            help="Don't wait on build")
        self.build_parser_common.add_argument(
            '--target', default=None,
            help='Define build target to build into')
        self.build_parser_common.add_argument(
            '--background', action='store_true', default=False,
            help='Run the build at a low priority')

    def register_rpm_common(self):
        """Create a common parser for rpm commands"""

        self.rpm_parser_common = argparse.ArgumentParser(
            'rpm_common', add_help=False)
        self.rpm_parser_common.add_argument(
            '--builddir', default=None, help='Define an alternate builddir')
        self.rpm_parser_common.add_argument(
            '--arch', help='Prep for a specific arch')

    def register_build(self):
        """Register the build target"""

        build_parser = self.subparsers.add_parser(
            'build', help='Request build', parents=[self.build_parser_common],
            description='This command requests a build of the package in the '
                        'build system. By default it discovers the target '
                        'to build for based on branch data, and uses the '
                        'latest commit as the build source.')
        build_parser.add_argument(
            '--skip-nvr-check', action='store_false', default=True,
            dest='nvr_check',
            help='Submit build to buildsystem without check if NVR was '
                 'already built. NVR is constructed locally and may be '
                 'different from NVR constructed during build on builder.')
        build_parser.add_argument(
            '--skip-tag', action='store_true', default=False,
            help='Do not attempt to tag package')
        build_parser.add_argument(
            '--scratch', action='store_true', default=False,
            help='Perform a scratch build')
        build_parser.add_argument(
            '--srpm', nargs='?', const='CONSTRUCT',
            help='Build from an srpm. If no srpm is provided with this option'
                 ' an srpm will be generated from current module content.')
        build_parser.set_defaults(command=self.build)

    def register_chainbuild(self):
        """Register the chain build target"""

        chainbuild_parser = self.subparsers.add_parser(
            'chain-build', parents=[self.build_parser_common],
            help='Build current package in order with other packages',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="""
Build current package in order with other packages.

example: %(name)s chain-build libwidget libgizmo

The current package is added to the end of the CHAIN list.
Colons (:) can be used in the CHAIN parameter to define groups of
packages.  Packages in any single group will be built in parallel
and all packages in a group must build successfully and populate
the repository before the next group will begin building.

For example:

%(name)s chain-build libwidget libaselib : libgizmo :

will cause libwidget and libaselib to be built in parallel, followed
by libgizmo and then the current directory package. If no groups are
defined, packages will be built sequentially.""" % {'name': self.name})
        chainbuild_parser.add_argument(
            'package', nargs='+',
            help='List the packages and order you want to build in')
        chainbuild_parser.set_defaults(command=self.chainbuild)

    def register_clean(self):
        """Register the clean target"""
        clean_parser = self.subparsers.add_parser(
            'clean', help='Remove untracked files',
            description="This command can be used to clean up your working "
                        "directory. By default it will follow .gitignore "
                        "rules.")
        clean_parser.add_argument(
            '--dry-run', '-n', action='store_true', help='Perform a dry-run')
        clean_parser.add_argument(
            '-x', action='store_true', help='Do not follow .gitignore rules')
        clean_parser.set_defaults(command=self.clean)

    def register_clog(self):
        """Register the clog target"""

        clog_parser = self.subparsers.add_parser(
            'clog', help='Make a clog file containing top changelog entry',
            description='This will create a file named "clog" that contains '
                        'the latest rpm changelog entry. The leading "- " '
                        'text will be stripped.')
        clog_parser.add_argument(
            '--raw', action='store_true', default=False,
            help='Generate a more "raw" clog without twiddling the contents')
        clog_parser.set_defaults(command=self.clog)

    def register_clone(self):
        """Register the clone target and co alias"""

        clone_parser = self.subparsers.add_parser(
            'clone', help='Clone and checkout a module',
            description='This command will clone the named module from the '
                        'configured repository base URL. By default it will '
                        'also checkout the master branch for your working '
                        'copy.')
        # Allow an old style clone with subdirs for branches
        clone_parser.add_argument(
            '--branches', '-B', action='store_true',
            help='Do an old style checkout with subdirs for branches')
        # provide a convenient way to get to a specific branch
        clone_parser.add_argument(
            '--branch', '-b', help='Check out a specific branch')
        # allow to clone without needing a account on the scm server
        clone_parser.add_argument(
            '--anonymous', '-a', action='store_true',
            help='Check out a module anonymously')
        # store the module to be cloned
        clone_parser.add_argument(
            'module', nargs=1, help='Name of the module to clone')
        # Eventually specify where to clone the module
        clone_parser.add_argument(
            "clone_target", default=None, nargs="?",
            help='Directory in which to clone the module')
        clone_parser.set_defaults(command=self.clone)

        # Add an alias for historical reasons
        co_parser = self.subparsers.add_parser(
            'co', parents=[clone_parser], conflict_handler='resolve',
            help='Alias for clone')
        co_parser.set_defaults(command=self.clone)

    def register_commit(self):
        """Register the commit target and ci alias"""

        commit_parser = self.subparsers.add_parser(
            'commit', help='Commit changes',
            description='This invokes a git commit. All tracked files with '
                        'changes will be committed unless a specific file '
                        'list is provided. $EDITOR will be used to generate a'
                        ' changelog message unless one is given to the '
                        'command. A push can be done at the same time.')
        commit_parser.add_argument(
            '-m', '--message', default=None,
            help='Use the given <msg> as the commit message summary')
        commit_parser.add_argument(
            '--with-changelog',
            action='store_true',
            default=None,
            help='Get the last changelog from SPEC as commit message content. '
                 'This option must be used with -m together.')
        commit_parser.add_argument(
            '-c', '--clog', default=False, action='store_true',
            help='Generate the commit message from the Changelog section')
        commit_parser.add_argument(
            '--raw', action='store_true', default=False,
            help='Make the clog raw')
        commit_parser.add_argument(
            '-t', '--tag', default=False, action='store_true',
            help='Create a tag for this commit')
        commit_parser.add_argument(
            '-F', '--file', default=None,
            help='Take the commit message from the given file')
        # allow one to commit /and/ push at the same time.
        commit_parser.add_argument(
            '-p', '--push', default=False, action='store_true',
            help='Commit and push as one action')
        # Allow a list of files to be committed instead of everything
        commit_parser.add_argument(
            'files', nargs='*', default=[],
            help='Optional list of specific files to commit')
        commit_parser.add_argument(
            '-s', '--signoff', default=False, action='store_true',
            help='Include a signed-off-by')
        commit_parser.set_defaults(command=self.commit)

        # Add a ci alias
        ci_parser = self.subparsers.add_parser(
            'ci', parents=[commit_parser], conflict_handler='resolve',
            help='Alias for commit')
        ci_parser.set_defaults(command=self.commit)

    def register_compile(self):
        """Register the compile target"""

        compile_parser = self.subparsers.add_parser(
            'compile', parents=[self.rpm_parser_common],
            help='Local test rpmbuild compile',
            description='This command calls rpmbuild to compile the source. '
                        'By default the prep and configure stages will be '
                        'done as well, unless the short-circuit option is '
                        'used.')
        compile_parser.add_argument('--short-circuit',
                                    action='store_true',
                                    help='short-circuit compile')
        compile_parser.add_argument('--nocheck',
                                    action='store_true',
                                    help='nocheck compile')
        compile_parser.set_defaults(command=self.compile)

    def register_diff(self):
        """Register the diff target"""

        diff_parser = self.subparsers.add_parser(
            'diff', help='Show changes between commits, commit and working '
                         'tree, etc',
            description='Use git diff to show changes that have been made to '
                        'tracked files. By default cached changes (changes '
                        'that have been git added) will not be shown.')
        diff_parser.add_argument(
            '--cached', default=False, action='store_true',
            help='View staged changes')
        diff_parser.add_argument(
            'files', nargs='*', default=[],
            help='Optionally diff specific files')
        diff_parser.set_defaults(command=self.diff)

    def register_gimmespec(self):
        """Register the gimmespec target"""

        gimmespec_parser = self.subparsers.add_parser(
            'gimmespec', help='Print the spec file name')
        gimmespec_parser.set_defaults(command=self.gimmespec)

    def register_gitbuildhash(self):
        """Register the gitbuildhash target"""

        gitbuildhash_parser = self.subparsers.add_parser(
            'gitbuildhash',
            help='Print the git hash used to build the provided n-v-r',
            description='This will show you the commit hash string used to '
                        'build the provided build n-v-r')
        gitbuildhash_parser.add_argument(
            'build', help='name-version-release of the build to query.')
        gitbuildhash_parser.set_defaults(command=self.gitbuildhash)

    def register_giturl(self):
        """Register the giturl target"""

        giturl_parser = self.subparsers.add_parser(
            'giturl', help='Print the git url for building',
            description='This will show you which git URL would be used in a '
                        'build command. It uses the git hashsum of the HEAD '
                        'of the current branch (which may not be pushed).')
        giturl_parser.set_defaults(command=self.giturl)

    def register_import_srpm(self):
        """Register the import-srpm target"""

        import_srpm_parser = self.subparsers.add_parser(
            'import', help='Import srpm content into a module',
            description='This will extract sources, patches, and the spec '
                        'file from an srpm and update the current module '
                        'accordingly. It will import to the current branch by '
                        'default.')
        import_srpm_parser.add_argument(
            '--skip-diffs', help="Don't show diffs when import srpms",
            action='store_true')
        import_srpm_parser.add_argument('srpm', help='Source rpm to import')
        import_srpm_parser.set_defaults(command=self.import_srpm)

    def register_install(self):
        """Register the install target"""

        install_parser = self.subparsers.add_parser(
            'install', parents=[self.rpm_parser_common],
            help='Local test rpmbuild install',
            description='This will call rpmbuild to run the install section. '
                        'All leading sections will be processed as well, '
                        'unless the short-circuit option is used.')
        install_parser.add_argument(
            '--short-circuit',
            action='store_true',
            default=False,
            help='short-circuit install')
        install_parser.add_argument(
            '--nocheck',
            action='store_true',
            help='nocheck install')
        install_parser.set_defaults(command=self.install, default=False)

    def register_lint(self):
        """Register the lint target"""

        lint_parser = self.subparsers.add_parser(
            'lint', help='Run rpmlint against local spec and build output if '
                         'present.',
            description='Rpmlint can be configured using the --rpmlintconf/-r'
                         ' option or by setting a .rpmlint file in the '
                         'working directory')
        lint_parser.add_argument(
            '--info', '-i', default=False, action='store_true',
            help='Display explanations for reported messages')
        lint_parser.add_argument(
            '--rpmlintconf', '-r', default=None,
            help='Use a specific configuration file for rpmlint')
        lint_parser.set_defaults(command=self.lint)

    def register_local(self):
        """Register the local target"""

        local_parser = self.subparsers.add_parser(
            'local', parents=[self.rpm_parser_common],
            help='Local test rpmbuild binary',
            description='Locally test run of rpmbuild producing binary RPMs. '
                        'The rpmbuild output will be logged into a file named'
                        ' .build-%{version}-%{release}.log')
        # Allow the user to just pass "--md5" which will set md5 as the
        # hash, otherwise use the default of sha256
        local_parser.add_argument(
            '--md5', action='store_const', const='md5', default=None,
            dest='hash', help='Use md5 checksums (for older rpm hosts)')
        local_parser.set_defaults(command=self.local)

    def register_new(self):
        """Register the new target"""

        new_parser = self.subparsers.add_parser(
            'new', help='Diff against last tag',
            description='This will use git to show a diff of all the changes '
                        '(even uncommitted changes) since the last git tag '
                        'was applied.')
        new_parser.set_defaults(command=self.new)

    def register_mockbuild(self):
        """Register the mockbuild target"""

        mockbuild_parser = self.subparsers.add_parser(
            'mockbuild', help='Local test build using mock',
            description='This will use the mock utility to build the package '
                        'for the distribution detected from branch '
                        'information. This can be overridden using the global'
                        ' --release option. Your user must be in the local '
                        '"mock" group.',
                        epilog="If config file for mock isn't found in the "
                               "/etc/mock directory, a temporary config "
                               "directory for mock is created and populated "
                               "with a config file created with mock-config.")
        mockbuild_parser.add_argument(
            '--root', '--mock-config', metavar='CONFIG',
            dest='root', help='Override mock configuration (like mock -r)')
        # Allow the user to just pass "--md5" which will set md5 as the
        # hash, otherwise use the default of sha256
        mockbuild_parser.add_argument(
            '--md5', action='store_const', const='md5', default=None,
            dest='hash', help='Use md5 checksums (for older rpm hosts)')
        mockbuild_parser.add_argument(
            '--no-clean', '-n', help='Do not clean chroot before building '
            'package', action='store_true')
        mockbuild_parser.add_argument(
            '--no-cleanup-after', help='Do not clean chroot after building '
            '(if automatic cleanup is enabled', action='store_true')
        mockbuild_parser.add_argument(
            '--no-clean-all', '-N', help='Alias for both --no-clean and '
            '--no-cleanup-after', action='store_true')
        mockbuild_parser.add_argument(
            '--with', help='Enable configure option (bcond) for the build',
            dest='bcond_with', action='append')
        mockbuild_parser.add_argument(
            '--without', help='Disable configure option (bcond) for the build',
            dest='bcond_without', action='append')
        mockbuild_parser.set_defaults(command=self.mockbuild)

    def register_mock_config(self):
        """Register the mock-config target"""

        mock_config_parser = self.subparsers.add_parser(
            'mock-config', help='Generate a mock config',
            description='This will generate a mock config based on the '
                        'buildsystem target')
        mock_config_parser.add_argument(
            '--target', help='Override target used for config', default=None)
        mock_config_parser.add_argument('--arch', help='Override local arch')
        mock_config_parser.set_defaults(command=self.mock_config)

    def register_module_build(self):
        sub_help = 'Build a module using MBS'
        self.module_build_parser = self.subparsers.add_parser(
            'module-build', help=sub_help, description=sub_help)
        self.module_build_parser.add_argument(
            'scm_url', nargs='?',
            help='The module\'s SCM URL. This defaults to the current repo.')
        self.module_build_parser.add_argument(
            'branch', nargs='?',
            help=('The module\'s SCM branch. This defaults to the current '
                  'checked-out branch.'))
        self.module_build_parser.add_argument(
            '--watch', '-w', help='Watch the module build',
            action='store_true')
        self.module_build_parser.add_argument(
            '--optional', action='append', metavar='KEY=VALUE',
            dest='optional',
            help='MBS optional arguments in the form of "key=value"')
        self.module_build_parser.set_defaults(command=self.module_build)

    def register_module_build_cancel(self):
        sub_help = 'Cancel an MBS module build'
        self.module_build_cancel_parser = self.subparsers.add_parser(
            'module-build-cancel', help=sub_help, description=sub_help)
        self.module_build_cancel_parser.add_argument(
            'build_id', help='The ID of the module build to cancel', type=int)
        self.module_build_cancel_parser.set_defaults(
            command=self.module_build_cancel)

    def register_module_build_info(self):
        sub_help = 'Show information of an MBS module build'
        self.module_build_info_parser = self.subparsers.add_parser(
            'module-build-info', help=sub_help, description=sub_help)
        self.module_build_info_parser.add_argument(
            'build_id', help='The ID of the module build', type=int)
        self.module_build_info_parser.set_defaults(
            command=self.module_build_info)

    def register_module_local_build(self):
        sub_help = 'Build a module locally using the mbs-manager command'
        self.module_build_local_parser = self.subparsers.add_parser(
            'module-build-local', help=sub_help, description=sub_help)
        self.module_build_local_parser.add_argument(
            '--file', nargs='?', dest='file_path',
            help=('The module\'s modulemd yaml file. If not specified, a yaml file'
                  ' with the same basename as the name of the repository will be used.'))
        self.module_build_local_parser.add_argument(
            '--stream', nargs='?', dest='stream',
            help=('The module\'s stream/SCM branch. This defaults to the current '
                  'checked-out branch.'))
        self.module_build_local_parser.add_argument(
            '--skip-tests', help='Adds a macro for skipping the check section',
            action='store_true', dest='skiptests')
        self.module_build_local_parser.add_argument(
            '--add-local-build', action='append', dest='local_builds_nsvs',
            metavar='BUILD_ID', type=int,
            help='Import previously finished local module builds into MBS')
        self.module_build_local_parser.set_defaults(
            command=self.module_build_local)

    def register_module_build_watch(self):
        sub_help = 'Watch an MBS build'
        self.module_build_watch_parser = self.subparsers.add_parser(
            'module-build-watch', help=sub_help, description=sub_help)
        self.module_build_watch_parser.add_argument(
            'build_id', help='The ID of the module build to watch', type=int)
        self.module_build_watch_parser.set_defaults(
            command=self.module_build_watch)

    def register_module_overview(self):
        sub_help = 'Shows an overview of MBS builds'
        self.module_overview_parser = self.subparsers.add_parser(
            'module-overview', help=sub_help, description=sub_help)
        self.module_overview_parser.add_argument(
            '--unfinished', help='Show unfinished module builds',
            default=False, action='store_true')
        self.module_overview_parser.add_argument(
            '--limit', default=10, type=int,
            help='The number of most recent module builds to display')
        self.module_overview_parser.set_defaults(
            command=self.module_overview)

    def register_new_sources(self):
        """Register the new-sources target"""

        # Make it part of self to be used later
        self.new_sources_parser = self.subparsers.add_parser(
            'new-sources',
            help='Upload source files',
            description='This will upload new source file(s) to lookaside '
                        'cache, and all file names listed in sources file '
                        'will be replaced. .gitignore will be also updated '
                        'with new uploaded file(s). Please remember to '
                        'commit them.')
        self.new_sources_parser.add_argument('files', nargs='+')
        self.new_sources_parser.set_defaults(command=self.new_sources, replace=True)

    def register_patch(self):
        """Register the patch target"""

        patch_parser = self.subparsers.add_parser(
            'patch', help='Create and add a gendiff patch file',
            epilog='Patch file will be named: package-version-suffix.patch '
                   'and the file will be added to the repo index')
        patch_parser.add_argument(
            '--rediff', action='store_true', default=False,
            help='Recreate gendiff file retaining comments Saves old patch '
                 'file with a suffix of ~')
        patch_parser.add_argument(
            'suffix', help='Look for files with this suffix to diff')
        patch_parser.set_defaults(command=self.patch)

    def register_prep(self):
        """Register the prep target"""

        prep_parser = self.subparsers.add_parser(
            'prep', parents=[self.rpm_parser_common],
            help='Local test rpmbuild prep',
            description='Use rpmbuild to "prep" the sources (unpack the '
                        'source archive(s) and apply any patches.)')
        prep_parser.set_defaults(command=self.prep)

    def register_pull(self):
        """Register the pull target"""

        pull_parser = self.subparsers.add_parser(
            'pull', help='Pull changes from the remote repository and update '
                         'the working copy.',
            description='This command uses git to fetch remote changes and '
                        'apply them to the current working copy. A rebase '
                        'option is available which can be used to avoid '
                        'merges.',
            epilog='See git pull --help for more details')
        pull_parser.add_argument(
            '--rebase', action='store_true',
            help='Rebase the locally committed changes on top of the remote '
                 'changes after fetching. This can avoid a merge commit, but '
                 'does rewrite local history.')
        pull_parser.add_argument(
            '--no-rebase', action='store_true',
            help='Do not rebase, overriding .git settings to the contrary')
        pull_parser.set_defaults(command=self.pull)

    def register_push(self):
        """Register the push target"""

        push_parser = self.subparsers.add_parser(
            'push', help='Push changes to remote repository')
        push_parser.add_argument('--force', '-f', help='Force push', action='store_true')
        push_parser.set_defaults(command=self.push)

    def register_scratch_build(self):
        """Register the scratch-build target"""

        scratch_build_parser = self.subparsers.add_parser(
            'scratch-build', help='Request scratch build',
            parents=[self.build_parser_common],
            description='This command will request a scratch build of the '
                        'package. Without providing an srpm, it will attempt '
                        'to build the latest commit, which must have been '
                        'pushed. By default all appropriate arches will be '
                        'built.')
        scratch_build_parser.add_argument(
            '--srpm', nargs='?', const='CONSTRUCT',
            help='Build from an srpm. If no srpm is provided with this '
                 'option an srpm will be generated from the current module '
                 'content.')
        scratch_build_parser.set_defaults(command=self.scratch_build)

    def register_sources(self):
        """Register the sources target"""

        sources_parser = self.subparsers.add_parser(
            'sources', help='Download source files',
            description='Download source files')
        sources_parser.add_argument(
            '--outdir', default=os.curdir,
            help='Directory to download files into (defaults to pwd)')
        sources_parser.set_defaults(command=self.sources)

    def register_srpm(self):
        """Register the srpm target"""

        srpm_parser = self.subparsers.add_parser(
            'srpm', help='Create a source rpm',
            description='Create a source rpm')
        # optionally define old style hashsums
        srpm_parser.add_argument(
            '--md5', action='store_const', const='md5', default=None,
            dest='hash', help='Use md5 checksums (for older rpm hosts)')
        srpm_parser.set_defaults(command=self.srpm)

    def register_copr_build(self):
        """Register the copr-build target"""

        copr_parser = self.subparsers.add_parser(
            'copr-build', help='Build package in Copr',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="""
Build package in Copr.

Note: you need to have set up correct api key. For more information
see API KEY section of copr-cli(1) man page.
""")

        copr_parser.add_argument(
            '--config', required=False,
            metavar='CONFIG', dest='copr_config',
            help="Path to an alternative Copr configuration file")
        copr_parser.add_argument(
            '--nowait', action='store_true', default=False,
            help="Don't wait on build")
        copr_parser.add_argument(
            'project', nargs=1, help='Name of the project in format USER/PROJECT')
        copr_parser.set_defaults(command=self.copr_build)

    def register_switch_branch(self):
        """Register the switch-branch target"""

        switch_branch_parser = self.subparsers.add_parser(
            'switch-branch', help='Work with branches',
            description='This command can switch to a local git branch. If '
                        'provided with a remote branch name that does not '
                        'have a local match it will create one.  It can also '
                        'be used to list the existing local and remote '
                        'branches.')
        switch_branch_parser.add_argument(
            'branch', nargs='?', help='Branch name to switch to')
        switch_branch_parser.add_argument(
            '-l', '--list', action='store_true',
            help='List both remote-tracking branches and local branches')
        switch_branch_parser.add_argument(
            '--fetch', help='Fetch new data from remote before switch',
            action='store_true', dest='fetch')
        switch_branch_parser.set_defaults(command=self.switch_branch)

    def register_tag(self):
        """Register the tag target"""

        tag_parser = self.subparsers.add_parser(
            'tag', help='Management of git tags',
            description='This command uses git to create, list, or delete '
                        'tags.')
        tag_parser.add_argument(
            '-f', '--force', default=False,
            action='store_true', help='Force the creation of the tag')
        tag_parser.add_argument(
            '-m', '--message', default=None,
            help='Use the given <msg> as the tag message')
        tag_parser.add_argument(
            '-c', '--clog', default=False, action='store_true',
            help='Generate the tag message from the spec changelog section')
        tag_parser.add_argument(
            '--raw', action='store_true', default=False,
            help='Make the clog raw')
        tag_parser.add_argument(
            '-F', '--file', default=None,
            help='Take the tag message from the given file')
        tag_parser.add_argument(
            '-l', '--list', default=False, action='store_true',
            help='List all tags with a given pattern, or all if not pattern '
                 'is given')
        tag_parser.add_argument(
            '-d', '--delete', default=False, action='store_true',
            help='Delete a tag')
        tag_parser.add_argument(
            'tag', nargs='?', default=None, help='Name of the tag')
        tag_parser.set_defaults(command=self.tag)

    def register_unused_patches(self):
        """Register the unused-patches target"""

        unused_patches_parser = self.subparsers.add_parser(
            'unused-patches',
            help='Print list of patches not referenced by name in the '
                 'specfile')
        unused_patches_parser.set_defaults(command=self.unused_patches)

    def register_upload(self):
        """Register the upload target"""

        upload_parser = self.subparsers.add_parser(
            'upload', parents=[self.new_sources_parser],
            conflict_handler='resolve',
            help='Upload source files',
            description='This command will upload new source file(s) to '
                        'lookaside cache. Source file names are appended to '
                        'sources file, and .gitignore will be also updated '
                        'with new uploaded file(s). Please remember to commit '
                        'them.')
        upload_parser.set_defaults(command=self.upload, replace=False)

    def register_verify_files(self):
        """Register the verify-files target"""

        verify_files_parser = self.subparsers.add_parser(
            'verify-files', parents=[self.rpm_parser_common],
            help='Locally verify %%files section',
            description="Locally run 'rpmbuild -bl' to verify the spec file's"
                        " %files sections. This requires a successful run of "
                        "'{0} install' in advance.".format(self.name))
        verify_files_parser.set_defaults(command=self.verify_files)

    def register_verrel(self):

        verrel_parser = self.subparsers.add_parser(
            'verrel', help='Print the name-version-release')
        verrel_parser.set_defaults(command=self.verrel)

    def register_container_build(self):
        self.container_build_parser = self.subparsers.add_parser(
            'container-build',
            help='Build a container',
            description='Build a container')

        group = self.container_build_parser.add_mutually_exclusive_group()
        group.add_argument(
                           '--compose-id',
                           dest='compose_ids',
                           metavar='COMPOSE_ID',
                           type=int,
                           help='ODCS composes used. '
                                'Cannot be used with --signing-intent or --repo-url',
                           nargs='*')
        group.add_argument(
                          '--signing-intent',
                          help='Signing intent of the ODCS composes. Cannot be '
                               'used with --compose-id or --repo-url')
        group.add_argument(
                          '--repo-url',
                          metavar="URL",
                          help='URL of yum repo file'
                               'Cannot be used with --signing-intent or --compose-id',
                          nargs='*')

        self.container_build_parser.add_argument(
            '--target',
            help='Override the default target',
            default=None)

        self.container_build_parser.add_argument(
            '--nowait',
            action='store_true',
            default=False,
            help="Don't wait on build")

        self.container_build_parser.add_argument(
            '--scratch',
            help='Scratch build',
            action="store_true")

        self.container_build_parser.add_argument(
            '--arches',
            action='store',
            nargs='*',
            help='Limit a scratch build to an arch. May have multiple arches.')

        self.container_build_parser.set_defaults(command=self.container_build)

    def register_container_build_setup(self):
        self.container_build_setup_parser = \
            self.subparsers.add_parser('container-build-setup',
                                       help='set options for container-build')
        group = self.container_build_setup_parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--get-autorebuild',
            help='Get autorebuild value',
            action='store_true',
            default=None)
        group.add_argument(
            '--set-autorebuild',
            help='Turn autorebuilds on/off',
            choices=('true', 'false'),
            default=None)
        self.container_build_setup_parser.set_defaults(
            command=self.container_build_setup)

    # All the command functions go here
    def usage(self):
        self.parser.print_help()

    def build(self, sets=None):
        # We may have gotten arches by way of scratch build, so handle them
        arches = None
        if hasattr(self.args, 'arches'):
            arches = self.args.arches
        # Place holder for if we build with an uploaded srpm or not
        url = None
        # See if this is a chain or not
        chain = None
        if hasattr(self.args, 'chain'):
            chain = self.args.chain
        # Need to do something with BUILD_FLAGS or KOJI_FLAGS here for compat
        if self.args.target:
            self.cmd._target = self.args.target
        # handle uploading the srpm if we got one
        if hasattr(self.args, 'srpm') and self.args.srpm:
            # See if we need to generate the srpm first
            if self.args.srpm == 'CONSTRUCT':
                self.log.debug('Generating an srpm')
                self.srpm()
                self.args.srpm = '%s.src.rpm' % self.cmd.nvr
            # Figure out if we want a verbose output or not
            callback = None
            if not self.args.q:
                callback = koji_cli.lib._progress_callback
            # define a unique path for this upload.  Stolen from /usr/bin/koji
            uniquepath = ('cli-build/%r.%s'
                          % (time.time(),
                             ''.join([random.choice(string.ascii_letters)
                                      for i in range(8)])))
            # Should have a try here, not sure what errors we'll get yet though
            self.cmd.koji_upload(self.args.srpm, uniquepath, callback=callback)
            if not self.args.q:
                # print an extra blank line due to callback oddity
                print('')
            url = '%s/%s' % (uniquepath, os.path.basename(self.args.srpm))
        # nvr_check option isn't set by all commands which calls this
        # function so handle it as an optional argument
        nvr_check = True
        if hasattr(self.args, 'nvr_check'):
            nvr_check = self.args.nvr_check
        task_id = self.cmd.build(self.args.skip_tag, self.args.scratch,
                                 self.args.background, url, chain, arches,
                                 sets, nvr_check)

        # Log out of the koji session
        self.cmd.kojisession.logout()

        if self.args.nowait:
            return

        # Pass info off to our koji task watcher
        return koji_cli.lib.watch_tasks(self.cmd.kojisession, [task_id])

    def chainbuild(self):
        if self.cmd.module_name in self.args.package:
            raise Exception('%s must not be in the chain' % self.cmd.module_name)

        # make sure we didn't get an empty chain
        if self.args.package == [':']:
            raise Exception('Must provide at least one dependency build')

        # Break the chain up into sections
        sets = False
        urls = []
        build_set = []
        self.log.debug('Processing chain %s', ' '.join(self.args.package))
        for component in self.args.package:
            if component == ':':
                # We've hit the end of a set, add the set as a unit to the
                # url list and reset the build_set.
                urls.append(build_set)
                self.log.debug('Created a build set: %s', ' '.join(build_set))
                build_set = []
                sets = True
            else:
                # Figure out the scm url to build from package name
                hash = self.cmd.get_latest_commit(component, self.cmd.repo.branch_merge)
                # Passing given package name to module_name parameter directly without
                # guessing namespace as no way to guess that. rpms/ will be
                # added by default if namespace is not given.
                url = self.cmd.construct_build_url(component, hash)
                # If there are no ':' in the chain list, treat each object as
                # an individual chain
                if ':' in self.args.package:
                    build_set.append(url)
                else:
                    urls.append([url])
                    self.log.debug('Created a build set: %s', url)
        # Take care of the last build set if we have one
        if build_set:
            self.log.debug('Created a build set: %s', ' '.join(build_set))
            urls.append(build_set)
        # See if we ended in a : making our last build it's own group
        if self.args.package[-1] == ':':
            self.log.debug('Making the last build its own set.')
            urls.append([])
        # pass it off to build
        self.args.chain = urls
        self.args.skip_tag = False
        self.args.scratch = False
        return self.build(sets=sets)

    def clean(self):
        dry = False
        useignore = True
        if self.args.dry_run:
            dry = True
        if self.args.x:
            useignore = False
        return self.cmd.clean(dry, useignore)

    def clog(self):
        self.cmd.clog(raw=self.args.raw)

    def clone(self):
        if self.args.branches:
            self.cmd.clone_with_dirs(self.args.module[0],
                                     anon=self.args.anonymous,
                                     target=self.args.clone_target)
        else:
            self.cmd.clone(self.args.module[0],
                           branch=self.args.branch,
                           anon=self.args.anonymous,
                           target=self.args.clone_target)

    def commit(self):
        if self.args.with_changelog and not self.args.message:
            raise rpkgError('--with-changelog must be used with -m together.')

        if self.args.message and self.args.with_changelog:
            # Combose commit message with a summary and content into a file.
            self.cmd.clog(True)
            clog_file = os.path.abspath(os.path.join(self.args.path, 'clog'))
            commit_msg_file = os.path.abspath(os.path.join(self.args.path, 'commit-message'))
            with open(commit_msg_file, 'w') as commit_msg:
                commit_msg.write(self.args.message)
                commit_msg.write('\n\n')
                with open(clog_file, 'r') as clog:
                    commit_msg.write(clog.read())
            self.args.file = commit_msg_file
            os.remove(clog_file)
            # This assignment is a magic because commit message is in the file
            # commit-message already.
            self.args.message = None
        elif self.args.clog:
            self.cmd.clog(self.args.raw)
            self.args.file = os.path.abspath(os.path.join(self.args.path, 'clog'))

        # It is okay without specifying either -m or --clog. Changes will be
        # committed with command ``git commit``, then git will invoke default
        # configured editor for you and let you enter the commit message.

        try:
            self.cmd.commit(self.args.message, self.args.file, self.args.files, self.args.signoff)
            if self.args.tag:
                tagname = self.cmd.nvr
                self.cmd.add_tag(tagname, True, self.args.message, self.args.file)
        except Exception:
            if self.args.tag:
                self.log.error('Could not commit, will not tag!')
            if self.args.push:
                self.log.error('Could not commit, will not push!')
            raise
        finally:
            if self.args.clog or self.args.with_changelog and os.path.isfile(self.args.file):
                os.remove(self.args.file)
                del self.args.file

        if self.args.push:
            self.push()

    def compile(self):
        self.sources()

        arch = None
        short = False
        nocheck = False
        if self.args.arch:
            arch = self.args.arch
        if self.args.short_circuit:
            short = True
        if self.args.nocheck:
            nocheck = True
        self.cmd.compile(arch=arch, short=short,
                         builddir=self.args.builddir, nocheck=nocheck)

    def container_build_koji(self):
        # Keep it around for backward compatibility
        self.container_build()

    def container_build(self):
        target_override = False
        # Override the target if we were supplied one
        if self.args.target:
            self.cmd._target = self.args.target
            target_override = True

        opts = {"scratch": self.args.scratch,
                "quiet": self.args.q,
                "yum_repourls": self.args.repo_url,
                "git_branch": self.cmd.branch_merge,
                "arches": self.args.arches,
                "compose_ids": self.args.compose_ids,
                "signing_intent": self.args.signing_intent}

        section_name = "%s.container-build" % self.name
        err_msg = "Missing %(option)s option in [%(plugin.section)s] section. " \
                  "Using %(option)s from [%(root.section)s]"
        err_args = {"plugin.section": section_name, "root.section": self.name}

        kojiconfig = kojiprofile = None

        if self.cmd._compat_kojiconfig:
            if self.config.has_option(section_name, "kojiconfig"):
                kojiconfig = self.config.get(section_name, "kojiconfig")
            else:
                err_args["option"] = "kojiconfig"
                self.log.debug(err_msg % err_args)
                kojiconfig = self.config.get(self.name, "kojiconfig")
        else:
            if self.config.has_option(section_name, "kojiprofile"):
                kojiprofile = self.config.get(section_name, "kojiprofile")
            else:
                err_args["option"] = "kojiprofile"
                self.log.debug(err_msg % err_args)
                kojiprofile = self.config.get(self.name, "kojiprofile")

        if self.config.has_option(section_name, "build_client"):
            build_client = self.config.get(section_name, "build_client")
        else:
            err_args["option"] = "build_client"
            self.log.debug(err_msg % err_args)
            build_client = self.config.get(self.name, "build_client")

        self.cmd.container_build_koji(
            target_override,
            opts=opts,
            kojiconfig=kojiconfig,
            kojiprofile=kojiprofile,
            build_client=build_client,
            koji_task_watcher=koji_cli.lib.watch_tasks,
            nowait=self.args.nowait)

    def container_build_setup(self):
        self.cmd.container_build_setup(get_autorebuild=self.args.get_autorebuild,
                                       set_autorebuild=self.args.set_autorebuild)

    def copr_build(self):
        self.log.debug('Generating an srpm')
        self.args.hash = None
        self.srpm()
        srpm_name = '%s.src.rpm' % self.cmd.nvr
        self.cmd.copr_build(self.args.project[0],
                            srpm_name,
                            self.args.nowait,
                            self.args.copr_config)

    def diff(self):
        self.cmd.diff(self.args.cached, self.args.files)

    def gimmespec(self):
        print(self.cmd.spec)

    def gitbuildhash(self):
        print(self.cmd.gitbuildhash(self.args.build))

    def giturl(self):
        print(self.cmd.giturl())

    def import_srpm(self):
        uploadfiles = self.cmd.import_srpm(self.args.srpm)
        if uploadfiles:
            self.cmd.upload(uploadfiles, replace=True)
        if not self.args.skip_diffs:
            self.cmd.diff(cached=True)
        self.log.info('--------------------------------------------')
        self.log.info("New content staged and new sources uploaded.")
        self.log.info("Commit if happy or revert with: git reset --hard HEAD")

    def install(self):
        self.sources()
        self.cmd.install(arch=self.args.arch,
                         short=self.args.short_circuit,
                         builddir=self.args.builddir,
                         nocheck=self.args.nocheck)

    def lint(self):
        self.cmd.lint(self.args.info, self.args.rpmlintconf)

    def local(self):
        self.sources()
        self.cmd.local(arch=self.args.arch, hashtype=self.args.hash,
                       builddir=self.args.builddir)

    def mockbuild(self):
        try:
            self.sources()
        except Exception as e:
            raise rpkgError('Could not download sources: %s', e)

        mockargs = []

        if self.args.no_clean or self.args.no_clean_all:
            mockargs.append('--no-clean')

        if self.args.no_cleanup_after or self.args.no_clean_all:
            mockargs.append('--no-cleanup-after')

        if self.args.bcond_with:
            for arg in self.args.bcond_with:
                mockargs.extend(['--with', arg])

        if self.args.bcond_without:
            for arg in self.args.bcond_without:
                mockargs.extend(['--without', arg])

        # Pick up any mockargs from the env
        try:
            mockargs += os.environ['MOCKARGS'].split()
        except KeyError:
            # there were no args
            pass
        try:
            self.cmd.mockbuild(mockargs, self.args.root,
                               hashtype=self.args.hash)
        except Exception as e:
            raise rpkgError(e)

    def mock_config(self):
        print(self.cmd.mock_config(self.args.target, self.args.arch))

    def module_build(self):
        """
        Builds a module using MBS
        :return: None
        """
        self.module_validate_config()
        scm_url, branch = self.cmd.module_get_scm_info(
            self.args.scm_url, self.args.branch)
        api_url = self.config.get(self.config_section, 'api_url')
        auth_method, oidc_id_provider, oidc_client_id, oidc_client_secret, \
            oidc_scopes = self.module_get_auth_config()

        if not self.args.q:
            print('Submitting the module build...')
        build_id = self._cmd.module_submit_build(
            api_url, scm_url, branch, auth_method, self.args.optional,
            oidc_id_provider, oidc_client_id, oidc_client_secret, oidc_scopes)
        if self.args.watch:
            self.module_watch_build(build_id)
        elif not self.args.q:
            print('The build #{0} was submitted to the MBS'
                  .format(build_id))

    def module_build_cancel(self):
        """
        Cancel an MBS build
        :return: None
        """
        self.module_validate_config()
        build_id = self.args.build_id
        api_url = self.config.get(self.config_section, 'api_url')
        auth_method, oidc_id_provider, oidc_client_id, oidc_client_secret, \
            oidc_scopes = self.module_get_auth_config()

        if not self.args.q:
            print('Cancelling module build #{0}...'.format(build_id))
        self.cmd.module_build_cancel(
            api_url, build_id, auth_method, oidc_id_provider, oidc_client_id,
            oidc_client_secret, oidc_scopes)
        if not self.args.q:
                print('The module build #{0} was cancelled'.format(build_id))

    def module_build_info(self):
        """
        Show information about an MBS build
        :return: None
        """
        self.module_validate_config()
        api_url = self.config.get(self.config_section, 'api_url')
        self.cmd.module_build_info(api_url, self.args.build_id)

    def module_build_local(self):
        """
        Build a module locally using mbs-manager
        :return: None
        """
        self.module_validate_config()

        if not self.args.stream:
            _, stream = self.cmd.module_get_scm_info()
        else:
            stream = self.args.stream

        if not self.args.file_path:
            file_path = os.path.join(self.cmd.path, self.cmd.module_name + ".yaml")
        else:
            file_path = self.args.file_path

        if not os.path.isfile(file_path):
            raise IOError("Module metadata yaml file %s not found!" % file_path)

        self.cmd.module_local_build(
            file_path, stream, self.args.local_builds_nsvs,
            verbose=self.args.v, debug=self.args.debug, skip_tests=self.args.skiptests)

    def module_get_auth_config(self):
        """
        Get the authentication configuration for the MBS
        :return: a tuple consisting of the authentication method, the OIDC ID
        provider, the OIDC client ID, the OIDC client secret, and the OIDC
        scopes. If the authentication method is not OIDC, the OIDC values in
        the tuple are set to None.
        """
        auth_method = self.config.get(self.config_section, 'auth_method')
        oidc_id_provider = None
        oidc_client_id = None
        oidc_client_secret = None
        oidc_scopes = None
        if auth_method == 'oidc':
            oidc_id_provider = self.config.get(
                self.config_section, 'oidc_id_provider')
            oidc_client_id = self.config.get(
                self.config_section, 'oidc_client_id')
            oidc_scopes_str = self.config.get(
                self.config_section, 'oidc_scopes')
            oidc_scopes = [
                scope.strip() for scope in oidc_scopes_str.split(',')]
            if self.config.has_option(self.config_section,
                                      'oidc_client_secret'):
                oidc_client_secret = self.config.get(
                    self.config_section, 'oidc_client_secret')
        return (auth_method, oidc_id_provider, oidc_client_id,
                oidc_client_secret, oidc_scopes)

    def module_build_watch(self):
        """
        Watch an MBS build from the command-line
        :return: None
        """
        self.module_validate_config()
        self.module_watch_build(self.args.build_id)

    def module_overview(self):
        """
        Show the overview of the latest builds in the MBS
        :return: None
        """
        self.module_validate_config()
        api_url = self.config.get(self.config_section, 'api_url')
        self.cmd.module_overview(
            api_url, self.args.limit, finished=(not self.args.unfinished))

    def module_validate_config(self):
        """
        Validates the configuration needed for MBS commands
        :return: None or rpkgError
        """
        self.config_section = '{0}.mbs'.format(self.name)
        # Verify that all necessary config options are set
        config_error = ('The config option "{0}" in the "{1}" section is '
                        'required')
        if not self.config.has_option(self.config_section, 'auth_method'):
            raise rpkgError(config_error.format(
                'auth_method', self.config_section))
        required_configs = ['api_url']
        auth_method = self.config.get(self.config_section, 'auth_method')
        if auth_method not in ['oidc', 'kerberos']:
            raise rpkgError('The MBS authentication mechanism of "{0}" is not '
                            'supported'.format(auth_method))

        if auth_method == 'oidc':
            # Try to import this now so the user gets immediate feedback if
            # it isn't installed
            try:
                import openidc_client  # noqa: F401
            except ImportError:
                raise rpkgError('python-openidc-client needs to be installed')
            required_configs.append('oidc_id_provider')
            required_configs.append('oidc_client_id')
            required_configs.append('oidc_scopes')
        elif auth_method == 'kerberos':
            # Try to import this now so the user gets immediate feedback if
            # it isn't installed
            try:
                import requests_kerberos  # noqa: F401
            except ImportError:
                raise rpkgError(
                    'python-requests-kerberos needs to be installed')

        for required_config in required_configs:
            if not self.config.has_option(self.config_section,
                                          required_config):
                raise rpkgError(config_error.format(
                    required_config, self.config_section))

    def module_watch_build(self, build_id):
        """
        Watches the MBS build in a loop that updates every 15 seconds.
        The loop ends when the build state is 'failed', 'done', or 'ready'.
        :param build_id: an integer of the module build to watch
        :return: None
        """
        self.module_validate_config()
        api_url = self.config.get(self.config_section, 'api_url')
        self.cmd.module_watch_build(api_url, build_id)

    def new(self):
        new_diff = self.cmd.new()
        # When running rpkg with old version GitPython<1.0 which returns string
        # in type basestring, no need to encode.
        if isinstance(new_diff, six.string_types):
            print(new_diff)
        else:
            print(new_diff.encode('utf-8'))

    def new_sources(self):
        # Check to see if the files passed exist
        for file in self.args.files:
            if not os.path.isfile(file):
                raise Exception('Path does not exist or is '
                                'not a file: %s' % file)
        self.cmd.upload(self.args.files, replace=self.args.replace)
        self.log.info("Source upload succeeded. Don't forget to commit the "
                      "sources file")

    def upload(self):
        self.new_sources()

    def patch(self):
        self.cmd.patch(self.args.suffix, rediff=self.args.rediff)

    def prep(self):
        self.sources()
        self.cmd.prep(arch=self.args.arch, builddir=self.args.builddir)

    def pull(self):
        self.cmd.pull(rebase=self.args.rebase,
                      norebase=self.args.no_rebase)

    def push(self):
        self.cmd.push(getattr(self.args, 'force', False))

    def scratch_build(self):
        # A scratch build is just a build with --scratch
        self.args.scratch = True
        self.args.skip_tag = False
        return self.build()

    def sources(self):
        """Download files listed in sources

        For command compile, prep, install, local and srpm, files are needed to
        be downloaded before doing what the command does. Hence, for these
        cases, sources is not called from command line. Instead, from rpkg
        inside.
        """
        # When sources is not called from command line, option outdir is not
        # available.
        outdir = getattr(self.args, 'outdir', None)
        self.cmd.sources(outdir)

    def srpm(self):
        self.sources()
        self.cmd.srpm(hashtype=self.args.hash)

    def switch_branch(self):
        if self.args.branch:
            self.cmd.switch_branch(self.args.branch, self.args.fetch)
        else:
            if self.args.fetch:
                self.cmd.repo.fetch_remotes()
            (locals, remotes) = self.cmd.repo.list_branches()
            # This is some ugly stuff here, but trying to emulate
            # the way git branch looks
            locals = ['  %s  ' % branch for branch in locals]
            local_branch = self.cmd.repo.active_branch.name
            locals[locals.index('  %s  ' %
                                local_branch)] = '* %s' % local_branch
            print('Locals:\n%s\nRemotes:\n  %s' %
                  ('\n'.join(locals), '\n  '.join(remotes)))

    def tag(self):
        if self.args.list:
            self.cmd.list_tag(self.args.tag)
        elif self.args.delete:
            self.cmd.delete_tag(self.args.tag)
        else:
            filename = self.args.file
            tagname = self.args.tag
            if not tagname or self.args.clog:
                if not tagname:
                    tagname = self.cmd.nvr
                if self.args.clog:
                    self.cmd.clog(self.args.raw)
                    filename = 'clog'
            self.cmd.add_tag(tagname, self.args.force,
                             self.args.message, filename)

    def unused_patches(self):
        unused = self.cmd.unused_patches()
        print('\n'.join(unused))

    def verify_files(self):
        self.cmd.verify_files(builddir=self.args.builddir)

    def verrel(self):
        print('%s-%s-%s' % (self.cmd.module_name, self.cmd.ver,
                            self.cmd.rel))

    # Stole these three functions from /usr/bin/koji
    def setupLogging(self, log):
        """Setup the various logging stuff."""

        # Assign the log object to self
        self.log = log

        # Add a log filter class
        class StdoutFilter(logging.Filter):

            def filter(self, record):
                # If the record level is 20 (INFO) or lower, let it through
                return record.levelno <= logging.INFO

        # have to create a filter for the stdout stream to filter out WARN+
        myfilt = StdoutFilter()
        # Simple format
        formatter = logging.Formatter('%(message)s')
        stdouthandler = logging.StreamHandler(sys.stdout)
        stdouthandler.addFilter(myfilt)
        stdouthandler.setFormatter(formatter)
        stderrhandler = logging.StreamHandler()
        stderrhandler.setLevel(logging.WARNING)
        stderrhandler.setFormatter(formatter)
        self.log.addHandler(stdouthandler)
        self.log.addHandler(stderrhandler)

    def parse_cmdline(self, manpage=False):
        """Parse the commandline, optionally make a manpage

        This also sets up self.user
        """

        if manpage:
            # Generate the man page
            man_name = self.name
            if man_name.endswith('.py'):
                man_name = man_name[:-3]
            man_page = __import__('%s' % man_name)
            man_page.generate(self.parser, self.subparsers)
            sys.exit(0)
            # no return possible

        # Parse the args
        self.args = self.parser.parse_args()

        if self.args.user:
            self.user = self.args.user
        else:
            self.user = pwd.getpwuid(os.getuid())[0]
