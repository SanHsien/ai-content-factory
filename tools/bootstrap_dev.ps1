[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "==> Check Python 3.11+"
py -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'; print(sys.version)"

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "==> Create .venv"
    py -3 -m venv .venv
}

Write-Host "==> Offline bootstrap"
& $venvPython -B (Join-Path $repoRoot "scripts\bootstrap_offline.py")
if ($LASTEXITCODE -ne 0) {
    throw "bootstrap_offline.py failed with exit code $LASTEXITCODE"
}

Write-Host "==> Canonical Windows gate"
& pwsh -NoProfile -File (Join-Path $repoRoot "tools\dev_check.ps1")
