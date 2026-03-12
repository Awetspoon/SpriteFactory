"""GIF analysis helpers (Prompt 8)."""

from __future__ import annotations

from dataclasses import dataclass

from engine.common.math_utils import clamp01


@dataclass
class GifScanInput:
    """Lightweight inputs for GIF palette/frame stress estimation."""

    frame_count: int
    palette_size: int
    duplicate_frame_ratio: float = 0.0
    motion_change_ratio: float = 0.5


def estimate_gif_palette_stress(scan: GifScanInput) -> float:
    """
    Estimate GIF palette stress in [0, 1] using a deterministic heuristic.

    This is intentionally lightweight for Prompt 8 and can be replaced with real frame/palette
    analysis later.
    """

    frame_factor = clamp01((scan.frame_count - 1) / 30.0)
    palette_factor = clamp01(scan.palette_size / 256.0)
    duplicate_relief = clamp01(scan.duplicate_frame_ratio)
    motion_factor = clamp01(scan.motion_change_ratio)

    # Higher palette usage + more motion + more frames increases stress, duplicates reduce it.
    return clamp01((0.4 * frame_factor) + (0.35 * palette_factor) + (0.25 * motion_factor) - (0.3 * duplicate_relief))


def estimate_gif_palette_stress_stub(*args, **kwargs) -> float:
    """Compatibility alias emphasizing that this remains a heuristic stub."""

    return estimate_gif_palette_stress(*args, **kwargs)





