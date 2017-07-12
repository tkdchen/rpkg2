import os
import shutil
import subprocess
import sys
import tempfile
import unittest


class CommandTestCase(unittest.TestCase):
    def setUp(self):
        self.origin_dir = os.getcwd()
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
        self.kojiprofile = 'TODO'
        self.build_client = 'TODO'
        self.clone_config = '''
            bz.default-component %(module)s
            sendemail.to %(module)s-owner@fedoraproject.org
        '''
        self.user = 'TODO'
        self.dist = 'TODO'
        self.target = 'TODO'

    def tearDown(self):
        os.chdir(self.origin_dir)
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
        clonedir = os.path.join(cloneroot, module.split('/')[-1])
        open(os.path.join(clonedir, '.gitignore'), 'w').close()
        open(os.path.join(clonedir, 'sources'), 'w').close()
        subprocess.check_call(['git', 'config', 'user.name', 'tester'],
                              cwd=clonedir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.check_call(['git', 'config', 'user.email', 'tester@example.com'],
                              cwd=clonedir,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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

    def config_repo(self, repo_path):
        subprocess.check_call(['git', 'config', 'user.name', 'tester'], cwd=repo_path)
        subprocess.check_call(['git', 'config', 'user.email', 'tester@example.com'], cwd=repo_path)

    def get_tags(self, gitdir):
        result = []

        tags = subprocess.Popen(['git', 'tag', '-n1'], cwd=gitdir,
                                stdout=subprocess.PIPE,
                                universal_newlines=True).communicate()[0]

        for line in tags.split('\n'):
            if not line:
                continue

            tokens = [x for x in line.split() if x]
            result.append([tokens[0], ' '.join(tokens[1:])])

        return result

    def hijack_stdout(self):
        class cm(object):
            def __enter__(self):
                from six.moves import cStringIO as StringIO

                self.old_stdout = sys.stdout
                self.out = StringIO()
                sys.stdout = self.out

                return self.out

            def __exit__(self, *args):
                sys.stdout.flush()
                sys.stdout = self.old_stdout

                self.out.seek(0)

        return cm()
