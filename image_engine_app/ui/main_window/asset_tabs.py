"""Workspace asset rail for multi-asset navigation in the main window."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY


@dataclass(frozen=True)
class AssetTabItem:
    """Minimal asset row data used to render the workspace rail."""

    asset_id: str
    label: str
    tooltip: str = ""
    pinned: bool = False


class WorkspaceAssetTabs(QFrame):
    """List-style asset navigator bound to session tab order and active asset state."""

    asset_selected = Signal(str)
    pin_active_requested = Signal(str)
    asset_close_requested = Signal(str)
    window_prev_requested = Signal()
    window_next_requested = Signal()
    window_section_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._asset_list = QListWidget(self)
        self._summary_label = QLabel(self)
        self._empty_import_card = QLabel(self)
        self._window_label = QLabel(self)
        self._window_section_combo = QComboBox(self)
        self._window_prev_button = QToolButton(self)
        self._window_next_button = QToolButton(self)
        self._actions_button = QToolButton(self)
        self._pin_action = None
        self._remove_action = None
        self._build_ui()

    def set_tabs(
        self,
        items: list[AssetTabItem],
        *,
        active_asset_id: str | None = None,
        total_count: int | None = None,
        window_start: int = 0,
        window_size: int = 100,
    ) -> None:
        """Replace workspace list contents and select the active asset if present."""

        self._asset_list.blockSignals(True)
        self._asset_list.clear()

        for item in items:
            row = QListWidgetItem(f"[P] {item.label}" if item.pinned else item.label)
            row.setData(Qt.ItemDataRole.UserRole, item.asset_id)
            row.setData(Qt.ItemDataRole.UserRole + 1, bool(item.pinned))
            row.setToolTip(item.tooltip or item.label)
            self._asset_list.addItem(row)

        if items:
            self._asset_list.setEnabled(True)
            self._asset_list.setVisible(True)
            self._empty_import_card.setVisible(False)
            total = int(total_count) if total_count is not None else len(items)
            hidden = max(0, total - len(items))
            size = max(1, int(window_size))
            start = max(0, min(int(window_start), max(0, total - 1)))
            end = min(total, start + len(items))
            pin_relevant = total > size

            self._actions_button.setEnabled(True)
            self._actions_button.setVisible(True)
            if self._pin_action is not None:
                self._pin_action.setEnabled(pin_relevant)
            if self._remove_action is not None:
                self._remove_action.setEnabled(True)

            summary = f"{total} asset(s) in workspace"
            if hidden > 0:
                summary += f" ({hidden} hidden for performance)"
            self._summary_label.setText(summary)

            if hidden > 0:
                self._window_label.setText("")
                self._window_label.setVisible(False)
                self._sync_section_combo(total=total, start=start, window_size=size)
            else:
                self._window_label.setText("")
                self._window_label.setVisible(False)
                self._window_section_combo.clear()
                self._window_section_combo.setVisible(False)

            self._set_window_nav_state(
                has_prev=(hidden > 0 and start > 0),
                has_next=(hidden > 0 and end < total),
                has_sections=(hidden > 0),
            )
        else:
            self._asset_list.setEnabled(False)
            self._asset_list.setVisible(False)
            self._empty_import_card.setVisible(True)
            self._actions_button.setEnabled(False)
            self._actions_button.setVisible(False)
            if self._pin_action is not None:
                self._pin_action.setEnabled(False)
            if self._remove_action is not None:
                self._remove_action.setEnabled(False)
            self._summary_label.setText("No assets in workspace.")
            self._window_label.setText("")
            self._window_label.setVisible(False)
            self._window_section_combo.clear()
            self._window_section_combo.setVisible(False)
            self._set_window_nav_state(has_prev=False, has_next=False, has_sections=False)

        selected = False
        if active_asset_id is not None:
            selected = self._select_asset_row(active_asset_id)
        if not selected and self._asset_list.count() > 0:
            self._asset_list.setCurrentRow(0)

        self._asset_list.blockSignals(False)
        self._update_pin_action_text()

    def set_active_asset(self, asset_id: str | None) -> None:
        """Set the current workspace selection by asset id."""

        if asset_id is None:
            return
        self._asset_list.blockSignals(True)
        self._select_asset_row(asset_id)
        self._asset_list.blockSignals(False)
        self._update_pin_action_text()

    def active_asset_id(self) -> str | None:
        """Return the currently selected asset id, if any."""

        return self._item_asset_id(self._asset_list.currentItem())

    def _build_ui(self) -> None:
        self.setObjectName("workspaceAssetTabsCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
        )
        outer.setSpacing(SHELL_GEOMETRY.compact_gap)

        title_row = QHBoxLayout()
        title_row.setSpacing(SHELL_GEOMETRY.gap)
        title = QLabel("Workspace", self)
        title.setObjectName("shellTitle")
        title_row.addWidget(title, 0)
        title_row.addStretch(1)
        outer.addLayout(title_row)

        self._summary_label.setObjectName("shellHint")
        self._summary_label.setWordWrap(True)
        outer.addWidget(self._summary_label)

        paging = QHBoxLayout()
        paging.setSpacing(SHELL_GEOMETRY.compact_gap)

        self._window_label.setObjectName("shellSubtitle")
        self._window_label.setVisible(False)
        paging.addWidget(self._window_label)

        self._window_section_combo.setObjectName("workspaceSectionCombo")
        self._window_section_combo.setFixedWidth(SHELL_GEOMETRY.workspace_section_width)
        self._window_section_combo.setVisible(False)
        self._window_section_combo.currentIndexChanged.connect(self._on_window_section_changed)
        paging.addWidget(self._window_section_combo, 0)

        self._window_prev_button.setObjectName("workspacePagerButton")
        self._window_prev_button.setText("‹")
        self._window_prev_button.setToolTip("Show previous workspace section")
        self._window_prev_button.setAutoRaise(False)
        self._window_prev_button.setFixedSize(
            SHELL_GEOMETRY.workspace_pager_size,
            SHELL_GEOMETRY.workspace_pager_size,
        )
        self._window_prev_button.setEnabled(False)
        self._window_prev_button.setVisible(False)
        self._window_prev_button.clicked.connect(self.window_prev_requested.emit)
        paging.addWidget(self._window_prev_button)

        self._window_next_button.setObjectName("workspacePagerButton")
        self._window_next_button.setText("›")
        self._window_next_button.setToolTip("Show next workspace section")
        self._window_next_button.setAutoRaise(False)
        self._window_next_button.setFixedSize(
            SHELL_GEOMETRY.workspace_pager_size,
            SHELL_GEOMETRY.workspace_pager_size,
        )
        self._window_next_button.setEnabled(False)
        self._window_next_button.setVisible(False)
        self._window_next_button.clicked.connect(self.window_next_requested.emit)
        paging.addWidget(self._window_next_button)

        self._actions_button.setObjectName("workspaceMoreButton")
        self._actions_button.setText("More")
        self._actions_button.setToolTip("Workspace actions")
        self._actions_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._actions_button.setEnabled(False)
        self._actions_button.setVisible(False)
        actions_menu = QMenu(self._actions_button)
        self._pin_action = actions_menu.addAction("Pin Active", self._emit_pin_active_requested)
        self._remove_action = actions_menu.addAction("Remove Selected", self._emit_remove_requested)
        self._pin_action.setEnabled(False)
        self._remove_action.setEnabled(False)
        self._actions_button.setMenu(actions_menu)
        paging.addWidget(self._actions_button)

        paging.addStretch(1)

        outer.addLayout(paging)

        self._asset_list.setObjectName("workspaceAssetList")
        self._asset_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._asset_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._asset_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._asset_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._asset_list.setAlternatingRowColors(False)
        self._asset_list.currentItemChanged.connect(self._on_current_item_changed)
        outer.addWidget(self._asset_list, 1)

        self._empty_import_card.setObjectName("workspaceEmptyImportCard")
        self._empty_import_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_import_card.setWordWrap(True)
        self._empty_import_card.setText("No assets yet")
        outer.addWidget(self._empty_import_card, 1)

        self._asset_list.setVisible(False)
        self._empty_import_card.setVisible(True)
        self._summary_label.setText("No assets in workspace.")

    def _sync_section_combo(self, *, total: int, start: int, window_size: int) -> None:
        section_size = max(1, int(window_size))
        section_count = max(1, (total + section_size - 1) // section_size)
        current_section = max(0, min(section_count - 1, start // section_size))

        self._window_section_combo.blockSignals(True)
        self._window_section_combo.clear()
        for idx in range(section_count):
            section_start = idx * section_size
            section_end = min(total, section_start + section_size)
            text = f"{idx + 1}/{section_count}"
            self._window_section_combo.addItem(text, section_start)
            self._window_section_combo.setItemData(
                idx,
                f"Showing assets {section_start + 1}-{section_end} of {total}",
                Qt.ItemDataRole.ToolTipRole,
            )
        self._window_section_combo.setCurrentIndex(current_section)
        self._window_section_combo.setToolTip(
            f"Showing assets {start + 1}-{min(total, start + section_size)} of {total}"
        )
        self._window_section_combo.blockSignals(False)
        self._window_section_combo.setVisible(section_count > 1)

    def _select_asset_row(self, asset_id: str) -> bool:
        for idx in range(self._asset_list.count()):
            row = self._asset_list.item(idx)
            if self._item_asset_id(row) == asset_id:
                self._asset_list.setCurrentRow(idx)
                return True
        return False

    def _on_current_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        self._update_pin_action_text()
        asset_id = self._item_asset_id(current)
        if asset_id is None:
            return
        self.asset_selected.emit(asset_id)

    def _emit_pin_active_requested(self) -> None:
        asset_id = self.active_asset_id()
        if asset_id is None:
            return
        self.pin_active_requested.emit(asset_id)

    def _emit_remove_requested(self) -> None:
        asset_id = self.active_asset_id()
        if asset_id is None:
            return
        self.asset_close_requested.emit(asset_id)

    def _on_window_section_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self._window_section_combo.itemData(index)
        if data is None:
            return
        self.window_section_requested.emit(int(data))

    def _update_pin_action_text(self) -> None:
        current = self._asset_list.currentItem()
        if current is None:
            if self._pin_action is not None:
                self._pin_action.setText("Pin Active")
            return
        if self._pin_action is None:
            return
        if bool(current.data(Qt.ItemDataRole.UserRole + 1)):
            self._pin_action.setText("Unpin Active")
        else:
            self._pin_action.setText("Pin Active")

    @staticmethod
    def _item_asset_id(row: QListWidgetItem | None) -> str | None:
        if row is None:
            return None
        data = row.data(Qt.ItemDataRole.UserRole)
        return str(data) if data is not None else None

    def _set_window_nav_state(
        self,
        *,
        has_prev: bool,
        has_next: bool,
        has_sections: bool,
    ) -> None:
        show_window_controls = bool(has_sections)
        show_prev = bool(has_prev) and show_window_controls
        show_next = bool(has_next) and show_window_controls

        self._window_prev_button.setVisible(show_window_controls)
        self._window_next_button.setVisible(show_window_controls)
        self._window_prev_button.setEnabled(show_prev)
        self._window_next_button.setEnabled(show_next)
        self._window_section_combo.setVisible(show_window_controls and self._window_section_combo.count() > 1)
        self._window_section_combo.setEnabled(show_window_controls)
