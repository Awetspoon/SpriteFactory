# RUN_AUDIT.ps1
# One-click audit runner (creates venv if missing). Writes reports to .\_audit

$ErrorActionPreference = "Stop"

$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT

if (!(Test-Path ".\.venv")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

# Tests and imports may touch UI modules, so install UI deps here.
pip install PySide6 pillow

$env:PYTHONPATH = "image_engine_app"

python -m app.audit --app-data-dir .\_audit

Write-Host ""
Write-Host "Audit outputs:"
Write-Host "  _audit\audit_report.json"
Write-Host "  _audit\audit_report.md"
