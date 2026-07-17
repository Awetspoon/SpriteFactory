"""Shared asset-to-file export planning used by interactive and Batch output."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.export.exporters import ExportRequest, ExportResult, export_image
from image_engine_app.engine.export.format_resolver import (
    extension_for_export_format,
    resolve_export_format,
)
from image_engine_app.engine.export.naming import ensure_unique_path, render_name_template, safe_stem
from image_engine_app.engine.export.size_predictor import (
    ExportPredictorInput,
    ExportPredictorResult,
    predict_export_size,
)
from image_engine_app.engine.models import AssetFormat, ExportFormat, SettingsState
from image_engine_app.engine.process.export_source import ExportSourceResolution, resolve_export_source
from image_engine_app.engine.process.frame_pipeline import calculate_rendered_size


@dataclass(frozen=True)
class AssetExportOptions:
    """File-placement choices outside the asset's own export controls."""

    export_dir: str | Path
    name_template: str = "{stem}"
    index: int = 1
    group_outputs: bool = False
    overwrite_existing: bool = False
    preset_name: str = ""
    predictor_complexity: float = 0.5


@dataclass(frozen=True)
class AssetExportPlan:
    """Complete deterministic plan for one asset export."""

    prediction: ExportPredictorResult
    resolved_format: ExportFormat
    output_path: Path
    output_group: str
    request: ExportRequest


@dataclass(frozen=True)
class AssetExportOutcome:
    """The plan and encoder result for one asset."""

    plan: AssetExportPlan
    result: ExportResult


def predict_asset_export(
    asset: object,
    *,
    complexity: float = 0.5,
) -> ExportPredictorResult:
    """Predict the same dimensions and format that the encoder will receive."""

    source = resolve_export_source(asset)
    width, height = resolve_asset_export_dimensions(asset, source=source)
    settings = _asset_settings(asset)
    has_alpha, is_animated, frame_count = _asset_capabilities(asset)
    return predict_export_size(
        ExportPredictorInput(
            width=width,
            height=height,
            export_settings=settings.export,
            gif_settings=settings.gif,
            has_alpha=has_alpha,
            is_animated=is_animated,
            frame_count=frame_count,
            complexity=complexity,
        )
    )


def build_asset_export_plan(
    asset: object,
    options: AssetExportOptions,
) -> AssetExportPlan:
    """Build one source, format, size, name, and encoder request."""

    settings = _asset_settings(asset)
    source = resolve_export_source(asset)
    width, height = resolve_asset_export_dimensions(asset, source=source)
    has_alpha, is_animated, frame_count = _asset_capabilities(asset)
    resolved_format = resolve_export_format(
        settings.export,
        has_alpha=has_alpha,
        is_animated=is_animated,
        frame_count=frame_count,
    )
    prediction = predict_export_size(
        ExportPredictorInput(
            width=width,
            height=height,
            export_settings=settings.export,
            gif_settings=settings.gif,
            has_alpha=has_alpha,
            is_animated=is_animated,
            frame_count=frame_count,
            complexity=options.predictor_complexity,
        )
    )

    export_dir = Path(options.export_dir)
    output_group = export_group_for_asset(asset, resolved_format) if options.group_outputs else ""
    output_dir = export_dir / output_group if output_group else export_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    asset_id = str(getattr(asset, "id", "asset") or "asset")
    source_stem = safe_stem(str(getattr(asset, "original_name", "") or asset_id))
    name_stem = render_name_template(
        options.name_template,
        index=max(1, int(options.index)),
        stem=source_stem,
        group=output_group,
        asset_id=asset_id,
        preset=options.preset_name,
    )
    output_path = ensure_unique_path(
        output_dir / f"{name_stem}{extension_for_export_format(resolved_format)}",
        overwrite_existing=options.overwrite_existing,
    )

    resolved_export_settings = deepcopy(settings.export)
    resolved_export_settings.format = resolved_format
    request = ExportRequest(
        output_path=output_path,
        source_path=source.source_path,
        width=width,
        height=height,
        export_settings=resolved_export_settings,
        gif_settings=deepcopy(settings.gif),
        dpi=max(1, int(settings.pixel.dpi or 72)),
        asset_id=asset_id,
        frame_count=frame_count,
        has_alpha=has_alpha,
        processing_settings=deepcopy(source.processing_settings),
    )
    return AssetExportPlan(
        prediction=prediction,
        resolved_format=resolved_format,
        output_path=output_path,
        output_group=output_group,
        request=request,
    )


def execute_asset_export(plan: AssetExportPlan) -> ExportResult:
    """Execute a previously built asset export plan."""

    return export_image(plan.request)


def export_asset(
    asset: object,
    options: AssetExportOptions,
) -> AssetExportOutcome:
    """Plan and execute one asset export through the shared engine."""

    plan = build_asset_export_plan(asset, options)
    return AssetExportOutcome(plan=plan, result=execute_asset_export(plan))


def resolve_asset_export_dimensions(
    asset: object,
    *,
    source: ExportSourceResolution | None = None,
) -> tuple[int, int]:
    """Resolve the actual encoded dimensions for the selected source path."""

    resolved_source = source or resolve_export_source(asset)
    if resolved_source.uses_derived_preview:
        return _first_valid_dimensions(
            getattr(asset, "dimensions_final", None),
            getattr(asset, "dimensions_current", None),
            getattr(asset, "dimensions_original", None),
        )

    base_size = _first_valid_dimensions(
        getattr(asset, "dimensions_original", None),
        getattr(asset, "dimensions_current", None),
        getattr(asset, "dimensions_final", None),
    )
    if resolved_source.processing_settings is not None:
        return calculate_rendered_size(base_size, resolved_source.processing_settings)
    return base_size


def export_group_for_asset(asset: object, resolved_format: ExportFormat) -> str:
    """Return the stable Batch output group for an asset."""

    capabilities = getattr(asset, "capabilities", None)
    if (
        bool(getattr(capabilities, "is_animated", False))
        or getattr(asset, "format", None) is AssetFormat.GIF
        or resolved_format is ExportFormat.GIF
    ):
        return "gifs"
    if bool(getattr(capabilities, "is_sheet", False)):
        return "spritesheets"
    return resolved_format.value if resolved_format is not ExportFormat.AUTO else "other"


def _asset_settings(asset: object) -> SettingsState:
    settings = getattr(getattr(asset, "edit_state", None), "settings", None)
    return settings if isinstance(settings, SettingsState) else SettingsState()


def _asset_capabilities(asset: object) -> tuple[bool, bool, int]:
    capabilities = getattr(asset, "capabilities", None)
    has_alpha = bool(getattr(capabilities, "has_alpha", False))
    is_animated = bool(getattr(capabilities, "is_animated", False))
    return has_alpha, is_animated, (8 if is_animated else 1)


def _first_valid_dimensions(*values: object) -> tuple[int, int]:
    for value in values:
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            continue
        try:
            width = int(value[0])
            height = int(value[1])
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            return width, height
    return 1, 1
