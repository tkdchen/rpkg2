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

import argparse
import sys
import os
import logging
import time
import random
import string
import xmlrpclib
import pwd
import koji

class cliClient(object):
    """This is a client class for rpkg clients."""

    def __init__(self, config, name=None):
        """This requires a ConfigParser object

        Name of the app can optionally set, or discovered from exe name
        """

        self.config = config
        self.name = name
        if not name:
            self.name = os.path.basename(sys.argv[0])
        # Property holders, set to none
        self._cmd = None
        self._module = None
        # Setup the base argparser
        self.setup_argparser()
        # Add a subparser
        self.subparsers = self.parser.add_subparsers(title = 'Targets',
                                                 description = 'These are '
                                                 'valid commands you can '
                                                 'ask %s to do' % self.name)
        # Register all the commands
        self.setup_subparsers()

    # Define some properties here, for lazy loading
    @property
    def cmd(self):
        """This is a property for the command attribute"""

        if not self._cmd:
            self.load_cmd()
        return(self._cmd)

    def load_cmd(self):
        """This sets up the cmd object"""

        # Load up the library based on exe name
        site = os.path.basename(sys.argv[0])

        # Set target if we got it as an option
        target = None
        if hasattr(self.args, 'target') and self.args.target:
            target = self.args.target

        # load items from the config file
        items = dict(self.config.items(site, raw=True))

        # Create the cmd object
        self._cmd = self.site.Commands(self.args.path,
                                       items['lookaside'],
                                       items['lookasidehash'],
                                       items['lookaside_cgi'],
                                       items['gitbaseurl'],
                                       items['anongiturl'],
                                       items['branchre'],
                                       items['kojiconfig'],
                                       items['build_client'],
                                       user=self.args.user,
                                       dist=self.args.dist,
                                       target=target,
                                       quiet=self.args.q)

    # This function loads the extra stuff once we figure out what site
    # we are
    def do_imports(self, site=None):
        """Import extra stuff not needed during build

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

        self.parser = argparse.ArgumentParser(prog = self.name,
                                              epilog = 'For detailed help '
                                              'pass --help to a target')
        # Add some basic arguments that should be used by all.
        # Add a config file
        self.parser.add_argument('--config', '-C',
                                 default=None,
                                 help='Specify a config file to use')
        # Allow forcing the dist value
        self.parser.add_argument('--dist', default=None,
                                 help='Override the discovered distribution')
        # Override the  discovered user name
        self.parser.add_argument('--user', default=None,
                                 help='Override the discovered user name')
        # Let the user define a path to work in rather than cwd
        self.parser.add_argument('--path', default=None,
                                 help='Define the directory to work in '
                                 '(defaults to cwd)')
        # Verbosity
        self.parser.add_argument('-v', action = 'store_true',
                                 help = 'Run with verbose debug output')
        self.parser.add_argument('-q', action = 'store_true',
                                 help = 'Run quietly only displaying errors')

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
        self.register_commit()
        self.register_compile()
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

        help_parser = self.subparsers.add_parser('help', help = 'Show usage')
        help_parser.set_defaults(command = self.parser.print_help)

    # Setup a couple common parsers to save code duplication
    def register_build_common(self):
        """Create a common build parser to use in other commands"""

        self.build_parser_common = argparse.ArgumentParser('build_common',
                                                         add_help = False)
        self.build_parser_common.add_argument('--arches', nargs = '*',
                                         help = 'Build for specific arches')
        self.build_parser_common.add_argument('--md5', action='store_const',
                              const='md5', default=None, dest='hash',
                              help='Use md5 checksums (for older rpm hosts)')
        self.build_parser_common.add_argument('--nowait',
                                         action = 'store_true',
                                         default = False,
                                         help = "Don't wait on build")
        self.build_parser_common.add_argument('--target',
                                         default = None,
                                         help = 'Define build target to build '
                                         'into')
        self.build_parser_common.add_argument('--background',
                                         action = 'store_true',
                                         default = False,
                                         help = 'Run the build at a low '
                                         'priority')

    def register_rpm_common(self):
        """Create a common parser for rpm commands"""

        self.rpm_parser_common = argparse.ArgumentParser('rpm_common',
                                                         add_help=False)
        self.rpm_parser_common.add_argument('--builddir', default=None,
                                        help='Define an alternate builddir')
        self.rpm_parser_common.add_argument('--arch',
                                            help='Prep for a specific arch')

    def register_build(self):
        """Register the build target"""

        build_parser = self.subparsers.add_parser('build',
                                         help = 'Request build',
                                         parents = [self.build_parser_common],
                                         description = 'This command \
                                         requests a build of the package \
                                         in the build system.  By default \
                                         it discovers the target to build for \
                                         based on branch data, and uses the \
                                         latest commit as the build source.')
        build_parser.add_argument('--skip-tag', action = 'store_true',
                                  default = False,
                                  help = 'Do not attempt to tag package')
        build_parser.add_argument('--scratch', action = 'store_true',
                                  default = False,
                                  help = 'Perform a scratch build')
        build_parser.add_argument('--srpm', nargs = '?', const = 'CONSTRUCT',
                                  help = 'Build from an srpm.  If no srpm \
                                  is provided with this option an srpm will \
                                  be generated from current module content.')
        build_parser.set_defaults(command = self.build)

    def register_chainbuild(self):
        """Register the chain build target"""

        chainbuild_parser = self.subparsers.add_parser('chain-build',
                    help = 'Build current package in order with other packages',
                    parents = [self.build_parser_common],
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                    description = """
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
by libgizmo and then the currect directory package. If no groups are
defined, packages will be built sequentially.""" %
                    {'name': self.name})
        chainbuild_parser.add_argument('package', nargs = '+',
                                       help = 'List the packages and order you '
                                       'want to build in')
        chainbuild_parser.set_defaults(command = self.chainbuild)

    def register_clean(self):
        """Register the clean target"""
        clean_parser = self.subparsers.add_parser('clean',
                                         help = 'Remove untracked files',
                                         description = "This command can be \
                                         used to clean up your working \
                                         directory.  By default it will \
                                         follow .gitignore rules.")
        clean_parser.add_argument('--dry-run', '-n', action = 'store_true',
                                  help = 'Perform a dry-run')
        clean_parser.add_argument('-x', action = 'store_true',
                                  help = 'Do not follow .gitignore rules')
        clean_parser.set_defaults(command = self.clean)

    def register_clog(self):
        """Register the clog target"""

        clog_parser = self.subparsers.add_parser('clog',
                                        help = 'Make a clog file containing '
                                        'top changelog entry',
                                        description = 'This will create a \
                                        file named "clog" that contains the \
                                        latest rpm changelog entry. The \
                                        leading "- " text will be stripped.')
        clog_parser.add_argument('--raw', action='store_true',
                                 default=False,
                                 help='Generate a more "raw" clog without \
                                 twiddling the contents')
        clog_parser.set_defaults(command = self.clog)

    def register_clone(self):
        """Register the clone target and co alias"""

        clone_parser = self.subparsers.add_parser('clone',
                                         help = 'Clone and checkout a module',
                                         description = 'This command will \
                                         clone the named module from the \
                                         configured repository base URL.  \
                                         By default it will also checkout \
                                         the master branch for your working \
                                         copy.')
        # Allow an old style clone with subdirs for branches
        clone_parser.add_argument('--branches', '-B',
                                  action = 'store_true',
                                  help = 'Do an old style checkout with \
                                  subdirs for branches')
        # provide a convenient way to get to a specific branch
        clone_parser.add_argument('--branch', '-b',
                                  help = 'Check out a specific branch')
        # allow to clone without needing a account on the scm server
        clone_parser.add_argument('--anonymous', '-a',
                                  action = 'store_true',
                                  help = 'Check out a module anonymously')
        # store the module to be cloned
        clone_parser.add_argument('module', nargs = 1,
                                  help = 'Name of the module to clone')
        clone_parser.set_defaults(command = self.clone)

        # Add an alias for historical reasons
        co_parser = self.subparsers.add_parser('co', parents = [clone_parser],
                                          conflict_handler = 'resolve',
                                          help = 'Alias for clone',
                                          description = 'This command will \
                                          clone the named module from the \
                                          configured repository base URL.  \
                                          By default it will also checkout \
                                          the master branch for your working \
                                          copy.')
        co_parser.set_defaults(command = self.clone)

    def register_commit(self):
        """Register the commit target and ci alias"""

        commit_parser = self.subparsers.add_parser('commit',
                                          help = 'Commit changes',
                                          description = 'This envokes a git \
                                          commit.  All tracked files with \
                                          changes will be committed unless \
                                          a specific file list is provided.  \
                                          $EDITOR will be used to generate a \
                                          changelog message unless one is \
                                          given to the command.  A push \
                                          can be done at the same time.')
        commit_parser.add_argument('-c', '--clog',
                                   default = False,
                                   action = 'store_true',
                                   help = 'Generate the commit message from \
                                   the Changelog section')
        commit_parser.add_argument('--raw', action='store_true',
                                   default=False,
                                   help='Make the clog raw')
        commit_parser.add_argument('-t', '--tag',
                                   default = False,
                                   action = 'store_true',
                                   help = 'Create a tag for this commit')
        commit_parser.add_argument('-m', '--message',
                                   default = None,
                                   help = 'Use the given <msg> as the commit \
                                   message')
        commit_parser.add_argument('-F', '--file',
                                   default = None,
                                   help = 'Take the commit message from the \
                                   given file')
        # allow one to commit /and/ push at the same time.
        commit_parser.add_argument('-p', '--push',
                                   default = False,
                                   action = 'store_true',
                                   help = 'Commit and push as one action')
        # Allow a list of files to be committed instead of everything
        commit_parser.add_argument('files', nargs = '*',
                                   default = [],
                                   help = 'Optional list of specific files to \
                                   commit')
        commit_parser.set_defaults(command = self.commit)

        # Add a ci alias
        ci_parser = self.subparsers.add_parser('ci', parents = [commit_parser],
                                          conflict_handler = 'resolve',
                                          help = 'Alias for commit',
                                          description = 'This envokes a git \
                                          commit.  All tracked files with \
                                          changes will be committed unless \
                                          a specific file list is provided.  \
                                          $EDITOR will be used to generate a \
                                          changelog message unless one is \
                                          given to the command.  A push \
                                          can be done at the same time.')
        ci_parser.set_defaults(command = self.commit)

    def register_compile(self):
        """Register the compile target"""

        compile_parser = self.subparsers.add_parser('compile',
                                       parents=[self.rpm_parser_common],
                                       help = 'Local test rpmbuild compile',
                                       description = 'This command calls \
                                       rpmbuild to compile the source.  \
                                       By default the prep and configure \
                                       stages will be done as well, \
                                       unless the short-circuit option \
                                       is used.')
        compile_parser.add_argument('--short-circuit', action = 'store_true',
                                    help = 'short-circuit compile')
        compile_parser.set_defaults(command = self.compile)

    def register_diff(self):
        """Register the diff target"""

        diff_parser = self.subparsers.add_parser('diff',
                                        help = 'Show changes between commits, '
                                        'commit and working tree, etc',
                                        description = 'Use git diff to show \
                                        changes that have been made to \
                                        tracked files.  By default cached \
                                        changes (changes that have been git \
                                        added) will not be shown.')
        diff_parser.add_argument('--cached', default = False,
                                 action = 'store_true',
                                 help = 'View staged changes')
        diff_parser.add_argument('files', nargs = '*',
                                 default = [],
                                 help = 'Optionally diff specific files')
        diff_parser.set_defaults(command = self.diff)

    def register_gimmespec(self):
        """Register the gimmespec target"""

        gimmespec_parser = self.subparsers.add_parser('gimmespec',
                                         help = 'Print the spec file name')
        gimmespec_parser.set_defaults(command = self.gimmespec)

    def register_gitbuildhash(self):
        """Register the gitbuildhash target"""

        gitbuildhash_parser = self.subparsers.add_parser('gitbuildhash',
                                          help = 'Print the git hash used '
                                          'to build the provided n-v-r',
                                          description = 'This will show you \
                                          the commit hash string used to \
                                          build the provided build n-v-r')
        gitbuildhash_parser.add_argument('build',
                                         help='name-version-release of the \
                                         build to query.')
        gitbuildhash_parser.set_defaults(command = self.gitbuildhash)

    def register_giturl(self):
        """Register the giturl target"""

        giturl_parser = self.subparsers.add_parser('giturl',
                                          help = 'Print the git url for '
                                          'building',
                                          description = 'This will show you \
                                          which git URL would be used in a \
                                          build command.  It uses the git \
                                          hashsum of the HEAD of the current \
                                          branch (which may not be pushed).')
        giturl_parser.set_defaults(command = self.giturl)

    def register_import_srpm(self):
        """Register the import-srpm target"""

        import_srpm_parser = self.subparsers.add_parser('import',
                                               help = 'Import srpm content '
                                               'into a module',
                                               description = 'This will \
                                               extract sources, patches, and \
                                               the spec file from an srpm and \
                                               update the current module \
                                               accordingly.  It will import \
                                               to the current branch by \
                                               default.')
        #import_srpm_parser.add_argument('--branch', '-b',
        #                                help = 'Branch to import onto',
        #                                default = 'devel')
        #import_srpm_parser.add_argument('--create', '-c',
        #                                help = 'Create a new local repo',
        #                                action = 'store_true')
        import_srpm_parser.add_argument('srpm',
                                        help = 'Source rpm to import')
        import_srpm_parser.set_defaults(command = self.import_srpm)

    def register_install(self):
        """Register the install target"""

        install_parser = self.subparsers.add_parser('install',
                                       parents=[self.rpm_parser_common],
                                       help = 'Local test rpmbuild install',
                                       description = 'This will call \
                                       rpmbuild to run the install \
                                       section.  All leading sections \
                                       will be processed as well, unless \
                                       the short-circuit option is used.')
        install_parser.add_argument('--short-circuit', action = 'store_true',
                                    help = 'short-circuit install',
                                    default = False)
        install_parser.set_defaults(command = self.install)

    def register_lint(self):
        """Register the lint target"""

        lint_parser = self.subparsers.add_parser('lint',
                                            help = 'Run rpmlint against local '
                                            'spec and build output if present. \
                                            Rpmlint can be configured using the \
                                            --rpmlintconf/-r option or by setting \
                                            a .rpmlint file in the working \
                                            directory')
        lint_parser.add_argument('--info', '-i',
                                 default = False,
                                 action = 'store_true',
                                 help = 'Display explanations for reported \
                                 messages')
        lint_parser.add_argument('--rpmlintconf', '-r',
                                 default = None,
                                 help = 'Use a specific configuration file \
                                 for rpmlint')
        lint_parser.set_defaults(command = self.lint)

    def register_local(self):
        """Register the local target"""

        local_parser = self.subparsers.add_parser('local',
                                     parents=[self.rpm_parser_common],
                                     help = 'Local test rpmbuild binary',
                                     description = 'Locally test run of \
                                     rpmbuild producing binary RPMs. The \
                                     rpmbuild output will be logged into a \
                                     file named \
                                     .build-%{version}-%{release}.log')
        # Allow the user to just pass "--md5" which will set md5 as the
        # hash, otherwise use the default of sha256
        local_parser.add_argument('--md5', action='store_const',
                              const='md5', default=None, dest='hash',
                              help='Use md5 checksums (for older rpm hosts)')
        local_parser.set_defaults(command = self.local)

    def register_new(self):
        """Register the new target"""

        new_parser = self.subparsers.add_parser('new',
                                       help = 'Diff against last tag',
                                       description = 'This will use git to \
                                       show a diff of all the changes \
                                       (even uncommited changes) since the \
                                       last git tag was applied.')
        new_parser.set_defaults(command = self.new)

    def register_mockbuild(self):
        """Register the mockbuild target"""

        mockbuild_parser = self.subparsers.add_parser('mockbuild',
                               help='Local test build using mock',
                               description='This will use the mock \
                               utility to build the package for the \
                               distribution detected from branch \
                               information.  This can be overridden \
                               using the global --dist option. Your \
                               user must be in the local "mock" group.',
                               epilog='To generate a mock \
                               config for the current branch \
                               use mock-config target and save it \
                               to /etc/mock/<branch>-candidate-<arch>.cfg')
        mockbuild_parser.add_argument('--root', help='Override mock root')
        # Allow the user to just pass "--md5" which will set md5 as the
        # hash, otherwise use the default of sha256
        mockbuild_parser.add_argument('--md5', action='store_const',
                              const='md5', default=None, dest='hash',
                              help='Use md5 checksums (for older rpm hosts)')
        mockbuild_parser.set_defaults(command=self.mockbuild)

    def register_mock_config(self):
        """Register the mock-config target"""

        mock_config_parser = self.subparsers.add_parser('mock-config',
                                        help='Generate a mock config',
                                        description='This will generate a \
                                        mock config based on the buildsystem \
                                        target')
        mock_config_parser.add_argument('--target',
                                        help='Override target used for config',
                                        default=None)
        mock_config_parser.add_argument('--arch',
                                        help='Override local arch')
        mock_config_parser.set_defaults(command=self.mock_config)

    def register_new_sources(self):
        """Register the new-sources target"""

        # Make it part of self to be used later
        self.new_sources_parser = self.subparsers.add_parser('new-sources',
                                              help = 'Upload new source files',
                                              description = 'This will upload \
                                              new source files to the \
                                              lookaside cache and remove \
                                              any existing files.  The \
                                              "sources" and .gitignore file \
                                              will be updated for the new \
                                              file(s).')
        self.new_sources_parser.add_argument('files', nargs = '+')
        self.new_sources_parser.set_defaults(command = self.new_sources,
                                             replace = True)

    def register_patch(self):
        """Register the patch target"""

        patch_parser = self.subparsers.add_parser('patch',
                                         help = 'Create and add a gendiff '
                                         'patch file',
                                         epilog = 'Patch file will be '
                                         'named: package-version-suffix.patch '
                                         'and the file will be added to the '
                                         'repo index')
        patch_parser.add_argument('--rediff',
                          help = 'Recreate gendiff file retaining comments \
                          Saves old patch file with a suffix of ~',
                          action = 'store_true',
                          default = False)
        patch_parser.add_argument('suffix',
                                  help = 'Look for files with this suffix \
                                  to diff')
        patch_parser.set_defaults(command = self.patch)

    def register_prep(self):
        """Register the prep target"""

        prep_parser = self.subparsers.add_parser('prep',
                                        parents=[self.rpm_parser_common],
                                        help = 'Local test rpmbuild prep',
                                        description = 'Use rpmbuild to "prep" \
                                        the sources (unpack the source \
                                        archive(s) and apply any patches.)')
        prep_parser.set_defaults(command = self.prep)

    def register_pull(self):
        """Register the pull target"""

        pull_parser = self.subparsers.add_parser('pull',
                                        help = 'Pull changes from remote '
                                        'repository and update working copy.',
                                        description = 'This command uses git \
                                        to fetch remote changes and apply \
                                        them to the current working copy.  A \
                                        rebase option is available which can \
                                        be used to avoid merges.',
                                        epilog = 'See git pull --help for \
                                        more details')
        pull_parser.add_argument('--rebase', action = 'store_true',
                             help = 'Rebase the locally committed changes on \
                             top of the remote changes after fetching.  This \
                             can avoid a merge commit, but does rewrite local \
                             history.')
        pull_parser.add_argument('--no-rebase', action = 'store_true',
                             help = 'Do not rebase, override .git settings to \
                             automatically rebase')
        pull_parser.set_defaults(command = self.pull)

    def register_push(self):
        """Register the push target"""

        push_parser = self.subparsers.add_parser('push',
                                            help = 'Push changes to remote '
                                            'repository')
        push_parser.set_defaults(command = self.push)

    def register_scratch_build(self):
        """Register the scratch-build target"""

        scratch_build_parser = self.subparsers.add_parser('scratch-build',
                                        help = 'Request scratch build',
                                        parents = [self.build_parser_common],
                                        description = 'This command \
                                        will request a scratch build \
                                        of the package.  Without \
                                        providing an srpm, it will \
                                        attempt to build the latest \
                                        commit, which must have been \
                                        pushed.  By default all \
                                        approprate arches will be \
                                        built.')
        scratch_build_parser.add_argument('--srpm', nargs = '?',
                                  const = 'CONSTRUCT',
                                  help = 'Build from an srpm.  If no srpm \
                                  is provided with this option an srpm will \
                                  be generated from current module content.')
        scratch_build_parser.set_defaults(command = self.scratch_build)

    def register_sources(self):
        """Register the sources target"""

        sources_parser = self.subparsers.add_parser('sources',
                                               help = 'Download source files')
        sources_parser.add_argument('--outdir',
                                    default = os.curdir,
                                    help = 'Directory to download files into \
                                    (defaults to pwd)')
        sources_parser.set_defaults(command = self.sources)

    def register_srpm(self):
        """Register the srpm target"""

        srpm_parser = self.subparsers.add_parser('srpm',
                                                 help = 'Create a source rpm')
        # optionally define old style hashsums
        srpm_parser.add_argument('--md5', action='store_const',
                              const='md5', default=None, dest='hash',
                              help='Use md5 checksums (for older rpm hosts)')
        srpm_parser.set_defaults(command = self.srpm)

    def register_switch_branch(self):
        """Register the switch-branch target"""

        switch_branch_parser = self.subparsers.add_parser('switch-branch',
                                                help = 'Work with branches',
                                                description = 'This command \
                                                can create or switch to a \
                                                local git branch.  It can \
                                                also be used to list the \
                                                existing local and remote \
                                                branches.')
        switch_branch_parser.add_argument('branch',  nargs = '?',
                                          help = 'Switch to or create branch')
        switch_branch_parser.add_argument('-l', '--list',
                                          help = 'List both remote-tracking \
                                          branches and local branches',
                                          action = 'store_true')
        switch_branch_parser.set_defaults(command = self.switch_branch)

    def register_tag(self):
        """Register the tag target"""

        tag_parser = self.subparsers.add_parser('tag',
                                       help = 'Management of git tags',
                                       description = 'This command uses git \
                                       to create, list, or delete tags.')
        tag_parser.add_argument('-f', '--force',
                                default = False,
                                action = 'store_true',
                                help = 'Force the creation of the tag')
        tag_parser.add_argument('-m', '--message',
                                default = None,
                                help = 'Use the given <msg> as the tag \
                                message')
        tag_parser.add_argument('-c', '--clog',
                                default = False,
                                action = 'store_true',
                                help = 'Generate the tag message from the \
                                spec changelog section')
        tag_parser.add_argument('--raw', action='store_true',
                                default=False,
                                help='Make the clog raw')
        tag_parser.add_argument('-F', '--file',
                                default = None,
                                help = 'Take the tag message from the given \
                                file')
        tag_parser.add_argument('-l', '--list',
                                default = False,
                                action = 'store_true',
                                help = 'List all tags with a given pattern, \
                                or all if not pattern is given')
        tag_parser.add_argument('-d', '--delete',
                                default = False,
                                action = 'store_true',
                                help = 'Delete a tag')
        tag_parser.add_argument('tag',
                                nargs = '?',
                                default = None,
                                help = 'Name of the tag')
        tag_parser.set_defaults(command = self.tag)

    def register_unused_patches(self):
        """Register the unused-patches target"""

        unused_patches_parser = self.subparsers.add_parser('unused-patches',
                                             help = 'Print list of patches '
                                             'not referenced by name in '
                                             'the specfile')
        unused_patches_parser.set_defaults(command = self.unused_patches)

    def register_upload(self):
        """Register the upload target"""

        upload_parser = self.subparsers.add_parser('upload',
                                          parents = [self.new_sources_parser],
                                          conflict_handler = 'resolve',
                                          help = 'Upload source files',
                                          description = 'This command will \
                                          add a new source archive to the \
                                          lookaside cache.  The sources and \
                                          .gitignore file will be updated \
                                          with the new file(s).')
        upload_parser.set_defaults(command = self.new_sources,
                                   replace = False)

    def register_verify_files(self):
        """Register the verify-files target"""

        verify_files_parser = self.subparsers.add_parser('verify-files',
                                            parents=[self.rpm_parser_common],
                                            help='Locally verify %%files '
                                            'section',
                                            description="Locally run \
                                            'rpmbuild -bl' to verify the \
                                            spec file's %files sections. \
                                            This requires a successful run \
                                            of the 'compile' target.")
        verify_files_parser.set_defaults(command = self.verify_files)

    def register_verrel(self):

        verrel_parser = self.subparsers.add_parser('verrel',
                                                   help = 'Print the '
                                                   'name-version-release')
        verrel_parser.set_defaults(command = self.verrel)

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
                callback = self._progress_callback
            # define a unique path for this upload.  Stolen from /usr/bin/koji
            uniquepath = 'cli-build/%r.%s' % (time.time(),
                                 ''.join([random.choice(string.ascii_letters)
                                          for i in range(8)]))
            # Should have a try here, not sure what errors we'll get yet though
            self.cmd.koji_upload(self.args.srpm, uniquepath, callback=callback)
            if not self.args.q:
                # print an extra blank line due to callback oddity
                print('')
            url = '%s/%s' % (uniquepath, os.path.basename(self.args.srpm))
        task_id = self.cmd.build(self.args.skip_tag, self.args.scratch,
                                 self.args.background, url, chain, arches,
                                 sets)
        # Now that we have the task ID we need to deal with it.
        if self.args.nowait:
            # Log out of the koji session
            self.cmd.kojisession.logout()
            return
        # pass info off to our koji task watcher
        self.cmd.kojisession.logout()
        return self._watch_koji_tasks(self.cmd.kojisession,
                                      [task_id])

    def chainbuild(self):
        if self.cmd.module_name in self.args.package:
            raise Exception('%s must not be in the chain' %
                            self.cmd.module_name)
        # make sure we didn't get an empty chain
        if self.args.package == [':']:
            raise Exception('Must provide at least one dependency '
                            'build')
        # Break the chain up into sections
        sets = False
        urls = []
        build_set = []
        self.log.debug('Processing chain %s' % ' '.join(self.args.package))
        for component in self.args.package:
            if component == ':':
                # We've hit the end of a set, add the set as a unit to the
                # url list and reset the build_set.
                urls.append(build_set)
                self.log.debug('Created a build set: %s' % ' '.join(build_set))
                build_set = []
                sets = True
            else:
                # Figure out the scm url to build from package name
                hash = self.cmd.get_latest_commit(component)
                url = self.cmd.anongiturl % {'module':
                                             component} + '#%s' % hash
                # If there are no ':' in the chain list, treat each object as an
                # individual chain
                if ':' in self.args.package:
                    build_set.append(url)
                else:
                    urls.append([url])
                    self.log.debug('Created a build set: %s' % url)
        # Take care of the last build set if we have one
        if build_set:
            self.log.debug('Created a build set: %s' % ' '.join(build_set))
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
                                     anon=self.args.anonymous)
        else:
            self.cmd.clone(self.args.module[0], branch=self.args.branch,
                           anon=self.args.anonymous)

    def commit(self):
        if self.args.clog:
            self.cmd.clog(self.args.raw)
            self.args.file = os.path.abspath(os.path.join(self.args.path,
                                                          'clog'))
        self.cmd.commit(self.args.message, self.args.file,
                        self.args.files)
        if self.args.tag:
            tagname = self.cmd.nvr
            self.cmd.add_tag(tagname, True, self.args.message,
                             self.args.file)
        if self.args.push:
            self.push()

    def compile(self):
        arch = None
        short = False
        if self.args.arch:
            arch = self.args.arch
        if self.args.short_circuit:
            short = True
        self.cmd.compile(arch=arch, short=short,
                         builddir=self.args.builddir)

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
        self.cmd.diff(cached=True)
        self.log.info('--------------------------------------------')
        self.log.info("New content staged and new sources uploaded.")
        self.log.info("Commit if happy or revert with: git reset --hard HEAD")

    def install(self):
        self.cmd.install(arch=self.args.arch,
                         short=self.args.short_circuit,
                         builddir=self.args.builddir)

    def lint(self):
        self.cmd.lint(self.args.info, self.args.rpmlintconf)

    def local(self):
        self.cmd.local(arch=self.args.arch, hashtype=self.args.hash,
                       builddir=self.args.builddir)

    def mockbuild(self):
        try:
            self.cmd.sources()
        except Exception, e:
            self.log.error('Could not download sources: %s' % e)
            sys.exit(1)

        # Pick up any mockargs from the env
        mockargs = []
        try:
            mockargs = os.environ['MOCKARGS'].split()
        except KeyError:
            # there were no args
            pass
        try:
            self.cmd.mockbuild(mockargs, self.args.root,
                               hashtype=self.args.hash)
        except Exception, e:
            self.log.error('Could not run mockbuild: %s' % e)
            sys.exit(1)

    def mock_config(self):
        try:
            print(self.cmd.mock_config(self.args.target, self.args.arch))
        except Exception, e:
            self.log.error('Could not generate the mock config: %s' % e)
            sys.exit(1)

    def new(self):
        print(self.cmd.new())

    def new_sources(self):
        # Check to see if the files passed exist
        for file in self.args.files:
            if not os.path.isfile(file):
                raise Exception('Path does not exist or is '
                                'not a file: %s' % file)
        self.cmd.upload(self.args.files, replace=self.args.replace)
        self.log.info("Source upload succeeded. Don't forget to commit the "
                      "sources file")

    def patch(self):
        self.cmd.patch(self.args.suffix, rediff=self.args.rediff)

    def prep(self):
        self.cmd.prep(arch=self.args.arch, builddir=self.args.builddir)

    def pull(self):
        self.cmd.pull(rebase=self.args.rebase,
                      norebase=self.args.no_rebase)

    def push(self):
        self.cmd.push()

    def scratch_build(self):
        # A scratch build is just a build with --scratch
        self.args.scratch = True
        self.args.skip_tag = False
        return self.build()

    def sources(self):
        self.cmd.sources(self.args.outdir)

    def srpm(self):
        self.cmd.sources()
        self.cmd.srpm(hashtype=self.args.hash)

    def switch_branch(self):
        if self.args.branch:
            self.cmd.switch_branch(self.args.branch)
        else:
            (locals, remotes) = self.cmd._list_branches()
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

    # Other class stuff goes here
    # The next 6 functions come from the koji project, from /usr/bin/koji
    # They should be in a library somewhere, but I have to steal them.
    # The code is licensed LGPLv2.1 and thus my (slightly) derived code
    # is too.
    def _display_tasklist_status(self, tasks):
        free = 0
        open = 0
        failed = 0
        done = 0
        for task_id in tasks.keys():
            status = tasks[task_id].info['state']
            if status == koji.TASK_STATES['FAILED']:
                failed += 1
            elif status == koji.TASK_STATES['CLOSED'] or \
            status == koji.TASK_STATES['CANCELED']:
                done += 1
            elif status == koji.TASK_STATES['OPEN'] or \
            status == koji.TASK_STATES['ASSIGNED']:
                open += 1
            elif status == koji.TASK_STATES['FREE']:
                free += 1
        self.log.info("  %d free  %d open  %d done  %d failed" %
                      (free, open, done, failed))
    
    def _display_task_results(self, tasks):
        for task in [task for task in tasks.values() if task.level == 0]:
            state = task.info['state']
            task_label = task.str()
    
            if state == koji.TASK_STATES['CLOSED']:
                self.log.info('%s completed successfully' % task_label)
            elif state == koji.TASK_STATES['FAILED']:
                self.log.info('%s failed' % task_label)
            elif state == koji.TASK_STATES['CANCELED']:
                self.log.info('%s was canceled' % task_label)
            else:
                # shouldn't happen
                self.log.info('%s has not completed' % task_label)
    
    def _watch_koji_tasks(self, session, tasklist):
        if not tasklist:
            return
        self.log.info('Watching tasks (this may be safely interrupted)...')
        # Place holder for return value
        rv = 0
        try:
            tasks = {}
            for task_id in tasklist:
                tasks[task_id] = TaskWatcher(task_id, session, self.log,
                                             quiet=self.args.q)
            while True:
                all_done = True
                for task_id,task in tasks.items():
                    changed = task.update()
                    if not task.is_done():
                        all_done = False
                    else:
                        if changed:
                            # task is done and state just changed
                            if not self.args.q:
                                self._display_tasklist_status(tasks)
                        if not task.is_success():
                            rv = 1
                    for child in session.getTaskChildren(task_id):
                        child_id = child['id']
                        if not child_id in tasks.keys():
                            tasks[child_id] = TaskWatcher(child_id,
                                                          session,
                                                          self.log,
                                                          task.level + 1,
                                                          quiet=self.args.q)
                            tasks[child_id].update()
                            # If we found new children, go through the list
                            # again, in case they have children also
                            all_done = False
                if all_done:
                    if not self.args.q:
                        print
                        self._display_task_results(tasks)
                    break
    
                time.sleep(1)
        except (KeyboardInterrupt):
            if tasks:
                self.log.info(
    """
