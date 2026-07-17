"""Shared preset planning for interactive, import, and batch workflows."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable

from image_engine_app.engine.models import (
    AssetRecord,
    EditMode,
    EditState,
    HeavyJobSpec,
    PresetModel,
    normalize_edit_mode,
)
from image_engine_app.engine.process.edit_baseline import (
    clear_generated_outputs,
    edit_state_from_detected_settings,
    implied_heavy_jobs,
)
from image_engine_app.engine.process.preset_compat import preset_matches_asset
from image_engine_app.engine.process.presets_apply import PresetApplyError, apply_preset_to_edit_state


@dataclass(frozen=True)
class PresetApplicationPlan:
    """Complete, deterministic result of applying one preset to one asset."""

    preset_name: str
    edit_state: EditState
    queued_heavy_jobs: tuple[HeavyJobSpec, ...]
    requires_apply: bool


def plan_preset_application(
    asset: AssetRecord,
    preset: PresetModel,
    *,
    queue_heavy_jobs: bool = True,
) -> PresetApplicationPlan:
    """Build one preset result from the asset's detected baseline."""

    compatible, reason = preset_matches_asset(preset, asset)
    if not compatible:
        raise PresetApplyError(reason)

    baseline_state = edit_state_from_detected_settings(asset)
    _promote_mode_for_preset(baseline_state, preset)
    updated_state = apply_preset_to_edit_state(preset, baseline_state)

    heavy_jobs = implied_heavy_jobs(preset, updated_state) if queue_heavy_jobs else []
    updated_state.queued_heavy_jobs = deepcopy(heavy_jobs)
    return PresetApplicationPlan(
        preset_name=preset.name,
        edit_state=updated_state,
        queued_heavy_jobs=tuple(deepcopy(heavy_jobs)),
        requires_apply=bool(preset.requires_apply or preset.uses_heavy_tools or heavy_jobs),
    )


def commit_preset_application(asset: AssetRecord, plan: PresetApplicationPlan) -> bool:
    """Install a planned preset and invalidate any stale generated output."""

    changed = asset.edit_state != plan.edit_state
    asset.edit_state = deepcopy(plan.edit_state)
    clear_generated_outputs(asset)
    return changed


def select_first_compatible_preset(
    asset: AssetRecord,
    presets: Iterable[PresetModel],
) -> PresetModel | None:
    """Return the first catalog-ordered preset compatible with the asset."""

    for preset in presets:
        compatible, _reason = preset_matches_asset(preset, asset)
        if compatible:
            return preset
    return None


def _promote_mode_for_preset(edit_state: EditState, preset: PresetModel) -> None:
    mode_rank = {
        EditMode.ADVANCED: 0,
        EditMode.EXPERT: 1,
    }
    current_mode = normalize_edit_mode(edit_state.mode)
    preset_mode = normalize_edit_mode(preset.mode_min)
    if mode_rank[current_mode] < mode_rank[preset_mode]:
        edit_state.mode = preset_mode
