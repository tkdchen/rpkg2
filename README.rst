Introduction
============

This is the rpkg project, which mostly is a python library for dealing with
rpm packaging in a git source control.  pyrpkg is the base library that sites
can subclass to create useful tools.

rpkg now can work with Python 2.6, 2.7, 3.5 and 3.6.

License
=======

Unless otherwise specified, all files are licensed under GPLv2+.
There are parts of koji code in pyrpkg/cli, those parts are licensed
under LGPLv2(.1).  See COPYING-koji for that license statement.

Contribution
============

Welcome to write patches to fix or improve rpkg. All code should work well with
Python 2.6 and 2.7, and compatibility with Python 3 would be a big bonus.
Before you create a PR to propose your changes, make sure

* to sign-off your commits by ``git commit -s``. This serves as a confirmation
  that you have the right to submit your changes. See `Developer Certificate of
  Origin`_ for details.

* pass all test cases by running ``python setup.py test``.

.. _Developer Certificate of Origin: https://developercertificate.org/

More Information
================

See https://pagure.io/rpkg for more information, bug tracking, etc.
