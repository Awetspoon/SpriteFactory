"""Scrollable settings panel with mode/format gating and core settings wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.models import (
    BackgroundRemovalMode,
    ChromaSubsampling,
    EditMode,
    ExportFormat,
    ExportProfile,
    ScaleMethod,
    normalize_background_removal_mode,
)
from image_engine_app.engine.analyze.background_scan import BackgroundScanResult, inspect_background_state
from image_engine_app.ui.common.state_bindings import EngineUIState
from image_engine_app.ui.main_window.settings_group_builders import settings_group_builders
from image_engine_app.ui.main_window.settings_panel_state import build_settings_panel_header_state


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


class _SettingsGroupNavigator(QFrame):
    """Stable section navigator + stacked pages for the settings panel."""

    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._pages: list[QWidget] = []
        self._titles: list[str] = []
        self._current_index = -1
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._stack = QStackedWidget(self)
        self._stack.setObjectName("settingsGroupStackPages")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        nav = QWidget(self)
        nav.setObjectName("settingsGroupNavRail")
        nav.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._nav_layout = QVBoxLayout(nav)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(6)
        self._nav_layout.addStretch(1)
        root.addWidget(nav, 0)
        root.addWidget(self._stack, 1)

    def addItem(self, page: QWidget, title: str) -> int:
        index = len(self._pages)
        button = QPushButton(title, self)
        button.setObjectName("settingsGroupNavButton")
        button.setCheckable(True)
        button.setAutoExclusive(False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(34)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setToolTip(title)
        button.clicked.connect(lambda _checked=False, index=index: self.setCurrentIndex(index))
        self._button_group.addButton(button, index)
        self._nav_layout.insertWidget(max(0, self._nav_layout.count() - 1), button)

        self._buttons.append(button)
        self._pages.append(page)
        self._titles.append(title)
        self._stack.addWidget(page)

        if self._current_index < 0:
            self.setCurrentIndex(0)
        return index

    def count(self) -> int:
        return len(self._pages)

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, index: int) -> None:
        if index < 0 or index >= len(self._pages):
            return
        self._current_index = index
        self._stack.setCurrentIndex(index)
        for button_index, button in enumerate(self._buttons):
            button.blockSignals(True)
            button.setChecked(button_index == index)
            button.blockSignals(False)
        self.currentChanged.emit(index)

    def itemText(self, index: int) -> str:
        if index < 0 or index >= len(self._titles):
            return ""
        return self._titles[index]

    def setItemText(self, index: int, text: str) -> None:
        if index < 0 or index >= len(self._titles):
            return
        normalized = str(text or "")
        self._titles[index] = normalized
        self._buttons[index].setText(normalized)

    def setItemToolTip(self, index: int, text: str) -> None:
        if index < 0 or index >= len(self._buttons):
            return
        self._buttons[index].setToolTip(str(text or ""))

    def setItemEnabled(self, index: int, enabled: bool) -> None:
        if index < 0 or index >= len(self._buttons):
            return
        self._buttons[index].setEnabled(bool(enabled))

    def setItemVisible(self, index: int, visible: bool) -> None:
        if index < 0 or index >= len(self._buttons):
            return
        self._buttons[index].setVisible(bool(visible))

    def widget(self, index: int) -> QWidget | None:
        if index < 0 or index >= len(self._pages):
            return None
        return self._pages[index]


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
        "Pixel and Resolution": "Real output size, DPI, target width/height, and scale style.",
        "Color and Light": "Brightness, contrast, color, temperature, and gamma.",
        "Detail": "Sharpening and fine-texture controls.",
        "Cleanup": "Noise, halo, artifact, and banding cleanup.",
        "Edges": "Edge softness, refine, feather, and grow/shrink.",
        "Transparency": "White/black cutout and alpha edge cleanup.",
        "AI Enhance": "Upscale, deblur, and reconstruction controls.",
        "GIF Controls": "Animation timing, palette, and GIF output tuning.",
        "Export": "Final output format, quality, and metadata settings.",
        "Expert Encoding": "Compression, chroma, palette, and icon size tuning.",
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
        self._toolbox = _SettingsGroupNavigator(self)
        self._filter_hint = QLabel("", self)
        self._header_title = QLabel(self)
        self._header_subtitle = QLabel(self)
        self._group_indices: dict[str, int] = {}
        self._group_specs_by_index: dict[int, _GroupSpec] = {}
        self._group_lock_labels_by_index: dict[int, QLabel] = {}
        self._group_controls_by_index: dict[int, QWidget] = {}
        self._current_mode = EditMode.SIMPLE.value
        self._asset_has_alpha = False
        self._asset_is_gif = False
        self._background_scan = BackgroundScanResult()
        self._visible_group_count = 0
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
        self._background_status: QLabel | None = None
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
        ui_state.background_removal_mode_changed.connect(self._on_background_removal_mode_changed)
        ui_state.export_profile_changed.connect(lambda _value: self._sync_controls_from_asset(ui_state.active_asset))
        self._on_mode_changed(ui_state.active_asset.edit_state.mode.value if ui_state.active_asset else EditMode.SIMPLE.value)
        self._on_active_asset_changed(ui_state.active_asset)

    def _build_ui(self) -> None:
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header_card = QFrame(container)
        header_card.setObjectName("settingsHeaderCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._header_title.setObjectName("shellTitle")
        title_row.addWidget(self._header_title, 1)

        reset_current_btn = QPushButton("Reset Edits", header_card)
        reset_current_btn.setObjectName("settingsResetButton")
        reset_current_btn.setAutoDefault(False)
        reset_current_btn.setToolTip("Reset only the active asset edits back to the original default state.")
        reset_current_btn.clicked.connect(self._emit_reset_current_defaults)
        self._reset_current_defaults_btn = reset_current_btn
        title_row.addWidget(reset_current_btn, 0)
        header_layout.addLayout(title_row)

        self._header_subtitle.setObjectName("shellSubtitle")
        self._header_subtitle.setWordWrap(True)
        header_layout.addWidget(self._header_subtitle)

        layout.addWidget(header_card)

        utility_row = QHBoxLayout()
        utility_row.setSpacing(6)

        self._search.setPlaceholderText("Filter sections...")
        self._search.textChanged.connect(lambda _text: self._apply_filters())
        utility_row.addWidget(self._search, 1)

        self._filter_hint.setObjectName("shellHint")
        self._filter_hint.setVisible(False)
        layout.addLayout(utility_row)
        layout.addWidget(self._filter_hint)

        self._toolbox.setObjectName("settingsGroupToolbox")
        self._toolbox.currentChanged.connect(self._on_toolbox_index_changed)
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
        self.setMinimumWidth(300)
        self._apply_filters()
        self._set_bound_controls_enabled(False)
        self._refresh_header_summary()

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
        widget.setMinimumWidth(122)
        widget.setValue(default)
        return widget

    @staticmethod
    def _apply_editor_width_defaults(parent: QWidget) -> None:
        for spin in parent.findChildren(QSpinBox):
            spin.setMinimumWidth(max(spin.minimumWidth(), 116))
        for dspin in parent.findChildren(QDoubleSpinBox):
            dspin.setMinimumWidth(max(dspin.minimumWidth(), 116))
        for combo in parent.findChildren(QComboBox):
            combo.setMinimumWidth(max(combo.minimumWidth(), 132))

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
        page.setObjectName("settingsGroupPage")
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        help_text = self.GROUP_HELP.get(spec.title, "")
        if help_text:
            help_label = QLabel(help_text, page)
            help_label.setObjectName("settingsHelpText")
            help_label.setWordWrap(True)
            vbox.addWidget(help_label)

        lock_label = QLabel("", page)
        lock_label.setObjectName("settingsLockLabel")
        lock_label.setWordWrap(True)
        lock_label.setVisible(False)
        vbox.addWidget(lock_label)

        controls_widget = QWidget(page)
        controls_widget.setObjectName("settingsGroupControls")
        form = QFormLayout(controls_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(5)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(5)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        builder = settings_group_builders(self).get(spec.title)
        if builder is not None:
            builder(form, page)

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
            f"QLabel {{ color:{fg}; background:{bg}; border:1px solid {border}; border-radius:10px; padding:7px 10px; }}"
        )

    def _emit_reset_current_defaults(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_global_reset()

    def _emit_open_encoding_window(self) -> None:
        self.open_encoding_window_requested.emit()

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
        self._refresh_header_summary()

    def _on_active_asset_changed(self, asset: object) -> None:
        if asset is None:
            self._asset_has_alpha = False
            self._asset_is_gif = False
            self._background_scan = BackgroundScanResult()
        else:
            caps = getattr(asset, "capabilities", None)
            self._asset_has_alpha = bool(getattr(caps, "has_alpha", False))
            fmt_value = getattr(getattr(asset, "format", None), "value", "")
            self._asset_is_gif = (fmt_value == "gif")
            self._background_scan = inspect_background_state(self._resolve_asset_inspection_path(asset))
        self._sync_controls_from_asset(asset)
        self._apply_filters()
        self._update_export_controls_hint(asset)
        self._refresh_header_summary()
        self._refresh_background_status(asset)

    def _apply_filters(self) -> None:
        query = self._search.text().strip().lower()
        visible_count = 0
        first_visible_index: int | None = None
        current_index = int(self._toolbox.currentIndex()) if self._toolbox.count() > 0 else -1
        current_still_visible = False
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
                reason = f"Hidden by section filter: {query!r}"
            elif not meets_mode:
                reason = f"Requires {spec.min_mode.title()} mode."
                lock_kind = "mode"
            elif spec.requires_alpha and not self._asset_has_alpha:
                reason = "Requires an image with transparency (alpha channel)."
                lock_kind = "alpha"
            elif spec.requires_gif and not self._asset_is_gif:
                reason = "Requires a GIF/animated asset."
                lock_kind = "gif"

            controls_widget = self._group_controls_by_index.get(idx)
            lock_label = self._group_lock_labels_by_index.get(idx)

            self._toolbox.setItemVisible(idx, bool(matches_query))
            self._toolbox.setItemEnabled(idx, bool(matches_query))

            if not matches_query:
                self._toolbox.setItemToolTip(idx, "")
                continue

            visible_count += 1
            if first_visible_index is None:
                first_visible_index = idx
            if idx == current_index:
                current_still_visible = True

            locked = bool(reason)
            self._toolbox.setItemText(idx, spec.title)
            self._toolbox.setItemToolTip(idx, "" if not locked else reason)

            if lock_label is not None:
                lock_label.setVisible(locked)
                if locked:
                    self._set_lock_label_message(lock_label, lock_kind=lock_kind, reason=reason)
            if controls_widget is not None:
                controls_widget.setEnabled(not locked)

        if (not current_still_visible) and first_visible_index is not None:
            self._toolbox.setCurrentIndex(first_visible_index)

        if query:
            self._filter_hint.setText(f"Showing {visible_count} matching section(s) for {query!r}.")
            self._filter_hint.setVisible(True)
        else:
            self._filter_hint.setText("")
            self._filter_hint.setVisible(False)
        self._visible_group_count = visible_count
        self._refresh_header_summary()

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
                mode_value = normalize_background_removal_mode(
                    getattr(settings.alpha, "background_removal_mode", None),
                    remove_white_bg=bool(getattr(settings.alpha, "remove_white_bg", False)),
                ).value
                for idx in range(self._white_bg_mode.count()):
                    if self._white_bg_mode.itemData(idx) == mode_value:
                        self._white_bg_mode.setCurrentIndex(idx)
                        break
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
        if self._suspend_setting_events or self._white_bg_mode is None:
            return
        mode_value = normalize_background_removal_mode(self._white_bg_mode.currentData()).value
        if self._ui_state is not None:
            self._ui_state.set_background_removal_mode(mode_value)
            return
        self._update_setting("alpha", "background_removal_mode", mode_value)
        self._update_setting("alpha", "remove_white_bg", mode_value == BackgroundRemovalMode.WHITE.value)

    def _on_background_removal_mode_changed(self, _mode_value: str) -> None:
        if self._ui_state is None:
            return
        self._sync_controls_from_asset(self._ui_state.active_asset)
        self._refresh_background_status(self._ui_state.active_asset)

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

    def _on_toolbox_index_changed(self, _index: int) -> None:
        self._queue_scroll_to_active_group()
        self._refresh_header_summary()

    def _queue_scroll_to_active_group(self) -> None:
        QTimer.singleShot(0, self._scroll_to_active_group)

    def _scroll_to_active_group(self) -> None:
        container = self.widget()
        current_index = int(self._toolbox.currentIndex()) if self._toolbox.count() > 0 else -1
        if container is None or current_index < 0:
            return
        scroll_bar = self.verticalScrollBar()
        target_point = self._toolbox.mapTo(container, QPoint(0, 0))
        target_value = max(0, int(target_point.y()) - 8)
        scroll_bar.setValue(min(scroll_bar.maximum(), target_value))

    def _refresh_header_summary(self) -> None:
        if self._header_title is None:
            return
        active_group_title = None
        current_index = int(self._toolbox.currentIndex()) if self._toolbox.count() > 0 else -1
        if current_index >= 0:
            active_group_title = self._toolbox.itemText(current_index)

        state = build_settings_panel_header_state(
            asset=(self._ui_state.active_asset if self._ui_state is not None else None),
            mode_value=self._current_mode,
            visible_group_count=self._visible_group_count,
            total_group_count=self._toolbox.count(),
            active_group_title=active_group_title,
            has_alpha=self._asset_has_alpha,
            is_gif=self._asset_is_gif,
        )

        self._header_title.setText(state.title_text)
        self._header_subtitle.setText(state.subtitle_text)

    @staticmethod
    def _resolve_asset_inspection_path(asset: object) -> Path | None:
        candidates = (
            getattr(asset, "cache_path", None),
            getattr(asset, "source_uri", None),
            getattr(asset, "derived_current_path", None),
            getattr(asset, "derived_final_path", None),
        )
        for raw in candidates:
            if not isinstance(raw, str) or not raw.strip():
                continue
            candidate = Path(raw)
            if candidate.exists():
                return candidate
        return None

    def _refresh_background_status(self, asset: object) -> None:
        if self._background_status is None:
            return

        if asset is None:
            self._background_status.setText(
                "Load an asset to see whether it already has transparency or a removable white/black edge background."
            )
            return

        mode_value = BackgroundRemovalMode.OFF
        settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        if settings is not None:
            mode_value = normalize_background_removal_mode(
                getattr(settings.alpha, "background_removal_mode", None),
                remove_white_bg=bool(getattr(settings.alpha, "remove_white_bg", False)),
            )

        scan = self._background_scan
        if not scan.can_inspect:
            message = "Could not inspect the source file. Use the checkerboard preview to verify whether transparency is already present."
        else:
            message = self._build_background_status_text(scan=scan, active_mode=mode_value, is_gif=self._asset_is_gif)

        self._background_status.setText(message)

    @staticmethod
    def _build_background_status_text(
        *,
        scan: BackgroundScanResult,
        active_mode: BackgroundRemovalMode,
        is_gif: bool,
    ) -> str:
        lead = ""
        if scan.has_transparent_pixels:
            lead = "Transparency already exists in the source."
        elif scan.recommended_mode is BackgroundRemovalMode.WHITE:
            lead = "A likely white edge background is still baked into the source."
        elif scan.recommended_mode is BackgroundRemovalMode.BLACK:
            lead = "A likely black edge background is still baked into the source."
        else:
            lead = "No clear white/black edge background was detected in the source."

        if active_mode is BackgroundRemovalMode.OFF:
            if scan.recommended_mode is BackgroundRemovalMode.WHITE:
                follow = "Try Remove white BG only if the checkerboard still shows a solid white backdrop."
            elif scan.recommended_mode is BackgroundRemovalMode.BLACK:
                follow = "Try Remove black BG only if the checkerboard still shows a solid black backdrop."
            elif scan.has_transparent_pixels:
                follow = "BG cutout is usually not needed unless you still see a solid edge backdrop."
            else:
                follow = "Leave BG cutout off unless the preview still shows a solid white or black backdrop."
        elif active_mode is BackgroundRemovalMode.WHITE:
            if scan.recommended_mode is BackgroundRemovalMode.WHITE:
                follow = "White cutout matches the scan."
            elif scan.recommended_mode is BackgroundRemovalMode.BLACK:
                follow = "White cutout does not match the scan and can punch holes in dark outlines."
            elif scan.has_transparent_pixels:
                follow = "White cutout is active even though transparency already exists, so light outlines can thin out."
            else:
                follow = "White cutout is active. Compare Current vs Final before export."
        else:
            if scan.recommended_mode is BackgroundRemovalMode.BLACK:
                follow = "Black cutout matches the scan."
            elif scan.recommended_mode is BackgroundRemovalMode.WHITE:
                follow = "Black cutout does not match the scan and can punch holes in dark sprite details."
            elif scan.has_transparent_pixels:
                follow = "Black cutout is active even though transparency already exists, so dark outlines can thin out."
            else:
                follow = "Black cutout is active. Compare Current vs Final before export."

        if is_gif:
            if active_mode is BackgroundRemovalMode.OFF:
                gif_note = "For GIFs, only turn cutout on when each frame really contains that baked background color."
            else:
                gif_note = "GIF cutout runs on every frame, so the wrong color choice can make edges shimmer or look broken."
            return f"{lead} {follow} {gif_note}"

        return f"{lead} {follow}"











