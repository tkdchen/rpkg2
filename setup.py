#!/usr/bin/python
import sys

from setuptools import setup, Command
try:
    from unittest import TestLoader, TextTestRunner
except ImportError:
    from unittest2 import TestLoader, TextTestRunner


class DiscoverTest(Command):
    user_options = []

    def run(self):
        loader = TestLoader()
        suite = loader.discover(start_dir='test')
        runner = TextTestRunner()
        result = runner.run(suite)
        if not result.wasSuccessful():
            sys.exit(1)

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

setup(
    name="rpkg",
    version="1.28",
    author="Dennis Gilmore",
    author_email="ausil@fedoraproject.org",
    description=("A python library and runtime script for managing RPM"
                 "package sources in a git repository"),
    license="GPLv2+",
    url="https://fedorahosted.org/rpkg",
    package_dir={'': 'src'},
    packages=['pyrpkg'],
    scripts=['src/rpkg'],
    data_files=[('/etc/bash_completion.d', ['src/rpkg.bash']),
                ('/etc/rpkg', ['src/rpkg.conf'])],
    cmdclass={'test': DiscoverTest},
    classifiers=(
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2 :: Only',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ),
)
