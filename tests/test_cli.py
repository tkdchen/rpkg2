# -*- coding: utf-8 -*-

import os

from six.moves import configparser

import git
import pyrpkg.cli

from mock import patch
from utils import CommandTestCase
from utils import run
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
* Mon Nov 07 2016 cqi@redhat.com
- first release 0.1
- add new spec
'''


class CliTestCase(CommandTestCase):

    def new_cli(self):
        config = configparser.SafeConfigParser()
        config.read(config_file)

        client = pyrpkg.cli.cliClient(config, name='rpkg')
        client.do_imports()
        client.parse_cmdline()

        return client

    def make_changes(self):
        cmds = (['touch', 'new-file.txt'],
                ['git', 'add', 'new-file.txt'])
        map(lambda cmd: run(cmd, cwd=self.cloned_repo_path), cmds)


class TestClog(CliTestCase):

    def setUp(self):
        super(TestClog, self).setUp()

        self.make_changes()

    def cli_clog(self):
        """Run clog command"""
        cli = self.new_cli()
        cli.clog()

    def test_clog(self):
        with patch('sys.argv', ['rpkg', '--path', self.cloned_repo_path, 'clog']):
            self.cli_clog()

            clog_file = os.path.join(self.cloned_repo_path, 'clog')
            self.assertTrue(os.path.exists(clog_file))
            with open(clog_file, 'r') as f:
                clog = f.read().strip()
            self.assertEqual('Initial version', clog)

    def test_raw_clog(self):
        with patch('sys.argv', ['rpkg', '--path', self.cloned_repo_path, 'clog', '--raw']):
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
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    'commit', '-m', 'new release']):
            self.cli_commit()

            commit_msg = self.get_last_commit_message()
            self.assertEqual('new release', commit_msg)

    def test_with_summary_and_changelog(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    'commit', '-m', 'new release', '--with-changelog']):
            self.cli_commit()

            commit_msg = self.get_last_commit_message()
            expected_commit_msg = '''new release

- Initial version'''
            self.assertEqual(expected_commit_msg, commit_msg)
            self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))
            self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'commit-message')))

    def test_with_clog(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path, 'commit', '--clog']):
            self.cli_commit()

            commit_msg = self.get_last_commit_message()
            expected_commit_msg = 'Initial version'
            self.assertEqual(expected_commit_msg, commit_msg)
            self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))

    def test_with_raw_clog(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    'commit', '--clog', '--raw']):
            self.cli_commit()

            commit_msg = self.get_last_commit_message()
            expected_commit_msg = '- Initial version'
            self.assertEqual(expected_commit_msg, commit_msg)
            self.assertFalse(os.path.exists(os.path.join(self.cloned_repo_path, 'clog')))

    def test_cannot_use_with_changelog_without_a_summary(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    'commit', '--with-changelog']):
            self.assertRaises(rpkgError, self.cli_commit)

    def test_push_after_commit(self):
        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'eng-rhel-6')

        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    'commit', '-m', 'new release', '--with-changelog', '--push']):
            self.cli_commit()

            diff_commits = repo.git.rev_list('origin/master...master')
            self.assertEqual('', diff_commits)


class TestSrpm(CliTestCase):

    def test_srpm(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'srpm']):
            cli = self.new_cli()
            cli.srpm()

            self.assertTrue(os.path.exists(os.path.join(self.cloned_repo_path,
                                                        'docpkg-1.2-2.el6.src.rpm')))


class TestCompile(CliTestCase):

    def test_compile(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'compile']):
            cli = self.new_cli()
            cli.compile()


class TestPrep(CliTestCase):

    def test_compile(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'prep']):
            cli = self.new_cli()
            cli.prep()


class TestInstall(CliTestCase):

    def test_compile(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'install']):
            cli = self.new_cli()
            cli.install()


class TestLocal(CliTestCase):

    def test_local(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'local']):
            cli = self.new_cli()
            cli.local()

            self.assertFilesExists((
                'docpkg-1.2-2.el6.src.rpm',
                'x86_64/docpkg-1.2-2.el6.x86_64.rpm',
            ))

    def test_local_with_arch(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'local', '--arch', 'i686']):
            cli = self.new_cli()
            cli.local()

            self.assertFilesExists((
                'docpkg-1.2-2.el6.src.rpm',
                'i686/docpkg-1.2-2.el6.i686.rpm',
            ))

    def test_local_with_builddir(self):
        custom_builddir = os.path.join(self.cloned_repo_path, 'this-builddir')

        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'local', '--builddir', custom_builddir]):
            cli = self.new_cli()
            cli.local()

            self.assertFilesExists(('this-builddir/README.rst',))


class TestVerifyFiles(CliTestCase):

    def test_verify_files(self):
        with patch('sys.argv', new=['rpkg', '--path', self.cloned_repo_path,
                                    '--release', 'rhel-6', 'verify-files']):
            cli = self.new_cli()
            cli.verify_files()
