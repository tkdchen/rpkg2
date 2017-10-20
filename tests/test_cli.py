# -*- coding: utf-8 -*-

import gzip
import hashlib
import logging
import os
try:
    import rpmfluff
except ImportError:
    rpmfluff = None
import shutil
import six
import subprocess
import sys
import tempfile

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from six.moves import configparser
from six.moves import StringIO

import git
import pyrpkg.cli

try:
    import openidc_client
except ImportError:
    openidc_client = None

import utils
from mock import PropertyMock, call, mock_open, patch, Mock
from pyrpkg import rpkgError, Commands
from utils import CommandTestCase


# rpkg.conf for running tests below
config_file = os.path.join(os.path.dirname(__file__), 'fixtures', 'rpkg.conf')

fake_spec_content = '''
Summary: package demo
Name: pkgtool
Version: 0.1
Release: 1%{?dist}
License: GPL
%description
package demo for testing
%changelog
* Mon Nov 07 2016 tester@example.com
- first release 0.1
- add new spec
'''


class CliTestCase(CommandTestCase):

    def new_cli(self, cfg=None):
        config = configparser.SafeConfigParser()
        config.read(cfg or config_file)

        client = pyrpkg.cli.cliClient(config, name='rpkg')
        client.setupLogging(pyrpkg.log)
        pyrpkg.log.setLevel(logging.CRITICAL)
        client.do_imports()
        client.parse_cmdline()

        return client

    def make_changes(self, repo=None, untracked=None, commit=None, filename=None, content=''):
        repo_path = repo or self.cloned_repo_path
        _filename = filename or 'new-file.txt'

        self.write_file(os.path.join(repo_path, _filename), content)

        cmds = []
        if not untracked:
            cmds.append(['git', 'add', _filename])
        if not untracked and commit:
            cmds.append(['git', 'commit', '-m', 'Add new file {0}'.format(_filename)])

        for cmd in cmds:
            self.run_cmd(cmd, cwd=repo_path,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class TestModuleNameOption(CliTestCase):

    def get_cmd(self, module_name, cfg=None):
        cmd = ['rpkg', '--path', self.cloned_repo_path, '--module-name', module_name, 'verrel']
        with patch('sys.argv', new=cmd):
            cli = self.new_cli(cfg=cfg)
        return cli.cmd

    def test_non_namespaced(self):
        cmd = self.get_cmd('foo')
        self.assertEqual(cmd._module_name, 'foo')
        self.assertEqual(cmd.ns_module_name, 'foo')

    def test_just_module_name(self):
        cmd = self.get_cmd(
            'foo',
            os.path.join(os.path.dirname(__file__), 'fixtures', 'rpkg-ns.conf'))
        self.assertEqual(cmd._module_name, 'foo')
        self.assertEqual(cmd.ns_module_name, 'rpms/foo')

    def test_explicit_default(self):
        cmd = self.get_cmd(
            'rpms/foo',
            os.path.join(os.path.dirname(__file__), 'fixtures', 'rpkg-ns.conf'))
        self.assertEqual(cmd._module_name, 'foo')
        self.assertEqual(cmd.ns_module_name, 'rpms/foo')

    def test_with_namespace(self):
        cmd = self.get_cmd(
            'container/foo',
            os.path.join(os.path.dirname(__file__), 'fixtures', 'rpkg-ns.conf'))
        self.assertEqual(cmd._module_name, 'foo')
        self.assertEqual(cmd.ns_module_name, 'container/foo')

    def test_with_nested_namespace(self):
        cmd = self.get_cmd(
            'user/project/foo',
            os.path.join(os.path.dirname(__file__), 'fixtures', 'rpkg-ns.conf'))
        self.assertEqual(cmd._module_name, 'foo')
        self.assertEqual(cmd.ns_module_name, 'user/project/foo')


class TestKojiConfigBackwardCompatibility(CliTestCase):
    """Test backward compatibility of kojiconfig and kojiprofile

    Remove this test case after deprecated kojiconfig is removed eventually.
    """

    @patch('pyrpkg.Commands._deprecated_read_koji_config')
    @patch('pyrpkg.koji.read_config')
    def test_use_deprecated_kojiconfig(self,
                                       read_config,
                                       _deprecated_read_koji_config):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'build']

        cfg_file = os.path.join(os.path.dirname(__file__),
                                'fixtures',
                                'rpkg-deprecated-kojiconfig.conf')

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli(cfg_file)

        cli.cmd.read_koji_config()

        self.assertFalse(hasattr(cli.cmd, 'kojiprofile'))
        self.assertEqual(utils.kojiconfig, cli.cmd.kojiconfig)
        self.assertTrue(cli.cmd._compat_kojiconfig)

        read_config.assert_not_called()
        _deprecated_read_koji_config.assert_called_once()

    @patch('pyrpkg.Commands._deprecated_read_koji_config')
    @patch('pyrpkg.koji.read_config')
    def test_use_kojiprofile(self, read_config, _deprecated_read_koji_config):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'build']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()

        cli.cmd.read_koji_config()

        self.assertFalse(hasattr(cli.cmd, 'kojiconfig'))
        self.assertEqual(utils.kojiprofile, cli.cmd.kojiprofile)
        self.assertFalse(cli.cmd._compat_kojiconfig)

        read_config.assert_called_once_with(utils.kojiprofile)
        _deprecated_read_koji_config.assert_not_called()


class TestContainerBuildWithKoji(CliTestCase):
    """Test container_build with koji"""

    def setUp(self):
        super(TestContainerBuildWithKoji, self).setUp()
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')
        self.container_build_koji_patcher = patch(
            'pyrpkg.Commands.container_build_koji')
        self.mock_container_build_koji = \
            self.container_build_koji_patcher.start()

    def tearDown(self):
        self.mock_container_build_koji.stop()
        super(TestContainerBuildWithKoji, self).tearDown()

    def test_using_kojiprofile(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.container_build_koji()

        self.mock_container_build_koji.assert_called_once_with(
            False,
            opts={
                'scratch': False,
                'quiet': False,
                'yum_repourls': None,
                'git_branch': 'eng-rhel-7',
                'arches': None,
            },
            kojiconfig=None,
            kojiprofile='koji',
            build_client=utils.build_client,
            koji_task_watcher=cli._watch_koji_tasks,
            nowait=False
        )

    def test_override_target(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'container-build',
                   '--target', 'f25-docker-candidate']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.container_build_koji()

        self.assertEqual('f25-docker-candidate', cli.cmd._target)
        self.mock_container_build_koji.assert_called_once_with(
            True,
            opts={
                'scratch': False,
                'quiet': False,
                'yum_repourls': None,
                'git_branch': 'eng-rhel-7',
                'arches': None,
            },
            kojiconfig=None,
            kojiprofile='koji',
            build_client=utils.build_client,
            koji_task_watcher=cli._watch_koji_tasks,
            nowait=False
        )

    def test_using_deprecated_kojiconfig(self):
        """test_build_using_deprecated_kojiconfig

        This is for ensuring container_build works with deprecated kojiconfig.
        This test can be delete after kojiconfig is removed eventually.
        """
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--module-name', 'mycontainer',
                   'container-build']

        cfg_file = os.path.join(os.path.dirname(__file__),
                                'fixtures',
                                'rpkg-deprecated-kojiconfig.conf')

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli(cfg_file)
            cli.container_build_koji()

        self.mock_container_build_koji.assert_called_once_with(
            False,
            opts={
                'scratch': False,
                'quiet': False,
                'yum_repourls': None,
                'git_branch': 'eng-rhel-7',
                'arches': None,
            },
            kojiconfig='/path/to/koji.conf',
            kojiprofile=None,
            build_client=utils.build_client,
            koji_task_watcher=cli._watch_koji_tasks,
            nowait=False
        )

    def test_use_container_build_own_config(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build']
        cfg_file = os.path.join(os.path.dirname(__file__),
                                'fixtures',
                                'rpkg-container-own-config.conf')

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli(cfg_file)
            cli.container_build_koji()

        args, kwargs = self.mock_container_build_koji.call_args
        self.assertEqual('koji-container', kwargs['kojiprofile'])
        self.assertEqual('koji', kwargs['build_client'])


class TestClog(CliTestCase):

    def setUp(self):
        super(TestClog, self).setUp()
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-6')

    def cli_clog(self):
        """Run clog command"""
        cli = self.new_cli()
        cli.clog()

    def test_clog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'clog']

        with patch('sys.argv', new=cli_cmd):
            self.cli_clog()

        clog_file = os.path.join(self.cloned_repo_path, 'clog')
        self.assertTrue(os.path.exists(clog_file))
        clog = self.read_file(clog_file).strip()
        self.assertEqual('Initial version', clog)

    def test_raw_clog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'clog', '--raw']

        with patch('sys.argv', new=cli_cmd):
            self.cli_clog()

        clog_file = os.path.join(self.cloned_repo_path, 'clog')
        self.assertTrue(os.path.exists(clog_file))
        clog = self.read_file(clog_file).strip()
        self.assertEqual('- Initial version', clog)

    def test_reference_source_files_in_spec_should_not_break_clog(self):
        """SPEC containing Source0 or Patch0 should not break clog

        This case is reported in bug 1412224
        """
        spec_file = os.path.join(self.cloned_repo_path, self.spec_file)
        spec = self.read_file(spec_file)
        self.write_file(spec_file, spec.replace('#Source0:', 'Source0: extrafile.txt'))
        self.test_raw_clog()


