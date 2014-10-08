import os
import sys
import StringIO
import unittest

old_path = list(sys.path)
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src')
sys.path.insert(0, src_path)
from pyrpkg import sources
sys.path = old_path


class formatLineTestCase(unittest.TestCase):
    def test_wrong_number_of_fields(self):
        WRONG_ENTRIES = [
            ('foo'),
            ('foo', 'bar', 'foo'),
        ]
        for entry in WRONG_ENTRIES:
            self.assertRaises(ValueError, sources._format_line, entry)

    def test_empty_entry(self):
        self.assertEqual('', sources._format_line(()))

    def test_correct_entry(self):
        CORRECT_ENTRIES = [
            (['foo', 'bar'], ('foo  bar')),
        ]
        for entry, line in CORRECT_ENTRIES:
            self.assertEqual(line,
                             sources._format_line(entry))


class parseLineTestCase(unittest.TestCase):
    def test_wrong_number_of_parts(self):
        WRONG_LINES = [
            'foo\n',
            'foo  \n',
            'foo bar\n',
        ]
        for line in WRONG_LINES:
            self.assertRaises(ValueError, sources._parse_line, line)

    def test_empty_line(self):
        EMPTY_LINES = [
            '',
            '\n',
            '  \n',
        ]
        for line in EMPTY_LINES:
            self.assertEqual([], sources._parse_line(line))

    def test_correct_line(self):
        CORRECT_LINES = [
            ('foo  bar\n', ['foo', 'bar']),
            ('foo   bar\n', ['foo', ' bar'])
        ]
        for line, entry in CORRECT_LINES:
            self.assertEqual(entry, sources._parse_line(line))


class ReaderTestCase(unittest.TestCase):
    def test_empty_sources(self):
        EMPTY_SOURCES = [
            ('', []),
            ('\n', [[]]),
            (' \n', [[]]),
            ('\n\n', [[], []]),
            (' \n ', [[], []]),
        ]
        for buffer, entries in EMPTY_SOURCES:
            fp = StringIO.StringIO(buffer)
            reader = sources.Reader(fp)
            self.assertEqual(entries, [a for a in reader])
            fp.close()

    def test_correct_sources(self):
        CORRECT_SOURCES = [
            ('foo  bar\n', [['foo', 'bar']]),
            ('foo  bar\nfooo  baaar\n', [['foo', 'bar'],
                                         ['fooo', 'baaar'],
                                         ]),
        ]
        for buffer, entries in CORRECT_SOURCES:
            fp = StringIO.StringIO(buffer)
            reader = sources.Reader(fp)
            self.assertEqual(entries, [a for a in reader])
            fp.close()


class WriterTestCase(unittest.TestCase):
    def test_writerows(self):
        CORRECT_SOURCES = [
            ([['foo', 'bar']], 'foo  bar\n'),
            ([['foo', 'bar'],
              ['fooo', 'baaar'],
              ], 'foo  bar\nfooo  baaar\n'),
        ]
        for entries, buffer in CORRECT_SOURCES:
            fp = StringIO.StringIO()
            writer = sources.Writer(fp)
            writer.writerows(entries)
            self.assertEqual(fp.getvalue(), buffer)
            fp.close()


if __name__ == '__main__':
    unittest.main()
