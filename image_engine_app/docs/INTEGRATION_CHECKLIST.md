# Import and Web Sources Integration

Sprite Factory uses one import contract for local files, folders, ZIPs, direct URLs, downloaded web files, and cached web files.

## Ownership

- `engine/ingest/import_result.py` describes imported assets, reuse, duplicates, unsupported sources, failures, and cancellation.
- `engine/ingest/local_ingest.py` scans local sources, safely expands ZIPs, validates signatures, and deduplicates content.
- `engine/ingest/url_ingest.py` validates and downloads one URL into the cache.
- `app/services/asset_import.py` detects metadata and prepares new assets for the workspace.
- `app/services/web_sources_workflow.py` plans scans and owns linked pages plus accumulated Found Files.
- `app/services/web_sources_scanner.py` discovers pages and scans page lists; `web_sources_downloader.py` retrieves and imports selected files through `AssetImportService`.
- `app/services/workspace_state.py` is the only owner of workspace addition, restored-state replacement, ordering, pinning, and 100-item sections.

## Required flow

1. Resolve selected sources into an `ImportResult`.
2. Prepare new entries through `AssetImportService` exactly once.
3. Register `result.assets` through `WorkspaceCoordinator`.
4. Show counts from the result without rebuilding or reclassifying its assets.
5. Load saved workspace assets directly so persisted edits are preserved.

## Behavior checks

- A mixed file and ZIP selection enters the workspace through one controller call.
- Folder imports remain deterministic and preserve relative queue paths.
- Duplicate content is skipped even when filenames differ.
- Cached web files are marked reused but still return a workspace asset.
- Web ZIP members receive the same metadata and detected controls as local files.
- Invalid archive members cannot escape the extraction directory.
- Adding more than 100 assets selects and displays the correct section.
- Restoring a workspace removes stale tab and pin IDs without resetting saved controls.
