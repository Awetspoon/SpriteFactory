"""App data path helpers for cache, sessions, and exports (Prompt 14)."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


DEFAULT_APP_DIR_NAME = "image_engine_app"
APPDATA_ENV_OVERRIDE = "IMAGE_ENGINE_APPDATA_DIR"


@dataclass(frozen=True)
class AppPaths:
    """Resolved application data directories."""

    root: Path
    cache: Path
    sessions: Path
    exports: Path
    logs: Path
    settings_file: Path


def resolve_app_data_root(
    *,
    app_dir_name: str = DEFAULT_APP_DIR_NAME,
    base_dir: str | Path | None = None,
) -> Path:
    """
    Resolve the app data root directory.

    Priority:
    1) explicit `base_dir`
    2) `IMAGE_ENGINE_APPDATA_DIR`
    3) platform-ish local fallback (`~/.local/share` on non-Windows, `%LOCALAPPDATA%` on Windows)
    """

    if base_dir is not None:
        return Path(base_dir)

    env_override = os.getenv(APPDATA_ENV_OVERRIDE)
    if env_override:
        return Path(env_override)

    if os.name == "nt":
        local_appdata = os.getenv("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / app_dir_name
        return Path.home() / "AppData" / "Local" / app_dir_name

    return Path.home() / ".local" / "share" / app_dir_name


def build_app_paths(
    *,
    app_dir_name: str = DEFAULT_APP_DIR_NAME,
    base_dir: str | Path | None = None,
) -> AppPaths:
    """Build all application data paths without creating them."""

    root = resolve_app_data_root(app_dir_name=app_dir_name, base_dir=base_dir)
    return AppPaths(
        root=root,
        cache=root / "cache",
        sessions=root / "sessions",
        exports=root / "exports",
        logs=root / "logs",
        settings_file=root / "settings.json",
    )


def ensure_app_paths(
    *,
    app_dir_name: str = DEFAULT_APP_DIR_NAME,
    base_dir: str | Path | None = None,
) -> AppPaths:
    """Create the standard app data directories and return the resolved paths."""

    paths = build_app_paths(app_dir_name=app_dir_name, base_dir=base_dir)
    for directory in (paths.root, paths.cache, paths.sessions, paths.exports, paths.logs):
        directory.mkdir(parents=True, exist_ok=True)
    return paths

