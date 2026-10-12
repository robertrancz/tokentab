# Build a standalone tokentab.exe (Windows).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Syncing project + PyInstaller..."
uv sync --group dev

Write-Host "Cleaning previous build artifacts..."
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist, build

Write-Host "Building one-file executable..."
uv run pyinstaller --noconfirm --clean tokentab.spec

$exe = Join-Path (Get-Location) "dist\tokentab.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: $exe not found"
}

Write-Host ""
Write-Host "OK: $exe"
Write-Host "Run:  .\dist\tokentab.exe"
Write-Host "Demo: .\dist\tokentab.exe --demo"
Write-Host "Help: .\dist\tokentab.exe --help"
