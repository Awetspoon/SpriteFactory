# Audit Summary — 2026-03-12

Scope covered in this pass:
- Web Sources scan/download/import flow
- Workspace tab rendering + section/window behavior
- Root launcher/runtime-state hygiene
- Cache-key stability for resolved media downloads
- Repo hygiene cleanup (`__pycache__`, `.pytest_cache`, runtime leftovers)

What changed:
- Rebuilt the Fandom/wiki file-page download path so the app resolves the best direct media URL from the file page instead of grabbing the first page image.
- Added stronger browser-like download headers for Fandom/Wikia family hosts to reduce HTTP 403 failures.
- Kept cache keys stable when a logical source URL resolves to a different raw media URL.
- Added a one-time runtime cache migration in the root launcher so stale Web Sources cache from older broken builds does not keep poisoning imports.
- Simplified workspace behavior for normal-size queues: the Pin Active control is now hidden unless the workspace is actually sectioned.
- Restyled the workspace tab strip so imported assets are visibly present without relying on pinning to make the area understandable.
- Removed repo junk and stale runtime/cache artifacts from the deliverable zip.

What was verified here:
- `python -m compileall` succeeded for the patched source tree.
- 156 non-Qt tests passed in this environment.
- Targeted regression tests were added for direct-media resolution and stable cache-key behavior.

What was not fully verifiable in this environment:
- Full live Qt UI interaction, because PySide6 is not installed in the container.
- Live outbound Fandom downloads, because this container has no outbound network access.

Recommended user-side smoke test after extracting:
1. Launch from repo root with `py .\main.py`
2. Scan the Fandom item-sprites area
3. Download a small batch (5-10 files)
4. Confirm the workspace tabs show the imported sprite filenames directly
5. Confirm the loaded asset is the sprite itself, not the Pokémon Wiki logo
