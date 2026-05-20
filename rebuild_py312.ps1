$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py312 = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
$Venv = Join-Path $Root ".venv312"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py312)) {
    Write-Host "Python 3.12 not found. Installing with winget..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.12 --scope user --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
}

if (-not (Test-Path $Py312)) {
    throw "Python 3.12 executable not found: $Py312"
}

if (Test-Path $Venv) {
    Write-Host "Removing existing .venv312..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Venv
}

Write-Host "Creating .venv312 with Python 3.12..." -ForegroundColor Cyan
& $Py312 -m venv $Venv

Write-Host "Upgrading pip/setuptools/wheel..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip setuptools wheel

Write-Host "Installing optsim dependencies..." -ForegroundColor Cyan
& $VenvPython -m pip install -e ".[all,dev]"

Write-Host ""
Write-Host "Running doctor..." -ForegroundColor Cyan
& $VenvPython -m optsim.cli doctor

Write-Host ""
Write-Host "Done. Activate with:" -ForegroundColor Green
Write-Host "  .\.venv312\Scripts\Activate.ps1"
Write-Host "Run GUI with:" -ForegroundColor Green
Write-Host "  python -m optsim.gui"
