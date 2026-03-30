"""Sequential batch runner with preview skip, auto preset, heavy queue, and auto export (Prompt 13)."""

from __future__ import annotations

from copy import deepcopy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from image_engine_app.engine.analyze.gif_scan import GifScanInput, estimate_gif_palette_stress_for_source
from image_engine_app.engine.analyze.quality_scan import QualityScanInput, scan_quality
from image_engine_app.engine.analyze.recommend import RecommendationInput, build_recommendations
from image_engine_app.engine.classify.classifier import classify_asset
from image_engine_app.engine.export.exporters import ExportRequest, ExportResult, export_image
from image_engine_app.engine.export.size_predictor import ExportPredictorInput, ExportPredictorResult, predict_export_size
from image_engine_app.engine.export.naming import safe_stem as export_safe_stem, render_name_template, ensure_unique_path
from image_engine_app.engine.models import (
    AssetFormat,
    AssetRecord,
    ExportFormat,
    HeavyJobSpec,
    QueueItem,
    QueueItemStatus,
    PresetModel,
)
from image_engine_app.engine.process.heavy_queue import HeavyQueueEngine
from image_engine_app.engine.process.heavy_runtime import execute_heavy_job
from image_engine_app.engine.process.light_steps import LightProcessError
from image_engine_app.engine.process.performance_backend import CPU_MODE, PerformanceBackend
from image_engine_app.engine.process.pipeline import PipelinePhase, ProcessingPlan, ProcessingStep, build_processing_plan
from image_engine_app.engine.process.preset_compat import preset_matches_asset
from image_engine_app.engine.process.presets_apply import ViewEditStates, apply_preset_stack
from image_engine_app.engine.process.preview_support import render_light_pipeline_preview, resolve_export_source, select_export_source_path


LOGGER = logging.getLogger("image_engine_app.batch.runner")


@dataclass
class BatchWorkItem:
    """Batch input item tying a QueueItem to an AssetRecord."""

    asset: AssetRecord
    queue_item: QueueItem


@dataclass
class BatchRunnerConfig:
    """Behavior flags and rules for batch processing."""

    preview_skip_mode: bool = False
    auto_export: bool = False
    export_dir: str | Path | None = None
    derived_cache_dir: str | Path | None = None
    auto_preset_rules: dict[str, list[PresetModel]] = field(default_factory=dict)
    per_source_preset_rules: dict[str, list[PresetModel]] = field(default_factory=dict)
    group_outputs: bool = True
    group_outputs_by: str = "source"
    export_name_template: str = "{index:03d}_{stem}"
    overwrite_existing_exports: bool = False
    stop_on_error: bool = False
    heavy_progress_steps: int = 3
    heavy_step_delay_seconds: float = 0.0
    predictor_complexity: float = 0.5
    performance_mode: str = CPU_MODE


@dataclass
class BatchItemRunResult:
    """Per-item batch execution result."""

    asset_id: str
    queue_item: QueueItem
    classification_tags: list[str] = field(default_factory=list)
    applied_preset_names: list[str] = field(default_factory=list)
    processing_plan: ProcessingPlan | None = None
    preview_skipped: bool = False
    heavy_jobs: list[HeavyJobSpec] = field(default_factory=list)
    predictor_result: ExportPredictorResult | None = None
    export_result: ExportResult | None = None
    error: str | None = None


@dataclass
class BatchRunReport:
    """Batch run summary."""

    items: list[BatchItemRunResult] = field(default_factory=list)
    cancelled: bool = False

    @property
    def processed_count(self) -> int:
        return sum(1 for item in self.items if item.queue_item.status is QueueItemStatus.DONE)

    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.items if item.queue_item.status is QueueItemStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for item in self.items if item.queue_item.status is QueueItemStatus.SKIPPED)


@dataclass(frozen=True)
class BatchProgressEvent:
    """Live batch progress event emitted during execution."""

    event_type: str
    item_index: int
    item_total: int
    asset_id: str | None = None
    asset_label: str | None = None
    queue_status: str | None = None
    queue_progress: float | None = None
    overall_progress: float | None = None
    stage: str | None = None
    processed_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    message: str | None = None


BatchProgressCallback = Callable[[BatchProgressEvent], None]
BatchCancelRequestedCallback = Callable[[], bool]


