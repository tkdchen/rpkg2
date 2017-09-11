# pyrpkg - a Python library for RPM Packagers
#
# Copyright (C) 2017 Red Hat Inc.
# Author(s): Chenxiong Qi <cqi@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from pyrpkg.pkgrepo import PackageRepo
from pyrpkg.errors import rpkgError
from utils import CommandTestCase


class LoadBranchMergeTest(CommandTestCase):
    """Test PackageRepo.load_branch_merge"""

    def setUp(self):
        super(LoadBranchMergeTest, self).setUp()
        self.pkg_repo = PackageRepo(self.cloned_repo_path)

    def test_load_branch_merge_from_eng_rhel_6(self):
        self.checkout_branch(self.pkg_repo.repo, 'eng-rhel-6')
        self.assertEqual(self.pkg_repo.branch_merge, 'eng-rhel-6')

    def test_load_branch_merge_from_eng_rhel_6_5(self):
        """
        Ensure load_branch_merge can work well against a more special branch
        eng-rhel-6.5
        """
        self.checkout_branch(self.pkg_repo.repo, 'eng-rhel-6.5')
        self.assertEqual(self.pkg_repo.branch_merge, 'eng-rhel-6.5')

    def test_load_branch_merge_from_not_remote_merge_branch(self):
        """Ensure load_branch_merge fails against local-branch

        A new local branch named local-branch is created for this test, loading
        branch merge from this local branch should fail because there is no
        configuration item branch.local-branch.merge.
        """
        self.create_branch(self.pkg_repo.repo, 'local-branch')
        self.checkout_branch(self.pkg_repo.repo, 'local-branch')
        try:
            self.pkg_repo.branch_merge
        except rpkgError as e:
            self.assertEqual('Unable to find remote branch.  Use --release', str(e))
        else:
            self.fail("It's expected to raise rpkgError, but not.")
