# -*- coding: utf-8 -*-

import logging
import os
import sys

from os.path import exists
from os.path import join
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

    def new_cli(self):
        config = configparser.SafeConfigParser()
        config.read(config_file)

        client = pyrpkg.cli.cliClient(config, name='rpkg')
        client.setupLogging(pyrpkg.log)
        pyrpkg.log.setLevel(logging.CRITICAL)
        client.do_imports()
        client.parse_cmdline()

        return client

    def touch(self, filename, content=None):
        """Touch a file with optional content"""

        _content = content if content else ''
        with open(filename, 'w') as f:
            f.write(_content)

    def make_changes(self, repo=None, untracked=None, commit=None, filename=None, content=''):
        repo_path = repo or self.cloned_repo_path
        _filename = filename or 'new-file.txt'

        self.write_file(os.path.join(repo_path, _filename), content)

        cmds = []
        if not untracked:
            cmds.append(['git', 'add', _filename])
        if not untracked and commit:
            cmds.append(['git', 'commit', '-m', 'Add new file {0}'.format(_filename)])

        if cmds:
            map(lambda cmd: self.run_cmd(cmd, cwd=repo_path), cmds)


class TestClog(CliTestCase):

    def setUp(self):
        super(TestClog, self).setUp()

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
        with open(clog_file, 'r') as f:
            clog = f.read().strip()
        self.assertEqual('Initial version', clog)

    def test_raw_clog(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'clog', '--raw']

        with patch('sys.argv', new=cli_cmd):
            self.cli_clog()

        clog_file = os.path.join(self.cloned_repo_path, 'clog')
        self.assertTrue(os.path.exists(clog_file))
        with open(clog_file, 'r') as f:
            clog = f.read().strip()
        self.assertEqual('- Initial version', clog)


class TestCommit(CliTestCase):

    def setUp(self):
        super(TestCommit, self).setUp()
        self.make_changes()

    def get_last_commit_message(self):
        repo = git.Repo(self.cloned_repo_path)
        return repo.iter_commits().next().message.strip()

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

        origin_last_commit = str(git.Repo(self.repo_path).iter_commits().next())
        cloned_last_commit = str(cli.cmd.repo.iter_commits().next())
        self.assertEqual(origin_last_commit, cloned_last_commit)

    def test_pull_rebase(self):
        self.make_changes(repo=self.repo_path, commit=True)
        self.make_changes(repo=self.cloned_repo_path, commit=True,
                          filename='README.rst', content='Hello teseting.')

        origin_last_commit = str(git.Repo(self.repo_path).iter_commits().next())

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'pull', '--rebase']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.pull()

        commits = cli.cmd.repo.iter_commits()
        commits.next()
        fetched_commit = str(commits.next())
        self.assertEqual(origin_last_commit, fetched_commit)
        self.assertEqual('', cli.cmd.repo.git.log('--merges'))


class TestSrpm(CliTestCase):

    def test_srpm(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'srpm']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.srpm()

        self.assertTrue(os.path.exists(os.path.join(self.cloned_repo_path,
                                                    'docpkg-1.2-2.el6.src.rpm')))


