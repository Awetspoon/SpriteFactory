"""Image export pipeline with real encoding and metadata fallback mode."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Callable

from image_engine_app.engine.models import ExportFormat, ExportSettings, SettingsState
from image_engine_app.engine.process.light_steps import render_light_image


class ExporterError(Exception):
    """Raised when an exporter cannot handle a request."""


class ExporterFallbackError(Exception):
    """Raised when metadata fallback export cannot handle a request."""


@dataclass
class ExportRequest:
    """Export request for writing an image to disk.

    source_path:
        Optional local path to the image to export. If absent, the exporter falls
        back to writing a metadata file so UI flows can still complete.
    """

    output_path: str | Path
    width: int
    height: int
    export_settings: ExportSettings
    asset_id: str | None = None
    frame_count: int = 1
    has_alpha: bool = False
    source_path: str | Path | None = None
    light_settings: SettingsState | None = None


@dataclass
class ExportResult:
    """Export result."""

    success: bool
    output_path: Path
    format: ExportFormat
    bytes_written: int
    message: str
    is_stub: bool = False
    fallback_kind: str | None = None


def _resolve_export_format(request: ExportRequest) -> ExportFormat:
    selected = request.export_settings.format
    if selected is not ExportFormat.AUTO:
        return selected
    if int(request.frame_count or 1) > 1:
        return ExportFormat.GIF
    return ExportFormat.PNG if request.has_alpha else ExportFormat.WEBP


def export_image(request: ExportRequest) -> ExportResult:
    """Export an image.

    - If request.source_path is available and Pillow can be imported, write a real file.
    - If source pixels are unavailable but Pillow is installed, write a generated placeholder image.
    - Otherwise, write a metadata fallback file to keep UX/tests stable.
    """
    fmt = _resolve_export_format(request)
    out_path = Path(request.output_path)

    src = Path(request.source_path) if request.source_path else None

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return export_image_metadata_fallback(
            request,
            message_override="Pillow not installed; wrote fallback metadata export instead.",
        )

    if src is None or not src.exists() or (not src.is_file()):
        return export_generated_placeholder(
            request,
            fmt=fmt,
            message_override="Source image unavailable; generated placeholder export instead.",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    target_w = max(1, int(request.width))
    target_h = max(1, int(request.height))

    try:
        with Image.open(src) as im:
            im.load()

            is_animated = bool(getattr(im, "is_animated", False)) and int(getattr(im, "n_frames", 1) or 1) > 1
            if fmt is ExportFormat.GIF and is_animated:
                kwargs = _build_save_kwargs(fmt, request.export_settings)
                _save_gif_animated(
                    im,
                    out_path,
                    request.export_settings,
                    kwargs,
                    target_size=(None if request.light_settings is not None else (target_w, target_h)),
                    light_settings=request.light_settings,
                )
                bytes_written = int(out_path.stat().st_size) if out_path.exists() else 0
                return ExportResult(
                    success=True,
                    output_path=out_path,
                    format=fmt,
                    bytes_written=bytes_written,
                    message=(
                        "Exported animated GIF (frames preserved with edits)"
                        if request.light_settings is not None
                        else "Exported animated GIF (frames preserved)"
                    ),
                    is_stub=False,
                    fallback_kind=None,
                )

            im = _prepare_static_export_image(
                im,
                request=request,
                fmt=fmt,
                target_size=(target_w, target_h),
            )

            save_kwargs = _build_save_kwargs(fmt, request.export_settings)

            dpi = getattr(request.export_settings, "dpi", None)
            if dpi is None:
                dpi = 72
            if fmt in (ExportFormat.PNG, ExportFormat.JPG, ExportFormat.TIFF):
                save_kwargs.setdefault("dpi", (int(dpi), int(dpi)))

            _save_image(im, out_path, fmt, save_kwargs)

        bytes_written = out_path.stat().st_size if out_path.exists() else 0
        return ExportResult(
            success=True,
            output_path=out_path,
            format=fmt,
            bytes_written=int(bytes_written),
            message=f"Exported {fmt.value.upper()}",
            is_stub=False,
            fallback_kind=None,
        )
    except Exception as exc:
        return ExportResult(
            success=False,
            output_path=out_path,
            format=fmt,
            bytes_written=0,
            message=f"Export failed: {exc}",
            is_stub=False,
            fallback_kind=None,
        )


# ----------------------------
# Metadata fallback path
# ----------------------------

def export_image_metadata_fallback(request: ExportRequest, message_override: str | None = None) -> ExportResult:
    """Write a small JSON metadata file as a fallback export output."""
    fmt = _resolve_export_format(request)

    dispatch: dict[ExportFormat, Callable[[ExportRequest], ExportResult]] = {
        ExportFormat.PNG: export_png_metadata_fallback,
        ExportFormat.JPG: export_jpeg_metadata_fallback,
        ExportFormat.WEBP: export_webp_metadata_fallback,
        ExportFormat.GIF: export_gif_metadata_fallback,
        ExportFormat.ICO: export_ico_metadata_fallback,
        ExportFormat.TIFF: export_tiff_metadata_fallback,
        ExportFormat.BMP: export_bmp_metadata_fallback,
    }
    try:
        handler = dispatch[fmt]
    except KeyError as exc:  # pragma: no cover
        raise ExporterFallbackError(f"No fallback exporter for format {fmt.value}") from exc

    res = handler(request)
    if message_override:
        return ExportResult(
            success=res.success,
            output_path=res.output_path,
            format=res.format,
            bytes_written=res.bytes_written,
            message=message_override,
            is_stub=True,
            fallback_kind="metadata",
        )
    return res


def export_generated_placeholder(
    request: ExportRequest,
    *,
    fmt: ExportFormat | None = None,
    message_override: str | None = None,
) -> ExportResult:
    """Write a real placeholder image file when source pixels are unavailable."""

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return export_image_metadata_fallback(
            request,
            message_override=message_override or "Source image unavailable; wrote fallback metadata export instead.",
        )

    resolved_fmt = fmt or _resolve_export_format(request)
    out_path = Path(request.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    size = (max(1, int(request.width)), max(1, int(request.height)))

    try:
        if resolved_fmt is ExportFormat.GIF and int(request.frame_count or 1) > 1:
            frames = [
                _build_placeholder_image(request, size=size, frame_variant=0),
                _build_placeholder_image(request, size=size, frame_variant=1),
            ]
            save_kwargs = _build_save_kwargs(resolved_fmt, request.export_settings)
            adaptive_palette = getattr(Image, "ADAPTIVE", 1)
            first = frames[0].convert("P", palette=adaptive_palette, colors=256)
            rest = [frame.convert("P", palette=adaptive_palette, colors=256) for frame in frames[1:]]
            first.save(
                out_path,
                format="GIF",
                save_all=True,
                append_images=rest,
                duration=[120 for _ in frames],
                loop=0,
                optimize=bool(save_kwargs.get("optimize", True)),
            )
        else:
            image = _build_placeholder_image(request, size=size, frame_variant=0)
            image = _normalize_image_for_format(image, resolved_fmt, prefer_alpha=request.has_alpha)
            save_kwargs = _build_save_kwargs(resolved_fmt, request.export_settings)
            if resolved_fmt in (ExportFormat.PNG, ExportFormat.JPG, ExportFormat.TIFF):
                dpi = getattr(request.export_settings, "dpi", None)
                if dpi is None:
                    dpi = 72
                save_kwargs.setdefault("dpi", (int(dpi), int(dpi)))
            _save_image(image, out_path, resolved_fmt, save_kwargs)
    except Exception:
        return export_image_metadata_fallback(
            request,
            message_override=message_override or "Placeholder export failed; wrote fallback metadata export instead.",
        )

    bytes_written = int(out_path.stat().st_size) if out_path.exists() else 0
    return ExportResult(
        success=True,
        output_path=out_path,
        format=resolved_fmt,
        bytes_written=bytes_written,
        message=message_override or f"Generated placeholder {resolved_fmt.value.upper()} export",
        is_stub=True,
        fallback_kind="placeholder",
    )


def export_png_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.PNG)


def export_jpeg_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.JPG)


def export_webp_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.WEBP)


def export_gif_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.GIF)


def export_ico_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.ICO)


def export_tiff_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.TIFF)


def export_bmp_metadata_fallback(request: ExportRequest) -> ExportResult:
    return _write_metadata_fallback_file(request, ExportFormat.BMP)


def _write_metadata_fallback_file(request: ExportRequest, fmt: ExportFormat) -> ExportResult:
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata_fallback_export": True,
        "format": fmt.value,
        "width": int(request.width),
        "height": int(request.height),
        "asset_id": request.asset_id,
        "frame_count": int(request.frame_count),
        "has_alpha": bool(request.has_alpha),
        "quality": int(request.export_settings.quality),
        "compression_level": int(request.export_settings.compression_level),
    }
    raw = json.dumps(payload, indent=2).encode("utf-8")
    output_path.write_bytes(raw)
    return ExportResult(
        success=True,
        output_path=output_path,
        format=fmt,
        bytes_written=len(raw),
        message=f"Metadata fallback export wrote metadata ({fmt.value})",
        is_stub=True,
        fallback_kind="metadata",
    )


# ----------------------------
# Helpers
# ----------------------------

def _build_save_kwargs(fmt: ExportFormat, settings: ExportSettings) -> dict:
    kwargs: dict = {}
    if fmt is ExportFormat.JPG:
        kwargs["quality"] = int(settings.quality)
        kwargs["optimize"] = True
        kwargs["progressive"] = True
    elif fmt is ExportFormat.PNG:
        kwargs["compress_level"] = int(settings.compression_level)
        kwargs["optimize"] = True
    elif fmt is ExportFormat.WEBP:
        kwargs["quality"] = int(settings.quality)
        kwargs["method"] = 6
    elif fmt is ExportFormat.GIF:
        kwargs["optimize"] = True
    elif fmt is ExportFormat.TIFF:
        kwargs["compression"] = "tiff_deflate"
    elif fmt is ExportFormat.ICO:
        kwargs["ico_sizes"] = list(getattr(settings, "ico_sizes", [16, 32, 48, 64, 128, 256]))
    return kwargs


def _map_resample(settings: ExportSettings, fallback):
    # ExportSettings currently doesn't include scale method; use fallback.
    _ = settings
    return fallback


def _build_placeholder_image(
    request: ExportRequest,
    *,
    size: tuple[int, int],
    frame_variant: int,
):
    from PIL import Image, ImageDraw  # type: ignore

    width, height = size
    supports_alpha = request.has_alpha and _format_supports_alpha(_resolve_export_format(request))
    accent = _placeholder_accent(request.asset_id, variant=frame_variant)

    if supports_alpha:
        base_color = (0, 0, 0, 0)
        panel_fill = (accent[0], accent[1], accent[2], 88)
    else:
        base_color = (244, 247, 248, 255)
        panel_fill = (233, 240, 242, 255)

    image = Image.new("RGBA", size, base_color)
    draw = ImageDraw.Draw(image, "RGBA")

    inset = max(2, min(width, height) // 12)
    right = max(inset + 1, width - inset - 1)
    bottom = max(inset + 1, height - inset - 1)
    border_width = max(1, min(width, height) // 28)

    draw.rectangle(
        (inset, inset, right, bottom),
        fill=panel_fill,
        outline=(accent[0], accent[1], accent[2], 220),
        width=border_width,
    )

    inner_margin = max(border_width + 2, inset + (min(width, height) // 10))
    stripe_top = max(inner_margin, min(height - inner_margin, inner_margin + ((frame_variant * height) // 10)))
    stripe_bottom = min(bottom - border_width, stripe_top + max(2, height // 10))
    draw.rectangle(
        (inner_margin, stripe_top, right - inner_margin, stripe_bottom),
        fill=(accent[0], accent[1], accent[2], 135 if supports_alpha else 165),
    )

    draw.line(
        (inner_margin, bottom - inner_margin, right - inner_margin, inner_margin),
        fill=(accent[0], accent[1], accent[2], 200),
        width=border_width,
    )
    draw.line(
        (inner_margin, inner_margin, right - inner_margin, bottom - inner_margin),
        fill=(accent[0], accent[1], accent[2], 120),
        width=max(1, border_width // 2),
    )

    return image


def _prepare_static_export_image(
    im,
    *,
    request: ExportRequest,
    fmt: ExportFormat,
    target_size: tuple[int, int],
):
    """Prepare a still image for export, applying light settings directly when needed."""

    from PIL import Image  # type: ignore

    if request.light_settings is not None:
        # When exporting directly from the raw source, let the live settings drive the final size.
        # This keeps batch exports accurate even if a derived preview file was never written.
        processed = render_light_image(im, request.light_settings, target_size=None)
        return _normalize_image_for_format(processed, fmt, prefer_alpha=request.has_alpha)

    normalized = _normalize_image_for_format(im, fmt, prefer_alpha=request.has_alpha)
    if fmt is ExportFormat.ICO:
        icon_side = max(1, int(max(target_size)))
        target_size = (icon_side, icon_side)
    if normalized.size != target_size:
        normalized = normalized.resize(
            target_size,
            resample=_map_resample(request.export_settings, fallback=Image.Resampling.LANCZOS),
        )
    return normalized


def _placeholder_accent(asset_id: str | None, *, variant: int) -> tuple[int, int, int]:
    seed = f"{asset_id or 'asset'}:{variant}".encode("utf-8")
    digest = hashlib.sha1(seed).digest()
    return (
        70 + (digest[0] % 120),
        100 + (digest[1] % 100),
        120 + (digest[2] % 90),
    )


def _normalize_image_for_format(im, fmt: ExportFormat, *, prefer_alpha: bool):
    from PIL import Image  # type: ignore

    if fmt is ExportFormat.JPG:
        if im.mode != "RGB":
            return im.convert("RGB")
        return im
    if fmt in (ExportFormat.PNG, ExportFormat.WEBP, ExportFormat.TIFF):
        if prefer_alpha and im.mode != "RGBA":
            return im.convert("RGBA")
        if (not prefer_alpha) and im.mode != "RGB":
            return im.convert("RGB")
        return im
    if fmt is ExportFormat.BMP:
        return im.convert("RGB")
    if fmt is ExportFormat.GIF:
        return im.convert("P", palette=getattr(Image, "ADAPTIVE", 1), colors=256)
    if fmt is ExportFormat.ICO:
        icon = im.convert("RGBA")
        side = max(1, int(max(icon.size)))
        if icon.size != (side, side):
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            offset = ((side - icon.size[0]) // 2, (side - icon.size[1]) // 2)
            canvas.paste(icon, offset, mask=icon.getchannel("A"))
            icon = canvas
        return icon
    return im


def _format_supports_alpha(fmt: ExportFormat) -> bool:
    return fmt in {ExportFormat.PNG, ExportFormat.WEBP, ExportFormat.TIFF, ExportFormat.GIF, ExportFormat.ICO}


def _save_gif_animated(
    im,
    out_path: Path,
    settings: ExportSettings,
    kwargs: dict,
    *,
    target_size: tuple[int, int] | None = None,
    light_settings: SettingsState | None = None,
) -> None:
    """Save an animated GIF preserving frames + timing (best-effort)."""
    try:
        from PIL import Image, ImageSequence  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ExporterError(f"Pillow unavailable for animated GIF export: {exc}") from exc

    target: tuple[int, int] | None = None
    if target_size is not None:
        target = (max(1, int(target_size[0])), max(1, int(target_size[1])))

    frames = []
    durations: list[int] = []
    base_duration = int(getattr(im, "info", {}).get("duration", 40) or 40)
    loop = int(getattr(im, "info", {}).get("loop", 0) or 0)
    disposal = getattr(im, "info", {}).get("disposal", None)
    palette_limit = max(2, min(256, int(getattr(settings, "palette_limit", 256) or 256)))

    for frame in ImageSequence.Iterator(im):
        rgba = frame.convert("RGBA")
        if light_settings is not None:
            rgba = render_light_image(rgba, light_settings, target_size=target)
        elif target is not None and rgba.size != target:
            rgba = rgba.resize(target, resample=getattr(Image.Resampling, "NEAREST", Image.NEAREST))
        durations.append(int(getattr(frame, "info", {}).get("duration", base_duration) or base_duration))
        quantized = _quantize_gif_frame(
            rgba,
            palette_limit=palette_limit,
            transparency_threshold=24,
        )
        frames.append(quantized)

    if not frames:
        raise ExporterError("Animated GIF export had no frames.")

    first = frames[0]
    rest = frames[1:]
    save_kwargs: dict = {
        "save_all": True,
        "append_images": rest,
        "duration": durations if len(durations) > 1 else durations[0],
        "loop": loop,
    }
    if disposal is not None:
        save_kwargs["disposal"] = disposal
    if "optimize" in kwargs:
        save_kwargs["optimize"] = bool(kwargs.get("optimize"))
    save_kwargs.setdefault("disposal", 2)

    first.save(out_path, format="GIF", **save_kwargs)


def _quantize_gif_frame(
    rgba,
    *,
    palette_limit: int,
    transparency_threshold: int,
):
    """Quantize an RGBA frame for GIF while preserving binary transparency."""

    from PIL import Image  # type: ignore

    frame = rgba.convert("RGBA")
    alpha = frame.getchannel("A")
    transparent_mask = alpha.point(
        lambda value: 255 if int(value) <= int(transparency_threshold) else 0,
        mode="L",
    )

    if transparent_mask.getbbox() is None:
        return frame.quantize(colors=max(2, min(256, int(palette_limit or 256))), method=getattr(Image, "FASTOCTREE", 2))

    rgb = frame.convert("RGB")
    quantized = rgb.quantize(colors=max(2, min(255, int(palette_limit or 256) - 1)), method=getattr(Image, "FASTOCTREE", 2))

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


def _save_image(im, out_path: Path, fmt: ExportFormat, kwargs: dict) -> None:
    if fmt is ExportFormat.JPG:
        im.save(out_path, format="JPEG", **kwargs)
        return
    if fmt is ExportFormat.PNG:
        im.save(out_path, format="PNG", **kwargs)
        return
    if fmt is ExportFormat.WEBP:
        im.save(out_path, format="WEBP", **kwargs)
        return
    if fmt is ExportFormat.GIF:
        im.save(out_path, format="GIF", **kwargs)
        return
    if fmt is ExportFormat.TIFF:
        im.save(out_path, format="TIFF", **kwargs)
        return
    if fmt is ExportFormat.BMP:
        im.save(out_path, format="BMP", **kwargs)
        return
    if fmt is ExportFormat.ICO:
        ico_sizes_raw = kwargs.pop("ico_sizes", [16, 32, 48, 64, 128, 256])
        max_side = max(1, int(max(im.size)))
        filtered_sizes = sorted({max(1, int(s)) for s in ico_sizes_raw if int(s) <= max_side})
        if not filtered_sizes:
            filtered_sizes = [max_side]
        ico_sizes = [(size, size) for size in filtered_sizes]
        im.save(out_path, format="ICO", sizes=ico_sizes)
        return
    im.save(out_path, **kwargs)

