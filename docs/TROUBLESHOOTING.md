# Troubleshooting

## PowerShell blocks .ps1 scripts (ExecutionPolicy)
If you see "not digitally signed" / "cannot be loaded":

Run once (recommended):
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Or bypass for a single run:
```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

---

## "Qt platform plugin" errors (qwindows / plugins)
If the EXE fails with a Qt plugin error, this project ships a PyInstaller runtime hook:

- `pyinstaller_rthooks/pyside6_plugin_path.py`

If you still hit issues:
1. Rebuild using the provided spec + scripts
2. Ensure `PySide6` is installed in the build venv
3. Avoid running from a path with unusual characters

---

## Webpage Scan finds too many junk images
Use:
- **Sprite Scan Mode**
- **Same-domain only**
- **Min width/height** filters
- **Max pages** cap

---

## Webpage Scan finds 0 images
Check:
- The page loads in your browser
- Your connection/firewall is not blocking requests
- Try **Depth 0** first
- Some sites use heavy JS rendering; the scanner reads static HTML

---

## Export outputs "metadata JSON" instead of images
Export writes real images when:
- an asset has a local `cache_path`, and
- `pillow` is installed

Install:
```powershell
pip install pillow
```

---

## Long paths / Windows path issues
If you build/run from deeply nested folders, Windows path limits can bite.

Best practice:
- keep the repo path short (for example `C:\dev\SpriteFactory`)
- keep output paths short

