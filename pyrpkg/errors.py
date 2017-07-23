# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


"""Custom error classes"""

import six


class rpkgError(Exception):
    """Our base error class"""
    faultCode = 1000


class rpkgAuthError(rpkgError):
    """Raised in case of authentication errors"""
    faultCode = 1002


class UnknownTargetError(Exception):
    faultCode = 1004


class HashtypeMixingError(rpkgError):
    """Raised when we try to mix hash types in a sources file"""
    def __init__(self, existing_hashtype, new_hashtype):
        super(HashtypeMixingError, self).__init__()

        self.existing_hashtype = existing_hashtype
        self.new_hashtype = new_hashtype


class MalformedLineError(rpkgError):
    """Raised when parsing a sources file with malformed lines"""
    pass


class InvalidHashType(rpkgError):
    """Raised when we don't know the requested hash algorithm"""
    pass


class DownloadError(rpkgError):
    """Raised when something went wrong during a download"""
    pass


class UploadError(rpkgError):
    """Raised when something went wrong during an upload"""

    def __init__(self, message, http_status=None):
        self.message = message
        self.http_status = http_status

    def __str__(self):
        return str(self.message)

    def __unicode__(self):
        return six.text_type(self.message)
