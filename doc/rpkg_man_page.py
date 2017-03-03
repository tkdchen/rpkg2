# Print a man page from the help texts.
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.


import os
import sys
import datetime


# We could substitute the "" in .TH with the rpkg version if we knew it
man_header = """\
.\\" man page for rpkg
.TH rpkg 1 "%(today)s" "" "rpm\\-packager"
.SH "NAME"
rpkg \\- RPM Packaging utility
.SH "SYNOPSIS"
.B "rpkg"
[
.I global_options
]
.I "command"
[
.I command_options
]
[
.I command_arguments
]
.br
.B "rpkg"
.B "help"
.br
.B "rpkg"
.I "command"
.B "\\-\\-help"
.SH "DESCRIPTION"
.B "rpkg"
is a script to interact with the RPM Packaging system.
"""

man_footer = """\
.SH "SEE ALSO"
.UR "https://pagure.io/rpkg/"
.BR "https://pagure.io/rpkg/"
"""


class ManFormatter(object):

    def __init__(self, man):
        self.man = man

    def write(self, data):
        for line in data.split('\n'):
            self.man.write('  %s\n' % line)


def strip_usage(s):
    """Strip "usage: " string from beginning of string if present"""
    if s.startswith('usage: '):
        return s.replace('usage: ', '', 1)
    else:
        return s


def man_constants():
    """Global constants for man file templates"""
    today = datetime.date.today()
    today_manstr = today.strftime(r'%Y\-%m\-%d')
    return {'today': today_manstr}


def generate(parser, subparsers):
    """\
    Generate the man page on stdout

    Given the argparse based parser and subparsers arguments, generate
    the corresponding man page and write it to stdout.
    """

    # Not nice, but works: Redirect any print statement output to
    # stderr to avoid clobbering the man page output on stdout.
    man_file = sys.stdout
    sys.stdout = sys.stderr

    mf = ManFormatter(man_file)

    choices = subparsers.choices
    k = sorted(choices.keys())

    man_file.write(man_header % man_constants())

    helptext = parser.format_help()
    helptext = strip_usage(helptext)
    helptextsplit = helptext.split('\n')
    helptextsplit = [line for line in helptextsplit
                     if not line.startswith('  -h, --help')]

    man_file.write('.SS "%s"\n' % ("Global Options",))

    outflag = False
    for line in helptextsplit:
        if line == "optional arguments:":
            outflag = True
        elif line == "":
            outflag = False
        elif outflag:
            man_file.write("%s\n" % line)

    help_texts = {}
    for pa in subparsers._choices_actions:
        help_texts[pa.dest] = getattr(pa, 'help', None)

    man_file.write('.SH "COMMAND OVERVIEW"\n')

    for command in k:
        cmdparser = choices[command]
        if not cmdparser.add_help:
            continue
        usage = cmdparser.format_usage()
        usage = strip_usage(usage)
        usage = ''.join(usage.split('\n'))
        usage = ' '.join(usage.split())
        if help_texts[command]:
            man_file.write('.TP\n.B "%s"\n%s\n' % (usage, help_texts[command]))
        else:
            man_file.write('.TP\n.B "%s"\n' % (usage))

    man_file.write('.SH "COMMAND REFERENCE"\n')
    for command in k:
        cmdparser = choices[command]
        if not cmdparser.add_help:
            continue

        man_file.write('.SS "%s"\n' % cmdparser.prog)

        help = help_texts[command]
        if help and not cmdparser.description:
            if not help.endswith('.'):
                help = "%s." % help
            cmdparser.description = help

        h = cmdparser.format_help()
        mf.write(h)

    man_file.write(man_footer)


if __name__ == '__main__':
    module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, module_path)

    import pyrpkg.cli
    client = pyrpkg.cli.cliClient(name='rpkg', config=None)
    generate(client.parser, client.subparsers)
