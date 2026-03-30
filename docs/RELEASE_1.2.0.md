# Sprite Factory Pro 1.2.0

![Sprite Factory Pro 1.2.0](sprite-factory-ui.png)

## Highlights

- Rebuilt the shell into a cleaner preview-first studio layout.
- Added `Compare View`, `Current Only`, and `Final Only`, with `Reset Shell` restoring the full compare layout.
- Added per-pane preview reset so both preview panels can return to fit view quickly.
- Tightened controls, reduced duplicate UI, and removed dead or confusing preset/navigation surfaces.
- Refreshed the helper text so it explains the app as it works today.

## Editing And Preview

- Preset picks now refresh the final preview so changes can be judged before export.
- `Reset Edits` is now clearly separated from `Reset View`.
- Animated GIF preview/export behavior was rebuilt so animation survives edits and export more reliably.
- Animated assets now only surface animation-safe presets in quick pickers and batch tools.
- Background detection is clearer, and transparent content is easier to judge in preview.

## Batch And Export

- Batch processing now runs on isolated clones instead of mutating live workspace assets.
- Mixed-format batch export was hardened across PNG, JPG, WEBP, BMP, TIFF, ICO, sprite sheets, and GIFs.
- Batch wording and failure reporting were cleaned up so runs are easier to understand.
- One-file Windows packaging is now aligned for a cleaner GitHub release flow.

## Presets And Advanced Use

- Preset compatibility is stricter so obviously bad matches are filtered out.
- The preset manager is clearer for advanced users:
  - duplicate a system template
  - edit the JSON delta
  - save your own user preset

## Performance Mode

- `CPU` / `GPU` is now wired honestly through the heavy-processing path.
- If a real GPU backend is not available, the app cleanly falls back to CPU instead of pretending GPU is active.
