Name:		olpc-pwrlogs
Version:	0.2.1
Release:	1%{?dist}
Summary:	OLPC power log monitors

Group:		System Environment/Base
License:	Public-Domain
Source0:	pwrlogs.tar.gz
BuildRoot:	%(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch: noarch


%description
OLPC power draw loggers.

%prep
%setup -c -n pwrlog_src 


%build


%install
rm -rf $RPM_BUILD_ROOT
%{__install} -D -m 0755 olpc-pwr-log		$RPM_BUILD_ROOT/usr/bin/olpc-pwr-log
%{__install} -D -m 0755 olpc-solar-log		$RPM_BUILD_ROOT/usr/bin/olpc-solar-log
%{__install} -D -m 0755 rtcwake-log		$RPM_BUILD_ROOT/usr/bin/rtcwake-log
%{__install} -D -m 0755 rtcwake-screen-log	$RPM_BUILD_ROOT/usr/bin/rtcwake-screen-log
%{__install} -D -m 0755 process-pwr_log.py	$RPM_BUILD_ROOT/usr/bin/process-pwr_log.py


%clean
rm -rf $RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
/usr/bin/olpc-pwr-log
/usr/bin/olpc-solar-log
/usr/bin/rtcwake-log
/usr/bin/rtcwake-screen-log
/usr/bin/process-pwr_log.py

%changelog

