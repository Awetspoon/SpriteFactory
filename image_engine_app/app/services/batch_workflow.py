"""Application-owned Batch preparation and isolated execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from image_engine_app.app.paths import AppPaths
from image_engine_app.app.services.batch_preset_rules import build_batch_auto_preset_rules
from image_engine_app.app.services.preset_library import PresetLibrary
from image_engine_app.app.services.preset_workflow import PresetWorkflowService
from image_engine_app.engine.batch.batch_runner import (
    BatchCancelRequestedCallback,
    BatchProgressCallback,
    BatchRunReport,
    BatchRunner,
    BatchRunnerConfig,
    BatchWorkItem,
)
from image_engine_app.engine.models import (
    AssetRecord,
    BackgroundRemovalMode,
    BatchEditSource,
    QueueItem,
    QueueItemStatus,
    normalize_background_removal_mode,
)
from image_engine_app.engine.process.edit_baseline import clear_generated_outputs
from image_engine_app.engine.process.heavy_queue import HeavyQueueEngine
from image_engine_app.engine.process.presets_apply import PresetApplyError


@dataclass(frozen=True)
class BatchPreparationResult:
    """Isolated assets plus chosen-preset compatibility totals."""

    assets: list[AssetRecord]
    applied_preset_count: int = 0
    skipped_preset_count: int = 0


class BatchWorkflowService:
    """Own Batch settings preparation and the engine runner boundary."""

    def __init__(
        self,
        *,
        app_paths: AppPaths | None,
        preset_library: PresetLibrary,
        preset_workflow: PresetWorkflowService,
        heavy_queue_factory: Callable[[], HeavyQueueEngine],
    ) -> None:
        self._app_paths = app_paths
        self._preset_library = preset_library
        self._preset_workflow = preset_workflow
        self._heavy_queue_factory = heavy_queue_factory

    def prepare_assets(
        self,
        *,
        selected_assets: list[AssetRecord],
        active_asset: AssetRecord | None,
        edit_source: BatchEditSource,
        selected_preset_name: str,
        background_override: str | None,
    ) -> BatchPreparationResult:
        """Copy live assets and apply exactly one Batch edit-source rule."""

        assets = [deepcopy(asset) for asset in selected_assets]
        for asset in assets:
            clear_generated_outputs(asset)

        if edit_source is BatchEditSource.COPY_ACTIVE:
            if active_asset is None:
                raise ValueError("select an active asset before copying its controls")
            self._copy_active_controls(active_asset, assets)

        applied_preset_count = 0
        skipped_preset_count = 0
        if edit_source is BatchEditSource.CHOSEN_PRESET:
            if not selected_preset_name:
                raise ValueError("choose a preset for this batch")
            applied_preset_count, skipped_preset_count = self._apply_named_preset(
                assets,
                selected_preset_name,
            )

        if background_override is not None:
            self._apply_background_override(assets, background_override)

        return BatchPreparationResult(
            assets=assets,
            applied_preset_count=applied_preset_count,
            skipped_preset_count=skipped_preset_count,
        )

    def run(
        self,
        assets: list[AssetRecord],
        *,
        preview_skip_mode: bool = True,
        auto_export: bool = False,
        auto_preset: bool = True,
        export_name_template: str | None = None,
        avoid_overwrite: bool = True,
        export_dir: str | Path | None = None,
        event_callback: BatchProgressCallback | None = None,
        cancel_requested: BatchCancelRequestedCallback | None = None,
    ) -> BatchRunReport:
        """Run copied assets so Batch can never mutate the live workspace."""

        run_assets = [deepcopy(asset) for asset in assets]
        for asset in run_assets:
            clear_generated_outputs(asset)

        resolved_export_dir: str | Path | None = None
        if auto_export:
            if export_dir is not None:
                resolved_export_dir = export_dir
            elif self._app_paths is not None:
                resolved_export_dir = self._app_paths.exports

        config = BatchRunnerConfig(
            preview_skip_mode=preview_skip_mode,
            auto_export=auto_export,
            export_dir=resolved_export_dir,
            derived_cache_dir=(
                (self._app_paths.cache / "batch_runs")
                if self._app_paths is not None
                else None
            ),
            auto_preset_rules=build_batch_auto_preset_rules(
                self._preset_library,
                enabled=auto_preset,
            ),
            export_name_template=(export_name_template or "{stem}"),
            overwrite_existing_exports=(not avoid_overwrite),
            heavy_progress_steps=2,
            heavy_step_delay_seconds=0.0,
        )
        runner = BatchRunner(config, heavy_queue_factory=self._heavy_queue_factory)
        work_items = [
            BatchWorkItem(
                asset=asset,
                queue_item=QueueItem(
                    id=f"batch-{index:03d}",
                    asset_id=asset.id,
                    status=QueueItemStatus.PENDING,
                    progress=0.0,
                ),
            )
            for index, asset in enumerate(run_assets, start=1)
        ]
        return runner.run(
            work_items,
            event_callback=event_callback,
            cancel_requested=cancel_requested,
        )

    @staticmethod
    def _copy_active_controls(active_asset: AssetRecord, assets: list[AssetRecord]) -> None:
        template_mode = deepcopy(active_asset.edit_state.mode)
        template_jobs = deepcopy(active_asset.edit_state.queued_heavy_jobs)
        template_settings = deepcopy(active_asset.edit_state.settings)
        for asset in assets:
            asset.edit_state.mode = deepcopy(template_mode)
            asset.edit_state.queued_heavy_jobs = deepcopy(template_jobs)
            asset.edit_state.settings = deepcopy(template_settings)

    def _apply_named_preset(
        self,
        assets: list[AssetRecord],
        preset_name: str,
    ) -> tuple[int, int]:
        applied_count = 0
        skipped_count = 0
        for asset in assets:
            try:
                self._preset_workflow.apply_named(
                    asset,
                    preset_name,
                    refresh_final=False,
                )
            except PresetApplyError:
                skipped_count += 1
                continue
            applied_count += 1

        if applied_count <= 0:
            raise PresetApplyError(
                f"Preset '{preset_name}' is not compatible with the selected assets"
            )
        return applied_count, skipped_count

    @staticmethod
    def _apply_background_override(assets: list[AssetRecord], mode_value: str) -> None:
        normalized = normalize_background_removal_mode(mode_value).value
        for asset in assets:
            alpha = asset.edit_state.settings.alpha
            alpha.background_removal_mode = normalized
            alpha.remove_white_bg = normalized == BackgroundRemovalMode.WHITE.value
