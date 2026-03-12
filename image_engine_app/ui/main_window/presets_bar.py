"""Preset dropdown bar for quick preset selection."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.common.state_bindings import EngineUIState


class PresetsBar(QFrame):
    """Horizontal preset strip with a single preset dropdown."""

    preset_clicked = Signal(str)

    DEFAULT_PRESETS = [
        "Pixel Clean Upscale",
        "Artifact Cleanup",
        "Photo Recover",
        "Edge Repair",
        "Web Quick Export",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._preset_combo = QComboBox(self)
        self._build_ui()
        self.set_presets(self.DEFAULT_PRESETS)

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        self.preset_clicked.connect(ui_state.request_preset)

    def set_presets(self, preset_names: list[str]) -> None:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw_name in preset_names:
            name = str(raw_name or "").strip()
            if (not name) or (name in seen):
                continue
            seen.add(name)
            ordered.append(name)

        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem("Choose preset...", None)
        for name in ordered:
            self._preset_combo.addItem(name, name)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.setEnabled(bool(ordered))
        self._preset_combo.blockSignals(False)

    def _on_preset_selected(self, _index: int) -> None:
        name = self._preset_combo.currentData()
        if isinstance(name, str) and name:
            self.preset_clicked.emit(name)

        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.blockSignals(False)

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { border:1px solid #bfd2d4; border-radius:8px; background:#ffffff; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        label = QLabel("Presets", self)
        label.setStyleSheet("font-weight:600; color:#0f3338;")
        layout.addWidget(label)

        self._preset_combo.setMinimumWidth(240)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        layout.addWidget(self._preset_combo, 0)
        layout.addStretch(1)

