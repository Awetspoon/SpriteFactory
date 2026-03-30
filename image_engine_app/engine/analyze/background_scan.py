"""Source transparency/background scan helpers for UI guidance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.models import BackgroundRemovalMode
from image_engine_app.engine.process.light_steps import build_background_cutout_keep_mask


@dataclass(frozen=True)
class BackgroundScanResult:
    can_inspect: bool = False
    has_transparent_pixels: bool = False
    white_coverage_ratio: float = 0.0
    black_coverage_ratio: float = 0.0
    sampled_frames: int = 0

    @property
    def likely_white_background(self) -> bool:
        return self.white_coverage_ratio >= 0.03 and self.white_coverage_ratio >= (self.black_coverage_ratio * 1.1)

    @property
    def likely_black_background(self) -> bool:
        return self.black_coverage_ratio >= 0.03 and self.black_coverage_ratio >= (self.white_coverage_ratio * 1.1)

    @property
    def recommended_mode(self) -> BackgroundRemovalMode | None:
        if self.likely_white_background:
            return BackgroundRemovalMode.WHITE
        if self.likely_black_background:
            return BackgroundRemovalMode.BLACK
        return None


def inspect_background_state(
    source_path: str | Path | None,
    *,
    max_frames: int = 3,
) -> BackgroundScanResult:
    """Inspect a local source file and estimate whether white/black cutout is warranted."""

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return BackgroundScanResult()

    if source_path is None:
        return BackgroundScanResult()

    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return BackgroundScanResult()

    try:
        with Image.open(path) as image:
            frame_total = max(1, int(getattr(image, "n_frames", 1) or 1))
            frame_indices = _sample_frame_indices(frame_total, max(1, int(max_frames)))
            seen_transparency = False
            white_ratio = 0.0
            black_ratio = 0.0

            for frame_index in frame_indices:
                try:
                    image.seek(frame_index)
                except EOFError:
                    break

                rgba = image.convert("RGBA")
                alpha = rgba.getchannel("A")
                alpha_min, alpha_max = alpha.getextrema()
                seen_transparency = seen_transparency or alpha_min < 250 or alpha_max < 255

                rgb = _visible_rgb_for_scan(rgba, alpha)
                white_ratio = max(
                    white_ratio,
                    _mask_removed_ratio(build_background_cutout_keep_mask(rgb, BackgroundRemovalMode.WHITE)),
                )
                black_ratio = max(
                    black_ratio,
                    _mask_removed_ratio(build_background_cutout_keep_mask(rgb, BackgroundRemovalMode.BLACK)),
                )

            return BackgroundScanResult(
                can_inspect=True,
                has_transparent_pixels=seen_transparency,
                white_coverage_ratio=white_ratio,
                black_coverage_ratio=black_ratio,
                sampled_frames=len(frame_indices),
            )
    except Exception:
        return BackgroundScanResult()


def _sample_frame_indices(frame_total: int, max_frames: int) -> tuple[int, ...]:
    if frame_total <= 1 or max_frames <= 1:
        return (0,)
    if frame_total <= max_frames:
        return tuple(range(frame_total))

    last = frame_total - 1
    values = {int(round((last * idx) / (max_frames - 1))) for idx in range(max_frames)}
    return tuple(sorted(values))


def _visible_rgb_for_scan(rgba_image, alpha_image):
    from PIL import Image  # type: ignore

    rgb = Image.new("RGB", rgba_image.size, (127, 127, 127))
    rgb.paste(rgba_image.convert("RGB"), mask=alpha_image)
    return rgb


def _mask_removed_ratio(mask_image) -> float:
    histogram = mask_image.histogram()
    total = sum(histogram)
    if total <= 0:
        return 0.0

    removed = 0.0
    for value, count in enumerate(histogram):
        if count <= 0:
            continue
        removed += (255 - value) * count
    return float(removed / (255.0 * total))