class TestCommit(CliTestCase):

    def setUp(self):
        super(TestCommit, self).setUp()
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-6')
        self.make_changes()

    def get_last_commit_message(self):
        repo = git.Repo(self.cloned_repo_path)
        return six.next(repo.iter_commits()).message.strip()

    def cli_commit(self):
        """Run commit command"""
        cli = self.new_cli()
        cli.commit()

    def test_with_only_summary(self):
        cli = ['rpkg', '--path', self.cloned_repo_path, 'commit', '-m', 'new release']

        with patch('sys.argv', new=cli):
            self.cli_commit()

        commit_msg = self.get_last_commit_message()
        self.assertEqual('new release', commit_msg)

    def test_with_summary_and_changelog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'commit', '-m', 'new release', '--with-changelog']

        with patch('sys.argv', new=cli_cmd):
            self.cli_commit()

        commit_msg = self.get_last_commit_message()
        expected_commit_msg = '''new release

- Initial version'''
        self.assertEqual(expected_commit_msg, commit_msg)
        self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))
        self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'commit-message')))

    def test_with_clog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'commit', '--clog']

        with patch('sys.argv', new=cli_cmd):
            self.cli_commit()

        commit_msg = self.get_last_commit_message()
        expected_commit_msg = 'Initial version'
        self.assertEqual(expected_commit_msg, commit_msg)
        self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))

    def test_with_raw_clog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'commit', '--clog', '--raw']
        with patch('sys.argv', new=cli_cmd):
            self.cli_commit()

        commit_msg = self.get_last_commit_message()
        expected_commit_msg = '- Initial version'
        self.assertEqual(expected_commit_msg, commit_msg)
        self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))

    def test_cannot_use_with_changelog_without_a_summary(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'commit', '--with-changelog']

        with patch('sys.argv', new=cli_cmd):
            self.assertRaises(rpkgError, self.cli_commit)

    def test_push_after_commit(self):
        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'eng-rhel-6')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'commit', '-m', 'new release', '--with-changelog', '--push']

        with patch('sys.argv', new=cli_cmd):
            self.cli_commit()

        diff_commits = repo.git.rev_list('origin/master...master')
        self.assertEqual('', diff_commits)

    def test_signoff(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'commit', '-m', 'new release', '-s']

        with patch('sys.argv', new=cli_cmd):
            self.cli_commit()

            commit_msg = self.get_last_commit_message()
            self.assertTrue('Signed-off-by:' in commit_msg)


class TestPull(CliTestCase):

    def test_pull(self):
        self.make_changes(repo=self.repo_path, commit=True)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'pull']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.pull()

        origin_last_commit = str(six.next(git.Repo(self.repo_path).iter_commits()))
        cloned_last_commit = str(six.next(cli.cmd.repo.iter_commits()))
        self.assertEqual(origin_last_commit, cloned_last_commit)

    def test_pull_rebase(self):
        self.make_changes(repo=self.repo_path, commit=True)
        self.make_changes(repo=self.cloned_repo_path, commit=True,
                          filename='README.rst', content='Hello teseting.')

        origin_last_commit = str(six.next(git.Repo(self.repo_path).iter_commits()))

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'pull', '--rebase']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.pull()

        commits = cli.cmd.repo.iter_commits()
        six.next(commits)
        fetched_commit = str(six.next(commits))
        self.assertEqual(origin_last_commit, fetched_commit)
        self.assertEqual('', cli.cmd.repo.git.log('--merges'))


class TestSrpm(CliTestCase):
    """Test srpm command"""

    @patch('pyrpkg.Commands._run_command')
    def test_srpm(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'srpm']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.srpm()

        expected_cmd = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ['--nodeps', '-bs', os.path.join(cli.cmd.path, cli.cmd.spec)]
        _run_command.assert_called_once_with(expected_cmd, shell=True)


class TestCompile(CliTestCase):

    @patch('pyrpkg.Commands._run_command')
    def test_compile(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'compile']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.compile()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + ['-bc', spec]

        _run_command.assert_called_once_with(rpmbuild, shell=True)

    @patch('pyrpkg.Commands._run_command')
    def test_compile_with_options(self, _run_command):
        builddir = os.path.join(self.cloned_repo_path, 'builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q', 'compile',
                   '--builddir', builddir, '--short-circuit', '--arch', 'i686', '--nocheck']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.compile()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ["--define '_builddir %s'" % builddir, '--target', 'i686', '--short-circuit',
             '--nocheck', '--quiet', '-bc', spec]

        _run_command.assert_called_once_with(rpmbuild, shell=True)


class TestPrep(CliTestCase):

    @patch('pyrpkg.Commands._run_command')
    def test_prep(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'prep']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.prep()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + ['--nodeps', '-bp', spec]
        _run_command.assert_called_once_with(rpmbuild, shell=True)

    @patch('pyrpkg.Commands._run_command')
    def test_prep_with_options(self, _run_command):
        builddir = os.path.join(self.cloned_repo_path, 'builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q',
                   'compile', '--arch', 'i686', '--builddir', builddir]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.prep()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ["--define '_builddir %s'" % builddir, '--target', 'i686', '--quiet', '--nodeps',
             '-bp', spec]
        _run_command.assert_called_once_with(rpmbuild, shell=True)


class TestInstall(CliTestCase):

    @patch('pyrpkg.Commands._run_command')
    def test_install(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'install']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.install()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + ['-bi', spec]

        _run_command.assert_called_once_with(rpmbuild, shell=True)

    @patch('pyrpkg.Commands._run_command')
    def test_install_with_options(self, _run_command):
        builddir = os.path.join(self.cloned_repo_path, 'builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q',
                   'install', '--nocheck', '--arch', 'i686', '--builddir', builddir]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.install()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ["--define '_builddir %s'" % builddir, '--target', 'i686', '--nocheck', '--quiet',
             '-bi', spec]

        _run_command.assert_called_once_with(rpmbuild, shell=True)


