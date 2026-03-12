# Changelog

## 1.1.2 - 2026-03-12
- Hardened Web Sources HTML scan fetch with retry header profiles for blocked hosts (e.g., HTTP 403 fallback pass).
- Added clearer Web Sources scan status messages for HTTP 401/403/429 cases.
- Added regression tests for HTTP 403 scan retry + friendly error mapping.
- Rewrote README for clearer product overview, workflow guidance, and release usage.
## 1.1.1 - 2026-03-12
- Replaced README/UI screenshot with a true full-size capture of the running **Sprite Factory Pro** app window.
- Synced repository docs to reflect the current branded UI state.

## 1.1.0 - 2026-03-12
- Rebranded UI and runtime identity to **Sprite Factory Pro**.
- Moved `Encoding Window` access from top toolbar into `Settings > Expert Encoding` and kept full expert controls.
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
- Added/updated app icon assets for Clean Pro branding.

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
