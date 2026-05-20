# Build a self-contained Windows distribution of optsim.
#
# Usage:
#   PowerShell> .\packaging\build_windows.ps1
#
# Requirements:
#   - Python 3.11 (other 3.10-3.12 versions work too)
#   - The project installed with `pip install -e .[all,package]`

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location $ProjectRoot
try {
    if ($Clean) {
        Write-Host "Cleaning previous build outputs..."
        Remove-Item -Recurse -Force ".\build" -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force ".\dist" -ErrorAction SilentlyContinue
    }

    Write-Host "Running PyInstaller..."
    pyinstaller --noconfirm packaging\optsim.spec

    $exePath = Join-Path $ProjectRoot "dist\optsim\optsim.exe"
    if (Test-Path $exePath) {
        Write-Host "Build complete: $exePath"
    } else {
        Write-Host "Build finished but optsim.exe was not found." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