class TestLocal(CliTestCase):

    @patch('pyrpkg.subprocess.check_call')
    def test_local(self, check_call):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'local']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.local()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + ['-ba', spec]
        tee = ['tee', '.build-%s-%s.log' % (cli.cmd.ver, cli.cmd.rel)]
        cmd = '%s | %s; exit "${PIPESTATUS[0]} ${pipestatus[1]}"' % (
            ' '.join(rpmbuild), ' '.join(tee)
        )
        check_call.assert_called_once_with(cmd, shell=True)

    @patch('pyrpkg.subprocess.check_call')
    def test_local_with_options(self, check_call):
        builddir = os.path.join(self.cloned_repo_path, 'this-builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q', 'local',
                   '--builddir', builddir, '--arch', 'i686']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.local()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ["--define '_builddir %s'" % builddir, '--target', 'i686', '--quiet', '-ba', spec]
        tee = ['tee', '.build-%s-%s.log' % (cli.cmd.ver, cli.cmd.rel)]

        cmd = '%s | %s; exit "${PIPESTATUS[0]} ${pipestatus[1]}"' % (
            ' '.join(rpmbuild), ' '.join(tee)
        )

        check_call.assert_called_once_with(cmd, shell=True)


class TestVerifyFiles(CliTestCase):

    @patch('pyrpkg.Commands._run_command')
    def test_verify_files(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'verify-files']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.verify_files()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + ['-bl', spec]
        _run_command.assert_called_once_with(rpmbuild, shell=True)

    @patch('pyrpkg.Commands._run_command')
    def test_verify_files_with_options(self, _run_command):
        builddir = os.path.join(self.cloned_repo_path, 'this-builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q',
                   'verify-files', '--builddir', builddir]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.verify_files()

        spec = os.path.join(cli.cmd.path, cli.cmd.spec)
        rpmbuild = ['rpmbuild'] + cli.cmd.rpmdefines + \
            ["--define '_builddir %s'" % builddir, '--quiet', '-bl', spec]
        _run_command.assert_called_once_with(rpmbuild, shell=True)


class TestVerrel(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_verrel_get_module_name_from_spec(self):
        cli_cmd = ['rpkg', '--path', self.repo_path, '--release', 'rhel-6', 'verrel']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.verrel()

        output = sys.stdout.getvalue().strip()
        self.assertEqual('docpkg-1.2-2.el6', output)

    @patch('sys.stdout', new=StringIO())
    def test_verrel(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'verrel']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.verrel()

        module_name = os.path.basename(self.repo_path)
        output = sys.stdout.getvalue().strip()
        self.assertEqual('{0}-1.2-2.el6'.format(module_name), output)


class TestSwitchBranch(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_list_branches(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'switch-branch']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.switch_branch()

        output = sys.stdout.getvalue()

        # Not test all branches listed, just test part of them.
        strings = ('Locals', 'Remotes', 'eng-rhel-6', 'origin/eng-rhel-6')
        for string in strings:
            self.assertTrue(string in output)

    def test_switch_branch_tracking_remote_branch(self):
        repo = git.Repo(self.cloned_repo_path)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'switch-branch', 'rhel-6.8']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.switch_branch()

        self.assertEqual('rhel-6.8', repo.active_branch.name)

        # Ensure local branch is tracking remote branch
        self.assertEqual('refs/heads/rhel-6.8', repo.git.config('branch.rhel-6.8.merge'))

    def test_switch_local_branch(self):
        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'master')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'switch-branch', 'eng-rhel-6']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.switch_branch()

        self.assertEqual('eng-rhel-6', repo.active_branch.name)

    def test_fail_on_dirty_repo(self):
        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'eng-rhel-6')

        self.make_changes()

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'switch-branch', 'master']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.switch_branch()
            except rpkgError as e:
                expected_msg = '{0} has uncommitted changes'.format(self.cloned_repo_path)
                self.assertTrue(expected_msg in str(e))
            else:
                self.fail('switch branch on dirty repo should fail.')

    def test_fail_switch_unknown_remote_branch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'switch-branch',
                   'unknown-remote-branch']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.switch_branch()
            except rpkgError as e:
                self.assertEqual('Unknown remote branch origin/unknown-remote-branch', str(e))
            else:
                self.fail('Switch to unknown remote branch should fail.')


class TestUnusedPatches(CliTestCase):

    def setUp(self):
        super(TestUnusedPatches, self).setUp()

        self.patches = (
            os.path.join(self.cloned_repo_path, '0001-add-new-feature.patch'),
            os.path.join(self.cloned_repo_path, '0002-hotfix.patch'),
        )
        for patch_file in self.patches:
            self.write_file(patch_file)
        git.Repo(self.cloned_repo_path).index.add(self.patches)

    @patch('sys.stdout', new=StringIO())
    def test_list_unused_patches(self):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-6')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'unused-patches']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.unused_patches()

        output = sys.stdout.getvalue().strip()
        expected_patches = [os.path.basename(patch_file) for patch_file in self.patches]
        self.assertEqual('\n'.join(expected_patches), output)


class TestDiff(CliTestCase):

    def setUp(self):
        super(TestDiff, self).setUp()

        with open(os.path.join(self.cloned_repo_path, self.spec_file), 'a') as f:
            f.write('- upgrade dependencies')

        self.make_changes()

    @patch('pyrpkg.Commands._run_command')
    @patch('pyrpkg.os.chdir')
    def test_diff(self, chdir, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'diff']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.diff()

        self.assertEqual(2, chdir.call_count)
        _run_command.assert_called_once_with(['git', 'diff'])

    @patch('pyrpkg.Commands._run_command')
    @patch('pyrpkg.os.chdir')
    def test_diff_cached(self, chdir, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'diff', '--cached']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.diff()

        self.assertEqual(2, chdir.call_count)
        _run_command.assert_called_once_with(['git', 'diff', '--cached'])


class TestGimmeSpec(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_gimmespec(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'gimmespec']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.gimmespec()

        output = sys.stdout.getvalue().strip()
        self.assertEqual('docpkg.spec', output)


class TestClean(CliTestCase):

    def test_dry_run(self):
        self.make_changes(untracked=True)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'clean', '--dry-run']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.clean()

        self.assertFilesExist(['new-file.txt'], search_dir=self.cloned_repo_path)

    def test_clean(self):
        self.make_changes(untracked=True)
        dirname = os.path.join(self.cloned_repo_path, 'temp-build')
        os.mkdir(dirname)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'clean']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.clean()

        self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'new-file.txt')))
        self.assertFalse(os.path.exists(dirname))

        # Ensure no tracked files and directories are removed.
        self.assertFilesExist(['docpkg.spec', '.git'], search_dir=self.cloned_repo_path)


class TestLint(CliTestCase):

    @patch('pyrpkg.Commands._run_command')
    def test_lint(self, _run_command):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')

        cli_cmd = ['rpkg', '--module-name', 'docpkg', '--path', self.cloned_repo_path, 'lint']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.lint()

        rpmlint = ['rpmlint', os.path.join(cli.cmd.path, cli.cmd.spec)]
        _run_command.assert_called_once_with(rpmlint, shell=True)

    @patch('pyrpkg.Commands._run_command')
    def test_lint_warning_with_info(self, _run_command):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')

        cli_cmd = ['rpkg', '--module-name', 'docpkg', '--path', self.cloned_repo_path,
                   'lint', '--info']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.lint()

        rpmlint = ['rpmlint', '-i', os.path.join(cli.cmd.path, cli.cmd.spec)]
        _run_command.assert_called_once_with(rpmlint, shell=True)


