"""
Our so-called sources file is simple text-based line-oriented file format. Each
line represents one file and has two fields: file hash and base name of the
file. Field separator is two spaces and Unix end-of-lines.

This sources module implements API similar to csv module from standard library
to read and write data in sources file format.
"""


class Reader(object):
    def __init__(self, sourcesfile):
        self.sourcesfile = sourcesfile
        self._sourcesiter = None

    def __iter__(self):
        for entry in self.sourcesfile:
            yield _parse_line(entry)


class Writer(object):
    def __init__(self, sourcesfile):
        self.sourcesfile = sourcesfile

    def writerow(self, row):
        self.sourcesfile.write("%s\n" % _format_line(row))

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def reader(sourcesfile):
    return Reader(sourcesfile)


def writer(sourcesfile):
    return Writer(sourcesfile)


def _parse_line(line):
    stripped_line = line.strip()
    if not stripped_line:
        return []
    entries = stripped_line.split('  ', 1)
    if len(entries) != 2:
        raise ValueError("Malformed line: %r." % line)
    return entries


def _format_line(entry):
    if len(entry) != 0 and len(entry) != 2:
        raise ValueError("Incorrect number of fields for entry: %r."
                         % (entry,))
    return "  ".join(entry)
