"""Detected asset baselines and control-captured preset helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    EditState,
    HeavyJobSpec,
    HeavyTool,
    PresetModel,
    SettingsState,
)


CONTROL_GROUP_ORDER = (
    "pixel",
    "color",
    "detail",
    "cleanup",
    "edges",
    "alpha",
    "ai",
    "gif",
    "export",
)
_NO_CHANGE = object()
_STABLE_TAG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


@dataclass(frozen=True)
class CapturedControlSettings:
    """Sparse preset data captured from one asset's edited controls."""

    settings_delta: dict[str, Any]
    changed_groups: tuple[str, ...]
    applies_to_formats: tuple[str, ...]
    applies_to_tags: tuple[str, ...]
    uses_heavy_tools: bool
    requires_apply: bool


def capture_detected_settings(asset: AssetRecord) -> SettingsState:
    """Store the asset-specific settings produced by import detection."""

    detected = deepcopy(asset.edit_state.settings)
    asset.detected_settings = detected
    return deepcopy(detected)


def ensure_detected_settings(asset: AssetRecord) -> SettingsState:
    """Return a baseline, safely adopting current controls for legacy assets."""

    baseline = getattr(asset, "detected_settings", None)
    if baseline is None:
        baseline = capture_detected_settings(asset)
    return deepcopy(baseline)


def edit_state_from_detected_settings(asset: AssetRecord) -> EditState:
    """Build a clean edit state while retaining the asset's UI behavior choices."""

    state = deepcopy(asset.edit_state)
    state.settings = ensure_detected_settings(asset)
    state.queued_heavy_jobs.clear()
    return state


def restore_detected_settings(asset: AssetRecord) -> None:
    """Restore the detected controls and discard generated edit output."""

    asset.edit_state = edit_state_from_detected_settings(asset)
    clear_generated_outputs(asset)


def clear_generated_outputs(asset: AssetRecord) -> None:
    """Return preview dimensions to the source after settings are replaced."""

    asset.derived_current_path = None
    asset.derived_final_path = None

    original = getattr(asset, "dimensions_original", (0, 0))
    if isinstance(original, tuple) and len(original) == 2:
        width = int(original[0] or 0)
        height = int(original[1] or 0)
        if width > 0 and height > 0:
            asset.dimensions_current = (width, height)
            asset.dimensions_final = (width, height)


def settings_delta_from_detected(asset: AssetRecord) -> dict[str, Any]:
    """Return only control values that differ from the detected baseline."""

    current = asset.edit_state.settings.to_dict()
    baseline = ensure_detected_settings(asset).to_dict()
    result = _sparse_difference(current, baseline)
    return result if isinstance(result, dict) else {}


def capture_control_settings(asset: AssetRecord) -> CapturedControlSettings:
    """Capture reusable preset metadata from the active asset's controls."""

    delta = settings_delta_from_detected(asset)
    changed_groups = tuple(group for group in CONTROL_GROUP_ORDER if group in delta)
    ai_delta = delta.get("ai") if isinstance(delta.get("ai"), dict) else {}
    uses_heavy_tools = _has_heavy_ai_change(ai_delta)

    format_value = getattr(getattr(asset, "format", None), "value", None)
    formats = (str(format_value),) if format_value and asset.format is not AssetFormat.UNKNOWN else ("*",)
    tags = tuple(_stable_asset_tags(asset)) or ("*",)

    return CapturedControlSettings(
        settings_delta=delta,
        changed_groups=changed_groups,
        applies_to_formats=formats,
        applies_to_tags=tags,
        uses_heavy_tools=uses_heavy_tools,
        requires_apply=uses_heavy_tools,
    )


def implied_heavy_jobs(preset: PresetModel, edit_state: EditState) -> list[HeavyJobSpec]:
    """Build the single heavy step implied by a preset's AI controls."""

    if not preset.uses_heavy_tools or not isinstance(preset.settings_delta, dict):
        return []
    ai_delta = preset.settings_delta.get("ai")
    if not isinstance(ai_delta, dict):
        return []

    factor = _safe_float(ai_delta.get("upscale_factor"), default=1.0)
    deblur = _safe_float(ai_delta.get("deblur_strength"), default=0.0)
    background = _safe_float(ai_delta.get("bg_remove_strength"), default=0.0)

    if factor > 1.0:
        resolved_factor = max(2.0, float(edit_state.settings.ai.upscale_factor))
        return [
            HeavyJobSpec(
                tool=HeavyTool.AI_UPSCALE,
                params={"factor": resolved_factor, "preset": preset.name},
            )
        ]
    if deblur > 0.0:
        return [
            HeavyJobSpec(
                tool=HeavyTool.AI_DEBLUR,
                params={
                    "strength": max(0.2, float(edit_state.settings.ai.deblur_strength)),
                    "detail_reconstruct": float(edit_state.settings.ai.detail_reconstruct),
                    "preset": preset.name,
                },
            )
        ]
    if background > 0.0:
        return [
            HeavyJobSpec(
                tool=HeavyTool.BG_REMOVE,
                params={"strength": background, "preset": preset.name},
            )
        ]
    return []


def _sparse_difference(current: Any, baseline: Any) -> Any:
    if isinstance(current, dict) and isinstance(baseline, dict):
        changed: dict[str, Any] = {}
        for key, current_value in current.items():
            difference = _sparse_difference(current_value, baseline.get(key, _NO_CHANGE))
            if difference is not _NO_CHANGE:
                changed[key] = difference
        return changed if changed else _NO_CHANGE
    return _NO_CHANGE if current == baseline else deepcopy(current)


def _stable_asset_tags(asset: AssetRecord) -> list[str]:
    stable: list[str] = []
    for raw_tag in asset.classification_tags or []:
        tag = str(raw_tag).strip().lower()
        if not _STABLE_TAG.fullmatch(tag) or tag in stable:
            continue
        stable.append(tag)
    return stable


def _has_heavy_ai_change(ai_delta: dict[str, Any]) -> bool:
    thresholds = {
        "upscale_factor": 1.0,
        "deblur_strength": 0.0,
        "bg_remove_strength": 0.0,
    }
    for key, threshold in thresholds.items():
        if key not in ai_delta:
            continue
        try:
            if float(ai_delta[key]) > threshold:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
