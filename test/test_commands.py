# -*- coding: utf-8 -*-

import os
import shutil
import tempfile
import unittest
import subprocess

import git
from mock import patch

from pyrpkg import Commands
from pyrpkg import rpkgError


# Path to repositories that is for running tests
# For running tests, we need two repositories at least that should be created
# firstly. repo_path points to the repository representing a remote repository
# and containing a SPEC file for now.
# Within this repository, by default, three branches are created by default for
# convenience, that are eng-rhel-6, eng-rhel-6.5, and eng-rhel-7.
repo_path = None

# This is the path pointing to the repository cloned from remote repository at
# repo_path. Cloning this repository aims to provide a useful git repository
# for tests, that contains available metadata related to origin remote
# repository.
# By default, local branches eng-rhel-6, eng-rhel-6.5, and eng-rhel-7 tracking
# remote branches individually are created.
cloned_repo_path = None

# Following global variables are used to construct Commands for tests in this
# module. Only for testing purpose, and they are not going to be used for
# hitting real services.
lookaside = 'http://dist-git-qa.server/repo/pkgs'
lookaside_cgi = 'http://dist-git-qa.server/lookaside/upload.cgi'
gitbaseurl = 'ssh://%(user)s@dist-git-qa.server/rpms/%(module)s'
anongiturl = 'git://dist-git-qa.server/rpms/%(module)s'
lookasidehash = 'md5'
branchre = 'rhel'
kojiconfig = '/etc/koji.conf.d/brewstage.conf'
build_client = 'brew-stage'

spec_file = '''
Summary: Dummy summary
Name: docpkg
Version: 1.2
Release: 2
License: GPL
Group: Applications/Productivity
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
%description
This is a dummy description.
%prep
%build
%clean
rm -rf $$RPM_BUILD_ROOT
%install
rm -rf $RPM_BUILD_ROOT
mkdir $RPM_BUILD_ROOT
%files
%changelog
* Thu Apr 21 2006 Chenxiong Qi <cqi@redhat.com> - 1.2-2
- Initial version
'''


def run(cmd, **kwargs):
    returncode = subprocess.call(cmd, **kwargs)
    if returncode != 0:
        raise RuntimeError('Command fails. Command: %s. Return code %d' % (
            ' '.join(cmd), returncode))


def setup_module():
    # create a base repo
    global repo_path
    repo_path = tempfile.mkdtemp(prefix='rpkg-commands-tests-')

    # Add spec file to this repo and commit
    spec_file_path = os.path.join(repo_path, 'package.spec')
    with open(spec_file_path, 'w') as f:
        f.write(spec_file)

    git_cmds = [
        ['git', 'init'],
        ['git', 'add', spec_file_path],
        ['git', 'commit', '-m', 'initial commit'],
        ['git', 'branch', 'eng-rhel-6'],
        ['git', 'branch', 'eng-rhel-6.5'],
        ['git', 'branch', 'eng-rhel-7'],
        ]
    for cmd in git_cmds:
        run(cmd, cwd=repo_path)

    # Clone the repo
    global cloned_repo_path
    cloned_repo_path = tempfile.mkdtemp(prefix='rpkg-commands-tests-cloned-')
    git_cmds = [
        ['git', 'clone', repo_path, cloned_repo_path],
        ['git', 'branch', '--track', 'eng-rhel-6', 'origin/eng-rhel-6'],
        ['git', 'branch', '--track', 'eng-rhel-6.5', 'origin/eng-rhel-6.5'],
        ['git', 'branch', '--track', 'eng-rhel-7', 'origin/eng-rhel-7'],
        ]
    for cmd in git_cmds:
        run(cmd, cwd=cloned_repo_path)


def teardown_module():
    shutil.rmtree(repo_path)
    shutil.rmtree(cloned_repo_path)