class TestGitUrl(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_giturl(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'giturl']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.giturl()

        last_commit = str(six.next(cli.cmd.repo.iter_commits()))
        expected_giturl = '{0}?#{1}'.format(
            cli.cmd.anongiturl % {'module': os.path.basename(self.repo_path)},
            last_commit)
        output = sys.stdout.getvalue().strip()
        self.assertEqual(expected_giturl, output)


class TestNew(CliTestCase):

    def test_no_tags_yet(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'new']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.new()
            except rpkgError as e:
                self.assertTrue('no tags' in str(e))
            else:
                self.fail('Command new should fail due to no tags in the repo.')

    @patch('sys.stdout', new=StringIO())
    def test_get_diff(self):
        self.run_cmd(['git', 'tag', '-m', 'New release v0.1', 'v0.1'],
                     cwd=self.cloned_repo_path,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.make_changes(repo=self.cloned_repo_path,
                          commit=True,
                          content='New change')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'new']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.new()

            output = sys.stdout.getvalue()
            self.assertTrue('+New change' in output)

    @patch('sys.stdout', new=StringIO())
    @patch('pyrpkg.Commands.new')
    def test_diff_returned_as_bytestring(self, new):
        # diff is return from Commands.new as bytestring when using
        # GitPython<1.0. So, mock new method directly to test diff in
        #  bytestring can be printed correctly.
        new.return_value = b'New content'
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'new']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.new()

        output = sys.stdout.getvalue()
        self.assertTrue(b'New content' in output)


class TestNewPrintUnicode(CliTestCase):
    """Test new diff contains unicode characters

    Fix issue 205: https://pagure.io/rpkg/issue/205
    """

    def setUp(self):
        super(TestNewPrintUnicode, self).setUp()
        self.run_cmd(['git', 'tag', '-m', 'New release 0.1', '0.1'],
                     cwd=self.cloned_repo_path,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.make_a_dummy_commit(git.Repo(self.cloned_repo_path),
                                 file_content='Include unicode chars á ř',
                                 commit_message=u'Write unicode to file')

    @patch('sys.stdout', new=StringIO())
    def test_get_diff(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'new']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.new()

            output = sys.stdout.getvalue()
            self.assertTrue('+Include unicode' in output)


class LookasideCacheMock(object):

    def init_lookaside_cache(self):
        self.lookasidecache_storage = tempfile.mkdtemp('rpkg-tests-lookasidecache-storage-')

    def destroy_lookaside_cache(self):
        shutil.rmtree(self.lookasidecache_storage)

    def lookasidecache_upload(self, module_name, filepath, hash):
        filename = os.path.basename(filepath)
        storage_filename = os.path.join(self.lookasidecache_storage, filename)
        with open(storage_filename, 'w') as fout:
            with open(filepath, 'r') as fin:
                fout.write(fin.read())

    def lookasidecache_download(self, name, filename, hash, outfile, hashtype=None, **kwargs):
        with open(outfile, 'w') as f:
            f.write('binary data')

    def hash_file(self, filename):
        md5 = hashlib.md5()
        with open(filename, 'r') as f:
            content = f.read()
            if six.PY3:
                content = content.encode('utf-8')
            md5.update(content)
        return md5.hexdigest()

    def assertFilesUploaded(self, filenames):
        assert isinstance(filenames, (tuple, list))
        for filename in filenames:
            self.assertTrue(
                os.path.exists(os.path.join(self.lookasidecache_storage, filename)),
                '{0} is not uploaded. It is not in fake lookaside storage.'.format(filename))


class TestUpload(LookasideCacheMock, CliTestCase):

    def setUp(self):
        super(TestUpload, self).setUp()

        self.init_lookaside_cache()
        self.sources_file = os.path.join(self.cloned_repo_path, 'sources')
        self.gitignore_file = os.path.join(self.cloned_repo_path, '.gitignore')
        self.readme_patch = os.path.join(self.cloned_repo_path, 'readme.patch')
        self.write_file(self.readme_patch, '+Hello world')

    def tearDown(self):
        self.destroy_lookaside_cache()
        super(TestUpload, self).tearDown()

    def test_upload(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'upload', self.readme_patch]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.upload', new=self.lookasidecache_upload):
                cli.upload()

        expected_sources_content = '{0}  readme.patch'.format(self.hash_file(self.readme_patch))
        self.assertEqual(expected_sources_content, self.read_file(self.sources_file).strip())
        self.assertTrue('readme.patch' in self.read_file(self.gitignore_file).strip())

        git_status = cli.cmd.repo.git.status()
        self.assertTrue('Changes not staged for commit:' not in git_status)
        self.assertTrue('Changes to be committed:' in git_status)

    def test_append_to_sources(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'upload', self.readme_patch]
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.upload', new=self.lookasidecache_upload):
                cli.upload()

        readme_rst = os.path.join(self.cloned_repo_path, 'README.rst')
        self.make_changes(filename=readme_rst, content='# dockpkg', commit=True)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'upload', readme_rst]
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.upload', new=self.lookasidecache_upload):
                cli.upload()

        expected_sources_content = [
            '{0}  {1}'.format(self.hash_file(self.readme_patch),
                              os.path.basename(self.readme_patch)),
            '{0}  {1}'.format(self.hash_file(readme_rst),
                              os.path.basename(readme_rst)),
            ]
        self.assertEqual(expected_sources_content,
                         self.read_file(self.sources_file).strip().split('\n'))


class TestSources(LookasideCacheMock, CliTestCase):

    def setUp(self):
        super(TestSources, self).setUp()
        self.init_lookaside_cache()

        # Uploading a file aims to run the loop in sources command.
        self.readme_patch = os.path.join(self.cloned_repo_path, 'readme.patch')
        self.write_file(self.readme_patch, content='+Welcome to README')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'upload', self.readme_patch]
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.upload', new=self.lookasidecache_upload):
                cli.upload()

    def tearDown(self):
        # Tests may put a file readme.patch in current directory, so, let's remove it.
        if os.path.exists('readme.patch'):
            os.remove('readme.patch')
        self.destroy_lookaside_cache()
        super(TestSources, self).tearDown()

    def test_sources(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'sources']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.download',
                       new=self.lookasidecache_download):
                cli.sources()

        # NOTE: without --outdir, whatever to run sources command in package
        # repository, sources file is downloaded into current working
        # directory. Is this a bug, or need to improve?
        self.assertTrue(os.path.exists('readme.patch'))

    def test_sources_to_outdir(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'sources', '--outdir', self.cloned_repo_path]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.download',
                       new=self.lookasidecache_download):
                cli.sources()

        self.assertFilesExist(['readme.patch'], search_dir=self.cloned_repo_path)


class TestFailureImportSrpm(CliTestCase):

    def test_import_nonexistent_srpm(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'import', 'nonexistent-srpm']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.import_srpm()
            except rpkgError as e:
                self.assertEqual('File not found.', str(e))
            else:
                self.fail('import_srpm should fail if srpm does not exist.')

    def test_repo_is_dirty(self):
        srpm_file = os.path.join(os.path.dirname(__file__), 'fixtures', 'docpkg-0.2-1.src.rpm')
        self.make_changes()
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'import', srpm_file]
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.import_srpm()
            except rpkgError as e:
                self.assertEqual('There are uncommitted changes in your repo', str(e))
            else:
                self.fail('import_srpm should fail if package repository is dirty.')


