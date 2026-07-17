"""Decode a source file and render a static or animated preview."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from image_engine_app.engine.models import SettingsState
from image_engine_app.engine.process.animation import save_animated_gif
from image_engine_app.engine.process.errors import ProcessingError, ProcessingUnavailable
from image_engine_app.engine.process.frame_pipeline import render_frame, resample_for_settings
from image_engine_app.engine.process.pillow_runtime import require_pillow


@dataclass(frozen=True)
class SourceRenderResult:
    """Result of rendering a source file for preview or derived output."""

    output_path: Path
    logical_size: tuple[int, int]
    encoded_size: tuple[int, int]
    frame_count: int
    is_animated: bool


def render_source_preview(
    *,
    source_path: str | Path,
    output_path: str | Path,
    settings: SettingsState,
) -> SourceRenderResult:
    """Render a source path without depending on UI state or asset objects."""

    Image, _, _, _ = require_pillow()
    source = Path(source_path)
    output = Path(output_path)
    if not source.exists() or not source.is_file():
        raise ProcessingError(f"Source image does not exist: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source) as image:
            frame_count = max(1, int(getattr(image, "n_frames", 1) or 1))
            is_animated = bool(getattr(image, "is_animated", False)) and frame_count > 1
            if is_animated and output.suffix.lower() == ".gif":
                animation = save_animated_gif(
                    image,
                    output,
                    gif_settings=settings.gif,
                    frame_transform=lambda frame: render_frame(frame, settings),
                    preserve_canvas_size=True,
                    resize_resample=resample_for_settings(settings),
                    default_duration_ms=100,
                )
                return SourceRenderResult(
                    output_path=animation.output_path,
                    logical_size=animation.logical_size,
                    encoded_size=animation.encoded_size,
                    frame_count=animation.frame_count,
                    is_animated=True,
                )

            image.load()
            rendered = render_frame(image, settings)
            rendered.save(output, format="PNG", optimize=True)
            size = (int(rendered.size[0]), int(rendered.size[1]))
            return SourceRenderResult(
                output_path=output,
                logical_size=size,
                encoded_size=size,
                frame_count=1,
                is_animated=False,
            )
    except ProcessingUnavailable:
        raise
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Processing failed for {source.name}: {exc}") from exc
