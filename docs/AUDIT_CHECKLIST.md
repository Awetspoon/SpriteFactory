# Sprite Factory Audit Checklist

This checklist defines what "working" means at each stage.
Run the commands from the repository root.

**Rule:** If an item fails, capture the error/traceback and fix before moving on.

---

## 1) Code health

- [ ] Compile sanity: `python -m compileall image_engine_app`
- [ ] Unit tests: `python -m unittest discover -s image_engine_app/tests -p "test_*.py"`

Pass: 0 failures, 0 errors.

---

## 2) App boot

- [ ] Launch: `python -m image_engine_app --app-data-dir .\.local\ui-check`
- [ ] No exceptions on startup
- [ ] Workspace visible

---

## 3) Ingestion

- [ ] Direct image URL load (png/jpg/webp) imports as an asset
- [ ] Folder import loads multiple images without UI freezing
- [ ] Webpage Scan on `https://pokemondb.net/sprites` finds images
- [ ] Depth 0 scans the current page only
- [ ] Depth 1+ follows same-domain links within caps

---

## 4) Processing

- [ ] Applying a preset changes **Current** and/or **Final** output (real pixels)
- [ ] Current remains the working preview
- [ ] Switching Apply Target works (Current / Final / Both)

---

## 5) Batch (async + cancel)

- [ ] Batch run stays responsive (no UI hang)
- [ ] Progress updates stream live
- [ ] Cancel stops cooperatively and returns UI to idle state

---

## 6) Export

- [ ] Export writes real image files when source/derived file exists
- [ ] Export fallback writes a generated placeholder image when source pixels are missing
- [ ] Metadata fallback only appears as the last-resort export path

---

## 7) Packaging (Windows)

- [ ] Onedir build: `powershell -ExecutionPolicy Bypass -File .\build_exe.ps1`
- [ ] EXE launches without Qt plugin errors
- [ ] Optional onefile build works

---

## 8) One-command audit

- [ ] Run: `python -m image_engine_app.app.audit --app-data-dir .\.local\audit`
- [ ] Produces: `.local/audit/audit_report.json` and `.local/audit/audit_report.md`
- [ ] Overall status shows PASS