@unittest.skipUnless(rpmfluff, 'rpmfluff is not available')
class TestImportSrpm(LookasideCacheMock, CliTestCase):

    def setUp(self):
        super(TestImportSrpm, self).setUp()
        self.init_lookaside_cache()

        # Gzip file that will be added into the SRPM
        self.docpkg_gz = os.path.join(self.cloned_repo_path, 'docpkg.gz')
        gzf = gzip.open(self.docpkg_gz, 'w')
        gzf.write(b'file content of docpkg')
        gzf.close()

        # Build the SRPM
        self.build = rpmfluff.SimpleRpmBuild(name='docpkg', version='0.2', release='1')
        self.build.add_changelog_entry('- New release 0.2-1', version='0.2', release='1',
                                       nameStr='tester <tester@example.com>')
        self.build.add_simple_payload_file()
        content = gzip.open(self.docpkg_gz, 'r').read()
        if six.PY3:
            content = str(content, encoding='utf-8')
        self.build.add_source(rpmfluff.SourceFile('docpkg.gz', content))
        self.build.make()
        self.srpm_file = self.build.get_built_srpm()

        self.chaos_repo = tempfile.mkdtemp(prefix='rpkg-tests-chaos-repo-')
        cmds = (
            ['git', 'init'],
            ['touch', 'README.rst'],
            ['git', 'add', 'README.rst'],
            ['git', 'config', 'user.name', 'tester'],
            ['git', 'config', 'user.email', 'tester@example.com'],
            ['git', 'commit', '-m', '"Add README"'],
        )
        for cmd in cmds:
            self.run_cmd(cmd, cwd=self.chaos_repo,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def tearDown(self):
        os.remove(self.docpkg_gz)
        shutil.rmtree(self.build.get_base_dir())
        shutil.rmtree(self.chaos_repo)
        self.destroy_lookaside_cache()
        super(TestImportSrpm, self).tearDown()

    def assert_import_srpm(self, target_repo):
        cli_cmd = ['rpkg', '--path', target_repo, '--module-name', 'docpkg',
                   'import', '--skip-diffs', self.srpm_file]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.lookaside.CGILookasideCache.upload', self.lookasidecache_upload):
                cli.import_srpm()

        docpkg_gz = os.path.basename(self.docpkg_gz)
        diff_cached = cli.cmd.repo.git.diff('--cached')
        self.assertTrue('+- - New release 0.2-1' in diff_cached)
        self.assertTrue('+hello world' in diff_cached)
        self.assertFilesExist(['.gitignore',
                               'sources',
                               'docpkg.spec',
                               'hello-world.txt',
                               docpkg_gz], search_dir=target_repo)
        self.assertFilesNotExist(['CHANGELOG.rst'], search_dir=target_repo)
        with open(os.path.join(target_repo, 'sources'), 'r') as f:
            self.assertEqual(
                '{0}  {1}'.format(self.hash_file(os.path.join(target_repo, docpkg_gz)), docpkg_gz),
                f.read().strip())
        with open(os.path.join(target_repo, '.gitignore'), 'r') as f:
            self.assertEqual('/{0}'.format(docpkg_gz), f.read().strip())
        self.assertFilesUploaded([docpkg_gz])

    def test_import(self):
        self.assert_import_srpm(self.chaos_repo)
        self.assert_import_srpm(self.cloned_repo_path)


class TestMockbuild(CliTestCase):
    """Test mockbuild command"""

    def setUp(self):
        super(TestMockbuild, self).setUp()
        self.run_command_patcher = patch('pyrpkg.Commands._run_command')
        self.mock_run_command = self.run_command_patcher.start()

    def tearDown(self):
        self.run_command_patcher.stop()
        super(TestMockbuild, self).tearDown()

    def mockbuild(self, cli_cmd):
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mockbuild()
            return cli

    def test_mockbuild(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-6', 'mockbuild',
                   '--root', '/etc/mock/some-root']
        cli = self.mockbuild(cli_cmd)

        expected_cmd = ['mock', '-r', '/etc/mock/some-root',
                        '--resultdir', cli.cmd.mock_results_dir, '--rebuild',
                        cli.cmd.srpmname]
        self.mock_run_command.assert_called_with(expected_cmd)

    def test_with_without(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-6', 'mockbuild',
                   '--root', '/etc/mock/some-root',
                   '--with', 'a', '--without', 'b', '--with', 'c',
                   '--without', 'd']
        cli = self.mockbuild(cli_cmd)

        expected_cmd = ['mock', '--with', 'a', '--with', 'c',
                        '--without', 'b', '--without', 'd',
                        '-r', '/etc/mock/some-root',
                        '--resultdir', cli.cmd.mock_results_dir, '--rebuild',
                        cli.cmd.srpmname]
        self.mock_run_command.assert_called_with(expected_cmd)

    @patch('pyrpkg.Commands._config_dir_basic')
    @patch('pyrpkg.Commands._config_dir_other')
    @patch('os.path.exists', return_value=False)
    def test_use_mock_config_got_from_koji(
            self, exists, config_dir_other, config_dir_basic):
        config_dir_basic.return_value = '/path/to/config-dir'

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-7', 'mockbuild']
        self.mockbuild(cli_cmd)

        args, kwargs = self.mock_run_command.call_args
        cmd_to_execute = args[0]

        self.assertTrue('--configdir' in cmd_to_execute)
        self.assertTrue(config_dir_basic.return_value in cmd_to_execute)

    @patch('pyrpkg.Commands._config_dir_basic')
    @patch('os.path.exists', return_value=False)
    def test_fail_to_store_mock_config_in_created_config_dir(
            self, exists, config_dir_basic):
        config_dir_basic.side_effect = rpkgError

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-7', 'mockbuild']
        self.assertRaises(rpkgError, self.mockbuild, cli_cmd)

    @patch('pyrpkg.Commands._config_dir_basic')
    @patch('pyrpkg.Commands._config_dir_other')
    @patch('os.path.exists', return_value=False)
    def test_fail_to_populate_mock_config(
            self, exists, config_dir_other, config_dir_basic):
        config_dir_basic.return_value = '/path/to/config-dir'
        config_dir_other.side_effect = rpkgError

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-7', 'mockbuild']
        self.assertRaises(rpkgError, self.mockbuild, cli_cmd)


class TestCoprBuild(CliTestCase):
    """Test copr command"""

    def setUp(self):
        super(TestCoprBuild, self).setUp()
        self.nvr_patcher = patch('pyrpkg.Commands.nvr',
                                 new_callable=PropertyMock,
                                 return_value='rpkg-1.29-3.fc26')
        self.mock_nvr = self.nvr_patcher.start()

        self.srpm_patcher = patch('pyrpkg.cli.cliClient.srpm')
        self.mock_srpm = self.srpm_patcher.start()

        self.run_command_patcher = patch('pyrpkg.Commands._run_command')
        self.mock_run_command = self.run_command_patcher.start()

    def tearDown(self):
        self.run_command_patcher.stop()
        self.srpm_patcher.stop()
        self.nvr_patcher.stop()
        super(TestCoprBuild, self).tearDown()

    def assert_copr_build(self, cli_cmd, expected_copr_cli):
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.copr_build()

        self.mock_srpm.assert_called_once()
        self.mock_run_command.assert_called_once_with(expected_copr_cli)

    def test_copr_build(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'copr-build', 'user/project']

        self.assert_copr_build(cli_cmd, [
            'copr-cli', 'build', 'user/project',
            '{0}.src.rpm'.format(self.mock_nvr.return_value)
        ])

    def test_copr_build_no_wait(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'copr-build', '--nowait', 'user/project']

        self.assert_copr_build(cli_cmd, [
            'copr-cli', 'build', '--nowait', 'user/project',
            '{0}.src.rpm'.format(self.mock_nvr.return_value)
        ])

    def test_copr_build_with_alternative_config_file(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'copr-build', '--config', '/path/to/alternative/config',
                   'user/project']

        self.assert_copr_build(cli_cmd, [
            'copr-cli', '--config', '/path/to/alternative/config',
            'build', 'user/project',
            '{0}.src.rpm'.format(self.mock_nvr.return_value)
        ])


class TestMockConfig(CliTestCase):
    """Test mockconfig command"""

    def setUp(self):
        super(TestMockConfig, self).setUp()

        self.topurl_patcher = patch('pyrpkg.Commands.topurl',
                                    new_callable=PropertyMock,
                                    return_value='http://localhost/hub')
        self.mock_topurl = self.topurl_patcher.start()

        self.disttag_patcher = patch('pyrpkg.Commands.disttag',
                                     new_callable=PropertyMock,
                                     return_value='fc26')
        self.mock_disttag = self.disttag_patcher.start()

        self.target_patcher = patch('pyrpkg.Commands.target',
                                    new_callable=PropertyMock,
                                    return_value='f26-candidate')
        self.mock_target = self.target_patcher.start()

        self.localarch_patcher = patch('pyrpkg.Commands.localarch',
                                       new_callable=PropertyMock,
                                       return_value='x86_64')
        self.mock_localarch = self.localarch_patcher.start()

        self.genMockConfig_patcher = patch('koji.genMockConfig',
                                           return_value='x86_64 mock config')
        self.mock_genMockConfig = self.genMockConfig_patcher.start()

        self.fake_build_target = {
            'build_tag': 364,
            'build_tag_name': 'f26-build',
            'dest_tag': 359,
            'dest_tag_name': 'f26-updates-candidate',
            'id': 178,
            'name': 'f26-candidate'
        }
        self.fake_repo = {
            'create_event': 27478349,
            'create_ts': 1506694416.4495,
            'creation_time': '2017-09-29 14:13:36.449504',
            'dist': False,
            'id': 790843,
            'state': 1
        }

        self.anon_kojisession_patcher = patch(
            'pyrpkg.Commands.anon_kojisession',
            new_callable=PropertyMock)
        self.mock_anon_kojisession = self.anon_kojisession_patcher.start()
        self.kojisession = self.mock_anon_kojisession.return_value
        self.kojisession.getBuildTarget.return_value = self.fake_build_target
        self.kojisession.getRepo.return_value = self.fake_repo

    def tearDown(self):
        self.genMockConfig_patcher.stop()
        self.localarch_patcher.stop()
        self.target_patcher.stop()
        self.disttag_patcher.stop()
        self.topurl_patcher.stop()
        super(TestMockConfig, self).tearDown()

    @patch('sys.stdout', new_callable=StringIO)
    def test_mock_config(self, stdout):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'mock-config']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mock_config()

        self.mock_genMockConfig.assert_called_once_with(
            'f26-candidate-x86_64',
            'x86_64',
            distribution='fc26',
            tag_name=self.fake_build_target['build_tag_name'],
            repoid=self.fake_repo['id'],
            topurl='http://localhost/hub'
        )

        mock_config = stdout.getvalue().strip()
        self.assertEqual('x86_64 mock config', mock_config)

    def test_fail_if_specified_target_not_exists(self):
        self.kojisession.getBuildTarget.return_value = None

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'mock-config', '--target', 'some-target']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            self.assertRaises(rpkgError, cli.mock_config)

    def test_fail_if_cannot_find_a_valid_repo(self):
        self.kojisession.getRepo.side_effect = Exception

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'mock-config']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            self.assertRaises(rpkgError, cli.mock_config)

    def test_mock_config_from_specified_target(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'mock-config', '--target', 'f25-candidate']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mock_config()

        self.kojisession.getBuildTarget.assert_called_once_with(
            'f25-candidate')
        args, kwargs = self.mock_genMockConfig.call_args
        self.assertEqual('f25-candidate-x86_64', args[0])

    def test_mock_config_from_specified_arch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'mock-config', '--arch', 'i686']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mock_config()

        args, kwargs = self.mock_genMockConfig.call_args
        self.assertEqual('f26-candidate-i686', args[0])
        self.assertEqual('i686', args[1])


