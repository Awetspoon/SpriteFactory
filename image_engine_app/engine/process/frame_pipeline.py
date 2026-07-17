"""Pure in-memory processing for one static image or animation frame."""

from __future__ import annotations

from image_engine_app.engine.models import ScaleMethod, SettingsState
from image_engine_app.engine.process.pillow_runtime import require_pillow
from image_engine_app.engine.process.transparency import apply_transparency


def render_frame(image, settings: SettingsState, *, target_size: tuple[int, int] | None = None):
    """Apply all visible edit settings to one in-memory Pillow image."""

    require_pillow()
    rendered = image.copy()
    if rendered.mode not in {"RGB", "RGBA"}:
        rendered = rendered.convert("RGBA" if "A" in rendered.getbands() else "RGB")

    pixel = settings.pixel
    desired_size = calculate_output_size(
        rendered.size,
        resize_percent=float(pixel.resize_percent or 100.0),
        width=pixel.width,
        height=pixel.height,
    )
    resample = resample_for_settings(settings)
    if desired_size != rendered.size:
        rendered = rendered.resize(desired_size, resample=resample)

    if target_size is not None:
        normalized_target = (max(1, int(target_size[0])), max(1, int(target_size[1])))
        if rendered.size != normalized_target:
            rendered = rendered.resize(normalized_target, resample=resample)

    rendered = apply_ai_preview(rendered, settings)
    rendered = apply_cleanup(rendered, settings)
    rendered = apply_detail(rendered, settings)
    rendered = apply_edges(rendered, settings)
    rendered = apply_color_adjustments(rendered, settings)
    return apply_transparency(rendered, settings)


def resample_for_settings(settings: SettingsState) -> int:
    """Return the Pillow resampling filter selected by pixel settings."""

    pixel = settings.pixel
    return _resample_from_method(pixel.scale_method, pixel_snap=bool(pixel.pixel_snap))


def _resample_from_method(method: ScaleMethod, *, pixel_snap: bool) -> int:
    Image, _, _, _ = require_pillow()
    if pixel_snap:
        return int(getattr(Image.Resampling, "NEAREST", Image.NEAREST))
    mapping = {
        ScaleMethod.NEAREST: getattr(Image.Resampling, "NEAREST", Image.NEAREST),
        ScaleMethod.BILINEAR: getattr(Image.Resampling, "BILINEAR", Image.BILINEAR),
        ScaleMethod.BICUBIC: getattr(Image.Resampling, "BICUBIC", Image.BICUBIC),
        ScaleMethod.LANCZOS: getattr(Image.Resampling, "LANCZOS", Image.LANCZOS),
    }
    return int(mapping.get(method, getattr(Image.Resampling, "LANCZOS", Image.LANCZOS)))


