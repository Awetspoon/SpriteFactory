# build_exe.ps1
# Builds a Windows EXE (onedir) using PyInstaller. Fails fast if PyInstaller errors.

$ErrorActionPreference = "Stop"

$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT

if (!(Test-Path ".\.venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install pyinstaller PySide6 pillow

# Ensure module path
$env:PYTHONPATH = "image_engine_app"

# Run tests (comment out if you want faster builds)
python -m unittest discover -s image_engine_app\tests -p "test_*.py"

# Clean previous builds
if (Test-Path ".\build") { Remove-Item -Recurse -Force ".\build" }
if (Test-Path ".\dist")  { Remove-Item -Recurse -Force ".\dist"  }

python -m PyInstaller --noconfirm --clean --distpath ".\dist" --workpath ".\build" .\spritefactory.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Build complete."
Write-Host "Sprite Factory EXE is in: $ROOT\dist\SpriteFactory\SpriteFactory.exe"

