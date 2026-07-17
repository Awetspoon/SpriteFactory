# build_exe_onefile.ps1
# Builds a Windows EXE (onefile) using PyInstaller. Fails fast if PyInstaller errors.

$ErrorActionPreference = "Stop"

$ROOT = if ($PSScriptRoot -and $PSScriptRoot.Length -gt 0) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $ROOT
$BUILD_ROOT = Join-Path $ROOT ".local\\pyinstaller"
$WORK_PATH = Join-Path $BUILD_ROOT "build"
$DIST_PATH = Join-Path $BUILD_ROOT "dist"
$RELEASE_PATH = Join-Path $ROOT ".local\\release"
$SMOKE_DATA_PATH = Join-Path $BUILD_ROOT "smoke-runtime"
$WORKSPACE_ROOT = [System.IO.Path]::GetFullPath($ROOT).TrimEnd('\')

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

function Remove-WorkspaceDirectory {
  param([Parameter(Mandatory = $true)][string]$Path)

  $target = [System.IO.Path]::GetFullPath($Path)
  $workspacePrefix = $WORKSPACE_ROOT + "\"
  if (-not $target.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove a directory outside the workspace: $target"
  }
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
}

if (!(Test-Path ".\.venv")) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1

if (!(Test-PythonImports @("PyInstaller", "PIL", "PySide6", "setuptools"))) {
  python -m pip install --upgrade pip setuptools wheel
  if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed with exit code $LASTEXITCODE" }

  python -m pip install --no-build-isolation -e ".[build]"
  if ($LASTEXITCODE -ne 0) { throw "editable install failed with exit code $LASTEXITCODE" }
}

python -m unittest discover -s image_engine_app\tests -p "test_*.py"
if ($LASTEXITCODE -ne 0) { throw "tests failed with exit code $LASTEXITCODE" }

Remove-WorkspaceDirectory $WORK_PATH
Remove-WorkspaceDirectory $DIST_PATH
Remove-WorkspaceDirectory $SMOKE_DATA_PATH
New-Item -ItemType Directory -Force -Path $BUILD_ROOT | Out-Null
New-Item -ItemType Directory -Force -Path $RELEASE_PATH | Out-Null
New-Item -ItemType Directory -Force -Path $SMOKE_DATA_PATH | Out-Null

python -m PyInstaller --noconfirm --clean --distpath $DIST_PATH --workpath $WORK_PATH .\spritefactory_onefile.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$builtExe = Join-Path $DIST_PATH "SpriteFactory.exe"
if (!(Test-Path $builtExe)) { throw "Expected onefile EXE was not created at $builtExe" }

$versionInfo = (Get-Item -LiteralPath $builtExe).VersionInfo
if (-not $versionInfo.ProductVersion.StartsWith($PROJECT_VERSION)) {
  throw "Built EXE reports ProductVersion '$($versionInfo.ProductVersion)' instead of '$PROJECT_VERSION'"
}

$smokeArguments = @(
  "--smoke-test",
  "--app-data-dir",
  "`"$SMOKE_DATA_PATH`""
)
$smokeProcess = Start-Process `
  -FilePath $builtExe `
  -ArgumentList $smokeArguments `
  -WindowStyle Hidden `
  -PassThru

if (-not $smokeProcess.WaitForExit(90000)) {
  Stop-Process -Id $smokeProcess.Id -Force
  throw "Frozen-app smoke test timed out after 90 seconds"
}
$smokeProcess.Refresh()
if ($smokeProcess.ExitCode -ne 0) {
  throw "Frozen-app smoke test failed with exit code $($smokeProcess.ExitCode)"
}

$smokeLog = Join-Path $SMOKE_DATA_PATH "logs\\image_engine_app.log"
if (!(Test-Path -LiteralPath $smokeLog)) {
  throw "Frozen-app smoke test did not create its application log"
}
$smokeLogText = Get-Content -LiteralPath $smokeLog -Raw
if ($smokeLogText -notmatch "Runtime icon loaded") {
  throw "Frozen-app smoke test did not load the packaged application icon"
}
if ($smokeLogText -notmatch "UI shell launched") {
  throw "Frozen-app smoke test did not reach the main UI shell"
}

$artifactName = "SpriteFactory-v$PROJECT_VERSION-win64.exe"
$artifactPath = Join-Path $RELEASE_PATH $artifactName
Copy-Item -LiteralPath $builtExe -Destination $artifactPath -Force

$artifact = Get-Item -LiteralPath $artifactPath
$artifactHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash

Write-Host ""
Write-Host "Build complete."
Write-Host "Sprite Factory EXE is in: $DIST_PATH\\SpriteFactory.exe"
Write-Host "GitHub-ready EXE is in: $artifactPath"
Write-Host "Frozen-app smoke test: PASS"
Write-Host "Version: $($versionInfo.ProductVersion)"
Write-Host "Size: $([Math]::Round($artifact.Length / 1MB, 2)) MB"
Write-Host "SHA-256: $artifactHash"
