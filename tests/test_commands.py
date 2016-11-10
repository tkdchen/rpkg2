# -*- coding: utf-8 -*-

import os
import shutil

import git
from mock import patch

from pyrpkg import rpkgError

from utils import CommandTestCase


def mock_load_rpmdefines(self):
    """Mock Commands.load_rpmdefines by setting empty list to _rpmdefines

    :param Commands self: load_rpmdefines is an instance method of Commands,
    self is the instance whish is calling this method.
    """
    self._rpmdefines = []


def mock_load_spec(fake_spec):
    """Return a mocked load_spec method that sets a fake spec to Commands

    :param str fake_spec: an arbitrary string representing a fake spec
    file. What value is passed to fake_spec depends on the test purpose
    completely.
    """
    def mocked_load_spec(self):
        """Mocked load_spec to set fake spec to an instance of Commands

        :param Commands self: load_spec is an instance method of Commands, self
        is the instance which is calling this method.
        """
        self._spec = fake_spec
    return mocked_load_spec


def mock_load_branch_merge(fake_branch_merge):
    """Return a mocked load_branch_merge method

    The mocked method sets a fake branch name to _branch_merge.

    :param str fake_branch_merge: an arbitrary string representing a fake
    branch name. What value should be passed to fake_branch_merge depends on
    the test purpose completely.
    """
    def mocked_method(self):
        """
        Mocked load_branch_merge to set fake branch name to an instance of
        Commands.

        :param Commands self: load_branch_merge is an instance method of
        Commands, so self is the instance which is calling this method.
        """
        self._branch_merge = fake_branch_merge
    return mocked_method


class LoadNameVerRelTest(CommandTestCase):
    """Test case for Commands.load_nameverrel"""

    def setUp(self):
        super(LoadNameVerRelTest, self).setUp()
        self.cmd = self.make_commands()
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')

    def test_load_from_spec(self):
        """Ensure name, version, release can be loaded from a valid SPEC"""
        self.cmd.load_nameverrel()
        self.assertEqual('docpkg', self.cmd._module_name_spec)
        self.assertEqual('0', self.cmd._epoch)
        self.assertEqual('1.2', self.cmd._ver)
        self.assertEqual('2.el6', self.cmd._rel)

    def test_load_spec_where_path_contains_space(self):
        """Ensure load_nameverrel works with a repo whose path contains space

        This test aims to test the space appearing in path does not break rpm
        command execution.

        For this test purpose, firstly, original repo has to be cloned to a
        new place which has a name containing arbitrary spaces.
        """
        cloned_repo_dir = '/tmp/rpkg test cloned repo'
        if os.path.exists(cloned_repo_dir):
            shutil.rmtree(cloned_repo_dir)
        cloned_repo = self.cmd.repo.clone(cloned_repo_dir)

        # Switching to branch eng-rhel-6 explicitly is required by running this
        # on RHEL6/7 because an old version of git is available in the
        # repo.
        # The failure reason is, old version of git makes the master as the
        # active branch in cloned repository, whatever the current active
        # branch is in the remote repository.
        # As of fixing this, I ran test on Fedora 23 with git 2.5.5, and test
        # fails on RHEL7 with git 1.8.3.1
        cloned_repo.git.checkout('eng-rhel-6')

        cmd = self.make_commands(path=cloned_repo_dir)

        cmd.load_nameverrel()
        self.assertEqual('docpkg', cmd._module_name_spec)
        self.assertEqual('0', cmd._epoch)
        self.assertEqual('1.2', cmd._ver)
        self.assertEqual('2.el6', cmd._rel)

    @patch('pyrpkg.Commands.load_rpmdefines', new=mock_load_rpmdefines)
    @patch('pyrpkg.Commands.load_spec',
           new=mock_load_spec('unknown-rpm-option a-nonexistent-package.spec'))
    def test_load_when_rpm_fails(self):
        """Ensure rpkgError is raised when rpm command fails

        Commands.load_spec is mocked to help generate an incorrect rpm command
        line to cause the error that this test expects.

        Test test does not care about what rpm defines are retrieved from
        repository, so setting an empty list to Commands._rpmdefines is safe
        and enough.
        """
        self.assertRaises(rpkgError, self.cmd.load_nameverrel)


