Use kojiprofile
===============

``kojiprofile`` is supported from version 1.50, and ``kojiconfig`` is
deprecated at same time. To migrate to ``kojiprofile``, please follow these
steps below.

* Add ``kojiprofile`` in your application's configuration file. For example,

  ::

    [myapp]
    kojiprofile = koji

* Remove deprecated ``kojiconfig`` from configuration file.

* Replace argument ``kojiconfig`` with ``kojiprofile`` in ``Commands.__init__``.

* Remove argument ``kojiconfig`` from ``Commands.container_build_koji``
  argument list.
