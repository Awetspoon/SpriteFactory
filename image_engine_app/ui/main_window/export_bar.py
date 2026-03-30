"""Bottom action bar with export controls and live size predictor display."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from image_engine_app.engine.models import ExportProfile
from image_engine_app.ui.common.icons import icon
from image_engine_app.ui.common.state_bindings import EngineUIState


class ExportBar(QFrame):
    """Fixed bottom action bar shell."""

    browse_export_dir_requested = Signal()
    open_export_dir_requested = Signal()
    skip_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._profile_combo = QComboBox(self)
        self._export_btn = QPushButton("Export", self)
        self._skip_btn = QPushButton("Skip", self)
        self._export_dir_field = QLineEdit(self)
        self._browse_btn = QToolButton(self)
        self._open_folder_btn = QToolButton(self)
        self._size_label = QLabel("Size --", self)
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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        profile_label = QLabel("Profile", self)
        profile_label.setObjectName("shellSubtitle")
        layout.addWidget(profile_label)
        for profile in ExportProfile:
            self._profile_combo.addItem(profile.value.replace("_", " ").title(), userData=profile.value)
        self._profile_combo.currentIndexChanged.connect(self._emit_profile_change)
        self._profile_combo.setMaximumWidth(104)
        layout.addWidget(self._profile_combo)

        self._export_btn.setObjectName("shellPrimaryAction")
        self._export_btn.setIcon(icon("export"))
        self._export_btn.clicked.connect(self._request_export)
        layout.addWidget(self._export_btn)

        self._skip_btn.setIcon(icon("skip"))
        self._skip_btn.setToolTip("Move to the next asset without exporting.")
        self._skip_btn.clicked.connect(self._request_skip)
        layout.addWidget(self._skip_btn)

        dest_label = QLabel("To", self)
        dest_label.setObjectName("shellSubtitle")
        layout.addWidget(dest_label)
        self._export_dir_field.setReadOnly(True)
        self._export_dir_field.setPlaceholderText("Default exports folder")
        self._export_dir_field.setMinimumWidth(0)
        self._export_dir_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._export_dir_field, 1)

        self._browse_btn.setText("Browse")
        self._browse_btn.setToolTip("Choose export folder")
        self._browse_btn.setAutoRaise(False)
        self._browse_btn.clicked.connect(self.browse_export_dir_requested.emit)
        layout.addWidget(self._browse_btn)

        self._open_folder_btn.setText("Open")
        self._open_folder_btn.clicked.connect(self.open_export_dir_requested.emit)
        self._open_folder_btn.setToolTip("Open the current export folder in File Explorer.")
        layout.addWidget(self._open_folder_btn)

        self._auto_next_toggle.setChecked(True)
        self._auto_next_toggle.setToolTip("After successful export, move to the next asset in workspace order.")
        layout.addWidget(self._auto_next_toggle)

        self._size_label.setObjectName("exportSizeBadge")
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._size_label.setMinimumHeight(24)
        self._size_label.setMinimumWidth(88)
        self._size_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._size_label)

        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool) -> None:
        has_asset = bool(enabled)
        self._profile_combo.setEnabled(has_asset)
        self._export_btn.setEnabled(has_asset)
        self._skip_btn.setEnabled(has_asset)
        self._export_dir_field.setEnabled(has_asset)
        self._browse_btn.setEnabled(has_asset)
        self._open_folder_btn.setEnabled(has_asset)
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
            self._ui_state.set_export_profile(value)

    def _on_active_asset_changed(self, asset: object) -> None:
        has_asset = asset is not None
        self._set_controls_enabled(has_asset)
        if not has_asset:
            self._size_label.setText("Size --")
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


