"""Batch preset-rule helpers."""

from __future__ import annotations

from image_engine_app.app.services.preset_library import PresetLibrary
from image_engine_app.engine.models import EditMode, ExportFormat, ExportProfile, PresetModel


def build_batch_auto_preset_rules(library: PresetLibrary, *, enabled: bool) -> dict[str, list[PresetModel]]:
    auto_preset_rules: dict[str, list[PresetModel]] = {}
    if not enabled:
        return auto_preset_rules

    if library.has_preset("Pixel Clean Upscale"):
        pixel_cleanup = library.get("Pixel Clean Upscale")
        auto_preset_rules["pixel_art"] = [pixel_cleanup]
        auto_preset_rules["sprite_sheet"] = [pixel_cleanup]
    if library.has_preset("Photo Recover"):
        auto_preset_rules["photo"] = [library.get("Photo Recover")]
    if library.has_preset("GIF Safe Cleanup"):
        auto_preset_rules["animation"] = [library.get("GIF Safe Cleanup")]
    if library.has_preset("Artifact Cleanup"):
        auto_preset_rules.setdefault("artwork", []).append(library.get("Artifact Cleanup"))

    return auto_preset_rules


def build_batch_per_source_preset_rules(*, enabled: bool) -> dict[str, list[PresetModel]]:
    if not enabled:
        return {}

    return {
        "gif": [
            PresetModel(
                name="Batch GIF Export",
                description="Batch export rule for animated sources",
                settings_delta={"export": {"format": ExportFormat.GIF.value, "palette_limit": 256}},
                uses_heavy_tools=False,
                requires_apply=False,
                mode_min=EditMode.ADVANCED,
            )
        ],
        "png": [
            PresetModel(
                name="Batch PNG Export",
                description="Batch export rule for PNG sources",
                settings_delta={"export": {"format": ExportFormat.PNG.value}},
                uses_heavy_tools=False,
                requires_apply=False,
                mode_min=EditMode.ADVANCED,
            )
        ],
        "spritesheet": [
            PresetModel(
                name="Batch Spritesheet Export",
                description="Batch export rule for spritesheets",
                settings_delta={
                    "export": {
                        "export_profile": ExportProfile.APP_ASSET.value,
                        "format": ExportFormat.PNG.value,
                    }
                },
                uses_heavy_tools=False,
                requires_apply=False,
                mode_min=EditMode.ADVANCED,
            )
        ],
    }
