# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


import hashlib
import os
import shutil
import tempfile
import unittest

import mock
import pycurl

from pyrpkg.lookaside import CGILookasideCache
from pyrpkg.errors import DownloadError, InvalidHashType, UploadError


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
        self.assertEqual(result, '983d43ddff6da90f6a5d3b6172446a1ffe228b803fe64fdd5dcfab5646078a896851fe82f623c9d6e5654b3d2f363a04ec17cfb62b607437a9c7c132d511e522')  # noqa

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

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_download(self, mock_curl):
        def mock_getinfo(info):
            return 200 if info == pycurl.RESPONSE_CODE else 0

        def mock_perform():
            with open(self.filename, 'rb') as f:
                curlopts[pycurl.WRITEDATA].write(f.read())

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.side_effect = mock_getinfo
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        with open(self.filename, 'wb') as f:
            f.write(b'content')

        name = 'pyrpkg'
        filename = 'pyrpkg-0.0.tar.xz'
        hash = hashlib.sha512(b'content').hexdigest()
        outfile = os.path.join(self.workdir, 'pyrpkg-0.0.tar.xz')
        full_url = 'http://example.com/%s/%s/%s/%s' % (name, filename, hash,
                                                       filename)

        lc = CGILookasideCache('sha512', 'http://example.com', '_')
        lc.download(name, filename, hash, outfile, hashtype='sha512')
        self.assertEqual(curl.perform.call_count, 1)
        self.assertEqual(curlopts[pycurl.URL].decode('utf-8'), full_url)
        self.assertEqual(os.path.getmtime(outfile), 0)

        with open(outfile) as f:
            self.assertEqual(f.read(), 'content')

        # Try a second time
        lc.download(name, filename, hash, outfile)
        self.assertEqual(curl.perform.call_count, 1)

        # Try a third time
        os.remove(outfile)
        lc.download(name, filename, hash, outfile)
        self.assertEqual(curl.perform.call_count, 2)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_download_kwargs(self, mock_curl):
        def mock_getinfo(info):
            return 200 if info == pycurl.RESPONSE_CODE else 0

        def mock_perform():
            with open(self.filename, 'rb') as f:
                curlopts[pycurl.WRITEDATA].write(f.read())

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.side_effect = mock_getinfo
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        with open(self.filename, 'wb') as f:
            f.write(b'content')

        name = 'pyrpkg'
        filename = 'pyrpkg-0.0.tar.xz'
        branch = 'f22'
        hash = hashlib.sha512(b'content').hexdigest()
        outfile = os.path.join(self.workdir, 'pyrpkg-0.0.tar.xz')

        path = '%(name)s/%(filename)s/%(branch)s/%(hashtype)s/%(hash)s'
        full_url = 'http://example.com/%s' % (
            path % {'name': name, 'filename': filename, 'branch': branch,
                    'hashtype': 'sha512', 'hash': hash})

        lc = CGILookasideCache('sha512', 'http://example.com', '_')

        # Modify the download path, to try arbitrary kwargs
        lc.download_path = path

        lc.download(name, filename, hash, outfile, hashtype='sha512',
                    branch=branch)
        self.assertEqual(curl.perform.call_count, 1)
        self.assertEqual(curlopts[pycurl.URL].decode('utf-8'), full_url)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_download_corrupted(self, mock_curl):
        def mock_getinfo(info):
            return 200 if info == pycurl.RESPONSE_CODE else 0

        def mock_perform():
            with open(self.filename) as f:
                curlopts[pycurl.WRITEDATA].write(f.read())

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.side_effect = mock_getinfo
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        with open(self.filename, 'wb') as f:
            f.write(b'content')

        hash = "not the right hash"
        outfile = os.path.join(self.workdir, 'pyrpkg-0.0.tar.xz')

        lc = CGILookasideCache('sha512', 'http://example.com', '_')
        self.assertRaises(DownloadError, lc.download, 'pyrpkg',
                          'pyrpkg-0.0.tar.xz', hash, outfile)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_download_failed(self, mock_curl):
        curl = mock_curl.return_value
        curl.perform.side_effect = Exception(
            'Could not resolve host: example.com')

        with open(self.filename, 'wb') as f:
            f.write(b'content')

        hash = hashlib.sha512(b'content').hexdigest()
        outfile = os.path.join(self.workdir, 'pyrpkg-0.0.tar.xz')

        lc = CGILookasideCache('sha512', 'http://example.com', '_')
        self.assertRaises(DownloadError, lc.download, 'pyrpkg',
                          'pyrpkg-0.0.tar.xz', hash, outfile)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_download_failed_status_code(self, mock_curl):
        def mock_getinfo(info):
            return 500 if info == pycurl.RESPONSE_CODE else 0

        def mock_perform():
            with open(self.filename) as f:
                curlopts[pycurl.WRITEDATA].write(f.read())

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.side_effect = mock_getinfo
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        with open(self.filename, 'wb') as f:
            f.write(b'content')

        hash = hashlib.sha512(b'content').hexdigest()
        outfile = os.path.join(self.workdir, 'pyrpkg-0.0.tar.xz')

        lc = CGILookasideCache('sha512', 'http://example.com', '_')
        self.assertRaises(DownloadError, lc.download, 'pyrpkg',
                          'pyrpkg-0.0.tar.xz', hash, outfile)

    @mock.patch('pyrpkg.lookaside.sys.stdout')
    def test_print_download_progress(self, mock_stdout):
        def mock_write(msg):
            written_lines.append(msg)

        written_lines = []
        expected_lines = [
            '\r##################                                                       25.0%',  # noqa
            '\r####################################                                     50.0%',  # noqa
            '\r######################################################                   75.0%',  # noqa
            '\r######################################################################## 100.0%',  # noqa
            ]

        mock_stdout.write.side_effect = mock_write

        lc = CGILookasideCache('_', '_', '_')
        lc.print_progress(2000.0, 500.0, 0.0, 0.0)
        self.assertEqual(mock_stdout.write.call_count, 1)
        self.assertEqual(len(written_lines), 1)

        lc.print_progress(2000.0, 1000.0, 0.0, 0.0)
        self.assertEqual(mock_stdout.write.call_count, 2)
        self.assertEqual(len(written_lines), 2)

        lc.print_progress(2000.0, 1500.0, 0.0, 0.0)
        self.assertEqual(mock_stdout.write.call_count, 3)
        self.assertEqual(len(written_lines), 3)

        lc.print_progress(2000.0, 2000.0, 0.0, 0.0)
        self.assertEqual(mock_stdout.write.call_count, 4)
        self.assertEqual(len(written_lines), 4)

        self.assertEqual(written_lines, expected_lines)

    @mock.patch('pyrpkg.lookaside.sys.stdout')
    def test_print_upload_progress(self, mock_stdout):
        def mock_write(msg):
            written_lines.append(msg)

        written_lines = []
        expected_lines = [
            '\r##################                                                       25.0%',  # noqa
            '\r####################################                                     50.0%',  # noqa
            '\r######################################################                   75.0%',  # noqa
            '\r######################################################################## 100.0%',  # noqa
            ]

        mock_stdout.write.side_effect = mock_write

        lc = CGILookasideCache('_', '_', '_')
        lc.print_progress(0.0, 0.0, 2000.0, 500.0)
        self.assertEqual(mock_stdout.write.call_count, 1)
        self.assertEqual(len(written_lines), 1)

        lc.print_progress(0.0, 0.0, 2000.0, 1000.0)
        self.assertEqual(mock_stdout.write.call_count, 2)
        self.assertEqual(len(written_lines), 2)

        lc.print_progress(0.0, 0.0, 2000.0, 1500.0)
        self.assertEqual(mock_stdout.write.call_count, 3)
        self.assertEqual(len(written_lines), 3)

        lc.print_progress(0.0, 0.0, 2000.0, 2000.0)
        self.assertEqual(mock_stdout.write.call_count, 4)
        self.assertEqual(len(written_lines), 4)

        self.assertEqual(written_lines, expected_lines)

    @mock.patch('pyrpkg.lookaside.sys.stdout')
    def test_print_no_progress(self, mock_stdout):
        def mock_write(msg):
            written_lines.append(msg)

        written_lines = []

        mock_stdout.write.side_effect = mock_write

        lc = CGILookasideCache('_', '_', '_')
        lc.print_progress(0.0, 0.0, 0.0, 0.0)
        self.assertEqual(len(written_lines), 0)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists(self, mock_curl):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Available')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        lc = CGILookasideCache('_', '_', '_')
        exists = lc.remote_file_exists('pyrpkg', 'pyrpkg-0.tar.xz', 'thehash')
        self.assertTrue(exists)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_does_not_exist(self, mock_curl):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Missing')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        lc = CGILookasideCache('_', '_', '_')
        exists = lc.remote_file_exists('pyrpkg', 'pyrpkg-0.tar.xz', 'thehash')
        self.assertFalse(exists)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists_with_custom_certs(self, mock_curl):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Available')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        client_cert = os.path.join(self.workdir, 'my-client-cert.cert')
        with open(client_cert, 'w'):
            pass

        ca_cert = os.path.join(self.workdir, 'my-custom-cacert.cert')
        with open(ca_cert, 'w'):
            pass

        lc = CGILookasideCache('_', '_', '_', client_cert=client_cert,
                               ca_cert=ca_cert)
        lc.remote_file_exists('pyrpkg', 'pyrpkg-0.tar.xz', 'thehash')
        self.assertEqual(curlopts[pycurl.SSLCERT], client_cert)
        self.assertEqual(curlopts[pycurl.CAINFO], ca_cert)

    @mock.patch('pyrpkg.lookaside.logging.getLogger')
    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists_missing_custom_certs(self, mock_curl,
                                                     mock_logger):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Available')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        def mock_warn(msg, *args, **kwargs):
            warn_messages.append(msg)

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        warn_messages = []
        log = mock_logger.return_value
        log.warning.side_effect = mock_warn

        client_cert = os.path.join(self.workdir, 'my-client-cert.cert')
        ca_cert = os.path.join(self.workdir, 'my-custom-cacert.cert')

        lc = CGILookasideCache('_', '_', '_', client_cert=client_cert,
                               ca_cert=ca_cert)
        lc.remote_file_exists('pyrpkg', 'pyrpkg-0.tar.xz', 'thehash')
        self.assertTrue(pycurl.SSLCERT not in curlopts)
        self.assertTrue(pycurl.CAINFO not in curlopts)
        self.assertEqual(len(warn_messages), 2)
        self.assertTrue('Missing certificate: ' in warn_messages[0])
        self.assertTrue('Missing certificate: ' in warn_messages[1])

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists_check_failed(self, mock_curl):
        curl = mock_curl.return_value
        curl.perform.side_effect = Exception(
            'Could not resolve host: example.com')

        lc = CGILookasideCache('_', '_', '_')
        self.assertRaises(UploadError, lc.remote_file_exists, 'pyrpkg',
                          'pyrpkg-0.tar.xz', 'thehash')

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists_check_failed_status_code(self, mock_curl):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Available')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 500
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        lc = CGILookasideCache('_', '_', '_')
        self.assertRaises(UploadError, lc.remote_file_exists, 'pyrpkg',
                          'pyrpkg-0.0.tar.xz', 'thehash')

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_remote_file_exists_check_unexpected_error(self, mock_curl):
        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION]('Something unexpected')

        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        lc = CGILookasideCache('_', '_', '_')
        self.assertRaises(UploadError, lc.remote_file_exists, 'pyrpkg',
                          'pyrpkg-0.tar.xz', 'thehash')

    @mock.patch('pyrpkg.lookaside.logging.getLogger')
    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload(self, mock_curl, mock_logger):
        def mock_setopt(opt, value):
            curlopts[opt] = value

        def mock_perform():
            curlopts[pycurl.WRITEFUNCTION](b'Some output')

        def mock_debug(msg):
            debug_messages.append(msg)

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.perform.side_effect = mock_perform
        curl.setopt.side_effect = mock_setopt

        debug_messages = []
        log = mock_logger.return_value
        log.debug.side_effect = mock_debug

        lc = CGILookasideCache('sha512', '_', '_')

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: False):
            lc.upload('pyrpkg', 'pyrpkg-0.0.tar.xz', 'thehash')

        self.assertTrue(pycurl.HTTPPOST in curlopts)
        self.assertEqual(curlopts[pycurl.HTTPPOST], [
            ('name', 'pyrpkg'), ('sha512sum', 'thehash'),
            ('file', (pycurl.FORM_FILE, 'pyrpkg-0.0.tar.xz'))])

        self.assertEqual(debug_messages, [b'Some output'])

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload_already_exists(self, mock_curl):
        curl = mock_curl.return_value

        lc = CGILookasideCache('_', '_', '_')
        hash = 'thehash'

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: True):
            lc.upload('pyrpkg', 'pyrpkg-0.0.tar.xz', hash)

        self.assertEqual(curl.perform.call_count, 0)
        self.assertEqual(curl.setopt.call_count, 0)

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload_with_custom_certs(self, mock_curl):
        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.setopt.side_effect = mock_setopt

        client_cert = os.path.join(self.workdir, 'my-client-cert.cert')
        with open(client_cert, 'w'):
            pass

        ca_cert = os.path.join(self.workdir, 'my-custom-cacert.cert')
        with open(ca_cert, 'w'):
            pass

        lc = CGILookasideCache('_', '_', '_', client_cert=client_cert,
                               ca_cert=ca_cert)

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: False):
            lc.upload('pyrpkg', 'pyrpkg-0.0.tar.xz', 'thehash')

        self.assertEqual(curlopts[pycurl.SSLCERT], client_cert)
        self.assertEqual(curlopts[pycurl.CAINFO], ca_cert)

    @mock.patch('pyrpkg.lookaside.logging.getLogger')
    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload_missing_custom_certs(self, mock_curl, mock_logger):
        def mock_setopt(opt, value):
            curlopts[opt] = value

        def mock_warn(msg, *args, **kwargs):
            warn_messages.append(msg)

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 200
        curl.setopt.side_effect = mock_setopt

        warn_messages = []
        log = mock_logger.return_value
        log.warning.side_effect = mock_warn

        client_cert = os.path.join(self.workdir, 'my-client-cert.cert')
        ca_cert = os.path.join(self.workdir, 'my-custom-cacert.cert')

        lc = CGILookasideCache('_', '_', '_', client_cert=client_cert,
                               ca_cert=ca_cert)

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: False):
            lc.upload('pyrpkg', 'pyrpkg-0.tar.xz', 'thehash')

        self.assertTrue(pycurl.SSLCERT not in curlopts)
        self.assertTrue(pycurl.CAINFO not in curlopts)
        self.assertEqual(len(warn_messages), 2)
        self.assertTrue('Missing certificate: ' in warn_messages[0])
        self.assertTrue('Missing certificate: ' in warn_messages[1])

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload_failed(self, mock_curl):
        curl = mock_curl.return_value
        curl.perform.side_effect = Exception(
            'Could not resolve host: example.com')

        lc = CGILookasideCache('_', '_', '_')

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: False):
            self.assertRaises(UploadError, lc.upload, 'pyrpkg',
                              'pyrpkg-0.tar.xz', 'thehash')

    @mock.patch('pyrpkg.lookaside.pycurl.Curl')
    def test_upload_failed_status_code(self, mock_curl):
        def mock_setopt(opt, value):
            curlopts[opt] = value

        curlopts = {}
        curl = mock_curl.return_value
        curl.getinfo.return_value = 500
        curl.setopt.side_effect = mock_setopt

        lc = CGILookasideCache('sha512', '_', '_')

        with mock.patch.object(lc, 'remote_file_exists', lambda *x: False):
            self.assertRaises(UploadError, lc.upload, 'pyrpkg',
                              'pyrpkg-0.tar.xz', 'thehash')
