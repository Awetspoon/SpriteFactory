# Project Structure

This document describes the intended repository layout for Sprite Factory.

## Active code paths

- `image_engine_app/` — current production application code.
  - `app/` — application composition, controller wiring, services, settings, persistence, and audit.
  - `assets/` — packaged static assets such as app icons and UI images.
  - `engine/` — ingest, processing, analysis, batch, export, models, and the single bundled preset catalog under `engine/presets/`.
  - `ui/` — PySide6 windows, coordinators, controls, and dialogs.
  - `tests/` — unit and smoke coverage for the active app.
  - `docs/` — package-specific reference notes and default data files.

## Rebuild boundaries

- `image_engine_app/app/bootstrap.py` is the non-visual composition root. It creates paths, logging, the controller, session storage, and the clean startup session.
- `image_engine_app/ui/desktop_runtime.py` owns Qt application setup, native style, icons, window state, and the event loop.
- `image_engine_app/app/main.py` only connects the composition root to the desktop runtime.
- `image_engine_app/app/services/workspace_state.py` owns workspace ordering, selection, pinning, and section-window behavior.
- `image_engine_app/engine/ingest/import_result.py` defines the one result contract shared by every import route.
- `image_engine_app/engine/ingest/local_ingest.py` owns file, folder, ZIP expansion, validation, and content deduplication.
- `image_engine_app/app/services/asset_import.py` prepares every newly imported asset exactly once; restored assets bypass new-import defaults.
- `image_engine_app/app/services/asset_edit.py` owns interactive control mutations, edit-state replacement, detected Reset, and Final-preview refresh.
- `image_engine_app/app/services/preset_library.py` owns the merged system/user preset catalog and the only user-preset persistence path.
- `image_engine_app/app/services/preset_workflow.py` applies catalog presets through the shared edit service and controls whether Final is rebuilt.
- `image_engine_app/engine/models/workspace.py` holds the single live workspace-state boundary using real asset and session models.
- `image_engine_app/engine/process/frame_pipeline.py` owns pure in-memory frame effects.
- `image_engine_app/engine/process/transparency.py` owns background removal and alpha cleanup.
- `image_engine_app/engine/process/animation.py` is the only animated-GIF encoding path for Preview and Export.
- `image_engine_app/engine/process/source_renderer.py` handles explicit source decoding and derived rendering without UI state.
- `image_engine_app/engine/process/asset_preview.py` updates asset preview paths; `export_source.py` resolves export inputs separately.
- `image_engine_app/engine/process/edit_impact.py` is the shared rule for visible/playback settings versus export-only metadata and encoding settings.
- `image_engine_app/engine/process/preset_application.py` is the shared preset compatibility, detected-baseline, mode, and heavy-job plan used by Workspace and Batch.
- `image_engine_app/ui/main_window/edit_coordinator.py` turns Qt edit requests into application-service calls; widgets do not mutate assets.
- `image_engine_app/engine/` must not import `image_engine_app.app`, `image_engine_app.ui`, or PySide6.
- The controlled replacement sequence is documented in `docs/STAGED_REBUILD.md`.

## Repository support files

- `pyproject.toml` — repo-root Python project manifest for `image_engine_app`.
- `docs/` — repository-level docs, screenshots, release notes, and support notes.
- `pyinstaller_rthooks/` — runtime hooks used by frozen builds.
- `spritefactory.spec` / `spritefactory_onefile.spec` — PyInstaller entry specs.
- `run_app.ps1` — local development launcher.
- `build_exe.ps1` / `build_exe_onefile.ps1` — Windows packaging helpers.
- `RUN_AUDIT.ps1` — repository audit entry point.
- `BUILD_LOCK.md` — locked build-next checklist that intentionally stays at repo root.
- App icon assets live under `image_engine_app/assets/icons/` and are bundled by the PyInstaller specs.

## Generated or local-only paths

These should not be treated as source structure and should stay out of version control:

- `.venv/`
- `.local/`
- `.cache/`
- `build/`
- `dist/`
- `_runtime_data/`
- legacy scratch folders like `_ui_check/`, `_ui_check_v3/`, and `_audit/`
- Python `__pycache__/` folders

## Notes

- `image_engine_app` is the only application package and source of production behavior.
- Imports should be package-qualified (`image_engine_app.*`) rather than relying on `PYTHONPATH=image_engine_app`.
- Output-size choices are defined once in `engine/process/output_size.py`; the UI maps them onto the existing resize/width/height controls rather than maintaining duplicate size state.
- Current always reads the imported source, while Final is the only derived interactive preview.
- `python -m image_engine_app` is the preferred development entrypoint; the repo-root `main.py` wrapper is compatibility sugar only.
- Legacy repo-root `_runtime_data/` may still exist on a local machine, but it is not part of the intended source layout.