class TestCompile(CliTestCase):

    def compile(self, cli_cmd):
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.compile()

    @patch('sys.stdout', new=StringIO())
    def test_compile(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'compile']
        self.compile(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('Executing(%prep):' in stdout)
        self.assertTrue('Executing(%build):' in stdout)

    @patch('sys.stdout', new=StringIO())
    def test_compile_short_circuit(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6',
                   'compile', '--short-circuit']
        self.compile(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('Executing(%prep):' not in stdout)
        self.assertTrue('Executing(%build):' in stdout)

    @patch('sys.stdout', new=StringIO())
    def test_compile_quiet(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q', 'compile']
        self.compile(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertEqual('', stdout)

    @patch('sys.stdout', new=StringIO())
    def test_compile_arch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q',
                   'compile', '--arch', 'i686']
        self.compile(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('''Building target platforms: i686
Building for target i686''', stdout)


class TestPrep(CliTestCase):

    def prep(self, cli_cmd):
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.prep()

    @patch('sys.stdout', new=StringIO())
    def test_prep(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'prep']
        self.prep(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('Executing(%prep):' in stdout)

    @patch('sys.stdout', new=StringIO())
    def test_prep_arch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q',
                   'compile', '--arch', 'i686']
        self.prep(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('''Building target platforms: i686
Building for target i686''', stdout)


class TestInstall(CliTestCase):

    def install(self, cli_cmd):
        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.install()

    @patch('sys.stdout', new=StringIO())
    def test_install(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'install']
        self.install(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('Executing(%prep):' in stdout)
        self.assertTrue('Executing(%build):' in stdout)
        self.assertTrue('Executing(%install):' in stdout)
        self.assertTrue('Executing(%check):' in stdout)
        self.assertTrue('Executing(%doc):' in stdout)

    @patch('sys.stdout', new=StringIO())
    def test_install_nocheck(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6',
                   'install', '--nocheck']
        self.install(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('Executing(%check):' not in stdout)

    @patch('sys.stdout', new=StringIO())
    def test_install_quiet(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', '-q', 'install']
        self.install(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertEqual('', stdout)

    @patch('sys.stdout', new=StringIO())
    def test_install_arch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release',
                   'rhel-6', 'install', '--arch', 'i686']
        self.install(cli_cmd)
        stdout = sys.stdout.getvalue()

        self.assertTrue('''Building target platforms: i686
Building for target i686''', stdout)


class TestLocal(CliTestCase):

    def translate_arch(self, arch):
        """Translate local arch to arch the rpmbuild uses

        This is another workaround for running tests in Copr, where when
        building RPM in a i386 target, local arch is i386, but arch in RPM is
        "translated" to i686.
        """
        translation = {
            'i386': 'i686',
            }
        return translation.get(arch, arch)

    def test_local(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'local']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.local()

        self.assertTrue(exists(join(self.cloned_repo_path, 'docpkg-1.2-2.el6.src.rpm')))
        # This covers some special cases, e.g. building in copr, that is
        # RPMs are not put in arch subdirectory even if %{_build_name_fmt}
        # is %{ARCH}/%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}.rpm
        arch = self.translate_arch(cli.cmd.localarch)
        self.assertTrue(
            exists(join(self.cloned_repo_path, 'docpkg-1.2-2.el6.{0}.rpm'.format(arch))) or
            exists(join(self.cloned_repo_path, '{0}/docpkg-1.2-2.el6.{0}.rpm'.format(arch))))

    def test_local_with_arch(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6',
                   'local', '--arch', 'i686']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.local()

        self.assertTrue(exists(join(self.cloned_repo_path, 'docpkg-1.2-2.el6.src.rpm')))
        self.assertTrue(
            exists(join(self.cloned_repo_path, 'docpkg-1.2-2.el6.i686.rpm')) or
            exists(join(self.cloned_repo_path, 'i686/docpkg-1.2-2.el6.i686.rpm')))

    def test_local_with_builddir(self):
        custom_builddir = os.path.join(self.cloned_repo_path, 'this-builddir')

        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6',
                   'local', '--builddir', custom_builddir]

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.local()

        self.assertFilesExists(('this-builddir/README.rst',))


class TestVerifyFiles(CliTestCase):

    def test_verify_files(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, '--release', 'rhel-6', 'verify-files']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.verify_files()


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
        self.make_changes()

        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'eng-rhel-6')

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

        self.assertEqual('eng-rhel-6', repo.active_branch.name)

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
        map(self.touch, self.patches)
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

    def test_diff(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'diff']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.diff()

    def test_diff_cached(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'diff', '--cached']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.diff()


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

        self.assertFilesExists(['new-file.txt'])

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
        self.assertFilesExists(['docpkg.spec', '.git'])


class TestLint(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_lint(self):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')

        cli_cmd = ['rpkg', '--module-name', 'docpkg', '--path', self.cloned_repo_path, 'lint']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.lint()

        summary = sys.stdout.getvalue().strip().split('\n')[-1]
        self.assertEqual(
            '0 packages and 1 specfiles checked; 0 errors, 0 warnings.', summary)

    @patch('sys.stdout', new=StringIO())
    def test_lint_warning_detected(self):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')

        spec_file = os.path.join(self.cloned_repo_path, self.spec_file)
        spec_content = self.read_file(spec_file).replace('%install', '')
        self.write_file(spec_file, spec_content)

        cli_cmd = ['rpkg', '--module-name', 'docpkg', '--path', self.cloned_repo_path, 'lint']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.lint()

        output = sys.stdout.getvalue()
        self.assertTrue('W: no-%install-section' in output)

    @patch('sys.stdout', new=StringIO())
    def test_lint_warining_with_info(self):
        self.checkout_branch(git.Repo(self.cloned_repo_path), 'eng-rhel-7')

        spec_file = os.path.join(self.cloned_repo_path, self.spec_file)
        spec_content = self.read_file(spec_file).replace('%install', '')
        self.write_file(spec_file, spec_content)

        cli_cmd = ['rpkg', '--module-name', 'docpkg', '--path', self.cloned_repo_path,
                   'lint', '--info']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            with patch('pyrpkg.Commands._run_command', new=self.redirect_cmd_output):
                cli.lint()

        warning_explanation = 'The spec file does not contain an %install section.'
        output = sys.stdout.getvalue()
        self.assertTrue('W: no-%install-section' in output)
        self.assertTrue(warning_explanation in output)


class TestGitUrl(CliTestCase):

    @patch('sys.stdout', new=StringIO())
    def test_giturl(self):
        cli_cmd = ['rpkg', '--path', self.cloned_repo_path, 'giturl']

        with patch('sys.argv', new=cli_cmd):
            cli = self.new_cli()
            cli.giturl()

        last_commit = str(cli.cmd.repo.iter_commits().next())
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
