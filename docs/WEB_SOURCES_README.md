# Web Sources

Web Sources finds sprite and image files on public web pages and imports selected files into the Sprite Factory workspace.

## Workflow

All page sources use the same scan request:

`Entered URLs, Saved Pages, or Selected Linked Pages -> Page Scanner -> Found Files -> Download Selected -> Workspace`

The page scanner, linked-page discovery, saved-page registry, connection check, and downloader are separate operations. This prevents a menu action from accidentally calling the wrong behavior.

## 1. Scan Pages

- Paste one complete page URL per line.
- URLs can come from different websites.
- **Scan Pages** validates and deduplicates the list before scanning.
- Scans over 100 pages require confirmation and are capped at 100 pages.
- **More** contains Save Entered Pages, Check First URL, Include uncertain image links, and Clear Entered URLs.

## 2. Saved Pages

- **Save Entered Pages** groups exact page URLs under their website host.
- Check one page, several pages, or an entire website row.
- Checked pages from several websites can be scanned together.
- **Scan Selected** uses the same scanner as entered and linked URLs.
- **More** contains only saved-page selection, connection, and removal actions.
- Saved-page changes do not clear Found Files.

## 3. Find Linked Pages

- Use this optional section for an index, category, or directory page.
- **Discover from** explicitly shows which entered or saved page will be inspected.
- **Find Pages** discovers page links but does not scan their files.
- Search and select the discovered pages, then use **Scan Selected**.
- **More** contains only selection and clear actions for linked pages.

## 4. Found Files

- Found Files persists across separate scans.
- New scan results are merged by normalized file URL.
- Failed scans and duplicate links do not remove successful earlier results.
- Search matches filename, URL, and source page.
- Hide words removes matching rows from view without deleting them.
- File Types controls PNG, GIF, WEBP, JPG/JPEG, and ZIP visibility.
- **More** contains Select All Visible Files, Clear File Selection, and Clear Found Files.

## Download

- **Download Options** controls skipping files already downloaded and ZIP extraction.
- **Download Selected** imports selected files into the workspace.
- Smart routing places assets into Main, Shiny, Animated, or Items.
- Only **Clear Found Files** empties the persistent result basket.

## Ownership

- `web_sources_panel.py` renders state and emits typed user requests.
- `web_sources_coordinator.py` validates requests, controls progress, and calls services.
- `web_sources_service.py` scans pages, discovers links, downloads files, and creates assets.
- `web_sources_models.py` defines request contracts and the Found Files store.
- `settings_store.py` persists saved pages, the last selected page, and scan/download options.

## Network Failures

Website failures are reported per page when possible, while successful pages are retained. HTTP 403/429 normally means the remote website blocked or rate-limited the request. HTTP 500/502/503/504 means the remote server failed. Connection checks test one selected URL and never start a scan.
