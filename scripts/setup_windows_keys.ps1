#Requires -Version 5.1
<#
.SYNOPSIS
    Initialize encrypted API key storage for Vagus Asistent on Windows.

.DESCRIPTION
    Sets up the KeyManager master key in ~/.vagus, verifies Python 3.10+,
    confirms the cryptography package is available, and optionally prompts
    the user before initialization.

.PARAMETER Silent
    Skip the interactive confirmation prompt and run non-interactively.

.PARAMETER Force
    Alias for -Silent. Skip confirmation and proceed automatically.

.EXAMPLE
    .\setup_windows_keys.ps1
    Runs in interactive mode, prompts before initializing.

.EXAMPLE
    .\setup_windows_keys.ps1 -Silent
    Runs without prompting (for CI / automated setups).

.EXAMPLE
    .\setup_windows_keys.ps1 -Force
    Same as -Silent.
#>
param(
    [switch]$Silent,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# -Force is an alias for -Silent
if ($Force) { $Silent = $true }

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONPATH = "$projectRoot\src;$projectRoot"

Write-Host "[INFO] Checking Python environment..." -ForegroundColor Cyan

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python not found in PATH. Install Python 3.10+ and re-run." -ForegroundColor Red
    exit 1
}

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python 3.10+ is required. Current version is too old." -ForegroundColor Red
    exit 1
}

python -c "import cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Missing dependency: 'cryptography'. Run: pip install cryptography" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Dependencies OK." -ForegroundColor Cyan

if (-not $Silent) {
    $answer = Read-Host "Initialize API key storage in $HOME\.vagus ? [y/N]"
    if ($answer -notin @("y", "Y", "yes", "YES")) {
        Write-Host "[INFO] Cancelled by user." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "[INFO] Initializing KeyManager..." -ForegroundColor Cyan

python -c "from pathlib import Path; import sys; sys.path.insert(0, r'$projectRoot\src'); from vagus.security import KeyManager; km=KeyManager(); key=km._get_master_key(); d=Path.home()/'.vagus'; print(f'[OK] Initialized at: {d}'); print(f'[OK] Master key bytes: {len(key)}')"

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to initialize key storage. Check logs above for details." -ForegroundColor Red
    exit 1
}

Write-Host "[DONE] Windows key setup completed." -ForegroundColor Green
exit 0
