# Sprite Factory V3 Rebuild Plan

## Goal

Rebuild Sprite Factory with a cleaner architecture, stricter module boundaries, and predictable feature flow, while preserving current working behavior during migration.

## Strategy

Use a parallel-track rebuild:

1. Keep current app (`image_engine_app`) as stable production path.
2. Build new architecture in `image_engine_v3`.
3. Migrate features incrementally with regression tests.
4. Switch over only when parity checks pass.

This avoids a risky big-bang rewrite.

## Target Architecture

- `domain/`: core models and pure business rules (no UI, no filesystem).
- `application/`: use-cases, orchestration, and contracts/ports.
- `infrastructure/`: filesystem, settings/session persistence, network/ingest adapters.
- `presentation/`: Qt UI and view-model/controller adapters.
- `app/`: composition root and startup wiring.

## Migration Phases

### Phase 0: Foundation

- Create v3 folder structure and module contracts.
- Define dependency direction (`presentation -> application -> domain`; `infrastructure` plugged via contracts).
- Add baseline smoke tests for v3 package imports.

### Phase 1: Persistence and Session Flow

- Migrate settings/session persistence into infrastructure adapters.
- Keep existing file formats for backward compatibility.
- Add compatibility tests for existing session files.

### Phase 2: Asset Workspace and State

- Port workspace state transitions (active asset, tab order, pinning, section windows).
- Preserve current behavior for <=100 tab sectioning.
- Add behavior tests for pin/section edge cases.

### Phase 3: Presets and Processing Pipeline

- Port preset apply flow, mode gating, and preview/update coordination.
- Keep light/heavy processing behavior unchanged.
- Reuse existing engine logic where possible through adapters.

### Phase 4: UI Rebuild

- Rebuild editor UI against v3 application contracts.
- Keep all current controls, but grouped with strict wiring and no duplicate handlers.
- Add UI behavior tests for critical actions and state sync.

### Phase 5: Batch, Export, and Web Sources

- Port batch runner and export orchestration through application use-cases.
- Port web sources flow with improved error reporting.
- Add end-to-end workflow tests.

### Phase 6: Cutover

- Feature parity checklist complete.
- Release candidate build from v3 entrypoint.
- Keep v2 as fallback until stable release sign-off.

## Non-Negotiable Rules

- No intended feature removals.
- No silent behavior changes.
- Tests required for each migrated feature slice.
- If uncertain, keep behavior and document deviation for review.

## Current Status

- Phase 0 complete: v3 scaffolding and architecture docs created.
- Phase 1 complete: v3 workspace/session persistence contracts + legacy adapter + tests added.
- Phase 2 started: v3 workspace state use-cases, legacy state adapter, and behavior parity tests.

