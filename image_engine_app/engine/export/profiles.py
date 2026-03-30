"""Export profile rules and defaults (Prompt 12)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from image_engine_app.engine.models import ExportFormat, ExportProfile, ExportSettings


@dataclass(frozen=True)
class ExportProfileRule:
    """Defaults and predictor hints for a named export profile."""

    profile: ExportProfile
    default_format: ExportFormat
    default_quality: int
    default_compression_level: int
    strip_metadata: bool
    size_warning_threshold_bytes: int | None = None
    comparison_formats: tuple[ExportFormat, ...] = field(default_factory=tuple)


PROFILE_RULES: dict[ExportProfile, ExportProfileRule] = {
    ExportProfile.WEB: ExportProfileRule(
        profile=ExportProfile.WEB,
        default_format=ExportFormat.WEBP,
        default_quality=82,
        default_compression_level=6,
        strip_metadata=True,
        size_warning_threshold_bytes=2 * 1024 * 1024,
        comparison_formats=(ExportFormat.JPG, ExportFormat.WEBP, ExportFormat.PNG),
    ),
    ExportProfile.APP_ASSET: ExportProfileRule(
        profile=ExportProfile.APP_ASSET,
        default_format=ExportFormat.PNG,
        default_quality=100,
        default_compression_level=4,
        strip_metadata=True,
        size_warning_threshold_bytes=4 * 1024 * 1024,
        comparison_formats=(ExportFormat.PNG, ExportFormat.WEBP, ExportFormat.JPG, ExportFormat.ICO),
    ),
    ExportProfile.PRINT: ExportProfileRule(
        profile=ExportProfile.PRINT,
        default_format=ExportFormat.TIFF,
        default_quality=100,
        default_compression_level=0,
        strip_metadata=False,
        size_warning_threshold_bytes=20 * 1024 * 1024,
        comparison_formats=(ExportFormat.TIFF, ExportFormat.PNG, ExportFormat.JPG),
    ),
}


def get_profile_rule(profile: ExportProfile) -> ExportProfileRule:
    """Return profile rule metadata."""

    return PROFILE_RULES[profile]


def apply_profile_defaults(settings: ExportSettings, *, profile: ExportProfile | None = None) -> ExportSettings:
    """Return a copy of ExportSettings with profile defaults applied."""

    updated = deepcopy(settings)
    target_profile = profile or updated.export_profile
    rule = get_profile_rule(target_profile)

    updated.export_profile = target_profile
    if updated.format is ExportFormat.AUTO:
        updated.format = rule.default_format
    updated.quality = rule.default_quality if updated.quality <= 0 else updated.quality
    updated.compression_level = (
        rule.default_compression_level
        if updated.compression_level < 0
        else updated.compression_level
    )
    updated.strip_metadata = rule.strip_metadata
    return updated


def profile_comparison_formats(profile: ExportProfile) -> tuple[ExportFormat, ...]:
    """Return recommended comparison formats for the profile's predictor UI."""

    return get_profile_rule(profile).comparison_formats

