import os

from . import CommandTestCase


class CommandDeleteTagTestCase(CommandTestCase):
    def test_delete_tag(self):
        self.make_new_git(self.module)

        tag = 'v1.0'
        message = 'This is a release'

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, self.module)
        cmd.path = moduledir
        self.config_repo(cmd.path)

        # First, add a tag
        cmd.add_tag(tag, message=message)
        self.assertEqual(self.get_tags(moduledir), [[tag, message]])

        # Now delete it
        cmd.delete_tag(tag)
        tags = [t for (t, m) in self.get_tags(moduledir)]
        self.assertFalse(tag in tags)

    def test_delete_tag_fails_inexistent(self):
        self.make_new_git(self.module)

        tag = 'v1.0'

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, self.module)
        cmd.path = moduledir
        self.config_repo(cmd.path)

        # Try deleting an inexistent tag
        def raises():
            cmd.delete_tag(tag)
        self.assertRaises(pyrpkg.rpkgError, raises)
