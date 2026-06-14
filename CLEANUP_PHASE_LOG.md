# Cleanup Phase Log

This log follows the generic audit order from the external cleanup checklist and records the safe cleanup state for Sprite Factory.

## 2026-06-05

### 01 LOCK

- `[x]` Source of truth:
  - [README.md](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/README.md)
  - [docs/README.md](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/docs/README.md)
  - [pyproject.toml](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/pyproject.toml)
  - [image_engine_app](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app)
  - [image_engine_app/tests](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/tests)
- `[x]` App purpose locked:
  - Windows desktop app for sprite/image cleanup, preview, batch export, and mixed-format processing.
- `[x]` Must-not-change rule:
  - Keep the current app purpose and release path intact; do not reintroduce fake UI or root-level runtime/build clutter.

### 02 BREAKDOWN

- `[x]` Active app path: `image_engine_app`
- `[x]` Parallel rebuild/support path: `image_engine_v3`
- `[x]` Packaging path: PyInstaller specs + PowerShell build scripts
- `[x]` Release target: single-file Windows EXE

### 03 MAP

- `KEEP`:
  - [image_engine_app](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app)
  - [image_engine_v3](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_v3)
  - [docs](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/docs)
  - [pyinstaller_rthooks](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/pyinstaller_rthooks)
- `KEEP`:
  - [build_exe_onefile.ps1](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/build_exe_onefile.ps1)
  - [build_exe.ps1](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/build_exe.ps1)
  - [run_app.ps1](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/run_app.ps1)
- `TIDY`:
  - Repository docs should clearly distinguish source paths from ignored local/runtime/build paths.

### 04 CHECK

- `[x]` Package entrypoint exists: [main.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/main.py)
- `[x]` Preferred launch path exists: `python -m image_engine_app`
- `[x]` Test suite exists and is the main verification baseline.

### 05 AUDIT

- `[x] KEEP` App/runtime structure is coherent.
- `[x] KEEP` Build/release path already points to `.local\release`.
- `[~] TIDY` Local generated folders still exist in the workspace as ignored machine output:
  - `.local/`
  - `.cache/`
  - `_runtime_data/`
  - `build/`
  - `dist/`
  - `__pycache__/`
- `[x] KEEP` These are already excluded from version control and are not part of the uploadable repo content.
- `[x] KEEP` Runtime migration away from repo-root `_runtime_data` is already implemented in [image_engine_app/launcher.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/launcher.py).

### 06 FIX

- `[x]` Added this cleanup log to lock the audit order and current repo-clean state.
- `[x]` Tightened docs so local/generated paths are called out more clearly.
- `[x]` Split preset catalog/order/persistence logic out of [image_engine_app/app/ui_controller.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/ui_controller.py) into [image_engine_app/app/services/preset_library.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/services/preset_library.py) so the controller keeps orchestration instead of also owning preset storage rules.
- `[x]` Split imported-asset hydration, metadata probing, and format helpers out of [image_engine_app/app/ui_controller.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/ui_controller.py) into [image_engine_app/app/services/asset_profile_service.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/services/asset_profile_service.py) so asset setup and inference defaults live in one place.
- `[x]` Split batch auto-preset and per-source preset rule assembly out of [image_engine_app/app/ui_controller.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/ui_controller.py) into [image_engine_app/app/services/batch_preset_rules.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/services/batch_preset_rules.py) so batch rule composition stops living inline inside controller execution.
- `[x]` Split export prediction/label/export-path assembly out of [image_engine_app/app/ui_controller.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/ui_controller.py) into [image_engine_app/app/services/export_workflow.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/services/export_workflow.py) so the controller delegates export workflow instead of building requests directly.
- `[~]` Local ignored machine output can be manually removed later if you want a physically cleaner workspace, but it is already logically clean for repo/release purposes.

### 07 VERIFY

- `[x]` Full test suite passed after doc cleanup.
  - Command:
    - `.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"`
  - Result:
    - `317` tests passed.

### 08 NEXT

- The broadest remaining cleanup target is still [image_engine_app/app/ui_controller.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/app/ui_controller.py), but the highest-risk preset, asset-profile, batch-rule, and export-workflow patch seams have now been separated into services and reverified.

## 2026-06-11

### Shell Layout Pass

- `[x]` Reworked the main shell in place around the locked editor structure:
  - left rail for `Workspace`, `Web Sources`, and `Helper`
  - workspace/source panel with a real import action
  - center preview studio kept dominant
  - workflow/export controls kept under preview
  - right inspector aligned to the locked mock title `EDIT SETTINGS`
- `[x]` Tightened shared visual rules in [image_engine_app/ui/common/shell_theme.py](C:/Users/Marcus/Desktop/Marcus%20APPs/windows/SpriteFactory/image_engine_app/ui/common/shell_theme.py) so panels, buttons, rails, and footer controls use the same compact radius/spacing language.
- `[x]` Updated helper wording and smoke tests to reflect the new left rail and source panel.

### Verify

- `[x]` Focused UI suite passed:
  - `image_engine_app.tests.test_main_window_smoke`
  - `image_engine_app.tests.test_settings_panel`
  - `image_engine_app.tests.test_control_strip`
  - `image_engine_app.tests.test_preview_panel`
  - `image_engine_app.tests.test_export_bar`
- `[x]` Full test suite passed:
  - Command: `.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"`
  - Result: `317` tests passed.

### Mockup Alignment Pass

- `[x]` Matched the approved clean-editor mockup more closely:
  - left rail now uses icon+label navigation for `Workspace`, `Web Sources`, and `Helper`
  - workspace panel now has a centered empty import card and a bottom import action
  - preview empty states use a cleaner framed placeholder in both panes
  - settings picker uses compact tiles instead of old stacked rows
  - right header stays focused on `EDIT SETTINGS` and `Reset All`
- `[x]` Tightened the top toolbar so `Quick Preset` and `Choose preset...` stay together instead of stretching across the whole row.
- `[x]` Normalized top-toolbar geometry so brand, menu buttons, active-asset badges, quick preset, and right-side actions share fixed heights and cleaner spacing.
- `[x]` Removed the old performance selector end-to-end because the current processing path does not need a user-facing backend choice.
- `[x]` Corrected the mock alignment miss in the right inspector:
  - settings tiles now use fixed 3-column icon cards instead of stretch-expanded clipped text buttons
  - selecting a tile no longer auto-scrolls the inspector down and hides the `EDIT SETTINGS` header
  - the extra left-side `Source` card was removed so the workspace panel keeps one import area like the mock
- `[x]` Focused UI tests passed after the pass.
- `[x]` Full test suite passed:
  - Command: `.\.venv\Scripts\python.exe -B -m unittest discover -s image_engine_app\tests -p "test_*.py"`
  - Result: `318` tests passed.
