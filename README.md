# Sprite Factory

Sprite Factory is a Windows desktop image/sprite editor built with PySide6. It focuses on fast preview-driven cleanup, preset workflows, batch processing, and export for game and web assets.

[Latest release](https://github.com/Awetspoon/SpriteFactory/releases/latest) | [All releases](https://github.com/Awetspoon/SpriteFactory/releases) | [Docs index](docs/README.md) | [Project structure](docs/PROJECT_STRUCTURE.md)

![Sprite Factory main window](docs/sprite-factory-ui.png)

## Features

- Local file/folder import and URL/webpage image ingestion
- Workspace tabs with pinning and large-workspace sectioning
- Guided editor controls across `Simple`, `Advanced`, and `Expert` modes
- Preset system with user presets and safe mode-aware application
- Before/Current/Final preview workflow with reset/zoom support
- Batch processing with progress and cooperative cancel support
- Session save/load + autosave recovery
- Multi-format export (`PNG`, `WEBP`, `JPG`, `GIF`, `ICO`, `TIFF`, `BMP`)
- Windows packaging via PyInstaller (`onedir` and `onefile`)

## Requirements

- Windows 10/11
- Python `3.11+`
- `PySide6`
- `Pillow`
- `PyInstaller` (build only)

## Setup (From Source)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install PySide6 pillow pyinstaller
```

## Run

Option A (recommended helper script):

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

Option B (direct module run):

```powershell
$env:PYTHONPATH = "image_engine_app"
python -m app.main --app-data-dir .\_ui_check
```

## Build

Onedir build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Output:
- `dist\SpriteFactory\SpriteFactory.exe`

Onefile build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1
```

Output:
- `dist\SpriteFactory.exe`

## Publish / Release Flow

1. Run audit: `powershell -ExecutionPolicy Bypass -File .\RUN_AUDIT.ps1`
2. Build release artifact (`build_exe.ps1` or `build_exe_onefile.ps1`)
3. Validate packaged app with smoke checks from [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
4. Upload artifact to GitHub Releases

## Testing

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"
```

## Folder Structure

```text
image_engine_app/
  app/              # startup, controller, persistence/settings services
  ui/               # main window, coordinators, widgets, dialogs
  engine/           # ingest, processing, analysis, export, batch
  tests/            # unit + smoke tests
  docs/             # integration/reference docs

image_engine_v3/     # parallel rebuild scaffold still used by tests/adapters
docs/                # repository-level docs, screenshots, and archive material
docs/archive/        # older review/planning notes kept out of the repo root
pyinstaller_rthooks/ # runtime hooks for frozen app
requirements.txt     # convenience install list for runtime/build dependencies
```

## V3 Rebuild Track

A clean rebuild track now exists in `image_engine_v3/` so we can migrate feature-by-feature without destabilizing the live app.

- Plan: [docs/V3_REBUILD_PLAN.md](docs/V3_REBUILD_PLAN.md)
- Architecture: [docs/V3_ARCHITECTURE.md](docs/V3_ARCHITECTURE.md)

## Configuration

Optional environment variables (see `.env.example`):

Generated runtime folders such as `_ui_check/`, `_ui_check_v3/`, `build/`, and `dist/` are intentionally not part of the tracked source layout.


- `IMAGE_ENGINE_APPDATA_DIR`: override app data root (sessions/cache/logs)
- `PYTHONPATH=image_engine_app`: required when launching module directly from repo root

## Screenshots

Current screenshot:
- `docs/sprite-factory-ui.png`

Placeholder for more:
- import workflow
- controls/editor panel
- batch manager
- export flow

## License

This project is licensed under the [MIT License](LICENSE).

