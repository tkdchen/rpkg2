# -*- coding: utf-8 -*-
import six

from . import CommandTestCase


class CommandPatchTestCase(CommandTestCase):
    def setUp(self):
        super(CommandPatchTestCase, self).setUp()
        self.text_ascii = "Lorem ipsum dolor sit amet, consectetur elit.\n" \
            "Sed vel enim nec tortor posuere sodales sit amet mauris.\n" \
            "Duis ipsum dui, consectetur pretium a, vestibulum.\n"\
            "Nunc vel consectetur libero. Aenean , metus quis posuere\n" \
            "vulputate, purus metus fringilla, sit amet interdum tellus\n"
        self.text_utf8 = "ěšč\n" \
                         "ščř\n" \
                         "ýáí"
        if six.PY3:
            self.text_utf8 = self.text_utf8.encode("utf-8")

    def test_byte_offset_first_line(self):
        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        line, offset = cmd._byte_offset_to_line_number(self.text_ascii, 10)
        # 10 byte offset mean line 1 and character 11
        self.assertEqual(line, 1)
        self.assertEqual(offset, 11)

    def test_byte_offset_next_line(self):
        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)

        line, offset = cmd._byte_offset_to_line_number(self.text_ascii, 46)
        # 46 byte offset is first character on second line
        self.assertEqual(line, 2)
        self.assertEqual(offset, 1)

    def test_byte_offset_utf8(self):
        import pyrpkg
        cmd = pyrpkg.Commands(self.path, self.lookaside, self.lookasidehash,
                              self.lookaside_cgi, self.gitbaseurl,
                              self.anongiturl, self.branchre, self.kojiprofile,
                              self.build_client, self.user, self.dist,
                              self.target, self.quiet)
        text = self.text_utf8.decode('UTF-8', 'ignore')
        line, offset = cmd._byte_offset_to_line_number(text, 9)
        # 9 byte offset mean line 3 and second character
        self.assertEqual(line, 3)
        self.assertEqual(offset, 2)
