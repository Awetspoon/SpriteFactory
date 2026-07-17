Sprite Factory 1.2.4 makes linked-page discovery easier to understand and standardizes the public product identity across the app and release.

![Sprite Factory 1.2.4](sprite-factory-1.2.4-ui.png)

## Clearer Linked-Page Scanning

- **Index or category page** now accepts either a pasted URL or a page chosen from entered and saved sources.
- **Find Linked Pages** only discovers links from that source; it does not scan files or download anything.
- **Filter found pages** is clearly separated and becomes useful after links have been discovered.
- Discovered pages are no longer selected automatically. Choose the pages you want, then use **Scan Selected Pages**.
- The in-app Helper now explains the same order shown in the interface.

## Consistent Product Identity

- The app title, shell name, executable metadata, icon paths, README, screenshots, and release documentation now use **Sprite Factory**.
- Obsolete icon aliases and superseded screenshots have been removed.
- GitHub displays one **Update Notes** title, followed directly by the update details without a repeated heading.

## Reliability

- Added regression tests for direct linked-page URLs and explicit page selection.
- The complete automated suite, structure audit, release metadata checks, executable build, packaged icon check, and frozen-app startup test must pass before publishing.

## Download

Download `SpriteFactory-v1.2.4-win64.exe` from the Assets section below. It runs on 64-bit Windows 10 or Windows 11 and does not require Python.

Windows may show a SmartScreen warning because this community release is not code-signed. Only continue if the file came from the official `Awetspoon/SpriteFactory` release page.
