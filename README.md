# Sprite Factory Pro

Sprite Factory Pro is a Windows desktop app for cleaning, enhancing, previewing, batch-processing, and exporting sprites, GIFs, icons, and image assets.

[Download Latest Release](https://github.com/Awetspoon/SpriteFactory/releases/latest) | [Release Notes](docs/RELEASE_1.2.2.md) | [Troubleshooting](docs/TROUBLESHOOTING.md)

![Sprite Factory Pro main window](docs/sprite-factory-pro-1.2.1-ui.png)

## What It Does

- Import local files, folders, ZIP archives, or images found from web pages.
- Preview `Current` and `Final` output side by side before exporting.
- Apply cleanup, color, detail, transparency, GIF, export, and encoding controls.
- Remove white or black backgrounds when you choose to, without forcing it on import.
- Use presets for faster sprite, photo, GIF, and mixed-format workflows.
- Batch process large queues with presets, background overrides, file naming, and export rules.
- Export to `PNG`, `WEBP`, `JPG`, `GIF`, `ICO`, `TIFF`, and `BMP`.

## Download

The easiest way to use the app is the latest Windows release:

[Sprite Factory Pro Releases](https://github.com/Awetspoon/SpriteFactory/releases/latest)

Download the `.exe`, run it, then import files from the top `Import` menu or use the `Web Sources` tab.

## Main Workflow

1. Open a new session or continue working in the current workspace.
2. Import files, folders, ZIPs, or scan web pages for sprite/image links.
3. Select an asset from the workspace.
4. Choose a preset or adjust edit settings manually.
5. Use `Preview` to check the result in the final pane.
6. Use `Apply` when you want to commit the edit to the asset.
7. Export one file, skip to the next asset, or open Batch Manager for queue export.

## Web Sources

`Web Sources` is built for collecting sprite/image links from normal websites, not just one specific site.

- Save useful pages so you can scan them again later.
- Paste direct page URLs or a manual list of page URLs.
- Find linked index/category pages, filter the list, then scan only the pages you need.
- Filter found files by `PNG`, `GIF`, `WEBP`, `JPG`, or `ZIP`.
- Large scans warn before running so you do not accidentally overload the app or site.

## Batch Manager

Batch Manager processes selected workspace assets with a separate batch workflow so normal preview/edit state does not get tangled with queue export.

- Copy current edits when needed.
- Apply a chosen preset or smart preset rules.
- Override background-removal behavior for the batch.
- Keep source names or use batch naming rules.
- Save files after processing and review failures clearly.

## Run From Source

Requirements:

- Windows 10/11
- Python 3.11+
- PySide6
- Pillow

Quick launch:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

Manual setup:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
py -m image_engine_app
```

## Build

Build the Windows release executable:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe_onefile.ps1
```

The build output is written under `.local\release\` and is intentionally ignored by Git.

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"
```

## Repository Layout

```text
image_engine_app/      active app, UI, engine, services, and tests
image_engine_v3/       workspace/session service layer used by the app
pyinstaller_rthooks/   PyInstaller runtime hook support
docs/                  release notes, screenshot, and support docs
```

Generated folders such as `.venv/`, `.local/`, `build/`, `dist/`, `_runtime_data/`, and caches are ignored.

## License

[MIT](LICENSE)
