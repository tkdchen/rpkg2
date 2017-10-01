# -*- coding: utf-8 -*-

import os
import shutil
import six
import subprocess
import tempfile

import git
import rpm
from mock import patch
from mock import Mock
from mock import PropertyMock

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
            self.assertEqual('Unable to find remote branch.  Use --release', str(e))
        else:
            self.fail("It's expected to raise rpkgError, but not.")

    def test_load_branch_merge_using_release_option(self):
        """Ensure load_branch_merge uses release specified via --release

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
        for i in range(3):
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

        with open(os.path.join(self.cloned_repo_path, self.spec_file), 'w') as specfile:
            specfile.write('''
Summary: package demo
Name: pkgtool
Version: 0.1
Release: 1%{?dist}
License: GPL
%description
package demo for testing
%changelog
* Mon Nov 07 2016 tester@example.com
- add %%changelog section
- add new spec
$what_is_this

* Mon Nov 06 2016 tester@example.com
- initial
''')

        self.clog_file = os.path.join(self.cloned_repo_path, 'clog')
        self.cmd = self.make_commands()
        self.checkout_branch(self.cmd.repo, 'eng-rhel-6')

    def test_clog(self):
        self.cmd.clog()

        with open(self.clog_file, 'r') as clog:
            clog_lines = clog.readlines()

        expected_lines = ['add %changelog section\n',
                          'add new spec\n']
        self.assertEqual(expected_lines, clog_lines)

    def test_raw_clog(self):
        self.cmd.clog(raw=True)

        with open(self.clog_file, 'r') as clog:
            clog_lines = clog.readlines()

        expected_lines = ['- add %changelog section\n',
                          '- add new spec\n']
        self.assertEqual(expected_lines, clog_lines)


class TestProperties(CommandTestCase):

    def setUp(self):
        super(TestProperties, self).setUp()
        self.invalid_repo = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.invalid_repo)
        super(TestProperties, self).tearDown()

    def test_target(self):
        cmd = self.make_commands()
        self.checkout_branch(cmd.repo, 'eng-rhel-6')
        self.assertEqual('eng-rhel-6-candidate', cmd.target)

    def test_spec(self):
        cmd = self.make_commands()
        self.assertEqual('docpkg.spec', cmd.spec)

    def test_no_spec_as_it_is_deadpackage(self):
        with patch('os.listdir', return_value=['dead.package']):
            cmd = self.make_commands()
            self.assertRaises(rpkgError, cmd.load_spec)

    def test_no_spec_there(self):
        with patch('os.listdir', return_value=['anyfile']):
            cmd = self.make_commands()
            self.assertRaises(rpkgError, cmd.load_spec)

    def test_nvr(self):
        cmd = self.make_commands(dist='eng-rhel-6')

        module_name = os.path.basename(self.repo_path)
        self.assertEqual('{0}-1.2-2.el6'.format(module_name), cmd.nvr)

    def test_nvr_cannot_get_module_name_from_push_url(self):
        cmd = self.make_commands(path=self.repo_path, dist='eng-rhel-6')
        self.assertEqual('docpkg-1.2-2.el6', cmd.nvr)

    def test_localarch(self):
        expected_localarch = rpm.expandMacro('%{_arch}')
        cmd = self.make_commands()
        self.assertEqual(expected_localarch, cmd.localarch)

    def test_commithash(self):
        cmd = self.make_commands(path=self.cloned_repo_path)
        repo = git.Repo(self.cloned_repo_path)
        expected_commit_hash = str(six.next(repo.iter_commits()))
        self.assertEqual(expected_commit_hash, cmd.commithash)

    def test_dist(self):
        repo = git.Repo(self.cloned_repo_path)
        self.checkout_branch(repo, 'eng-rhel-7')

        cmd = self.make_commands(path=self.cloned_repo_path)
        self.assertEqual('el7', cmd.disttag)
        self.assertEqual('rhel', cmd.distvar)
        self.assertEqual('7', cmd.distval)
        self.assertEqual('0', cmd.epoch)

    def test_repo(self):
        cmd = self.make_commands(path=self.cloned_repo_path)
        cmd.load_repo()
        self.assertEqual(self.cloned_repo_path, os.path.dirname(cmd._repo.git_dir))

        cmd = self.make_commands(path=self.invalid_repo)
        self.assertRaises(rpkgError, cmd.load_repo)

        cmd = self.make_commands(path='some-dir')
        self.assertRaises(rpkgError, cmd.load_repo)

    def test_mockconfig(self):
        cmd = self.make_commands(path=self.cloned_repo_path)
        self.checkout_branch(cmd.repo, 'eng-rhel-7')
        expected_localarch = rpm.expandMacro('%{_arch}')
        self.assertEqual('eng-rhel-7-candidate-{0}'.format(expected_localarch), cmd.mockconfig)

    def test_get_ns_module_name(self):
        cmd = self.make_commands(path=self.cloned_repo_path)

        tests = (
            ('http://localhost/rpms/docpkg.git', 'docpkg'),
            ('http://localhost/docker/docpkg.git', 'docpkg'),
            ('http://localhost/docpkg.git', 'docpkg'),
            ('http://localhost/rpms/docpkg', 'docpkg'),
            )
        for push_url, expected_ns_module_name in tests:
            cmd._push_url = push_url
            cmd.load_ns()
            cmd.load_module_name()
            self.assertEqual(expected_ns_module_name, cmd.ns_module_name)

        cmd.distgit_namespaced = True
        tests = (
            ('http://localhost/rpms/docpkg.git', 'rpms/docpkg'),
            ('http://localhost/docker/docpkg.git', 'docker/docpkg'),
            ('http://localhost/docpkg.git', 'rpms/docpkg'),
            ('http://localhost/rpms/docpkg', 'rpms/docpkg'),
            )
        for push_url, expected_ns_module_name in tests:
            cmd._push_url = push_url
            cmd.load_ns()
            cmd.load_module_name()
            self.assertEqual(expected_ns_module_name, cmd.ns_module_name)


class TestNamespaced(CommandTestCase):

    def test_get_namespace_giturl(self):
        cmd = self.make_commands()
        cmd.gitbaseurl = 'ssh://%(user)s@localhost/%(module)s'
        cmd.distgit_namespaced = False

        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'docpkg'},
                         cmd._get_namespace_giturl('docpkg'))
        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'docker/docpkg'},
                         cmd._get_namespace_giturl('docker/docpkg'))
        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'rpms/docpkg'},
                         cmd._get_namespace_giturl('rpms/docpkg'))

    def test_get_namespace_giturl_namespaced_is_enabled(self):
        cmd = self.make_commands()
        cmd.gitbaseurl = 'ssh://%(user)s@localhost/%(module)s'
        cmd.distgit_namespaced = True

        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'rpms/docpkg'},
                         cmd._get_namespace_giturl('docpkg'))
        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'docker/docpkg'},
                         cmd._get_namespace_giturl('docker/docpkg'))
        self.assertEqual(cmd.gitbaseurl % {'user': cmd.user, 'module': 'rpms/docpkg'},
                         cmd._get_namespace_giturl('rpms/docpkg'))

    def test_get_namespace_anongiturl(self):
        cmd = self.make_commands()
        cmd.anongiturl = 'git://localhost/%(module)s'
        cmd.distgit_namespaced = False

        self.assertEqual(cmd.anongiturl % {'module': 'docpkg'},
                         cmd._get_namespace_anongiturl('docpkg'))
        self.assertEqual(cmd.anongiturl % {'module': 'docker/docpkg'},
                         cmd._get_namespace_anongiturl('docker/docpkg'))
        self.assertEqual(cmd.anongiturl % {'module': 'rpms/docpkg'},
                         cmd._get_namespace_anongiturl('rpms/docpkg'))

    def test_get_namespace_anongiturl_namespaced_is_enabled(self):
        cmd = self.make_commands()
        cmd.anongiturl = 'git://localhost/%(module)s'
        cmd.distgit_namespaced = True

        self.assertEqual(cmd.anongiturl % {'module': 'rpms/docpkg'},
                         cmd._get_namespace_anongiturl('docpkg'))
        self.assertEqual(cmd.anongiturl % {'module': 'docker/docpkg'},
                         cmd._get_namespace_anongiturl('docker/docpkg'))
        self.assertEqual(cmd.anongiturl % {'module': 'rpms/docpkg'},
                         cmd._get_namespace_anongiturl('rpms/docpkg'))


class TestGetLatestCommit(CommandTestCase):

    def test_get_latest_commit(self):
        cmd = self.make_commands(path=self.cloned_repo_path)
        # Repos used for running tests locates in local filesyste, refer to
        # self.repo_path and self.cloned_repo_path.
        cmd.anongiturl = '/tmp/%(module)s'
        cmd.distgit_namespaced = False

        self.assertEqual(str(six.next(git.Repo(self.repo_path).iter_commits())),
                         cmd.get_latest_commit(os.path.basename(self.repo_path),
                                               'eng-rhel-6'))


def load_kojisession(self):
    self._kojisession = Mock()
    self._kojisession.getFullInheritance.return_value = [
        {'child_id': 342, 'currdepth': 1, 'filter': [], 'intransitive': False,
         'maxdepth': None, 'name': 'f25-override', 'nextdepth': None, 'noconfig': False,
         'parent_id': 341, 'pkg_filter': '', 'priority': 0},
        {'child_id': 341, 'currdepth': 2, 'filter': [], 'intransitive': False,
         'maxdepth': None, 'name': 'f25-updates', 'nextdepth': None, 'noconfig': False,
         'parent_id': 336, 'pkg_filter': '', 'priority': 0},
        {'child_id': 336, 'currdepth': 3, 'filter': [], 'intransitive': False,
         'maxdepth': None, 'name': 'f25', 'nextdepth': None, 'noconfig': False,
         'parent_id': 335, 'pkg_filter': '', 'priority': 0},
        ]


class TestTagInheritanceTag(CommandTestCase):

    @patch('pyrpkg.Commands.load_kojisession', new=load_kojisession)
    def test_error_if_not_inherit(self):
        build_target = {
            'build_tag': 342, 'build_tag_name': 'f25-build',
            'dest_tag': 337, 'dest_tag_name': 'f25-updates-candidate',
            'id': 167, 'name': 'f25-candidate',
            }
        dest_tag = {
            'arches': None, 'extra': {},
            'id': 337, 'locked': False,
            'maven_include_all': False, 'maven_support': False,
            'name': 'f25-updates-candidate',
            'perm': None, 'perm_id': None,
            }

        cmd = self.make_commands()
        self.assertRaises(rpkgError, cmd.check_inheritance, build_target, dest_tag)


class TestLoadModuleNameFromSpecialPushURL(CommandTestCase):
    """Test load module name from a special push url that ends in /

    For issue: https://pagure.io/rpkg/issue/192
    """

    def setUp(self):
        super(TestLoadModuleNameFromSpecialPushURL, self).setUp()

        self.case_repo = tempfile.mkdtemp(prefix='case-test-load-module-name-')
        cmd = ['git', 'clone', '{0}/'.format(self.repo_path), self.case_repo]
        self.run_cmd(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def tearDown(self):
        shutil.rmtree(self.case_repo)
        super(TestLoadModuleNameFromSpecialPushURL, self).tearDown()

    def test_load_module_name(self):
        cmd = self.make_commands(path=self.case_repo)
        self.assertEqual(os.path.basename(self.repo_path), cmd.module_name)


class TestLoginKojiSession(CommandTestCase):
    """Test login_koji_session"""

    def setUp(self):
        super(TestLoginKojiSession, self).setUp()

        self.cmd = self.make_commands()
        self.cmd.log = Mock()
        self.koji_config = {
            'authtype': 'ssl',
            'server': 'http://localhost/kojihub',
            'cert': '/path/to/cert',
            'ca': '/path/to/ca',
            'serverca': '/path/to/serverca',
        }
        self.session = Mock()

    @patch('pyrpkg.koji.is_requests_cert_error', return_value=True)
    def test_ssl_login_cert_revoked_or_expired(self, is_requests_cert_error):
        self.session.ssl_login.side_effect = Exception

        self.koji_config['authtype'] = 'ssl'

        self.assertRaises(rpkgError,
                          self.cmd.login_koji_session,
                          self.koji_config, self.session)
        self.cmd.log.info.assert_called_once_with(
            'Certificate is revoked or expired.')

    def test_ssl_login(self):
        self.koji_config['authtype'] = 'ssl'

        self.cmd.login_koji_session(self.koji_config, self.session)

        self.session.ssl_login.assert_called_once_with(
            self.koji_config['cert'],
            self.koji_config['ca'],
            self.koji_config['serverca'],
            proxyuser=None,
        )

    def test_runas_option_cannot_be_set_for_password_auth(self):
        self.koji_config['authtype'] = 'password'
        self.cmd.runas = 'user'
        self.assertRaises(rpkgError,
                          self.cmd.login_koji_session,
                          self.koji_config, self.session)

    @patch('pyrpkg.Commands.user', new_callable=PropertyMock)
    def test_password_login(self, user):
        user.return_value = 'tester'
        self.session.opts = {}
        self.koji_config['authtype'] = 'password'

        self.cmd.login_koji_session(self.koji_config, self.session)

        self.assertEqual({'user': 'tester', 'password': None},
                         self.session.opts)
        self.session.login.assert_called_once()

    @patch('pyrpkg.Commands._load_krb_user', return_value=False)
    def test_krb_login_fails_if_no_valid_credential(self, _load_krb_user):
        self.koji_config['authtype'] = 'kerberos'
        self.cmd.realms = ['FEDORAPROJECT.ORG']

        self.cmd.login_koji_session(self.koji_config, self.session)

        self.session.krb_login.assert_not_called()
        self.assertEqual(2, self.cmd.log.warning.call_count)

    @patch('pyrpkg.Commands._load_krb_user', return_value=True)
    def test_krb_login_fails(self, _load_krb_user):
        self.koji_config['authtype'] = 'kerberos'
        # Simulate ClientSession.krb_login fails and error is raised.
        self.session.krb_login.side_effect = Exception

        self.cmd.login_koji_session(self.koji_config, self.session)

        self.session.krb_login.assert_called_once_with(proxyuser=None)
        self.cmd.log.error.assert_called_once()

    @patch('pyrpkg.Commands._load_krb_user', return_value=True)
    def test_successful_krb_login(self, _load_krb_user):
        self.koji_config['authtype'] = 'kerberos'

        self.cmd.login_koji_session(self.koji_config, self.session)

        self.session.krb_login.assert_called_once_with(proxyuser=None)


class TestConstructBuildURL(CommandTestCase):
    """Test Commands.construct_build_url"""

    @patch('pyrpkg.Commands.ns_module_name', new_callable=PropertyMock)
    @patch('pyrpkg.Commands.commithash', new_callable=PropertyMock)
    def test_construct_url(self, commithash, ns_module_name):
        commithash.return_value = '12345'
        ns_module_name.return_value = 'container/fedpkg'

        cmd = self.make_commands()

        anongiturl = 'https://src.example.com/%(module)s'
        with patch.object(cmd, 'anongiturl', new=anongiturl):
            url = cmd.construct_build_url()

        expected_url = '{0}?#{1}'.format(
            anongiturl % {'module': ns_module_name.return_value},
            commithash.return_value)
        self.assertEqual(expected_url, url)
