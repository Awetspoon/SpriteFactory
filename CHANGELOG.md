# Changelog

## Unreleased
- Release polish docs added (README + troubleshooting + release checklist).
- URL ingest: implemented bounded stream preview metadata probe with MIME/signature validation.
- URL ingest: added WebP/ICO/TIFF dimension parsing (including WebP chunk scanning) and resolution-guard coverage.
- UI controller: wired best-effort stream preview preflight into URL import with preview metadata in summary.
- Main window: URL import status now includes preview details; bulk webpage imports disable preview preflight for speed.
- Packaging: hardened PyInstaller spec root/version handling and fixed PreviewPanel startup regression used by app + packaged EXE.

