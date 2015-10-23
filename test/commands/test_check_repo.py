import os
import shutil
import subprocess
import tempfile

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
            self.anongiturl, self.branchre, self.kojiconfig,
            self.build_client, self.user, self.dist,
            self.target, self.quiet
        )

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
