# MegaRAC Commander — Unified HTML5 iKVM & IPMI 2.0 Control Center

An open-source web application, Java 8 Swing Reflection bridge (`ModernJViewerBridge.java`), and IPMI 2.0 toolkit built for **AMI MegaRAC SP (Firmware Revision 7.17.00)** Baseboard Management Controllers (ASPEED AST2300/AST2400 boards such as ASRock Rack, Tyan, Supermicro, Gigabyte, Chenbro, and Dell/Quanta).

## Highlights

- **Unified Side-by-Side Single-Screen Dashboard**: Watch the live **Chromeless HTML5 iKVM Console** on the left while adjusting **Fan Speed PWM Sliders**, **Boot Device Overrides (`efiboot`, `persistent`, `clear-cmos`)**, **Live SDR Sensors**, and **Raw IPMI Hex Commands** in the right-hand dock.
- **Native `JViewer.jar` Swing Reflection (`ModernJViewerBridge.java`)**:
  - Dynamically walks the live `JMenuBar` and `JToolBar` inside your BMC's `JViewer.jar` on the Swing Event Dispatch Thread.
  - Hides the dated 2012 Java Swing menu bar and toolbar (`Chromeless UI` toggle) so only the raw server video canvas fills the screen.
  - Exposes all native JViewer actions (`Pause`, `Resume`, `Refresh`, `Sync Cursor`, `Abs/Rel Mouse`, `Hold Right Ctrl / Left Alt`, `Virtual Media Wizard`, `Keyboard Layout`) as modern HTML5 buttons.
- **Unlocks Hidden `ipmitool` Settings**:
  - Supports ASRock Rack (`0x3a 0x01`, `0x3a 0xd8`), AMI/Supermicro/Tyan (`0x30 0x70 0x66`), and Dell/Quanta (`0x30 0x30`) manual PWM fan overrides + Low-RPM Noctua sensor threshold fixes (`ipmitool sensor thresh <FAN> lower 100 150 200`).
  - Auto-negotiates IPMI 2.0 (`lanplus`, `-C 3`, `-C 17`, `-C 0`) and IPMI 1.5 (`lan`) cipher suites.

## Installation across Popular Systems

### 1. Docker Compose (Recommended — All Dependencies Bundled)
```bash
docker compose down
docker compose up --build -d
# Open http://localhost:8765
```

### 2. Debian / Ubuntu (`.deb` Package)
```bash
./packaging/build-packages.sh
sudo apt install ./dist/megarac-commander_1.0.0_all.deb
sudo systemctl enable --now megarac-commander
```

### 3. Universal Linux Installer (Debian, Ubuntu, Fedora, RHEL, Arch, openSUSE)
```bash
chmod +x install.sh
./install.sh
```

### 4. Arch Linux (`makepkg`)
```bash
./packaging/build-packages.sh
cp dist/megarac-commander-1.0.0-linux-any.tar.gz packaging/arch/
cd packaging/arch && makepkg -si
```

### 5. macOS (Homebrew) & Windows (PowerShell / Winget)
- **macOS**: `brew install --build-from-source packaging/homebrew/megarac-commander.rb`
- **Windows**: Run `powershell -ExecutionPolicy Bypass -File packaging\windows\install-windows.ps1`

### 6. Python (`pipx` / `pip`)
```bash
pipx install .
megarac-commander --bind 0.0.0.0 --port 8765
```

## Publishing to GitHub
This folder is a complete Git repository structure including `.github/workflows/release.yml` (which automatically builds `.deb`, `.tar.gz`, Python `.whl`, and Windows `.zip` release assets on every `v*` tag):
```bash
git init
git add .
git commit -m "Initial release of MegaRAC Commander v1.0.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/megarac-commander.git
git push -u origin main
```
