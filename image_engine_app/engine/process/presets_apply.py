"""Apply one preset to the application's single editable asset state."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any

from image_engine_app.engine.models import EditState, PresetModel
from image_engine_app.engine.process.bounds import clamp_edit_state_for_mode, mode_meets_minimum


class PresetApplyError(Exception):
    """Raised when a preset cannot be applied safely."""


def apply_preset_to_edit_state(
    preset: PresetModel,
    edit_state: EditState,
) -> EditState:
    """Apply one preset to an EditState and clamp it to the active mode."""

    if not mode_meets_minimum(edit_state.mode, preset.mode_min):
        raise PresetApplyError(
            f"Preset {preset.name!r} requires mode {preset.mode_min.value}, "
            f"but state mode is {edit_state.mode.value}"
        )

    updated = deepcopy(edit_state)
    _apply_settings_delta(updated.settings, _normalize_legacy_settings_delta(preset.settings_delta))
    return clamp_edit_state_for_mode(updated)


def _apply_settings_delta(settings_obj: Any, delta: dict[str, Any]) -> None:
    if not isinstance(delta, dict):
        raise PresetApplyError("Preset settings_delta must be a dict")

    for key, value in delta.items():
        if not hasattr(settings_obj, key):
            raise PresetApplyError(f"Unknown preset settings key: {key!r}")

        current = getattr(settings_obj, key)
        if isinstance(value, dict):
            if not hasattr(current, "__dict__"):
                raise PresetApplyError(f"Cannot apply nested delta to non-object setting: {key!r}")
            _apply_settings_delta(current, value)
            continue

        if isinstance(current, Enum) and not isinstance(value, current.__class__):
            try:
                value = current.__class__(value)
            except Exception as exc:
                raise PresetApplyError(f"Invalid enum value for {key!r}: {value!r}") from exc

        setattr(settings_obj, key, value)


def _normalize_legacy_settings_delta(delta: dict[str, Any]) -> dict[str, Any]:
    """Map retired preset fields onto their one active control."""

    normalized = deepcopy(delta)
    export_delta = normalized.get("export")
    if not isinstance(export_delta, dict) or "palette_limit" not in export_delta:
        return normalized

    palette_size = export_delta.pop("palette_limit")
    gif_delta = normalized.setdefault("gif", {})
    if isinstance(gif_delta, dict):
        gif_delta.setdefault("palette_size", palette_size)
    return normalized
