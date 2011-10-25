# sitelib for noarch packages, sitearch for others (remove the unneeded one)
%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name:           rpkg
Version:        1.7
Release:        1%{?dist}
Summary:        Utility for interacting with rpm+git packaging systems

Group:          Applications/System
License:        GPLv2+ and LGPLv2
URL:            https://fedorahosted.org/rpkg
Source0:        https://fedorahosted.org/releases/r/p/rpkg/rpkg-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

Requires:       python-argparse
Requires:       pyrpkg => %{name}-%{version}

BuildArch:      noarch
BuildRequires:  python-devel, python-setuptools
# We br these things for man page generation due to imports
BuildRequires:  GitPython, koji, python-pycurl
%if 0%{?rhel} < 7
BuildRequires:  python-hashlib
BuildRequires:  python-argparse
BuildRequires:  python-kitchen
%endif

%description
A tool for managing RPM package sources in a git repository.

%package -n pyrpkg
Summary:        Python library for interacting with rpm+git
Group:          Applications/Databases
Requires:       GitPython >= 0.2.0, python-argparse
Requires:       python-pycurl, koji
Requires:       rpm-build, rpm-python
Requires:       rpmlint, mock, curl, openssh-clients, redhat-rpm-config
%if 0%{?rhel} < 7
Requires:       python-kitchen
Requires:       python-hashlib
%endif

%description -n pyrpkg
A python library for managing RPM package sources in a git repository.


%prep
%setup -q


%build
%{__python} setup.py build
%{__python} src/rpkg_man_page.py > rpkg.1


%install
rm -rf $RPM_BUILD_ROOT
%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT
%{__install} -d $RPM_BUILD_ROOT%{_mandir}/man1
%{__install} -p -m 0644 rpkg.1 $RPM_BUILD_ROOT%{_mandir}/man1

 
%clean
rm -rf $RPM_BUILD_ROOT


%files
%config(noreplace) %{_sysconfdir}/rpkg
%{_sysconfdir}/bash_completion.d
%{_bindir}/%{name}
%{_mandir}/*/*

%files -n pyrpkg
%doc COPYING COPYING-koji LGPL README
# For noarch packages: sitelib
%{python_sitelib}/pyrpkg
%{python_sitelib}/rpkg-%{version}-py?.?.egg-info


%changelog
* Tue Oct 25 2011 Jesse Keating <jkeating@redhat.com> - 1.7-1
- Support a manually specified mock root (jkeating)
- Add a mock-config subcommand (jkeating)
- Fix a traceback on error. (jkeating)
- Remove debugging code (jkeating)
- More git api updates (jkeating)
- Add topurl as a koji config and property (jkeating)
- Add a mockconfig property (jkeating)
- Turn the latest commit into a property (jkeating)

* Tue Sep 20 2011 Jesse Keating <jkeating@redhat.com> - 1.6-1
- Allow name property to load by itself (jkeating)

* Mon Sep 19 2011 Jesse Keating <jkeating@redhat.com> - 1.5-1
- Fix tag listing (#717528) (jkeating)
- Revamp n-v-r property loading (#721389) (jkeating)
- Don't use os.getlogin (jkeating)
- Code style changes (jkeating)
- Allow fedpkg lint to be configurable and to check spec file. (pingou)
- Handle non-scratch srpm builds better (jkeating)

* Wed Aug 17 2011 Jesse Keating <jkeating@redhat.com> - 1.4-1
- Be more generic when no spec file is found (jkeating)
- Hint about use of git status when dirty (jkeating)
- Don't use print when we can log.info it (jkeating)
- Don't exit from a library (jkeating)
- Do the rpm query in our module path (jkeating)
- Use git's native ability to checkout a branch (jkeating)
- Use keyword arg with clone (jkeating)
- Allow the on-demand generation of an srpm (jkeating)
- Fix up exit codes (jkeating)

* Mon Aug 01 2011 Jesse Keating <jkeating@redhat.com> - 1.3-1
- Fix a debug string (jkeating)
- Set the right property (jkeating)
- Make sure we have a default hashtype (jkeating)
- Use underscore for the dist tag (jkeating)
- Fix the kojiweburl property (jkeating)

* Wed Jul 20 2011 Jesse Keating <jkeating@redhat.com> - 1.2-1
- Fill out the krb_creds function (jkeating)
- Fix the log message (jkeating)
- site_setup is no longer needed (jkeating)
- Remove some rhtisms (jkeating)
- Wire up the patch command in client code (jkeating)
- Add a patch command (jkeating)

* Fri Jun 17 2011 Jesse Keating <jkeating@redhat.com> - 1.1-2
- Use version macro in files

* Fri Jun 17 2011 Jesse Keating <jkeating@redhat.com> - 1.1-1
- New tarball release with correct license files

* Fri Jun 17 2011 Jesse Keating <jkeating@redhat.com> - 1.0-2
- Fix up things found in review

* Tue Jun 14 2011 Jesse Keating <jkeating@redhat.com> - 1.0-1
- Initial package
