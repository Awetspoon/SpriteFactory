"""Preset manager built around reusable control changes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.models import AssetRecord, EditMode, PresetModel
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY


@dataclass
class _PresetDraft:
    name: str = ""
    description: str = ""
    applies_to_formats: list[str] | None = None
    applies_to_tags: list[str] | None = None
    settings_delta_text: str = "{}"
    uses_heavy_tools: bool = False
    requires_apply: bool = False


class PresetManagerDialog(QDialog):
    """Create user presets from controls and manage system templates."""

    presets_changed = Signal()

    def __init__(
        self,
        controller,
        parent: QWidget | None = None,
        *,
        active_asset_provider: Callable[[], AssetRecord | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._active_asset_provider = active_asset_provider or (lambda: None)
        self.setObjectName("presetManagerDialog")
        self.setWindowTitle("Preset Manager")
        self.resize(980, 640)
        self.setMinimumSize(820, 560)

        self._list = QListWidget(self)
        self._list.setObjectName("shellListPanel")
        self._name = QLineEdit(self)
        self._desc = QLineEdit(self)
        self._formats = QLineEdit(self)
        self._tags = QLineEdit(self)
        self._uses_heavy = QCheckBox("Uses heavy processing", self)
        self._requires_apply = QCheckBox("Requires Apply", self)
        self._delta = QPlainTextEdit(self)

        self._preset_kind = QLabel("No preset selected", self)
        self._preset_kind.setObjectName("shellBadgeWarm")
        self._scope_hint = QLabel(self)
        self._scope_hint.setObjectName("shellHint")
        self._scope_hint.setWordWrap(True)
        self._save_hint = QLabel(self)
        self._save_hint.setObjectName("shellHint")
        self._save_hint.setWordWrap(True)
        self._capture_status = QLabel(self)
        self._capture_status.setObjectName("shellHint")
        self._capture_status.setWordWrap(True)

        self._btn_new = QPushButton("New from Active", self)
        self._btn_duplicate = QPushButton("Duplicate", self)
        self._btn_delete = QPushButton("Delete", self)
        self._btn_capture = QPushButton("Use Active Controls", self)
        self._btn_capture.setObjectName("shellPrimaryAction")
        self._btn_format_json = QPushButton("Format JSON", self)
        self._btn_save = QPushButton("Save Preset", self)
        self._btn_save.setObjectName("shellPrimaryAction")
        self._btn_close = QPushButton("Close", self)

        self._advanced_toggle = QToolButton(self)
        self._advanced_toggle.setText("Advanced")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._advanced_panel = QFrame(self)
        self._advanced_panel.setObjectName("presetManagerCard")

        self._build_ui()
        self._wire()
        self.refresh_from_controller()

    def refresh_from_controller(self) -> None:
        selected_name = self._selected_preset_name()
        self._list.blockSignals(True)
        self._list.clear()

        selected_row = -1
        for row, entry in enumerate(self._controller.available_preset_entries()):
            preset = self._controller.get_preset(entry.name)
            source = "User" if self._controller.is_user_preset(preset.name) else "System"
            item = QListWidgetItem(f"{entry.label}  ({source})")
            item.setData(Qt.ItemDataRole.UserRole, preset.name)
            self._list.addItem(item)
            if preset.name == selected_name:
                selected_row = row

        self._list.blockSignals(False)
        if self._list.count() > 0:
            self._list.setCurrentRow(selected_row if selected_row >= 0 else 0)
            self._load_selected_into_form()
        else:
            self._load_draft_into_form(_PresetDraft())
        self._refresh_active_asset_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
        )
        layout.setSpacing(SHELL_GEOMETRY.gap)

        header_card = QFrame(self)
        header_card.setObjectName("presetManagerCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
        )
        header_layout.setSpacing(4)
        title = QLabel("Preset Studio", header_card)
        title.setObjectName("shellTitle")
        intro = QLabel(
            "Save the active asset's control changes once, then reuse the same preset in Workspace or Batch.",
            header_card,
        )
        intro.setObjectName("shellSubtitle")
        intro.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(intro)
        layout.addWidget(header_card)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setObjectName("presetManagerSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(SHELL_GEOMETRY.splitter_handle_width)

        left = QFrame(splitter)
        left.setObjectName("presetManagerCard")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
        )
        left_layout.setSpacing(SHELL_GEOMETRY.gap)
        left_layout.addWidget(QLabel("Preset Library", left))
        left_layout.addWidget(self._list, 1)

        left_buttons = QHBoxLayout()
        left_buttons.addWidget(self._btn_new)
        left_buttons.addWidget(self._btn_duplicate)
        left_buttons.addWidget(self._btn_delete)
        left_layout.addLayout(left_buttons)

        right = QFrame(splitter)
        right.setObjectName("presetManagerCard")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
        )
        right_layout.setSpacing(SHELL_GEOMETRY.gap)

        capture_card = QFrame(right)
        capture_card.setObjectName("presetManagerCard")
        capture_layout = QHBoxLayout(capture_card)
        capture_layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
        )
        capture_text = QVBoxLayout()
        capture_title = QLabel("Create from current controls", capture_card)
        capture_title.setObjectName("shellTitle")
        capture_text.addWidget(capture_title)
        capture_text.addWidget(self._capture_status)
        capture_layout.addLayout(capture_text, 1)
        capture_layout.addWidget(self._btn_capture)
        right_layout.addWidget(capture_card)

        meta_row = QHBoxLayout()
        meta_row.addWidget(self._preset_kind)
        meta_row.addStretch(1)
        right_layout.addLayout(meta_row)
        right_layout.addWidget(self._scope_hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.addRow("Name", self._name)
        form.addRow("Description", self._desc)
        form.addRow("Formats", self._formats)
        form.addRow("Asset types", self._tags)
        right_layout.addLayout(form)
        right_layout.addWidget(self._save_hint)

        self._advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        right_layout.addWidget(self._advanced_toggle, 0, Qt.AlignmentFlag.AlignLeft)

        advanced_layout = QVBoxLayout(self._advanced_panel)
        advanced_layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.card_margin,
        )
        advanced_layout.setSpacing(SHELL_GEOMETRY.compact_gap)
        flags = QHBoxLayout()
        flags.addWidget(self._uses_heavy)
        flags.addWidget(self._requires_apply)
        flags.addStretch(1)
        advanced_layout.addLayout(flags)
        advanced_layout.addWidget(QLabel("Captured settings (JSON)", self._advanced_panel))
        self._delta.setPlaceholderText('{"cleanup": {"denoise": 0.2}}')
        self._delta.setTabStopDistance(28)
        advanced_layout.addWidget(self._delta, 1)
        json_tools = QHBoxLayout()
        json_tools.addWidget(self._btn_format_json)
        json_tools.addStretch(1)
        advanced_layout.addLayout(json_tools)
        self._advanced_panel.setVisible(False)
        right_layout.addWidget(self._advanced_panel, 1)
        right_layout.addStretch(1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self._btn_save)
        footer.addWidget(self._btn_close)
        right_layout.addLayout(footer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 650])
        layout.addWidget(splitter, 1)

    def _wire(self) -> None:
        self._btn_close.clicked.connect(self.close)
        self._btn_new.clicked.connect(self._new_preset)
        self._btn_duplicate.clicked.connect(self._duplicate_selected)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_capture.clicked.connect(self._capture_active_controls)
        self._btn_format_json.clicked.connect(self._format_delta_json)
        self._btn_save.clicked.connect(self._save_current)
        self._advanced_toggle.toggled.connect(self._set_advanced_visible)
        self._list.currentItemChanged.connect(lambda *_args: self._load_selected_into_form())

    def _active_asset(self) -> AssetRecord | None:
        try:
            return self._active_asset_provider()
        except Exception:
            return None

    def _selected_preset_name(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return str(raw) if raw else None

    def _new_preset(self) -> None:
        self._list.clearSelection()
        self._list.setCurrentItem(None)
        self._load_draft_into_form(_PresetDraft())
        if self._active_asset() is not None:
            self._capture_active_controls(fill_identity=True)
        self._name.setFocus()

    def _duplicate_selected(self) -> None:
        selected = self._selected_preset_name()
        if not selected:
            return
        base = self._controller.get_preset(selected)
        self._load_draft_into_form(
            _PresetDraft(
                name=f"{base.name} Copy",
                description=base.description,
                applies_to_formats=list(base.applies_to_formats or []),
                applies_to_tags=list(base.applies_to_tags or []),
                settings_delta_text=json.dumps(base.settings_delta or {}, indent=2, sort_keys=True),
                uses_heavy_tools=bool(base.uses_heavy_tools),
                requires_apply=bool(base.requires_apply),
            )
        )

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
        self.presets_changed.emit()
        self.refresh_from_controller()

    def _capture_active_controls(self, _checked: bool = False, *, fill_identity: bool = False) -> None:
        asset = self._active_asset()
        if asset is None:
            self._capture_status.setText("Select an asset in Workspace before capturing controls.")
            return

        captured = self._controller.capture_preset_controls(asset)
        if fill_identity and not self._name.text().strip():
            stem = Path(asset.original_name or "Custom").stem.strip() or "Custom"
            self._name.setText(f"{stem} Polish")
        if fill_identity and not self._desc.text().strip():
            self._desc.setText("Control adjustments captured from the active asset")

        self._formats.setText(", ".join(captured.applies_to_formats))
        self._tags.setText(", ".join(captured.applies_to_tags))
        self._delta.setPlainText(json.dumps(captured.settings_delta, indent=2, sort_keys=True))
        self._uses_heavy.setChecked(captured.uses_heavy_tools)
        self._requires_apply.setChecked(captured.requires_apply)
        self._preset_kind.setText("New user preset")
        self._btn_delete.setEnabled(False)
        self._refresh_delta_summary()

    def _save_current(self) -> None:
        try:
            preset = self._read_form_as_preset()
            self._controller.upsert_user_preset(preset)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        self.presets_changed.emit()
        self.refresh_from_controller()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == preset.name:
                self._list.setCurrentRow(row)
                break

    def _format_delta_json(self) -> None:
        try:
            parsed = json.loads(self._delta.toPlainText().strip() or "{}")
        except Exception as exc:
            QMessageBox.critical(self, "Format failed", f"Captured settings must be valid JSON:\n{exc}")
            return
        self._delta.setPlainText(json.dumps(parsed, indent=2, sort_keys=True))
        self._refresh_delta_summary()

    def _read_form_as_preset(self) -> PresetModel:
        name = self._name.text().strip()
        if not name:
            raise ValueError("Preset name cannot be empty")

        formats = [part.strip() for part in self._formats.text().split(",") if part.strip()]
        tags = [part.strip() for part in self._tags.text().split(",") if part.strip()]
        try:
            delta = json.loads(self._delta.toPlainText().strip() or "{}")
        except Exception as exc:
            raise ValueError(f"Captured settings must be valid JSON: {exc}") from exc
        if not isinstance(delta, dict):
            raise ValueError("Captured settings must be a JSON object")
        if not delta:
            raise ValueError("No control changes were captured. Adjust a control first or duplicate a system preset.")

        return PresetModel(
            name=name,
            description=self._desc.text().strip(),
            applies_to_formats=formats or ["*"],
            applies_to_tags=tags or ["*"],
            settings_delta=delta,
            uses_heavy_tools=self._uses_heavy.isChecked(),
            requires_apply=self._requires_apply.isChecked(),
            mode_min=EditMode.ADVANCED,
        )

    def _load_selected_into_form(self) -> None:
        selected = self._selected_preset_name()
        if not selected:
            return
        preset = self._controller.get_preset(selected)
        self._load_draft_into_form(
            _PresetDraft(
                name=preset.name,
                description=preset.description,
                applies_to_formats=list(preset.applies_to_formats or []),
                applies_to_tags=list(preset.applies_to_tags or []),
                settings_delta_text=json.dumps(preset.settings_delta or {}, indent=2, sort_keys=True),
                uses_heavy_tools=bool(preset.uses_heavy_tools),
                requires_apply=bool(preset.requires_apply),
            )
        )
        is_user = self._controller.is_user_preset(selected)
        self._btn_delete.setEnabled(is_user)
        self._preset_kind.setText("User preset" if is_user else "System template")
        self._save_hint.setText(
            "Saving updates this user preset."
            if is_user
            else "Duplicate this template, or capture the active controls to create your own preset."
        )

    def _load_draft_into_form(self, draft: _PresetDraft) -> None:
        self._name.setText(draft.name)
        self._desc.setText(draft.description)
        self._formats.setText(", ".join(draft.applies_to_formats or []))
        self._tags.setText(", ".join(draft.applies_to_tags or []))
        self._delta.setPlainText(draft.settings_delta_text or "{}")
        self._uses_heavy.setChecked(draft.uses_heavy_tools)
        self._requires_apply.setChecked(draft.requires_apply)
        self._btn_delete.setEnabled(False)
        self._preset_kind.setText("New user preset")
        self._scope_hint.setText(
            "Formats and asset types are filled from the active asset. Advanced users can edit these scopes."
        )
        self._save_hint.setText("Only controls that differ from the detected asset baseline are saved.")
        self._refresh_delta_summary()

    def _refresh_active_asset_status(self) -> None:
        asset = self._active_asset()
        self._btn_capture.setEnabled(asset is not None)
        if asset is None:
            self._capture_status.setText("No active asset. Select one in Workspace to capture its control changes.")
            return
        self._capture_status.setText(f"Active: {asset.original_name or asset.id}")

    def _refresh_delta_summary(self) -> None:
        try:
            delta = json.loads(self._delta.toPlainText().strip() or "{}")
        except Exception:
            self._capture_status.setText("Advanced settings contain invalid JSON.")
            return
        groups = [str(group).replace("_", " ").title() for group in delta if isinstance(delta, dict)]
        if groups:
            self._capture_status.setText(f"Captured groups: {', '.join(groups)}")
        else:
            self._refresh_active_asset_status()

    def _set_advanced_visible(self, visible: bool) -> None:
        self._advanced_panel.setVisible(bool(visible))
        self._advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow)
