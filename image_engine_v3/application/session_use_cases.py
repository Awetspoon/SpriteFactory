"""V3 workspace/session persistence use-cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from image_engine_v3.application.contracts import WorkspaceRepository


class WorkspacePersistenceService:
    """Application use-case wrapper around workspace persistence ports."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    def save_workspace_bundle(
        self,
        *,
        session_payload: dict[str, Any],
        assets_payload: list[dict[str, Any]] | None = None,
        autosave: bool = False,
        name: str | None = None,
    ) -> Path:
        if not isinstance(session_payload, dict):
            raise ValueError("session_payload must be a dict")
        payload_assets = assets_payload or []
        if not isinstance(payload_assets, list):
            raise ValueError("assets_payload must be a list")

        normalized_assets: list[dict[str, Any]] = []
        for item in payload_assets:
            if isinstance(item, dict):
                normalized_assets.append(item)

        return self._repository.save_workspace(
            session_payload=session_payload,
            assets_payload=normalized_assets,
            autosave=bool(autosave),
            name=name,
        )

    def load_workspace_bundle(self, path: str | Path) -> dict[str, Any]:
        payload = self._repository.load_workspace(path)
        if not isinstance(payload, dict):
            raise ValueError("workspace payload must be a dict")
        payload.setdefault("assets", [])
        return payload

    def load_latest_autosave_bundle(self) -> dict[str, Any] | None:
        payload = self._repository.load_latest_autosave_workspace()
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ValueError("autosave payload must be a dict")
        payload.setdefault("assets", [])
        return payload
