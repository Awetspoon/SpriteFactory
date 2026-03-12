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

from dataclasses import dataclass
from pathlib import Path

from engine.models import ScaleMethod, SettingsState


class LightStepUnavailable(RuntimeError):
    """Raised when Pillow is not available for light processing."""


class LightProcessError(RuntimeError):
    """Raised when light processing fails to produce an output."""


@dataclass(frozen=True)
class LightProcessResult:
    """Outcome of a light processing run."""

    output_path: Path
    size: tuple[int, int]


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

    # Temperature/curves remain placeholders (future steps).
    return img


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
    _, _, ImageFilter, _ = _require_pillow()
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


def _white_background_alpha_mask(rgb_img):
    """Build an alpha-keep mask from RGB values (white becomes transparent)."""
    _require_pillow()
    from PIL import ImageChops  # type: ignore
    if rgb_img.mode != "RGB":
        rgb_img = rgb_img.convert("RGB")

    r, g, b = rgb_img.split()
    min_rgb = ImageChops.darker(ImageChops.darker(r, g), b)

    white_cutoff = 250
    white_floor = 210
    span = max(1, white_cutoff - white_floor)

    return min_rgb.point(
        lambda v: (
            0
            if v >= white_cutoff
            else (255 if v <= white_floor else int(round((white_cutoff - v) * 255 / span)))
        )
    )


def _apply_alpha_rules(img, settings: SettingsState):
    Image, _, ImageFilter, _ = _require_pillow()
    from PIL import ImageChops  # type: ignore
    s = settings.alpha
    remove_white_bg = bool(getattr(s, "remove_white_bg", False))

    if img.mode != "RGBA":
        if not remove_white_bg:
            return img
        img = img.convert("RGBA")

    r, g, b, a = img.split()

    if remove_white_bg:
        keep_mask = _white_background_alpha_mask(Image.merge("RGB", (r, g, b)))
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
            im.load()
            # Normalize to RGBA for safe processing, preserve alpha if present.
            if im.mode not in {"RGB", "RGBA"}:
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")

            # Resize
            p = settings.pixel
            target_size = _compute_target_size(
                im.size,
                resize_percent=float(p.resize_percent or 100.0),
                width=p.width,
                height=p.height,
            )
            resample = _resample_from_method(p.scale_method, pixel_snap=bool(p.pixel_snap))
            if target_size != im.size:
                im = im.resize(target_size, resample=resample)

            # AI preview -> Cleanup -> Detail -> Edges -> Color -> Alpha
            im = _apply_ai_preview(im, settings)
            im = _apply_cleanup(im, settings)
            im = _apply_detail(im, settings)
            im = _apply_edges(im, settings)
            im = _apply_color_adjust(im, settings)
            im = _apply_alpha_rules(im, settings)

            # Write PNG derived output for preview stability.
            im.save(out, format="PNG", optimize=True)
            return LightProcessResult(output_path=out, size=(int(im.size[0]), int(im.size[1])))
    except LightStepUnavailable:
        raise
    except Exception as exc:
        raise LightProcessError(f"Light processing failed for {src.name}: {exc}") from exc










