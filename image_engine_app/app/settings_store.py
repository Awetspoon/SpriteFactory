"""User settings and session persistence helpers (Prompt 14)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from image_engine_app.app.paths import AppPaths
from image_engine_app.engine.models import AssetRecord, SessionState


def load_json_file(path: str | Path, *, default: Any = None) -> Any:
    """Load JSON from disk, returning `default` if the file does not exist."""

    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def save_json_file(path: str | Path, payload: Any) -> Path:
    """Save JSON atomically to disk."""

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    tmp_path.replace(file_path)
    return file_path


def load_user_settings(paths: AppPaths) -> dict[str, Any]:
    """Load user settings JSON, returning an empty dict when absent."""

    payload = load_json_file(paths.settings_file, default={})
    if not isinstance(payload, dict):
        return {}
    return payload


def save_user_settings(paths: AppPaths, settings: dict[str, Any]) -> Path:
    """Persist user settings JSON."""

    return save_json_file(paths.settings_file, settings)


_PATH_PREFERENCE_UNSET = object()


def _normalize_optional_path(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def load_path_preferences(paths: AppPaths) -> dict[str, str | None]:
    """Load remembered user-facing folder paths for sessions and exports."""

    settings = load_user_settings(paths)
    block = settings.get("paths") if isinstance(settings, dict) else None
    if not isinstance(block, dict):
        block = {}
    return {
        "last_session_dir": _normalize_optional_path(block.get("last_session_dir")),
        "last_export_dir": _normalize_optional_path(block.get("last_export_dir")),
    }


def save_path_preferences(
    paths: AppPaths,
    *,
    last_session_dir: Any = _PATH_PREFERENCE_UNSET,
    last_export_dir: Any = _PATH_PREFERENCE_UNSET,
) -> Path:
    """Persist remembered user-facing folder paths without disturbing other settings."""

    settings = load_user_settings(paths)
    block = settings.get("paths")
    if not isinstance(block, dict):
        block = {}

    if last_session_dir is not _PATH_PREFERENCE_UNSET:
        block["last_session_dir"] = _normalize_optional_path(last_session_dir)
    if last_export_dir is not _PATH_PREFERENCE_UNSET:
        block["last_export_dir"] = _normalize_optional_path(last_export_dir)

    settings["paths"] = block
    return save_user_settings(paths, settings)


DEFAULT_WEB_SOURCES_OPTIONS: dict[str, bool] = {
    "show_likely": False,
    "auto_sort": False,
    "skip_duplicates": True,
    "allow_zip": True,
}


DEFAULT_WEB_SOURCES_REGISTRY: list[dict[str, Any]] = []

# Legacy built-ins from older releases are removed automatically so the
# website list is user-defined only.
LEGACY_BUILTIN_WEB_SOURCE_IDS: set[str] = {
    "pokemon_db",
    "project_pokemon",
    "pokeapi",
}


def default_web_sources_registry() -> list[dict[str, Any]]:
    """Return bundled default Web Sources entries.

    Defaults are intentionally empty so users control the list end-to-end.
    """

    return [dict(item) for item in DEFAULT_WEB_SOURCES_REGISTRY]


def _strip_legacy_builtin_sources(registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove legacy built-in website entries from persisted settings."""

    out: list[dict[str, Any]] = []
    for entry in registry:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("id", "")).strip().lower()
        if source_id in LEGACY_BUILTIN_WEB_SOURCE_IDS:
            continue
        out.append(dict(entry))
    return out


def load_web_sources_settings(paths: AppPaths) -> dict[str, Any]:
    """Load normalized `web_sources` settings block from user settings."""

    settings = load_user_settings(paths)
    block = settings.get("web_sources") if isinstance(settings, dict) else None
    if not isinstance(block, dict):
        block = {}

    defaults_registry = default_web_sources_registry()
    registry_raw = block.get("registry")
    if isinstance(registry_raw, list):
        registry = _strip_legacy_builtin_sources(registry_raw)
    else:
        registry = defaults_registry

    last_raw = block.get("last_selected")
    last_selected = last_raw if isinstance(last_raw, dict) else {}

    options_raw = block.get("options")
    options = dict(DEFAULT_WEB_SOURCES_OPTIONS)
    if isinstance(options_raw, dict):
        for key in DEFAULT_WEB_SOURCES_OPTIONS.keys():
            if key in options_raw:
                options[key] = bool(options_raw[key])

    return {
        "registry": registry,
        "last_selected": {
            "website_id": (str(last_selected.get("website_id")) if last_selected.get("website_id") else None),
            "area_id": (str(last_selected.get("area_id")) if last_selected.get("area_id") else None),
        },
        "options": options,
    }


