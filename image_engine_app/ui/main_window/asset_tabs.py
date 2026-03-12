"""Workspace asset tabs for multi-asset navigation in the main window."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class AssetTabItem:
    """Minimal asset tab data used to render the workspace tab bar."""

    asset_id: str
    label: str
    tooltip: str = ""
    pinned: bool = False


class WorkspaceAssetTabs(QFrame):
    """Tabbed asset navigator bound to session tab order and active asset state."""

    asset_selected = Signal(str)
    pin_active_requested = Signal(str)
    asset_close_requested = Signal(str)
    window_prev_requested = Signal()
    window_next_requested = Signal()
    window_section_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._tab_bar = QTabBar(self)
        self._summary_label = QLabel(self)
        self._window_label = QLabel(self)
        self._window_section_combo = QComboBox(self)
        self._window_prev_button = QToolButton(self)
        self._window_next_button = QToolButton(self)
        self._pin_button = QToolButton(self)
        self._build_ui()

    def _clear_tab_bar(self) -> None:
        """Qt6/PySide6: QTabBar has no .clear(), so remove tabs manually."""
        while self._tab_bar.count() > 0:
            self._tab_bar.removeTab(0)

    def set_tabs(
        self,
        items: list[AssetTabItem],
        *,
        active_asset_id: str | None = None,
        total_count: int | None = None,
        window_start: int = 0,
        window_size: int = 100,
    ) -> None:
        """Replace tab contents and select the active asset if present."""

        self._tab_bar.blockSignals(True)
        self._clear_tab_bar()

        for item in items:
            label = f"[P] {item.label}" if item.pinned else item.label
            index = self._tab_bar.addTab(label)
            self._tab_bar.setTabData(index, item.asset_id)
            self._tab_bar.setTabToolTip(index, item.tooltip or item.label)

        if items:
            self._tab_bar.setEnabled(True)
            self._pin_button.setEnabled(True)
            self._pin_button.setVisible(True)
            total = int(total_count) if total_count is not None else len(items)
            hidden = max(0, total - len(items))
            size = max(1, int(window_size))
            start = max(0, min(int(window_start), max(0, total - 1)))
            end = min(total, start + len(items))

            summary = f"{total} asset(s) in workspace"
            if hidden > 0:
                summary += f" ({hidden} hidden for performance)"
            self._summary_label.setText(summary)

            if hidden > 0:
                self._window_label.setText(f"Showing {start + 1}-{end}")
                self._window_label.setVisible(True)
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
            self._tab_bar.setEnabled(False)
            self._pin_button.setEnabled(False)
            self._pin_button.setVisible(False)
            self._summary_label.setText("No assets in workspace")
            self._window_label.setText("")
            self._window_label.setVisible(False)
            self._window_section_combo.clear()
            self._window_section_combo.setVisible(False)
            self._set_window_nav_state(has_prev=False, has_next=False, has_sections=False)

        if active_asset_id is not None:
            for idx in range(self._tab_bar.count()):
                if self._tab_bar.tabData(idx) == active_asset_id:
                    self._tab_bar.setCurrentIndex(idx)
                    break
        elif self._tab_bar.count() > 0:
            self._tab_bar.setCurrentIndex(0)

        self._tab_bar.blockSignals(False)
        self._update_pin_button_text()

    def set_active_asset(self, asset_id: str | None) -> None:
        """Set the current tab selection by asset id."""

        if asset_id is None:
            return
        self._tab_bar.blockSignals(True)
        for idx in range(self._tab_bar.count()):
            if self._tab_bar.tabData(idx) == asset_id:
                self._tab_bar.setCurrentIndex(idx)
                break
        self._tab_bar.blockSignals(False)
        self._update_pin_button_text()

    def active_asset_id(self) -> str | None:
        """Return the currently selected asset id, if any."""

        idx = self._tab_bar.currentIndex()
        if idx < 0:
            return None
        data = self._tab_bar.tabData(idx)
        return str(data) if data is not None else None

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border:1px solid #bfd2d4; border-radius:8px; background:#ffffff; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)

        title = QLabel("Workspace Tabs", self)
        title.setStyleSheet("font-weight:600; color:#0f3338;")
        top.addWidget(title)

        self._summary_label.setStyleSheet("color:#4f6b70;")
        top.addWidget(self._summary_label, 1)

        self._window_label.setStyleSheet("color:#3f5f64;")
        self._window_label.setVisible(False)
        top.addWidget(self._window_label)

        self._window_section_combo.setMinimumWidth(220)
        self._window_section_combo.setVisible(False)
        self._window_section_combo.currentIndexChanged.connect(self._on_window_section_changed)
        top.addWidget(self._window_section_combo)

        self._window_prev_button.setText("<")
        self._window_prev_button.setToolTip("Show previous tab section")
        self._window_prev_button.setAutoRaise(True)
        self._window_prev_button.setEnabled(False)
        self._window_prev_button.setVisible(False)
        self._window_prev_button.clicked.connect(self.window_prev_requested.emit)
        top.addWidget(self._window_prev_button)

        self._window_next_button.setText(">")
        self._window_next_button.setToolTip("Show next tab section")
        self._window_next_button.setAutoRaise(True)
        self._window_next_button.setEnabled(False)
        self._window_next_button.setVisible(False)
        self._window_next_button.clicked.connect(self.window_next_requested.emit)
        top.addWidget(self._window_next_button)

        self._pin_button.setText("Pin Active")
        self._pin_button.setEnabled(False)
        self._pin_button.setVisible(False)
        self._pin_button.clicked.connect(self._emit_pin_active_requested)
        top.addWidget(self._pin_button)

        outer.addLayout(top)

        self._tab_bar.setMovable(False)
        self._tab_bar.setTabsClosable(True)
        self._tab_bar.setDocumentMode(True)
        self._tab_bar.currentChanged.connect(self._on_current_changed)
        self._tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)
        outer.addWidget(self._tab_bar)

        self._summary_label.setText("No assets in workspace")

    def _sync_section_combo(self, *, total: int, start: int, window_size: int) -> None:
        section_size = max(1, int(window_size))
        section_count = max(1, (total + section_size - 1) // section_size)
        current_section = max(0, min(section_count - 1, start // section_size))

        self._window_section_combo.blockSignals(True)
        self._window_section_combo.clear()
        for idx in range(section_count):
            section_start = idx * section_size
            section_end = min(total, section_start + section_size)
            text = f"Section {idx + 1}/{section_count} ({section_start + 1}-{section_end})"
            self._window_section_combo.addItem(text, section_start)
        self._window_section_combo.setCurrentIndex(current_section)
        self._window_section_combo.blockSignals(False)
        self._window_section_combo.setVisible(section_count > 1)

    def _on_current_changed(self, index: int) -> None:
        self._update_pin_button_text()
        if index < 0:
            return
        data = self._tab_bar.tabData(index)
        if data is None:
            return
        self.asset_selected.emit(str(data))

    def _emit_pin_active_requested(self) -> None:
        asset_id = self.active_asset_id()
        if asset_id is None:
            return
        self.pin_active_requested.emit(asset_id)

    def _on_tab_close_requested(self, index: int) -> None:
        if index < 0:
            return
        data = self._tab_bar.tabData(index)
        if data is None:
            return
        self.asset_close_requested.emit(str(data))

    def _on_window_section_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self._window_section_combo.itemData(index)
        if data is None:
            return
        self.window_section_requested.emit(int(data))

    def _update_pin_button_text(self) -> None:
        idx = self._tab_bar.currentIndex()
        if idx < 0:
            self._pin_button.setText("Pin Active")
            return
        label = self._tab_bar.tabText(idx)
        if label.startswith("[P] "):
            self._pin_button.setText("Unpin Active")
        else:
            self._pin_button.setText("Pin Active")

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

        self._window_prev_button.setVisible(show_prev)
        self._window_next_button.setVisible(show_next)
        self._window_prev_button.setEnabled(show_prev)
        self._window_next_button.setEnabled(show_next)
        self._window_section_combo.setVisible(show_window_controls and self._window_section_combo.count() > 1)
        self._window_section_combo.setEnabled(show_window_controls)


