#!/usr/bin/python -tt
# fedpkg-fixbranches - a script to convert an existing package clone to
#                      the new branch layout.
#                      https://fedoraproject.org/wiki/Dist_Git_Branch_Proposal
#
# Copyright (C) 2011 Red Hat Inc.
# Author(s): Jesse Keating <jkeating@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

import argparse
import os
import sys
import logging
import re
import pyfedpkg
import git
import urllib2

# URL to check to see if we've converted the upstream repos
STATUSURL = 'http://jkeating.fedorapeople.org/reposconverted'

# REGEXES!  SO AWESOME
# This regex is used to find local branches that use a Fedora/EPEL/OLPC
# namespace with a trailing / in the branch name.
# Should match f14/master or f15/user/fred but not f14 or f15
# or f15-user-fred
lbranchre = r'^f\d/|^f\d\d/|^fc\d/|^el\d/|^olpc\d/'

# Add a log filter class
class StdoutFilter(logging.Filter):

    def filter(self, record):
        # If the record level is 20 (INFO) or lower, let it through
        return record.levelno <= logging.INFO

# Add a simple function to print usage, for the 'help' command
def usage(args):
    parser.print_help()

# FUNCTIONS!
def convert(args):
    # This is where the meat of the conversion happens
    # make a git repo
    log.debug('Converting repo from path %s' % args.path)
    repo = git.Repo(args.path)

    # Get the right remotes
    log.debug('Checking for proper Fedora remotes in the repo')
    fedpkg = 'pkgs.*\.fedoraproject\.org\/'
    remotes = [remote.name for remote in repo.remotes if
               re.search(fedpkg, remote.url)]
    if not remotes:
        log.error('Repo has no Fedora remotes')
        sys.exit(1)
    log.debug('Found %s remotes to work on' % len(remotes))

    # Create a dict to hold local branch info
    log.debug('Gathering data about local branches')
    lbranchdict = {}
    branches = [branch for branch in repo.branches if
                re.match(lbranchre, branch.name)]
    for branch in branches:
        # Check to see if we have conflicting branch names from remotes we don't
        # know about
        if not repo.git.config('--get', 'branch.%s.remote' % branch.name) in \
        remotes:
            log.error('Local branch %s conflicts with Fedora namespace,' %
                      branch.name)
            log.error('and users non-Fedora remote %s.' %
                      repo.git.config('--get', 'branch.%s.remote' %
                      branch.name))
            log.error('Please remove/rename the branch and try again')
            sys.exit(1)
        # Dict keys are branch stubs, such as f14 or el5 and the
        # dict value is any branches that have a top path that uses
        # that stub value.
        branchstub = branch.name.split('/')[0]
        lbranchdict.setdefault(branchstub, []).append(branch)

    # Rename local branches
    log.debug('Renaming any local Fedora branches that have "/" in the name')
    for branchset in lbranchdict.keys():
        masterbranch = None
        # Skipping /master rename each branch replacing / with -
        for branch in lbranchdict[branchset]:
            if branch.name == '%s/master' % branchset:
                masterbranch = branch
                continue
            log.info('Renaming %s to %s' % (branch.name,
                                            branch.name.replace('/', '-')))
            if not args.dry_run:
                branch.rename(branch.name.replace('/', '-'))
        if masterbranch:
            # rename <top>/master to <top>
            log.info('Renaming %s to %s' % (masterbranch.name, branchset))
            if not args.dry_run:
                masterbranch.rename(branchset)

    # Loop through the remotes in order to update the local branch data
    # with the proper remote branch names.  If we update any then prune
    # and fetch new data.
    log.debug('Checking for old style branches in a Fedora remote too see '
              'if we should prune branch data')
    branchre = r'refs/heads/(f[0-9]/|f[0-9][0-9]/|fc[0-9]/|el[0-9]/|olpc[0-9]/)'
    for remote in remotes:
        pruned = False
        # Check to see if the remote data matches the old style
        # This regex looks at the ref name which should be "origin/f15/master"
        # or simliar.  This regex fills in the remote name we care about and
        # attempts to find any fedora/epel/olpc branch that has the old style
        # /master tail.
        refsre = r'%s/(f\d\d/master|f\d/master|fc\d/master' % remote
        refsre += r'|el\d/master|olpc\d/master)'
        for ref in repo.refs:
            if type(ref) == git.refs.RemoteReference and \
            re.match(refsre, ref.name):
                log.debug('Found a remote with old style branches: %s' %
                          remote)
                log.info('Pruning branch data from %s' % remote)
                if not args.dry_run:
                    repo.git.remote('prune', remote)
                pruned = True
                break

        # Find the local branches to convert
        log.debug('Looking for local branches tracking %s to update merge '
                  'data' % remote)
        lbranches = [branch for branch in repo.branches if
                     repo.git.config('--get', 'branch.%s.remote' %
                                     branch.name) == remote]
        log.debug('Found %s local branches related to %s' % (len(lbranches),
                                                             remote))
        for branch in lbranches:
            # Get the merge point
            merge = repo.git.config('--get', 'branch.%s.merge' % branch.name)
            # See if we match our regex
            if re.match(branchre, merge):
                # See if we're on the branch "master"
                # This regex should capture any branch that is
                # refs/heads/something/master  but won't match
                # refs/heads/something/else/master
                if re.match(r'refs/heads/[^/]*/master$', merge):
                    # Rename the merge point scraping off /master
                    log.info('Fixing merge point of %s' % branch)
                    log.debug('Changing %s merge point of %s to %s' %
                              (branch, merge, merge.replace('/master', '')))
                    if not args.dry_run:
                        repo.git.config('branch.%s.merge' % branch.name,
                                        merge.replace('/master', ''))
                # Otherwise transpose / for - after refs/heads/
                else:
                    newmerge = 'refs/heads/%s' % \
                                merge.replace('refs/heads/', '').replace('/',
                                                                         '-')
                    log.info('Fixing merge point of %s' % branch)
                    log.debug('Changing %s merge point of %s to %s' %
                              (branch, merge, newmerge))
                    if not args.dry_run:
                        repo.git.config('branch.%s.merge' % branch.name,
                                        newmerge)
        # Now fetch the remote
        if pruned:
            log.info('Fetching remote branch data for %s' % remote)
            if not args.dry_run:
                repo.git.fetch(remote)
    return