class LoadBranchMergeTest(CommandTestCase):
    """Test case for testing Commands.load_branch_merge"""

    def setUp(self):
        super(LoadBranchMergeTest, self).setUp()

        self.cmd = self.make_commands()

    def test_load_branch_merge_from_eng_rhel_6(self):
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')
        self.cmd.load_branch_merge()
        self.assertEqual(self.cmd._branch_merge, 'eng-rhel-6')

    def test_load_branch_merge_from_eng_rhel_6_5(self):
        """
        Ensure load_branch_merge can work well against a more special branch
        eng-rhel-6.5
        """
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6.5')
        self.cmd.load_branch_merge()
        self.assertEqual(self.cmd._branch_merge, 'eng-rhel-6.5')

    def test_load_branch_merge_from_not_remote_merge_branch(self):
        """Ensure load_branch_merge fails against local-branch

        A new local branch named local-branch is created for this test, loading
        branch merge from this local branch should fail because there is no
        configuration item branch.local-branch.merge.
        """
        self.create_branch(self.cmd.repo, 'local-branch')
        self.checkout_branch(self.cmd.repo, 'local-branch')
        try:
            self.cmd.load_branch_merge()
        except rpkgError as e:
            self.assertEqual('Unable to find remote branch.  Use --dist', str(e))
        else:
            self.fail("It's expected to raise rpkgError, but not.")

    def test_load_branch_merge_using_dist_option(self):
        """Ensure load_branch_merge uses dist specified via --dist

        Switch to eng-rhel-6 branch, that is valid for load_branch_merge and to
        see if load_branch_merge still uses dist rather than such a valid
        branch.
        """
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')

        cmd = self.make_commands(dist='branch_merge')
        cmd.load_branch_merge()
        self.assertEqual('branch_merge', cmd._branch_merge)


class LoadRPMDefinesTest(CommandTestCase):
    """Test case for Commands.load_rpmdefines"""

    def setUp(self):
        super(LoadRPMDefinesTest, self).setUp()
        self.cmd = self.make_commands()

    def assert_loaded_rpmdefines(self, branch_name, expected_defines):
        self.checkout_branch(self.cmd.repo, branch_name)

        self.cmd.load_rpmdefines()
        self.assertTrue(self.cmd._rpmdefines)

        # Convert defines into dict for assertion conveniently. The dict
        # contains mapping from variable name to value. For example,
        # {
        #     '_sourcedir': '/path/to/src-dir',
        #     '_specdir': '/path/to/spec',
        #     '_builddir': '/path/to/build-dir',
        #     '_srcrpmdir': '/path/to/srcrpm-dir',
        #     'dist': 'el7'
        # }
        defines = dict([item.split(' ') for item in (
            define.replace("'", '').split(' ', 1)[1] for
            define in self.cmd._rpmdefines)])

        for var, val in expected_defines.items():
            self.assertTrue(var in defines)
            self.assertEqual(val, defines[var])

    def test_load_rpmdefines_from_eng_rhel_6(self):
        """Run load_rpmdefines against branch eng-rhel-6"""
        expected_rpmdefines = {
            '_sourcedir': self.cloned_repo_path,
            '_specdir': self.cloned_repo_path,
            '_builddir': self.cloned_repo_path,
            '_srcrpmdir': self.cloned_repo_path,
            '_rpmdir': self.cloned_repo_path,
            'dist': u'.el6',
            'rhel': u'6',
            'el6': u'1',
            }
        self.assert_loaded_rpmdefines('eng-rhel-6', expected_rpmdefines)

    def test_load_rpmdefines_from_eng_rhel_6_5(self):
        """Run load_rpmdefines against branch eng-rhel-6.5

        Working on a different branch name is the only difference from test
        method test_load_rpmdefines_from_eng_rhel_6.
        """
        expected_rpmdefines = {
            '_sourcedir': self.cloned_repo_path,
            '_specdir': self.cloned_repo_path,
            '_builddir': self.cloned_repo_path,
            '_srcrpmdir': self.cloned_repo_path,
            '_rpmdir': self.cloned_repo_path,
            'dist': u'.el6_5',
            'rhel': u'6',
            'el6_5': u'1',
            }
        self.assert_loaded_rpmdefines('eng-rhel-6.5', expected_rpmdefines)

    @patch('pyrpkg.Commands.load_branch_merge',
           new=mock_load_branch_merge('invalid-branch-name'))
    def test_load_rpmdefines_against_invalid_branch(self):
        """Ensure load_rpmdefines if active branch name is invalid

        This test requires an invalid branch name even if
        Commands.load_branch_merge is able to get it from current active
        branch. So, I only care about the value returned from method
        load_branch_merge, and just mock it and let it return the value this
        test requires.
        """
        self.assertRaises(rpkgError, self.cmd.load_rpmdefines)


