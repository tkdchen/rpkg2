# -*- coding: utf-8 -*-

import gzip
import hashlib
import logging
import os
import rpmfluff
import shutil
import six
import sys
import tempfile

from six.moves import configparser
from six.moves import StringIO

import git
import pyrpkg.cli

from mock import patch
from utils import CommandTestCase
from pyrpkg import rpkgError


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
            self.run_cmd(cmd, cwd=repo_path)


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
        self.run_cmd(['git', 'tag', '-m', 'New release v0.1', 'v0.1'], cwd=self.cloned_repo_path)
        self.make_changes(repo=self.cloned_repo_path, commit=True, content='New change')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'new']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.new()

            output = sys.stdout.getvalue()
            self.assertTrue('+New change' in output)


class TestNewPrintUnicode(CliTestCase):
    """Test new diff contains unicode characters

    Fix issue 205: https://pagure.io/rpkg/issue/205
    """

    def setUp(self):
        super(TestNewPrintUnicode, self).setUp()
        self.run_cmd(['git', 'tag', '-m', 'New release 0.1', '0.1'], cwd=self.cloned_repo_path)
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
            self.run_cmd(cmd, cwd=self.chaos_repo)

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

    @patch('pyrpkg.Commands._run_command')
    def test_mockbuild(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-6', 'mockbuild',
                   '--root', '/etc/mock/some-root']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mockbuild()

        expected_cmd = ['mock', '-r', '/etc/mock/some-root',
                        '--resultdir', cli.cmd.mock_results_dir, '--rebuild',
                        cli.cmd.srpmname]
        _run_command.assert_called_with(expected_cmd)

    @patch('pyrpkg.Commands._run_command')
    def test_with_without(self, _run_command):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path,
                   '--release', 'rhel-6', 'mockbuild',
                   '--root', '/etc/mock/some-root',
                   '--with', 'a', '--without', 'b', '--with', 'c',
                   '--without', 'd']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.mockbuild()

        expected_cmd = ['mock', '--with', 'a', '--with', 'c',
                        '--without', 'b', '--without', 'd',
                        '-r', '/etc/mock/some-root',
                        '--resultdir', cli.cmd.mock_results_dir, '--rebuild',
                        cli.cmd.srpmname]
        _run_command.assert_called_with(expected_cmd)
