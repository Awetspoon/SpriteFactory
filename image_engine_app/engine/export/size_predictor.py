"""Live export file size predictor and comparison heuristics (Prompt 12)."""

from __future__ import annotations

from dataclasses import dataclass
import math

from image_engine_app.engine.common.math_utils import clamp01

from image_engine_app.engine.export.profiles import get_profile_rule, profile_comparison_formats
from image_engine_app.engine.models import (
    ExportComparisonEntry,
    ExportFormat,
    ExportPrediction,
    ExportProfile,
    ExportSettings,
)


@dataclass
class ExportPredictorInput:
    """Inputs used by the live export size predictor."""

    width: int
    height: int
    export_settings: ExportSettings
    has_alpha: bool = False
    is_animated: bool = False
    frame_count: int = 1
    color_count_estimate: int | None = None
    complexity: float = 0.5
    threshold_bytes: int | None = None


@dataclass
class ExportPredictorResult:
    """Predictor output with UI-facing warnings and rating."""

    prediction: ExportPrediction
    warnings: list[str]
    compression_efficiency_rating: str


def predict_export_size(
    request: ExportPredictorInput,
    *,
    compare_formats: list[ExportFormat] | None = None,
) -> ExportPredictorResult:
    """Estimate export size and compare alternate formats."""

    width = max(1, request.width)
    height = max(1, request.height)
    complexity = clamp01(request.complexity)
    frame_count = max(1, request.frame_count if request.is_animated else 1)
    raw_bytes = width * height * (4 if request.has_alpha else 3) * frame_count

    primary_format = _resolve_primary_format(request)
    prediction_bytes = _estimate_bytes_for_format(
        file_format=primary_format,
        width=width,
        height=height,
        frame_count=frame_count,
        complexity=complexity,
        has_alpha=request.has_alpha,
        color_count_estimate=request.color_count_estimate,
        settings=request.export_settings,
    )

    formats_to_compare = compare_formats or list(
        profile_comparison_formats(request.export_settings.export_profile)
    )
    if primary_format not in formats_to_compare:
        formats_to_compare.insert(0, primary_format)

    comparison = [
        ExportComparisonEntry(
            format=fmt.value,
            predicted_bytes=_estimate_bytes_for_format(
                file_format=fmt,
                width=width,
                height=height,
                frame_count=frame_count,
                complexity=complexity,
                has_alpha=request.has_alpha,
                color_count_estimate=request.color_count_estimate,
                settings=request.export_settings,
            ),
        )
        for fmt in _dedupe_preserve_order(formats_to_compare)
    ]

    confidence = _predictor_confidence(request, primary_format)
    prediction = ExportPrediction(
        predicted_bytes=prediction_bytes,
        predicted_format=primary_format.value,
        confidence=confidence,
        comparison=comparison,
    )

    threshold = request.threshold_bytes
    if threshold is None:
        threshold = get_profile_rule(request.export_settings.export_profile).size_warning_threshold_bytes

    warnings: list[str] = []
    if threshold is not None and prediction_bytes > threshold:
        warnings.append(
            f"Predicted export size ({prediction_bytes} bytes) exceeds threshold ({threshold} bytes)"
        )
    if request.has_alpha and primary_format is ExportFormat.JPG:
        warnings.append("JPEG export does not preserve alpha transparency")

    efficiency_rating = _compression_efficiency_rating(prediction_bytes, raw_bytes)
    return ExportPredictorResult(
        prediction=prediction,
        warnings=warnings,
        compression_efficiency_rating=efficiency_rating,
    )


def _resolve_primary_format(request: ExportPredictorInput) -> ExportFormat:
    selected = request.export_settings.format
    if selected is not ExportFormat.AUTO:
        return selected

    if request.is_animated:
        return ExportFormat.GIF
    if request.has_alpha:
        return ExportFormat.PNG if request.export_settings.export_profile is ExportProfile.APP_ASSET else ExportFormat.WEBP
    if request.export_settings.export_profile is ExportProfile.PRINT:
        return ExportFormat.TIFF
    return ExportFormat.WEBP


