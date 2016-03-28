import os

from . import CommandTestCase


class CommandPackageNameTestCase(CommandTestCase):
    def test_name_is_not_unicode(self):
        self.make_new_git(self.module)

        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiconfig,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        cmd.clone(self.module, anon=True)

        moduledir = os.path.join(self.path, self.module)
        cmd.path = moduledir

        # pycurl can't handle unicode variable
        # module_name needs to be string
        self.assertNotEqual(type(cmd.module_name), unicode)
        self.assertEqual(type(cmd.module_name), str)
