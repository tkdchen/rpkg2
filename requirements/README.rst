Requirements
============

* fedora-py2.txt: contains Python 2 packages that are required to run rpkg and
  tests, those are needed to be installed via package manager.

* fedora-py3.txt: contains Python 3 packages that are required to run rpkg and
  tests, those are needed to be installed via package manager.

* pypi.txt: contains Python packages that can be installed from PyPI via
  ``pip``. Some of required packages are not available in PyPI as of writing
  this README file. They has to be installed from package manager too.

* fedora-cli-tools.txt: contains command line tools that rpkg executes them in
  various commands, e.g. rpmlint, rpmbuild and mock.