def _estimate_bytes_for_format(
    *,
    file_format: ExportFormat,
    width: int,
    height: int,
    frame_count: int,
    complexity: float,
    has_alpha: bool,
    color_count_estimate: int | None,
    settings: ExportSettings,
) -> int:
    raw_frame_bytes = width * height * (4 if has_alpha else 3)
    raw_total = raw_frame_bytes * frame_count
    complexity = clamp01(complexity)
    quality = max(1, min(100, int(settings.quality)))
    compression_level = max(0, min(9, int(settings.compression_level)))
    palette_limit = settings.palette_limit

    if file_format is ExportFormat.PNG:
        factor = 0.10 + (0.42 * complexity) + (0.06 if has_alpha else 0.0) - (0.02 * (compression_level / 9))
        if palette_limit:
            factor *= max(0.2, min(1.0, palette_limit / 256))
        return max(128, int(raw_total * factor))

    if file_format is ExportFormat.JPG:
        chroma_factor = {
            "444": 1.12,
            "422": 1.0,
            "420": 0.86,
            "auto": 0.92 if complexity < 0.5 else 1.0,
        }.get(settings.chroma_subsampling.value, 1.0)
        q = quality / 100.0
        factor = (0.015 + 0.23 * (q ** 1.2) * (0.45 + 0.55 * complexity)) * chroma_factor
        return max(128, int(raw_total * factor))

    if file_format is ExportFormat.WEBP:
        q = quality / 100.0
        alpha_overhead = 0.04 if has_alpha else 0.0
        factor = 0.012 + 0.17 * (q ** 1.15) * (0.4 + 0.6 * complexity) + alpha_overhead
        return max(96, int(raw_total * factor))

    if file_format is ExportFormat.GIF:
        palette = palette_limit or max(2, min(256, settings.palette_limit or 256))
        palette_factor = max(0.08, min(1.0, palette / 256))
        dither_factor = 1.0 + (0.25 * max(0.0, min(1.0, settings.palette_limit / 256 if settings.palette_limit else 0.0)))
        anim_factor = 1.0 + (0.65 * math.log2(max(1, frame_count)))
        base = width * height * max(1, frame_count)
        return max(256, int(base * (0.12 + 0.35 * complexity) * palette_factor * dither_factor * anim_factor))

    if file_format is ExportFormat.ICO:
        sizes = settings.ico_sizes or [16, 32, 48, 64, 128, 256]
        total = 0
        for size in sizes:
            side = max(1, min(int(size), max(width, height)))
            total += _estimate_bytes_for_format(
                file_format=ExportFormat.PNG,
                width=side,
                height=side,
                frame_count=1,
                complexity=complexity,
                has_alpha=True,
                color_count_estimate=color_count_estimate,
                settings=settings,
            )
        return max(512, total + (16 * len(sizes)) + 6)

    if file_format is ExportFormat.TIFF:
        factor = 0.6 + (0.45 * complexity)
        return max(512, int(raw_total * factor))

    if file_format is ExportFormat.BMP:
        return max(256, raw_total + 54)

    if file_format is ExportFormat.AUTO:
        # Should be resolved before calling, but keep a safe fallback.
        return _estimate_bytes_for_format(
            file_format=ExportFormat.PNG if has_alpha else ExportFormat.WEBP,
            width=width,
            height=height,
            frame_count=frame_count,
            complexity=complexity,
            has_alpha=has_alpha,
            color_count_estimate=color_count_estimate,
            settings=settings,
        )

    return max(256, int(raw_total * 0.5))


def _predictor_confidence(request: ExportPredictorInput, primary_format: ExportFormat) -> float:
    base = 0.72
    if request.is_animated:
        base -= 0.08
    if primary_format in {ExportFormat.BMP, ExportFormat.TIFF, ExportFormat.ICO}:
        base += 0.05
    if request.color_count_estimate is None:
        base -= 0.05
    if request.complexity < 0.1 or request.complexity > 0.9:
        base -= 0.03
    return clamp01(base)


def _compression_efficiency_rating(predicted_bytes: int, raw_bytes: int) -> str:
    if raw_bytes <= 0:
        return "unknown"
    ratio = predicted_bytes / raw_bytes
    if ratio <= 0.08:
        return "excellent"
    if ratio <= 0.18:
        return "good"
    if ratio <= 0.35:
        return "fair"
    return "poor"


def _dedupe_preserve_order(formats: list[ExportFormat]) -> list[ExportFormat]:
    seen: set[ExportFormat] = set()
    out: list[ExportFormat] = []
    for fmt in formats:
        if fmt in seen:
            continue
        seen.add(fmt)
        out.append(fmt)
    return out






