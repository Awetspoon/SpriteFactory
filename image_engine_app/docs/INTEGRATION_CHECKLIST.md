# Integration Checklist â€” Web Sources Tab

This checklist is written to avoid broken patches.

## 1) Add new files (no edits yet)
Add these files to your repo:
- `image_engine_app/ui/main_window/web_sources_panel.py`
- `image_engine_app/engine/ingest/web_sources_rules.py`
- `image_engine_app/engine/ingest/zip_extract.py`
- `image_engine_app/app/web_sources_models.py`

## 2) Wire the tab into the main UI
Edit:
- `image_engine_app/ui/main_window/asset_tabs.py`

Add a new tab labeled **Web Sources** and place `WebSourcesPanel(...)` in it.

**Rule:** Do not move or rename existing tabs; just add one.

## 3) Add controller entry points
Edit:
- `image_engine_app/app/ui_controller.py`

Add methods:
- `scan_web_source_area(area_url: str, *, allowed_exts: set[str] | None = None) -> ScanResults`
- `download_web_items(items: list[WebItem], target: ImportTarget, *, smart: SmartOptions) -> DownloadReport`

These methods should call your existing:
- `engine/ingest/webpage_scan.py`
- `engine/ingest/url_ingest.py`
- app/controller cache path handling (existing cache flow)

## 4) Add settings persistence
Edit:
- `image_engine_app/app/settings_store.py`

Store:
- `web_sources_registry` (list of websites + areas)
- `web_sources_last_selected` (website_id, area_id)
- `web_sources_options` (toggles like Show Likely, Auto-sort, Skip duplicates)

A default registry example is in `docs/DEFAULT_WEB_SOURCES.json`.

## 5) Import destination mapping
In controller, map ImportTarget â†’ your actual library folders.

Targets:
- Normal
- Shiny
- Animated
- Items

If your project uses different folder names, only change the mapping.

## 6) ZIP support
When a selected item is a `.zip`:
- download zip to cache
- use `engine/ingest/zip_extract.py` to extract only allowed images
- import extracted results like normal

## 7) Library refresh
After downloads finish, trigger whatever your app uses to refresh the library grid / index.

## 8) Smoke tests
- Scan a page with PNGs â†’ results list populates
- Download 1 PNG â†’ appears in library
- Download same PNG again â†’ skipped (when Skip duplicates ON)
- Download a ZIP â†’ wizard/flow extracts and imports images


