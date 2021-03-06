ChangeLog
=========

1.51 (2017-10-20)
-----------------

- Do not read real koji config in test (cqi)
- Ignore TestModulesCli if openidc-client is unavailable (cqi)
- Port mbs-build to rpkg (mprahl)
- Add .vscode to .gitignore (mprahl)
- Fix TestPatch.test_rediff in order to run with old version of mock (cqi)
- Allow to specify alternative Copr config file - #184 (cqi)
- Tests for patch command (cqi)
- More Tests for mockbuild command (cqi)
- More tests for getting spec file (cqi)
- Tests for container-build-setup command (cqi)
- Test for container-build to use custom config (cqi)
- Suppress output from git command within setUp (cqi)
- Skip test if rpmfluff is not available (lsedlar)
- Allow to override build URL (cqi)
- Test for mock-config command (cqi)
- Tests for copr-build command (cqi)
- Fix arch-override for container-build (lucarval)
- Remove unsupported osbs for container-build (lucarval)
- cli: add --arches support for koji_cointainerbuild (mlangsdo)
- Strip refs/heads/ from branch only once (lsedlar)
- Don't install bin and config files (cqi)
- Fix kojiprofile selection in cliClient.container_build_koji (cqi)
- Avoid branch detection for 'rpkg sources' (praiskup)
- Fix encoding in new command (cqi)
- Minor wording improvement in help (pgier)
- Fix indentation (pviktori)
- Add --with and --without options to mockbuild (pviktori)

v1.50 (2017-08-01)
------------------

- Fix PEP8 error (cqi)
- Spelling fixes (ville.skytta)
- Reword help and description of new-sources and upload commands - 1248737
  (cqi)
- Set autorebuild enabled by default (bfontecc)
- Add commands to whitelist_externals (cqi)
- Declare Python 3 versions to support in setup.py (cqi)
- Replace unicode with six.text_type (cqi)
- Run tests in both Python 2 and 3 with tox (cqi)
- Make tests and covered code compatible with Py3 (cqi)
- Add requirements files (cqi)
- Do not build srpm in test (cqi)
- Do not actually run git-diff in tests (cqi)
- Remove deprecated modules used in koji (cqi)
- Non-zero exit when rpmbuild fails in local command (cqi)
- Report deprecation of config via logger (lsedlar)
- Print --dist deprecation warning explicitly (lsedlar)
- utils: Avoid DeprecationWarning for messages for users (lsedlar)
- Supply namespace to lookaside (if enabled) (lsedlar)
- Support reading koji config from profile - #187 (cqi)
- Remove kitchen (cqi)
- Fix string format (cqi)
- Recommend --release instead of --dist in mockbuild --help (tmz)
- Allow overriding container build target by downstream (lsedlar)
- Add a separate property for namespace (lsedlar)
- Allow container builds from any namespace (maxamillion)
- Make osbs support optional (cqi)
- make osbs dependency optional (pavlix)
- Allow explicit namespaces with slashes (lsedlar)
- Do not hang indefinitely when lookaside cache server stops sending data
  (jkaluza)
- Make --module-name work with namespaces - #216 (lsedlar)
- Include README.rst in dist package (cqi)
- More document in README - #189 (cqi)
- Make new command be able to print unicode - #205 (cqi)
- Allow to specify custom info to a dummy commit (cqi)
- Load module name correctly even if push url ends in slash - #192 (cqi)
- Replace fedorahosted.org with pagure.io - #202 (cqi)
- Fix rpm command to get changelog from SPEC - rhbz#1412224 (cqi)
- Rewrite tests to avoid running rpmbuild and rpmlint (cqi)
- Use fake value to make Command in test (cqi)
- Python 3.6 invalid escape sequence deprecation fixes (ville.skytta)

v1.49 (2017-02-22)
------------------

- More upload PyCURL fixes for EL 7 (merlin)
- Move tag inheritance check into a separate method (cqi)

v1.48 (2016-12-22)
------------------

- Better message when fail to authenticate via Kerberos - #180 (cqi)

v1.47 (2016-12-15)
------------------

- Refactor Commands._srpmdetails
- Add missing import koji.ssl.SSLCommon - BZ#1404102 (cqi)
- Fix upload with old PyCURL - BZ#1241059 (lsedlar)
- Default krb_rdns to None (lsedlar)
- Add missing krb_rdns in default Koji config (cqi)
- Coerce the distgit_namespaced config option to a boolean - #74 (merlinthp)
- We need krb_rdns (puiterwijk)
- Fix wrong _has_krb_creds name (cqi)
- Warning if repo is an old checkout - #148 (cqi)
- Pass byte string to pycurl setopt (cqi)
- Refine Kerberos with cccolutils (cqi)
- Refactor load_kojisession - #107 (cqi)
- Call cliClient.sources from mockbuild (cqi)
- Give hint to scratch-build when build from local changes - BZ#841516 (cqi)
- Hint for fixing nontracking branch - BZ#1325775 (cqi)
- Fix using undefined variable (lsedlar)
- Read kerberos realms from config file (lsedlar)
- Make rpmbuild run with local en_US.UTF-8 in tests (cqi)
- Append fixed issue ids to each changelog - #85 (cqi)
- Dont show merge commits (cqi)
- Swtich to using CCColUtils to determine username from krb realms (puiterwijk)
- Use fake user info to config repository in tests (cqi)
- Remove unnecessary touch method (cqi)
- Fix setUp of TestImportSrpm for EL6 (cqi)
- Add tests for import_srpm (cqi)
- Tests for lookaside related commands (cqi)
- More tests to Commands and cliClient (cqi)
- Remove unused code (cqi)
- Fix tests for running tests in Copr (cqi)
- Replace nopep8 with noqa (cqi)
- Fix manpage generator (cqi)
- Backwards compatible with krbV - #139 (cqi)
- Add missing -q option to rpm command (cqi)
- Fix tests (cqi)
- python3: fix container usage (pavlix)
- python3: fix string types (pavlix)
- python3: fix configparser usage (pavlix)
- Recommend --release instead of --dist (cqi)
- More test cases for cli commands (cqi)
- Better clog - #135 (cqi)
- Avoid sys.exit in cliClient - #102 (cqi)
- Add --release to bash completion (cqi)
- Replace krbV with python-gssapi - #133 (cqi)
- Enusre to download sources in cliClient (cqi)
- New --release option (cqi)
- Commit -c should clean up after itself. - #16 (qwan)
- New option name '--mock-config' for mockbuild's '--root' - BZ#714726 (qwan)
- Allow using gssapi for lookaside caches (puiterwijk)
- Give upload its own command (cqi)
- Add docstring to check_repo (cqi)
- Add a description for the srpm and sources subcommands (pgier)
- Avoid formatting string in logging method call (cqi)
- New source code layout (cqi)
- Integration between setuptools and nosetests (cqi)
- Fix PEP8 errors (cqi)
- container-build: use correct parameter for git branch (vrutkovs)
- Avoid format string manually when call logger method (cqi)
- Remove deprecated methods (cqi)
- Show useful message when command new fails - #84 (cqi)
- Simplify _run_command (cqi)
- Output both stdout and stderr when not in tty (cqi)
- Remove downloaded invalid file - #79 (cqi)
- Fix description of verify-files - BZ#1203757 (cqi)
- Fix check unpushed changes in check_repo - BZ#1169663 (cqi)
