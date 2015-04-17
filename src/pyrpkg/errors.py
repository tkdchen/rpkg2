# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


"""Custom error classes"""


class rpkgError(Exception):
    """Our base error class"""
    faultCode = 1000


class rpkgAuthError(rpkgError):
    """Raised in case of authentication errors"""
    faultCode = 1002


class HashtypeMixingError(rpkgError):
    """Raised when we try to mix hash types in a sources file"""
    def __init__(self, existing_hashtype, new_hashtype):
        super(HashtypeMixingError, self).__init__()

        self.existing_hashtype = existing_hashtype
        self.new_hashtype = new_hashtype


class MalformedLineError(rpkgError):
    """Raised when parsing a sources file with malformed lines"""
    pass
