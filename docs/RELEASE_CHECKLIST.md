# Release checklist (Windows)

This is the practical "ship a build" list.
Run the commands from the repository root.

## 1) Prepare
- [ ] Pull latest code
- [ ] Create/activate venv
- [ ] `pip install -U pip`
- [ ] `pip install PySide6 pillow pyinstaller`

## 2) Run audit
- [ ] `powershell -ExecutionPolicy Bypass -File .\RUN_AUDIT.ps1`
- [ ] Confirm `_audit\audit_report.md` shows PASS where expected

## 3) Version + icon
- [ ] Update `pyinstaller_version_info.py` version strings if needed
- [ ] Replace `spritefactory.ico` with your real icon (keep filename)

## 4) Build
- [ ] Onedir: `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- [ ] Launch `dist\SpriteFactory\SpriteFactory.exe`

## 5) Onefile (optional)
- [ ] `powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1`
- [ ] Launch `dist\SpriteFactory.exe`

## 6) Smoke test packaged build
- [ ] Import folder images
- [ ] Run Webpage Scan (depth 0 + depth 1)
- [ ] Apply preset
- [ ] Batch run + cancel
- [ ] Export (confirm files written)

## 7) Clean machine test (recommended)
- [ ] Copy `dist/` to a second PC without Python
- [ ] Run the EXE and repeat smoke test

## 8) Ship
- [ ] Zip the dist output
- [ ] Include this project README + `docs/TROUBLESHOOTING.md`
