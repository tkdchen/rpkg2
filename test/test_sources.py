import os
import random
import shutil
import string
import sys
import tempfile
import unittest

old_path = list(sys.path)
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src')
sys.path.insert(0, src_path)
from pyrpkg import sources
sys.path = old_path


class SourceFileEntryTestCase(unittest.TestCase):
    def test_entry(self):
        e = sources.SourceFileEntry('md5', 'afile', 'ahash')
        expected = 'MD5 (afile) = ahash\n'
        self.assertEqual(str(e), expected)


class SourcesFileTestCase(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix='rpkg-tests.')
        self.sourcesfile = os.path.join(self.workdir, self._testMethodName)

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def test_parse_empty_line(self):
        s = sources.SourcesFile(self.sourcesfile)
        entry = s.parse_line('')
        self.assertIsNone(entry)

    def test_parse_eol_line(self):
        s = sources.SourcesFile(self.sourcesfile)
        entry = s.parse_line('\n')
        self.assertIsNone(entry)

    def test_parse_whitespace_line(self):
        s = sources.SourcesFile(self.sourcesfile)
        entry = s.parse_line('    \n')
        self.assertIsNone(entry)

    def test_parse_old_style_line(self):
        s = sources.SourcesFile(self.sourcesfile)

        line = 'ahash  afile\n'
        newline = 'MD5 (afile) = ahash\n'
        entry = s.parse_line(line)

        self.assertTrue(isinstance(entry, sources.SourceFileEntry))
        self.assertEqual(entry.hashtype, 'md5')
        self.assertEqual(entry.hash, 'ahash')
        self.assertEqual(entry.file, 'afile')
        self.assertEqual(str(entry), newline)

    def test_parse_entry_line(self):
        s = sources.SourcesFile(self.sourcesfile)

        line = 'MD5 (afile) = ahash\n'
        entry = s.parse_line(line)

        self.assertTrue(isinstance(entry, sources.SourceFileEntry))
        self.assertEqual(entry.hashtype, 'md5')
        self.assertEqual(entry.hash, 'ahash')
        self.assertEqual(entry.file, 'afile')
        self.assertEqual(str(entry), line)

    def test_parse_wrong_lines(self):
        s = sources.SourcesFile(self.sourcesfile)

        lines = ['ahash',
                 'ahash  ',
                 'ahash afile',
                 'SHA512 (afile) = ahash garbage',
                 'MD5 SHA512 (afile) = ahash',
                 ]

        for line in lines:
            with self.assertRaises(sources.MalformedLineError):
                s.parse_line(line)

    def test_open_new_file(self):
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

    def test_open_empty_file(self):
        open(self.sourcesfile, 'w').write('')
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

    def test_open_existing_file_with_old_style_lines(self):
        lines = ['ahash  afile\n', 'anotherhash  anotherfile\n']
        newlines = ['MD5 (afile) = ahash\n',
                    'MD5 (anotherfile) = anotherhash\n']

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile)

        for i, entry in enumerate(s.entries):
            self.assertTrue(isinstance(entry, sources.SourceFileEntry))
            self.assertEqual(str(entry), newlines[i])

    def test_open_existing_file(self):
        lines = ['MD5 (afile) = ahash\n', 'MD5 (anotherfile) = anotherhash\n']

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile)

        for i, entry in enumerate(s.entries):
            self.assertTrue(isinstance(entry, sources.SourceFileEntry))
            self.assertEqual(str(entry), lines[i])

    def test_open_existing_file_with_mixed_lines(self):
        lines = ['ahash  afile\n',
                 'anotherhash  anotherfile\n',
                 'MD5 (thirdfile) = thirdhash\n',
                 ]
        expected = [
            'MD5 (afile) = ahash\n',
            'MD5 (anotherfile) = anotherhash\n',
            'MD5 (thirdfile) = thirdhash\n',
            ]

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile)

        for i, entry in enumerate(s.entries):
            self.assertTrue(isinstance(entry, sources.SourceFileEntry))
            self.assertEqual(str(entry), expected[i])

    def test_open_existing_file_with_identical_entries_old_and_new(self):
        lines = ['ahash  afile\n',
                 'MD5 (afile) = ahash\n',
                 ]

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile)

        self.assertEqual(len(s.entries), 1)
        self.assertEqual(s.entries[0].hashtype, 'md5')
        self.assertEqual(s.entries[0].file, 'afile')
        self.assertEqual(s.entries[0].hash, 'ahash')
        self.assertEqual(str(s.entries[0]), lines[-1])

    def test_open_existing_file_with_wrong_line(self):
        line = 'some garbage here\n'

        with open(self.sourcesfile, 'w') as f:
            f.write(line)

        with self.assertRaises(sources.MalformedLineError):
            return sources.SourcesFile(self.sourcesfile)

    def test_add_entry(self):
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

        s.add_entry('md5', 'afile', 'ahash')
        self.assertEqual(len(s.entries), 1)
        self.assertEqual(str(s.entries[-1]), 'MD5 (afile) = ahash\n')

        s.add_entry('md5', 'anotherfile', 'anotherhash')
        self.assertEqual(len(s.entries), 2)
        self.assertEqual(str(s.entries[-1]), 'MD5 (anotherfile) = anotherhash\n')

    def test_add_entry_twice(self):
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

        s.add_entry('md5', 'afile', 'ahash')
        self.assertEqual(len(s.entries), 1)
        self.assertEqual(str(s.entries[-1]), 'MD5 (afile) = ahash\n')

        s.add_entry('md5', 'afile', 'ahash')
        self.assertEqual(len(s.entries), 1)

    def test_add_entry_mixing_hashtypes(self):
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

        s.add_entry('md5', 'afile', 'ahash')
        self.assertEqual(len(s.entries), 1)
        self.assertEqual(str(s.entries[-1]), 'MD5 (afile) = ahash\n')

        with self.assertRaises(sources.HashtypeMixingError):
            s.add_entry('sha512', 'anotherfile', 'anotherhash')

    def test_write_new_file(self):
        s = sources.SourcesFile(self.sourcesfile)
        self.assertEqual(len(s.entries), 0)

        s.add_entry('md5', 'afile', 'ahash')
        s.add_entry('md5', 'anotherfile', 'anotherhash')
        s.write()

        with open(self.sourcesfile) as f:
             lines = f.readlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], 'MD5 (afile) = ahash\n')
        self.assertEqual(lines[1], 'MD5 (anotherfile) = anotherhash\n')

    def test_write_adding_a_line(self):
        lines = ['ahash  afile\n', 'anotherhash  anotherfile\n']

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile)
        s.add_entry('md5', 'thirdfile', 'thirdhash')
        s.write()

        with open(self.sourcesfile) as f:
             lines = f.readlines()

        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], 'MD5 (afile) = ahash\n')
        self.assertEqual(lines[1], 'MD5 (anotherfile) = anotherhash\n')
        self.assertEqual(lines[2], 'MD5 (thirdfile) = thirdhash\n')

    def test_write_over(self):
        lines = ['ahash  afile\n', 'anotherhash  anotherfile\n']

        with open(self.sourcesfile, 'w') as f:
            for line in lines:
                f.write(line)

        s = sources.SourcesFile(self.sourcesfile, replace=True)
        s.add_entry('md5', 'thirdfile', 'thirdhash')
        s.write()

        with open(self.sourcesfile) as f:
             lines = f.readlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], 'MD5 (thirdfile) = thirdhash\n')


if __name__ == '__main__':
    unittest.main()
