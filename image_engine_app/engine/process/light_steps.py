"""Non-AI light processing steps (real MVP implementation).

This module upgrades the earlier placeholder into a minimal Pillow-based pipeline
so presets + batch runs can produce real pixel changes.

Design goals:
- Keep operations deterministic and conservative (avoid surprising results).
- Support a small core of spec features needed for v1 MVP:
  - Resize (percent/width/height)
  - Denoise (median/gaussian blend)
  - Sharpen (unsharp mask)
  - Basic color adjust (brightness/contrast/saturation/gamma)
  - Edge/transparency cleanup controls
  - Alpha threshold (optional)
- Be tolerant of environments without Pillow (raises LightStepUnavailable).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.models import (
    BackgroundRemovalMode,
    ScaleMethod,
    SettingsState,
    normalize_background_removal_mode,
)


class LightStepUnavailable(RuntimeError):
    """Raised when Pillow is not available for light processing."""


class LightProcessError(RuntimeError):
    """Raised when light processing fails to produce an output."""


@dataclass(frozen=True)
class LightProcessResult:
    """Outcome of a light processing run."""

    output_path: Path
    size: tuple[int, int]


def render_light_image(image, settings: SettingsState, *, target_size: tuple[int, int] | None = None):
    """Apply the light pipeline to an in-memory Pillow image and return the processed result."""

    _require_pillow()
    im = image.copy()

    if im.mode not in {"RGB", "RGBA"}:
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

    pixel_settings = settings.pixel
    desired_size = _compute_target_size(
        im.size,
        resize_percent=float(pixel_settings.resize_percent or 100.0),
        width=pixel_settings.width,
        height=pixel_settings.height,
    )
    resample = _resample_from_method(pixel_settings.scale_method, pixel_snap=bool(pixel_settings.pixel_snap))
    if desired_size != im.size:
        im = im.resize(desired_size, resample=resample)

    if target_size is not None:
        normalized_target = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        if im.size != normalized_target:
            im = im.resize(normalized_target, resample=resample)

    im = _apply_ai_preview(im, settings)
    im = _apply_cleanup(im, settings)
    im = _apply_detail(im, settings)
    im = _apply_edges(im, settings)
    im = _apply_color_adjust(im, settings)
    im = _apply_alpha_rules(im, settings)
    return im


def _require_pillow():
    try:
        from PIL import Image  # type: ignore
        from PIL import ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise LightStepUnavailable("Pillow is required for light processing.") from exc
    return Image, ImageEnhance, ImageFilter, ImageOps


def _resample_from_method(method: ScaleMethod, *, pixel_snap: bool) -> int:
    Image, _, _, _ = _require_pillow()
    if pixel_snap:
        return int(getattr(Image.Resampling, "NEAREST", Image.NEAREST))
    mapping = {
        ScaleMethod.NEAREST: getattr(Image.Resampling, "NEAREST", Image.NEAREST),
        ScaleMethod.BILINEAR: getattr(Image.Resampling, "BILINEAR", Image.BILINEAR),
        ScaleMethod.BICUBIC: getattr(Image.Resampling, "BICUBIC", Image.BICUBIC),
        ScaleMethod.LANCZOS: getattr(Image.Resampling, "LANCZOS", Image.LANCZOS),
    }
    return int(mapping.get(method, getattr(Image.Resampling, "LANCZOS", Image.LANCZOS)))


def _compute_target_size(
    original: tuple[int, int],
    *,
    resize_percent: float,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    ow, oh = original
    if ow <= 0 or oh <= 0:
        return (max(1, ow), max(1, oh))

    if width and height:
        return (max(1, int(width)), max(1, int(height)))

    if width and not height:
        ratio = oh / ow
        return (max(1, int(width)), max(1, int(round(width * ratio))))

    if height and not width:
        ratio = ow / oh
        return (max(1, int(round(height * ratio))), max(1, int(height)))

    if resize_percent and abs(resize_percent - 100.0) > 0.001:
        factor = max(0.01, float(resize_percent) / 100.0)
        return (max(1, int(round(ow * factor))), max(1, int(round(oh * factor))))

    return (ow, oh)


def _apply_color_adjust(img, settings: SettingsState):
    Image, ImageEnhance, _, _ = _require_pillow()
    s = settings.color

    # Pillow enhancers expect 1.0 as "no change". Our sliders are centered at 0.0.
    if abs(float(s.brightness)) > 1e-6:
        img = ImageEnhance.Brightness(img).enhance(1.0 + float(s.brightness))
    if abs(float(s.contrast)) > 1e-6:
        img = ImageEnhance.Contrast(img).enhance(1.0 + float(s.contrast))
    if abs(float(s.saturation)) > 1e-6:
        img = ImageEnhance.Color(img).enhance(1.0 + float(s.saturation))

    gamma = float(s.gamma) if s.gamma else 1.0
    if gamma and abs(gamma - 1.0) > 1e-6:
        inv = 1.0 / max(1e-6, gamma)
        lut = [int(round(((i / 255.0) ** inv) * 255.0)) for i in range(256)]
        if img.mode == "RGBA":
            # Keep alpha untouched: gamma is a color-tone adjustment, not transparency.
            r, g, b, a = img.split()
            img = Image.merge("RGBA", (r.point(lut), g.point(lut), b.point(lut), a))
        elif img.mode == "RGB":
            img = img.point(lut * 3)
        else:
            img = img.point(lut)

    temperature = max(-1.0, min(1.0, float(getattr(s, "temperature", 0.0) or 0.0)))
    if abs(temperature) > 1e-6:
        img = _apply_temperature_adjust(img, temperature=temperature)

    curves = getattr(s, "curves", None)
    if curves:
        img = _apply_curves_adjust(img, curves=curves)

    return img


def _apply_temperature_adjust(img, *, temperature: float):
    Image, _, _, _ = _require_pillow()

    if img.mode not in {"RGB", "RGBA", "L"}:
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    if img.mode == "L":
        rgb = img.convert("RGB")
        adjusted = _apply_temperature_adjust(rgb, temperature=temperature)
        return adjusted.convert("L")

    shift = max(-1.0, min(1.0, float(temperature)))
    red_gain = 1.0 + (0.18 * shift)
    green_gain = 1.0 + (0.05 * shift)
    blue_gain = 1.0 - (0.18 * shift)

    red_lut = [_clamp_channel(value * red_gain) for value in range(256)]
    green_lut = [_clamp_channel(value * green_gain) for value in range(256)]
    blue_lut = [_clamp_channel(value * blue_gain) for value in range(256)]

    if img.mode == "RGBA":
        r, g, b, a = img.split()
        return Image.merge("RGBA", (r.point(red_lut), g.point(green_lut), b.point(blue_lut), a))

    r, g, b = img.split()
    return Image.merge("RGB", (r.point(red_lut), g.point(green_lut), b.point(blue_lut)))


def _apply_curves_adjust(img, *, curves):
    Image, _, _, _ = _require_pillow()

    if not isinstance(curves, dict):
        return img

    rgb_curve = _build_curve_lut(curves.get("rgb"))
    red_curve = _build_curve_lut(curves.get("r"))
    green_curve = _build_curve_lut(curves.get("g"))
    blue_curve = _build_curve_lut(curves.get("b"))

    if not any(lut is not None for lut in (rgb_curve, red_curve, green_curve, blue_curve)):
        return img

    if img.mode not in {"RGB", "RGBA"}:
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    if img.mode == "RGBA":
        r, g, b, a = img.split()
    else:
        r, g, b = img.split()
        a = None

    if rgb_curve is not None:
        r = r.point(rgb_curve)
        g = g.point(rgb_curve)
        b = b.point(rgb_curve)
    if red_curve is not None:
        r = r.point(red_curve)
    if green_curve is not None:
        g = g.point(green_curve)
    if blue_curve is not None:
        b = b.point(blue_curve)

    if a is not None:
        return Image.merge("RGBA", (r, g, b, a))
    return Image.merge("RGB", (r, g, b))


def _build_curve_lut(points) -> list[int] | None:
    if not isinstance(points, (list, tuple)):
        return None

    parsed: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        try:
            x = _clamp_channel(point[0])
            y = _clamp_channel(point[1])
        except Exception:
            continue
        parsed.append((x, y))

    if not parsed:
        return None

    parsed.sort(key=lambda item: item[0])
    if parsed[0][0] != 0:
        parsed.insert(0, (0, parsed[0][1]))
    if parsed[-1][0] != 255:
        parsed.append((255, parsed[-1][1]))

    lut: list[int | None] = [None] * 256
    for idx in range(len(parsed) - 1):
        x1, y1 = parsed[idx]
        x2, y2 = parsed[idx + 1]
        if x2 <= x1:
            continue
        span = x2 - x1
        for x in range(x1, x2 + 1):
            ratio = (x - x1) / span
            lut[x] = _clamp_channel(y1 + ((y2 - y1) * ratio))

    for x in range(256):
        if lut[x] is not None:
            continue
        lut[x] = 0 if x == 0 else lut[x - 1]
    return [int(value or 0) for value in lut]


def _clamp_channel(value: float | int) -> int:
    return max(0, min(255, int(round(float(value)))))


def _apply_cleanup(img, settings: SettingsState):
    _, _, ImageFilter, _ = _require_pillow()
    s = settings.cleanup

    # Denoise in [0,1] -> radius in [0,2]
    denoise = max(0.0, float(s.denoise))
    artifact = max(0.0, float(s.artifact_removal))
    banding = max(0.0, float(s.banding_removal))
    halo = max(0.0, float(s.halo_cleanup))

    strength = max(denoise, artifact, banding, halo)
    if strength <= 1e-6:
        return img

    # Conservative blend: median filter for small impulse noise + light gaussian blur.
    median_size = 3 if strength < 0.35 else 5
    blurred = img.filter(ImageFilter.MedianFilter(size=median_size))

    radius = min(2.0, 0.5 + (strength * 1.5))
    blurred2 = blurred.filter(ImageFilter.GaussianBlur(radius=radius))

    # Blend back toward original so we don't destroy edges.
    blend_alpha = min(0.65, 0.15 + (strength * 0.5))
    try:
        from PIL import ImageChops  # type: ignore

        out = ImageChops.blend(img, blurred2, blend_alpha)
        return out
    except Exception:
        return blurred2


def _apply_detail(img, settings: SettingsState):
    Image, _, ImageFilter, _ = _require_pillow()
    s = settings.detail
    amount = float(s.sharpen_amount)
    clarity = float(s.clarity)
    texture = float(s.texture)

    if max(abs(amount), abs(clarity), abs(texture)) <= 1e-6:
        return img

    out = img

    # Primary sharpen control.
    # Positive sharpens, negative softly blurs to help beginners back off crunchy results.
    if amount > 1e-6:
        radius = float(s.sharpen_radius) if s.sharpen_radius else 1.0
        radius = max(0.1, min(3.0, radius))
        threshold = int(max(0.0, float(s.sharpen_threshold or 0.0)) * 10)
        percent = int(round(min(240.0, amount * 120.0)))
        if percent > 0:
            out = out.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
    elif amount < -1e-6:
        soften = min(1.0, abs(amount) / 2.0)
        soft_layer = out.filter(ImageFilter.GaussianBlur(radius=0.35 + (soften * 1.2)))
        out = Image.blend(out, soft_layer, min(0.45, 0.08 + (soften * 0.25)))

    # Clarity/texture are subtle overlays.
    # Positive increases structure; negative softens structure.
    clarity_norm = min(1.0, abs(clarity) / 2.0)
    texture_norm = min(1.0, abs(texture) / 2.0)

    if bool(getattr(getattr(settings, "pixel", None), "pixel_snap", False)):
        clarity_norm *= 0.75
        texture_norm *= 0.7

    if clarity > 1e-6 and clarity_norm > 1e-6:
        clarity_layer = out.filter(
            ImageFilter.UnsharpMask(
                radius=1.4 + (clarity_norm * 0.8),
                percent=int(round(18 + (clarity_norm * 42))),
                threshold=3,
            )
        )
        out = Image.blend(out, clarity_layer, min(0.28, 0.05 + (clarity_norm * 0.18)))
    elif clarity < -1e-6 and clarity_norm > 1e-6:
        clarity_soft = out.filter(ImageFilter.GaussianBlur(radius=0.55 + (clarity_norm * 0.95)))
        out = Image.blend(out, clarity_soft, min(0.30, 0.06 + (clarity_norm * 0.20)))

    if texture > 1e-6 and texture_norm > 1e-6:
        texture_layer = out.filter(
            ImageFilter.UnsharpMask(
                radius=0.45 + (texture_norm * 0.55),
                percent=int(round(14 + (texture_norm * 34))),
                threshold=2,
            )
        )
        out = Image.blend(out, texture_layer, min(0.24, 0.04 + (texture_norm * 0.16)))
    elif texture < -1e-6 and texture_norm > 1e-6:
        texture_soft = out.filter(ImageFilter.GaussianBlur(radius=0.35 + (texture_norm * 0.75)))
        out = Image.blend(out, texture_soft, min(0.26, 0.05 + (texture_norm * 0.18)))

    return out

def _apply_ai_preview(img, settings: SettingsState):
    """Fast non-AI approximation so AI sliders update live preview."""

    Image, _, ImageFilter, _ = _require_pillow()
    s = settings.ai

    upscale_factor = max(1.0, float(getattr(s, "upscale_factor", 1.0) or 1.0))
    deblur_strength = max(0.0, float(getattr(s, "deblur_strength", 0.0) or 0.0))
    detail_reconstruct = max(0.0, float(getattr(s, "detail_reconstruct", 0.0) or 0.0))

    if max(upscale_factor - 1.0, deblur_strength, detail_reconstruct) <= 1e-6:
        return img

    out = img

    # Keep live preview responsive while still reflecting the upscale control.
    preview_factor = min(4.0, upscale_factor)
    if preview_factor > 1.0:
        p = settings.pixel
        resample = _resample_from_method(p.scale_method, pixel_snap=bool(p.pixel_snap))
        target = (
            max(1, int(round(out.width * preview_factor))),
            max(1, int(round(out.height * preview_factor))),
        )
        out = out.resize(target, resample=resample)

    if deblur_strength > 1e-6:
        out = out.filter(
            ImageFilter.UnsharpMask(
                radius=min(3.0, 0.8 + (deblur_strength * 1.2)),
                percent=int(round(min(220.0, 25.0 + (deblur_strength * 110.0)))),
                threshold=1,
            )
        )

    if detail_reconstruct > 1e-6:
        layer = out.filter(
            ImageFilter.UnsharpMask(
                radius=min(2.0, 0.5 + (detail_reconstruct * 0.9)),
                percent=int(round(min(200.0, 20.0 + (detail_reconstruct * 90.0)))),
                threshold=0,
            )
        )
        out = Image.blend(out, layer, min(0.35, 0.08 + (detail_reconstruct * 0.16)))

    return out

def _apply_edges(img, settings: SettingsState):
    Image, _, ImageFilter, _ = _require_pillow()
    s = settings.edges

    antialias = max(0.0, float(getattr(s, "antialias", 0.0) or 0.0))
    refine = max(0.0, float(getattr(s, "edge_refine", 0.0) or 0.0))
    feather = max(0.0, float(getattr(s, "feather_px", 0.0) or 0.0))
    grow_shrink = float(getattr(s, "grow_shrink_px", 0.0) or 0.0)

    if max(antialias, refine, feather, abs(grow_shrink)) <= 1e-6:
        return img

    out = img
    if antialias > 1e-6:
        blur_radius = min(2.0, antialias * 2.0)
        blurred = out.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        try:
            out = out.blend(blurred, alpha=min(0.6, antialias * 0.5))
        except Exception:
            out = blurred

    if refine > 1e-6:
        out = out.filter(
            ImageFilter.UnsharpMask(
                radius=1.0,
                percent=int(round(40 + refine * 160)),
                threshold=0,
            )
        )

    if out.mode == "RGBA":
        r, g, b, a = out.split()

        if feather > 1e-6:
            a = a.filter(ImageFilter.GaussianBlur(radius=min(4.0, feather)))

        steps = int(min(4, abs(grow_shrink)))
        if steps > 0:
            for _ in range(steps):
                if grow_shrink > 0:
                    a = a.filter(ImageFilter.MaxFilter(size=3))
                else:
                    a = a.filter(ImageFilter.MinFilter(size=3))

        out = Image.merge("RGBA", (r, g, b, a))

    return out


def _background_strength(pixel: tuple[int, int, int], mode: BackgroundRemovalMode) -> int:
    """Return 0..255 confidence that a pixel belongs to a removable background."""

    r, g, b = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
    min_c = min(r, g, b)
    max_c = max(r, g, b)
    spread = max_c - min_c

    if mode is BackgroundRemovalMode.WHITE:
        if min_c < 205 or spread > 46:
            return 0
        if min_c >= 248 and spread <= 18:
            return 255
        brightness = max(0.0, min(1.0, (min_c - 205) / 43.0))
        neutrality = max(0.0, min(1.0, 1.0 - (spread / 46.0)))
        return int(round(255.0 * brightness * neutrality))

    if mode is BackgroundRemovalMode.BLACK:
        if max_c > 72 or spread > 46:
            return 0
        if max_c <= 14 and spread <= 18:
            return 255
        darkness = max(0.0, min(1.0, (72 - max_c) / 58.0))
        neutrality = max(0.0, min(1.0, 1.0 - (spread / 46.0)))
        return int(round(255.0 * darkness * neutrality))

    return 0


def build_background_cutout_keep_mask(rgb_img, mode: BackgroundRemovalMode):
    """Build a keep-mask by flood-filling removable white/black pixels from the image edges."""

    _require_pillow()
    if rgb_img.mode != "RGB":
        rgb_img = rgb_img.convert("RGB")

    Image, _, _, _ = _require_pillow()
    width, height = rgb_img.size
    if width <= 0 or height <= 0:
        return Image.new("L", (max(1, width), max(1, height)), 255)

    keep_mask = Image.new("L", (width, height), 255)
    keep_pixels = keep_mask.load()
    rgb_pixels = rgb_img.load()
    visited = bytearray(width * height)
    pending: deque[tuple[int, int]] = deque()

    def _try_seed(x: int, y: int) -> None:
        idx = y * width + x
        if visited[idx]:
            return
        strength = _background_strength(rgb_pixels[x, y], mode)
        if strength <= 0:
            return
        visited[idx] = 1
        keep_pixels[x, y] = 255 - strength
        pending.append((x, y))

    for x in range(width):
        _try_seed(x, 0)
        if height > 1:
            _try_seed(x, height - 1)
    for y in range(1, max(1, height - 1)):
        _try_seed(0, y)
        if width > 1:
            _try_seed(width - 1, y)

    neighbors = (
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),            (1, 0),
        (-1, 1),  (0, 1),   (1, 1),
    )
    while pending:
        x, y = pending.popleft()
        for dx, dy in neighbors:
            nx = x + dx
            ny = y + dy
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            idx = ny * width + nx
            if visited[idx]:
                continue
            strength = _background_strength(rgb_pixels[nx, ny], mode)
            if strength <= 0:
                continue
            visited[idx] = 1
            keep_pixels[nx, ny] = min(keep_pixels[nx, ny], 255 - strength)
            pending.append((nx, ny))

    return keep_mask


def _apply_alpha_rules(img, settings: SettingsState):
    Image, _, ImageFilter, _ = _require_pillow()
    from PIL import ImageChops  # type: ignore
    s = settings.alpha
    background_mode = normalize_background_removal_mode(
        getattr(s, "background_removal_mode", None),
        remove_white_bg=bool(getattr(s, "remove_white_bg", False)),
    )

    if img.mode != "RGBA":
        if background_mode is BackgroundRemovalMode.OFF:
            return img
        img = img.convert("RGBA")

    r, g, b, a = img.split()

    if background_mode is not BackgroundRemovalMode.OFF:
        keep_mask = build_background_cutout_keep_mask(Image.merge("RGB", (r, g, b)), background_mode)
        a = ImageChops.multiply(a, keep_mask)

    smooth = max(0.0, float(getattr(s, "alpha_smooth", 0.0) or 0.0))
    if smooth > 1e-6:
        a = a.filter(ImageFilter.GaussianBlur(radius=min(2.5, smooth * 2.5)))

    matte = max(0.0, float(getattr(s, "matte_fix", 0.0) or 0.0))
    if matte > 1e-6:
        a = a.filter(ImageFilter.MedianFilter(size=3))
        if matte > 0.2:
            a = a.filter(ImageFilter.GaussianBlur(radius=min(1.5, matte * 1.5)))

    thr = int(getattr(s, "alpha_threshold", 0) or 0)
    if thr > 0:
        a = a.point(lambda v: 255 if v >= thr else 0)

    return Image.merge("RGBA", (r, g, b, a))


def apply_light_processing(
    *,
    source_path: str | Path,
    output_path: str | Path,
    settings: SettingsState,
) -> LightProcessResult:
    """Apply the minimal light pipeline and write a derived image file.

    The derived output is written as PNG for stable previews, regardless of the original format.
    """
    Image, _, _, _ = _require_pillow()

    src = Path(source_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        raise LightProcessError(f"Source image does not exist: {src}")

    try:
        with Image.open(src) as im:
            frame_count = int(getattr(im, "n_frames", 1) or 1)
            is_animated = bool(getattr(im, "is_animated", False)) and frame_count > 1

            if is_animated and out.suffix.lower() == ".gif":
                size = _save_light_processed_gif_preview(im, out, settings)
                return LightProcessResult(output_path=out, size=size)

            im.load()
            im = render_light_image(im, settings)

            # Write PNG derived output for preview stability.
            im.save(out, format="PNG", optimize=True)
            return LightProcessResult(output_path=out, size=(int(im.size[0]), int(im.size[1])))
    except LightStepUnavailable:
        raise
    except Exception as exc:
        raise LightProcessError(f"Light processing failed for {src.name}: {exc}") from exc


def _save_light_processed_gif_preview(im, out: Path, settings: SettingsState) -> tuple[int, int]:
    from PIL import Image, ImageSequence  # type: ignore

    frames: list = []
    durations: list[int] = []
    loop = int(getattr(im, "info", {}).get("loop", 0) or 0)
    disposal = getattr(im, "info", {}).get("disposal", 2)
    source_frame_size = (int(im.size[0]), int(im.size[1]))
    logical_size: tuple[int, int] | None = None
    resample = _resample_from_method(
        settings.pixel.scale_method,
        pixel_snap=bool(getattr(settings.pixel, "pixel_snap", False)),
    )

    for frame in ImageSequence.Iterator(im):
        rgba = frame.convert("RGBA")
        processed = render_light_image(rgba, settings)
        if logical_size is None:
            logical_size = (int(processed.size[0]), int(processed.size[1]))
        # Keep animated preview renders at the source frame size so preset clicks do not
        # balloon the on-screen preview while export still honors the logical output size.
        if processed.size != source_frame_size:
            processed = processed.resize(source_frame_size, resample=resample)
        durations.append(_gif_delay_or_default(getattr(frame, "info", {}).get("duration", 100)))
        frames.append(_quantize_preview_gif_frame(processed))

    if not frames or logical_size is None:
        raise LightProcessError("Animated GIF preview had no frames.")

    first = frames[0]
    rest = frames[1:]
    save_kwargs: dict[str, object] = {
        "save_all": True,
        "append_images": rest,
        "duration": durations if len(durations) > 1 else durations[0],
        "loop": loop,
        "optimize": False,
        "disposal": int(disposal) if isinstance(disposal, int) else 2,
    }
    first.save(out, format="GIF", **save_kwargs)
    return logical_size


def _gif_delay_or_default(raw_delay: object) -> int:
    try:
        value = int(raw_delay)
    except Exception:
        value = 0
    return max(20, value if value > 0 else 100)


def _quantize_preview_gif_frame(rgba):
    from PIL import Image  # type: ignore

    frame = rgba.convert("RGBA")
    alpha = frame.getchannel("A")
    transparent_mask = alpha.point(
        lambda value: 255 if int(value) <= 24 else 0,
        mode="L",
    )

    if transparent_mask.getbbox() is None:
        return frame.quantize(colors=256, method=getattr(Image, "FASTOCTREE", 2))

    rgb = frame.convert("RGB")
    quantized = rgb.quantize(colors=255, method=getattr(Image, "FASTOCTREE", 2))

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











