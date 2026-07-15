"""Prepare isolated batch assets without mutating the live workspace state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from image_engine_app.engine.models import (
    AssetRecord,
    BackgroundRemovalMode,
    BatchEditSource,
    normalize_background_removal_mode,
)
from image_engine_app.engine.process.presets_apply import PresetApplyError


@dataclass(frozen=True)
class BatchPreparationResult:
    assets: list[AssetRecord]
    applied_preset_count: int = 0
    skipped_preset_count: int = 0


def prepare_batch_assets(
    *,
    selected_assets: list[AssetRecord],
    active_asset: AssetRecord | None,
    controller: Any,
    edit_source: BatchEditSource,
    selected_preset_name: str,
    background_override: str | None,
) -> BatchPreparationResult:
    assets = [deepcopy(asset) for asset in selected_assets]
    _clear_derived_outputs(assets)

    if edit_source is BatchEditSource.COPY_ACTIVE:
        if active_asset is None:
            raise ValueError("select an active asset before copying its controls")
        _apply_active_edit_settings(active_asset, assets)

    applied_preset_count = 0
    skipped_preset_count = 0
    if edit_source is BatchEditSource.CHOSEN_PRESET:
        if not selected_preset_name:
            raise ValueError("choose a preset for this batch")
        applied_preset_count, skipped_preset_count = _apply_named_preset_to_assets(
            controller,
            assets,
            selected_preset_name,
        )

    if background_override is not None:
        _apply_background_override(assets, background_override)

    return BatchPreparationResult(
        assets=assets,
        applied_preset_count=applied_preset_count,
        skipped_preset_count=skipped_preset_count,
    )


def _apply_active_edit_settings(active_asset: AssetRecord, assets: list[AssetRecord]) -> None:
    template_mode = deepcopy(active_asset.edit_state.mode)
    template_heavy_jobs = deepcopy(active_asset.edit_state.queued_heavy_jobs)
    template_settings = deepcopy(active_asset.edit_state.settings)

    for asset in assets:
        asset.edit_state.mode = deepcopy(template_mode)
        asset.edit_state.queued_heavy_jobs = deepcopy(template_heavy_jobs)
        asset.edit_state.settings = deepcopy(template_settings)


def _apply_named_preset_to_assets(
    controller: Any,
    assets: list[AssetRecord],
    preset_name: str,
) -> tuple[int, int]:
    applied_count = 0
    skipped_count = 0

    for asset in assets:
        try:
            controller.apply_named_preset(asset, preset_name)
        except PresetApplyError:
            skipped_count += 1
            continue
        applied_count += 1

    if applied_count <= 0:
        raise PresetApplyError(f"Preset '{preset_name}' is not compatible with the selected assets")
    return applied_count, skipped_count


def _apply_background_override(assets: list[AssetRecord], mode_value: str) -> None:
    normalized = normalize_background_removal_mode(mode_value).value
    for asset in assets:
        alpha_settings = asset.edit_state.settings.alpha
        alpha_settings.background_removal_mode = normalized
        alpha_settings.remove_white_bg = (normalized == BackgroundRemovalMode.WHITE.value)


def _clear_derived_outputs(assets: list[AssetRecord]) -> None:
    for asset in assets:
        asset.derived_current_path = None
        asset.derived_final_path = None
