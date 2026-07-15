"""Batch preset-rule helpers."""

from __future__ import annotations

from image_engine_app.app.services.preset_library import PresetLibrary
from image_engine_app.engine.models import PresetModel
from image_engine_app.engine.presets import (
    ARTIFACT_CLEANUP,
    GIF_SAFE_CLEANUP,
    PHOTO_RECOVER,
    PIXEL_CLEAN_UPSCALE,
)


def build_batch_auto_preset_rules(library: PresetLibrary, *, enabled: bool) -> dict[str, list[PresetModel]]:
    auto_preset_rules: dict[str, list[PresetModel]] = {}
    if not enabled:
        return auto_preset_rules

    if library.has_preset(PIXEL_CLEAN_UPSCALE):
        pixel_cleanup = library.get(PIXEL_CLEAN_UPSCALE)
        auto_preset_rules["pixel_art"] = [pixel_cleanup]
        auto_preset_rules["sprite_sheet"] = [pixel_cleanup]
    if library.has_preset(PHOTO_RECOVER):
        auto_preset_rules["photo"] = [library.get(PHOTO_RECOVER)]
    if library.has_preset(GIF_SAFE_CLEANUP):
        auto_preset_rules["animation"] = [library.get(GIF_SAFE_CLEANUP)]
    if library.has_preset(ARTIFACT_CLEANUP):
        auto_preset_rules.setdefault("artwork", []).append(library.get(ARTIFACT_CLEANUP))

    return auto_preset_rules
