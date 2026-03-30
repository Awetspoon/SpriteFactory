# Web Sources + Smart Layer
## Full Breakdown (Ready To Start)

Date: 2026-03-02
Repo: SpriteFactory_Windows_Python_V2

## 1) Current State (Already Implemented)
- Core ingest pipeline exists for URL + webpage scan + local import.
- Smart-layer scaffold files exist:
  - `image_engine_app/ui/main_window/web_sources_panel.py`
  - `image_engine_app/app/web_sources_models.py`
  - `image_engine_app/engine/ingest/web_sources_rules.py`
  - `image_engine_app/engine/ingest/zip_extract.py`
  - `image_engine_app/docs/WEB_SOURCES_SPEC.md`
  - `image_engine_app/docs/INTEGRATION_CHECKLIST.md`
  - `image_engine_app/docs/DEFAULT_WEB_SOURCES.json`

## 2) What Is Missing vs Lock-In Spec

### A. UI wiring missing
- `WebSourcesPanel` is present but not mounted in `main_window.py`.
- No signal hookups from panel to controller (`scan_requested`, `download_requested`).

### B. Controller orchestration missing
- `ui_controller.py` does not yet expose dedicated Web Sources flows:
  - source registry load/save
  - scan + confidence shaping
  - download/import report with counters
  - ZIP branch handling + safe extraction path
  - auto-sort + dedupe behavior.

### C. Persistence missing
- `settings_store.py` currently has no structured `web_sources_*` settings contract.
- Missing persisted toggles:
  - `show_likely`
  - `auto_sort`
  - `skip_duplicates`
  - `allow_zip`
  - selected website/area.

### D. Smart feature gaps
- Confidence is not currently surfaced as badges in integrated workflow.
- Auto bucket routing exists as rules but not yet used in import orchestration.
- ZIP wizard path not connected to runtime flow.
- Duplicate handling summary (skipped/renamed/failed counters) not integrated in UI status.
- Preview pane is currently URL/text-centric; no enlarged image preview rendering in Web Sources panel flow.
- Quick resize post-import toggle is not yet wired.

### E. Tests missing
- No dedicated tests for Web Sources panel orchestration path.
- Missing end-to-end behavior tests for:
  - confidence filtering
  - dedupe outcomes
  - zip extraction/import path
  - auto-sort bucket routing.

## 3) File Ownership Plan (Exact)

### `image_engine_app/ui/main_window/main_window.py`
Add:
- `self.web_sources_panel = WebSourcesPanel(self)`
- tab insertion in center layout (new tab or dock section)
- signal connections:
  - `self.web_sources_panel.scan_requested.connect(self._on_web_sources_scan_requested)`
  - `self.web_sources_panel.download_requested.connect(self._on_web_sources_download_requested)`
- handlers:
  - `_on_web_sources_scan_requested(payload: object) -> None`
  - `_on_web_sources_download_requested(payload: object) -> None`

### `image_engine_app/app/ui_controller.py`
Add:
- `load_web_sources_registry(...)`
- `scan_web_sources_area(...) -> ScanResults`
- `download_web_sources_items(...) -> DownloadReport`
- helper methods:
  - `_classify_web_item_confidence(...)`
  - `_resolve_web_import_target(...)`
  - `_dedupe_destination_path(...)`
  - `_import_downloaded_file(...)`
  - `_import_extracted_zip_images(...)`

### `image_engine_app/app/settings_store.py`
Add schema section:
- `settings['web_sources'] = { ... }`
Keys:
- `registry`
- `last_selected`
- `options`

### `image_engine_app/ui/main_window/web_sources_panel.py`
Keep existing scaffold and add:
- confidence badge rendering in list labels
- optional thumbnail/preview pixmap load
- progress line updates from controller reports

### `image_engine_app/engine/ingest/web_sources_rules.py`
Already present. Use directly in controller for:
- `confidence_for`
- `guess_import_target`
- `dedupe_key`

### `image_engine_app/engine/ingest/zip_extract.py`
Already present. Use directly in controller for ZIP branch.

## 4) Execution Order (Low-Risk)
1. Wire panel into main window (no behavior change yet).
2. Add controller methods with pure data returns (ScanResults/DownloadReport).
3. Connect panel scan flow -> results render.
4. Connect panel download flow -> import + counters.
5. Add dedupe + auto-sort options.
6. Add ZIP extraction branch.
7. Add settings persistence.
8. Add quick resize toggle (default OFF).
9. Add tests and finalize.

## 5) Smart Defaults (Beginner Safe)
- Show likely links: OFF
- Auto-sort downloads: OFF
- Skip duplicates: ON
- ZIP extract wizard: ON
- Auto-resize after import: OFF

## 6) Definition of Done
- User can: Website -> Area -> Scan -> Select -> Download -> items appear in workspace/library.
- Confidence filter works with OFF-by-default likely links.
- Dedupe report visible (`downloaded/skipped/failed`).
- ZIP import accepts image files only and blocks unsafe entries.
- Settings persist across relaunch.
- Unit tests cover smart path and pass in CI/local.
