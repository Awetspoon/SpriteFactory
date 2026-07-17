Sprite Factory 1.2.2 completes the staged rebuild of the editor while preserving the real sprite, image, GIF, preset, web scanning, batch, and export workflows.

## Editing And Preview

- Current always represents the imported source, while Final shows the controls or preset that will be exported.
- Imported assets receive detected format, transparency, animation, and baseline settings before editing begins.
- Presets replace edits from that detected baseline instead of stacking hidden changes.
- Reset All restores the selected asset's detected baseline; pane Reset buttons only restore preview zoom.
- Static and animated previews share the same size, cleanup, detail, color, edge, and background-removal rules used by export.

## Presets, Batch, And Export

- Workspace, Preset Studio, recommendations, and Batch now use one validated system-and-user preset catalog.
- Advanced users can create presets from active controls or maintain a settings delta in Preset Studio.
- Batch preparation runs on copied assets in a separate cache, so queue edits cannot alter the live workspace or Final preview.
- Interactive Export and Batch use the same output format, filename, collision, resize, animation, and encoding decisions.
- Animated GIFs retain frames, timing, looping, transparency, palette, and dithering through preview and export.

## Web Sources

- Scan one page, a manual page list, saved pages from different websites, or selected links discovered from an index page.
- Found files accumulate across successful scans instead of disappearing when another page is scanned.
- Format, search, and hidden-word filters narrow large result sets without changing the stored scan results.
- Scan limits, retries, cancellation, partial failures, and clear network messages make large or unreliable sites safer to use.

## Interface And Reliability

- The preview-first shell now uses responsive splitters, bounded side panels, consistent control geometry, and matching Batch and Preset dialogs.
- Startup, persistence, imports, edits, presets, Web Sources, Batch, and export have clear service boundaries instead of duplicate UI-owned logic.
- Obsolete replacement modules, copied state adapters, dead tests, old screenshots, and superseded processing helpers were removed.

## Download

Download `SpriteFactory-v1.2.2-win64.exe` from the GitHub release assets. Python is not required.

## Verification

The release process runs the complete automated suite, compilation, repository audit, version checks, packaging checks, and a frozen-app launch test before producing the Windows artifact.
