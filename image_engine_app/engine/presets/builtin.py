"""Curated system presets shared by Workspace, Preset Studio, and Batch."""

from __future__ import annotations

from typing import Any

from image_engine_app.engine.models import (
    EditMode,
    ExportFormat,
    ExportProfile,
    PresetModel,
    ScaleMethod,
)


PIXEL_CLEAN_UPSCALE = "Pixel Clean Upscale"
ARTIFACT_CLEANUP = "Artifact Cleanup"
PHOTO_RECOVER = "Photo Recover"
EDGE_REPAIR = "Edge Repair"
GIF_SAFE_CLEANUP = "GIF Safe Cleanup"


def _preset(
    name: str,
    description: str,
    *,
    formats: list[str],
    tags: list[str],
    settings: dict[str, Any],
    heavy: bool = False,
) -> PresetModel:
    return PresetModel(
        name=name,
        description=description,
        applies_to_formats=formats,
        applies_to_tags=tags,
        settings_delta=settings,
        uses_heavy_tools=heavy,
        requires_apply=heavy,
        mode_min=EditMode.ADVANCED,
    )


def build_builtin_presets() -> dict[str, PresetModel]:
    """Return one ordered, non-overlapping catalog of bundled presets."""

    presets = [
        _preset(
            PIXEL_CLEAN_UPSCALE,
            "Four-times recovery for small sprites using nearest-neighbour scaling.",
            formats=["png", "webp", "bmp"],
            tags=["pixel_art", "sprite_sheet", "ui", "icon"],
            settings={
                "pixel": {"pixel_snap": True, "scale_method": ScaleMethod.NEAREST.value},
                "cleanup": {"denoise": 0.12, "artifact_removal": 0.20, "halo_cleanup": 0.06},
                "detail": {"sharpen_amount": 0.20, "clarity": 0.10, "texture": 0.06},
                "ai": {"upscale_factor": 4.0, "deblur_strength": 0.10, "detail_reconstruct": 0.12},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.PNG.value},
            },
            heavy=True,
        ),
        _preset(
            "Sprite Crisp 2x",
            "Double sprite dimensions with hard pixel edges and light cleanup.",
            formats=["png", "webp", "bmp"],
            tags=["pixel_art", "ui", "icon"],
            settings={
                "pixel": {"resize_percent": 200.0, "pixel_snap": True, "scale_method": ScaleMethod.NEAREST.value},
                "detail": {"sharpen_amount": 0.16, "clarity": 0.08, "texture": 0.04},
                "cleanup": {"artifact_removal": 0.08, "halo_cleanup": 0.04},
            },
        ),
        _preset(
            "Sprite Crisp 4x",
            "Quadruple sprite dimensions with hard pixel edges and restrained sharpening.",
            formats=["png", "webp", "bmp"],
            tags=["pixel_art", "ui", "icon"],
            settings={
                "pixel": {"resize_percent": 400.0, "pixel_snap": True, "scale_method": ScaleMethod.NEAREST.value},
                "detail": {"sharpen_amount": 0.18, "clarity": 0.10, "texture": 0.05},
                "cleanup": {"artifact_removal": 0.10, "halo_cleanup": 0.04},
            },
        ),
        _preset(
            "Sprite Detail Boost",
            "Increase sprite readability without changing output dimensions.",
            formats=["png", "webp", "bmp", "tiff"],
            tags=["pixel_art", "artwork", "ui"],
            settings={
                "detail": {"sharpen_amount": 0.42, "clarity": 0.24, "texture": 0.16, "sharpen_threshold": 0.10},
                "cleanup": {"artifact_removal": 0.12, "halo_cleanup": 0.05},
            },
        ),
        _preset(
            "Sprite Sheet Prep",
            "Double a sprite sheet cleanly and keep PNG export settings.",
            formats=["png", "webp", "bmp"],
            tags=["sprite_sheet", "pixel_art", "ui"],
            settings={
                "pixel": {"resize_percent": 200.0, "pixel_snap": True, "scale_method": ScaleMethod.NEAREST.value},
                "cleanup": {"artifact_removal": 0.10, "halo_cleanup": 0.04},
                "detail": {"sharpen_amount": 0.12, "clarity": 0.06},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.PNG.value},
            },
        ),
        _preset(
            GIF_SAFE_CLEANUP,
            "Light frame-safe cleanup that keeps GIF timing and animation intact.",
            formats=["gif"],
            tags=["animation", "pixel_art", "artwork", "ui"],
            settings={
                "cleanup": {"denoise": 0.10, "artifact_removal": 0.14, "halo_cleanup": 0.05},
                "detail": {"sharpen_amount": 0.08, "clarity": 0.04, "texture": 0.02},
                "alpha": {"alpha_smooth": 0.04, "matte_fix": 0.05},
                "gif": {"dither_strength": 0.06, "palette_size": 256, "frame_optimize": True},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.GIF.value},
            },
        ),
        _preset(
            "GIF Crisp 2x",
            "Double an animated sprite with nearest-neighbour scaling and GIF-safe cleanup.",
            formats=["gif"],
            tags=["animation", "pixel_art", "ui"],
            settings={
                "pixel": {"resize_percent": 200.0, "pixel_snap": True, "scale_method": ScaleMethod.NEAREST.value},
                "cleanup": {"artifact_removal": 0.10, "halo_cleanup": 0.04},
                "detail": {"sharpen_amount": 0.08, "clarity": 0.04},
                "gif": {"dither_strength": 0.04, "palette_size": 256, "frame_optimize": True},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.GIF.value},
            },
        ),
        _preset(
            "PNG Alpha Clean",
            "Clean transparent sprite, artwork, logo, and UI edges without removing the background automatically.",
            formats=["png", "webp"],
            tags=["transparent", "ui", "logo", "icon", "pixel_art", "artwork"],
            settings={
                "cleanup": {"artifact_removal": 0.14, "halo_cleanup": 0.10},
                "edges": {"edge_refine": 0.16, "antialias": 0.10},
                "alpha": {"alpha_smooth": 0.08, "matte_fix": 0.10},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.PNG.value},
            },
        ),
        _preset(
            "ICO Icon Polish",
            "Polish small icon edges and retain an ICO-ready output profile.",
            formats=["ico", "png"],
            tags=["icon", "ui", "transparent"],
            settings={
                "detail": {"sharpen_amount": 0.18, "clarity": 0.10},
                "cleanup": {"artifact_removal": 0.10, "halo_cleanup": 0.08},
                "alpha": {"alpha_smooth": 0.06, "matte_fix": 0.10},
                "export": {"export_profile": ExportProfile.APP_ASSET.value, "format": ExportFormat.ICO.value},
            },
        ),
        _preset(
            ARTIFACT_CLEANUP,
            "Reduce compression blocks, color banding, and noise while protecting detail.",
            formats=["jpg", "png", "webp", "bmp", "tiff"],
            tags=["photo", "artwork", "texture"],
            settings={
                "cleanup": {"denoise": 0.34, "artifact_removal": 0.42, "halo_cleanup": 0.16, "banding_removal": 0.22},
                "detail": {"sharpen_amount": 0.06, "clarity": -0.04},
            },
        ),
        _preset(
            PHOTO_RECOVER,
            "Recover a blurred photo with deblur, reconstruction, and balanced cleanup.",
            formats=["jpg", "png", "webp", "bmp", "tiff"],
            tags=["photo"],
            settings={
                "detail": {"sharpen_amount": 0.34, "clarity": 0.24, "texture": 0.10},
                "cleanup": {"denoise": 0.22, "artifact_removal": 0.14},
                "ai": {"deblur_strength": 0.64, "detail_reconstruct": 0.34},
                "export": {"export_profile": ExportProfile.WEB.value, "format": ExportFormat.WEBP.value, "quality": 90},
            },
            heavy=True,
        ),
        _preset(
            EDGE_REPAIR,
            "Refine artwork and UI edges while reducing halos and rough alpha transitions.",
            formats=["png", "webp", "ico", "bmp"],
            tags=["artwork", "ui", "logo", "icon", "pixel_art"],
            settings={
                "edges": {"edge_refine": 0.40, "antialias": 0.20, "feather_px": 0.20, "grow_shrink_px": 0.0},
                "cleanup": {"halo_cleanup": 0.32},
                "alpha": {"alpha_smooth": 0.12},
            },
        ),
        _preset(
            "Texture Repair",
            "Smooth texture artifacts without flattening useful surface detail.",
            formats=["jpg", "png", "webp", "bmp", "tiff"],
            tags=["texture", "artwork"],
            settings={
                "cleanup": {"denoise": 0.22, "artifact_removal": 0.22, "banding_removal": 0.14},
                "detail": {"clarity": 0.10, "texture": 0.16, "sharpen_amount": 0.08},
            },
        ),
        _preset(
            "TIFF Print Clean",
            "Prepare TIFF artwork and scans for a clean print-oriented export.",
            formats=["tiff", "png"],
            tags=["photo", "artwork"],
            settings={
                "cleanup": {"denoise": 0.16, "artifact_removal": 0.12},
                "detail": {"clarity": 0.08, "sharpen_amount": 0.14},
                "export": {"export_profile": ExportProfile.PRINT.value, "format": ExportFormat.TIFF.value},
            },
        ),
        _preset(
            "WEBP Photo Finish",
            "Apply a restrained photo finish and efficient WEBP output settings.",
            formats=["jpg", "png", "webp"],
            tags=["photo", "artwork"],
            settings={
                "cleanup": {"denoise": 0.14, "artifact_removal": 0.12},
                "detail": {"clarity": 0.10, "sharpen_amount": 0.16},
                "export": {"export_profile": ExportProfile.WEB.value, "format": ExportFormat.WEBP.value, "quality": 90},
            },
        ),
        _preset(
            "Web Quick Export",
            "Use lightweight WEBP export defaults without adding visual edits.",
            formats=["jpg", "png", "webp", "bmp", "tiff"],
            tags=["*"],
            settings={
                "export": {
                    "export_profile": ExportProfile.WEB.value,
                    "format": ExportFormat.WEBP.value,
                    "quality": 84,
                    "strip_metadata": True,
                }
            },
        ),
    ]
    return {preset.name: preset for preset in presets}
