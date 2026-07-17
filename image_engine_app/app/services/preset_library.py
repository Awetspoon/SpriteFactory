"""Preset library management for system + user presets."""

from __future__ import annotations

from dataclasses import dataclass

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.preset_store import PresetStore
from image_engine_app.engine.models import EditState, PresetModel
from image_engine_app.engine.process.edit_baseline import implied_heavy_jobs
from image_engine_app.engine.process.preset_compat import (
    PresetCatalogEntry,
    describe_asset_scope,
    describe_preset_scope,
    preset_catalog_entry,
)
from image_engine_app.engine.process.presets_apply import PresetApplyError, apply_preset_to_edit_state


@dataclass(frozen=True)
class PresetLibraryState:
    """Snapshot-friendly preset collections."""

    system_presets: dict[str, PresetModel]
    user_presets: dict[str, PresetModel]
    presets: dict[str, PresetModel]


class PresetLibrary:
    """Owns preset catalog ordering, persistence, and validation."""

    def __init__(
        self,
        *,
        system_presets: dict[str, PresetModel],
        app_paths: AppPaths | None = None,
    ) -> None:
        self._app_paths = app_paths
        self._system_presets = dict(system_presets)
        self._user_presets: dict[str, PresetModel] = {}
        self._presets: dict[str, PresetModel] = dict(self._system_presets)

        self._validate_system_presets()
        if self._app_paths is not None:
            self._load_user_presets()

    @property
    def state(self) -> PresetLibraryState:
        return PresetLibraryState(
            system_presets=dict(self._system_presets),
            user_presets=dict(self._user_presets),
            presets=dict(self._presets),
        )

    def has_preset(self, name: str) -> bool:
        return name in self._presets

    def available_names(self) -> list[str]:
        names: list[str] = []
        names.extend([name for name in self._system_presets.keys() if name in self._presets])
        user_only = sorted([name for name in self._presets.keys() if name not in self._system_presets])
        names.extend(user_only)
        return list(dict.fromkeys(names))

    def get(self, name: str) -> PresetModel:
        return self._presets[name]

    def list_all(self) -> list[PresetModel]:
        return [self._presets[name] for name in self.available_names()]

    def available_entries(
        self,
        asset=None,
        *,
        compatible_only: bool = False,
    ) -> list[PresetCatalogEntry]:
        entries: list[PresetCatalogEntry] = []
        for name in self.available_names():
            preset = self._presets[name]
            entry = preset_catalog_entry(preset, asset=asset)
            if compatible_only and asset is not None and not entry.compatible:
                continue
            entries.append(entry)

        return entries

    def describe_preset_scope(self, preset_name: str) -> str:
        return describe_preset_scope(self.get(preset_name))

    @staticmethod
    def describe_asset_scope(asset) -> str:
        return describe_asset_scope(asset)

    def is_user_preset(self, name: str) -> bool:
        return name in self._user_presets

    def upsert_user_preset(self, preset: PresetModel) -> None:
        name = (preset.name or "").strip()
        if not name:
            raise ValueError("Preset name cannot be empty")
        if len(name) > 80:
            raise ValueError("Preset name is too long")
        if not isinstance(preset.settings_delta, dict):
            raise ValueError("Preset settings_delta must be a dict")

        self._validate_preset_or_raise(preset)
        preset.name = name
        preset.description = (preset.description or "").strip()

        self._user_presets[name] = preset
        self._presets[name] = preset
        self._persist_user_presets()

    def delete_user_preset(self, name: str) -> bool:
        if name not in self._user_presets:
            return False

        del self._user_presets[name]
        if name in self._system_presets:
            self._presets[name] = self._system_presets[name]
        else:
            self._presets.pop(name, None)
        self._persist_user_presets()
        return True

    def _load_user_presets(self) -> None:
        if self._app_paths is None:
            return
        store = PresetStore(self._app_paths)
        result = store.load_user_presets()
        for preset in result.presets:
            name = (preset.name or "").strip()
            if not name:
                continue
            try:
                self._validate_preset_or_raise(preset)
            except ValueError:
                continue
            self._user_presets[name] = preset
            self._presets[name] = preset

    def _persist_user_presets(self) -> None:
        if self._app_paths is None:
            return
        store = PresetStore(self._app_paths)
        store.save_user_presets(list(self._user_presets.values()))

    def _validate_system_presets(self) -> None:
        for name, preset in self._system_presets.items():
            try:
                self._validate_preset_or_raise(preset)
            except ValueError as exc:
                raise ValueError(f"Invalid bundled preset {name!r}: {exc}") from exc

    @staticmethod
    def _validate_preset_or_raise(preset: PresetModel) -> None:
        try:
            updated = apply_preset_to_edit_state(preset, EditState(mode=preset.mode_min))
        except PresetApplyError as exc:
            raise ValueError(str(exc)) from exc

        has_heavy_step = bool(implied_heavy_jobs(preset, updated))
        preset.uses_heavy_tools = bool(preset.uses_heavy_tools or has_heavy_step)
        preset.requires_apply = bool(preset.requires_apply or preset.uses_heavy_tools)
