# Windows Installer for MegaRAC Commander (PowerShell)
$ErrorActionPreference = "Stop"
Write-Host "=== Installing MegaRAC Commander on Windows ===" -ForegroundColor Cyan

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Checking Python 3 and Temurin OpenJDK 8 via winget..."
    winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    winget install -e --id EclipseAdoptium.Temurin.8.JDK --accept-package-agreements --accept-source-agreements
}

$InstallDir = Join-Path $env:LOCALAPPDATA "MegaRAC-Commander"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item "index.html", "bridge_server.py", "ModernJViewerBridge.java" -Destination $InstallDir -Force

$BatPath = Join-Path $InstallDir "megarac-commander.bat"
Set-Content -Path $BatPath -Value "@echo off`r`npython `"$InstallDir\bridge_server.py`" --bind 127.0.0.1 --port 8765 %*"

Write-Host "Installed to $InstallDir" -ForegroundColor Green
Write-Host "Run '$BatPath' and open http://localhost:8765 in your browser." -ForegroundColor Green
