# Release Checklist (Windows)

Run these checks from the repository root.

## 1. Prepare

- [ ] Pull latest code
- [ ] Create/activate venv
- [ ] `pip install -U pip`
- [ ] `pip install -e ".[build]"`

## 2. Verify Source

- [ ] `.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"`
- [ ] `powershell -ExecutionPolicy Bypass -File .\RUN_AUDIT.ps1`
- [ ] Confirm `.local\audit\audit_report.md` reports `Overall: PASS`

## 3. Version And Visuals

- [ ] Confirm `pyproject.toml`, `pyinstaller_version_info.py`, the window title, release notes, and screenshot use the same version
- [ ] Confirm `image_engine_app/assets/icons/` contains the current ICO and PNG app icon assets
- [ ] Confirm `docs/sprite-factory-pro-1.2.3-ui.png` shows the current real application

## 4. Build Release

- [ ] `powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1`
- [ ] Confirm the script reports `Frozen-app smoke test: PASS`
- [ ] Confirm `.local\release\SpriteFactory-v1.2.3-win64.exe` exists
- [ ] Record the printed size and SHA-256 value

## 5. Manual Workflow Check

- [ ] Import folder images
- [ ] Scan one page and a multi-page list in Web Sources
- [ ] Apply and reset a preset while watching Final
- [ ] Process and cancel a Batch queue
- [ ] Export a static image and an animated GIF

## 6. Clean Machine Check

- [ ] Copy `.local\release\SpriteFactory-v1.2.3-win64.exe` to a second PC without Python
- [ ] Run the executable and repeat the manual workflow check

## 7. Publish

- [ ] Upload `.local\release\SpriteFactory-v1.2.3-win64.exe` to GitHub Releases
- [ ] Use `docs/RELEASE_1.2.3.md` for release notes
- [ ] Keep `README.md` and `docs/TROUBLESHOOTING.md` current
