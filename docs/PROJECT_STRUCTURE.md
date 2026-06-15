# Project Structure

This document describes the intended repository layout for Sprite Factory.

## Active code paths

- `image_engine_app/` — current production application code.
  - `app/` — startup, controller wiring, settings, persistence, audit.
  - `engine/` — ingest, processing, analysis, batch, export, models.
  - `ui/` — PySide6 windows, coordinators, controls, and dialogs.
  - `tests/` — unit and smoke coverage for the active app.
  - `docs/` — package-specific reference notes and default data files.
- `image_engine_v3/` — workspace/session service layer used by current tests and adapter wiring.
  Keep this at the repository root because the active codebase imports it directly.

## Repository support files

- `pyproject.toml` — repo-root Python project manifest for `image_engine_app` and `image_engine_v3`.
- `docs/` — repository-level docs, screenshots, release notes, and support notes.
- `pyinstaller_rthooks/` — runtime hooks used by frozen builds.
- `spritefactory.spec` / `spritefactory_onefile.spec` — PyInstaller entry specs.
- `run_app.ps1` — local development launcher.
- `build_exe.ps1` / `build_exe_onefile.ps1` — Windows packaging helpers.
- `RUN_AUDIT.ps1` — repository audit entry point.
- `BUILD_LOCK.md` — locked build-next checklist that intentionally stays at repo root.

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

- The active application path is `image_engine_app`, not `image_engine_v3`.
- `image_engine_v3` is still important because the active code and tests depend on it.
- Imports should be package-qualified (`image_engine_app.*`, `image_engine_v3.*`) rather than relying on `PYTHONPATH=image_engine_app`.
- `python -m image_engine_app` is the preferred development entrypoint; the repo-root `main.py` wrapper is compatibility sugar only.
- Legacy repo-root `_runtime_data/` may still exist on a local machine, but it is not part of the intended source layout.
