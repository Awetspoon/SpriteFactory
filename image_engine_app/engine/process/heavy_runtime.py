"""Real heavy-job execution helpers for queued enhancement steps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.analyze.background_scan import inspect_background_state
from image_engine_app.engine.models import (
    AssetRecord,
    BackgroundRemovalMode,
    HeavyJobSpec,
    HeavyTool,
    normalize_background_removal_mode,
)
from image_engine_app.engine.process.performance_backend import PerformanceBackend, PerformanceModeResolution
from image_engine_app.engine.process.preview_support import render_light_pipeline_preview


@dataclass(frozen=True)
class HeavyJobExecutionResult:
    """Result of running a queued heavy job against an asset."""

    resolution: PerformanceModeResolution
    rendered_preview: bool


def execute_heavy_job(
    asset: AssetRecord,
    job: HeavyJobSpec,
    *,
    derived_cache_dir: str | Path | None,
    performance_backend: PerformanceBackend,
    requested_mode: str,
) -> HeavyJobExecutionResult:
    """Execute a heavy job by applying its effect to the asset and rendering outputs."""

    resolution = performance_backend.run_heavy_job(job, requested_mode=requested_mode)
    _apply_job_effect_to_asset(asset, job)
    cache_root = derived_cache_dir if derived_cache_dir is not None else (Path(".") / "_derived_cache")
    local_source = _resolve_local_source(asset)

    if local_source is None:
        return HeavyJobExecutionResult(
            resolution=resolution,
            rendered_preview=False,
        )

    if not render_light_pipeline_preview(asset, derived_cache_dir=cache_root, final_only=False):
        return HeavyJobExecutionResult(
            resolution=resolution,
            rendered_preview=False,
        )

    return HeavyJobExecutionResult(
        resolution=resolution,
        rendered_preview=True,
    )


def _apply_job_effect_to_asset(asset: AssetRecord, job: HeavyJobSpec) -> None:
    settings = asset.edit_state.settings
    params = dict(job.params or {})

    if job.tool is HeavyTool.AI_UPSCALE:
        factor = _safe_float(params.get("factor"), default=float(settings.ai.upscale_factor or 1.0))
        settings.ai.upscale_factor = max(float(settings.ai.upscale_factor or 1.0), max(1.0, factor))
        return

    if job.tool is HeavyTool.AI_DEBLUR:
        strength = _safe_float(params.get("strength"), default=float(settings.ai.deblur_strength or 0.0))
        reconstruct = _safe_float(
            params.get("detail_reconstruct"),
            default=max(float(settings.ai.detail_reconstruct or 0.0), strength * 0.45),
        )
        settings.ai.deblur_strength = max(float(settings.ai.deblur_strength or 0.0), max(0.0, strength))
        settings.ai.detail_reconstruct = max(float(settings.ai.detail_reconstruct or 0.0), max(0.0, reconstruct))
        return

    if job.tool is HeavyTool.BG_REMOVE:
        strength = _safe_float(params.get("strength"), default=float(settings.ai.bg_remove_strength or 0.0))
        settings.ai.bg_remove_strength = max(float(settings.ai.bg_remove_strength or 0.0), max(0.0, strength))
        _apply_background_remove_defaults(asset, params=params, strength=max(0.0, strength))
        return

    if job.tool is HeavyTool.AI_EXTEND:
        _apply_extend_defaults(asset, params=params)
        return


def _apply_background_remove_defaults(asset: AssetRecord, *, params: dict[str, object], strength: float) -> None:
    alpha = asset.edit_state.settings.alpha
    requested_mode = params.get("mode") or params.get("background_mode")
    mode = normalize_background_removal_mode(
        requested_mode if isinstance(requested_mode, str) else getattr(alpha, "background_removal_mode", None),
        remove_white_bg=bool(getattr(alpha, "remove_white_bg", False)),
    )

    if mode is BackgroundRemovalMode.OFF:
        scan = inspect_background_state(_resolve_local_source(asset))
        mode = scan.recommended_mode or BackgroundRemovalMode.OFF

    alpha.background_removal_mode = mode.value
    alpha.remove_white_bg = mode is BackgroundRemovalMode.WHITE
    if strength > 0.0:
        alpha.alpha_smooth = max(float(getattr(alpha, "alpha_smooth", 0.0) or 0.0), min(1.2, 0.12 + (strength * 0.55)))
        alpha.matte_fix = max(float(getattr(alpha, "matte_fix", 0.0) or 0.0), min(1.0, 0.08 + (strength * 0.45)))


def _apply_extend_defaults(asset: AssetRecord, *, params: dict[str, object]) -> None:
    width, height = asset.dimensions_final or asset.dimensions_current or asset.dimensions_original or (0, 0)
    pad = max(0, _safe_int(params.get("padding"), default=0))
    left = max(0, _safe_int(params.get("left"), default=pad))
    right = max(0, _safe_int(params.get("right"), default=pad))
    top = max(0, _safe_int(params.get("top"), default=pad))
    bottom = max(0, _safe_int(params.get("bottom"), default=pad))
    target_width = max(width + left + right, _safe_int(params.get("target_width"), default=width))
    target_height = max(height + top + bottom, _safe_int(params.get("target_height"), default=height))

    if width > 0 and height > 0 and (target_width > width or target_height > height):
        asset.edit_state.settings.pixel.width = int(target_width)
        asset.edit_state.settings.pixel.height = int(target_height)


def _resolve_local_source(asset: AssetRecord) -> str | Path | None:
    for candidate in (
        asset.cache_path,
        asset.source_uri,
        asset.derived_final_path,
        asset.derived_current_path,
    ):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        try:
            path = Path(candidate)
        except Exception:
            continue
        if path.exists() and path.is_file():
            return path
    return None


def _safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)