class TestContainerBuildSetup(CliTestCase):
    """Test container-build-setup command"""

    def setUp(self):
        super(TestContainerBuildSetup, self).setUp()

        self.osbs_repo_config = os.path.join(self.cloned_repo_path,
                                             '.osbs-repo-config')
        self.write_file(self.osbs_repo_config, '''[autorebuild]
enabled = True
''')

        self.log_patcher = patch.object(pyrpkg, 'log')
        self.mock_log = self.log_patcher.start()

    def tearDown(self):
        if os.path.exists(self.osbs_repo_config):
            os.unlink(self.osbs_repo_config)
        self.mock_log.stop()
        super(TestContainerBuildSetup, self).tearDown()

    def test_get_autorebuild_when_config_file_not_exists(self):
        os.unlink(self.osbs_repo_config)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build-setup', '--get-autorebuild']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.container_build_setup()

        self.mock_log.info.assert_called_once_with('false')

    def test_get_autorebuild_from_config_file(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build-setup', '--get-autorebuild']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.container_build_setup()

        self.mock_log.info.assert_called_once_with('true')

    def test_set_autorebuild_by_creating_config_file(self):
        os.unlink(self.osbs_repo_config)

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build-setup', '--set-autorebuild', 'true']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands.repo',
                       new_callable=PropertyMock) as repo:
                cli.container_build_setup()

                repo.return_value.index.add.assert_called_once_with(
                    [self.osbs_repo_config])

        repo_config = self.read_file(self.osbs_repo_config).strip()
        self.assertEqual('''[autorebuild]
enabled = true''', repo_config)

    def test_set_autorebuild_in_existing_config_file(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'container-build-setup', '--set-autorebuild', 'false']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands.repo',
                       new_callable=PropertyMock) as repo:
                cli.container_build_setup()

                repo.return_value.index.add.assert_called_once_with(
                    [self.osbs_repo_config])

        repo_config = self.read_file(self.osbs_repo_config).strip()
        self.assertEqual('''[autorebuild]
enabled = false''', repo_config)


