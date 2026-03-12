# image_engine_v3

This is the parallel rebuild scaffold for Sprite Factory v3.

It is intentionally isolated from the current production path (`image_engine_app`) so we can migrate safely.

## Planned Layers

- `domain/`
- `application/`
- `infrastructure/`
- `presentation/`
- `app/`

## Current Progress

- Phase 0 complete: scaffolding and architecture baselines
- Phase 1 complete: session/workspace persistence contracts and legacy adapter
- Phase 2 in progress: workspace state transitions and section-window behavior

## Included In This Step

- `application/contracts.py`: v3 repository and workspace-state contracts
- `application/session_use_cases.py`: workspace persistence use-cases
- `application/workspace_use_cases.py`: workspace ordering, pinning, close/select, and section window transitions
- `infrastructure/session_store_adapter.py`: compatibility adapter to existing v2 session storage
- `infrastructure/workspace_state_adapter.py`: compatibility adapter between v2 workspace/session objects and v3 state

See:
- `docs/V3_REBUILD_PLAN.md`
- `docs/V3_ARCHITECTURE.md`