def parse_cmdline(generate_manpage = False):
    """Parse the command line"""

    # Create the parser object
    parser = argparse.ArgumentParser(description = 'Fedora Packaging utility',
                                     prog = 'fedpkg-fixbranches')

    # Add top level arguments
    # Let the user define which path to look at instead of pwd
    parser.add_argument('--path', default = None,
                    help='Directory to interact with instead of current dir')
    # Verbosity
    parser.add_argument('-v', action = 'store_true',
                        help = 'Run with verbose debug output')
    parser.add_argument('-q', action = 'store_true',
                        help = 'Run quietly only displaying errors')

    # What would it do?
    parser.add_argument('--dry-run', '-n', action = 'store_true',
                        help = 'Do everything except actually rename the '
                        'branches')

    # Use the force
    parser.add_argument('--force', '-f', action = 'store_true',
                        help = 'Force update even if upstream has not been '
                        'converted')

    # Parse the args
    return parser.parse_args()


# The main code goes here
if __name__ == '__main__':
    args = parse_cmdline()

    # setup the logger -- This logger will take things of INFO or DEBUG and
    # log it to stdout.  Anything above that (WARN, ERROR, CRITICAL) will go
    # to stderr.  Normal operation will show anything INFO and above.
    # Quiet hides INFO, while Verbose exposes DEBUG.  In all cases WARN or
    # higher are exposed (via stderr).
    log = pyfedpkg.log

    if args.v:
        log.setLevel(logging.DEBUG)
    elif args.q:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    # have to create a filter for the stdout stream to filter out WARN+
    myfilt = StdoutFilter()
    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.addFilter(myfilt)
    stdouthandler.setFormatter(formatter)
    stderrhandler = logging.StreamHandler()
    stderrhandler.setLevel(logging.WARNING)
    stderrhandler.setFormatter(formatter)
    log.addHandler(stdouthandler)
    log.addHandler(stderrhandler)

    # Are we using the force?
    if args.force:
        log.warning('WARNING: Using --force is not recommended!')

    # Check to see if the branches have been converted
    log.info('Checking status of upstream branch conversion')
    log.debug('Reading url %s' % STATUSURL)
    try:
        if not urllib2.urlopen(STATUSURL).read() and not args.force:
            log.error('Fedora repos have not yet been converted.')
            sys.exit(1)
    except urllib2.HTTPError, e:
        log.error('Could not check status of conversion from webpage: %s' % e)
        sys.exit(1)

    if not args.path:
        try:
            args.path=os.getcwd()
        except:
            log.error('Could not get current path, have you deleted it?')
            sys.exit(1)

    # Validate the path
    if not os.path.exists(args.path):
        log.error('Invalid path %s' % args.path)
        sys.exit(1)

    if not os.path.exists(os.path.join(args.path, '.git')):
        # We aren't looking at a repo itself, lets see if it's a split out
        # Look for folders that are named like one of ours, and treat each
        # as if it were its own repo (because it kinda is)
        branchdirre = 'f\d\d|f\d|fc\d|olpc\d|el\d|master'
        dirs = [folder for folder in os.listdir(args.path) if
                re.match(branchdirre, folder)]
        if not dirs:
            log.error('%s does not appear to be a valid repo' % args.path)
            sys.exit(1)
        # Loop through the dirs and do the dirty work
        log.info('Found a clone --branches setup, updating each subdir')
        origpath = args.path
        for repo in dirs:
            try:
                args.path = os.path.join(origpath, repo)
                log.info('Working on subdir %s' % repo)
                convert(args)
                log.info('All done with %s' % repo)
            except KeyboardInterrupt:
                pass
        log.info('Completed all conversions')
        sys.exit(0)

    # Run the necessary command
    try:
        convert(args)
        log.info('All done!')
    except KeyboardInterrupt:
        pass