Tasks still running. You can continue to watch with the '%s watch-task' command.
    Running Tasks:
    %s""" % (self.config.get(os.path.basename(sys.argv[0]), 'build_client'),
                             '\n'.join(['%s: %s' % (t.str(),
                                                    t.display_state(t.info))
                       for t in tasks.values() if not t.is_done()])))
            # A ^c should return non-zero so that it doesn't continue
            # on to any && commands.
            rv = 1
        return rv
    
    # Stole these three functions from /usr/bin/koji
    def _format_size(self, size):
        if (size / 1073741824 >= 1):
            return "%0.2f GiB" % (size / 1073741824.0)
        if (size / 1048576 >= 1):
            return "%0.2f MiB" % (size / 1048576.0)
        if (size / 1024 >=1):
            return "%0.2f KiB" % (size / 1024.0)
        return "%0.2f B" % (size)
    
    def _format_secs(self, t):
        h = t / 3600
        t = t % 3600
        m = t / 60
        s = t % 60
        return "%02d:%02d:%02d" % (h, m, s)
    
    def _progress_callback(self, uploaded, total, piece, time, total_time):
        percent_done = float(uploaded)/float(total)
        percent_done_str = "%02d%%" % (percent_done * 100)
        data_done = self._format_size(uploaded)
        elapsed = self._format_secs(total_time)
    
        speed = "- B/sec"
        if (time):
            if (uploaded != total):
                speed = self._format_size(float(piece)/float(time)) + "/sec"
            else:
                speed = self._format_size(float(total)/float(total_time)) + \
                "/sec"
    
        # write formated string and flush
        sys.stdout.write("[% -36s] % 4s % 8s % 10s % 14s\r" %
                         ('='*(int(percent_done*36)),
                          percent_done_str, elapsed, data_done, speed))
        sys.stdout.flush()

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

        if  manpage:
            # Generate the man page
            man_page = __import__('%s' % 
                                  os.path.basename(sys.argv[0]).strip('.py'))
            man_page.generate(self.parser, self.subparsers)
            sys.exit(0)
            # no return possible

        # Parse the args
        self.args = self.parser.parse_args()
        if self.args.user:
            self.user = self.args.user
        else:
            self.user = pwd.getpwuid(os.getuid())[0]

# Add a class stolen from /usr/bin/koji to watch tasks
# this was cut/pasted from koji, and then modified for local use.
# The formatting is koji style, not the stile of this file.  Do not use these
# functions as a style guide.
# This is fragile and hopefully will be replaced by a real kojiclient lib.
class TaskWatcher(object):

    def __init__(self,task_id,session,log,level=0,quiet=False):
        self.id = task_id
        self.session = session
        self.info = None
        self.level = level
        self.quiet = quiet
        self.log = log

    #XXX - a bunch of this stuff needs to adapt to different tasks

    def str(self):
        if self.info:
            label = koji.taskLabel(self.info)
            return "%s%d %s" % ('  ' * self.level, self.id, label)
        else:
            return "%s%d" % ('  ' * self.level, self.id)

    def __str__(self):
        return self.str()

    def get_failure(self):
        """Print infomation about task completion"""
        if self.info['state'] != koji.TASK_STATES['FAILED']:
            return ''
        error = None
        try:
            result = self.session.getTaskResult(self.id)
        except (xmlrpclib.Fault,koji.GenericError),e:
            error = e
        if error is None:
            # print "%s: complete" % self.str()
            # We already reported this task as complete in update()
            return ''
        else:
            return '%s: %s' % (error.__class__.__name__, str(error).strip())

    def update(self):
        """Update info and log if needed.  Returns True on state change."""
        if self.is_done():
            # Already done, nothing else to report
            return False
        last = self.info
        self.info = self.session.getTaskInfo(self.id, request=True)
        if self.info is None:
            raise Exception("No such task id: %i" % self.id)
        state = self.info['state']
        if last:
            #compare and note status changes
            laststate = last['state']
            if laststate != state:
                self.log.info("%s: %s -> %s" % (self.str(),
                                           self.display_state(last),
                                           self.display_state(self.info)))
                return True
            return False
        else:
            # First time we're seeing this task, so just show the current state
            self.log.info("%s: %s" % (self.str(), self.display_state(self.info)))
            return False

    def is_done(self):
        if self.info is None:
            return False
        state = koji.TASK_STATES[self.info['state']]
        return (state in ['CLOSED','CANCELED','FAILED'])

    def is_success(self):
        if self.info is None:
            return False
        state = koji.TASK_STATES[self.info['state']]
        return (state == 'CLOSED')

    def display_state(self, info):
        # We can sometimes be passed a task that is not yet open, but
        # not finished either.  info would be none.
        if not info:
            return 'unknown'
        if info['state'] == koji.TASK_STATES['OPEN']:
            if info['host_id']:
                host = self.session.getHost(info['host_id'])
                return 'open (%s)' % host['name']
            else:
                return 'open'
        elif info['state'] == koji.TASK_STATES['FAILED']:
            return 'FAILED: %s' % self.get_failure()
        else:
            return koji.TASK_STATES[info['state']].lower()

if __name__ == '__main__':
    client = cliClient()
    client.do_imports()
    client.parse_cmdline()

    if not client.args.path:
        try:
            client.args.path=os.getcwd()
        except:
            print('Could not get current path, have you deleted it?')
            sys.exit(1)

    # setup the logger -- This logger will take things of INFO or DEBUG and
    # log it to stdout.  Anything above that (WARN, ERROR, CRITICAL) will go
    # to stderr.  Normal operation will show anything INFO and above.
    # Quiet hides INFO, while Verbose exposes DEBUG.  In all cases WARN or
    # higher are exposed (via stderr).
    log = client.site.log
    client.setupLogging(log)

    if client.args.v:
        log.setLevel(logging.DEBUG)
    elif client.args.q:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.INFO)

    # Run the necessary command
    try:
        client.args.command()
    except KeyboardInterrupt:
        pass
