# Sprite Factory Pro

Sprite Factory Pro is a Windows desktop app for sprite and image cleanup, enhancement, and export. It is built for people who need to process many assets quickly without losing control over quality.

[Latest release](https://github.com/Awetspoon/SpriteFactory/releases/latest) | [All releases](https://github.com/Awetspoon/SpriteFactory/releases) | [Docs index](docs/README.md)

![Sprite Factory main window](docs/sprite-factory-ui.png)

## What The Program Does

- Imports sprites/images from local files, folders, ZIP archives, and web pages
- Detects and lists downloadable image links from URL scan areas
- Lets you apply presets or manual controls for cleanup/upscale/detail/transparency
- Shows side-by-side preview (`Before` and `Final`) while editing
- Exports to `PNG`, `WEBP`, `JPG`, `GIF`, `ICO`, `TIFF`, and `BMP`
- Runs batch exports with progress, cancellation, and auto-export queueing
- Saves sessions so users can reopen and continue work later

## Core Workflow

1. Start a new session from the top toolbar.
2. Import assets from the `Import` dropdown (file/folder/ZIP) or use `Web Sources`.
3. Pick a preset from the preset dropdown.
4. Fine-tune controls in `Settings` (resolution, detail, cleanup, transparency, export).
5. Click `Apply` for preview updates.
6. Export one asset, or open `Batch Manager` to export selected items automatically.

## Web Sources (URL Scanner)

- `Scan Area` scans a website area and collects direct + likely media links.
- `Network Check` helps diagnose DNS/TCP/HTTP access issues.
- Friendly errors are shown for common blockers:
  - `WinError 10013` (Windows blocked network access)
  - `HTTP 403` (site blocked automated requests)
  - `HTTP 429` (rate limited)
- If a site blocks scans, use a direct file URL where possible.

## Requirements

- Windows 10/11
- Python 3.11+
- PySide6
- Pillow
- PyInstaller (build only)

## Run From Source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install PySide6 pillow pyinstaller

# Launch
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

Direct module run:

```powershell
$env:PYTHONPATH = "image_engine_app"
python -m app.main --app-data-dir .\_ui_check
```

## Build Windows EXE

One-file release build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1
```

Output:

- `dist\SpriteFactory.exe`

Folder (onedir) build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Output:

- `dist\SpriteFactory\SpriteFactory.exe`

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"
```

## Repository Layout

```text
image_engine_app/
  app/              # startup/controller/settings
  ui/               # main window + coordinators/widgets/dialogs
  engine/           # ingest/process/analyze/export/batch
  tests/            # automated tests

image_engine_v3/     # staged rebuild track
pyinstaller_rthooks/ # runtime hooks for frozen build
docs/                # repo docs and screenshots
```

## License

[MIT](LICENSE)