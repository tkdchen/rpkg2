import os
import shutil
import tempfile

from . import CommandTestCase


class CommandCloneTestCase(CommandTestCase):
    def test_clone_anonymous(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, self.module)
        self.assertTrue(os.path.isdir(os.path.join(moduledir, '.git')))

    def test_clone_anonymous_with_path(self):
        self.make_new_git(self.module)

        altpath = tempfile.mkdtemp(prefix='rpkg-tests.')

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True, path=altpath)

        moduledir = os.path.join(altpath, self.module)
        self.assertTrue(os.path.isdir(os.path.join(moduledir, '.git')))

        notmoduledir = os.path.join(self.path, self.module)
        self.assertFalse(os.path.isdir(os.path.join(notmoduledir, '.git')))

        shutil.rmtree(altpath)

    def test_clone_anonymous_with_branch(self):
        self.make_new_git(self.module,
                          branches=['rpkg-tests-1', 'rpkg-tests-2'])

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True, branch='rpkg-tests-1')

        with open(os.path.join(
                self.path, self.module, '.git', 'HEAD')) as HEAD:
            self.assertEqual(HEAD.read(), 'ref: refs/heads/rpkg-tests-1\n')

    def test_clone_anonymous_with_bare_dir(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True, bare_dir='%s.git' % self.module)

        clonedir = os.path.join(self.path, '%s.git' % self.module)
        self.assertTrue(os.path.isdir(clonedir))
        self.assertFalse(os.path.exists(os.path.join(clonedir, 'index')))

    def test_clone_fails_with_both_branch_and_bare_dir(self):
        self.make_new_git(self.module,
                          branches=['rpkg-tests-1', 'rpkg-tests-2'])

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)

        with self.assertRaises(pyrpkg.rpkgError):
            cmd.clone(self.module, anon=True, branch='rpkg-tests-1',
                      bare_dir='test.git')