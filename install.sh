#!/usr/bin/env bash
# Universal Linux Installer for MegaRAC Commander (Debian/Ubuntu, Fedora/RHEL, Arch, openSUSE)
set -euo pipefail

echo "=== Installing MegaRAC Commander System Dependencies ==="
if command -v apt-get >/dev/null 2>&1; then
    sudo dpkg --add-architecture i386 || true
    sudo apt-get update
    sudo apt-get install -y python3 ipmitool curl ca-certificates openjdk-8-jdk icedtea-netx xvfb x11vnc novnc websockify fluxbox xterm xdotool
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 ipmitool curl ca-certificates java-1.8.0-openjdk-devel icedtea-web xorg-x11-server-Xvfb x11vnc novnc python3-websockify fluxbox xterm xdotool
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm python ipmitool curl ca-certificates jdk8-openjdk icedtea-web xorg-server-xvfb x11vnc novnc websockify fluxbox xterm xdotool
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y python3 ipmitool curl ca-certificates java-1_8_0-openjdk-devel icedtea-web xvfb-run x11vnc novnc python3-websockify fluxbox xterm xdotool
fi

# Create chromeless noVNC template if /usr/share/novnc/vnc_lite.html exists
if [ -f /usr/share/novnc/vnc_lite.html ] && [ ! -f /usr/share/novnc/vnc_clean.html ]; then
    sudo cp /usr/share/novnc/vnc_lite.html /usr/share/novnc/vnc_clean.html
    sudo sed -i 's/<head>/<head><style>#top_bar{display:none!important;}body,html{margin:0!important;padding:0!important;background:#000!important;overflow:hidden!important;}</style>/' /usr/share/novnc/vnc_clean.html
fi

sudo mkdir -p /opt/megarac-commander
sudo cp index.html bridge_server.py ModernJViewerBridge.java /opt/megarac-commander/
if command -v javac >/dev/null 2>&1; then
    sudo javac -source 1.8 -target 1.8 /opt/megarac-commander/ModernJViewerBridge.java || true
fi

sudo tee /usr/local/bin/megarac-commander >/dev/null << 'EOF'
#!/usr/bin/env bash
exec python3 /opt/megarac-commander/bridge_server.py "$@"
EOF
sudo chmod +x /usr/local/bin/megarac-commander

if [ -d /etc/systemd/system ]; then
    sudo cp packaging/systemd/megarac-commander.service /etc/systemd/system/megarac-commander.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now megarac-commander.service
    echo "Started systemd service: megarac-commander.service (http://localhost:8765)"
else
    echo "Installed /usr/local/bin/megarac-commander. Run 'megarac-commander' to start."
fi
