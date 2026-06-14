# SpriteFactory V2 Lock-In Rebuild Plan

## Goal (Plain English)
- Rebuild the UI/controls/workflow cleanly from the ground up.
- Keep the working engine/export/session logic where possible.
- Keep editing controls reliable and clear.
- Keep preview as the main focus.
- Avoid losing features from the current program.

## Lock-In Baseline
- Reference project (current working code): `SpriteFactory_Windows_Python`
- Rebuild workspace (new): `SpriteFactory_Windows_Python_V2`

## What We Keep
- Queue + review flow (`Keep / Reject / Unreviewed`)
- Per-image saved settings snapshots
- Threaded preview / export / URL import / auto-group workers
- ZIP + manifest export pipeline
- Session save/load + autosave restore behavior (compatibility target)
- URL import strategy/filter concepts (generic any-URL support)

## What We Rebuild Cleanly
- Controls area architecture
- Preview-first layout
- Clean editing workflow UX
- Control grouping/category labeling (plain English first)
- Duplicate/confusing settings presentation
- Visibility logic and layout breakage issues

## Core V2 Architecture Direction
1. Preview-first center panel
2. Clean controls shell structure
3. One canonical settings state (no duplicate logic paths)
4. Common controls use safe defaults
5. Deeper controls remain organized and stable

## Planned Build Phases
### Phase 1 - Feature Inventory (No heavy coding)
- List every working feature from the baseline
- Mark: Keep / Redesign UI / Remove / Defer
- Document current snapshot/session keys for compatibility

### Phase 2 - V2 UX Spec (Plain English)
- Final layout blueprint (Queue / Preview / Controls)
- Editing behavior and apply order
- Category mapping (Pixel & Resolution, Color & Light, Detail, Cleanup, Edges, Transparency, AI Enhance, Export)
- Preview / Checks placement rules

### Phase 3 - V2 UI Foundation
- New main layout shell
- Preview containment and sizing
- Controls shell stack
- Shared canonical settings bindings

### Phase 4 - Inspector Rebuild
- Guided controls in plain English
- Organized depth for experienced users
- Dense controls stay stable and predictable

### Phase 5 - Integration + Compatibility
- Session/autosave compatibility checks
- Per-image snapshot compatibility checks
- URL import/preview/background auto-detect polish

### Phase 6 - Full Audit + Release
- Regression audit
- Duplicate/dead code scan
- Clean build and release EXE

## Immediate Next Step
- Start Phase 1 inventory from the locked baseline project and write `docs/V2_FEATURE_INVENTORY.md`.
