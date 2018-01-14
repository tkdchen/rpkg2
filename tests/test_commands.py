# -*- coding: utf-8 -*-

import errno
import os
import shutil
import six
import subprocess
import tempfile

from contextlib import contextmanager

import git
import rpm
from mock import call
from mock import patch
from mock import Mock
from mock import PropertyMock
from mock import mock_open

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
        cloned_repo = self.cmd.repo.repo.clone(cloned_repo_dir)

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

    @patch('pyrpkg.pkgrepo.PackageRepo.branch_merge', new_callable=PropertyMock)
    def test_load_rpmdefines_against_invalid_branch(self, branch_merge):
        branch_merge.return_value = 'invalid-branch-name'

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
            cmd.repo.check()
        except rpkgError as e:
            if 'There are unpushed changes in your repo' in e:
                self.fail('There are unpushed changes in your repo. This '
                          'should not happen. Something must be going wrong.')

            self.fail('Should not fail. Something must be going wrong.')

    def test_check_repo_without_specificed_dist(self):
        cmd = self.make_commands(self.cloned_repo_path)
        try:
            cmd.repo.check()
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
        self.assertEqual(expected_commit_hash, cmd.repo.commit_hash)

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
        self.assertEqual('eng-rhel-7-candidate-{0}'.format(expected_localarch),
                         cmd.mockconfig)

    def test_get_ns_module_name(self):
        tests = (
            ('http://localhost/rpms/docpkg.git', 'docpkg'),
            ('http://localhost/docker/docpkg.git', 'docpkg'),
            ('http://localhost/docpkg.git', 'docpkg'),
            ('http://localhost/rpms/docpkg', 'docpkg'),
            )
        for push_url, expected_ns_module_name in tests:
            with patch('pyrpkg.pkgrepo.PackageRepo.push_url',
                       new_callable=PropertyMock,
                       return_value=push_url):
                cmd = self.make_commands(path=self.cloned_repo_path)
                cmd.load_ns()
                cmd.load_module_name()
                self.assertEqual(expected_ns_module_name, cmd.ns_module_name)

        tests = (
            ('http://localhost/rpms/docpkg.git', 'rpms/docpkg'),
            ('http://localhost/docker/docpkg.git', 'docker/docpkg'),
            ('http://localhost/docpkg.git', 'rpms/docpkg'),
            ('http://localhost/rpms/docpkg', 'rpms/docpkg'),
            )
        for push_url, expected_ns_module_name in tests:
            with patch('pyrpkg.pkgrepo.PackageRepo.push_url',
                       new_callable=PropertyMock,
                       return_value=push_url):
                cmd = self.make_commands(path=self.cloned_repo_path)
                cmd.distgit_namespaced = True
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

    def test_construct_with_given_module_name_and_hash(self):
        cmd = self.make_commands()

        anongiturl = 'https://src.example.com/%(module)s'
        with patch.object(cmd, 'anongiturl', new=anongiturl):
            for module_name in ('extra-cmake-modules',
                                'rpms/kf5-kfilemetadata'):
                url = cmd.construct_build_url(module_name, '123456')

                expected_url = '{0}?#{1}'.format(
                    anongiturl % {'module': module_name},
                    '123456')
                self.assertEqual(expected_url, url)


class TestCleanupTmpDir(CommandTestCase):
    """Test Commands._cleanup_tmp_dir for mockbuild command"""

    def setUp(self):
        super(TestCleanupTmpDir, self).setUp()
        self.tmp_dir_name = tempfile.mkdtemp(prefix='test-cleanup-tmp-dir-')

    def tearDown(self):
        if os.path.exists(self.tmp_dir_name):
            os.rmdir(self.tmp_dir_name)
        super(TestCleanupTmpDir, self).tearDown()

    @patch('shutil.rmtree')
    def test_do_nothing_is_tmp_dir_is_invalid(self, rmtree):
        cmd = self.make_commands()
        for invalid_dir in ('', None):
            cmd._cleanup_tmp_dir(invalid_dir)
            rmtree.assert_not_called()

    def test_remove_tmp_dir(self):
        cmd = self.make_commands()
        cmd._cleanup_tmp_dir(self.tmp_dir_name)

        self.assertFalse(os.path.exists(self.tmp_dir_name))

    def test_keep_silient_if_tmp_dir_does_not_exist(self):
        cmd = self.make_commands()
        tmp_dir = tempfile.mkdtemp()
        os.rmdir(tmp_dir)

        cmd._cleanup_tmp_dir(tmp_dir)

    def test_raise_error_if_other_non_no_such_file_dir_error(self):
        cmd = self.make_commands()
        with patch('shutil.rmtree',
                   side_effect=OSError((errno.EEXIST), 'error message')):
            self.assertRaises(rpkgError, cmd._cleanup_tmp_dir, '/tmp/dir')


