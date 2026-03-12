"""Preset application helpers with mode clamping and apply-target logic (Prompt 11)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from engine.models import ApplyTarget, EditState, PresetModel
from engine.process.bounds import clamp_edit_state_for_mode, mode_meets_minimum


class PresetApplyError(Exception):
    """Raised when a preset cannot be applied safely."""


@dataclass
class ViewEditStates:
    """Current/final edit states used by preview apply-target rules."""

    current: EditState
    final: EditState


@dataclass
class PresetApplyReport:
    """Result of applying one or more presets to one or both views."""

    states: ViewEditStates
    applied_preset_names: list[str] = field(default_factory=list)
    effective_target: ApplyTarget = ApplyTarget.BOTH
    sync_applied: bool = False
    requires_apply: bool = False


def apply_preset_to_edit_state(
    preset: PresetModel,
    edit_state: EditState,
) -> EditState:
    """Apply a single preset to an EditState and clamp by the state's mode."""

    if not mode_meets_minimum(edit_state.mode, preset.mode_min):
        raise PresetApplyError(
            f"Preset {preset.name!r} requires mode {preset.mode_min.value}, "
            f"but state mode is {edit_state.mode.value}"
        )

    updated = deepcopy(edit_state)
    _apply_settings_delta(updated.settings, preset.settings_delta)
    return clamp_edit_state_for_mode(updated)


def apply_preset_to_views(
    preset: PresetModel,
    *,
    states: ViewEditStates,
    target: ApplyTarget | None = None,
    sync_current_final: bool | None = None,
) -> PresetApplyReport:
    """Apply a single preset to Current/Final/Both using sync mirroring rules."""

    effective_target = target or states.current.apply_target
    sync_enabled = states.current.sync_current_final if sync_current_final is None else sync_current_final

    current_state = deepcopy(states.current)
    final_state = deepcopy(states.final)

    if effective_target is ApplyTarget.BOTH or sync_enabled:
        current_state = apply_preset_to_edit_state(preset, current_state)
        final_state = apply_preset_to_edit_state(preset, final_state)
        sync_applied = sync_enabled and effective_target is not ApplyTarget.BOTH
    elif effective_target is ApplyTarget.CURRENT:
        current_state = apply_preset_to_edit_state(preset, current_state)
        sync_applied = False
    elif effective_target is ApplyTarget.FINAL:
        final_state = apply_preset_to_edit_state(preset, final_state)
        sync_applied = False
    else:  # pragma: no cover - defensive for enum expansion
        raise PresetApplyError(f"Unsupported apply target: {effective_target!r}")

    return PresetApplyReport(
        states=ViewEditStates(current=current_state, final=final_state),
        applied_preset_names=[preset.name],
        effective_target=effective_target,
        sync_applied=sync_applied,
        requires_apply=(preset.requires_apply or preset.uses_heavy_tools),
    )


def apply_preset_stack(
    presets: list[PresetModel],
    *,
    states: ViewEditStates,
    target: ApplyTarget | None = None,
    sync_current_final: bool | None = None,
) -> PresetApplyReport:
    """Apply multiple presets in order (stacking), where later presets override earlier deltas."""

    working = ViewEditStates(current=deepcopy(states.current), final=deepcopy(states.final))
    applied_names: list[str] = []
    requires_apply = False
    effective_target = target or states.current.apply_target
    sync_enabled = states.current.sync_current_final if sync_current_final is None else sync_current_final

    for preset in presets:
        report = apply_preset_to_views(
            preset,
            states=working,
            target=effective_target,
            sync_current_final=sync_enabled,
        )
        working = report.states
        applied_names.extend(report.applied_preset_names)
        requires_apply = requires_apply or report.requires_apply

    return PresetApplyReport(
        states=working,
        applied_preset_names=applied_names,
        effective_target=effective_target,
        sync_applied=(sync_enabled and effective_target is not ApplyTarget.BOTH),
        requires_apply=requires_apply,
    )


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
            except Exception as exc:  # pragma: no cover - invalid preset values are raised cleanly
                raise PresetApplyError(
                    f"Invalid enum value for {key!r}: {value!r}"
                ) from exc

        setattr(settings_obj, key, value)
