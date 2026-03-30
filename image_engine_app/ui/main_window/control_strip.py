"""Preview control strip for apply targets, live behavior, and workspace actions."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.models import ApplyTarget, BackgroundRemovalMode
from image_engine_app.ui.common.icons import icon
from image_engine_app.ui.common.state_bindings import EngineUIState
from image_engine_app.ui.main_window.control_strip_state import ControlStripViewState, build_control_strip_view_state


class ControlStrip(QFrame):
    """Compact workspace tools shelf shown below the preview panes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._apply_target_buttons: dict[str, QToolButton] = {}
        self._scope_group: QFrame | None = None
        self._behavior_group: QFrame | None = None
        self._actions_group: QFrame | None = None
        self._header_summary = QLabel(self)
        self._queue_badge = QLabel(self)
        self._target_badge = QLabel(self)
        self._background_button = QToolButton(self)
        self._background_mode_actions: dict[str, QAction] = {}
        self._sync_button = QToolButton(self)
        self._auto_apply_button = QToolButton(self)
        self._preview_button = QPushButton(self)
        self._apply_button = QPushButton(self)
        self._options_button = QToolButton(self)
        self._reset_settings_action = QAction(icon("reset"), "Reset Edits", self)
        self._reset_view_action = QAction(icon("reset"), "Reset View", self)
        self._build_ui()
        self._apply_view_state(ControlStripViewState(has_asset=False))

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        ui_state.apply_target_changed.connect(self._on_apply_target_changed)
        ui_state.sync_changed.connect(self._on_sync_changed)
        ui_state.auto_apply_light_changed.connect(self._on_auto_apply_light_changed)
        ui_state.background_removal_mode_changed.connect(self._on_background_mode_changed)
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)
        ui_state.heavy_queue_state_changed.connect(self._on_heavy_queue_state_changed)
        self._sync_from_ui_state()

    def _build_ui(self) -> None:
        self.setObjectName("controlStripRoot")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        eyebrow = QLabel("TOOLS", self)
        eyebrow.setObjectName("controlStripEyebrow")
        header_text.addWidget(eyebrow)

        self._header_summary.setObjectName("controlStripSummary")
        self._header_summary.setWordWrap(True)
        header_text.addWidget(self._header_summary)

        header.addLayout(header_text, 1)

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
        self._background_button.setObjectName("controlStripMenuAction")
        self._background_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._background_button.setMenu(bg_menu)
        self._background_button.setMinimumWidth(84)
        header.addWidget(self._background_button, 0)

        self._target_badge.setObjectName("controlStripHeaderBadge")
        self._target_badge.setMinimumWidth(82)
        self._target_badge.setMinimumHeight(24)
        self._target_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._target_badge, 0)

        self._queue_badge.setObjectName("controlStripHeaderBadge")
        self._queue_badge.setMinimumWidth(84)
        self._queue_badge.setMinimumHeight(24)
        self._queue_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._queue_badge, 0)

        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(8)

        self._scope_group, scope_layout = self._create_group("TARGET")
        apply_group = QButtonGroup(self)
        apply_group.setExclusive(True)
        for value, label_text in (
            (ApplyTarget.CURRENT.value, "Cur"),
            (ApplyTarget.FINAL.value, "Fin"),
            (ApplyTarget.BOTH.value, "Both"),
        ):
            btn = QToolButton(self)
            btn.setObjectName("controlStripChip")
            btn.setText(label_text)
            btn.setCheckable(True)
            btn.setToolTip(f"Apply to {value}")
            btn.clicked.connect(partial(self._emit_apply_target, value))
            apply_group.addButton(btn)
            self._apply_target_buttons[value] = btn
            scope_layout.addWidget(btn)
        scope_layout.addStretch(1)
        body.addWidget(self._scope_group, 1)

        self._behavior_group, behavior_layout = self._create_group("LIVE")
        self._sync_button.setObjectName("controlStripToggle")
        self._sync_button.setText("Link")
        self._sync_button.setToolTip("Keep current and final previews linked")
        self._sync_button.setCheckable(True)
        self._sync_button.clicked.connect(self._emit_sync_change)
        behavior_layout.addWidget(self._sync_button)

        self._auto_apply_button.setObjectName("controlStripToggle")
        self._auto_apply_button.setText("Auto")
        self._auto_apply_button.setToolTip("Auto-run light preview while editing")
        self._auto_apply_button.setCheckable(True)
        self._auto_apply_button.clicked.connect(self._emit_auto_apply_change)
        behavior_layout.addWidget(self._auto_apply_button)
        behavior_layout.addStretch(1)
        body.addWidget(self._behavior_group, 1)

        self._actions_group, action_layout = self._create_group("RUN")
        self._preview_button.setObjectName("controlStripSecondaryAction")
        self._preview_button.setText("Preview")
        self._preview_button.setIcon(icon("apply"))
        self._preview_button.clicked.connect(self._emit_light_preview_requested)
        action_layout.addWidget(self._preview_button, 0)

        self._apply_button.setObjectName("controlStripPrimaryAction")
        self._apply_button.setIcon(icon("apply"))
        self._apply_button.clicked.connect(self._emit_apply_requested)
        action_layout.addWidget(self._apply_button, 0)

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
        body.addWidget(self._actions_group, 0)

        root.addLayout(body)

    def _create_group(self, title: str) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame(self)
        frame.setObjectName("controlStripGroup")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)

        label = QLabel(title, frame)
        label.setObjectName("controlStripSectionLabel")
        layout.addWidget(label)

        content = QHBoxLayout()
        content.setSpacing(6)
        layout.addLayout(content)
        return frame, content

    def _emit_apply_target(self, target_value: str) -> None:
        if self._ui_state is not None:
            self._ui_state.set_apply_target(target_value)

    def _emit_sync_change(self) -> None:
        if self._ui_state is not None:
            self._ui_state.set_sync_current_final(self._sync_button.isChecked())

    def _emit_auto_apply_change(self) -> None:
        if self._ui_state is not None:
            self._ui_state.set_auto_apply_light(self._auto_apply_button.isChecked())

    def _emit_background_mode(self, mode_value: str) -> None:
        if self._ui_state is not None:
            self._ui_state.set_background_removal_mode(mode_value)

    def _emit_light_preview_requested(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_light_preview()

    def _emit_apply_requested(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_apply()

    def _emit_reset_view(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_reset_view()

    def _emit_reset_settings(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_global_reset()

    def _on_apply_target_changed(self, _target_value: str) -> None:
        self._sync_from_ui_state()

    def _on_sync_changed(self, _enabled: bool) -> None:
        self._sync_from_ui_state()

    def _on_auto_apply_light_changed(self, _enabled: bool) -> None:
        self._sync_from_ui_state()

    def _on_background_mode_changed(self, _mode_value: str) -> None:
        self._sync_from_ui_state()

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
        self._set_group_enabled(self._scope_group, state.has_asset)
        self._set_group_enabled(self._behavior_group, state.has_asset)
        self._set_group_enabled(self._actions_group, state.has_asset)
        self._preview_button.setEnabled(state.has_asset)
        self._apply_button.setEnabled(state.has_asset)
        self._options_button.setEnabled(state.has_asset)
        self._background_button.setEnabled(state.has_asset)
        self._reset_settings_action.setEnabled(state.has_asset)
        self._reset_view_action.setEnabled(state.has_asset)

        self._header_summary.setText(state.summary_text)
        self._background_button.setText(state.background_button_text)
        self._background_button.setToolTip(state.background_button_tooltip)
        self._set_badge_text(self._target_badge, state.target_badge_text, tone="neutral")
        self._set_badge_text(self._queue_badge, state.queue_badge_text, tone=state.queue_badge_tone)
        for mode_value, action in self._background_mode_actions.items():
            action.blockSignals(True)
            action.setChecked(mode_value == state.background_mode)
            action.blockSignals(False)

        button = self._apply_target_buttons.get(state.apply_target)
        if button is not None:
            for candidate in self._apply_target_buttons.values():
                candidate.blockSignals(True)
            button.setChecked(True)
            for candidate in self._apply_target_buttons.values():
                candidate.blockSignals(False)

        self._sync_button.blockSignals(True)
        self._sync_button.setChecked(state.sync_current_final)
        self._sync_button.blockSignals(False)

        self._auto_apply_button.blockSignals(True)
        self._auto_apply_button.setChecked(state.auto_apply_light)
        self._auto_apply_button.blockSignals(False)

        self._preview_button.setText(state.preview_button_text)
        self._preview_button.setToolTip(state.preview_button_tooltip)
        self._apply_button.setText(state.apply_button_text)
        self._apply_button.setToolTip(state.apply_button_tooltip)

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
