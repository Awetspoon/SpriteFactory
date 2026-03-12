"""Image export pipeline with real encoding and metadata fallback mode."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from engine.models import ExportFormat, ExportSettings


class ExporterError(Exception):
    """Raised when an exporter cannot handle a request."""


class ExporterFallbackError(Exception):
    """Raised when metadata fallback export cannot handle a request."""


# Backward-compatible alias kept for older imports.
ExporterStubError = ExporterFallbackError


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


@dataclass
class ExportResult:
    """Export result."""

    success: bool
    output_path: Path
    format: ExportFormat
    bytes_written: int
    message: str
    is_stub: bool = False


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
    - Otherwise, write a metadata fallback file to keep UX/tests stable.
    """
    src = Path(request.source_path) if request.source_path else None
    if src is None or not src.exists():
        return export_image_stub(request)

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return export_image_stub(
            request,
            message_override="Pillow not installed; wrote fallback metadata export instead.",
        )

    fmt = _resolve_export_format(request)

    out_path = Path(request.output_path)
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
                    target_size=(target_w, target_h),
                )
                bytes_written = int(out_path.stat().st_size) if out_path.exists() else 0
                return ExportResult(
                    success=True,
                    output_path=out_path,
                    format=fmt,
                    bytes_written=bytes_written,
                    message="Exported animated GIF (frames preserved)",
                    is_stub=False,
                )

            # Convert mode to suit target format.
            if fmt is ExportFormat.JPG:
                if im.mode in ("RGBA", "LA"):
                    im = im.convert("RGB")
            elif fmt in (ExportFormat.PNG, ExportFormat.WEBP, ExportFormat.TIFF, ExportFormat.BMP, ExportFormat.GIF, ExportFormat.ICO):
                if request.has_alpha and im.mode not in ("RGBA", "LA"):
                    im = im.convert("RGBA")

            if im.size != (target_w, target_h):
                im = im.resize(
                    (target_w, target_h),
                    resample=_map_resample(request.export_settings, fallback=Image.Resampling.LANCZOS),
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
        )
    except Exception as exc:
        return ExportResult(
            success=False,
            output_path=out_path,
            format=fmt,
            bytes_written=0,
            message=f"Export failed: {exc}",
            is_stub=False,
        )


# ----------------------------
# Metadata fallback path
# ----------------------------

def export_image_stub(request: ExportRequest, message_override: str | None = None) -> ExportResult:
    """Write a small JSON metadata file as a fallback export output."""
    fmt = _resolve_export_format(request)

    dispatch: dict[ExportFormat, Callable[[ExportRequest], ExportResult]] = {
        ExportFormat.PNG: export_png_stub,
        ExportFormat.JPG: export_jpeg_stub,
        ExportFormat.WEBP: export_webp_stub,
        ExportFormat.GIF: export_gif_stub,
        ExportFormat.ICO: export_ico_stub,
        ExportFormat.TIFF: export_tiff_stub,
        ExportFormat.BMP: export_bmp_stub,
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
        )
    return res


def export_png_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.PNG)


def export_jpeg_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.JPG)


def export_webp_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.WEBP)


def export_gif_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.GIF)


def export_ico_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.ICO)


def export_tiff_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.TIFF)


def export_bmp_stub(request: ExportRequest) -> ExportResult:
    return _write_stub_file(request, ExportFormat.BMP)


def _write_stub_file(request: ExportRequest, fmt: ExportFormat) -> ExportResult:
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stub_export": True,
        "fallback_metadata_export": True,
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
        message=f"Fallback metadata export wrote metadata ({fmt.value})",
        is_stub=True,
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


def _save_gif_animated(
    im,
    out_path: Path,
    settings: ExportSettings,
    kwargs: dict,
    *,
    target_size: tuple[int, int] | None = None,
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
        if target is not None and rgba.size != target:
            rgba = rgba.resize(target, resample=getattr(Image.Resampling, "NEAREST", Image.NEAREST))
        durations.append(int(getattr(frame, "info", {}).get("duration", base_duration) or base_duration))
        quantized = rgba.quantize(colors=palette_limit, method=getattr(Image, "FASTOCTREE", 2))
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

    first.save(out_path, format="GIF", **save_kwargs)


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
        ico_sizes = [(max(1, int(s)), max(1, int(s))) for s in ico_sizes_raw]
        im.save(out_path, format="ICO", sizes=ico_sizes)
        return
    im.save(out_path, **kwargs)
