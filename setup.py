import os
import subprocess
from setuptools import setup, command

setup(
    name = "rpkg",
    version = "1.20",
    author = "Jesse Keating",
    author_email = "jkeating@redhat.com",
    description = ("A python library and runtime script for managing RPM"
                                   "package sources in a git repository"),
    license = "GPLv2+",
    url = "https://fedorahosted.org/rpkg",
    package_dir = {'': 'src'},
    packages = ['pyrpkg'],
    scripts = ['src/rpkg'],
    data_files = [('/etc/bash_completion.d', ['src/rpkg.bash']),
                  ('/etc/rpkg', ['src/rpkg.conf'])],
)
