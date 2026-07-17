# Changelog

## 1.2.4 - 2026-07-17
- Reordered Find Linked Pages into a clear choose-or-paste, discover, filter, select, and scan workflow.
- Allowed direct index or category URLs in the discovery source field instead of mistaking them for result-filter text.
- Removed automatic page selection after discovery so scans process only the pages the user explicitly selects.
- Standardized the public application, icon, documentation, executable, and release identity as Sprite Factory.
- Updated Helper guidance and added regression coverage for direct discovery URLs and explicit linked-page selection.

## 1.2.3 - 2026-07-17
- Rebuilt Saved Pages as a persistent Saved Library where each website contains its saved child pages and whole websites or individual pages can be scanned together.
- Added Save Selected to Library for discovered links, preserving useful page names, grouping by website host, and preventing duplicate bookmarks.
- Removed ambiguous highlighted-page scan fallback behavior so Scan Checked processes exactly what the user checked.
- Migrated legacy Web Sources `areas` and `area_id` settings to the clearer `pages` and `page_id` schema without losing existing libraries.
- Refreshed the in-app Helper, repository documentation, release metadata, screenshot, and Windows download guidance.
- Completed the staged architecture cleanup and removed superseded V3 scaffolding, old mockups, duplicate coordinators, retired processing paths, and their dead tests.

## 1.2.2 - 2026-07-16
- Rebuilt startup, state, persistence, imports, editing, presets, export, Batch, and Web Sources around one clear application-service layer instead of overlapping UI-owned workflows.
- Unified static and animated processing so preview and export share the same sizing, transparency, GIF timing, palette, and format decisions.
- Made Final the reliable edited preview: control and preset changes rebuild it from the detected asset baseline, while Reset restores that baseline without stacking old edits.
- Consolidated system and user presets into one compatibility-aware library used by the editor, Preset Studio, automatic recommendations, and Batch.
- Isolated every Batch run from the live workspace and routed interactive and batch exports through the same format, naming, resizing, and encoding plan.
- Rebuilt Web Sources with persistent accumulated results, saved pages, multi-page scans, clear limits, retry handling, filtering, and partial-failure reporting.
- Reworked the desktop shell with responsive splitters, consistent geometry, preview-first sizing, matching dialogs, and clearer Helper guidance.
- Hardened Windows packaging with package-data checks, synchronized version metadata, and an automated frozen-app launch test.

## 1.2.1 - 2026-06-15
- Tightened the main shell spacing and control geometry so the preview studio, toolbar, workflow dock, and settings panel feel more consistent.
- Reworked Web Sources around saved pages, manual page lists, filtered index scanning, and safer scan limits for large sites.
- Cleaned workspace paging/import presentation and removed duplicate or dead preset/import surfaces.
- Improved batch, preset, background-removal, GIF-preview, and export workflows so edits are isolated and easier to verify before export.
- Restored app icon handling, refreshed helper guidance, and cleaned release/repository documentation for upload.

## 1.2.0 - 2026-03-30
- Rebuilt the shell into a cleaner preview-first studio layout with compare/current/final view modes, per-pane reset, and calmer off-white theming.
- Simplified and cleaned the controls/settings surfaces, removed duplicate preset/navigation UI, and refreshed helper copy to match the real app behavior.
- Reworked preset handling with compatibility filtering, animation-safe GIF behavior, a stronger preset manager, and clearer user-preset editing for advanced users.
- Rebuilt batch processing so runs operate on isolated clones, preserve mixed-format export behavior, report failures more clearly, and handle copied edits/presets/background overrides consistently.
- Fixed GIF preview/export behavior so animated assets keep animation in preview/export, stay at sane preview scale, and show clearer transparency/background state.
- Removed the unused backend toggle from the toolbar and processing path so heavy jobs follow one clear execution flow.
- Hardened the one-file Windows release flow and aligned packaging/version metadata for GitHub release publishing.

## 1.1.2 - 2026-03-12
- Hardened Web Sources HTML scan fetch with retry header profiles for blocked hosts (e.g., HTTP 403 fallback pass).
- Added clearer Web Sources scan status messages for HTTP 401/403/429 cases.
- Added regression tests for HTTP 403 scan retry + friendly error mapping.
- Rewrote README for clearer product overview, workflow guidance, and release usage.
## 1.1.1 - 2026-03-12
- Replaced README/UI screenshot with a true full-size capture of the running **Sprite Factory** app window.
- Synced repository docs to reflect the current branded UI state.

## 1.1.0 - 2026-03-12
- Rebranded UI and runtime identity to **Sprite Factory**.
- Moved `Encoding Window` access from top toolbar into `Settings > Export Encoding` and kept full encoding controls.
- Rebuilt Transparency controls to explicitly choose white background behavior:
  - Keep white background
  - Remove white background
- Added alpha-processing support for white-background removal in light pipeline.
- Expanded test coverage for:
  - encoding window button signal wiring
  - white background mode syncing to settings
  - alpha white-background processing behavior
- Refined startup UI behavior to open maximized reliably.
- Cleaned Web Sources behavior to be **custom-only**:
  - removed forced built-in website defaults
  - strips legacy built-in entries from saved settings
  - keeps user-managed source list clean
- Reworked top toolbar session/import actions into cleaner dropdown menus.
- Added and updated the application icon assets.

## 1.0.4 - 2026-03-11
- Repository and release documentation polish.
- URL ingest preflight metadata probe and MIME/signature validation improvements.
- WebP/ICO/TIFF dimension parsing improvements and guard coverage.

## 1.0.3 - 2026-03-09
- Sprite Factory branding pass and export/session workflow improvements.

## 1.0.2 - 2026-03-09
- Session/save/export UX fixes.

## 1.0.1 - 2026-03-09
- Initial SpriteFactory baseline import.
