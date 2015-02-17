"""
Our so-called sources file is simple text-based line-oriented file format.

Each line represents one source file and is in the same format as the output
of commands like `md5sum --tag filename`:

    hashtype (filename) = hash

To preserve backwards compatibility, lines can also be in the older format,
which corresponds to the output of commands like `md5sum filename`:

    hash  filename

This module implements a simple API to read these files, parse lines into
entries, and write these entries to the file in the proper format.
"""


import os
import re


LINE_PATTERN = re.compile(
    r'^(?P<hashtype>[^ ]+?) \((?P<file>[^ )]+?)\) = (?P<hash>[^ ]+?)$')


class MalformedLineError(Exception):
    pass


class SourcesFile(object):
    def __init__(self, sourcesfile, replace=False):
        self.sourcesfile = sourcesfile
        self.entries = []

        if not replace:
            if not os.path.exists(sourcesfile):
                return

            with open(sourcesfile) as f:
                for line in f:
                    entry = self.parse_line(line)

                    if entry and entry not in self.entries:
                        self.entries.append(entry)

    def parse_line(self, line):
        stripped = line.strip()

        if not stripped:
            return

        m = LINE_PATTERN.match(stripped)
        if m is not None:
            return SourceFileEntry(m.group('hashtype'), m.group('file'),
                                   m.group('hash'))

        # Try falling back on the old format
        try:
            hash, file = stripped.split('  ', 1)

        except ValueError:
            raise MalformedLineError(line)

        return SourceFileEntry('md5', file, hash)

    def add_entry(self, hashtype, file, hash):
        entry = SourceFileEntry(hashtype, file, hash)

        if entry not in self.entries:
            self.entries.append(entry)

    def write(self):
        with open(self.sourcesfile, 'w') as f:
            for entry in self.entries:
                f.write(str(entry))


class SourceFileEntry(object):
    def __init__(self, hashtype, file, hash):
            self.hashtype = hashtype.lower()
            self.hash = hash
            self.file = file

    def __str__(self):
        return '%s (%s) = %s\n' % (self.hashtype.upper(), self.file,
                                   self.hash)


    def __eq__(self, other):
        return ((self.hashtype, self.hash, self.file) ==
                (other.hashtype, other.hash, other.file))
