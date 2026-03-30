"""Deterministic quality analysis heuristics (Prompt 8)."""

from __future__ import annotations

from dataclasses import dataclass, field

from image_engine_app.engine.common.math_utils import clamp01

from image_engine_app.engine.models import AnalysisSummary, AssetFormat


@dataclass
class QualityScanInput:
    """Synthetic/statistical inputs for deterministic image quality heuristics."""

    width: int
    height: int
    file_format: AssetFormat = AssetFormat.UNKNOWN
    classification_tags: list[str] = field(default_factory=list)
    edge_density: float = 0.5
    high_frequency_ratio: float = 0.5
    noise_variance: float = 0.2
    blockiness: float = 0.0
    edge_continuity: float = 0.7
    banding_likelihood: float = 0.0


def scan_quality(stats: QualityScanInput) -> AnalysisSummary:
    """Compute analysis scores in the schema range [0, 1] using deterministic heuristics."""

    edge_density = clamp01(stats.edge_density)
    high_freq = clamp01(stats.high_frequency_ratio)
    noise_var = clamp01(stats.noise_variance)
    blockiness = clamp01(stats.blockiness)
    continuity = clamp01(stats.edge_continuity)
    banding = clamp01(stats.banding_likelihood)

    blur_score = clamp01(1.0 - (0.65 * high_freq + 0.35 * edge_density))

    noise_score = clamp01((0.75 * noise_var) + (0.1 * high_freq) + (0.15 * (1.0 - continuity)))

    lossy_weight = 1.0 if stats.file_format in {AssetFormat.JPG, AssetFormat.WEBP} else 0.65
    compression_score = clamp01((0.7 * blockiness * lossy_weight) + (0.3 * banding))

    edge_integrity_score = clamp01(
        (0.55 * continuity) + (0.25 * edge_density) + (0.2 * high_freq) - (0.25 * blockiness)
    )

    resolution_need_score = _estimate_resolution_need(
        width=stats.width,
        height=stats.height,
        tags=stats.classification_tags,
    )

    warnings: list[str] = []
    if blur_score >= 0.7:
        warnings.append("Blur appears high")
    if noise_score >= 0.65:
        warnings.append("Noise appears elevated")
    if compression_score >= 0.55:
        warnings.append("Compression artifacts likely visible")
    if resolution_need_score >= 0.7:
        warnings.append("Resolution may be insufficient for target use")
    if edge_integrity_score <= 0.35:
        warnings.append("Edge integrity appears weak")

    return AnalysisSummary(
        blur_score=blur_score,
        noise_score=noise_score,
        compression_score=compression_score,
        edge_integrity_score=edge_integrity_score,
        resolution_need_score=resolution_need_score,
        gif_palette_stress=None,
        warnings=warnings,
    )


def _estimate_resolution_need(*, width: int, height: int, tags: list[str]) -> float:
    width = max(0, width)
    height = max(0, height)
    if width == 0 or height == 0:
        return 1.0

    tag_set = set(tags)
    pixels = width * height

    if "icon" in tag_set:
        target_pixels = 128 * 128
    elif "pixel_art" in tag_set or "sprite_sheet" in tag_set:
        target_pixels = 256 * 256
    elif "ui" in tag_set:
        target_pixels = 512 * 512
    elif "photo" in tag_set:
        target_pixels = 1280 * 720
    else:
        target_pixels = 1024 * 1024

    ratio = pixels / target_pixels
    if ratio >= 1.0:
        return 0.0
    return clamp01(1.0 - ratio)






