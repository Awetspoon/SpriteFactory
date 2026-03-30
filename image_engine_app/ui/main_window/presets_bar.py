"""Compact quick-preset picker for the main shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from image_engine_app.ui.common.state_bindings import EngineUIState


class PresetsBar(QWidget):
    """Compact quick preset control for the main toolbar."""

    preset_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._title_label = QLabel("Quick Preset", self)
        self._preset_combo = QComboBox(self)
        self._context_hint = ""
        self._build_ui()
        self.set_presets([])

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        self.preset_clicked.connect(ui_state.request_preset)

    def set_presets(self, preset_names: list[object]) -> None:
        ordered: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for raw_name in preset_names:
            name = str(getattr(raw_name, "name", raw_name) or "").strip()
            if (not name) or (name in seen):
                continue
            seen.add(name)
            label = str(getattr(raw_name, "label", name) or name).strip() or name
            tooltip = str(getattr(raw_name, "scope_text", "") or "").strip()
            ordered.append((name, label, tooltip))

        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem("Choose preset...", None)
        for name, label, tooltip in ordered:
            self._preset_combo.addItem(label, name)
            item_index = self._preset_combo.count() - 1
            if tooltip:
                self._preset_combo.setItemData(item_index, tooltip, Qt.ItemDataRole.ToolTipRole)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.setEnabled(bool(ordered))
        self._preset_combo.blockSignals(False)

    def set_context_hint(self, text: str) -> None:
        hint = str(text or "").strip()
        self._context_hint = hint
        tooltip = hint or "Apply a compatible quick preset to the active asset."
        self.setToolTip(tooltip)
        self._title_label.setToolTip(tooltip)
        self._preset_combo.setToolTip(tooltip)

    def _on_preset_selected(self, _index: int) -> None:
        name = self._preset_combo.currentData()
        if isinstance(name, str) and name:
            self.preset_clicked.emit(name)

        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.blockSignals(False)

    def _build_ui(self) -> None:
        self.setObjectName("toolbarPresetStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._title_label.setObjectName("toolbarLabel")
        layout.addWidget(self._title_label, 0)

        self._preset_combo.setMinimumWidth(0)
        self._preset_combo.setMaximumWidth(220)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        layout.addWidget(self._preset_combo, 1)
        self.set_context_hint("")


