"""Settings group builder helpers for the settings panel."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget

from image_engine_app.engine.models import (
    BackgroundRemovalMode,
    ChromaSubsampling,
    ExportFormat,
    ExportProfile,
    ScaleMethod,
)


def settings_group_builders(panel: Any) -> dict[str, Callable[[QFormLayout, QWidget], None]]:
    return {
        "Pixel and Resolution": partial(build_pixel_resolution_group, panel),
        "Color and Light": partial(build_color_light_group, panel),
        "Detail": partial(build_detail_group, panel),
        "Cleanup": partial(build_cleanup_group, panel),
        "Edges": partial(build_edges_group, panel),
        "Transparency": partial(build_transparency_group, panel),
        "AI Enhance": partial(build_ai_enhance_group, panel),
        "GIF Controls": partial(build_gif_controls_group, panel),
        "Export": partial(build_export_group, panel),
        "Expert Encoding": partial(build_expert_encoding_group, panel),
    }


def build_pixel_resolution_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    resize = panel._new_float_spin(page, minimum=1.0, maximum=3200.0, step=10.0, default=100.0)
    resize.setSuffix(" %")
    resize.valueChanged.connect(panel._on_resize_percent_changed)
    panel._resize_percent = resize
    form.addRow("Resize % (real size)", resize)

    dpi = QSpinBox(page)
    dpi.setRange(1, 2400)
    dpi.setValue(72)
    dpi.valueChanged.connect(panel._on_dpi_changed)
    panel._dpi = dpi
    form.addRow("DPI (metadata)", dpi)

    target_width = QSpinBox(page)
    target_width.setRange(0, 32768)
    target_width.setValue(0)
    target_width.setSpecialValueText("Auto")
    target_width.setToolTip("0 = Auto. Set an exact output width in pixels.")
    target_width.valueChanged.connect(panel._on_target_width_changed)
    panel._target_width = target_width
    form.addRow("Target width (px)", target_width)

    target_height = QSpinBox(page)
    target_height.setRange(0, 32768)
    target_height.setValue(0)
    target_height.setSpecialValueText("Auto")
    target_height.setToolTip("0 = Auto. Set an exact output height in pixels.")
    target_height.valueChanged.connect(panel._on_target_height_changed)
    panel._target_height = target_height
    form.addRow("Target height (px)", target_height)

    scale_method = QComboBox(page)
    scale_method.addItem("Nearest (pixel art)", ScaleMethod.NEAREST)
    scale_method.addItem("Bilinear (smooth)", ScaleMethod.BILINEAR)
    scale_method.addItem("Bicubic (balanced)", ScaleMethod.BICUBIC)
    scale_method.addItem("Lanczos (sharp photo)", ScaleMethod.LANCZOS)
    scale_method.currentIndexChanged.connect(panel._on_scale_method_changed)
    panel._scale_method = scale_method
    form.addRow("Scale method", scale_method)

    snap = QCheckBox("Pixel snap (nearest)", page)
    snap.setToolTip("On = nearest-neighbor scaling for pixel art. Off = use the selected scale method.")
    panel._bind_bool(snap, "pixel", "pixel_snap")
    panel._pixel_snap = snap
    form.addRow("", snap)


def build_color_light_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    brightness = panel._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(brightness, "color", "brightness")
    panel._brightness = brightness
    form.addRow("Brightness (light/dark)", brightness)

    contrast = panel._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(contrast, "color", "contrast")
    panel._contrast = contrast
    form.addRow("Contrast (separation)", contrast)

    saturation = panel._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(saturation, "color", "saturation")
    panel._saturation = saturation
    form.addRow("Saturation (color)", saturation)

    temperature = panel._new_float_spin(page, minimum=-1.0, maximum=1.0, step=0.05, default=0.0)
    panel._bind_float(temperature, "color", "temperature")
    panel._temperature = temperature
    form.addRow("Temperature (warm/cool)", temperature)

    gamma = panel._new_float_spin(page, minimum=0.1, maximum=8.0, step=0.05, default=1.0)
    panel._bind_float(gamma, "color", "gamma")
    panel._gamma = gamma
    form.addRow("Gamma (midtones)", gamma)


def build_detail_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    sharpen = panel._new_float_spin(page, minimum=-2.0, maximum=5.0, step=0.1, default=0.0)
    panel._bind_float(sharpen, "detail", "sharpen_amount")
    panel._sharpen_amount = sharpen
    sharpen.setToolTip("Positive sharpens; negative softens.")
    form.addRow("Sharpen (edge crispness)", sharpen)

    sharpen_radius = panel._new_float_spin(page, minimum=0.0, maximum=3.0, step=0.1, default=0.0)
    sharpen_radius.setSpecialValueText("Auto")
    sharpen_radius.setToolTip("0 = Auto radius. Increase for wider sharpening halo.")
    panel._bind_float(sharpen_radius, "detail", "sharpen_radius")
    panel._sharpen_radius = sharpen_radius
    form.addRow("Sharpen radius", sharpen_radius)

    sharpen_threshold = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.1, default=0.0)
    sharpen_threshold.setToolTip("Higher threshold protects flat areas from over-sharpening.")
    panel._bind_float(sharpen_threshold, "detail", "sharpen_threshold")
    panel._sharpen_threshold = sharpen_threshold
    form.addRow("Sharpen threshold", sharpen_threshold)

    clarity = panel._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(clarity, "detail", "clarity")
    panel._clarity = clarity
    clarity.setToolTip("Positive increases local contrast; negative softens.")
    form.addRow("Clarity (mid detail)", clarity)

    texture = panel._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(texture, "detail", "texture")
    panel._texture = texture
    texture.setToolTip("Positive enhances micro detail; negative smooths it.")
    form.addRow("Texture (fine detail)", texture)


def build_cleanup_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    denoise = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(denoise, "cleanup", "denoise")
    panel._denoise = denoise
    form.addRow("Denoise (noise cleanup)", denoise)

    artifact = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(artifact, "cleanup", "artifact_removal")
    panel._artifact_removal = artifact
    form.addRow("Artifact fix (compression)", artifact)

    halo = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(halo, "cleanup", "halo_cleanup")
    panel._halo_cleanup = halo
    form.addRow("Halo cleanup (edge glow)", halo)

    banding = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(banding, "cleanup", "banding_removal")
    panel._banding_removal = banding
    form.addRow("Banding cleanup", banding)


def build_edges_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    antialias = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(antialias, "edges", "antialias")
    panel._edge_antialias = antialias
    form.addRow("Antialias (edge smooth)", antialias)

    edge_refine = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(edge_refine, "edges", "edge_refine")
    panel._edge_refine = edge_refine
    form.addRow("Edge refine", edge_refine)

    grow_shrink = panel._new_float_spin(page, minimum=-8.0, maximum=8.0, step=1.0, default=0.0)
    panel._bind_float(grow_shrink, "edges", "grow_shrink_px")
    panel._edge_grow_shrink = grow_shrink
    form.addRow("Grow/Shrink (px)", grow_shrink)

    feather = panel._new_float_spin(page, minimum=0.0, maximum=8.0, step=0.25, default=0.0)
    panel._bind_float(feather, "edges", "feather_px")
    panel._edge_feather = feather
    form.addRow("Feather (px)", feather)


def build_transparency_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    white_bg_mode = QComboBox(page)
    white_bg_mode.addItem("Keep original", BackgroundRemovalMode.OFF.value)
    white_bg_mode.addItem("Remove white BG", BackgroundRemovalMode.WHITE.value)
    white_bg_mode.addItem("Remove black BG", BackgroundRemovalMode.BLACK.value)
    white_bg_mode.currentIndexChanged.connect(panel._on_white_bg_mode_changed)
    white_bg_mode.setToolTip(
        "Choose whether to keep the background, remove edge-connected white, or remove edge-connected black."
    )
    panel._white_bg_mode = white_bg_mode
    form.addRow("Background cutout", white_bg_mode)

    background_status = QLabel(page)
    background_status.setObjectName("settingsHelpText")
    background_status.setWordWrap(True)
    background_status.setText(
        "Load an asset to see whether it already has transparency or a removable white/black edge background."
    )
    panel._background_status = background_status
    form.addRow(background_status)

    alpha_smooth = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(alpha_smooth, "alpha", "alpha_smooth")
    panel._alpha_smooth = alpha_smooth
    form.addRow("Alpha smooth", alpha_smooth)

    matte = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(matte, "alpha", "matte_fix")
    panel._matte_fix = matte
    form.addRow("Matte fix", matte)

    threshold = QSpinBox(page)
    threshold.setRange(0, 255)
    threshold.setValue(0)
    panel._bind_int(threshold, "alpha", "alpha_threshold")
    panel._alpha_threshold = threshold
    form.addRow("Alpha threshold", threshold)


def build_ai_enhance_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    upscale = panel._new_float_spin(page, minimum=1.0, maximum=16.0, step=0.5, default=1.0)
    panel._bind_float(upscale, "ai", "upscale_factor")
    panel._upscale_factor = upscale
    form.addRow("Upscale factor", upscale)

    deblur = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(deblur, "ai", "deblur_strength")
    panel._ai_deblur = deblur
    form.addRow("Deblur strength", deblur)

    reconstruct = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(reconstruct, "ai", "detail_reconstruct")
    panel._ai_detail_reconstruct = reconstruct
    form.addRow("Detail reconstruct", reconstruct)

    bg_remove = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(bg_remove, "ai", "bg_remove_strength")
    panel._ai_bg_remove = bg_remove
    form.addRow("BG remove strength", bg_remove)


def build_gif_controls_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    frame_delay = QSpinBox(page)
    frame_delay.setRange(1, 5000)
    frame_delay.setValue(100)
    frame_delay.setSuffix(" ms")
    panel._bind_int(frame_delay, "gif", "frame_delay_ms")
    panel._frame_delay = frame_delay
    form.addRow("Frame delay", frame_delay)

    dither = panel._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
    panel._bind_float(dither, "gif", "dither_strength")
    panel._gif_dither = dither
    form.addRow("Dither", dither)

    loop = QCheckBox("Loop animation", page)
    panel._bind_bool(loop, "gif", "loop")
    panel._gif_loop = loop
    form.addRow("", loop)

    palette = QSpinBox(page)
    palette.setRange(2, 256)
    palette.setValue(256)
    panel._bind_int(palette, "gif", "palette_size")
    panel._gif_palette_size = palette
    form.addRow("Palette size", palette)

    optimize = QCheckBox("Optimize frames", page)
    panel._bind_bool(optimize, "gif", "frame_optimize")
    panel._gif_frame_optimize = optimize
    form.addRow("", optimize)


def build_export_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    format_hint = QLabel("Select an asset to enable export controls.", page)
    format_hint.setObjectName("shellHint")
    format_hint.setWordWrap(True)
    panel._export_format_hint = format_hint
    form.addRow("", format_hint)

    export_profile = QComboBox(page)
    export_profile.addItem("Web", ExportProfile.WEB)
    export_profile.addItem("App Asset", ExportProfile.APP_ASSET)
    export_profile.addItem("Print", ExportProfile.PRINT)
    export_profile.currentIndexChanged.connect(panel._on_export_profile_changed)
    panel._export_profile = export_profile
    form.addRow("Export profile", export_profile)

    export_format = QComboBox(page)
    export_format.addItem("Auto (profile/source)", ExportFormat.AUTO)
    export_format.addItem("PNG", ExportFormat.PNG)
    export_format.addItem("WEBP", ExportFormat.WEBP)
    export_format.addItem("JPG", ExportFormat.JPG)
    export_format.addItem("GIF", ExportFormat.GIF)
    export_format.addItem("ICO", ExportFormat.ICO)
    export_format.addItem("TIFF", ExportFormat.TIFF)
    export_format.addItem("BMP", ExportFormat.BMP)
    export_format.currentIndexChanged.connect(panel._on_export_format_changed)
    panel._export_format = export_format
    form.addRow("Export format", export_format)

    quality = QSpinBox(page)
    quality.setRange(1, 100)
    quality.setSingleStep(5)
    quality.setValue(90)
    quality.setSuffix(" %")
    quality.setToolTip("Used by JPEG and lossy WEBP exports. Higher quality keeps more detail but increases file size.")
    panel._bind_int(quality, "export", "quality")
    panel._export_quality = quality
    form.addRow("Lossy quality (JPEG/WEBP)", quality)

    quality_hint = QLabel(
        "100 = max quality/larger files. 70-85 is often a good web balance. PNG/GIF outputs usually ignore this control.",
        page,
    )
    quality_hint.setObjectName("shellHint")
    quality_hint.setWordWrap(True)
    panel._export_quality_hint = quality_hint
    form.addRow("", quality_hint)

    strip = QCheckBox("Remove metadata (recommended for web/private sharing)", page)
    strip.setChecked(True)
    strip.setToolTip("Removes metadata where supported. Can slightly reduce file size and improve privacy.")
    panel._bind_bool(strip, "export", "strip_metadata")
    panel._strip_metadata = strip
    form.addRow("", strip)


def build_expert_encoding_group(panel: Any, form: QFormLayout, page: QWidget) -> None:
    open_encoding = QPushButton("Open Encoding Window", page)
    open_encoding.setAutoDefault(False)
    open_encoding.clicked.connect(panel._emit_open_encoding_window)
    panel._open_encoding_window_btn = open_encoding
    form.addRow("", open_encoding)

    compression = QSpinBox(page)
    compression.setRange(0, 9)
    compression.setValue(6)
    panel._bind_int(compression, "export", "compression_level")
    panel._compression_level = compression
    form.addRow("Compression level", compression)

    chroma = QComboBox(page)
    chroma.addItem("Auto", ChromaSubsampling.AUTO)
    chroma.addItem("4:4:4", ChromaSubsampling.CS_444)
    chroma.addItem("4:2:2", ChromaSubsampling.CS_422)
    chroma.addItem("4:2:0", ChromaSubsampling.CS_420)
    chroma.currentIndexChanged.connect(panel._on_chroma_subsampling_changed)
    panel._chroma_subsampling = chroma
    form.addRow("Chroma subsampling", chroma)

    palette_limit = QSpinBox(page)
    palette_limit.setRange(0, 256)
    palette_limit.setValue(0)
    palette_limit.setSpecialValueText("Auto")
    palette_limit.valueChanged.connect(panel._on_palette_limit_changed)
    panel._palette_limit = palette_limit
    form.addRow("Palette Limit", palette_limit)

    ico_sizes = QLineEdit(page)
    ico_sizes.setPlaceholderText("16, 32, 48, 64, 128, 256")
    ico_sizes.setToolTip("Comma-separated icon sizes used when exporting ICO.")
    ico_sizes.editingFinished.connect(panel._on_ico_sizes_changed)
    panel._ico_sizes = ico_sizes
    form.addRow("ICO sizes", ico_sizes)