class TestConfigMockConfigDir(CommandTestCase):
    """Test Commands._config_dir_basic for mockbuild"""

    def setUp(self):
        super(TestConfigMockConfigDir, self).setUp()

        self.cmd = self.make_commands()

        self.fake_root = 'fedora-26-x86_64'
        self.mock_config_patcher = patch('pyrpkg.Commands.mock_config',
                                         return_value='mock config x86_64')
        self.mock_mock_config = self.mock_config_patcher.start()

        self.mkdtemp_patcher = patch('tempfile.mkdtemp',
                                     return_value='/tmp/mockconfig/dir')
        self.mock_mkdtemp = self.mkdtemp_patcher.start()

    def tearDown(self):
        self.mkdtemp_patcher.stop()
        self.mock_config_patcher.stop()
        super(TestConfigMockConfigDir, self).tearDown()

    @contextmanager
    def assert_file_op(self, filename, mode, write_data=None):
        """Assert file object operation"""
        with patch.object(six.moves.builtins, 'open', mock_open()) as mock:
            yield
            mock.assert_called_once_with(filename, mode)
            if write_data is not None:
                mock.return_value.write.assert_called_once_with(write_data)

    def test_config_in_created_config_dir(self):
        config_file = '{0}.cfg'.format(
            os.path.join(self.mock_mkdtemp.return_value, self.fake_root))

        with self.assert_file_op(
                config_file, 'wb',
                write_data=self.mock_mock_config.return_value):
            config_dir = self.cmd._config_dir_basic(root=self.fake_root)
            self.assertEqual(self.mock_mkdtemp.return_value, config_dir)

    def test_config_in_specified_config_dir(self):
        fake_config_dir = '/path/to/fake/config-dir'
        config_file = '{0}.cfg'.format(
            os.path.join(fake_config_dir, self.fake_root))

        with self.assert_file_op(
                config_file, 'wb',
                write_data=self.mock_mock_config.return_value):
            config_dir = self.cmd._config_dir_basic(config_dir=fake_config_dir,
                                                    root=self.fake_root)
            self.assertEqual(fake_config_dir, config_dir)

    @patch('pyrpkg.Commands.mockconfig', new_callable=PropertyMock)
    def test_config_using_root_guessed_from_branch(self, mockconfig):
        mockconfig.return_value = 'f26-candidate-i686'
        config_file = '{0}.cfg'.format(
            os.path.join(self.mock_mkdtemp.return_value,
                         mockconfig.return_value))

        with self.assert_file_op(
                config_file, 'wb',
                write_data=self.mock_mock_config.return_value):
            config_dir = self.cmd._config_dir_basic()
            self.assertEqual(self.mock_mkdtemp.return_value,
                             config_dir)

    def test_fail_if_error_occurs_while_getting_mock_config(self):
        self.mock_mock_config.side_effect = rpkgError

        with patch('pyrpkg.Commands._cleanup_tmp_dir') as mock:
            self.assertRaises(
                rpkgError, self.cmd._config_dir_basic, root=self.fake_root)
            mock.assert_called_once_with(self.mock_mkdtemp.return_value)

        with patch('pyrpkg.Commands._cleanup_tmp_dir') as mock:
            self.assertRaises(rpkgError,
                              self.cmd._config_dir_basic,
                              config_dir='/path/to/fake/config-dir',
                              root=self.fake_root)
            mock.assert_called_once_with(None)

    def test_fail_if_error_occurs_while_writing_cfg_file(self):
        with patch.object(six.moves.builtins, 'open', mock_open()) as m:
            m.return_value.write.side_effect = IOError

            with patch('pyrpkg.Commands._cleanup_tmp_dir') as mock:
                self.assertRaises(rpkgError,
                                  self.cmd._config_dir_basic,
                                  root=self.fake_root)
                mock.assert_called_once_with(self.mock_mkdtemp.return_value)

            with patch('pyrpkg.Commands._cleanup_tmp_dir') as mock:
                self.assertRaises(rpkgError,
                                  self.cmd._config_dir_basic,
                                  config_dir='/path/to/fake/config-dir',
                                  root=self.fake_root)
                mock.assert_called_once_with(None)


