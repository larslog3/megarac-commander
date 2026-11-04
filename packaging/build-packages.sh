#!/usr/bin/env bash
# Builds distributable packages (.deb, .tar.gz, and Python wheel) in ./dist/
set -euo pipefail

VERSION="1.0.0"
mkdir -p dist

echo "=== 1. Building Portable Tarball (dist/megarac-commander-${VERSION}-linux-any.tar.gz) ==="
tar -czf "dist/megarac-commander-${VERSION}-linux-any.tar.gz" \
    index.html bridge_server.py ModernJViewerBridge.java Dockerfile docker-compose.yml install.sh packaging README.md LICENSE

if command -v dpkg-deb >/dev/null 2>&1; then
    echo "=== 2. Building Debian/Ubuntu Package (dist/megarac-commander_${VERSION}_all.deb) ==="
    DEB_ROOT="$(mktemp -d)"
    mkdir -p "${DEB_ROOT}/DEBIAN"
    mkdir -p "${DEB_ROOT}/opt/megarac-commander"
    mkdir -p "${DEB_ROOT}/usr/local/bin"
    mkdir -p "${DEB_ROOT}/lib/systemd/system"

    cat << EOF > "${DEB_ROOT}/DEBIAN/control"
Package: megarac-commander
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: all
Depends: python3, ipmitool, curl
Recommends: openjdk-8-jdk | default-jdk, icedtea-netx, xvfb, x11vnc, novnc, websockify, fluxbox, xdotool
Maintainer: MegaRAC Commander Contributors <opensource@example.com>
Description: Unified HTML5 iKVM and IPMI 2.0 Control Center for AMI MegaRAC SP
 Replaces the legacy Java JViewer console with a chromeless HTML5 stream,
 extracts native JViewer menus via Swing reflection, and unlocks hidden
 ipmitool fan PWM curves, boot flags, and sensor thresholds.
EOF

    cat << 'EOF' > "${DEB_ROOT}/DEBIAN/postinst"
#!/bin/sh
set -e
if [ -f /usr/share/novnc/vnc_lite.html ] && [ ! -f /usr/share/novnc/vnc_clean.html ]; then
    cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc_clean.html
    sed -i 's/<head>/<head><style>#top_bar{display:none!important;}body,html{margin:0!important;padding:0!important;background:#000!important;overflow:hidden!important;}</style>/' /usr/share/novnc/vnc_clean.html
fi
if command -v javac >/dev/null 2>&1; then
    javac -source 1.8 -target 1.8 /opt/megarac-commander/ModernJViewerBridge.java || true
fi
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
fi
EOF
    chmod 0755 "${DEB_ROOT}/DEBIAN/postinst"

    cp index.html bridge_server.py ModernJViewerBridge.java "${DEB_ROOT}/opt/megarac-commander/"
    cp packaging/systemd/megarac-commander.service "${DEB_ROOT}/lib/systemd/system/"

    cat << 'EOF' > "${DEB_ROOT}/usr/local/bin/megarac-commander"
#!/usr/bin/env bash
exec python3 /opt/megarac-commander/bridge_server.py "$@"
EOF
    chmod 0755 "${DEB_ROOT}/usr/local/bin/megarac-commander"

    dpkg-deb --build "${DEB_ROOT}" "/tmp/megarac-commander_${VERSION}_all.deb" && cp "/tmp/megarac-commander_${VERSION}_all.deb" "dist/megarac-commander_${VERSION}_all.deb" && rm -f "/tmp/megarac-commander_${VERSION}_all.deb"
    rm -rf "${DEB_ROOT}"
fi

echo "=== Done! Packages written to ./dist/ ==="
ls -lh dist/
