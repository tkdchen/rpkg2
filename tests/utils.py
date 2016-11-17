# -*- coding: utf-8 -*-

import os
import subprocess
import tempfile
import unittest
import shutil
import sys

from pyrpkg import Commands

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
Release: 2%{dist}
License: GPL
Group: Applications/Productivity
BuildRoot: %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
%description
Dummy docpkg for tests
%prep
%check
%build
touch README.rst
%clean
rm -rf $$RPM_BUILD_ROOT
%install
rm -rf $$RPM_BUILD_ROOT
%files
%defattr(-,root,root,-)
%doc README.rst
%changelog
* Thu Apr 21 2016 Tester <tester@example.com> - 1.2-2
- Initial version
'''


class Assertions(object):

    def assertFilesExists(self, filenames):
        """Assert existence of files within package repository

        :param filenames: a sequence of file names within package repository to be checked.
        :type filenames: list or tuple
        """
        assert isinstance(filenames, (tuple, list))
        for filename in filenames:
            self.assertTrue(os.path.exists(os.path.join(self.cloned_repo_path, filename)))


class Utils(object):

    def run_cmd(self, cmd, **kwargs):
        returncode = subprocess.call(cmd, **kwargs)
        if returncode != 0:
            raise RuntimeError('Command fails. Command: %s. Return code %d' % (
                ' '.join(cmd), returncode))

    def redirect_cmd_output(self, cmd, shell=False, env=None, pipe=[], cwd=None):
        if shell:
            cmd = ' '.join(cmd)
        proc = subprocess.Popen(cmd, shell=shell, cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        sys.stdout.write(stdout)
        sys.stderr.write(stderr)

    def read_file(self, filename):
        with open(filename, 'r') as f:
            return f.read()

    def write_file(self, filename, content=''):
        with open(filename, 'w') as f:
            f.write(content)


class CommandTestCase(Assertions, Utils, unittest.TestCase):

    def setUp(self):
        # create a base repo
        self.repo_path = tempfile.mkdtemp(prefix='rpkg-commands-tests-')

        self.spec_file = 'docpkg.spec'

        # Add spec file to this repo and commit
        spec_file_path = os.path.join(self.repo_path, self.spec_file)
        with open(spec_file_path, 'w') as f:
            f.write(spec_file)

        git_cmds = [
            ['git', 'init'],
            ['git', 'add', spec_file_path],
            ['touch', 'sources'],
            ['git', 'config', 'user.email', 'cqi@redhat.com'],
            ['git', 'config', 'user.name', 'Chenxiong Qi'],
            ['git', 'commit', '-m', '"initial commit"'],
            ['git', 'branch', 'eng-rhel-6'],
            ['git', 'branch', 'eng-rhel-6.5'],
            ['git', 'branch', 'eng-rhel-7'],
            ['git', 'branch', 'rhel-6.8'],
            ['git', 'branch', 'rhel-7'],
            ]
        for cmd in git_cmds:
            self.run_cmd(cmd, cwd=self.repo_path)

        # Clone the repo
        self.cloned_repo_path = tempfile.mkdtemp(prefix='rpkg-commands-tests-cloned-')
        self.run_cmd(['git', 'clone', self.repo_path, self.cloned_repo_path])
        git_cmds = [
            ['git', 'config', 'user.email', 'cqi@redhat.com'],
            ['git', 'config', 'user.name', 'Chenxiong Qi'],
            ['git', 'branch', '--track', 'eng-rhel-6', 'origin/eng-rhel-6'],
            ['git', 'branch', '--track', 'eng-rhel-6.5', 'origin/eng-rhel-6.5'],
            ['git', 'branch', '--track', 'eng-rhel-7', 'origin/eng-rhel-7'],
            ]
        for cmd in git_cmds:
            self.run_cmd(cmd, cwd=self.cloned_repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path)
        shutil.rmtree(self.cloned_repo_path)

    def make_commands(self, path=None, user=None, dist=None, target=None, quiet=None):
        """Helper method for creating Commands object for test cases

        This is where you should extend to add more features to support
        additional requirements from other Commands specific test cases.

        Some tests need customize one of user, dist, target, and quiet options
        when creating an instance of Commands. Keyword arguments user, dist,
        target, and quiet here is for this purpose.

        :param str path: path to repository where this Commands will work on
        top of
        :param str user: user passed to --user option
        :param str dist: dist passed to --dist option
        :param str target: target passed to --target option
        :param str quiet: quiet passed to --quiet option
        """
        _repo_path = path if path else self.cloned_repo_path
        return Commands(_repo_path,
                        lookaside, lookasidehash, lookaside_cgi,
                        gitbaseurl, anongiturl,
                        branchre,
                        kojiconfig, build_client,
                        user=user, dist=dist, target=target, quiet=quiet)

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

    def make_a_dummy_commit(self, repo):
        filename = os.path.join(repo.working_dir, 'document.txt')
        with open(filename, 'a+') as f:
            f.write('Hello rpkg')
        repo.index.add([filename])
        repo.index.commit('update document')
