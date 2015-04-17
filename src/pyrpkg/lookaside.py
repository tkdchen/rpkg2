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

from .errors import InvalidHashType


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
