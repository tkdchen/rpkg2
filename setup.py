#!/usr/bin/python

import os
import sys

from setuptools import setup, find_packages


def read_requirements(requirements_file):
    specifiers = []
    dep_links = []

    def read_lines():
        with open(requirements_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line == '' or line.startswith('#') or line.startswith('-r'):
                    continue
                yield line

    for line in read_lines():
        if line.startswith('git+'):
            dep_links.append(line)
        else:
            specifiers.append(line)

    return specifiers, dep_links


setup_py_path = os.path.dirname(os.path.realpath(__file__))
pypi_txt = os.path.join(setup_py_path, 'requirements', 'pypi.txt')
test_pypi_txt = os.path.join(setup_py_path, 'requirements', 'test-pypi.txt')

install_requires, dep_links = read_requirements(pypi_txt)
tests_require, test_dep_links = read_requirements(test_pypi_txt)
dep_links += test_dep_links

ver = sys.version_info
if ver.major <= 2 and ver.minor < 7:
    install_requires.append('argparse==1.4.0')
    tests_require.append('unittest2')


setup(
    name="rpkg",
    version="1.51",
    author="Dennis Gilmore",
    author_email="ausil@fedoraproject.org",
    description=("A python library and runtime script for managing RPM"
                 "package sources in a git repository"),
    license="GPLv2+",
    url="https://pagure.io/rpkg",
    packages=find_packages(),
    install_requires=install_requires,
    tests_require=tests_require,
    dependency_links=dep_links,
    test_suite='nose.collector',
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
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ),
)
