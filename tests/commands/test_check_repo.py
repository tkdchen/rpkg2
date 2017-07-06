import logging
import os
import shutil
import subprocess
import sys
import tempfile

from mock import patch
from six.moves import StringIO
from pyrpkg.errors import rpkgError

from . import CommandTestCase


class CheckRepoCase(CommandTestCase):

    def setUp(self):
        super(CheckRepoCase, self).setUp()
        self.dist = "master"
        self.make_new_git(self.module)
        moduledir = os.path.join(self.gitroot, self.module)

        self.altpath = tempfile.mkdtemp(prefix='rpkg-tests.')
        self.clonedir = os.path.join(self.altpath, self.module)
        subprocess.check_call(['git', 'clone', 'file://%s' % moduledir],
                              cwd=self.altpath, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        import pyrpkg
        self.cmd = pyrpkg.Commands(
            self.clonedir, self.lookaside, self.lookasidehash,
            self.lookaside_cgi, self.gitbaseurl,
            self.anongiturl, self.branchre, self.kojiprofile,
            self.build_client, self.user, self.dist,
            self.target, self.quiet
        )
        self.config_repo(self.clonedir)

    def tearDown(self):
        super(CheckRepoCase, self).tearDown()
        # Drop the clone
        shutil.rmtree(self.altpath)

    def test_repo_is_dirty(self):
        with open(os.path.join(self.clonedir, 'sources'), 'w') as fd:
            fd.write("a")

        try:
            self.cmd.check_repo(is_dirty=True, all_pushed=False)
        except rpkgError as exception:
            self.assertTrue("has uncommitted changes" in str(exception))
        else:
            self.fail("Expected an rpkgError exception.")

    def test_repo_has_unpushed_changes(self):
        with open(os.path.join(self.clonedir, 'sources'), 'w') as fd:
            fd.write("a")
        subprocess.check_call(
            ['git', 'add', 'sources'],
            cwd=self.clonedir
        )
        subprocess.check_call(
            ['git', 'commit', '-m', 'commit sources'],
            cwd=self.clonedir,
        )

        try:
            self.cmd.check_repo(is_dirty=False, all_pushed=True)
        except rpkgError as exception:
            self.assertTrue("There are unpushed changes in your repo" in
                            str(exception))
        else:
            self.fail("Expected an rpkgError exception.")

    def test_repo_is_clean(self):
        self.cmd.check_repo(is_dirty=True, all_pushed=False)

    def test_repo_has_everything_pushed(self):
        self.cmd.check_repo(is_dirty=False, all_pushed=True)

    def test_check_repo_has_namespace(self):

        def assert_warning(push_url, expected_msg):
            with patch('sys.stderr', new=StringIO()):
                with patch('pyrpkg.Commands.push_url', new=push_url):
                    self.cmd.log.addHandler(logging.StreamHandler())
                    self.cmd.log.setLevel(logging.WARNING)

                    self.cmd.check_repo(is_dirty=False, all_pushed=False)
                    output = sys.stderr.getvalue()
                    self.assertTrue(expected_msg in output)

        assert_warning('https://localhost/package',
                       'Your git configuration does not use a namespace.')
        assert_warning('https://localhost/rpms/package', '')
        assert_warning('https://localhost/docker/package', '')
        assert_warning('https://localhost/module/rpms/package', '')
