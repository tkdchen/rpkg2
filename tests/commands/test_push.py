# -*- coding: utf-8 -*-

import os
import git

from . import CommandTestCase


SPECFILE_TEMPLATE = """Name:           test
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

    def setUp(self):
        # Tests within this case would change working directory. Changing back
        # to original directory to avoid any potential problems.
        self.original_dir = os.path.abspath(os.curdir)
        super(CommandPushTestCase, self).setUp()

    def tearDown(self):
        os.chdir(self.original_dir)
        super(CommandPushTestCase, self).tearDown()

    def test_push_outside_repo(self):
        """push from outside repo with --path option"""

        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside,
                              self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone_config = CLONE_CONFIG
        cmd.clone(self.module, anon=True)
        cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        spec_file = 'module.spec'
        with open(spec_file, 'w') as f:
            f.write(SPECFILE_TEMPLATE % '')

        cmd.repo.index.add([spec_file])
        cmd.repo.index.commit("add SPEC")

        # Now, change directory to parent and test the push
        os.chdir(self.path)
        cmd.push()


class TestPushWithPatches(CommandTestCase):

    def setUp(self):
        super(TestPushWithPatches, self).setUp()

        self.make_new_git(self.module)

        import pyrpkg
        self.cmd = pyrpkg.Commands(self.path, self.lookaside,
                                   self.lookasidehash,
                                   self.lookaside_cgi, self.gitbaseurl,
                                   self.anongiturl, self.branchre,
                                   self.kojiprofile,
                                   self.build_client, self.user, self.dist,
                                   self.target, self.quiet)
        self.cmd.clone_config = CLONE_CONFIG
        self.cmd.clone(self.module, anon=True)
        self.cmd.path = os.path.join(self.path, self.module)
        os.chdir(os.path.join(self.path, self.module))

        # Track SPEC and a.patch in git
        spec_file = 'module.spec'
        with open(spec_file, 'w') as f:
            f.write(SPECFILE_TEMPLATE % '''Patch0: a.patch
Patch1: b.path
Patch2: c.path
Patch3: d.path
''')

        for patch_file in ('a.patch', 'b.patch', 'c.patch', 'd.patch'):
            with open(patch_file, 'w') as f:
                f.write(patch_file)

        # Track c.patch in sources
        from pyrpkg.sources import SourcesFile
        sources_file = SourcesFile(self.cmd.sources_filename,
                                   self.cmd.source_entry_type)
        file_hash = self.cmd.lookasidecache.hash_file('c.patch')
        sources_file.add_entry(self.cmd.lookasidehash, 'c.patch', file_hash)
        sources_file.write()

        self.cmd.repo.index.add([spec_file, 'a.patch', 'sources'])
        self.cmd.repo.index.commit('add SPEC and patches')

    def test_find_untracked_patches(self):
        untracked_patches = self.cmd.find_untracked_patches()
        untracked_patches.sort()
        self.assertEqual(['b.patch', 'd.patch'], untracked_patches)

    def test_push_not_blocked_by_untracked_patches(self):
        self.cmd.push()

        # Verify added files are pushed to origin
        origin_repo_path = self.cmd.repo.git.config(
            '--get', 'remote.origin.url').replace('file://', '')
        origin_repo = git.Repo(origin_repo_path)
        git_tree = origin_repo.head.commit.tree
        self.assertTrue('a.patch' in git_tree)
        self.assertTrue('b.patch' not in git_tree)
        self.assertTrue('c.patch' not in git_tree)
        self.assertTrue('d.patch' not in git_tree)

        sources_content = origin_repo.git.show('master:sources').strip()
        with open('sources', 'r') as f:
            expected_sources_content = f.read().strip()
        self.assertEqual(expected_sources_content, sources_content)
