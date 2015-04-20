# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


"""Interact with a lookaside cache

This module contains everything needed to upload and download source files the
way it is done by Fedora, RHEL, and other distributions maintainers.
"""


import hashlib
import logging
import os
import sys

import pycurl

from .errors import DownloadError, InvalidHashType


class CGILookasideCache(object):
    """A class to interact with a CGI-based lookaside cache"""
    def __init__(self, hashtype, download_url, upload_url):
        """Constructor

        Args:
            hashtype (str): The hash algorithm to use for uploads. (e.g 'md5')
            download_url (str): The URL used to download source files.
            upload_url (str): The URL of the CGI script called when uploading
                source files.
        """
        self.hashtype = hashtype
        self.download_url = download_url
        self.upload_url = upload_url

        self.log = logging.getLogger(__name__)

        self.download_path = '%(name)s/%(filename)s/%(hash)s/%(filename)s'

    def print_progress(self, to_download, downloaded, to_upload, uploaded):
        if to_download > 0:
            done = downloaded / to_download

        elif to_upload > 0:
            done = uploaded / to_upload

        else:
            return

        done_chars = int(done * 72)
        remain_chars = 72 - done_chars
        done = int(done * 1000) / 10.0

        p = "\r%s%s %s%%" % ("#" * done_chars, " " * remain_chars, done)
        sys.stdout.write(p)
        sys.stdout.flush()

    def hash_file(self, filename, hashtype=None):
        """Compute the hash of a file

        Args:
            filename (str): The full path to the file. It is assumed to exist.
            hashtype (str, optional): The hash algorithm to use. (e.g 'md5')
                This defaults to the hashtype passed to the constructor.

        Returns:
            The hash digest.
        """
        if hashtype is None:
            hashtype = self.hashtype

        try:
            sum = hashlib.new(hashtype)

        except ValueError:
            raise InvalidHashType(hashtype)

        with open(filename, 'rb') as f:
            chunk = f.read(8192)

            while chunk:
                sum.update(chunk)
                chunk = f.read(8192)

        return sum.hexdigest()

    def file_is_valid(self, filename, hash, hashtype=None):
        """Ensure the file is correct

        Args:
            filename (str): The full path to the file. It is assumed to exist.
            hash (str): The known good hash of the file.
            hashtype (str, optional): The hash algorithm to use. (e.g 'md5')
                This defaults to the hashtype passed to the constructor.

        Returns:
            True if the file is valid, False otherwise.
        """
        sum = self.hash_file(filename, hashtype)
        return sum == hash

    def download(self, name, filename, hash, outfile, hashtype=None, **kwargs):
        """Download a source file

        Args:
            name (str): The name of the module. (usually the name of the SRPM)
            filename (str): The name of the file to download.
            hash (str): The known good hash of the file.
            outfile (str): The full path where to save the downloaded file.
            hashtype (str, optional): The hash algorithm. (e.g 'md5')
                This defaults to the hashtype passed to the constructor.
            **kwargs: Additional keyword arguments. They will be used when
                contructing the full URL to the file to download.
        """
        if hashtype is None:
            hashtype = self.hashtype

        if os.path.exists(outfile):
            if self.file_is_valid(outfile, hash, hashtype=hashtype):
                return

        self.log.info("Downloading %s", filename)
        urled_file = filename.replace(' ', '%20')

        path_dict = {'name': name, 'filename': urled_file, 'hash': hash,
                     'hashtype': hashtype}
        path_dict.update(kwargs)
        path = self.download_path % path_dict
        url = '%s/%s' % (self.download_url, path)
        self.log.debug("Full url: %s" % url)

        with open(outfile, 'wb') as f:
            c = pycurl.Curl()
            c.setopt(pycurl.URL, url)
            c.setopt(pycurl.HTTPHEADER, ['Pragma:'])
            c.setopt(pycurl.NOPROGRESS, False)
            c.setopt(pycurl.PROGRESSFUNCTION, self.print_progress)
            c.setopt(pycurl.OPT_FILETIME, True)
            c.setopt(pycurl.WRITEDATA, f)

            try:
                c.perform()
                tstamp = c.getinfo(pycurl.INFO_FILETIME)
                status = c.getinfo(pycurl.RESPONSE_CODE)

            except Exception as e:
                raise DownloadError(e)

            finally:
                c.close()

        # Get back a new line, after displaying the download progress
        sys.stdout.write('\n')
        sys.stdout.flush()

        if status != 200:
            raise DownloadError('Server returned status code %d' % status)

        os.utime(outfile, (tstamp, tstamp))

        if not self.file_is_valid(outfile, hash, hashtype=hashtype):
            raise DownloadError('%s failed checksum' % filename)
