import os
import shutil
import tempfile
import unittest


class GitIgnoreTestCase(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix='rpkg-tests.')

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def test_match_empty(self):
        import pyrpkg
        gi = pyrpkg.GitIgnore(os.path.join(self.workdir, 'gitignore'))

        self.assertFalse(gi.match('this does not exist'))

        # The empty string could match an empty file, but we don't want it to
        self.assertFalse(gi.match(''))

    def test_match_line_from_existing_file(self):
        gi_path = os.path.join(self.workdir, 'gitignore')

        with open(gi_path, 'w') as f:
            f.write('this line exists\n')

        import pyrpkg
        gi = pyrpkg.GitIgnore(gi_path)

        self.assertTrue(gi.match('this line exists'))
        self.assertTrue(gi.match('this line exists\n'))
        self.assertTrue(gi.match('/this line exists'))
        self.assertTrue(gi.match('/this line exists\n'))

        self.assertFalse(gi.match('but this line does not'))

    def test_match_unwritten_line(self):
        import pyrpkg
        gi = pyrpkg.GitIgnore(os.path.join(self.workdir, 'gitignore'))
        gi.add('here is a new line')

        self.assertTrue(gi.modified)
        self.assertTrue(gi.match('here is a new line'))

    def test_match_glob(self):
        import pyrpkg
        gi = pyrpkg.GitIgnore(os.path.join(self.workdir, 'gitignore'))
        gi.add('*')

        self.assertTrue(gi.match('Surely this is matched by a wildcard?'))

    def test_write_new_file(self):
        gi_path = os.path.join(self.workdir, 'gitignore')

        import pyrpkg
        gi = pyrpkg.GitIgnore(gi_path)
        gi.add('here is a new line')
        gi.write()

        self.assertFalse(gi.modified)

        with open(gi_path) as f:
            self.assertEqual(f.read(), 'here is a new line\n')

    def test_write_append_to_existing_file(self):
        gi_path = os.path.join(self.workdir, 'gitignore')

        lines = ('this line exists', 'here is a new line')

        with open(gi_path, 'w') as f:
            f.write(lines[0])

        import pyrpkg
        gi = pyrpkg.GitIgnore(gi_path)
        gi.add(lines[1])
        gi.write()

        self.assertFalse(gi.modified)

        with open(gi_path) as f:
            self.assertEqual(f.read(), '%s\n' % '\n'.join(lines))