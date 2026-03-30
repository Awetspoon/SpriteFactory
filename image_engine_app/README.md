# image_engine_app

This package contains the core Sprite Factory application code.

## Package Layout

- `app/` - application entrypoints, controllers, settings, and persistence helpers
- `ui/` - PySide6 windows, coordinators, and shared widgets
- `engine/` - ingest, processing, analysis, batch, and export logic
- `tests/` - unit and smoke coverage for the packaged workflow
- `docs/` - web source notes and internal integration references

## Run In Development

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m image_engine_app --app-data-dir .\.local\ui-check
```

Without `--app-data-dir`, the packaged entrypoint uses the normal platform app-data location instead of creating runtime folders in the repository root.

## Run The Audit

```powershell
python -m image_engine_app.app.audit --app-data-dir .\.local\audit
```

See the root [README.md](../README.md) for the main quick start, release links, and packaging instructions, and [docs/README.md](../docs/README.md) for the support document index.