class BatchRunner:
    """Sequential batch processor that orchestrates existing engine modules."""

    def __init__(
        self,
        config: BatchRunnerConfig | None = None,
        *,
        heavy_queue_factory: Callable[[], HeavyQueueEngine] | None = None,
        performance_backend: PerformanceBackend | None = None,
    ) -> None:
        self.config = config or BatchRunnerConfig()
        self._heavy_queue_factory = heavy_queue_factory or (lambda: HeavyQueueEngine())
        self._performance_backend = performance_backend or PerformanceBackend()

    def run(
        self,
        work_items: list[BatchWorkItem],
        *,
        event_callback: BatchProgressCallback | None = None,
        cancel_requested: BatchCancelRequestedCallback | None = None,
    ) -> BatchRunReport:
        """Process batch items sequentially in input order."""

        report = BatchRunReport()
        total = len(work_items)
        LOGGER.info("Batch runner start: items=%s auto_export=%s preview_skip=%s", total, self.config.auto_export, self.config.preview_skip_mode)
        self._emit_event(
            event_callback,
            BatchProgressEvent(
                event_type="batch_start",
                item_index=0,
                item_total=total,
                overall_progress=0.0 if total else 1.0,
                processed_count=0,
                failed_count=0,
                skipped_count=0,
                message=f"Starting batch with {total} item(s)",
            ),
        )
        for index, work_item in enumerate(work_items):
            if self._is_cancel_requested(cancel_requested):
                report.cancelled = True
                LOGGER.info("Batch runner cancelled before item %s", index + 1)
                self._emit_event(
                    event_callback,
                    BatchProgressEvent(
                        event_type="batch_cancelled",
                        item_index=len(report.items),
                        item_total=total,
                        overall_progress=((len(report.items) / total) if total else 1.0),
                        processed_count=report.processed_count,
                        failed_count=report.failed_count,
                        skipped_count=report.skipped_count,
                        message="Batch cancelled",
                    ),
                )
                return report
            try:
                item_result = self._process_one(
                    index=index,
                    total_items=total,
                    work_item=work_item,
                    event_callback=event_callback,
                    cancel_requested=cancel_requested,
                )
                report.items.append(item_result)
            except _BatchRunCancelled as exc:
                if exc.item_result is not None:
                    report.items.append(exc.item_result)
                report.cancelled = True
                LOGGER.info("Batch runner cancelled during item %s", index + 1)
                self._emit_event(
                    event_callback,
                    BatchProgressEvent(
                        event_type="batch_cancelled",
                        item_index=len(report.items),
                        item_total=total,
                        asset_id=(exc.item_result.asset_id if exc.item_result is not None else None),
                        queue_status=(
                            exc.item_result.queue_item.status.value
                            if exc.item_result is not None
                            else None
                        ),
                        queue_progress=(
                            exc.item_result.queue_item.progress
                            if exc.item_result is not None
                            else None
                        ),
                        overall_progress=(
                            ((index + (exc.item_result.queue_item.progress if exc.item_result is not None else 0.0)) / total)
                            if total
                            else 1.0
                        ),
                        processed_count=report.processed_count,
                        failed_count=report.failed_count,
                        skipped_count=report.skipped_count,
                        message=str(exc),
                    ),
                )
                return report
            self._emit_event(
                event_callback,
                BatchProgressEvent(
                    event_type="item_complete",
                    item_index=index + 1,
                    item_total=total,
                    asset_id=item_result.asset_id,
                    asset_label=work_item.asset.original_name or work_item.asset.id,
                    queue_status=item_result.queue_item.status.value,
                    queue_progress=item_result.queue_item.progress,
                    overall_progress=((index + 1) / total) if total else 1.0,
                    stage="complete",
                    processed_count=report.processed_count,
                    failed_count=report.failed_count,
                    skipped_count=report.skipped_count,
                    message=f"Finished {work_item.asset.original_name or work_item.asset.id}",
                ),
            )
            if self.config.stop_on_error and item_result.queue_item.status is QueueItemStatus.FAILED:
                break
        self._emit_event(
            event_callback,
            BatchProgressEvent(
                event_type="batch_complete",
                item_index=len(report.items),
                item_total=total,
                overall_progress=1.0 if total else 1.0,
                processed_count=report.processed_count,
                failed_count=report.failed_count,
                skipped_count=report.skipped_count,
                message="Batch complete",
            ),
        )
        LOGGER.info("Batch runner complete: processed=%s failed=%s cancelled=%s", report.processed_count, report.failed_count, report.cancelled)
        return report

    def _process_one(
        self,
        *,
        index: int,
        total_items: int,
        work_item: BatchWorkItem,
        event_callback: BatchProgressCallback | None,
        cancel_requested: BatchCancelRequestedCallback | None,
    ) -> BatchItemRunResult:
        asset = work_item.asset
        queue_item = work_item.queue_item
        queue_item.status = QueueItemStatus.PROCESSING
        queue_item.progress = 0.0
        queue_item.notes = None

        result = BatchItemRunResult(
            asset_id=asset.id,
            queue_item=queue_item,
            preview_skipped=self.config.preview_skip_mode,
        )

        LOGGER.debug("Batch item start: index=%s/%s asset=%s", index + 1, total_items, asset.id)

        def mark(progress: float, stage: str, message: str | None = None) -> None:
            self._raise_if_cancel_requested(cancel_requested)
            queue_item.progress = progress
            overall = ((index + progress) / total_items) if total_items else 1.0
            LOGGER.debug(
                "Batch item progress: asset=%s stage=%s progress=%.3f overall=%.3f status=%s",
                asset.id,
                stage,
                progress,
                overall,
                queue_item.status.value,
            )
            self._emit_event(
                event_callback,
                BatchProgressEvent(
                    event_type="item_progress",
                    item_index=index + 1,
                    item_total=total_items,
                    asset_id=asset.id,
                    asset_label=asset.original_name or asset.id,
                    queue_status=queue_item.status.value,
                    queue_progress=queue_item.progress,
                    overall_progress=overall,
                    stage=stage,
                    message=message,
                ),
            )

        self._emit_event(
            event_callback,
            BatchProgressEvent(
                event_type="item_start",
                item_index=index + 1,
                item_total=total_items,
                asset_id=asset.id,
                asset_label=asset.original_name or asset.id,
                queue_status=queue_item.status.value,
                queue_progress=queue_item.progress,
                overall_progress=(index / total_items) if total_items else 1.0,
                stage="start",
                message=f"Processing {asset.original_name or asset.id}",
            ),
        )

        try:
            self._raise_if_cancel_requested(cancel_requested)
            mark(0.1, "classify")
            classification = classify_asset(asset)
            asset.classification_tags = list(classification.tags)
            result.classification_tags = list(classification.tags)

            mark(0.25, "analyze")
            quality_input = self._build_quality_input(asset)
            analysis = scan_quality(quality_input)
            if asset.format is AssetFormat.GIF and asset.capabilities.is_animated:
                analysis.gif_palette_stress = estimate_gif_palette_stress_for_source(
                    source_path=asset.cache_path or asset.source_uri or asset.derived_final_path,
                    fallback_scan=GifScanInput(
                        frame_count=8,
                        palette_size=asset.edit_state.settings.gif.palette_size,
                        duplicate_frame_ratio=0.1,
                        motion_change_ratio=0.5,
                    ),
                )
            asset.analysis = analysis
            asset.recommendations = build_recommendations(
                RecommendationInput(
                    file_format=asset.format,
                    classification_tags=asset.classification_tags,
                    analysis=asset.analysis,
                    has_alpha=asset.capabilities.has_alpha,
                    is_animated=asset.capabilities.is_animated,
                )
            )

            mark(0.4, "plan")
            result.processing_plan = None if self.config.preview_skip_mode else self._build_processing_plan(asset)

            mark(0.55, "presets")
            applied_presets = self._apply_auto_presets_if_any(asset)
            result.applied_preset_names = applied_presets

            mark(0.63, "light_pipeline")
            self._run_light_pipeline(asset)

            mark(0.7, "heavy_queue")
            heavy_jobs = self._run_heavy_jobs(asset)
            result.heavy_jobs = heavy_jobs

            mark(0.85, "export_prepare")
            if self.config.auto_export:
                mark(0.9, "exporting")
                predictor_result = self._predict_export(asset)
                export_result = self._auto_export(asset, predictor_result, index=index)
                result.predictor_result = predictor_result
                result.export_result = export_result
                mark(0.98, "export_saved")

            queue_item.status = QueueItemStatus.DONE
            mark(1.0, "done")
            LOGGER.info("Batch item done: asset=%s", asset.id)
        except _BatchRunCancelled as exc:
            queue_item.status = QueueItemStatus.SKIPPED
            queue_item.notes = str(exc)
            LOGGER.warning("Batch item cancelled: asset=%s stage_progress=%s reason=%s", asset.id, queue_item.progress, exc)
            self._emit_event(
                event_callback,
                BatchProgressEvent(
                    event_type="item_cancelled",
                    item_index=index + 1,
                    item_total=total_items,
                    asset_id=asset.id,
                    asset_label=asset.original_name or asset.id,
                    queue_status=queue_item.status.value,
                    queue_progress=queue_item.progress,
                    overall_progress=((index + queue_item.progress) / total_items) if total_items else 1.0,
                    stage="cancelled",
                    message=str(exc),
                ),
            )
            exc.item_result = result
            raise
        except Exception as exc:
            queue_item.status = QueueItemStatus.FAILED
            queue_item.notes = str(exc)
            result.error = str(exc)
            LOGGER.exception("Batch item failed: asset=%s stage_progress=%s", asset.id, queue_item.progress)
            self._emit_event(
                event_callback,
                BatchProgressEvent(
                    event_type="item_error",
                    item_index=index + 1,
                    item_total=total_items,
                    asset_id=asset.id,
                    asset_label=asset.original_name or asset.id,
                    queue_status=queue_item.status.value,
                    queue_progress=queue_item.progress,
                    overall_progress=((index + queue_item.progress) / total_items) if total_items else 1.0,
                    stage="error",
                    message=str(exc),
                ),
            )

        return result

    def _build_quality_input(self, asset: AssetRecord) -> QualityScanInput:
        width, height = asset.dimensions_current or asset.dimensions_original or (0, 0)
        tags = set(asset.classification_tags)
        edge_density = 0.55
        high_freq = 0.55
        noise_variance = 0.2
        blockiness = 0.1 if asset.format in {AssetFormat.JPG, AssetFormat.WEBP} else 0.03
        continuity = 0.75
        banding = 0.05

        if "pixel_art" in tags or "sprite_sheet" in tags:
            edge_density = 0.8
            high_freq = 0.7
            noise_variance = 0.08
            blockiness = 0.02
            continuity = 0.9
        elif "photo" in tags:
            edge_density = 0.45
            high_freq = 0.4
            noise_variance = 0.35 if asset.format is AssetFormat.JPG else 0.25
            blockiness = 0.3 if asset.format is AssetFormat.JPG else blockiness
            continuity = 0.6

        return QualityScanInput(
            width=max(1, width),
            height=max(1, height),
            file_format=asset.format,
            classification_tags=list(asset.classification_tags),
            edge_density=edge_density,
            high_frequency_ratio=high_freq,
            noise_variance=noise_variance,
            blockiness=blockiness,
            edge_continuity=continuity,
            banding_likelihood=banding,
        )

    def _build_processing_plan(self, asset: AssetRecord) -> ProcessingPlan:
        steps: list[ProcessingStep] = []
        s = asset.edit_state.settings

        if any(
            value > 0
            for value in (
                s.cleanup.denoise,
                s.cleanup.artifact_removal,
                s.cleanup.halo_cleanup,
                s.cleanup.banding_removal,
            )
        ):
            steps.append(ProcessingStep(key="cleanup.denoise", phase=PipelinePhase.DENOISE, params={}))

        if any(
            value > 0
            for value in (
                s.detail.sharpen_amount,
                s.detail.clarity,
                s.detail.texture,
            )
        ):
            steps.append(ProcessingStep(key="detail.sharpen", phase=PipelinePhase.SHARPEN, params={}))

        if s.ai.upscale_factor > 1.0 or any(job.tool.value == "ai_upscale" for job in asset.edit_state.queued_heavy_jobs):
            steps.append(
                ProcessingStep(
                    key="ai.upscale",
                    phase=PipelinePhase.UPSCALE,
                    params={"factor": s.ai.upscale_factor},
                    is_heavy=True,
                )
            )

        if any(
            value != default
            for value, default in (
                (s.color.brightness, 0.0),
                (s.color.contrast, 0.0),
                (s.color.saturation, 0.0),
                (s.color.temperature, 0.0),
                (s.color.gamma, 1.0),
            )
        ):
            steps.append(ProcessingStep(key="color.adjust", phase=PipelinePhase.COLOR, params={}))

        if self.config.auto_export:
            steps.append(
                ProcessingStep(
                    key=f"export.{asset.edit_state.settings.export.format.value}",
                    phase=PipelinePhase.EXPORT,
                    params={"format": asset.edit_state.settings.export.format.value},
                )
            )

        return build_processing_plan(steps)

    def _source_rule_keys(self, asset: AssetRecord) -> list[str]:
        """Return normalized source keys used for per-source preset rules and export grouping."""
        keys: list[str] = []
        if asset.capabilities.is_animated or asset.format is AssetFormat.GIF:
            keys.append("gif")
        if asset.capabilities.is_sheet:
            keys.append("spritesheet")
        if asset.format is AssetFormat.PNG:
            keys.append("png")
        elif asset.format is AssetFormat.JPG:
            keys.append("jpg")
        elif asset.format is AssetFormat.WEBP:
            keys.append("webp")
        elif asset.format is AssetFormat.ICO:
            keys.append("ico")
        if not keys:
            keys.append("other")
        return keys

    def _export_group_folder(self, asset: AssetRecord, predicted_format: str | None) -> str:
        """Choose a folder name for grouping batch exports."""
        if asset.capabilities.is_animated or asset.format is AssetFormat.GIF or (predicted_format or "").lower() == "gif":
            return "gifs"
        if asset.capabilities.is_sheet:
            return "spritesheets"

        fmt = (predicted_format or "").lower().strip()
        if fmt in {"png", "jpg", "webp", "tiff", "bmp", "ico"}:
            return fmt

        if asset.format is not None and getattr(asset.format, "value", None):
            val = str(asset.format.value).lower()
            if val in {"png", "jpg", "webp", "tiff", "bmp", "ico", "gif"}:
                return "gifs" if val == "gif" else val
        return "other"

    def _apply_auto_presets_if_any(self, asset: AssetRecord) -> list[str]:
        if not self.config.auto_preset_rules and not self.config.per_source_preset_rules:
            return []

        presets_to_apply: list[PresetModel] = []
        seen_names: set[str] = set()
        # Apply per-source rules first (file type / spritesheet / animation)
        for key in self._source_rule_keys(asset):
            for preset in self.config.per_source_preset_rules.get(key, []):
                compatible, _reason = preset_matches_asset(preset, asset)
                if not compatible:
                    continue
                if preset.name in seen_names:
                    continue
                seen_names.add(preset.name)
                presets_to_apply.append(preset)

        for tag in asset.classification_tags:
            for preset in self.config.auto_preset_rules.get(tag, []):
                compatible, _reason = preset_matches_asset(preset, asset)
                if not compatible:
                    continue
                if preset.name in seen_names:
                    continue
                seen_names.add(preset.name)
                presets_to_apply.append(preset)

        if not presets_to_apply:
            return []

        # The schema keeps one canonical EditState; we emulate current/final views for apply-target rules
        # and persist the resulting active state back onto the asset.
        states = ViewEditStates(current=deepcopy(asset.edit_state), final=deepcopy(asset.edit_state))
        report = apply_preset_stack(presets_to_apply, states=states)

        if report.effective_target is not None and (
            report.effective_target.value in {"final", "both"} or report.sync_applied
        ):
            asset.edit_state = report.states.final
        else:
            asset.edit_state = report.states.current

        return report.applied_preset_names

    def _run_light_pipeline(self, asset: AssetRecord) -> None:
        """Render the light (non-AI) pipeline to a derived Final output, if configured."""
        render_light_pipeline_preview(
            asset,
            derived_cache_dir=self.config.derived_cache_dir,
            final_only=True,
        )


    def _run_heavy_jobs(self, asset: AssetRecord) -> list[HeavyJobSpec]:
        if not asset.edit_state.queued_heavy_jobs:
            return []

        engine = self._heavy_queue_factory()
        for job in asset.edit_state.queued_heavy_jobs:
            engine.enqueue_or_replace(job)

        finished = engine.run_all(
            progress_steps=self.config.heavy_progress_steps,
            step_delay_seconds=self.config.heavy_step_delay_seconds,
            task_runner=lambda job: execute_heavy_job(
                asset,
                job,
                derived_cache_dir=self.config.derived_cache_dir,
                performance_backend=self._performance_backend,
                requested_mode=self.config.performance_mode,
            ),
        )

        # Preserve queue list with updated statuses after running.
        asset.edit_state.queued_heavy_jobs = engine.list_jobs()
        return finished

    def _predict_export(self, asset: AssetRecord) -> ExportPredictorResult:
        width, height = asset.dimensions_final or asset.dimensions_current or asset.dimensions_original or (1, 1)
        return predict_export_size(
            ExportPredictorInput(
                width=max(1, width),
                height=max(1, height),
                export_settings=asset.edit_state.settings.export,
                has_alpha=asset.capabilities.has_alpha,
                is_animated=asset.capabilities.is_animated,
                frame_count=8 if asset.capabilities.is_animated else 1,
                complexity=self.config.predictor_complexity,
            )
        )

    def _auto_export(
        self,
        asset: AssetRecord,
        predictor_result: ExportPredictorResult,
        *,
        index: int,
    ) -> ExportResult:
        if not self.config.export_dir:
            raise ValueError("auto_export is enabled but export_dir is not configured")

        export_dir = Path(self.config.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)

        predicted_format = predictor_result.prediction.predicted_format
        ext = _extension_for_export_format_string(predicted_format)

        group_folder = ""
        output_dir = export_dir
        if self.config.group_outputs:
            group_folder = self._export_group_folder(asset, predicted_format)
            output_dir = export_dir / group_folder
            output_dir.mkdir(parents=True, exist_ok=True)

        stem = export_safe_stem(asset.original_name or asset.id)
        name_stem = render_name_template(
            self.config.export_name_template,
            index=(index + 1),
            stem=stem,
            group=group_folder,
            asset_id=asset.id,
            preset="",
        )
        output_path = ensure_unique_path(
            output_dir / f"{name_stem}{ext}",
            overwrite_existing=self.config.overwrite_existing_exports,
        )

        width, height = asset.dimensions_final or asset.dimensions_current or asset.dimensions_original or (1, 1)
        export_source = resolve_export_source(asset)
        return export_image(
            ExportRequest(
                output_path=output_path,
                source_path=export_source.source_path,
                width=max(1, width),
                height=max(1, height),
                export_settings=asset.edit_state.settings.export,
                asset_id=asset.id,
                frame_count=8 if asset.capabilities.is_animated else 1,
                has_alpha=asset.capabilities.has_alpha,
                light_settings=export_source.light_settings,
            )
        )

    @staticmethod
    def _emit_event(
        callback: BatchProgressCallback | None,
        event: BatchProgressEvent,
    ) -> None:
        if callback is not None:
            callback(event)

    @staticmethod
    def _is_cancel_requested(callback: BatchCancelRequestedCallback | None) -> bool:
        return bool(callback and callback())

    @staticmethod
    def _raise_if_cancel_requested(callback: BatchCancelRequestedCallback | None) -> None:
        if callback is not None and callback():
            raise _BatchRunCancelled("Batch cancelled")


    def _select_export_source_path(self, asset: AssetRecord) -> str | None:
        """Choose source path for exports.

        Prefer derived_final_path, then derived_current_path, for processed outputs, but preserve GIF frames when exporting GIF from an animated source.
        """
        return select_export_source_path(asset)


class _BatchRunCancelled(RuntimeError):
    """Internal control-flow exception used for cooperative cancellation."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.item_result: BatchItemRunResult | None = None



def _extension_for_export_format_string(fmt: str) -> str:
    mapping = {
        ExportFormat.JPG.value: ".jpg",
        ExportFormat.PNG.value: ".png",
        ExportFormat.WEBP.value: ".webp",
        ExportFormat.GIF.value: ".gif",
        ExportFormat.ICO.value: ".ico",
        ExportFormat.TIFF.value: ".tiff",
        ExportFormat.BMP.value: ".bmp",
    }
    return mapping.get(fmt, ".bin")










