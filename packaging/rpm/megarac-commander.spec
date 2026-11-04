Name:           megarac-commander
Version:        1.0.0
Release:        1%{?dist}
Summary:        Unified HTML5 iKVM & IPMI 2.0 Control Center for AMI MegaRAC SP
License:        MIT
URL:            https://github.com/YOUR_USERNAME/megarac-commander
BuildArch:      noarch
Requires:       python3, ipmitool, curl

%description
Replaces the legacy AMI MegaRAC SP Java JViewer console with a chromeless HTML5
stream, extracts native JViewer menus via Swing reflection, and unlocks hidden
ipmitool fan PWM curves, boot flags, and sensor thresholds.

%install
mkdir -p %{buildroot}/opt/megarac-commander
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/lib/systemd/system
cp index.html bridge_server.py ModernJViewerBridge.java %{buildroot}/opt/megarac-commander/
cp packaging/systemd/megarac-commander.service %{buildroot}/usr/lib/systemd/system/
cat << 'EOF' > %{buildroot}/usr/bin/megarac-commander
#!/usr/bin/env bash
exec python3 /opt/megarac-commander/bridge_server.py "$@"
EOF
chmod 0755 %{buildroot}/usr/bin/megarac-commander

%files
/opt/megarac-commander/*
/usr/bin/megarac-commander
/usr/lib/systemd/system/megarac-commander.service
