# Sprite Factory Build Lock

This file is the single source of truth for **what we are building next**.

**Rule:** When Marcus says **"next step"**, implement the first unchecked item below, then mark it checked and ship a new replacement zip.

---

## Locked Step List

- [x] **1. Webpage Scan depth crawl (safe BFS)**
  - Depth > 0 follows same-domain links up to a max pages cap.
  - Collects `img src`, `srcset`, lazy-load attrs, and direct image links.

- [x] **2. Real export when a local source file exists**
  - If `asset.cache_path` (or equivalent) exists and Pillow is available, export a real image.
  - Otherwise, fall back to stub JSON export (keeps tests + wiring stable).

- [x] **3. Real preview rendering in Before/Current/Final panes**
  - Preview panes render images from `asset.cache_path` (or `source_uri` for local imports).
  - Rescales live on window resize.
  - Uses pixel-safe scaling when `pixel_snap` is enabled.

- [x] **4. Packaging hardening (PyInstaller)**
  - Add icon + version metadata.
  - Ensure Qt plugin paths are reliable (no "platform plugin" errors).
  - Provide both `onedir` (default) and optional `onefile` build outputs.

- [x] **5. Processing pipeline MVP (real pixel changes)**
  - Implement at least: resize (percent/width/height), basic sharpen/denoise placeholders upgraded to real Pillow operations.
  - Output goes to a deterministic working cache so Current/Final can differ.

- [x] **6. Current vs Final cache model**
  - Introduce per-asset derived file paths:
    - before = original/cache
    - current = working output
    - final = export-ready output
  - Preview panes display the correct file per view.

- [x] **7. Session save/load**
  - Save session state + asset list + settings + tab order to disk.
  - Load restores the workspace reliably.

- [x] **8. Audit runner (one command)**
  - Add `python -m app.audit --app-data-dir .\_audit`.
  - Produces `audit_report.md` + `audit_report.json`.

- [x] **9. Webpage Scan quality controls**
  - Min-size filter, filetype filter, duplicate suppression, crawl caps exposed in UI.
  - Optional "Sprite Scan Mode" preset to hide complexity.

- [x] **10. Batch quality upgrades**
  - Auto-group outputs into folders.
  - Per-source rules (GIF vs PNG vs spritesheets) apply different presets.

---

## Definition of "Finished Enough" for a Windows demo

A Windows demo build is considered acceptable when:
- UI never freezes during batch runs
- Webpage scan depth works for sprite pages
- Preview shows real images
- Export writes real images
- PyInstaller build launches cleanly on Windows

- [x] **11. Batch export naming + collision handling**
  - Add naming templates (index / original name / source group).
  - Ensure stable, unique filenames (no overwrites).

- [x] **12. Webpage Scan auto-naming + folder grouping**
  - Optional filename normalization (safe stems).
  - Optional grouping by page title / path segment (for example `pikachu`, `gen1`).

- [x] **13. Animated GIF handling (preserve frames)**
  - Preserve animation frames when exporting GIF.
  - Preview shows first frame + animation badge.

- [x] **14. Preset manager (create/edit/save)**
  - Add a UI dialog to create/edit presets.
  - Save to app-data and load on startup.

- [x] **15. Release polish**
  - README quick-start + troubleshooting.
  - Icons/version strings finalized.
  - Onefile build reliability checklist.

---

## Post-release Step List (Locked)

- [ ] **16. UI automation smoke tests (optional)**
  - Add a minimal Qt UI test harness for basic flows (open, import, batch start/cancel).

- [ ] **17. Spritesheet builder (MVP)**
  - Combine multiple frames/sprites into a grid spritesheet with metadata export.

- [ ] **18. Processing upgrades (pixel-art safe tools)**
  - Add edge grow/shrink, palette clamp, nearest-neighbour scaling controls.

- [ ] **19. Web download manager hardening**
  - Rate limiting, retry/backoff, respect robots/meta nofollow where applicable.

- [ ] **20. Optional update channel scaffold**
  - Add a simple "check for updates" placeholder + release notes view.