class CheckRepoWithOrWithoutDistOptionCase(CommandTestCase):
    """Check whether there are unpushed changes with or without specified dist

    Ensure check_repo works in a correct way to check if there are unpushed
    changes, and this should not be affected by specified dist or not.
    Bug 1169663 describes a concrete use case and this test case is designed
    as what that bug describs.
    """

    def setUp(self):
        super(CheckRepoWithOrWithoutDistOptionCase, self).setUp()

        private_branch = 'private-dev-branch'
        origin_repo = git.Repo(self.repo_path)
        origin_repo.git.checkout('master')
        origin_repo.git.branch(private_branch)
        self.make_a_dummy_commit(origin_repo)

        cloned_repo = git.Repo(self.cloned_repo_path)
        cloned_repo.git.pull()
        cloned_repo.git.checkout('-b', private_branch, 'origin/%s' % private_branch)
        for i in xrange(3):
            self.make_a_dummy_commit(cloned_repo)
        cloned_repo.git.push()

    def test_check_repo_with_specificed_dist(self):
        cmd = self.make_commands(self.cloned_repo_path, dist='eng-rhel-6')
        try:
            cmd.check_repo()
        except rpkgError as e:
            if 'There are unpushed changes in your repo' in e:
                self.fail('There are unpushed changes in your repo. This '
                          'should not happen. Something must be going wrong.')

            self.fail('Should not fail. Something must be going wrong.')

    def test_check_repo_without_specificed_dist(self):
        cmd = self.make_commands(self.cloned_repo_path)
        try:
            cmd.check_repo()
        except rpkgError as e:
            if 'There are unpushed changes in your repo' in e:
                self.fail('There are unpushed changes in your repo. This '
                          'should not happen. Something must be going wrong.')

            self.fail('Should not fail. Something must be going wrong.')


class ClogTest(CommandTestCase):

    def setUp(self):
        super(ClogTest, self).setUp()

        with open(os.path.join(self.repo_path, self.spec_file), 'w') as specfile:
            specfile.write('''
Summary: package demo
Name: pkgtool
Version: 0.1
Release: 1%{?dist}
License: GPL
%description
package demo for testing
%changelog
* Mon Nov 07 2016 cqi@redhat.com
- add %%changelog section
- add new spec
$what_is_this

* Mon Nov 06 2016 cqi@redhat.com
- initial
''')

        self.cmd = self.make_commands(self.repo_path)

    def test_clog(self):
        self.cmd.clog()

        with open(os.path.join(self.repo_path, 'clog'), 'r') as clog:
            clog_lines = clog.readlines()

        expected_lines = ['add %changelog section\n',
                          'add new spec\n']
        self.assertEqual(expected_lines, clog_lines)

    def test_raw_clog(self):
        self.cmd.clog(raw=True)

        with open(os.path.join(self.repo_path, 'clog'), 'r') as clog:
            clog_lines = clog.readlines()

        expected_lines = ['- add %changelog section\n',
                          '- add new spec\n']
        self.assertEqual(expected_lines, clog_lines)