def save_web_sources_settings(
    paths: AppPaths,
    *,
    registry: list[dict[str, Any]] | None = None,
    last_selected: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> Path:
    """Persist the `web_sources` settings block while preserving other settings."""

    settings = load_user_settings(paths)
    current = load_web_sources_settings(paths)

    next_registry = registry if registry is not None else current["registry"]
    next_last = dict(current["last_selected"])
    if isinstance(last_selected, dict):
        if "website_id" in last_selected:
            next_last["website_id"] = str(last_selected["website_id"]) if last_selected["website_id"] else None
        if "area_id" in last_selected:
            next_last["area_id"] = str(last_selected["area_id"]) if last_selected["area_id"] else None

    next_options = dict(DEFAULT_WEB_SOURCES_OPTIONS)
    next_options.update(current["options"] if isinstance(current.get("options"), dict) else {})
    if isinstance(options, dict):
        for key in DEFAULT_WEB_SOURCES_OPTIONS.keys():
            if key in options:
                next_options[key] = bool(options[key])

    settings["web_sources"] = {
        "registry": next_registry,
        "last_selected": next_last,
        "options": next_options,
    }
    return save_user_settings(paths, settings)


@dataclass(frozen=True)
class SessionSaveResult:
    """Result metadata for a session save/autosave operation."""

    path: Path
    autosave: bool
    session_id: str
    saved_at: datetime


@dataclass(frozen=True)
class WorkspaceLoadResult:
    """Loaded workspace bundle containing session metadata + persisted assets."""

    session: SessionState
    assets: list[AssetRecord]
    path: Path
    autosave: bool


class SessionStore:
    """File-backed session persistence and crash recovery helper."""

    AUTOSAVE_PREFIX = "autosave_"
    SESSION_PREFIX = "session_"

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.paths.sessions.mkdir(parents=True, exist_ok=True)

    def save_session(
        self,
        session: SessionState,
        *,
        name: str | None = None,
        autosave: bool = False,
        saved_at: datetime | None = None,
    ) -> SessionSaveResult:
        """Save a session JSON file. `autosave=True` targets crash recovery files."""

        timestamp = saved_at or datetime.now(timezone.utc)
        filename = self._session_filename(
            session=session,
            autosave=autosave,
            timestamp=timestamp,
            name=name,
        )
        return self.save_session_to_path(
            self.paths.sessions / filename,
            session,
            autosave=autosave,
            saved_at=timestamp,
        )

    def save_session_to_path(
        self,
        path: str | Path,
        session: SessionState,
        *,
        autosave: bool = False,
        saved_at: datetime | None = None,
    ) -> SessionSaveResult:
        """Save a session JSON file directly to the provided path."""

        timestamp = saved_at or datetime.now(timezone.utc)
        payload = self._session_payload(session, autosave=autosave, timestamp=timestamp)
        file_path = save_json_file(path, payload)
        if autosave:
            self._prune_other_autosaves(file_path)
        return SessionSaveResult(path=file_path, autosave=autosave, session_id=session.session_id, saved_at=timestamp)

    def autosave_session(self, session: SessionState, *, saved_at: datetime | None = None) -> SessionSaveResult:
        """Write an autosave file used for crash recovery restore."""

        return self.save_session(session, autosave=True, saved_at=saved_at)

    def save_workspace(
        self,
        session: SessionState,
        assets: list[AssetRecord],
        *,
        name: str | None = None,
        autosave: bool = False,
        saved_at: datetime | None = None,
    ) -> SessionSaveResult:
        """Save a workspace bundle (session + asset records) as JSON."""

        timestamp = saved_at or datetime.now(timezone.utc)
        filename = self._session_filename(
            session=session,
            autosave=autosave,
            timestamp=timestamp,
            name=name,
        )
        return self.save_workspace_to_path(
            self.paths.sessions / filename,
            session,
            assets,
            autosave=autosave,
            saved_at=timestamp,
        )

    def save_workspace_to_path(
        self,
        path: str | Path,
        session: SessionState,
        assets: list[AssetRecord],
        *,
        autosave: bool = False,
        saved_at: datetime | None = None,
    ) -> SessionSaveResult:
        """Save a workspace bundle directly to the provided path."""

        timestamp = saved_at or datetime.now(timezone.utc)
        payload = self._workspace_payload(session, assets, autosave=autosave, timestamp=timestamp)
        file_path = save_json_file(path, payload)
        if autosave:
            self._prune_other_autosaves(file_path)
        return SessionSaveResult(path=file_path, autosave=autosave, session_id=session.session_id, saved_at=timestamp)

    def autosave_workspace(
        self,
        session: SessionState,
        assets: list[AssetRecord],
        *,
        saved_at: datetime | None = None,
    ) -> SessionSaveResult:
        """Write a workspace autosave bundle for crash recovery restore."""

        return self.save_workspace(session, assets, autosave=True, saved_at=saved_at)

    def load_session(self, path: str | Path) -> SessionState:
        """Load a session JSON file and deserialize SessionState."""

        payload = load_json_file(path)
        if not isinstance(payload, dict) or "session" not in payload:
            raise ValueError(f"Invalid session file payload: {path}")
        return SessionState.from_dict(payload["session"])

    def load_workspace(self, path: str | Path) -> WorkspaceLoadResult:
        """Load a workspace bundle from disk, tolerating legacy session-only files."""

        file_path = Path(path)
        payload = load_json_file(file_path)
        if not isinstance(payload, dict) or "session" not in payload:
            raise ValueError(f"Invalid session file payload: {path}")

        session = SessionState.from_dict(payload["session"])
        raw_assets = payload.get("assets", [])
        assets: list[AssetRecord] = []
        if isinstance(raw_assets, list):
            for item in raw_assets:
                if isinstance(item, dict):
                    try:
                        assets.append(AssetRecord.from_dict(item))
                    except Exception:
                        continue

        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        autosave = bool(meta.get("autosave", file_path.name.startswith(self.AUTOSAVE_PREFIX)))
        return WorkspaceLoadResult(session=session, assets=assets, path=file_path, autosave=autosave)

    def list_session_files(self, *, include_autosaves: bool = True) -> list[Path]:
        """List session JSON files, newest first by modification time."""

        files = sorted(
            (p for p in self.paths.sessions.glob("*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if include_autosaves:
            return files
        return [p for p in files if not p.name.startswith(self.AUTOSAVE_PREFIX)]

    def load_latest_autosave(self) -> SessionState | None:
        """Load the most recent autosave session, or None if no autosaves exist."""

        autosaves = [p for p in self.list_session_files(include_autosaves=True) if p.name.startswith(self.AUTOSAVE_PREFIX)]
        if not autosaves:
            return None
        return self.load_session(autosaves[0])

    def load_latest_autosave_workspace(self) -> WorkspaceLoadResult | None:
        """Load the most recent autosave workspace bundle, or None if unavailable."""

        autosaves = [p for p in self.list_session_files(include_autosaves=True) if p.name.startswith(self.AUTOSAVE_PREFIX)]
        if not autosaves:
            return None
        return self.load_workspace(autosaves[0])

    def clear_autosaves(self) -> int:
        """Delete all autosave files. Returns number removed."""

        removed = 0
        for path in self.paths.sessions.glob(f"{self.AUTOSAVE_PREFIX}*.json"):
            if path.is_file():
                path.unlink()
                removed += 1
        return removed

    def _session_filename(
        self,
        *,
        session: SessionState,
        autosave: bool,
        timestamp: datetime,
        name: str | None,
    ) -> str:
        prefix = self.AUTOSAVE_PREFIX if autosave else self.SESSION_PREFIX
        stamp = timestamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_name = _slugify(name) if name else session.session_id
        return f"{prefix}{safe_name}_{stamp}.json"

    def _session_payload(
        self,
        session: SessionState,
        *,
        autosave: bool,
        timestamp: datetime,
    ) -> dict[str, Any]:
        return {
            "meta": {
                "autosave": autosave,
                "saved_at": timestamp.isoformat(),
                "schema": "image_engine_v1.0.1",
            },
            "session": session.to_dict(),
        }

    def _workspace_payload(
        self,
        session: SessionState,
        assets: list[AssetRecord],
        *,
        autosave: bool,
        timestamp: datetime,
    ) -> dict[str, Any]:
        return {
            "meta": {
                "autosave": autosave,
                "saved_at": timestamp.isoformat(),
                "schema": "image_engine_v1.0.1",
                "workspace_bundle": True,
            },
            "session": session.to_dict(),
            "assets": [asset.to_dict() for asset in (assets or [])],
        }

    def _prune_other_autosaves(self, keep_path: str | Path) -> int:
        removed = 0
        keep = Path(keep_path).resolve()
        for path in self.paths.sessions.glob(f"{self.AUTOSAVE_PREFIX}*.json"):
            if not path.is_file():
                continue
            try:
                current = path.resolve()
            except OSError:
                current = path
            if current == keep:
                continue
            path.unlink()
            removed += 1
        return removed


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "session"





