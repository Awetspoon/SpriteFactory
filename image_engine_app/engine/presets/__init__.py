"""Bundled preset catalog."""

from .builtin import (
    ARTIFACT_CLEANUP,
    EDGE_REPAIR,
    GIF_SAFE_CLEANUP,
    PHOTO_RECOVER,
    PIXEL_CLEAN_UPSCALE,
    build_builtin_presets,
)

__all__ = [
    "ARTIFACT_CLEANUP",
    "EDGE_REPAIR",
    "GIF_SAFE_CLEANUP",
    "PHOTO_RECOVER",
    "PIXEL_CLEAN_UPSCALE",
    "build_builtin_presets",
]
