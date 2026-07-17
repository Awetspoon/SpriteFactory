# Sprite Factory Staged Rebuild

Sprite Factory is being rebuilt through verified replacements, not by placing a second application over the current one.

## Safety baseline

- GitHub checkpoint: `efc38eb` on `codex/pre-rebuild-checkpoint-1.2.2`
- Baseline automated checks: 349 passing tests
- Existing PNG, GIF, WEBP, JPG, sprite, preset, batch, session, export, and web workflows remain the behavior contract.

## Replacement rule

Every stage follows the same order:

1. Record the current behavior with tests and representative assets.
2. Build one replacement behind a clear boundary.
3. Route the production application through the replacement.
4. Run focused tests, the full suite, compilation, and the repository audit.
5. Delete the replaced implementation and compatibility wiring.
6. Start the next stage only after the application remains usable.

No stage may create a second source of truth for assets, edits, presets, previews, queues, sessions, or exports.

## Target dependency direction

```text
Entrypoint / composition
          |
          v
Application use cases and services
          |
          v
Domain state and pure image engine

Qt UI ----------> application contracts
Infrastructure -> application contracts
```

The image engine must not import the application or Qt UI. Qt widgets must receive composed dependencies instead of constructing controllers, stores, or engine services themselves.

## Stages

### Stage 1: Startup and composition

Status: completed locally and verified.

- `app/bootstrap.py` owns argument parsing and non-visual dependency construction.
- `ui/desktop_runtime.py` owns Qt setup, icons, window state, and the event loop.
- `app/main.py` is now a small entrypoint connecting those two boundaries.
- Architecture tests prevent the bootstrap and engine from depending on Qt presentation code.

### Stage 2: State and persistence

Status: completed locally and verified.

- Workspace state now uses the real `AssetRecord` and `SessionState` models directly.
- Workspace ordering, pinning, selection, close behavior, and 100-item sections live in the active application service layer.
- Session and workspace persistence use the active `SessionStore`, including legacy session-only compatibility.
- The duplicate `image_engine_v3` scaffold, copied-state adapters, and redundant tests have been removed.

### Stage 3: Image processing

Status: completed locally and verified.

- `frame_pipeline.py` owns deterministic in-memory size, AI-preview, cleanup, detail, edge, color, and alpha sequencing.
- `transparency.py` owns edge-connected white/black removal and alpha cleanup, shared with background analysis.
- `animation.py` is the single GIF frame, timing, loop, palette, dithering, transparency, and encoding implementation used by Preview and Export.
- `source_renderer.py` decodes explicit source paths and renders static or animated derived outputs without Qt or asset/UI state.
- `asset_preview.py` and `export_source.py` keep asset-path decisions outside pure pixel processing.
- The former `light_steps.py` monolith, mixed preview/export helper, and duplicate GIF encoder have been removed.
- PNG, JPEG, WEBP, TIFF, BMP, ICO, static GIF, and animated GIF paths are covered by representative fixtures.

### Stage 4: Workspace and imports

Status: completed locally and verified.

- `engine/ingest/import_result.py` is the single result contract for local files, folders, ZIP members, URLs, cached web files, reuse, skips, failures, and cancellation.
- `engine/ingest/local_ingest.py` expands files, folders, and ZIPs deterministically, validates extension/signature agreement, and deduplicates by content hash.
- `app/services/asset_import.py` is the only new-asset preparation path for metadata detection, classification, suggested defaults, and the detected Reset baseline.
- Local and Web Sources ZIP members now use the same preparation path; Qt coordinators no longer extract or construct assets.
- Workspace add and persisted-state replacement now run through `WorkspaceStateService`, including stale-tab cleanup and stable 100-item sections.
- Restored assets retain their saved edits and are not treated as newly imported files.

### Stage 5: Controls and preview

Status: completed locally and verified.

- `app/services/asset_edit.py` is the single application workflow for manual controls, output-size choices, export profiles, edit-state replacement, Final refresh, and detected Reset.
- Qt controls now publish edit requests; they no longer mutate `AssetRecord.edit_state` directly.
- `engine/process/edit_impact.py` separates visible/playback changes from export-only settings such as DPI, quality, compression, metadata, and frame optimization.
- Current resolves only to the imported source. The obsolete derived-Current path and two-view edit-target model have been removed.
- Visible edits invalidate stale generated output before rebuilding Final; failed rendering falls back to the source instead of showing an older edit.
- The first active display uses the exact source for both Current and Final. A derived Final is created only after a visible edit.
- Import detection records source metadata and recommendations but never applies enhancement or export suggestions automatically.
- Presets replace the one edit state from the source baseline, Reset restores that same baseline, and queued heavy work remains explicit.

### Stage 6: Presets

Status: completed locally and verified.