class TestPatch(CliTestCase):
    """Test patch command"""

    def setUp(self):
        super(TestPatch, self).setUp()

        self.repo_patcher = patch('pyrpkg.Commands.repo',
                                  new_callable=PropertyMock)
        self.mock_repo = self.repo_patcher.start()

        self.Popen_patcher = patch('subprocess.Popen')
        self.mock_Popen = self.Popen_patcher.start()

        self.module_name_patcher = patch('pyrpkg.Commands.module_name',
                                         new_callable=PropertyMock,
                                         return_value='docpkg')
        self.mock_module_name = self.module_name_patcher.start()

        self.ver_patcher = patch('pyrpkg.Commands.ver',
                                 new_callable=PropertyMock,
                                 return_value='2.0')
        self.mock_ver = self.ver_patcher.start()

    def tearDown(self):
        self.ver_patcher.stop()
        self.module_name_patcher.stop()
        self.Popen_patcher.stop()
        self.repo_patcher.stop()
        super(TestPatch, self).tearDown()

    def test_expanded_source_dir_not_found(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'patch', 'fix']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            six.assertRaisesRegex(
                self, rpkgError,
                'Expanded source dir not found!', cli.patch)

    @patch('os.path.isdir', return_value=True)
    def test_generate_diff(self, isdir):
        self.mock_Popen.return_value.communicate.return_value = ['+ diff', '']

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'patch', 'fix']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('__builtin__.open', mock_open()) as m:
                cli.patch()
                m.return_value.write.assert_called_once_with('+ diff')

        patch_file = '{0}-{1}-fix.patch'.format(cli.cmd.module_name,
                                                cli.cmd.ver)
        self.mock_repo.return_value.index.add.assert_called_once_with(
                [patch_file])

    @patch('os.path.isdir', return_value=True)
    def test_generate_empty_patch(self, isdir):
        self.mock_Popen.return_value.communicate.return_value = ['', '']

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'patch', 'fix']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            six.assertRaisesRegex(
                self, rpkgError,
                'gendiff generated an empty patch!', cli.patch)

    @patch('os.rename')
    @patch('os.path.isdir', return_value=True)
    def test_rediff(self, isdir, rename):
        origin_diff = '''diff -up fedpkg-1.29/fedpkg/__init__.py.origin fedpkg-1.29/fedpkg/__init__.py
--- fedpkg-1.29/fedpkg/__init__.py.origin  2017-10-05 01:55:34.268488598 +0000
+++ fedpkg-1.29/fedpkg/__init__.py	2017-10-05 01:55:59.736947877 +0000
@@ -9,12 +9,12 @@
 # option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
 # the full text of the license.

-import pyrpkg'''

        self.mock_Popen.return_value.communicate.return_value = [
            origin_diff, '']

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'patch', '--rediff', 'fix']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()

            patch_file = '{0}-{1}-fix.patch'.format(cli.cmd.module_name,
                                                    cli.cmd.ver)
            copied_patch_file = '{0}~'.format(patch_file)

            with patch('__builtin__.open',
                       mock_open(read_data=origin_diff)) as m:
                with patch('os.path.exists', return_value=True) as exists:
                    cli.patch()

                    exists.assert_called_once_with(
                        os.path.join(cli.cmd.path, patch_file))

                rename.assert_called_once_with(
                    os.path.join(cli.cmd.path, patch_file),
                    os.path.join(cli.cmd.path, copied_patch_file))

                # Following calls assert_has_calls twice in order is a
                # workaround for running this test with old mock 1.0.1, that
                # is the latest version in el6 and el7.
                #
                # When run this test with newer version of mock, e.g. 2.0.0,
                # these 4 calls can be asserted together in order in a single
                # call of m.assert_has_calls.
                m.assert_has_calls([
                    call(os.path.join(cli.cmd.path, patch_file), 'r'),
                    call().readlines(),
                ])
                # Here, skip to check call().readlines().__iter__() that
                # happens only within mock 1.0.1.
                m.assert_has_calls([
                    call(os.path.join(cli.cmd.path, patch_file), 'w'),
                    call().write(origin_diff),
                ])

    def test_fail_if_no_previous_diff_exists(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   'patch', '--rediff', 'fix']
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()

            patch_file = '{0}-{1}-fix.patch'.format(cli.cmd.module_name,
                                                    cli.cmd.ver)
            with patch('os.path.exists', return_value=False) as exists:
                six.assertRaisesRegex(
                    self, rpkgError,
                    'Patch file [^ ]+ not found, unable to rediff', cli.patch)

                exists.assert_called_once_with(
                    os.path.join(cli.cmd.path, patch_file))


@unittest.skipUnless(
    openidc_client,
    'Skip if rpkg is rebuilt for an environment where Kerberos authentication'
    'is used and python-openidc-client is not available.')
class TestModulesCli(CliTestCase):
    """Test module commands"""

    scopes = [
        'openid',
        'https://id.fedoraproject.org/scope/groups',
        'https://mbs.fedoraproject.org/oidc/submit-build'
    ]
    module_build_json = {
        'component_builds': [
            59417, 59418, 59419, 59420, 59421, 59422, 59423, 59428,
            59424, 59425],
        'id': 2150,
        'koji_tag': 'module-14050f52e62d955b',
        'modulemd': '...',
        'name': 'python3-ecosystem',
        'owner': 'torsava',
        'scmurl': ('git://pkgs.fedoraproject.org/modules/python3-ecosystem'
                    '?#34774a9416c799aadda74f2c44ec4dba4d519c04'),
        'state': 4,
        'state_name': 'failed',
        'state_reason': 'Some error',
        'state_trace': [],
        'state_url': '/module-build-service/1/module-builds/1093',
        'stream': 'master',
        'tasks': {
            'rpms': {
                'module-build-macros': {
                    'nvr': 'module-build-macros-None-None',
                    'state': 3,
                    'state_reason': 'Some error',
                    'task_id': 22370514
                },
                'python-cryptography': {
                    'nvr': None,
                    'state': 3,
                    'state_reason': 'Some error',
                    'task_id': None
                },
                'python-dns': {
                    'nvr': None,
                    'state': 3,
                    'state_reason': 'Some error',
                    'task_id': None
                }
            }
        },
        'time_completed': '2017-10-11T09:42:11Z',
        'time_modified': '2017-10-11T09:42:11Z',
        'time_submitted': '2017-10-10T14:55:33Z',
        'version': '20171010145511'
    }

    @patch('sys.stdout', new=StringIO())
    @patch.object(openidc_client.OpenIDCClient, 'send_request')
    def test_module_build(self, mock_oidc_req):
        """
        Test a module build with an SCM URL and branch supplied
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build',
            'git://pkgs.fedoraproject.org/modules/testmodule?#79d87a5a',
            'master'
        ]
        mock_rv = Mock()
        mock_rv.json.return_value = {'id': 1094}
        mock_oidc_req.return_value = mock_rv

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build()

        exp_url = ('https://mbs.fedoraproject.org/module-build-service/1/'
                   'module-builds/')
        exp_json = {
            'scmurl': ('git://pkgs.fedoraproject.org/modules/testmodule?'
                       '#79d87a5a'),
            'branch': 'master'}
        mock_oidc_req.assert_called_once_with(
            exp_url,
            http_method='POST',
            json=exp_json,
            scopes=self.scopes,
            timeout=120)
        output = sys.stdout.getvalue().strip()
        expected_output = ('Submitting the module build...\nThe build #1094 '
                           'was submitted to the MBS')
        self.assertEqual(output, expected_output)

    @patch('sys.stdout', new=StringIO())
    @patch.object(openidc_client.OpenIDCClient, 'send_request')
    def test_module_build_input(self, mock_oidc_req):
        """
        Test a module build with default parameters
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build'
        ]
        mock_rv = Mock()
        mock_rv.json.return_value = {'id': 1094}
        mock_oidc_req.return_value = mock_rv

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build()

        output = sys.stdout.getvalue().strip()
        expected_output = ('Submitting the module build...\nThe build #1094 '
                           'was submitted to the MBS')
        self.assertEqual(output, expected_output)
        # Can't verify the calls since the SCM commit hash always changes
        mock_oidc_req.assert_called_once()

    @patch('sys.stdout', new=StringIO())
    @patch('requests.get')
    @patch.object(openidc_client.OpenIDCClient, 'send_request')
    def test_module_cancel(self, mock_oidc_req, mock_get):
        """
        Test canceling a module build when the build exists
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build-cancel',
            '1125'
        ]
        mock_rv = Mock()
        mock_rv.json.return_value = {'id': 1094}
        mock_get.return_value = mock_rv
        mock_rv_two = Mock()
        mock_rv_two.json.ok = True
        mock_oidc_req.return_value = mock_rv_two

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build_cancel()
        exp_url = ('https://mbs.fedoraproject.org/module-build-service/1/'
                   'module-builds/1125?verbose=true')
        mock_get.assert_called_once_with(exp_url, timeout=60)
        exp_url_two = ('https://mbs.fedoraproject.org/module-build-service/1/'
                       'module-builds/1125')
        mock_oidc_req.assert_called_once_with(
            exp_url_two,
            http_method='PATCH',
            json={'state': 'failed'},
            scopes=self.scopes,
            timeout=60)
        output = sys.stdout.getvalue().strip()
        expected_output = ('Cancelling module build #1125...\nThe module '
                           'build #1125 was cancelled')
        self.assertEqual(output, expected_output)

    @patch('requests.get')
    @patch.object(openidc_client.OpenIDCClient, 'send_request')
    def test_module_cancel_not_found(self, mock_oidc_req, mock_get):
        """
        Test canceling a module build when the build doesn't exist
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build-cancel',
            '1125'
        ]
        mock_rv = Mock()
        mock_rv.ok = False
        mock_rv.json.return_value = {
            'status': 404,
            'message': 'No such module found.',
            'error': 'Not Found'
        }
        mock_get.return_value = mock_rv

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            try:
                cli.module_build_cancel()
                raise RuntimeError('An rpkgError was not raised')
            except rpkgError as error:
                expected_error = ('The following error occurred while getting '
                                  'information on module build #1125:\nNo '
                                  'such module found.')
                self.assertEqual(str(error), expected_error)
        exp_url = ('https://mbs.fedoraproject.org/module-build-service/1/'
                   'module-builds/1125?verbose=true')
        mock_get.assert_called_once_with(exp_url, timeout=60)
        mock_oidc_req.assert_not_called()

    @patch('sys.stdout', new=StringIO())
    @patch('requests.get')
    @patch('pyrpkg.Commands.kojiweburl', new_callable=PropertyMock)
    def test_module_build_info(self, kojiweburl, mock_get):
        """
        Test getting information on a module build
        """
        kojiweburl.return_value = 'https://koji.example.org/koji'

        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build-info',
            '2150'
        ]
        mock_rv = Mock()
        mock_rv.ok = True
        mock_rv.json.return_value = self.module_build_json
        mock_get.return_value = mock_rv

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build_info()
        exp_url = ('https://mbs.fedoraproject.org/module-build-service/1/'
                   'module-builds/2150?verbose=true')
        mock_get.assert_called_once_with(exp_url, timeout=60)
        output = sys.stdout.getvalue().strip()
        expected_output = """
Name:           python3-ecosystem
Stream:         master
Version:        20171010145511
Koji Tag:       module-14050f52e62d955b
Owner:          torsava
State:          failed
State Reason:   Some error
Time Submitted: 2017-10-10T14:55:33Z
Time Completed: 2017-10-11T09:42:11Z
Components:
    Name:       module-build-macros
    NVR:        module-build-macros-None-None
    State:      FAILED
    Koji Task:  https://koji.example.org/koji/taskinfo?taskID=22370514

    Name:       python-dns
    NVR:        None
    State:      FAILED
    Koji Task:  

    Name:       python-cryptography
    NVR:        None
    State:      FAILED
    Koji Task:  
""".strip()  # noqa: W291
        self.assertEqual(expected_output, output)

    @patch('sys.stdout', new=StringIO())
    @patch.object(Commands, 'kojiweburl',
                  'https://koji.fedoraproject.org/koji')
    @patch('requests.get')
    @patch('os.system')
    @patch.object(Commands, 'load_kojisession')
    def test_module_build_watch(self, mock_load_koji, mock_system, mock_get):
        """
        Test watching a module build that is already complete
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build-watch',
            '1500'
        ]
        mock_rv = Mock()
        mock_rv.ok = True
        mock_rv.json.return_value = self.module_build_json
        mock_get.return_value = mock_rv

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build_watch()

        exp_url = ('https://mbs.fedoraproject.org/module-build-service/1/'
                   'module-builds/1500?verbose=true')
        mock_get.assert_called_once_with(exp_url, timeout=60)
        mock_system.assert_called_once_with('clear')
        output = sys.stdout.getvalue().strip()
        expected_output = """
