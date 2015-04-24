# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


"""Manage a .gitignore file"""


import fnmatch
import os


class GitIgnore(object):
    """A class to manage a .gitignore file"""
    def __init__(self, path):
        """Constructor

        Args:
            path (str): The full path to the .gitignore file. If it does not
                exist, the file will be created when running GitIgnore.write()
                for the first time.
        """
        self.path = path

        # Lines of the .gitignore file, used to check if entries need to be
        # added or already exist.
        self.__lines = []

        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                for line in f:
                    self.__lines.append(self.__ensure_newline(line))

        # Set to True if we end up making any modifications, used to
        # prevent unnecessary writes.
        self.modified = False

    def __ensure_newline(self, line):
        return line if line.endswith('\n') else '%s\n' % line

    def add(self, line):
        """Add a line

        Args:
            line (str): The line to add to the file. It will not be added if
                it already matches an existing line.
        """
        if self.match(line):
            return

        line = self.__ensure_newline(line)
        self.__lines.append(line)
        self.modified = True

    def match(self, line):
        """Check whether the line matches an existing one

        This uses fnmatch to match against wildcards.

        Args:
            line (str): The new line to match against existing ones.

        Returns:
            True if the new line matches, False otherwise.
        """
        line = line.lstrip('/').rstrip('\n')

        for entry in self.__lines:
            entry = entry.lstrip('/').rstrip('\n')
            if fnmatch.fnmatch(line, entry):
                return True

        return False

    def write(self):
        """Write the file to the disk

        This will only actually write if necessary, that is if lines have been
        added since the last time the file was written.
        """
        if self.modified:
            with open(self.path, 'w') as f:
                for line in self.__lines:
                    f.write(line)

            self.modified = False
