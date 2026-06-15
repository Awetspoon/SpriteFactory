# image_engine_v3

This package holds the workspace/session service layer used by the current Sprite Factory app.

It stays separate from `image_engine_app` so the production UI can depend on cleaner application,
domain, and infrastructure contracts without mixing that logic into the window code.

## Layers

- `domain/`
- `application/`
- `infrastructure/`
- `presentation/`
- `app/`

## Included

- `application/contracts.py`: v3 repository and workspace-state contracts
- `application/session_use_cases.py`: workspace persistence use-cases
- `application/workspace_use_cases.py`: workspace ordering, pinning, close/select, and section window transitions
- `infrastructure/session_store_adapter.py`: compatibility adapter to existing v2 session storage
- `infrastructure/workspace_state_adapter.py`: compatibility adapter between v2 workspace/session objects and v3 state
