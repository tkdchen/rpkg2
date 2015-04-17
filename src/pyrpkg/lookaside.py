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
