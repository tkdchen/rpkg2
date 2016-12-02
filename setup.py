#!/usr/bin/python

from setuptools import setup, find_packages


setup(
    name="rpkg",
    version="1.47",
    author="Dennis Gilmore",
    author_email="ausil@fedoraproject.org",
    description=("A python library and runtime script for managing RPM"
                 "package sources in a git repository"),
    license="GPLv2+",
    url="https://fedorahosted.org/rpkg",
    packages=find_packages(),
    scripts=['bin/rpkg'],
    data_files=[('/etc/bash_completion.d', ['etc/bash_completion.d/rpkg.bash']),
                ('/etc/rpkg', ['etc/rpkg/rpkg.conf'])],
    install_requires=['six', 'pycurl', 'cccolutils'],  # + koji, but it's not in PyPI
    tests_require=['nose', 'mock', 'GitPython'],
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
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ),
)