def make_commands(path=None, user=None, dist=None, target=None, quiet=None):
    """Helper method for creating Commands object for test cases

    This is where you should extend to add more features to support additional
    requirements from other Commands specific test cases.

    Some tests need customize one of user, dist, target, and quiet options when
    creating an instance of Commands. Keyword arguments user, dist, target, and
    quiet here is for this purpose.

    :param str path: path to repository where this Commands will work on top of
    :param str user: user passed to --user option
    :param str dist: dist passed to --dist option
    :param str target: target passed to --target option
    :param str quiet: quiet passed to --quiet option
    """
    _repo_path = path if path else cloned_repo_path
    return Commands(_repo_path,
                    lookaside, lookasidehash, lookaside_cgi,
                    gitbaseurl, anongiturl,
                    branchre,
                    kojiconfig, build_client,
                    user=user, dist=dist, target=target, quiet=quiet)


class GitMixin(object):

    def checkout_branch(self, repo, branch_name):
        """Checkout to a local branch

        :param git.Repo repo: `git.Repo` instance represents a git repository
        that current code works on top of.
        :param str branch_name: name of local branch to checkout
        """
        heads = [head for head in repo.heads if head.name == branch_name]
        assert len(heads) > 0, \
            'Repo must have a local branch named {} that ' \
            'is for running tests. But now, it does not exist. Please check ' \
            'if the repo is correct.'.format(branch_name)

        heads[0].checkout()

    def create_branch(self, repo, branch_name):
        repo.git.branch(branch_name)


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


class LoadNameVerRelTest(GitMixin, unittest.TestCase):
    """Test case for Commands.load_nameverrel"""

    def setUp(self):
        self.cmd = make_commands()
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')

    def test_load_from_spec(self):
        """Ensure name, version, release can be loaded from a valid SPEC"""
        self.cmd.load_nameverrel()
        self.assertEqual('docpkg', self.cmd._module_name_spec)
        self.assertEqual('0', self.cmd._epoch)
        self.assertEqual('1.2', self.cmd._ver)
        self.assertEqual('2', self.cmd._rel)

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

        cmd = make_commands(path=cloned_repo_dir)

        cmd.load_nameverrel()
        self.assertEqual('docpkg', cmd._module_name_spec)
        self.assertEqual('0', cmd._epoch)
        self.assertEqual('1.2', cmd._ver)
        self.assertEqual('2', cmd._rel)

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


class LoadBranchMergeTest(GitMixin, unittest.TestCase):
    """Test case for testing Commands.load_branch_merge"""

    def setUp(self):
        self.cmd = make_commands()
        self.origin_active_head = self.cmd.repo.active_branch

    def tearDown(self):
        self.origin_active_head.checkout()

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
            self.assertEqual('Unable to find remote branch.  Use --dist',
                              str(e))
        else:
            self.fail("It's expected to raise rpkgError, but not.")

    def test_load_branch_merge_using_dist_option(self):
        """Ensure load_branch_merge uses dist specified via --dist

        Switch to eng-rhel-6 branch, that is valid for load_branch_merge and to
        see if load_branch_merge still uses dist rather than such a valid
        branch.
        """
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')

        cmd = make_commands(dist='branch_merge')
        cmd.load_branch_merge()
        self.assertEqual('branch_merge', cmd._branch_merge)


class LoadRPMDefinesTest(GitMixin, unittest.TestCase):
    """Test case for Commands.load_rpmdefines"""

    def setUp(self):
        self.cmd = make_commands()

        # Branch will be checked out to a different one according to each
        # test's purpose. So, save current active branch, and checkout back
        # when each test finishes.
        self.origin_active_head = self.cmd.repo.active_branch

    def tearDown(self):
        self.origin_active_head.checkout()

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

        for var, val in expected_defines.iteritems():
            self.assertTrue(var in defines)
            self.assertEqual(val, defines[var])

    def test_load_rpmdefines_from_eng_rhel_6(self):
        """Run load_rpmdefines against branch eng-rhel-6"""
        expected_rpmdefines = {
            '_sourcedir': cloned_repo_path,
            '_specdir': cloned_repo_path,
            '_builddir': cloned_repo_path,
            '_srcrpmdir': cloned_repo_path,
            '_rpmdir': cloned_repo_path,
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
            '_sourcedir': cloned_repo_path,
            '_specdir': cloned_repo_path,
            '_builddir': cloned_repo_path,
            '_srcrpmdir': cloned_repo_path,
            '_rpmdir': cloned_repo_path,
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
