# Sprite Factory Web Sources Scaffold Pack

This scaffold adds the Web Sources feature flow:

`Website + Area` -> `Scan` -> select sprites -> `Download`

It is designed to be:
- **Beginner-friendly** with a simple UI flow
- **Non-bloated** with optional smart features
- **Patch-safe** because the UI stays thin and the controller owns the logic

## Where to drop these files

Copy the folders inside this pack into the repository root so paths line up, for example:

- `image_engine_app/ui/main_window/web_sources_panel.py`
- `image_engine_app/engine/ingest/web_sources_rules.py`
- `image_engine_app/engine/ingest/zip_extract.py`
- `image_engine_app/app/web_sources_models.py`

Then follow `image_engine_app/docs/INTEGRATION_CHECKLIST.md`.
