"""Preview controls for presets, background handling, and processing actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.models import BackgroundRemovalMode
from image_engine_app.ui.common.icons import icon
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY
from image_engine_app.ui.common.state_bindings import EngineUIState
from image_engine_app.ui.main_window.control_strip_state import ControlStripViewState, build_control_strip_view_state


class ControlStrip(QFrame):
    """Compact workspace tools shelf shown below the preview panes."""

    preset_selected = Signal(str)
    preset_manager_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._actions_group: QFrame | None = None
        self._header_summary = QLabel(self)
        self._queue_badge = QLabel(self)
        self._preset_button = QToolButton(self)
        self._preset_menu = QMenu(self._preset_button)
        self._background_button = QToolButton(self)
        self._background_mode_actions: dict[str, QAction] = {}
        self._run_button = QPushButton(self)
        self._run_heavy = False
        self._options_button = QToolButton(self)
        self._reset_settings_action = QAction(icon("reset"), "Reset Edits", self)
        self._reset_view_action = QAction(icon("reset"), "Reset View", self)
        self._build_ui()
        self.set_preset_entries([], has_asset=False)
        self._apply_view_state(ControlStripViewState(has_asset=False))

    def set_preset_entries(self, entries: list[object], *, has_asset: bool) -> None:
        """Refresh the active-asset preset menu without duplicating preset logic."""

        self._preset_menu.clear()
        if not has_asset:
            empty_action = QAction("Select an asset first", self._preset_menu)
            empty_action.setEnabled(False)
            self._preset_menu.addAction(empty_action)
            self._preset_menu.addSeparator()
        elif not entries:
            empty_action = QAction("No compatible presets", self._preset_menu)
            empty_action.setEnabled(False)
            self._preset_menu.addAction(empty_action)
            self._preset_menu.addSeparator()
        else:
            for entry in entries:
                name = str(getattr(entry, "name", entry) or "").strip()
                if not name:
                    continue
                label = str(getattr(entry, "label", name) or name).strip() or name
                action = QAction(label, self._preset_menu)
                action.setData(name)
                tooltip = str(getattr(entry, "scope_text", "") or "").strip()
                if tooltip:
                    action.setToolTip(tooltip)
                action.triggered.connect(lambda _checked=False, preset_name=name: self.preset_selected.emit(preset_name))
                self._preset_menu.addAction(action)
            self._preset_menu.addSeparator()

        manage_action = QAction("Manage Presets...", self._preset_menu)
        manage_action.triggered.connect(self.preset_manager_requested.emit)
        self._preset_menu.addAction(manage_action)
        self._preset_button.setEnabled(True)
        self._preset_button.setToolTip(
            "Apply a compatible preset to the active asset" if has_asset else "Open Preset Manager or select an asset first"
        )

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        ui_state.heavy_queue_state_changed.connect(self._on_heavy_queue_state_changed)
        self._sync_from_ui_state()

    def _build_ui(self) -> None:
        self.setObjectName("controlStripRoot")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QVBoxLayout(self)
        root.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
        )
        root.setSpacing(SHELL_GEOMETRY.compact_gap)

        header = QHBoxLayout()
        header.setSpacing(SHELL_GEOMETRY.gap)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        eyebrow = QLabel("TOOLS", self)
        eyebrow.setObjectName("controlStripEyebrow")
        header_text.addWidget(eyebrow)

        self._header_summary.setObjectName("controlStripSummary")
        self._header_summary.setWordWrap(True)
        header_text.addWidget(self._header_summary)

        header.addLayout(header_text, 1)

        self._preset_button.setObjectName("controlStripHeaderMenuAction")
        self._preset_button.setText("Preset")
        self._preset_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._preset_button.setMenu(self._preset_menu)
        self._preset_button.setFixedSize(
            SHELL_GEOMETRY.control_menu_width,
            SHELL_GEOMETRY.control_height,
        )
        header.addWidget(self._preset_button, 0)

        bg_menu = QMenu(self._background_button)
        bg_group = QActionGroup(self)
        bg_group.setExclusive(True)
        for mode_value, label_text in (
            (BackgroundRemovalMode.OFF.value, "Keep Background"),
            (BackgroundRemovalMode.WHITE.value, "Remove White"),
            (BackgroundRemovalMode.BLACK.value, "Remove Black"),
        ):
            action = QAction(label_text, self, checkable=True)
            action.triggered.connect(lambda _checked=False, mode_value=mode_value: self._emit_background_mode(mode_value))
            bg_group.addAction(action)
            bg_menu.addAction(action)
            self._background_mode_actions[mode_value] = action
        self._background_button.setObjectName("controlStripHeaderMenuAction")
        self._background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._background_button.setMenu(bg_menu)
        self._background_button.setFixedSize(
            SHELL_GEOMETRY.control_menu_width,
            SHELL_GEOMETRY.control_height,
        )
        header.addWidget(self._background_button, 0)

        self._queue_badge.setObjectName("controlStripHeaderBadge")
        self._queue_badge.setFixedSize(
            SHELL_GEOMETRY.control_badge_width,
            SHELL_GEOMETRY.control_height,
        )
        self._queue_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._queue_badge, 0)

        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(SHELL_GEOMETRY.gap)

        self._actions_group, action_layout = self._create_group("FINAL")
        self._run_button.setObjectName("controlStripPrimaryAction")
        self._run_button.setIcon(icon("apply"))
        self._run_button.clicked.connect(self._emit_run_requested)
        action_layout.addWidget(self._run_button, 0)

        options_menu = QMenu(self._options_button)
        self._reset_settings_action.triggered.connect(self._emit_reset_settings)
        self._reset_view_action.triggered.connect(self._emit_reset_view)
        options_menu.addAction(self._reset_settings_action)
        options_menu.addAction(self._reset_view_action)

        self._options_button.setObjectName("controlStripMenuAction")
        self._options_button.setText("More")
        self._options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._options_button.setMenu(options_menu)
        self._options_button.setMinimumWidth(72)
        action_layout.addWidget(self._options_button, 0)
        action_layout.addStretch(1)
        body.addWidget(self._actions_group, 1)

        root.addLayout(body)

    def _create_group(self, title: str) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName("controlStripGroup")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
        )
        layout.setSpacing(4)

        label = QLabel(title, frame)
        label.setObjectName("controlStripSectionLabel")
        layout.addWidget(label)

        content = QHBoxLayout()
        content.setSpacing(6)
        layout.addLayout(content)
        return frame, content

    def _emit_background_mode(self, mode_value: str) -> None:
        if self._ui_state is not None:
            self._ui_state.request_background_removal_mode(mode_value)

    def _emit_run_requested(self) -> None:
        if self._ui_state is not None:
            if self._run_heavy:
                self._ui_state.request_apply()
            else:
                self._ui_state.request_final_preview()

    def _emit_reset_view(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_reset_view()

    def _emit_reset_settings(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_global_reset()

    def _on_active_asset_changed(self, _asset: object) -> None:
        self._sync_from_ui_state()

    def _on_heavy_queue_state_changed(self, _state: object) -> None:
        self._sync_from_ui_state()

    def _sync_from_ui_state(self) -> None:
        if self._ui_state is None:
            self._apply_view_state(ControlStripViewState(has_asset=False))
            return
        self._apply_view_state(
            build_control_strip_view_state(
                self._ui_state.active_asset,
                self._ui_state.heavy_queue_state,
            )
        )

    def _apply_view_state(self, state: ControlStripViewState) -> None:
        self._set_group_enabled(self._actions_group, state.has_asset)
        self._run_button.setEnabled(state.has_asset and state.running_heavy_jobs == 0)
        self._options_button.setEnabled(state.has_asset)
        self._background_button.setEnabled(state.has_asset)
        self._reset_settings_action.setEnabled(state.has_asset)
        self._reset_view_action.setEnabled(state.has_asset)

        self._header_summary.setText(state.summary_text)
        self._background_button.setText(state.background_button_text)
        self._background_button.setToolTip(state.background_button_tooltip)
        self._set_badge_text(self._queue_badge, state.queue_badge_text, tone=state.queue_badge_tone)
        for mode_value, action in self._background_mode_actions.items():
            action.blockSignals(True)
            action.setChecked(mode_value == state.background_mode)
            action.blockSignals(False)

        self._run_heavy = state.run_heavy
        self._run_button.setText(state.run_button_text)
        self._run_button.setToolTip(state.run_button_tooltip)

    @staticmethod
    def _set_group_enabled(group: QFrame | None, enabled: bool) -> None:
        if group is not None:
            group.setEnabled(enabled)

    @staticmethod
    def _set_badge_text(label: QLabel, text: str, *, tone: str) -> None:
        label.setText(text)
        label.setStyleSheet("")
        label.setProperty("tone", tone)
        style = label.style()
        if style is not None:
            style.unpolish(label)
            style.polish(label)
        label.update()
