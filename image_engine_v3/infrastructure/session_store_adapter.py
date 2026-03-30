"""Legacy adapter from v3 workspace contracts to existing Sprite Factory storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from image_engine_app.app.paths import AppPaths, ensure_app_paths
from image_engine_app.app.settings_store import SessionStore
from image_engine_app.engine.models import AssetRecord, SessionState


class LegacySessionStoreWorkspaceRepository:
    """Adapter that preserves existing session/workspace file format compatibility."""

    def __init__(
        self,
        *,
        app_paths: AppPaths | None = None,
        app_data_dir: str | Path | None = None,
    ) -> None:
        self._paths = app_paths or ensure_app_paths(base_dir=app_data_dir)
        self._store = SessionStore(self._paths)

    @property
    def app_paths(self) -> AppPaths:
        return self._paths

    def save_workspace(
        self,
        *,
        session_payload: dict[str, Any],
        assets_payload: list[dict[str, Any]],
        autosave: bool = False,
        name: str | None = None,
    ) -> Path:
        session = SessionState.from_dict(session_payload)

        assets: list[AssetRecord] = []
        for item in assets_payload:
            if not isinstance(item, dict):
                continue
            try:
                assets.append(AssetRecord.from_dict(item))
            except Exception:
                continue

        result = self._store.save_workspace(session, assets, autosave=bool(autosave), name=name)
        return result.path

    def load_workspace(self, path: str | Path) -> dict[str, Any]:
        loaded = self._store.load_workspace(path)
        return {
            "session": loaded.session.to_dict(),
            "assets": [asset.to_dict() for asset in loaded.assets],
            "path": str(loaded.path),
            "autosave": bool(loaded.autosave),
        }

    def load_latest_autosave_workspace(self) -> dict[str, Any] | None:
        loaded = self._store.load_latest_autosave_workspace()
        if loaded is None:
            return None
        return {
            "session": loaded.session.to_dict(),
            "assets": [asset.to_dict() for asset in loaded.assets],
            "path": str(loaded.path),
            "autosave": bool(loaded.autosave),
        }

