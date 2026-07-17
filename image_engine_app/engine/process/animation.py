"""Shared animated-GIF frame processing and encoding."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.models import GifSettings
from image_engine_app.engine.process.errors import ProcessingError, ProcessingUnavailable
from image_engine_app.engine.process.pillow_runtime import require_pillow


@dataclass(frozen=True)
class AnimatedGifResult:
    """Outcome of encoding an animated GIF."""

    output_path: Path
    logical_size: tuple[int, int]
    encoded_size: tuple[int, int]
    frame_count: int


def quantize_gif_frame(
    rgba_image,
    *,
    palette_size: int,
    transparency_threshold: int = 24,
    dither_strength: float = 0.0,
):
    """Quantize one RGBA frame while preserving binary GIF transparency."""

    Image, _, _, _ = require_pillow()
    frame = rgba_image.convert("RGBA")
    colors = max(2, min(256, int(palette_size or 256)))
    dither = Image.Dither.FLOYDSTEINBERG if float(dither_strength) > 0.0 else Image.Dither.NONE
    alpha = frame.getchannel("A")
    transparent_mask = alpha.point(
        lambda value: 255 if int(value) <= int(transparency_threshold) else 0,
        mode="L",
    )

    if transparent_mask.getbbox() is None:
        return frame.quantize(
            colors=colors,
            method=getattr(Image, "FASTOCTREE", 2),
            dither=dither,
        )

    quantized = frame.convert("RGB").quantize(
        colors=max(2, min(255, colors - 1)),
        method=getattr(Image, "FASTOCTREE", 2),
        dither=dither,
    )
    palette = list(quantized.getpalette() or [])
    if len(palette) < 768:
        palette.extend([0] * (768 - len(palette)))
    transparency_index = 255
    palette[transparency_index * 3 : (transparency_index * 3) + 3] = [0, 0, 0]
    quantized.putpalette(palette)
    quantized.paste(transparency_index, mask=transparent_mask)
    quantized.info["transparency"] = transparency_index
    quantized.info["background"] = transparency_index
    quantized.info["disposal"] = 2
    return quantized


def save_animated_gif(
    source_image,
    output_path: str | Path,
    *,
    gif_settings: GifSettings,
    frame_transform: Callable[[object], object] | None = None,
    target_size: tuple[int, int] | None = None,
    preserve_canvas_size: bool = False,
    resize_resample: int | None = None,
    default_duration_ms: int = 100,
) -> AnimatedGifResult:
    """Transform and encode every source frame through one shared GIF path."""

    Image, _, _, _ = require_pillow()
    try:
        from PIL import ImageSequence  # type: ignore
    except Exception as exc:  # pragma: no cover - covered by Pillow availability checks
        raise ProcessingUnavailable("Pillow animation support is unavailable.") from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_size = (int(source_image.size[0]), int(source_image.size[1]))
    normalized_target = None
    if target_size is not None:
        normalized_target = (max(1, int(target_size[0])), max(1, int(target_size[1])))
    resample = resize_resample
    if resample is None:
        resample = int(getattr(Image.Resampling, "NEAREST", Image.NEAREST))

    settings = gif_settings
    delay_override = max(0, int(getattr(settings, "frame_delay_ms", 0) or 0))
    source_duration = _normalize_duration(
        getattr(source_image, "info", {}).get("duration"),
        default=default_duration_ms,
    )
    disposal = _normalize_disposal(
        getattr(source_image, "info", {}).get("disposal", 2)
    )

    frames: list[object] = []
    durations: list[int] = []
    logical_size: tuple[int, int] | None = None
    encoded_size: tuple[int, int] | None = None

    for source_frame in ImageSequence.Iterator(source_image):
        rendered = source_frame.convert("RGBA")
        if frame_transform is not None:
            rendered = frame_transform(rendered)
        if normalized_target is not None and rendered.size != normalized_target:
            rendered = rendered.resize(normalized_target, resample=resample)

        if logical_size is None:
            logical_size = (int(rendered.size[0]), int(rendered.size[1]))
        if preserve_canvas_size and rendered.size != source_size:
            rendered = rendered.resize(source_size, resample=resample)
        if encoded_size is None:
            encoded_size = (int(rendered.size[0]), int(rendered.size[1]))

        frame_duration = _normalize_duration(
            getattr(source_frame, "info", {}).get("duration"),
            default=source_duration,
        )
        durations.append(delay_override or frame_duration)
        frames.append(
            quantize_gif_frame(
                rendered,
                palette_size=int(getattr(settings, "palette_size", 256) or 256),
                transparency_threshold=24,
                dither_strength=float(getattr(settings, "dither_strength", 0.0) or 0.0),
            )
        )

    if not frames or logical_size is None or encoded_size is None:
        raise ProcessingError("Animated GIF source contained no frames.")

    save_options: dict[str, object] = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations if len(durations) > 1 else durations[0],
        "optimize": bool(getattr(settings, "frame_optimize", True)),
        "disposal": disposal,
    }
    if bool(getattr(settings, "loop", True)):
        raw_loop_count = getattr(settings, "loop_count", 0)
        try:
            loop_count = max(0, int(raw_loop_count)) if raw_loop_count is not None else 0
        except (TypeError, ValueError, OverflowError):
            loop_count = 0
        save_options["loop"] = loop_count
    else:
        for frame in frames:
            frame.info.pop("loop", None)

    frames[0].save(output, format="GIF", **save_options)
    return AnimatedGifResult(
        output_path=output,
        logical_size=logical_size,
        encoded_size=encoded_size,
        frame_count=len(frames),
    )


def _normalize_duration(raw_value: object, *, default: int) -> int:
    try:
        duration = int(raw_value)
    except Exception:
        duration = int(default)
    if duration <= 0:
        duration = int(default)
    return max(20, duration)


def _normalize_disposal(raw_value: object) -> int:
    try:
        disposal = int(raw_value)
    except Exception:
        disposal = 2
    return disposal if disposal in {0, 1, 2, 3} else 2
