# Release checklist (Windows)

This is the practical "ship a build" list.
Run the commands from the repository root.

## 1) Prepare
- [ ] Pull latest code
- [ ] Create/activate venv
- [ ] `pip install -U pip`
- [ ] `pip install -e ".[build]"`

## 2) Run audit
- [ ] `powershell -ExecutionPolicy Bypass -File .\RUN_AUDIT.ps1`
- [ ] Confirm `.local\audit\audit_report.md` shows PASS where expected

## 3) Version + icon
- [ ] Update `pyinstaller_version_info.py` version strings if needed
- [ ] Replace `spritefactory.ico` with your real icon (keep filename)

## 4) Build one-file release (recommended)
- [ ] `powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1`
- [ ] Launch `.local\pyinstaller\dist\SpriteFactory.exe`
- [ ] Confirm `.local\release\SpriteFactory-v1.2.0-win64.exe` exists

## 5) Build onedir package (optional)
- [ ] `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- [ ] Launch `.local\pyinstaller\dist\SpriteFactory\SpriteFactory.exe`
- [ ] Confirm `.local\release\SpriteFactory-v1.2.0-win64-onedir.zip` exists

## 6) Smoke test packaged build
- [ ] Import folder images
- [ ] Run Webpage Scan (depth 0 + depth 1)
- [ ] Apply preset
- [ ] Batch run + cancel
- [ ] Export (confirm files written)

## 7) Clean machine test (recommended)
- [ ] Copy `.local\release\SpriteFactory-v1.2.0-win64.exe` to a second PC without Python
- [ ] Run the EXE and repeat smoke test

## 8) Ship
- [ ] Upload `.local\release\SpriteFactory-v1.2.0-win64.exe` to GitHub Releases
- [ ] Attach `README.md` and keep `docs/TROUBLESHOOTING.md` current for support