class TestConfigMockConfigDirWithNecessaryFiles(CommandTestCase):
    """Test Commands._config_dir_other"""

    @patch('shutil.copy2')
    @patch('os.path.exists', return_value=True)
    def test_copy_cfg_files_from_etc_mock_dir(self, exists, copy2):
        cmd = self.make_commands()
        cmd._config_dir_other('/path/to/config-dir')

        exists.assert_has_calls([
            call('/etc/mock/site-defaults.cfg'),
            call('/etc/mock/logging.ini')
        ])
        copy2.assert_has_calls([
            call('/etc/mock/site-defaults.cfg',
                 '/path/to/config-dir/site-defaults.cfg'),
            call('/etc/mock/logging.ini',
                 '/path/to/config-dir/logging.ini'),
        ])

    @patch('os.path.exists', return_value=False)
    def test_create_empty_cfg_files_if_not_exist_in_system_mock(self, exists):
        cmd = self.make_commands()

        with patch.object(six.moves.builtins, 'open', mock_open()) as m:
            cmd._config_dir_other('/path/to/config-dir')

            m.assert_has_calls([
                call('/path/to/config-dir/site-defaults.cfg', 'w'),
                call().close(),
                call('/path/to/config-dir/logging.ini', 'w'),
                call().close(),
            ])

        exists.assert_has_calls([
            call('/etc/mock/site-defaults.cfg'),
            call('/etc/mock/logging.ini')
        ])

    @patch('shutil.copy2')
    @patch('os.path.exists', return_value=True)
    def test_fail_when_copy_cfg_file(self, exists, copy2):
        copy2.side_effect = OSError

        cmd = self.make_commands()
        self.assertRaises(rpkgError,
                          cmd._config_dir_other, '/path/to/config-dir')

    @patch('os.path.exists', return_value=False)
    def test_fail_if_error_when_write_empty_cfg_files(self, exists):
        cmd = self.make_commands()

        with patch.object(six.moves.builtins, 'open', mock_open()) as m:
            m.side_effect = IOError
            self.assertRaises(rpkgError,
                              cmd._config_dir_other, '/path/to/config-dir')


class TestLint(CommandTestCase):
    @patch('glob.glob')
    @patch('os.path.exists')
    @patch('pyrpkg.Commands._run_command')
    @patch('pyrpkg.Commands.load_rpmdefines', new=mock_load_rpmdefines)
    @patch('pyrpkg.Commands.rel', new_callable=PropertyMock)
    def test_lint_each_file_once(self, rel, run, exists, glob):
        rel.return_value = '2.fc26'

        cmd = self.make_commands()
        srpm_path = os.path.join(cmd.path, 'docpkg-1.2-2.fc26.src.rpm')
        bin_path = os.path.join(cmd.path, 'x86_64', 'docpkg-1.2-2.fc26.x86_64.rpm')

        def _mock_exists(path):
            return path in [
                srpm_path,
                os.path.join(cmd.path, 'x86_64'),
            ]

        def _mock_glob(g):
            return {
                os.path.join(cmd.path, 'x86_64', '*.rpm'): [bin_path],
            }[g]
        exists.side_effect = _mock_exists
        glob.side_effect = _mock_glob
        cmd._get_build_arches_from_spec = Mock(return_value=['x86_64', 'x86_64'])

        cmd.lint()

        self.assertEqual(
            run.call_args_list,
            [call(['rpmlint',
                   os.path.join(cmd.path, 'docpkg.spec'),
                   srpm_path,
                   bin_path,
                   ], shell=True)])
