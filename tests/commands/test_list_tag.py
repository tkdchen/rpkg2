import os

from . import CommandTestCase


class CommandListTagTestCase(CommandTestCase):
    def test_list_tag_no_tags(self):
        self.make_new_git(self.module)

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

        with self.hijack_stdout() as out:
            cmd.list_tag()

        self.assertEqual(out.read().strip(), '')

    def test_list_tag_many(self):
        self.make_new_git(self.module)

        tags = [['v1.0', 'This is a release'],
                ['v2.0', 'This is another release']]

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

        for tag, message in tags:
            cmd.add_tag(tag, message=message)

        with self.hijack_stdout() as out:
            cmd.list_tag()

        result = out.read().strip().split('\n')

        self.assertEqual(result, [t for (t, m) in tags])

    def test_list_tag_specific(self):
        self.make_new_git(self.module)

        tags = [['v1.0', 'This is a release'],
                ['v2.0', 'This is another release']]

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

        for tag, message in tags:
            cmd.add_tag(tag, message=message)

        with self.hijack_stdout() as out:
            cmd.list_tag(tagname='v1.0')

        result = out.read().strip().split('\n')

        self.assertEqual(result, ['v1.0'])

    def test_list_tag_inexistent(self):
        self.make_new_git(self.module)

        tags = [['v1.0', 'This is a release'],
                ['v2.0', 'This is another release']]

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

        for tag, message in tags:
            cmd.add_tag(tag, message=message)

        with self.hijack_stdout() as out:
            cmd.list_tag(tagname='v1.1')

        result = out.read().strip().split('\n')

        self.assertEqual(result, [''])

    def test_list_tag_glob(self):
        self.make_new_git(self.module)

        tags = [['v1.0', 'This is a release'],
                ['v2.0', 'This is another release']]

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

        for tag, message in tags:
            cmd.add_tag(tag, message=message)

        with self.hijack_stdout() as out:
            cmd.list_tag(tagname='v1*')

        result = out.read().strip().split('\n')

        self.assertEqual(result, ['v1.0'])

    def test_list_tag_wildcard(self):
        self.make_new_git(self.module)

        tags = [['v1.0', 'This is a release'],
                ['v2.0', 'This is another release']]

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

        for tag, message in tags:
            cmd.add_tag(tag, message=message)

        with self.hijack_stdout() as out:
            cmd.list_tag(tagname='*')

        result = out.read().strip().split('\n')

        self.assertEqual(result, [t for (t, m) in tags])