def calculate_output_size(
    original: tuple[int, int],
    *,
    resize_percent: float,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    original_width, original_height = original
    if original_width <= 0 or original_height <= 0:
        return max(1, original_width), max(1, original_height)

    if width and height:
        return max(1, int(width)), max(1, int(height))
    if width and not height:
        ratio = original_height / original_width
        return max(1, int(width)), max(1, int(round(width * ratio)))
    if height and not width:
        ratio = original_width / original_height
        return max(1, int(round(height * ratio))), max(1, int(height))
    if resize_percent and abs(resize_percent - 100.0) > 0.001:
        factor = max(0.01, float(resize_percent) / 100.0)
        return (
            max(1, int(round(original_width * factor))),
            max(1, int(round(original_height * factor))),
        )
    return original_width, original_height


def calculate_rendered_size(
    original: tuple[int, int],
    settings: SettingsState,
) -> tuple[int, int]:
    """Return the exact size produced by resize controls and AI preview upscale."""

    pixel = settings.pixel
    width, height = calculate_output_size(
        original,
        resize_percent=float(pixel.resize_percent or 100.0),
        width=pixel.width,
        height=pixel.height,
    )
    preview_factor = min(4.0, max(1.0, float(getattr(settings.ai, "upscale_factor", 1.0) or 1.0)))
    if preview_factor <= 1.0:
        return width, height
    return (
        max(1, int(round(width * preview_factor))),
        max(1, int(round(height * preview_factor))),
    )


def apply_color_adjustments(image, settings: SettingsState):
    """Apply brightness, contrast, saturation, gamma, temperature, and curves."""

    Image, ImageEnhance, _, _ = require_pillow()
    color = settings.color
    rendered = image

    if abs(float(color.brightness)) > 1e-6:
        rendered = ImageEnhance.Brightness(rendered).enhance(1.0 + float(color.brightness))
    if abs(float(color.contrast)) > 1e-6:
        rendered = ImageEnhance.Contrast(rendered).enhance(1.0 + float(color.contrast))
    if abs(float(color.saturation)) > 1e-6:
        rendered = ImageEnhance.Color(rendered).enhance(1.0 + float(color.saturation))

    gamma = float(color.gamma) if color.gamma else 1.0
    if abs(gamma - 1.0) > 1e-6:
        inverse = 1.0 / max(1e-6, gamma)
        lookup = [int(round(((value / 255.0) ** inverse) * 255.0)) for value in range(256)]
        if rendered.mode == "RGBA":
            red, green, blue, alpha = rendered.split()
            rendered = Image.merge(
                "RGBA",
                (red.point(lookup), green.point(lookup), blue.point(lookup), alpha),
            )
        elif rendered.mode == "RGB":
            rendered = rendered.point(lookup * 3)
        else:
            rendered = rendered.point(lookup)

    temperature = max(-1.0, min(1.0, float(getattr(color, "temperature", 0.0) or 0.0)))
    if abs(temperature) > 1e-6:
        rendered = _apply_temperature_adjustment(rendered, temperature=temperature)

    curves = getattr(color, "curves", None)
    if curves:
        rendered = _apply_curves_adjustment(rendered, curves=curves)
    return rendered


def _apply_temperature_adjustment(image, *, temperature: float):
    Image, _, _, _ = require_pillow()
    rendered = image
    if rendered.mode not in {"RGB", "RGBA", "L"}:
        rendered = rendered.convert("RGBA" if "A" in rendered.getbands() else "RGB")
    if rendered.mode == "L":
        return _apply_temperature_adjustment(
            rendered.convert("RGB"),
            temperature=temperature,
        ).convert("L")

    shift = max(-1.0, min(1.0, float(temperature)))
    red_lookup = [_clamp_channel(value * (1.0 + (0.18 * shift))) for value in range(256)]
    green_lookup = [_clamp_channel(value * (1.0 + (0.05 * shift))) for value in range(256)]
    blue_lookup = [_clamp_channel(value * (1.0 - (0.18 * shift))) for value in range(256)]

    if rendered.mode == "RGBA":
        red, green, blue, alpha = rendered.split()
        return Image.merge(
            "RGBA",
            (red.point(red_lookup), green.point(green_lookup), blue.point(blue_lookup), alpha),
        )
    red, green, blue = rendered.split()
    return Image.merge("RGB", (red.point(red_lookup), green.point(green_lookup), blue.point(blue_lookup)))


def _apply_curves_adjustment(image, *, curves):
    Image, _, _, _ = require_pillow()
    if not isinstance(curves, dict):
        return image

    rgb_curve = _build_curve_lookup(curves.get("rgb"))
    red_curve = _build_curve_lookup(curves.get("r"))
    green_curve = _build_curve_lookup(curves.get("g"))
    blue_curve = _build_curve_lookup(curves.get("b"))
    if not any(lookup is not None for lookup in (rgb_curve, red_curve, green_curve, blue_curve)):
        return image

    rendered = image
    if rendered.mode not in {"RGB", "RGBA"}:
        rendered = rendered.convert("RGBA" if "A" in rendered.getbands() else "RGB")
    if rendered.mode == "RGBA":
        red, green, blue, alpha = rendered.split()
    else:
        red, green, blue = rendered.split()
        alpha = None

    if rgb_curve is not None:
        red = red.point(rgb_curve)
        green = green.point(rgb_curve)
        blue = blue.point(rgb_curve)
    if red_curve is not None:
        red = red.point(red_curve)
    if green_curve is not None:
        green = green.point(green_curve)
    if blue_curve is not None:
        blue = blue.point(blue_curve)
    if alpha is not None:
        return Image.merge("RGBA", (red, green, blue, alpha))
    return Image.merge("RGB", (red, green, blue))


def _build_curve_lookup(points) -> list[int] | None:
    if not isinstance(points, (list, tuple)):
        return None

    parsed: list[tuple[int, int]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        try:
            parsed.append((_clamp_channel(point[0]), _clamp_channel(point[1])))
        except Exception:
            continue
    if not parsed:
        return None

    parsed.sort(key=lambda item: item[0])
    if parsed[0][0] != 0:
        parsed.insert(0, (0, parsed[0][1]))
    if parsed[-1][0] != 255:
        parsed.append((255, parsed[-1][1]))

    lookup: list[int | None] = [None] * 256
    for index in range(len(parsed) - 1):
        first_x, first_y = parsed[index]
        second_x, second_y = parsed[index + 1]
        if second_x <= first_x:
            continue
        span = second_x - first_x
        for value in range(first_x, second_x + 1):
            ratio = (value - first_x) / span
            lookup[value] = _clamp_channel(first_y + ((second_y - first_y) * ratio))

    for value in range(256):
        if lookup[value] is None:
            lookup[value] = 0 if value == 0 else lookup[value - 1]
    return [int(value or 0) for value in lookup]


def _clamp_channel(value: float | int) -> int:
    return max(0, min(255, int(round(float(value)))))


def apply_cleanup(image, settings: SettingsState):
    """Apply the four independent cleanup controls."""

    Image, _, ImageFilter, _ = require_pillow()
    cleanup = settings.cleanup
    denoise = max(0.0, float(cleanup.denoise))
    artifact = max(0.0, float(cleanup.artifact_removal))
    banding = max(0.0, float(cleanup.banding_removal))
    halo = max(0.0, float(cleanup.halo_cleanup))
    if max(denoise, artifact, banding, halo) <= 1e-6:
        return image

    rendered = image
    if denoise > 1e-6:
        layer = rendered.filter(ImageFilter.MedianFilter(size=3 if denoise < 0.8 else 5))
        rendered = Image.blend(rendered, layer, min(0.7, 0.12 + (denoise * 0.28)))
    if artifact > 1e-6:
        layer = rendered.filter(ImageFilter.BoxBlur(radius=min(2.0, 0.35 + (artifact * 0.75))))
        rendered = Image.blend(rendered, layer, min(0.52, 0.08 + (artifact * 0.22)))
    if banding > 1e-6:
        layer = rendered.filter(ImageFilter.GaussianBlur(radius=min(3.0, 0.7 + (banding * 1.1))))
        rendered = Image.blend(rendered, layer, min(0.38, 0.05 + (banding * 0.16)))
    if halo > 1e-6:
        layer = rendered.filter(ImageFilter.SMOOTH_MORE)
        rendered = Image.blend(rendered, layer, min(0.42, 0.06 + (halo * 0.18)))
    return rendered


def apply_detail(image, settings: SettingsState):
    """Apply sharpen, clarity, and texture controls."""

    Image, _, ImageFilter, _ = require_pillow()
    detail = settings.detail
    amount = float(detail.sharpen_amount)
    clarity = float(detail.clarity)
    texture = float(detail.texture)
    if max(abs(amount), abs(clarity), abs(texture)) <= 1e-6:
        return image

    rendered = image
    if amount > 1e-6:
        radius = max(0.1, min(3.0, float(detail.sharpen_radius) if detail.sharpen_radius else 1.0))
        threshold = int(max(0.0, float(detail.sharpen_threshold or 0.0)) * 10)
        percent = int(round(min(240.0, amount * 120.0)))
        if percent > 0:
            rendered = rendered.filter(
                ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold)
            )
    elif amount < -1e-6:
        soften = min(1.0, abs(amount) / 2.0)
        layer = rendered.filter(ImageFilter.GaussianBlur(radius=0.35 + (soften * 1.2)))
        rendered = Image.blend(rendered, layer, min(0.45, 0.08 + (soften * 0.25)))

    clarity_level = min(1.0, abs(clarity) / 2.0)
    texture_level = min(1.0, abs(texture) / 2.0)
    if bool(getattr(settings.pixel, "pixel_snap", False)):
        clarity_level *= 0.75
        texture_level *= 0.7

    if clarity > 1e-6 and clarity_level > 1e-6:
        layer = rendered.filter(
            ImageFilter.UnsharpMask(
                radius=1.4 + (clarity_level * 0.8),
                percent=int(round(18 + (clarity_level * 42))),
                threshold=3,
            )
        )
        rendered = Image.blend(rendered, layer, min(0.28, 0.05 + (clarity_level * 0.18)))
    elif clarity < -1e-6 and clarity_level > 1e-6:
        layer = rendered.filter(ImageFilter.GaussianBlur(radius=0.55 + (clarity_level * 0.95)))
        rendered = Image.blend(rendered, layer, min(0.30, 0.06 + (clarity_level * 0.20)))

    if texture > 1e-6 and texture_level > 1e-6:
        layer = rendered.filter(
            ImageFilter.UnsharpMask(
                radius=0.45 + (texture_level * 0.55),
                percent=int(round(14 + (texture_level * 34))),
                threshold=2,
            )
        )
        rendered = Image.blend(rendered, layer, min(0.24, 0.04 + (texture_level * 0.16)))
    elif texture < -1e-6 and texture_level > 1e-6:
        layer = rendered.filter(ImageFilter.GaussianBlur(radius=0.35 + (texture_level * 0.75)))
        rendered = Image.blend(rendered, layer, min(0.26, 0.05 + (texture_level * 0.18)))
    return rendered


def apply_ai_preview(image, settings: SettingsState):
    """Apply the deterministic preview approximation for queued AI controls."""

    Image, _, ImageFilter, _ = require_pillow()
    ai = settings.ai
    upscale_factor = max(1.0, float(getattr(ai, "upscale_factor", 1.0) or 1.0))
    deblur_strength = max(0.0, float(getattr(ai, "deblur_strength", 0.0) or 0.0))
    detail_reconstruct = max(0.0, float(getattr(ai, "detail_reconstruct", 0.0) or 0.0))
    if max(upscale_factor - 1.0, deblur_strength, detail_reconstruct) <= 1e-6:
        return image

    rendered = image
    preview_factor = min(4.0, upscale_factor)
    if preview_factor > 1.0:
        target = (
            max(1, int(round(rendered.width * preview_factor))),
            max(1, int(round(rendered.height * preview_factor))),
        )
        rendered = rendered.resize(target, resample=resample_for_settings(settings))
    if deblur_strength > 1e-6:
        rendered = rendered.filter(
            ImageFilter.UnsharpMask(
                radius=min(3.0, 0.8 + (deblur_strength * 1.2)),
                percent=int(round(min(220.0, 25.0 + (deblur_strength * 110.0)))),
                threshold=1,
            )
        )
    if detail_reconstruct > 1e-6:
        layer = rendered.filter(
            ImageFilter.UnsharpMask(
                radius=min(2.0, 0.5 + (detail_reconstruct * 0.9)),
                percent=int(round(min(200.0, 20.0 + (detail_reconstruct * 90.0)))),
                threshold=0,
            )
        )
        rendered = Image.blend(
            rendered,
            layer,
            min(0.35, 0.08 + (detail_reconstruct * 0.16)),
        )
    return rendered


def apply_edges(image, settings: SettingsState):
    """Apply antialias, edge refinement, feather, and grow/shrink controls."""

    Image, _, ImageFilter, _ = require_pillow()
    edges = settings.edges
    antialias = max(0.0, float(getattr(edges, "antialias", 0.0) or 0.0))
    refine = max(0.0, float(getattr(edges, "edge_refine", 0.0) or 0.0))
    feather = max(0.0, float(getattr(edges, "feather_px", 0.0) or 0.0))
    grow_shrink = float(getattr(edges, "grow_shrink_px", 0.0) or 0.0)
    if max(antialias, refine, feather, abs(grow_shrink)) <= 1e-6:
        return image

    rendered = image
    if antialias > 1e-6:
        blurred = rendered.filter(ImageFilter.GaussianBlur(radius=min(2.0, antialias * 2.0)))
        rendered = Image.blend(rendered, blurred, min(0.6, antialias * 0.5))
    if refine > 1e-6:
        rendered = rendered.filter(
            ImageFilter.UnsharpMask(
                radius=1.0,
                percent=int(round(40 + (refine * 160))),
                threshold=0,
            )
        )
    if rendered.mode == "RGBA":
        red, green, blue, alpha = rendered.split()
        if feather > 1e-6:
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=min(4.0, feather)))
        for _ in range(int(min(4, abs(grow_shrink)))):
            alpha = alpha.filter(
                ImageFilter.MaxFilter(size=3) if grow_shrink > 0 else ImageFilter.MinFilter(size=3)
            )
        rendered = Image.merge("RGBA", (red, green, blue, alpha))
    return rendered
