"""Scrollable settings panel with mode/format gating and core settings wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from engine.models import ChromaSubsampling, EditMode, ExportFormat, ExportProfile, ScaleMethod
from ui.common.state_bindings import EngineUIState


MODE_ORDER = {
    EditMode.SIMPLE.value: 0,
    EditMode.ADVANCED.value: 1,
    EditMode.EXPERT.value: 2,
}


@dataclass(frozen=True)
class _GroupSpec:
    title: str
    min_mode: str = EditMode.SIMPLE.value
    requires_alpha: bool = False
    requires_gif: bool = False


class SettingsPanel(QScrollArea):
    """Right-docked settings panel shell matching the spec layout."""

    open_encoding_window_requested = Signal()

    GROUP_SPECS = [
        _GroupSpec("Pixel and Resolution", min_mode=EditMode.SIMPLE.value),
        _GroupSpec("Color and Light", min_mode=EditMode.SIMPLE.value),
        _GroupSpec("Detail", min_mode=EditMode.SIMPLE.value),
        _GroupSpec("Cleanup", min_mode=EditMode.SIMPLE.value),
        _GroupSpec("Edges", min_mode=EditMode.ADVANCED.value),
        _GroupSpec("Transparency", min_mode=EditMode.ADVANCED.value),
        _GroupSpec("AI Enhance", min_mode=EditMode.ADVANCED.value),
        _GroupSpec("GIF Controls", min_mode=EditMode.ADVANCED.value, requires_gif=True),
        _GroupSpec("Export", min_mode=EditMode.SIMPLE.value),
        _GroupSpec("Expert Encoding", min_mode=EditMode.EXPERT.value),
    ]
    GROUP_HELP = {
        "Pixel and Resolution": "Resize changes real output dimensions. DPI is kept in sync with Resize to preserve print-size intent; use target width/height for exact output size and Scale method for style.",
        "Color and Light": "Tone controls only. 0.00 means no change; start small (0.05 to 0.25) and compare before/final.",
        "Detail": "Adds crispness and micro-detail. Positive values sharpen; negative values soften. Start low and compare before/final.",
        "Cleanup": "Reduces noise, artifacts, halos, and banding. Start at 0.05 to 0.25 and increase slowly.",
        "Edges": "Refines edge shape and softness. Use antialias/refine first, then feather/grow-shrink if needed.",
        "Transparency": "Choose whether to keep white background or convert white to transparency, then refine alpha edges with smooth/matte/threshold.",
        "AI Enhance": "Live preview approximation of AI-style controls. Set Upscale first, then Deblur/Detail in small steps.",
        "GIF Controls": "Animation timing and palette controls for GIF quality/file size. Unlocks when a GIF asset is active.",
        "Export": "Final output quality and metadata controls. Quality applies to JPEG/WEBP lossy output; PNG/GIF mostly ignore quality.",
        "Expert Encoding": "Advanced compression/chroma/palette controls for final size tuning (usually after all visual edits).",
    }

    _LOCK_THEME = {
        "mode": ("#1f4d53", "#edf8f6", "#91bcb6"),
        "alpha": ("#0b5f4f", "#ecfdf6", "#9fdac4"),
        "gif": ("#7a4f0f", "#fff8e8", "#eac879"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._search = QLineEdit(self)
        self._toolbox = QToolBox(self)
        self._filter_hint = QLabel("", self)
        self._group_indices: dict[str, int] = {}
        self._group_specs_by_index: dict[int, _GroupSpec] = {}
        self._group_lock_labels_by_index: dict[int, QLabel] = {}
        self._group_controls_by_index: dict[int, QWidget] = {}
        self._current_mode = EditMode.SIMPLE.value
        self._asset_has_alpha = False
        self._asset_is_gif = False
        self._suspend_setting_events = False
        self._syncing_resize_dpi = False
        self._last_resize_percent_for_dpi_sync = 100.0
        self._last_dpi_for_resize_sync = 72

        # Pixel
        self._resize_percent: QDoubleSpinBox | None = None
        self._dpi: QSpinBox | None = None
        self._pixel_snap: QCheckBox | None = None
        self._target_width: QSpinBox | None = None
        self._target_height: QSpinBox | None = None
        self._scale_method: QComboBox | None = None
        self._resize_preset_combo: QComboBox | None = None
        self._resize_preset_apply: QPushButton | None = None
        self._reset_current_defaults_btn: QPushButton | None = None

        # Color
        self._brightness: QDoubleSpinBox | None = None
        self._contrast: QDoubleSpinBox | None = None
        self._saturation: QDoubleSpinBox | None = None
        self._temperature: QDoubleSpinBox | None = None
        self._gamma: QDoubleSpinBox | None = None

        # Detail
        self._sharpen_amount: QDoubleSpinBox | None = None
        self._sharpen_radius: QDoubleSpinBox | None = None
        self._sharpen_threshold: QDoubleSpinBox | None = None
        self._clarity: QDoubleSpinBox | None = None
        self._texture: QDoubleSpinBox | None = None

        # Cleanup
        self._denoise: QDoubleSpinBox | None = None
        self._artifact_removal: QDoubleSpinBox | None = None
        self._halo_cleanup: QDoubleSpinBox | None = None
        self._banding_removal: QDoubleSpinBox | None = None

        # Edges
        self._edge_antialias: QDoubleSpinBox | None = None
        self._edge_refine: QDoubleSpinBox | None = None
        self._edge_grow_shrink: QDoubleSpinBox | None = None
        self._edge_feather: QDoubleSpinBox | None = None

        # Transparency
        self._white_bg_mode: QComboBox | None = None
        self._alpha_smooth: QDoubleSpinBox | None = None
        self._matte_fix: QDoubleSpinBox | None = None
        self._alpha_threshold: QSpinBox | None = None

        # AI
        self._upscale_factor: QDoubleSpinBox | None = None
        self._ai_deblur: QDoubleSpinBox | None = None
        self._ai_detail_reconstruct: QDoubleSpinBox | None = None
        self._ai_bg_remove: QDoubleSpinBox | None = None

        # GIF
        self._frame_delay: QSpinBox | None = None
        self._gif_dither: QDoubleSpinBox | None = None
        self._gif_loop: QCheckBox | None = None
        self._gif_palette_size: QSpinBox | None = None
        self._gif_frame_optimize: QCheckBox | None = None

        # Export
        self._export_profile: QComboBox | None = None
        self._export_format: QComboBox | None = None
        self._export_quality: QSpinBox | None = None
        self._strip_metadata: QCheckBox | None = None
        self._export_format_hint: QLabel | None = None
        self._export_quality_hint: QLabel | None = None

        # Expert encoding
        self._open_encoding_window_btn: QPushButton | None = None
        self._compression_level: QSpinBox | None = None
        self._chroma_subsampling: QComboBox | None = None
        self._palette_limit: QSpinBox | None = None
        self._ico_sizes: QLineEdit | None = None

        self._build_ui()

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        ui_state.mode_changed.connect(self._on_mode_changed)
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        ui_state.export_profile_changed.connect(lambda _value: self._sync_controls_from_asset(ui_state.active_asset))
        self._on_mode_changed(ui_state.active_asset.edit_state.mode.value if ui_state.active_asset else EditMode.SIMPLE.value)
        self._on_active_asset_changed(ui_state.active_asset)

    def _build_ui(self) -> None:
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self._search.setPlaceholderText("Search settings groups (pixel, export, gif, transparency...)")
        self._search.textChanged.connect(lambda _text: self._apply_filters())
        layout.addWidget(self._search)

        self._filter_hint.setStyleSheet("color:#4f6b70; font-size:11px;")
        layout.addWidget(self._filter_hint)

        reset_current_btn = QPushButton("Reset Current to Defaults", container)
        reset_current_btn.setAutoDefault(False)
        reset_current_btn.setToolTip("Reset only the active asset settings to safe defaults.")
        reset_current_btn.clicked.connect(self._emit_reset_current_defaults)
        self._reset_current_defaults_btn = reset_current_btn
        layout.addWidget(reset_current_btn)

        self._toolbox.setStyleSheet(
            "QToolBox::tab { padding:4px 12px 4px 22px; min-height:30px; font-weight:600; }"
        )
        layout.addWidget(self._toolbox, 1)

        for spec in self.GROUP_SPECS:
            page, controls_widget, lock_label = self._build_group_page(spec)
            idx = self._toolbox.addItem(page, spec.title)
            self._group_indices[spec.title] = idx
            self._group_specs_by_index[idx] = spec
            self._group_controls_by_index[idx] = controls_widget
            self._group_lock_labels_by_index[idx] = lock_label

        layout.addStretch(0)
        self.setWidget(container)
        self.setMinimumWidth(470)
        self._apply_filters()
        self._set_bound_controls_enabled(False)

    def _new_float_spin(
        self,
        parent: QWidget,
        *,
        minimum: float,
        maximum: float,
        step: float,
        default: float,
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox(parent)
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(2)
        widget.setAccelerated(True)
        widget.setMinimumWidth(186)
        widget.setValue(default)
        return widget

    @staticmethod
    def _apply_editor_width_defaults(parent: QWidget) -> None:
        for spin in parent.findChildren(QSpinBox):
            spin.setMinimumWidth(max(spin.minimumWidth(), 186))
        for dspin in parent.findChildren(QDoubleSpinBox):
            dspin.setMinimumWidth(max(dspin.minimumWidth(), 186))
        for combo in parent.findChildren(QComboBox):
            combo.setMinimumWidth(max(combo.minimumWidth(), 216))

    def _bind_float(self, widget: QDoubleSpinBox, group_name: str, field_name: str) -> None:
        widget.valueChanged.connect(
            lambda value, g=group_name, f=field_name: self._update_setting(g, f, float(value))
        )

    def _bind_int(self, widget: QSpinBox, group_name: str, field_name: str) -> None:
        widget.valueChanged.connect(
            lambda value, g=group_name, f=field_name: self._update_setting(g, f, int(value))
        )

    def _bind_bool(self, widget: QCheckBox, group_name: str, field_name: str) -> None:
        widget.toggled.connect(
            lambda checked, g=group_name, f=field_name: self._update_setting(g, f, bool(checked))
        )

    def _build_group_page(self, spec: _GroupSpec) -> tuple[QWidget, QWidget, QLabel]:
        page = QWidget(self)
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(8)

        help_text = self.GROUP_HELP.get(spec.title, "")
        if help_text:
            help_label = QLabel(help_text, page)
            help_label.setWordWrap(True)
            help_label.setStyleSheet("color:#3f5f64; font-size:12px;")
            vbox.addWidget(help_label)

        lock_label = QLabel("", page)
        lock_label.setWordWrap(True)
        lock_label.setVisible(False)
        lock_label.setStyleSheet(
            "QLabel { color:#7a4f0f; background:#fff8e8; border:1px solid #eac879; border-radius:6px; padding:6px 8px; }"
        )
        vbox.addWidget(lock_label)

        controls_widget = QWidget(page)
        form = QFormLayout(controls_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        if spec.title == "Pixel and Resolution":
            resize = self._new_float_spin(page, minimum=1.0, maximum=3200.0, step=10.0, default=100.0)
            resize.setSuffix(" %")
            resize.valueChanged.connect(self._on_resize_percent_changed)
            self._resize_percent = resize
            form.addRow("Resize % (real size)", resize)

            dpi = QSpinBox(page)
            dpi.setRange(1, 2400)
            dpi.setValue(72)
            dpi.valueChanged.connect(self._on_dpi_changed)
            self._dpi = dpi
            form.addRow("DPI (metadata)", dpi)

            target_width = QSpinBox(page)
            target_width.setRange(0, 32768)
            target_width.setValue(0)
            target_width.setSpecialValueText("Auto")
            target_width.setToolTip("0 = Auto. Set an exact output width in pixels.")
            target_width.valueChanged.connect(self._on_target_width_changed)
            self._target_width = target_width
            form.addRow("Target width (px)", target_width)

            target_height = QSpinBox(page)
            target_height.setRange(0, 32768)
            target_height.setValue(0)
            target_height.setSpecialValueText("Auto")
            target_height.setToolTip("0 = Auto. Set an exact output height in pixels.")
            target_height.valueChanged.connect(self._on_target_height_changed)
            self._target_height = target_height
            form.addRow("Target height (px)", target_height)

            scale_method = QComboBox(page)
            scale_method.addItem("Nearest (pixel art)", ScaleMethod.NEAREST)
            scale_method.addItem("Bilinear (smooth)", ScaleMethod.BILINEAR)
            scale_method.addItem("Bicubic (balanced)", ScaleMethod.BICUBIC)
            scale_method.addItem("Lanczos (sharp photo)", ScaleMethod.LANCZOS)
            scale_method.currentIndexChanged.connect(self._on_scale_method_changed)
            self._scale_method = scale_method
            form.addRow("Scale method", scale_method)

            snap = QCheckBox("Pixel snap (nearest)", page)
            snap.setToolTip("On = nearest-neighbor scaling for pixel art. Off = use the selected scale method.")
            self._bind_bool(snap, "pixel", "pixel_snap")
            self._pixel_snap = snap
            form.addRow("", snap)

            preset_row = QWidget(page)
            preset_layout = QHBoxLayout(preset_row)
            preset_layout.setContentsMargins(0, 0, 0, 0)
            preset_layout.setSpacing(6)

            preset_combo = QComboBox(preset_row)
            preset_combo.addItem("Choose...", None)
            for percent, label in (
                (125.0, "125% (1.25x)"),
                (150.0, "150% (1.5x)"),
                (200.0, "200% (2x)"),
                (300.0, "300% (3x)"),
                (400.0, "400% (4x)"),
                (800.0, "800% (8x)"),
            ):
                preset_combo.addItem(label, percent)
            self._resize_preset_combo = preset_combo
            preset_layout.addWidget(preset_combo, 1)

            preset_apply = QPushButton("Set", preset_row)
            preset_apply.setAutoDefault(False)
            preset_apply.setFixedWidth(56)
            preset_apply.clicked.connect(self._apply_selected_resize_preset)
            self._resize_preset_apply = preset_apply
            preset_layout.addWidget(preset_apply)

            form.addRow("Quick Upscale", preset_row)

        elif spec.title == "Color and Light":
            brightness = self._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(brightness, "color", "brightness")
            self._brightness = brightness
            form.addRow("Brightness (light/dark)", brightness)

            contrast = self._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(contrast, "color", "contrast")
            self._contrast = contrast
            form.addRow("Contrast (separation)", contrast)

            saturation = self._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(saturation, "color", "saturation")
            self._saturation = saturation
            form.addRow("Saturation (color)", saturation)

            temperature = self._new_float_spin(page, minimum=-1.0, maximum=1.0, step=0.05, default=0.0)
            self._bind_float(temperature, "color", "temperature")
            self._temperature = temperature
            form.addRow("Temperature (warm/cool)", temperature)

            gamma = self._new_float_spin(page, minimum=0.1, maximum=8.0, step=0.05, default=1.0)
            self._bind_float(gamma, "color", "gamma")
            self._gamma = gamma
            form.addRow("Gamma (midtones)", gamma)

        elif spec.title == "Detail":
            sharpen = self._new_float_spin(page, minimum=-2.0, maximum=5.0, step=0.1, default=0.0)
            self._bind_float(sharpen, "detail", "sharpen_amount")
            self._sharpen_amount = sharpen
            sharpen.setToolTip("Positive sharpens; negative softens.")
            form.addRow("Sharpen (edge crispness)", sharpen)

            sharpen_radius = self._new_float_spin(page, minimum=0.0, maximum=3.0, step=0.1, default=0.0)
            sharpen_radius.setSpecialValueText("Auto")
            sharpen_radius.setToolTip("0 = Auto radius. Increase for wider sharpening halo.")
            self._bind_float(sharpen_radius, "detail", "sharpen_radius")
            self._sharpen_radius = sharpen_radius
            form.addRow("Sharpen radius", sharpen_radius)

            sharpen_threshold = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.1, default=0.0)
            sharpen_threshold.setToolTip("Higher threshold protects flat areas from over-sharpening.")
            self._bind_float(sharpen_threshold, "detail", "sharpen_threshold")
            self._sharpen_threshold = sharpen_threshold
            form.addRow("Sharpen threshold", sharpen_threshold)

            clarity = self._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(clarity, "detail", "clarity")
            self._clarity = clarity
            clarity.setToolTip("Positive increases local contrast; negative softens.")
            form.addRow("Clarity (mid detail)", clarity)

            texture = self._new_float_spin(page, minimum=-2.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(texture, "detail", "texture")
            self._texture = texture
            texture.setToolTip("Positive enhances micro detail; negative smooths it.")
            form.addRow("Texture (fine detail)", texture)

        elif spec.title == "Cleanup":
            denoise = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(denoise, "cleanup", "denoise")
            self._denoise = denoise
            form.addRow("Denoise (noise cleanup)", denoise)

            artifact = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(artifact, "cleanup", "artifact_removal")
            self._artifact_removal = artifact
            form.addRow("Artifact fix (compression)", artifact)

            halo = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(halo, "cleanup", "halo_cleanup")
            self._halo_cleanup = halo
            form.addRow("Halo cleanup (edge glow)", halo)

            banding = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(banding, "cleanup", "banding_removal")
            self._banding_removal = banding
            form.addRow("Banding cleanup", banding)

        elif spec.title == "Edges":
            antialias = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(antialias, "edges", "antialias")
            self._edge_antialias = antialias
            form.addRow("Antialias (edge smooth)", antialias)

            edge_refine = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(edge_refine, "edges", "edge_refine")
            self._edge_refine = edge_refine
            form.addRow("Edge refine", edge_refine)

            grow_shrink = self._new_float_spin(page, minimum=-8.0, maximum=8.0, step=1.0, default=0.0)
            self._bind_float(grow_shrink, "edges", "grow_shrink_px")
            self._edge_grow_shrink = grow_shrink
            form.addRow("Grow/Shrink (px)", grow_shrink)

            feather = self._new_float_spin(page, minimum=0.0, maximum=8.0, step=0.25, default=0.0)
            self._bind_float(feather, "edges", "feather_px")
            self._edge_feather = feather
            form.addRow("Feather (px)", feather)

        elif spec.title == "Transparency":
            white_bg_mode = QComboBox(page)
            white_bg_mode.addItem("Keep white background", False)
            white_bg_mode.addItem("Remove white background", True)
            white_bg_mode.currentIndexChanged.connect(self._on_white_bg_mode_changed)
            white_bg_mode.setToolTip("Keep = preserve white as-is. Remove = convert near-white background to transparency.")
            self._white_bg_mode = white_bg_mode
            form.addRow("White background", white_bg_mode)

            alpha_smooth = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(alpha_smooth, "alpha", "alpha_smooth")
            self._alpha_smooth = alpha_smooth
            form.addRow("Alpha smooth", alpha_smooth)

            matte = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(matte, "alpha", "matte_fix")
            self._matte_fix = matte
            form.addRow("Matte fix", matte)

            threshold = QSpinBox(page)
            threshold.setRange(0, 255)
            threshold.setValue(0)
            self._bind_int(threshold, "alpha", "alpha_threshold")
            self._alpha_threshold = threshold
            form.addRow("Alpha threshold", threshold)

        elif spec.title == "AI Enhance":
            upscale = self._new_float_spin(page, minimum=1.0, maximum=16.0, step=0.5, default=1.0)
            self._bind_float(upscale, "ai", "upscale_factor")
            self._upscale_factor = upscale
            form.addRow("Upscale factor", upscale)

            deblur = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(deblur, "ai", "deblur_strength")
            self._ai_deblur = deblur
            form.addRow("Deblur strength", deblur)

            reconstruct = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(reconstruct, "ai", "detail_reconstruct")
            self._ai_detail_reconstruct = reconstruct
            form.addRow("Detail reconstruct", reconstruct)

            bg_remove = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(bg_remove, "ai", "bg_remove_strength")
            self._ai_bg_remove = bg_remove
            form.addRow("BG remove strength", bg_remove)

        elif spec.title == "GIF Controls":
            frame_delay = QSpinBox(page)
            frame_delay.setRange(1, 5000)
            frame_delay.setValue(100)
            frame_delay.setSuffix(" ms")
            self._bind_int(frame_delay, "gif", "frame_delay_ms")
            self._frame_delay = frame_delay
            form.addRow("Frame delay", frame_delay)

            dither = self._new_float_spin(page, minimum=0.0, maximum=2.0, step=0.05, default=0.0)
            self._bind_float(dither, "gif", "dither_strength")
            self._gif_dither = dither
            form.addRow("Dither", dither)

            loop = QCheckBox("Loop animation", page)
            self._bind_bool(loop, "gif", "loop")
            self._gif_loop = loop
            form.addRow("", loop)

            palette = QSpinBox(page)
            palette.setRange(2, 256)
            palette.setValue(256)
            self._bind_int(palette, "gif", "palette_size")
            self._gif_palette_size = palette
            form.addRow("Palette size", palette)

            optimize = QCheckBox("Optimize frames", page)
            self._bind_bool(optimize, "gif", "frame_optimize")
            self._gif_frame_optimize = optimize
            form.addRow("", optimize)

        elif spec.title == "Export":
            format_hint = QLabel("Select an asset to enable export controls.", page)
            format_hint.setWordWrap(True)
            format_hint.setStyleSheet("color:#3f5f64; font-size:11px;")
            self._export_format_hint = format_hint
            form.addRow("", format_hint)

            export_profile = QComboBox(page)
            export_profile.addItem("Web", ExportProfile.WEB)
            export_profile.addItem("App Asset", ExportProfile.APP_ASSET)
            export_profile.addItem("Print", ExportProfile.PRINT)
            export_profile.currentIndexChanged.connect(self._on_export_profile_changed)
            self._export_profile = export_profile
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
            export_format.currentIndexChanged.connect(self._on_export_format_changed)
            self._export_format = export_format
            form.addRow("Export format", export_format)

            quality = QSpinBox(page)
            quality.setRange(1, 100)
            quality.setSingleStep(5)
            quality.setValue(90)
            quality.setSuffix(" %")
            quality.setToolTip("Used by JPEG and lossy WEBP exports. Higher quality keeps more detail but increases file size.")
            self._bind_int(quality, "export", "quality")
            self._export_quality = quality
            form.addRow("Lossy quality (JPEG/WEBP)", quality)

            quality_hint = QLabel(
                "100 = max quality/larger files. 70-85 is often a good web balance. PNG/GIF outputs usually ignore this control.",
                page,
            )
            quality_hint.setWordWrap(True)
            quality_hint.setStyleSheet("color:#4f6b70; font-size:11px;")
            self._export_quality_hint = quality_hint
            form.addRow("", quality_hint)

            strip = QCheckBox("Remove metadata (recommended for web/private sharing)", page)
            strip.setChecked(True)
            strip.setToolTip("Removes metadata where supported. Can slightly reduce file size and improve privacy.")
            self._bind_bool(strip, "export", "strip_metadata")
            self._strip_metadata = strip
            form.addRow("", strip)

        elif spec.title == "Expert Encoding":
            open_encoding = QPushButton("Open Encoding Window", page)
            open_encoding.setAutoDefault(False)
            open_encoding.clicked.connect(self._emit_open_encoding_window)
            self._open_encoding_window_btn = open_encoding
            form.addRow("", open_encoding)

            compression = QSpinBox(page)
            compression.setRange(0, 9)
            compression.setValue(6)
            self._bind_int(compression, "export", "compression_level")
            self._compression_level = compression
            form.addRow("Compression level", compression)

            chroma = QComboBox(page)
            chroma.addItem("Auto", ChromaSubsampling.AUTO)
            chroma.addItem("4:4:4", ChromaSubsampling.CS_444)
            chroma.addItem("4:2:2", ChromaSubsampling.CS_422)
            chroma.addItem("4:2:0", ChromaSubsampling.CS_420)
            chroma.currentIndexChanged.connect(self._on_chroma_subsampling_changed)
            self._chroma_subsampling = chroma
            form.addRow("Chroma subsampling", chroma)

            palette_limit = QSpinBox(page)
            palette_limit.setRange(0, 256)
            palette_limit.setValue(0)
            palette_limit.setSpecialValueText("Auto")
            palette_limit.valueChanged.connect(self._on_palette_limit_changed)
            self._palette_limit = palette_limit
            form.addRow("Palette Limit", palette_limit)

            ico_sizes = QLineEdit(page)
            ico_sizes.setPlaceholderText("16, 32, 48, 64, 128, 256")
            ico_sizes.setToolTip("Comma-separated icon sizes used when exporting ICO.")
            ico_sizes.editingFinished.connect(self._on_ico_sizes_changed)
            self._ico_sizes = ico_sizes
            form.addRow("ICO sizes", ico_sizes)

        self._apply_editor_width_defaults(controls_widget)
        vbox.addWidget(controls_widget)
        vbox.addStretch(1)
        return page, controls_widget, lock_label

    def _set_lock_label_message(self, lock_label: QLabel, *, lock_kind: str, reason: str) -> None:
        kind = lock_kind if lock_kind in self._LOCK_THEME else "mode"
        fg, bg, border = self._LOCK_THEME[kind]
        heading = {
            "mode": "Mode",
            "alpha": "Transparency",
            "gif": "GIF",
        }.get(kind, "Settings")
        lock_label.setText(f"Locked ({heading}): {reason}")
        lock_label.setStyleSheet(
            f"QLabel {{ color:{fg}; background:{bg}; border:1px solid {border}; border-radius:6px; padding:6px 8px; }}"
        )

    def _emit_reset_current_defaults(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_global_reset()

    def _emit_open_encoding_window(self) -> None:
        self.open_encoding_window_requested.emit()

    def _apply_selected_resize_preset(self) -> None:
        if self._resize_percent is None or self._resize_preset_combo is None:
            return
        value = self._resize_preset_combo.currentData()
        if value is None:
            return
        self._resize_percent.setValue(float(value))

    def _on_resize_percent_changed(self, value: float) -> None:
        value_f = float(value)
        self._update_setting("pixel", "resize_percent", value_f)

        if self._suspend_setting_events:
            self._last_resize_percent_for_dpi_sync = value_f
            return

        if self._syncing_resize_dpi or self._dpi is None:
            self._last_resize_percent_for_dpi_sync = value_f
            return

        previous_resize = max(0.01, float(self._last_resize_percent_for_dpi_sync))
        current_dpi = int(self._dpi.value())
        scaled_dpi = int(round(current_dpi * (value_f / previous_resize)))
        self._last_resize_percent_for_dpi_sync = value_f
        scaled_dpi = max(1, min(int(self._dpi.maximum()), scaled_dpi))
        if scaled_dpi == current_dpi:
            self._last_dpi_for_resize_sync = current_dpi
            return

        self._syncing_resize_dpi = True
        try:
            self._dpi.setValue(scaled_dpi)
        finally:
            self._syncing_resize_dpi = False
        self._last_dpi_for_resize_sync = int(self._dpi.value())

    def _on_dpi_changed(self, value: int) -> None:
        value_i = int(value)
        self._update_setting("pixel", "dpi", value_i)

        if self._suspend_setting_events:
            self._last_dpi_for_resize_sync = value_i
            return

        if self._syncing_resize_dpi or self._resize_percent is None:
            self._last_dpi_for_resize_sync = value_i
            return

        previous_dpi = max(1, int(self._last_dpi_for_resize_sync))
        current_resize = float(self._resize_percent.value())
        scaled_resize = current_resize * (value_i / previous_dpi)
        self._last_dpi_for_resize_sync = value_i
        scaled_resize = max(float(self._resize_percent.minimum()), min(float(self._resize_percent.maximum()), scaled_resize))
        if abs(scaled_resize - current_resize) < 0.01:
            self._last_resize_percent_for_dpi_sync = current_resize
            return

        self._syncing_resize_dpi = True
        try:
            self._resize_percent.setValue(scaled_resize)
        finally:
            self._syncing_resize_dpi = False
        self._last_resize_percent_for_dpi_sync = float(self._resize_percent.value())

    def _on_mode_changed(self, mode_value: str) -> None:
        self._current_mode = mode_value
        self._apply_filters()

    def _on_active_asset_changed(self, asset: object) -> None:
        if asset is None:
            self._asset_has_alpha = False
            self._asset_is_gif = False
        else:
            caps = getattr(asset, "capabilities", None)
            self._asset_has_alpha = bool(getattr(caps, "has_alpha", False))
            fmt_value = getattr(getattr(asset, "format", None), "value", "")
            self._asset_is_gif = (fmt_value == "gif")
        self._sync_controls_from_asset(asset)
        self._apply_filters()
        self._update_export_controls_hint(asset)

    def _apply_filters(self) -> None:
        query = self._search.text().strip().lower()
        visible_count = 0
        for idx in range(self._toolbox.count()):
            spec = self._group_specs_by_index[idx]
            matches_query = (not query) or (query in spec.title.lower())
            meets_mode = MODE_ORDER[self._current_mode] >= MODE_ORDER[spec.min_mode]
            format_ok = True
            if spec.requires_alpha and not self._asset_has_alpha:
                format_ok = False
            if spec.requires_gif and not self._asset_is_gif:
                format_ok = False

            reason = ""
            lock_kind = ""
            if not matches_query:
                reason = f"Filtered by search: {query!r}"
            elif not meets_mode:
                reason = f"Requires {spec.min_mode.title()} mode."
                lock_kind = "mode"
            elif spec.requires_alpha and not self._asset_has_alpha:
                reason = "Requires an image with transparency (alpha channel)."
                lock_kind = "alpha"
            elif spec.requires_gif and not self._asset_is_gif:
                reason = "Requires a GIF/animated asset."
                lock_kind = "gif"

            page = self._toolbox.widget(idx)
            controls_widget = self._group_controls_by_index.get(idx)
            lock_label = self._group_lock_labels_by_index.get(idx)

            if page is not None:
                page.setVisible(matches_query)
            self._toolbox.setItemEnabled(idx, bool(matches_query))

            if not matches_query:
                self._toolbox.setItemToolTip(idx, "")
                continue

            visible_count += 1

            locked = bool(reason)
            self._toolbox.setItemText(idx, spec.title)
            self._toolbox.setItemToolTip(idx, "" if not locked else reason)

            if lock_label is not None:
                lock_label.setVisible(locked)
                if locked:
                    self._set_lock_label_message(lock_label, lock_kind=lock_kind, reason=reason)
            if controls_widget is not None:
                controls_widget.setEnabled(not locked)

        if query:
            self._filter_hint.setText(f"Filter: {query!r} ({visible_count} groups visible)")
        else:
            self._filter_hint.setText("")

    def _update_export_controls_hint(self, asset: object) -> None:
        if self._export_format_hint is None:
            return

        if asset is None:
            self._export_format_hint.setText("No asset selected. Load an image to edit export settings.")
            if self._export_quality is not None:
                self._export_quality.setEnabled(False)
            if self._export_quality_hint is not None:
                self._export_quality_hint.setText(
                    "Quality control is enabled after you select an asset."
                )
            return

        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        export_group = getattr(settings, "export", None)
        export_format = getattr(export_group, "format", None)

        selected_fmt_value = str(getattr(export_format, "value", "")).strip().lower()
        source_fmt_value = str(getattr(getattr(asset, "format", None), "value", "")).strip().lower()
        if selected_fmt_value in {"", ExportFormat.AUTO.value}:
            effective_fmt_value = source_fmt_value
            effective_fmt_label = f"AUTO ({source_fmt_value.upper() if source_fmt_value else 'UNKNOWN'})"
        else:
            effective_fmt_value = selected_fmt_value
            effective_fmt_label = selected_fmt_value.upper()

        lossy = effective_fmt_value in {"jpg", "jpeg", "webp"}

        if lossy:
            self._export_format_hint.setText(
                f"Active export format: {effective_fmt_label}. Quality directly affects export output."
            )
        else:
            self._export_format_hint.setText(
                f"Active export format: {effective_fmt_label}. Quality is usually ignored for this format; metadata toggle may still apply."
            )

        if self._export_quality is not None:
            self._export_quality.setEnabled(lossy)

        if self._export_quality_hint is not None:
            if lossy:
                self._export_quality_hint.setText(
                    "Tip: for web sharing, 70-85 is smaller; 90-100 keeps more detail."
                )
            else:
                self._export_quality_hint.setText(
                    "For PNG/GIF/BMP/TIFF, use cleanup/detail/transparency controls for visible quality; this slider has little effect."
                )

    def _sync_controls_from_asset(self, asset: object) -> None:
        has_asset = asset is not None and getattr(asset, "edit_state", None) is not None
        self._set_bound_controls_enabled(has_asset)
        if not has_asset:
            return

        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        if settings is None:
            return

        self._suspend_setting_events = True
        try:
            # Pixel
            if self._resize_percent is not None:
                self._resize_percent.setValue(float(getattr(settings.pixel, "resize_percent", 100.0)))
            if self._dpi is not None:
                self._dpi.setValue(int(getattr(settings.pixel, "dpi", 72)))
            if self._pixel_snap is not None:
                self._pixel_snap.setChecked(bool(getattr(settings.pixel, "pixel_snap", False)))
            if self._target_width is not None:
                target_w = getattr(settings.pixel, "width", None)
                self._target_width.setValue(int(target_w) if target_w is not None else 0)
            if self._target_height is not None:
                target_h = getattr(settings.pixel, "height", None)
                self._target_height.setValue(int(target_h) if target_h is not None else 0)
            if self._scale_method is not None:
                current_method = getattr(settings.pixel, "scale_method", ScaleMethod.LANCZOS)
                for idx in range(self._scale_method.count()):
                    if self._scale_method.itemData(idx) == current_method:
                        self._scale_method.setCurrentIndex(idx)
                        break
            if self._resize_preset_combo is not None:
                self._resize_preset_combo.setCurrentIndex(0)

            # Color
            if self._brightness is not None:
                self._brightness.setValue(float(getattr(settings.color, "brightness", 0.0)))
            if self._contrast is not None:
                self._contrast.setValue(float(getattr(settings.color, "contrast", 0.0)))
            if self._saturation is not None:
                self._saturation.setValue(float(getattr(settings.color, "saturation", 0.0)))
            if self._temperature is not None:
                self._temperature.setValue(float(getattr(settings.color, "temperature", 0.0)))
            if self._gamma is not None:
                self._gamma.setValue(float(getattr(settings.color, "gamma", 1.0)))

            # Detail
            if self._sharpen_amount is not None:
                self._sharpen_amount.setValue(float(getattr(settings.detail, "sharpen_amount", 0.0)))
            if self._sharpen_radius is not None:
                self._sharpen_radius.setValue(float(getattr(settings.detail, "sharpen_radius", 0.0)))
            if self._sharpen_threshold is not None:
                self._sharpen_threshold.setValue(float(getattr(settings.detail, "sharpen_threshold", 0.0)))
            if self._clarity is not None:
                self._clarity.setValue(float(getattr(settings.detail, "clarity", 0.0)))
            if self._texture is not None:
                self._texture.setValue(float(getattr(settings.detail, "texture", 0.0)))

            # Cleanup
            if self._denoise is not None:
                self._denoise.setValue(float(getattr(settings.cleanup, "denoise", 0.0)))
            if self._artifact_removal is not None:
                self._artifact_removal.setValue(float(getattr(settings.cleanup, "artifact_removal", 0.0)))
            if self._halo_cleanup is not None:
                self._halo_cleanup.setValue(float(getattr(settings.cleanup, "halo_cleanup", 0.0)))
            if self._banding_removal is not None:
                self._banding_removal.setValue(float(getattr(settings.cleanup, "banding_removal", 0.0)))

            # Edges
            if self._edge_antialias is not None:
                self._edge_antialias.setValue(float(getattr(settings.edges, "antialias", 0.0)))
            if self._edge_refine is not None:
                self._edge_refine.setValue(float(getattr(settings.edges, "edge_refine", 0.0)))
            if self._edge_grow_shrink is not None:
                self._edge_grow_shrink.setValue(float(getattr(settings.edges, "grow_shrink_px", 0.0)))
            if self._edge_feather is not None:
                self._edge_feather.setValue(float(getattr(settings.edges, "feather_px", 0.0)))

            # Transparency
            if self._white_bg_mode is not None:
                remove_white_bg = bool(getattr(settings.alpha, "remove_white_bg", False))
                self._white_bg_mode.setCurrentIndex(1 if remove_white_bg else 0)
            if self._alpha_smooth is not None:
                self._alpha_smooth.setValue(float(getattr(settings.alpha, "alpha_smooth", 0.0)))
            if self._matte_fix is not None:
                self._matte_fix.setValue(float(getattr(settings.alpha, "matte_fix", 0.0)))
            if self._alpha_threshold is not None:
                self._alpha_threshold.setValue(int(getattr(settings.alpha, "alpha_threshold", 0)))

            # AI
            if self._upscale_factor is not None:
                self._upscale_factor.setValue(float(getattr(settings.ai, "upscale_factor", 1.0)))
            if self._ai_deblur is not None:
                self._ai_deblur.setValue(float(getattr(settings.ai, "deblur_strength", 0.0)))
            if self._ai_detail_reconstruct is not None:
                self._ai_detail_reconstruct.setValue(float(getattr(settings.ai, "detail_reconstruct", 0.0)))
            if self._ai_bg_remove is not None:
                self._ai_bg_remove.setValue(float(getattr(settings.ai, "bg_remove_strength", 0.0)))

            # GIF
            if self._frame_delay is not None:
                self._frame_delay.setValue(int(getattr(settings.gif, "frame_delay_ms", 100)))
            if self._gif_dither is not None:
                self._gif_dither.setValue(float(getattr(settings.gif, "dither_strength", 0.0)))
            if self._gif_loop is not None:
                self._gif_loop.setChecked(bool(getattr(settings.gif, "loop", True)))
            if self._gif_palette_size is not None:
                self._gif_palette_size.setValue(int(getattr(settings.gif, "palette_size", 256)))
            if self._gif_frame_optimize is not None:
                self._gif_frame_optimize.setChecked(bool(getattr(settings.gif, "frame_optimize", True)))

            # Export + expert
            if self._export_profile is not None:
                current_profile = getattr(settings.export, "export_profile", ExportProfile.WEB)
                for idx in range(self._export_profile.count()):
                    if self._export_profile.itemData(idx) == current_profile:
                        self._export_profile.setCurrentIndex(idx)
                        break
            if self._export_format is not None:
                current_format = getattr(settings.export, "format", ExportFormat.AUTO)
                for idx in range(self._export_format.count()):
                    if self._export_format.itemData(idx) == current_format:
                        self._export_format.setCurrentIndex(idx)
                        break
            if self._export_quality is not None:
                self._export_quality.setValue(int(getattr(settings.export, "quality", 90)))
            if self._strip_metadata is not None:
                self._strip_metadata.setChecked(bool(getattr(settings.export, "strip_metadata", True)))
            if self._compression_level is not None:
                self._compression_level.setValue(int(getattr(settings.export, "compression_level", 6)))
            if self._chroma_subsampling is not None:
                current = getattr(settings.export, "chroma_subsampling", ChromaSubsampling.AUTO)
                for idx in range(self._chroma_subsampling.count()):
                    if self._chroma_subsampling.itemData(idx) == current:
                        self._chroma_subsampling.setCurrentIndex(idx)
                        break
            if self._palette_limit is not None:
                palette_value = getattr(settings.export, "palette_limit", None)
                self._palette_limit.setValue(int(palette_value) if palette_value is not None else 0)
            if self._ico_sizes is not None:
                sizes = getattr(settings.export, "ico_sizes", None)
                if not isinstance(sizes, list) or not sizes:
                    sizes = [16, 32, 48, 64, 128, 256]
                self._ico_sizes.setText(", ".join(str(max(1, int(value))) for value in sizes))
            if self._resize_percent is not None:
                self._last_resize_percent_for_dpi_sync = float(self._resize_percent.value())
            if self._dpi is not None:
                self._last_dpi_for_resize_sync = int(self._dpi.value())
        finally:
            self._suspend_setting_events = False

    def _set_bound_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._resize_percent,
            self._dpi,
            self._pixel_snap,
            self._target_width,
            self._target_height,
            self._scale_method,
            self._brightness,
            self._contrast,
            self._saturation,
            self._temperature,
            self._gamma,
            self._sharpen_amount,
            self._sharpen_radius,
            self._sharpen_threshold,
            self._clarity,
            self._texture,
            self._denoise,
            self._artifact_removal,
            self._halo_cleanup,
            self._banding_removal,
            self._edge_antialias,
            self._edge_refine,
            self._edge_grow_shrink,
            self._edge_feather,
            self._white_bg_mode,
            self._alpha_smooth,
            self._matte_fix,
            self._alpha_threshold,
            self._upscale_factor,
            self._ai_deblur,
            self._ai_detail_reconstruct,
            self._ai_bg_remove,
            self._frame_delay,
            self._gif_dither,
            self._gif_loop,
            self._gif_palette_size,
            self._gif_frame_optimize,
            self._export_profile,
            self._export_format,
            self._export_quality,
            self._strip_metadata,
            self._compression_level,
            self._chroma_subsampling,
            self._palette_limit,
            self._ico_sizes,
            self._open_encoding_window_btn,
        ):
            if widget is not None:
                widget.setEnabled(bool(enabled))

        if self._resize_preset_combo is not None:
            self._resize_preset_combo.setEnabled(bool(enabled))
        if self._resize_preset_apply is not None:
            self._resize_preset_apply.setEnabled(bool(enabled))
        if self._reset_current_defaults_btn is not None:
            self._reset_current_defaults_btn.setEnabled(bool(enabled))

    def _update_setting(self, group_name: str, field_name: str, value: Any) -> None:
        if self._suspend_setting_events or self._ui_state is None:
            return
        asset = self._ui_state.active_asset
        if asset is None:
            return

        settings = getattr(asset.edit_state, "settings", None)
        if settings is None:
            return
        group = getattr(settings, group_name, None)
        if group is None or not hasattr(group, field_name):
            return

        current = getattr(group, field_name)
        if current == value:
            return
        setattr(group, field_name, value)

        if bool(getattr(asset.edit_state, "auto_apply_light", False)):
            self._ui_state.request_light_preview()

    def _on_white_bg_mode_changed(self, _index: int) -> None:
        if self._white_bg_mode is None:
            return
        self._update_setting("alpha", "remove_white_bg", bool(self._white_bg_mode.currentData()))

    def _on_chroma_subsampling_changed(self, _index: int) -> None:
        if self._chroma_subsampling is None:
            return
        value = self._chroma_subsampling.currentData()
        if isinstance(value, ChromaSubsampling):
            self._update_setting("export", "chroma_subsampling", value)

    def _on_export_profile_changed(self, _index: int) -> None:
        if self._suspend_setting_events or self._export_profile is None or self._ui_state is None:
            return
        value = self._export_profile.currentData()
        if isinstance(value, ExportProfile):
            self._ui_state.set_export_profile(value)
            self._update_export_controls_hint(self._ui_state.active_asset)

    def _on_export_format_changed(self, _index: int) -> None:
        if self._export_format is None:
            return
        value = self._export_format.currentData()
        if isinstance(value, ExportFormat):
            self._update_setting("export", "format", value)
            if self._ui_state is not None:
                self._update_export_controls_hint(self._ui_state.active_asset)

    def _on_palette_limit_changed(self, value: int) -> None:
        self._update_setting("export", "palette_limit", (None if int(value) <= 0 else int(value)))

    def _on_ico_sizes_changed(self) -> None:
        if self._ico_sizes is None:
            return
        raw = self._ico_sizes.text().strip()
        tokens = [token.strip() for token in raw.replace(";", ",").split(",")]
        parsed: list[int] = []
        for token in tokens:
            if not token:
                continue
            try:
                value = int(token)
            except Exception:
                continue
            if value <= 0:
                continue
            parsed.append(min(2048, value))

        normalized = sorted(set(parsed)) if parsed else [16, 32, 48, 64, 128, 256]
        self._ico_sizes.setText(", ".join(str(size) for size in normalized))
        self._update_setting("export", "ico_sizes", normalized)

    def _on_target_width_changed(self, value: int) -> None:
        self._update_setting("pixel", "width", (None if int(value) <= 0 else int(value)))

    def _on_target_height_changed(self, value: int) -> None:
        self._update_setting("pixel", "height", (None if int(value) <= 0 else int(value)))

    def _on_scale_method_changed(self, _index: int) -> None:
        if self._scale_method is None:
            return
        value = self._scale_method.currentData()
        if isinstance(value, ScaleMethod):
            self._update_setting("pixel", "scale_method", value)










