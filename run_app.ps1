param(
  [switch]$Wait,
  [switch]$Console
)

$ErrorActionPreference = "Stop"
$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT

if (!(Test-Path ".\.venv")) {
  py -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .

$pythonExe = ".\.venv\Scripts\pythonw.exe"
if ($Console -or !(Test-Path $pythonExe)) {
  $pythonExe = ".\.venv\Scripts\python.exe"
}

if ($Wait) {
  & $pythonExe -m image_engine_app
  exit $LASTEXITCODE
}

Start-Process -FilePath $pythonExe -ArgumentList @("-m", "image_engine_app") -WorkingDirectory $ROOT | Out-Null
Write-Host "Sprite Factory launched."