Failed:
   module-build-macros https://koji.fedoraproject.org/koji/taskinfo?taskID=22370514
   python-dns
   python-cryptography

Summary:
   3 components in the "failed" state
torsava's build #2150 of python3-ecosystem-master is in the "failed" state (reason: Some error) (koji tag: "module-14050f52e62d955b")
""".strip()  # noqa: E501
        self.assertEqual(output, expected_output)

    @patch('sys.stdout', new=StringIO())
    @patch('requests.get')
    def test_module_overview(self, mock_get):
        """
        Test the module overview command with 4 modules in the finished state
        and a desired limit of 2
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-overview',
            '--limit',
            '2'
        ]
        # Minimum amount of JSON for the command to succeed
        json_one = {
            'items': [],
            'meta': {
                'next': None
            }
        }
        json_two = {
            'items': [
                {
                    'id': 1100,
                    'koji_tag': 'module-c24f55c24c8fede1',
                    'name': 'testmodule',
                    'owner': 'jkaluza',
                    'state_name': 'ready',
                    'stream': 'master',
                    'version': '20171011093314'
                },
                {
                    'id': 1099,
                    'koji_tag': 'module-72e94da1453758d8',
                    'name': 'testmodule',
                    'owner': 'jkaluza',
                    'state_name': 'ready',
                    'stream': 'master',
                    "version": "20171011092951"
                }
            ],
            'meta': {
                'next': ('http://mbs.fedoraproject.org/module-build-service/1/'
                         'module-builds/?state=5&verbose=true&per_page=2&'
                         'order_desc_by=id&page=2')
            }
        }
        json_three = {
            'items': [
                {
                    'id': 1109,
                    'koji_tag': 'module-057fc15e0e44b333',
                    'name': 'testmodule',
                    'owner': 'mprahl',
                    'state_name': 'failed',
                    'stream': 'master',
                    'version': '20171011173928'
                },
                {
                    'id': 1094,
                    'koji_tag': 'module-640521aea601c6b2',
                    'name': 'testmodule',
                    'owner': 'mprahl',
                    'state_name': 'failed',
                    'stream': 'master',
                    'version': '20171010151103'
                }
            ],
            'meta': {
                'next': ('http://mbs.fedoraproject.org/module-build-service/1'
                         '/module-builds/?state=4&verbose=true&per_page=2&'
                         'order_desc_by=id&page=2')
            }
        }

        mock_rv = Mock()
        mock_rv.ok = True
        mock_rv.json.side_effect = [json_one, json_two, json_three]
        mock_get.return_value = mock_rv
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_overview()

        # Can't confirm the call parameters because multithreading makes the
        # order random
        self.assertEqual(mock_get.call_count, 3)
        output = sys.stdout.getvalue().strip()
        expected_output = """
ID:       1100
Name:     testmodule
Stream:   master
Version:  20171011093314
Koji Tag: module-c24f55c24c8fede1
Owner:    jkaluza
State:    ready

ID:       1109
Name:     testmodule
Stream:   master
Version:  20171011173928
Koji Tag: module-057fc15e0e44b333
Owner:    mprahl
State:    failed
""".strip()
        self.assertEqual(output, expected_output)

    @patch.object(Commands, '_run_command')
    def test_module_build_local(self, mock_run):
        """
        Test submitting a local module build
        """
        cli_cmd = [
            'rpkg',
            '--path',
            self.cloned_repo_path,
            'module-build-local',
            'git://pkgs.fedoraproject.org/modules/testmodule?#79d87a5a',
            'master'
        ]
        mock_proc = Mock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.module_build_local()
        mock_run.assert_called_once_with([
            'mbs-manager',
            'build_module_locally',
            'git://pkgs.fedoraproject.org/modules/testmodule?#79d87a5a',
            'master'])
