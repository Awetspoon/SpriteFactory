"""Bottom action bar with export controls and live size predictor display."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from image_engine_app.engine.models import ExportProfile
from image_engine_app.ui.common.icons import icon
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY
from image_engine_app.ui.common.state_bindings import EngineUIState


class ExportBar(QFrame):
    """Responsive bottom action bar for output and navigation."""

    browse_export_dir_requested = Signal()
    open_export_dir_requested = Signal()
    skip_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._layout: QGridLayout | None = None
        self._compact_layout: bool | None = None
        self._profile_label = QLabel("Profile", self)
        self._destination_label = QLabel("Export to", self)
        self._profile_combo = QComboBox(self)
        self._export_btn = QPushButton("Export", self)
        self._skip_btn = QPushButton("Skip", self)
        self._export_dir_field = QLineEdit(self)
        self._folder_menu_btn = QToolButton(self)
        self._size_label = QLabel("Estimate --", self)
        self._auto_next_toggle = QCheckBox("Auto-next", self)
        self._build_ui()

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        ui_state.export_prediction_changed.connect(self._size_label.setText)
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        self._on_active_asset_changed(ui_state.active_asset)

    def auto_next_after_export(self) -> bool:
        return bool(self._auto_next_toggle.isChecked())

    def export_directory(self) -> str | None:
        path_value = self._export_dir_field.text().strip()
        return path_value or None

    def set_export_directory(self, path: str | Path | None) -> None:
        path_value = str(path).strip() if path is not None else ""
        self._export_dir_field.setText(path_value)
        if path_value:
            self._export_dir_field.setToolTip(path_value)
        else:
            self._export_dir_field.setToolTip("No export folder selected")

    def _build_ui(self) -> None:
        self.setObjectName("workspaceExportCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QGridLayout(self)
        layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
        )
        layout.setHorizontalSpacing(SHELL_GEOMETRY.compact_gap)
        layout.setVerticalSpacing(4)
        self._layout = layout

        self._profile_label.setObjectName("shellSubtitle")
        for profile in ExportProfile:
            self._profile_combo.addItem(profile.value.replace("_", " ").title(), userData=profile.value)
        self._profile_combo.currentIndexChanged.connect(self._emit_profile_change)
        self._profile_combo.setFixedWidth(SHELL_GEOMETRY.export_profile_width)

        self._export_btn.setObjectName("shellPrimaryAction")
        self._export_btn.setIcon(icon("export"))
        self._export_btn.clicked.connect(self._request_export)

        self._skip_btn.setIcon(icon("skip"))
        self._skip_btn.setToolTip("Move to the next asset without exporting.")
        self._skip_btn.clicked.connect(self._request_skip)

        self._destination_label.setObjectName("shellSubtitle")
        self._export_dir_field.setReadOnly(True)
        self._export_dir_field.setPlaceholderText("Default exports folder")
        self._export_dir_field.setMinimumWidth(0)
        self._export_dir_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        folder_menu = QMenu(self._folder_menu_btn)
        folder_menu.addAction("Choose Folder", self.browse_export_dir_requested.emit)
        folder_menu.addAction("Open Folder", self.open_export_dir_requested.emit)
        self._folder_menu_btn.setObjectName("exportBarMenuAction")
        self._folder_menu_btn.setText("Folder")
        self._folder_menu_btn.setToolTip("Choose or open the export folder")
        self._folder_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._folder_menu_btn.setMenu(folder_menu)

        self._auto_next_toggle.setChecked(True)
        self._auto_next_toggle.setToolTip("After successful export, move to the next asset in workspace order.")

        self._size_label.setObjectName("exportSizeBadge")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_label.setMinimumHeight(24)
        self._size_label.setFixedWidth(SHELL_GEOMETRY.export_size_width)
        self._size_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._layout_controls(self.width())
        self._set_controls_enabled(False)

    def _layout_controls(self, width: int) -> None:
        layout = self._layout
        if layout is None:
            return
        compact = int(width) < SHELL_GEOMETRY.export_compact_width
        if compact == self._compact_layout:
            return
        self._compact_layout = compact

        widgets = (
            self._profile_label,
            self._profile_combo,
            self._export_btn,
            self._skip_btn,
            self._destination_label,
            self._export_dir_field,
            self._folder_menu_btn,
            self._auto_next_toggle,
            self._size_label,
        )
        for widget in widgets:
            layout.removeWidget(widget)
        for column in range(9):
            layout.setColumnStretch(column, 0)

        if compact:
            layout.addWidget(self._profile_label, 0, 0)
            layout.addWidget(self._profile_combo, 0, 1)
            layout.addWidget(self._export_btn, 0, 2)
            layout.addWidget(self._skip_btn, 0, 3)
            layout.addWidget(self._size_label, 0, 4)
            layout.addWidget(self._destination_label, 1, 0)
            layout.addWidget(self._export_dir_field, 1, 1, 1, 2)
            layout.addWidget(self._folder_menu_btn, 1, 3)
            layout.addWidget(self._auto_next_toggle, 1, 4)
            layout.setColumnStretch(1, 1)
        else:
            layout.addWidget(self._profile_label, 0, 0)
            layout.addWidget(self._profile_combo, 0, 1)
            layout.addWidget(self._export_btn, 0, 2)
            layout.addWidget(self._skip_btn, 0, 3)
            layout.addWidget(self._destination_label, 0, 4)
            layout.addWidget(self._export_dir_field, 0, 5)
            layout.addWidget(self._folder_menu_btn, 0, 6)
            layout.addWidget(self._auto_next_toggle, 0, 7)
            layout.addWidget(self._size_label, 0, 8)
            layout.setColumnStretch(5, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._layout_controls(event.size().width())

    def _set_controls_enabled(self, enabled: bool) -> None:
        has_asset = bool(enabled)
        self._profile_combo.setEnabled(has_asset)
        self._export_btn.setEnabled(has_asset)
        self._skip_btn.setEnabled(has_asset)
        self._export_dir_field.setEnabled(has_asset)
        self._folder_menu_btn.setEnabled(has_asset)
        self._auto_next_toggle.setEnabled(has_asset)

    def _request_export(self) -> None:
        if self._ui_state is None or self._ui_state.active_asset is None:
            return
        self._ui_state.request_export()

    def _request_skip(self) -> None:
        if self._ui_state is None or self._ui_state.active_asset is None:
            return
        self.skip_requested.emit()

    def _emit_profile_change(self) -> None:
        if self._ui_state is None:
            return
        value = self._profile_combo.currentData()
        if isinstance(value, str):
            self._ui_state.request_export_profile(value)

    def _on_active_asset_changed(self, asset: object) -> None:
        has_asset = asset is not None
        self._set_controls_enabled(has_asset)
        if not has_asset:
            self._size_label.setText("Estimate --")
            return

        export_settings = getattr(getattr(asset, "edit_state", None), "settings", None)
        export_group = getattr(export_settings, "export", None)
        profile_value = getattr(getattr(export_group, "export_profile", None), "value", None)
        if not isinstance(profile_value, str):
            return
        for idx in range(self._profile_combo.count()):
            if self._profile_combo.itemData(idx) == profile_value:
                self._profile_combo.blockSignals(True)
                self._profile_combo.setCurrentIndex(idx)
                self._profile_combo.blockSignals(False)
                break