- `app/services/preset_library.py` owns the one ordered system/user catalog, validation, compatibility entries, and the only user-preset store access.
- `engine/process/preset_application.py` is the shared compatibility, detected-baseline replacement, mode-promotion, and heavy-job planning contract.
- `app/services/preset_workflow.py` applies catalog presets through `AssetEditService`, with an explicit no-preview path for imports and isolated Batch preparation.
- Workspace presets, chosen Batch presets, and smart Batch presets now use the same plan instead of maintaining separate application rules. Import recommendations remain advice until explicitly selected.
- Preset selection no longer stacks stale edits, compatibility-only lists no longer fall back to unusable choices, and Reset continues to restore the detected asset baseline.
- Presets containing heavy AI controls are normalized during catalog validation even if an advanced user omitted the heavy-processing flags.
- Chosen Batch presets no longer render temporary Final files before the queue starts; Batch rendering and heavy execution remain isolated from the live workspace.

### Stage 7: Export and Batch

Status: completed locally and verified.

- `engine/export/format_resolver.py` is the single AUTO-format and filename-extension authority for prediction, encoding, interactive Export, and Batch.
- `engine/export/asset_export.py` builds one source, final-size, profile, format, folder, naming, collision, and encoder plan for every asset.
- Interactive Export and Batch now use that same plan, so the prediction label, output extension, encoded format, and resized dimensions agree.
- Batch preparation and execution live in `app/services/batch_workflow.py`; Qt no longer owns asset cloning, preset application, or engine queue construction.
- Every Batch run operates on copied assets in a separate Batch cache, preserving the live workspace, active Final preview, and controls.
- Animated GIF exports continue from the source container so all frames remain live while edits, background removal, timing, looping, palette, and dithering are applied.
- Missing/stale derived paths fall back to an available source, naming collisions remain safe, and failed encoder results now mark the individual queue item as failed with its real error.
- The duplicate Batch predictor/exporter, format maps, source-selection wrappers, and UI Batch-preparation module have been removed.

### Stage 8: Web Sources

Status: completed locally and verified.

- `app/services/web_sources_workflow.py` is the single owner of saved-page selection, linked pages, persistent Found Files, scan planning, result accumulation, download options, and settings persistence.
- `web_sources_registry.py`, `web_sources_scanner.py`, `web_sources_downloader.py`, and `web_sources_network.py` separate saved shortcuts, page discovery/scanning, file retrieval/import, and network diagnostics.
- Entered URLs, saved pages from several websites, and selected linked pages now create the same typed scan request and use the same capped scanner.
- Successful files accumulate by normalized URL; repeated links, individual failed pages, cancellation, and hard scan failures do not erase earlier results.
- Qt renders state and coordinates progress only. It no longer owns the saved registry, Found Files store, network wording, sockets, retries, or scan merging.
- The retired combined Web Sources service and duplicate controller wrappers have been removed.

### Stage 9: UI shell

Status: completed locally and verified.

- `ui/common/shell_tokens.py` is the single source for shell dimensions, panel bounds, responsive thresholds, and core colors.
- The fixed Workspace/Preview/Settings row has been replaced by one bounded splitter. Workspace and Settings retain useful limits while Preview receives all remaining space.
- The minimum 1180x760 layout now fits without horizontal overlap; the Preview header and export footer deliberately reflow at narrow editor widths.
- Reset Shell restores both preview mode and the intended three-column proportions after Compact UI or manual splitter changes.
- Settings tiles, workspace paging, tool menus, status badges, export controls, scrollbars, and top-toolbar controls now share matching outer dimensions.
- Batch and Preset windows use the same shell cards, spacing, progress, selection, splitter, and primary-action styling. Hidden duplicate Batch selection buttons were removed.
- Responsive geometry and architecture checks now protect the supported minimum and normal desktop layouts.
- Verification completed with 406 passing tests, full compilation, visual renders at 1180 and 1600 pixels wide, and a clean repository audit.

### Stage 10: Packaging and release

Status: completed locally and verified.

- The in-app Helper and repository documentation now describe the rebuilt File, Workspace, Final preview, settings, presets, Web Sources, Batch, reset, and export workflows.
- Release metadata is synchronized across `pyproject.toml`, the window title, PyInstaller version resources, release notes, and the current real-application screenshot.
- PyInstaller collects only the runtime icons, default Web Sources JSON, and shared UI SVG; repository Markdown and local test caches are excluded from the executable.
- `build_exe_onefile.ps1` uses guarded workspace cleanup, runs the full suite, embeds the current icon/version, launches the frozen application in smoke-test mode, and verifies the real UI shell before copying the artifact.
- The resulting `.local/release/SpriteFactory-v1.2.2-win64.exe` reports version 1.2.2 and passed the packaged icon and startup checks.
- Verification completed with 407 passing tests, full compilation, release-metadata checks, a clean repository audit, and the frozen one-file application smoke test.
