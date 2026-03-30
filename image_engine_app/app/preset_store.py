"""User preset persistence helpers.

This module stores *user-created* presets (not the built-in defaults) in a single
JSON file under the app data root.

Design goals:
- Keep format stable and human-readable.
- Tolerate partial/invalid entries (skip rather than crash).
- Never require PySide6 (safe for unit tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.settings_store import load_json_file, save_json_file
from image_engine_app.engine.models import PresetModel


PRESETS_SCHEMA = "image_engine_v1.0.1_presets"


def presets_file_path(paths: AppPaths) -> Path:
    return paths.root / "presets.json"


@dataclass(frozen=True)
class PresetStoreLoadResult:
    presets: list[PresetModel]
    path: Path


class PresetStore:
    """File-backed user preset storage."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load_user_presets(self) -> PresetStoreLoadResult:
        path = presets_file_path(self.paths)
        payload = load_json_file(path, default=None)
        if not isinstance(payload, dict):
            return PresetStoreLoadResult(presets=[], path=path)

        raw_items = payload.get("presets", [])
        presets: list[PresetModel] = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                try:
                    presets.append(PresetModel.from_dict(item))
                except Exception:
                    continue
        return PresetStoreLoadResult(presets=presets, path=path)

    def save_user_presets(self, presets: list[PresetModel]) -> Path:
        path = presets_file_path(self.paths)
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "meta": {
                "schema": PRESETS_SCHEMA,
                "saved_at": now.isoformat(),
            },
            "presets": [preset.to_dict() for preset in (presets or [])],
        }
        return save_json_file(path, payload)

