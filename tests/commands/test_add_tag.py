import os

from . import CommandTestCase


class CommandAddTagTestCase(CommandTestCase):
    def setUp(self):
        super(CommandAddTagTestCase, self).setUp()
        if 'GIT_EDITOR' in os.environ:
            self.old_git_editor = os.environ['GIT_EDITOR']
        else:
            self.old_git_editor = None

    def tearDown(self):
        if self.old_git_editor is not None:
            os.environ['GIT_EDITOR'] = self.old_git_editor
        super(CommandAddTagTestCase, self).tearDown()

    def test_add_tag(self):
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

        # `git tag` will call $EDITOR to ask the user to write a message
        os.environ['GIT_EDITOR'] = ('/usr/bin/python -c "import sys; '
                                    'open(sys.argv[1], \'w\').write(\'%s\')"'
                                    % message)

        cmd.add_tag(tag)

        self.assertEqual(self.get_tags(moduledir), [[tag, message]])

    def test_add_tag_with_message(self):
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

        cmd.add_tag(tag, message=message)

        self.assertEqual(self.get_tags(moduledir), [[tag, message]])

    def test_add_tag_with_message_from_file(self):
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

        message_file = os.path.join(moduledir, 'tag_message')

        with open(message_file, 'w') as f:
            f.write(message)

        cmd.add_tag(tag, file=message_file)

        self.assertEqual(self.get_tags(moduledir), [[tag, message]])

    def test_add_tag_fails_with_existing(self):
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

        cmd.add_tag(tag, message=message)

        # Now add the same tag again
        def raises():
            cmd.add_tag(tag, message='No, THIS is a release')

        self.assertRaises(pyrpkg.rpkgError, raises)

    def test_add_tag_force_replace_existing(self):
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

        cmd.add_tag(tag, message=message)

        # Now add the same tag again by force
        newmessage = 'No, THIS is a release'
        cmd.add_tag(tag, message=newmessage, force=True)

        self.assertEqual(self.get_tags(moduledir), [[tag, newmessage]])

    def test_add_tag_many(self):
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

        self.assertEqual(self.get_tags(moduledir), tags)
