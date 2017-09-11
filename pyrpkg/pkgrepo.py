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

import git
import logging
import six

from six.moves import urllib
from pyrpkg.errors import rpkgError

# TODO: move operations on tag into class PackageRepo


logger = logging.getLogger(__name__)


class GitProxy(object):
    """Proxy to underlying git repository

    This is used for callers to interact with underlying repository from
    outside of PackageRepo.
    """

    def __init__(self, repo):
        self._repo = repo

    def get_config(self, name):
        return self._repo.git.config('--get', name)

    def checkout(self, *args, **kwargs):
        return self._repo.git.checkout(*args, **kwargs)

    def ls_files(self, *args, **kwargs):
        return self._repo.git.ls_files(*args, **kwargs)

    def describe(self, *args, **kwargs):
        return self._repo.git.describe(*args, **kwargs)

    def diff(self, *args, **kwargs):
        return self._repo.git.diff(*args, **kwargs)

    def log(self, *args, **kwargs):
        return self._repo.git.log(*args, **kwargs)

    def status(self, *args, **kwargs):
        return self._repo.git.status(*args, **kwargs)

    def rev_list(self, *args, **kwargs):
        return self._repo.git.rev_list(*args, **kwargs)


class PackageRepo(object):
    """Represent a package repository"""

    def __init__(self, path,
                 default_branch_remote='origin',
                 overwritten_branch_merge=None):
        self._path = path
        self._repo = git.Repo(path)
        self._default_branch_remote = default_branch_remote

        self._branch_merge = None
        if overwritten_branch_merge:
            self._branch_merge = overwritten_branch_merge

        self._branch_remote = None
        self._push_url = None
        self._commit = None

    @property
    def path(self):
        return self._path

    @property
    def repo(self):
        return self._repo

    @property
    def git(self):
        return GitProxy(self.repo)

    @property
    def active_branch(self):
        return self._repo.active_branch

    @property
    def branch_merge(self):
        """This property ensures the branch attribute"""
        if not self._branch_merge:
            self.load_branch_merge()
        return self._branch_merge

    def load_branch_merge(self):
        """Find the remote tracking branch from the branch we're on.

        The goal of this function is to catch if we are on a branch we can make
        some assumptions about.  If there is no merge point then we raise and
        ask the user to specify.

        NOTE: do not handle default branch merge. Command line option --release
              overrides return value from this method, which should be handled
              in caller side.
        """
        try:
            local_branch = self.repo.active_branch.name
        except TypeError as e:
            raise rpkgError('Repo in inconsistent state: %s' % e)
        try:
            merge = self.git.get_config(
                'branch.{0}.merge'.format(local_branch))
        except git.GitCommandError:
            raise rpkgError('Unable to find remote branch.  Use --release')
        # Trim off the refs/heads so that we're just working with
        # the branch name
        merge = merge.replace('refs/heads/', '', 1)
        self._branch_merge = merge

    @property
    def branch_remote(self):
        """This property ensures the branch_remote attribute"""
        if not self._branch_remote:
            self.load_branch_remote()
        return self._branch_remote

    def load_branch_remote(self):
        """Find the name of remote from branch we're on."""

        try:
            remote = self.git.get_config(
                'branch.%s.remote' % self.branch_merge)
        except (git.GitCommandError, rpkgError) as e:
            remote = self._default_branch_remote
            logger.debug("Could not determine the remote name: %s", str(e))
            logger.debug("Falling back to default remote name '%s'", remote)

        self._branch_remote = remote

    @property
    def push_url(self):
        """This property ensures the push_url attribute"""
        if not self._push_url:
            self.load_push_url()
        return self._push_url

    def load_push_url(self):
        """Find the pushurl or url of remote of branch we're on."""
        try:
            url = self.repo.git.remote('get-url', '--push', self.branch_remote)
        except git.GitCommandError as e:
            try:
                url = self.git.get_config(
                    'remote.%s.pushurl' % self.branch_remote)
            except git.GitCommandError:
                try:
                    url = self.git.get_config(
                        'remote.%s.url' % self.branch_remote)
                except git.GitCommandError as e:
                    raise rpkgError('Unable to find remote push url: {0}'.format(e))
        if isinstance(url, six.text_type):
            # GitPython >= 1.0 return unicode. It must be encoded to string.
            self._push_url = url
        else:
            self._push_url = url.decode( 'utf-8')

    def check(self, is_dirty=True, all_pushed=True):
        """Check various status of current repository

        :param bool is_dirty: Default to True. To check whether there is
            uncommitted changes.
        :param bool all_pushed: Default to True. To check whether all changes
            are pushed.
        :raises rpkgError: if any unexpected status is detected. For example,
            if changes are not committed yet.

        NOTE: has_namespace is removed because it should belong to package
              metadata and be handled there using package repository information
              provided by this module.
        """
        if is_dirty:
            if self.repo.is_dirty():
                raise rpkgError('%s has uncommitted changes.  Use git status '
                                'to see details' % self.path)

        get_config = self.git.get_config
        if all_pushed:
            branch = self.repo.active_branch
            try:
                remote = get_config('branch.%s.remote' % branch)
                merge = get_config('branch.%s.merge' % branch).replace(
                    'refs/heads', remote)
            except git.GitCommandError:
                raise rpkgError(
                    'Branch {0} does not track remote branch.\n'
                    'Use the following command to fix that:\n'
                    '    git branch -u origin/REMOTE_BRANCH_NAME'.format(branch))
            if self.git.rev_list('%s...%s' % (merge, branch)):
                raise rpkgError('There are unpushed changes in your repo')

    @property
    def commit_hash(self):
        """This property ensures the commit attribute"""
        if not self._commit:
            self.load_commit()
        return self._commit

    def load_commit(self):
        """Discover the latest commit to the package"""
        comobj = six.next(self.repo.iter_commits())
        # Work around different versions of GitPython
        if hasattr(comobj, 'sha'):
            self._commit = comobj.sha
        else:
            self._commit = comobj.hexsha

    def fetch_remotes(self):
        """Fetch from all remotes"""
        for remote in self.repo.remotes:
            self.repo.git.fetch(remote)

    def list_branches(self):
        """Returns a tuple of local and remote branch names"""
        refs = self.repo.refs
        # Sort into local and remote branches
        remote_branches = []
        local_branches = []
        for ref in refs:
            if type(ref) == git.Head:
                logger.debug('Found local branch %s', ref.name)
                local_branches.append(ref.name)
            elif type(ref) == git.RemoteReference:
                if ref.remote_head == 'HEAD':
                    logger.debug('Skipping remote branch alias HEAD')
                    continue  # Not useful in this context
                logger.debug('Found remote branch %s', ref.name)
                remote_branches.append(ref.name)
        return local_branches, remote_branches

    # Properties and methods that belongs to git.Repo
    # These ensures original cmd.repo.* works

    @property
    def heads(self):
        return self.repo.heads

    @property
    def index(self):
        return self.repo.index

    @property
    def git_dir(self):
        # TODO: replaced with self.path?
        return self.repo.git_dir

    def is_dirty(self):
        return self.repo.is_dirty()

    def iter_commits(self):
        return self._repo.iter_commits()
