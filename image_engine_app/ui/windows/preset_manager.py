"""Preset manager dialog (create/edit/save user presets)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from engine.models import EditMode, PresetModel


@dataclass
class _PresetDraft:
    name: str = ""
    description: str = ""
    applies_to_formats: list[str] | None = None
    applies_to_tags: list[str] | None = None
    settings_delta_text: str = "{}"
    uses_heavy_tools: bool = False
    requires_apply: bool = False
    mode_min: str = EditMode.SIMPLE.value


class PresetManagerDialog(QDialog):
    """UI for managing user presets.

    Built-in presets are shown but treated as read-only; saving edits creates/overrides
    a user preset entry.
    """

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Preset Manager")
        self.resize(980, 620)

        self._list = QListWidget(self)
        self._name = QLineEdit(self)
        self._desc = QLineEdit(self)
        self._formats = QLineEdit(self)
        self._tags = QLineEdit(self)
        self._mode_min = QComboBox(self)
        self._uses_heavy = QCheckBox("Uses heavy tools", self)
        self._requires_apply = QCheckBox("Requires Apply", self)
        self._delta = QPlainTextEdit(self)

        self._btn_new = QPushButton("New", self)
        self._btn_duplicate = QPushButton("Duplicate", self)
        self._btn_delete = QPushButton("Delete", self)
        self._btn_save = QPushButton("Save", self)
        self._btn_close = QPushButton("Close", self)

        self._build_ui()
        self._wire()
        self.refresh_from_controller()

    def refresh_from_controller(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()

        for preset in self._controller.list_presets():
            label = preset.name
            if self._controller.is_user_preset(preset.name):
                label = f"{label}  (User)"
            else:
                label = f"{label}  (System)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, preset.name)
            self._list.addItem(item)

        self._list.blockSignals(False)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
            self._load_selected_into_form()
        else:
            self._load_draft_into_form(_PresetDraft())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Create, edit, and save custom presets. Built-in presets are shown as System.")
        header.setWordWrap(True)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(QLabel("Presets"))
        left_layout.addWidget(self._list, 1)

        left_buttons = QHBoxLayout()
        left_buttons.addWidget(self._btn_new)
        left_buttons.addWidget(self._btn_duplicate)
        left_buttons.addWidget(self._btn_delete)
        left_buttons.addStretch(1)
        left_layout.addLayout(left_buttons)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

        form.addRow("Name", self._name)
        form.addRow("Description", self._desc)
        form.addRow("Applies to formats", self._formats)
        form.addRow("Applies to tags", self._tags)

        for mode in EditMode:
            self._mode_min.addItem(mode.value.title(), userData=mode.value)
        form.addRow("Min mode", self._mode_min)
        form.addRow("", self._uses_heavy)
        form.addRow("", self._requires_apply)

        right_layout.addLayout(form)

        right_layout.addWidget(QLabel("Settings delta (JSON)", self))
        self._delta.setPlaceholderText('{"cleanup": {"denoise": 0.2}, "export": {"format": "png"}}')
        self._delta.setTabStopDistance(28)
        right_layout.addWidget(self._delta, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self._btn_save)
        footer.addWidget(self._btn_close)
        right_layout.addLayout(footer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 640])
        layout.addWidget(splitter, 1)

    def _wire(self) -> None:
        self._btn_close.clicked.connect(self.close)
        self._btn_new.clicked.connect(self._new_preset)
        self._btn_duplicate.clicked.connect(self._duplicate_selected)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_save.clicked.connect(self._save_current)
        self._list.currentItemChanged.connect(lambda *_args: self._load_selected_into_form())

    def _selected_preset_name(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return str(raw) if raw else None

    def _new_preset(self) -> None:
        self._load_draft_into_form(_PresetDraft())
        self._name.setFocus()

    def _duplicate_selected(self) -> None:
        selected = self._selected_preset_name()
        if not selected:
            return
        base = self._controller.get_preset(selected)
        draft = _PresetDraft(
            name=f"{base.name} Copy",
            description=base.description,
            applies_to_formats=list(base.applies_to_formats or []),
            applies_to_tags=list(base.applies_to_tags or []),
            settings_delta_text=json.dumps(base.settings_delta or {}, indent=2, sort_keys=True),
            uses_heavy_tools=bool(base.uses_heavy_tools),
            requires_apply=bool(base.requires_apply),
            mode_min=base.mode_min.value,
        )
        self._load_draft_into_form(draft)

    def _delete_selected(self) -> None:
        selected = self._selected_preset_name()
        if not selected:
            return
        if not self._controller.is_user_preset(selected):
            QMessageBox.information(self, "Cannot delete", "System presets cannot be deleted.")
            return
        confirm = QMessageBox.question(
            self,
            "Delete preset",
            f"Delete user preset '{selected}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._controller.delete_user_preset(selected)
        self.refresh_from_controller()

    def _save_current(self) -> None:
        try:
            preset = self._read_form_as_preset()
            self._controller.upsert_user_preset(preset)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.refresh_from_controller()
        # Re-select the saved preset.
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == preset.name:
                self._list.setCurrentRow(row)
                break

    def _read_form_as_preset(self) -> PresetModel:
        name = (self._name.text() or "").strip()
        if not name:
            raise ValueError("Preset name cannot be empty")

        desc = (self._desc.text() or "").strip()
        formats = [p.strip() for p in (self._formats.text() or "").split(",") if p.strip()]
        tags = [p.strip() for p in (self._tags.text() or "").split(",") if p.strip()]

        mode_value = self._mode_min.currentData()
        mode_min = EditMode(str(mode_value))

        raw_delta = self._delta.toPlainText().strip() or "{}"
        try:
            delta_obj = json.loads(raw_delta)
        except Exception as exc:
            raise ValueError(f"Settings delta must be valid JSON: {exc}") from exc
        if not isinstance(delta_obj, dict):
            raise ValueError("Settings delta JSON must be an object (dict)")

        preset = PresetModel(
            name=name,
            description=desc,
            applies_to_formats=formats or ["*"],
            applies_to_tags=tags or ["*"],
            settings_delta=delta_obj,
            uses_heavy_tools=bool(self._uses_heavy.isChecked()),
            requires_apply=bool(self._requires_apply.isChecked()),
            mode_min=mode_min,
        )
        return preset

    def _load_selected_into_form(self) -> None:
        selected = self._selected_preset_name()
        if not selected:
            self._load_draft_into_form(_PresetDraft())
            return
        preset = self._controller.get_preset(selected)
        draft = _PresetDraft(
            name=preset.name,
            description=preset.description,
            applies_to_formats=list(preset.applies_to_formats or []),
            applies_to_tags=list(preset.applies_to_tags or []),
            settings_delta_text=json.dumps(preset.settings_delta or {}, indent=2, sort_keys=True),
            uses_heavy_tools=bool(preset.uses_heavy_tools),
            requires_apply=bool(preset.requires_apply),
            mode_min=preset.mode_min.value,
        )
        self._load_draft_into_form(draft)

        # Delete button only for user presets.
        self._btn_delete.setEnabled(bool(self._controller.is_user_preset(selected)))

    def _load_draft_into_form(self, draft: _PresetDraft) -> None:
        self._name.setText(draft.name)
        self._desc.setText(draft.description)
        self._formats.setText(", ".join(draft.applies_to_formats or []))
        self._tags.setText(", ".join(draft.applies_to_tags or []))
        self._delta.setPlainText(draft.settings_delta_text or "{}")
        self._uses_heavy.setChecked(bool(draft.uses_heavy_tools))
        self._requires_apply.setChecked(bool(draft.requires_apply))

        # Select mode
        for idx in range(self._mode_min.count()):
            if self._mode_min.itemData(idx) == draft.mode_min:
                self._mode_min.setCurrentIndex(idx)
                break

        self._btn_delete.setEnabled(False)
