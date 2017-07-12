import os
import shutil
import tempfile

import git

from . import CommandTestCase


CLONE_CONFIG = '''
    bz.default-component %(module)s
    sendemail.to %(module)s-owner@fedoraproject.org
'''


class CommandCloneTestCase(CommandTestCase):
    def test_clone_anonymous(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, self.module)
        self.assertTrue(os.path.isdir(os.path.join(moduledir, '.git')))
        confgit = git.Git(moduledir)
        self.assertEqual(confgit.config('bz.default-component'), self.module)
        self.assertEqual(confgit.config('sendemail.to'),
                         "%s-owner@fedoraproject.org" % self.module)

    def test_clone_anonymous_with_namespace(self):
        self.module = 'rpms/module1'
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet, distgit_namespaced=True)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, 'module1')
        self.assertTrue(os.path.isdir(os.path.join(moduledir, '.git')))
        confgit = git.Git(moduledir)
        self.assertEqual(confgit.config('bz.default-component'), self.module)
        self.assertEqual(confgit.config('sendemail.to'),
                         "%s-owner@fedoraproject.org" % self.module)

    def test_clone_anonymous_with_path(self):
        self.make_new_git(self.module)

        altpath = tempfile.mkdtemp(prefix='rpkg-tests.')

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
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
                              self.anongiturl, self.branchre, self.kojiprofile,
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
                              self.anongiturl, self.branchre, self.kojiprofile,
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
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)

        def raises():
            cmd.clone(self.module, anon=True, branch='rpkg-tests-1',
                      bare_dir='test.git')
        self.assertRaises(pyrpkg.rpkgError, raises)

    def test_clone_into_dir(self):
        self.make_new_git(self.module,
                          branches=['rpkg-tests-1', 'rpkg-tests-2'])

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(
            self.module, anon=True, branch='rpkg-tests-1', target='new_clone')

        with open(os.path.join(
                self.path, 'new_clone', '.git', 'HEAD')) as HEAD:
            self.assertEqual(HEAD.read(), 'ref: refs/heads/rpkg-tests-1\n')

    def test_clone_into_dir_with_namespace(self):
        self.module = 'rpms/module1'
        self.make_new_git(self.module,
                          branches=['rpkg-tests-1', 'rpkg-tests-2'])

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet, distgit_namespaced=True)
        cmd.clone(
            self.module, anon=True, branch='rpkg-tests-1', target='new_clone')

        with open(os.path.join(
                self.path, 'new_clone', '.git', 'HEAD')) as HEAD:
            self.assertEqual(HEAD.read(), 'ref: refs/heads/rpkg-tests-1\n')
