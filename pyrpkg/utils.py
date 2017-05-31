# Copyright (c) 2015 - Red Hat Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


"""Miscellaneous utilities

This module contains a bunch of utilities used elsewhere in pyrpkg.
"""


import os
import six
import sys

if six.PY3:
    def u(s):
        return s

    getcwd = os.getcwd
else:
    def u(s):
        return s.decode('utf-8')

    getcwd = os.getcwdu


class cached_property(property):
    """A property caching its return value

    This is pretty much the same as a normal Python property, except that the
    decorated function is called only once. Its return value is then saved,
    subsequent calls will return it without executing the function any more.

    Example:
        >>> class Foo(object):
        ...     @cached_property
        ...     def bar(self):
        ...         print("Executing Foo.bar...")
        ...         return 42
        ...
        >>> f = Foo()
        >>> f.bar
        Executing Foo.bar...
        42
        >>> f.bar
        42
    """
    def __get__(self, inst, type=None):
        try:
            return getattr(inst, '_%s' % self.fget.__name__)
        except AttributeError:
            v = super(cached_property, self).__get__(inst, type)
            setattr(inst, '_%s' % self.fget.__name__, v)
            return v


def warn_deprecated(clsname, oldname, newname):
    """Emit a deprecation warning

    Args:
        clsname (str): The name of the class which has its attribute
            deprecated.
        oldname (str): The name of the deprecated attribute.
        newname (str): The name of the new attribute, which should be used
            instead.
    """
    sys.stderr.write(
        "DeprecationWarning: %s.%s is deprecated and will be removed eventually.\n"
        "Please use %s.%s instead.\n" % (clsname, oldname, clsname, newname))


def _log_value(log_func, value, level, indent, suffix=''):
    offset = ' ' * level * indent
    log_func(''.join([offset, str(value), suffix]))


def log_result(log_func, result, level=0, indent=2):
    if isinstance(result, list):
        for item in result:
            log_result(log_func, item, level)
    elif isinstance(result, dict):
        for key, value in result.items():
            _log_value(log_func, key, level, indent, ':')
            log_result(log_func, value, level+1)
    else:
        _log_value(log_func, result, level, indent)
