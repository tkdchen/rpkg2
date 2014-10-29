import os
import shutil
import subprocess
import tempfile
import unittest


class CommandCloneTestCase(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='rpkg-tests.')
        self.gitroot = os.path.join(self.path, 'gitroot')

        self.module = 'module1'

        self.anongiturl = 'file://%s/%%(module)s' % self.gitroot
        self.branchre = r'master|rpkg-tests-.+'
        self.quiet = False

        # TODO: Figure out how to handle this
        self.lookaside = 'TODO'
        self.lookasidehash = 'md5'
        self.lookaside_cgi = 'TODO'
        self.gitbaseurl = 'TODO'
        self.kojiconfig = 'TODO'
        self.build_client = 'TODO'
        self.user = 'TODO'
        self.dist = 'TODO'
        self.target = 'TODO'

    def tearDown(self):
        shutil.rmtree(self.path)

    def make_new_git(self, module, branches=None):
        """Make a new git repo, so that tests can clone it

        This is not a test method.
        """
        if branches is None:
            branches = []

        # Create a bare Git repository
        moduledir = os.path.join(self.gitroot, module)
        os.makedirs(moduledir)
        subprocess.check_call(['git', 'init', '--bare'], cwd=moduledir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Clone it, and do the minimal Dist Git setup
        cloneroot = os.path.join(self.path, 'clonedir')
        os.makedirs(cloneroot)
        subprocess.check_call(['git', 'clone', 'file://%s' % moduledir],
                              cwd=cloneroot, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        clonedir = os.path.join(cloneroot, module)
        open(os.path.join(clonedir, '.gitignore'), 'w').close()
        open(os.path.join(clonedir, 'sources'), 'w').close()
        subprocess.check_call(['git', 'add', '.gitignore', 'sources'],
                              cwd=clonedir, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        subprocess.check_call(['git', 'commit', '-m',
                               'Initial setup of the repo'], cwd=clonedir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.check_call(['git', 'push', 'origin', 'master'],
                              cwd=clonedir, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)

        # Add the requested branches
        for branch in branches:
            subprocess.check_call(['git', 'branch', branch], cwd=clonedir,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            subprocess.check_call(['git', 'push', 'origin', branch],
                                  cwd=clonedir, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)

        # Drop the clone
        shutil.rmtree(cloneroot)

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
