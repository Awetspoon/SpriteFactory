# Sprite Factory V3: Settings Slice

## Why this slice matters

The right-side settings panel already exposes a lot of power, but it is still a large monolithic surface.
This makes the app feel heavier than it needs to, even when the underlying controls are working correctly.

## What landed in this slice

- a live settings header that summarizes the active asset, mode, format, and capabilities
- quick-jump buttons for high-traffic groups (`Pixel and Resolution`, `Cleanup`, `Transparency`, `Export`)
- clearer toolbox styling so sections read like intentional cards instead of a long accordion
- helper state for the header summary plus focused tests for summary and quick-jump behavior

## Rebuild direction

1. Keep existing control wiring stable while improving navigation and scanability first.
2. Move summary and navigation logic into helper/view-model state instead of burying it in the widget.
3. Split the giant settings panel into smaller section builders once the top-level UX is stable.
4. Reuse the same section metadata in v3 presentation so the rebuild does not fork behavior.

## Next steps

- extract per-section builder helpers from `settings_panel.py`
- add section-level defaults/recommendations for pixel-art vs photo assets
- introduce compact/advanced settings presets in the header area
- prepare a v3 settings presentation shell that can host the same grouped sections
