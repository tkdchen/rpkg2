import os
import shutil
import tempfile

import git
import subprocess

from . import CommandTestCase


SPECFILE_TEMPLATE="""Name:           test
Version:        1.0
Release:        1.0
Summary:        test

Group:          Applications/System
License:        GPLv2+

%s

%%description
Test

%%install
rm -f $RPM_BUILD_ROOT%%{_sysconfdir}/"""

CLONE_CONFIG = '''
    bz.default-component %(module)s
    sendemail.to %(module)s-owner@fedoraproject.org
'''
class CommandPushTestCase(CommandTestCase):
    def test_push_without_patches(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        specfile_path = self.module + ".spec"

        # specfile with no patches
        with open(specfile_path, 'w') as specfile:
            specfile.write(SPECFILE_TEMPLATE % "")
            specfile.close()

        try:
            cmd.push()
        except pyrpkg.rpkgError:
            self.fail("No unpushed patches. This shouldn't raise exception")


    def test_push_one_uncommitted_patch(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        specfile_path = self.module + ".spec"

        # add uncommitted patch
        with open(specfile_path, 'w') as specfile:
            specfile.write(SPECFILE_TEMPLATE % "Patch: test.patch")
            specfile.close()

        with open("test.patch", 'w') as f:
            f.close()

        def raises():
            cmd.push()

        self.assertRaises(pyrpkg.rpkgError, raises)

    def test_push_uncommitted_patch_with_force_option(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        specfile_path = self.module + ".spec"

        with open(specfile_path, 'w') as specfile:
            specfile.write(SPECFILE_TEMPLATE % "Patch: test.patch")
            specfile.close()

        with open("test.patch", 'w') as f:
            f.close()

        # Don't check uncommitted patches
        try:
            cmd.push(force=True)
        except pyrpkg.rpkgError:
            self.fail("No unpushed patches. This shouldn't raise exception")

    def test_push_committed_patch(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        specfile_path = self.module + ".spec"

        # add patch and commit it
        patch = "test.patch"
        with open(specfile_path, 'w') as specfile:
            specfile.write(SPECFILE_TEMPLATE % ("Patch: %s" % patch))
            specfile.close()

        with open("test.patch", 'w') as f:
            f.close()

        cmd.repo.index.add([specfile_path, patch])
        cmd.repo.index.commit("add Patch")

        try:
            cmd.push()
        except pyrpkg.rpkgError:
            self.fail("No unpushed patches. This shouldn't raise exception")

    def test_push_part_committed_patches(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        specfile_path = self.module + ".spec"

        # add two patches and commit only one
        patch = "test.patch"
        patch2 = "test2.patch"

        with open(specfile_path, 'w') as specfile:
            specfile.write(SPECFILE_TEMPLATE % ("Patch: %s\nPatch1: %s" %
                                                (patch, patch2)))
            specfile.close()

        with open(patch, 'w') as f:
            f.close()
        with open(patch2, 'w') as f:
            f.close()

        # add only one patch
        cmd.repo.index.add([specfile_path, patch])
        cmd.repo.index.commit("add Patch")

        def raises():
            cmd.push()

        self.assertRaises(pyrpkg.rpkgError, raises)
