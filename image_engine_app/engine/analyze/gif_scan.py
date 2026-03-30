"""GIF analysis helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from image_engine_app.engine.common.math_utils import clamp01


@dataclass
class GifScanInput:
    """Lightweight inputs for GIF palette/frame stress estimation."""

    frame_count: int
    palette_size: int
    duplicate_frame_ratio: float = 0.0
    motion_change_ratio: float = 0.5


def estimate_gif_palette_stress(scan: GifScanInput) -> float:
    """Estimate GIF palette stress in ``[0, 1]`` from normalized inputs."""

    frame_factor = clamp01((scan.frame_count - 1) / 30.0)
    palette_factor = clamp01(scan.palette_size / 256.0)
    duplicate_relief = clamp01(scan.duplicate_frame_ratio)
    motion_factor = clamp01(scan.motion_change_ratio)

    # Higher palette usage + more motion + more frames increases stress, duplicates reduce it.
    return clamp01((0.4 * frame_factor) + (0.35 * palette_factor) + (0.25 * motion_factor) - (0.3 * duplicate_relief))


def estimate_gif_palette_stress_from_path(
    source_path: str | Path | None,
    *,
    sample_frame_limit: int = 24,
) -> float | None:
    """Estimate GIF palette stress from a real GIF file when one is available."""

    if source_path is None:
        return None

    try:
        from PIL import Image, ImageChops, ImageStat  # type: ignore
    except Exception:
        return None

    try:
        path = Path(source_path)
    except Exception:
        return None
    if not path.exists() or not path.is_file():
        return None

    try:
        with Image.open(path) as im:
            frame_count = int(getattr(im, "n_frames", 1) or 1)
            if frame_count <= 0:
                return None

            sample_indexes = _sample_frame_indexes(frame_count, sample_frame_limit=sample_frame_limit)
            palette_size = 0
            duplicate_transitions = 0
            motion_values: list[float] = []
            previous_frame = None
            previous_hash = None

            for frame_index in sample_indexes:
                im.seek(frame_index)
                frame = _normalize_analysis_frame(im.convert("RGBA"))

                colors = frame.getcolors(maxcolors=257)
                palette_size = max(palette_size, 256 if colors is None else len(colors))

                frame_hash = hashlib.sha1(frame.tobytes()).digest()
                if previous_hash is not None and frame_hash == previous_hash:
                    duplicate_transitions += 1
                if previous_frame is not None:
                    diff = ImageChops.difference(previous_frame, frame).convert("L")
                    motion_values.append(clamp01(float(ImageStat.Stat(diff).mean[0]) / 255.0))

                previous_frame = frame.copy()
                previous_hash = frame_hash

            duplicate_ratio = (
                duplicate_transitions / max(1, len(sample_indexes) - 1)
                if len(sample_indexes) > 1
                else 0.0
            )
            motion_ratio = sum(motion_values) / len(motion_values) if motion_values else 0.0

            return estimate_gif_palette_stress(
                GifScanInput(
                    frame_count=frame_count,
                    palette_size=max(1, palette_size),
                    duplicate_frame_ratio=duplicate_ratio,
                    motion_change_ratio=motion_ratio,
                )
            )
    except Exception:
        return None


def estimate_gif_palette_stress_for_source(
    *,
    source_path: str | Path | None,
    fallback_scan: GifScanInput,
    sample_frame_limit: int = 24,
) -> float:
    """Estimate stress from a file when possible, otherwise fall back to heuristic inputs."""

    measured = estimate_gif_palette_stress_from_path(
        source_path,
        sample_frame_limit=sample_frame_limit,
    )
    if measured is not None:
        return measured
    return estimate_gif_palette_stress(fallback_scan)


def _sample_frame_indexes(frame_count: int, *, sample_frame_limit: int) -> list[int]:
    frame_count = max(1, int(frame_count))
    sample_frame_limit = max(1, int(sample_frame_limit))
    if frame_count <= sample_frame_limit:
        return list(range(frame_count))

    last_index = frame_count - 1
    seen: set[int] = set()
    indexes: list[int] = []
    for slot in range(sample_frame_limit):
        idx = int(round((slot * last_index) / max(1, sample_frame_limit - 1)))
        idx = min(last_index, max(0, idx))
        if idx in seen:
            continue
        seen.add(idx)
        indexes.append(idx)
    if last_index not in seen:
        indexes.append(last_index)
    return sorted(indexes)


def _normalize_analysis_frame(frame):
    max_dim = 96
    if frame.width <= max_dim and frame.height <= max_dim:
        return frame

    scale = min(max_dim / max(1, frame.width), max_dim / max(1, frame.height))
    target_size = (
        max(1, int(round(frame.width * scale))),
        max(1, int(round(frame.height * scale))),
    )
    return frame.resize(target_size)



