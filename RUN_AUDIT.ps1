# RUN_AUDIT.ps1
# One-click audit runner (creates venv if missing). Writes reports to .\.local\audit

$ErrorActionPreference = "Stop"

$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT

if (!(Test-Path ".\.venv")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

python -c "import image_engine_app, PIL, PySide6" 2>$null
$depsOk = $LASTEXITCODE -eq 0
if (-not $depsOk) {
  python -m pip install -e .
}

python -m image_engine_app.app.audit --app-data-dir .\.local\audit

Write-Host ""
Write-Host "Audit outputs:"
Write-Host "  .local\\audit\\audit_report.json"
Write-Host "  .local\\audit\\audit_report.md"
