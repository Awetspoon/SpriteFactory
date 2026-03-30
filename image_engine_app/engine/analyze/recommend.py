"""Recommendation heuristics and confidence scoring (Prompt 8)."""

from __future__ import annotations

from dataclasses import dataclass, field

from image_engine_app.engine.common.math_utils import clamp01

from image_engine_app.engine.models import (
    AnalysisSummary,
    AssetFormat,
    PresetSuggestion,
    RecommendationsSummary,
)


@dataclass
class RecommendationInput:
    """Inputs required to generate rule-based recommendations."""

    file_format: AssetFormat = AssetFormat.UNKNOWN
    classification_tags: list[str] = field(default_factory=list)
    analysis: AnalysisSummary = field(default_factory=AnalysisSummary)
    has_alpha: bool = False
    is_animated: bool = False


def build_recommendations(context: RecommendationInput) -> RecommendationsSummary:
    """Generate preset/export suggestions with deterministic confidence scoring."""

    tags = set(context.classification_tags)
    analysis = context.analysis
    suggestions: list[PresetSuggestion] = []

    if {"pixel_art", "sprite_sheet"} & tags:
        confidence = clamp01(0.62 + (0.35 * analysis.resolution_need_score))
        suggestions.append(
            PresetSuggestion(
                preset_name="Pixel Clean Upscale",
                confidence=confidence,
                reason="Pixel/sprite content benefits from clean scaling and edge-safe cleanup.",
            )
        )

    if context.is_animated:
        confidence = clamp01(0.66 + (0.18 * (analysis.compression_score or 0.0)) + (0.12 * (analysis.noise_score or 0.0)))
        suggestions.append(
            PresetSuggestion(
                preset_name="GIF Safe Cleanup",
                confidence=confidence,
                reason="Animated content benefits from lighter frame-safe cleanup and GIF-tuned export settings.",
            )
        )

    if analysis.compression_score >= 0.45 or analysis.noise_score >= 0.45:
        confidence = clamp01(0.58 + (0.22 * analysis.compression_score) + (0.2 * analysis.noise_score))
        suggestions.append(
            PresetSuggestion(
                preset_name="Artifact Cleanup",
                confidence=confidence,
                reason="Compression/noise indicators suggest cleanup before export.",
            )
        )

    if "photo" in tags and analysis.blur_score >= 0.45:
        confidence = clamp01(0.5 + (0.35 * analysis.blur_score))
        suggestions.append(
            PresetSuggestion(
                preset_name="Photo Recover",
                confidence=confidence,
                reason="Photo-like content with blur indicators may benefit from deblur/sharpen workflow.",
            )
        )

    if analysis.edge_integrity_score <= 0.35 and "pixel_art" not in tags:
        confidence = clamp01(0.48 + (0.4 * (1.0 - analysis.edge_integrity_score)))
        suggestions.append(
            PresetSuggestion(
                preset_name="Edge Repair",
                confidence=confidence,
                reason="Weak edge integrity suggests edge refinement and halo cleanup.",
            )
        )

    suggestions = _dedupe_suggestions_sorted(suggestions)

    suggested_export_profile = _recommend_export_profile(tags)
    suggested_export_format = _recommend_export_format(
        file_format=context.file_format,
        has_alpha=context.has_alpha,
        is_animated=context.is_animated,
        tags=tags,
    )

    return RecommendationsSummary(
        suggested_presets=suggestions,
        suggested_export_profile=suggested_export_profile,
        suggested_export_format=suggested_export_format,
    )


def _recommend_export_profile(tags: set[str]) -> str | None:
    if "icon" in tags or "ui" in tags or "sprite_sheet" in tags:
        return "app_asset"
    if "photo" in tags:
        return "web"
    if "texture" in tags:
        return "app_asset"
    if "artwork" in tags:
        return "print"
    return None


def _recommend_export_format(
    *,
    file_format: AssetFormat,
    has_alpha: bool,
    is_animated: bool,
    tags: set[str],
) -> str | None:
    if is_animated:
        return "gif"

    if "icon" in tags:
        return "ico"

    if has_alpha:
        if "photo" in tags:
            return "webp"
        return "png"

    if "photo" in tags:
        return "webp"

    if file_format is AssetFormat.JPG:
        return "jpg"

    return "png"


def _dedupe_suggestions_sorted(suggestions: list[PresetSuggestion]) -> list[PresetSuggestion]:
    by_name: dict[str, PresetSuggestion] = {}
    for suggestion in suggestions:
        existing = by_name.get(suggestion.preset_name)
        if existing is None or suggestion.confidence > existing.confidence:
            by_name[suggestion.preset_name] = suggestion
    return sorted(by_name.values(), key=lambda item: (-item.confidence, item.preset_name))






