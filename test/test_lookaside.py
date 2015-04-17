# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


import os
import shutil
import sys
import tempfile
import unittest

old_path = list(sys.path)
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../src')
sys.path.insert(0, src_path)
from pyrpkg.lookaside import CGILookasideCache
from pyrpkg.errors import InvalidHashType
sys.path = old_path


class CGILookasideCacheTestCase(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix='rpkg-tests.')
        self.filename = os.path.join(self.workdir, self._testMethodName)

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def test_hash_file(self):
        lc = CGILookasideCache('sha512', '_', '_')

        with open(self.filename, 'w') as f:
            f.write('something')

        result = lc.hash_file(self.filename, 'md5')
        self.assertEqual(result, '437b930db84b8079c2dd804a71936b5f')

        result = lc.hash_file(self.filename)
        self.assertEqual(result, '983d43ddff6da90f6a5d3b6172446a1ffe228b803fe64fdd5dcfab5646078a896851fe82f623c9d6e5654b3d2f363a04ec17cfb62b607437a9c7c132d511e522')  # nopep8

    def test_hash_file_invalid_hash_type(self):
        lc = CGILookasideCache('sha512', '_', '_')
        self.assertRaises(InvalidHashType, lc.hash_file, '_', 'sha42')

    def test_hash_file_empty(self):
        lc = CGILookasideCache('sha512', '_', '_')

        with open(self.filename, 'w') as f:
            f.write('')

        result = lc.hash_file(self.filename, 'md5')
        self.assertEqual(result, 'd41d8cd98f00b204e9800998ecf8427e')

    def test_file_is_valid(self):
        lc = CGILookasideCache('md5', '_', '_')

        with open(self.filename, 'w') as f:
            f.write('something')

        self.assertTrue(lc.file_is_valid(self.filename,
                                         '437b930db84b8079c2dd804a71936b5f'))
        self.assertFalse(lc.file_is_valid(self.filename, 'not the right hash',
                                          hashtype='sha512'))
