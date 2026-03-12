# Web Sources - Feature Spec (Non-bloated + Smart)

## Goal
Inside Sprite Factory, users can:
1) Pick a **Website**
2) Pick an **Area** (a saved URL)
3) **Scan** for real downloadable sprite files
4) Select what they want
5) **Download** into the app library
6) Resize/export like normal

## Smart Layer (optional toggles)
- **Confidence badges**: Direct / Likely
- **Auto-sort**: puts files into Normal/Shiny/Animated/Items based on filename rules
- **Skip duplicates**: avoids re-importing same file name
- **ZIP import**: downloads zip, extracts images only, imports results

## Default behavior (beginner-safe)
- Show likely links: OFF
- Auto-sort downloads: OFF
- Skip duplicates: ON
- ZIP support: ON

## What we do NOT do in v1
- Login/cookies
- Multi-page crawling
- Bypassing protections
- AI guessing Pokemon names

## Files added by this scaffold
- `ui/main_window/web_sources_panel.py` (tab panel)
- `engine/ingest/web_sources_rules.py` (smart rules)
- `engine/ingest/zip_extract.py` (safe zip extraction)
- `app/web_sources_models.py` (dataclasses shared by UI/controller)

## Controller responsibilities
The controller should:
- load/save the web sources registry in settings
- call existing `webpage_scan.py` to harvest URLs
- call existing `url_ingest.py` to download
- import into library folders + refresh library

