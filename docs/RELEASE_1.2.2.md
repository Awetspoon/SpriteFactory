# Sprite Factory Pro 1.2.2

Sprite Factory Pro 1.2.2 completes the preview-first redesign and focuses on reliable scanning, presets, batch processing, and a cleaner repository.

## Highlights

- Added a compact preset selector directly to the editing tools. It only offers compatible presets for the active asset and updates the final preview immediately.
- Rebuilt Preset Manager around `Use Active Controls`; it saves only changes from the active asset's detected baseline and keeps JSON under optional Advanced controls.
- Consolidated bundled presets into one validated engine catalog shared by Workspace, Preset Studio, recommendations, and Batch; removed overlapping starter variants.
- Added real output-size choices for 2x/3x/4x/8x sprite scaling and 240p through 2160p standard heights without duplicating the underlying pixel settings.
- Rebuilt Batch Manager around one explicit edit source so copied controls, chosen presets, and smart matching cannot stack accidentally.
- Reworked Web Sources for saved pages, one-page or multi-page scanning, linked-page discovery, keyword and format filtering, scan limits, retries, and clearer failures.
- Tightened the editor shell, preview controls, workspace paging, export dock, settings cards, labels, and helper guidance.
- Removed obsolete design drafts, superseded UI/backend modules, generated files, and dead tests from the repository.

## Download

Download `SpriteFactory-v1.2.2-win64.exe` from the GitHub release assets. It is a single-file Windows build and does not require Python.

## Verification

The release is validated with the full automated test suite, compile checks, the repository audit, and a clean one-file PyInstaller build.
