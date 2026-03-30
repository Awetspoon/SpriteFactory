# build_exe.ps1
# Builds a Windows EXE (onedir) using PyInstaller. Fails fast if PyInstaller errors.

$ErrorActionPreference = "Stop"

$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT
$BUILD_ROOT = Join-Path $ROOT ".local\\pyinstaller"
$WORK_PATH = Join-Path $BUILD_ROOT "build"
$DIST_PATH = Join-Path $BUILD_ROOT "dist"
$RELEASE_PATH = Join-Path $ROOT ".local\\release"

$versionMatch = Select-String -Path ".\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
if ($null -eq $versionMatch) { throw "Unable to read version from pyproject.toml" }
$PROJECT_VERSION = $versionMatch.Matches[0].Groups[1].Value

function Test-PythonImports {
  param([string[]]$Modules)
  $check = @"
import importlib.util
import sys
missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
"@
  & python -c $check @Modules
  return ($LASTEXITCODE -eq 0)
}

if (!(Test-Path ".\.venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1

if (!(Test-PythonImports @("PyInstaller", "PIL", "PySide6", "setuptools"))) {
  python -m pip install --upgrade pip setuptools wheel
  if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed with exit code $LASTEXITCODE" }

  python -m pip install --no-build-isolation -e ".[build]"
  if ($LASTEXITCODE -ne 0) { throw "editable install failed with exit code $LASTEXITCODE" }
}

# Run tests (comment out if you want faster builds)
python -m unittest discover -s image_engine_app\tests -p "test_*.py"
if ($LASTEXITCODE -ne 0) { throw "tests failed with exit code $LASTEXITCODE" }

# Clean previous builds
if (Test-Path $WORK_PATH) { Remove-Item -Recurse -Force $WORK_PATH }
if (Test-Path $DIST_PATH) { Remove-Item -Recurse -Force $DIST_PATH }
New-Item -ItemType Directory -Force -Path $BUILD_ROOT | Out-Null
New-Item -ItemType Directory -Force -Path $RELEASE_PATH | Out-Null

python -m PyInstaller --noconfirm --clean --distpath $DIST_PATH --workpath $WORK_PATH .\spritefactory.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$builtDir = Join-Path $DIST_PATH "SpriteFactory"
if (!(Test-Path $builtDir)) { throw "Expected onedir output folder was not created at $builtDir" }

$releaseZip = Join-Path $RELEASE_PATH "SpriteFactory-v$PROJECT_VERSION-win64-onedir.zip"
if (Test-Path $releaseZip) { Remove-Item -Force $releaseZip }
Compress-Archive -Path (Join-Path $builtDir "*") -DestinationPath $releaseZip

Write-Host ""
Write-Host "Build complete."
Write-Host "Sprite Factory EXE is in: $DIST_PATH\\SpriteFactory\\SpriteFactory.exe"
Write-Host "GitHub-ready onedir ZIP is in: $releaseZip"
