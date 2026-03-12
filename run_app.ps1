# run_app.ps1
# One-click local run for Sprite Factory (creates venv if missing).
# Default behavior is windowed launch (like EXE) so this script does not keep a shell open.

param(
  [switch]$Wait,
  [switch]$Console
)

$ErrorActionPreference = "Stop"

# Resolve script root safely (works whether run as file or pasted)
$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT

if (!(Test-Path ".\.venv")) {
  python -m venv .venv
}

# Activate venv
. .\.venv\Scripts\Activate.ps1

# Ensure runtime deps
python -m pip install --upgrade pip
pip install PySide6 pillow

# Set module path so "python -m app.main" works
$env:PYTHONPATH = "image_engine_app"

$appArgs = @("-B", "-m", "app.main", "--app-data-dir", ".\\_ui_check")
$pythonExe = ".\\.venv\\Scripts\\pythonw.exe"
if ($Console -or !(Test-Path $pythonExe)) {
  $pythonExe = ".\\.venv\\Scripts\\python.exe"
}

if ($Wait) {
  & $pythonExe @appArgs
  exit $LASTEXITCODE
}

Start-Process -FilePath $pythonExe -ArgumentList $appArgs -WorkingDirectory $ROOT | Out-Null
Write-Host "Sprite Factory launched (windowed)."
