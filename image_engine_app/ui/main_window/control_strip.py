"""Preview control strip for apply targets, sync, auto-apply, and view reset."""

from __future__ import annotations

from functools import partial

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)

from engine.models import ApplyTarget
from ui.common.icons import icon
from ui.common.state_bindings import EngineUIState


class ControlStrip(QFrame):
    """Bottom strip under preview area matching the Prompt 16 UI mapping."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_state: EngineUIState | None = None
        self._apply_target_buttons: dict[str, QToolButton] = {}
        self._sync_button = QToolButton(self)
        self._auto_apply_button = QToolButton(self)
        self._apply_button = QPushButton(self)
        self._build_ui()

    def bind_state(self, ui_state: EngineUIState) -> None:
        self._ui_state = ui_state
        ui_state.apply_target_changed.connect(self._on_apply_target_changed)
        ui_state.sync_changed.connect(self._on_sync_changed)
        ui_state.auto_apply_light_changed.connect(self._on_auto_apply_light_changed)
        ui_state.active_asset_changed.connect(self._on_active_asset_changed)

        self._on_apply_target_changed(
            ui_state.active_asset.edit_state.apply_target.value if ui_state.active_asset else ApplyTarget.BOTH.value
        )
        self._on_sync_changed(ui_state.active_asset.edit_state.sync_current_final if ui_state.active_asset else True)
        self._on_auto_apply_light_changed(ui_state.active_asset.edit_state.auto_apply_light if ui_state.active_asset else True)

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { border:1px solid #bfd2d4; border-radius:8px; background:#ffffff; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Apply Target:", self))

        apply_group = QButtonGroup(self)
        apply_group.setExclusive(True)
        for value, label_text in (
            (ApplyTarget.CURRENT.value, "Current"),
            (ApplyTarget.FINAL.value, "Final"),
            (ApplyTarget.BOTH.value, "Both"),
        ):
            btn = QToolButton(self)
            btn.setText(label_text)
            btn.setCheckable(True)
            btn.clicked.connect(partial(self._emit_apply_target, value))
            apply_group.addButton(btn)
            self._apply_target_buttons[value] = btn
            layout.addWidget(btn)
        self._apply_target_buttons[ApplyTarget.BOTH.value].setChecked(True)

        layout.addSpacing(8)
        self._sync_button.setText("Sync Current/Final")
        self._sync_button.setCheckable(True)
        self._sync_button.setChecked(True)
        self._sync_button.clicked.connect(self._emit_sync_change)
        layout.addWidget(self._sync_button)

        self._auto_apply_button.setText("Auto-Apply Light")
        self._auto_apply_button.setCheckable(True)
        self._auto_apply_button.setChecked(True)
        self._auto_apply_button.clicked.connect(self._emit_auto_apply_change)
        layout.addWidget(self._auto_apply_button)

        layout.addStretch(1)

        self._apply_button.setText("Apply")
        self._apply_button.setIcon(icon("apply"))
        self._apply_button.clicked.connect(self._emit_apply_requested)
        layout.addWidget(self._apply_button)

        reset_settings_btn = QPushButton(self)
        reset_settings_btn.setText("Reset Settings")
        reset_settings_btn.setIcon(icon("reset"))
        reset_settings_btn.setToolTip("Reset the active asset controls back to defaults.")
        reset_settings_btn.clicked.connect(self._emit_reset_settings)
        layout.addWidget(reset_settings_btn)

        reset_view_btn = QPushButton(self)
        reset_view_btn.setText("Reset View")
        reset_view_btn.setIcon(icon("reset"))
        reset_view_btn.setToolTip("Reset zoom/pan in preview panes to 100%.")
        reset_view_btn.clicked.connect(self._emit_reset_view)
        layout.addWidget(reset_view_btn)

    def _emit_apply_target(self, target_value: str) -> None:
        if self._ui_state is not None:
            self._ui_state.set_apply_target(target_value)

    def _emit_sync_change(self) -> None:
        if self._ui_state is not None:
            self._ui_state.set_sync_current_final(self._sync_button.isChecked())

    def _emit_auto_apply_change(self) -> None:
        if self._ui_state is not None:
            self._ui_state.set_auto_apply_light(self._auto_apply_button.isChecked())

    def _emit_apply_requested(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_apply()

    def _emit_reset_view(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_reset_view()

    def _emit_reset_settings(self) -> None:
        if self._ui_state is not None:
            self._ui_state.request_global_reset()

    def _on_apply_target_changed(self, target_value: str) -> None:
        button = self._apply_target_buttons.get(target_value)
        if button is None:
            return
        for btn in self._apply_target_buttons.values():
            btn.blockSignals(True)
        button.setChecked(True)
        for btn in self._apply_target_buttons.values():
            btn.blockSignals(False)

    def _on_sync_changed(self, enabled: bool) -> None:
        self._sync_button.blockSignals(True)
        self._sync_button.setChecked(bool(enabled))
        self._sync_button.blockSignals(False)

    def _on_auto_apply_light_changed(self, enabled: bool) -> None:
        self._auto_apply_button.blockSignals(True)
        self._auto_apply_button.setChecked(bool(enabled))
        self._auto_apply_button.blockSignals(False)

    def _on_active_asset_changed(self, asset: object) -> None:
        has_asset = asset is not None
        self.setEnabled(has_asset)
        if not has_asset:
            return
        edit_state = getattr(asset, "edit_state", None)
        if edit_state is None:
            return
        self._on_apply_target_changed(getattr(getattr(edit_state, "apply_target", None), "value", ApplyTarget.BOTH.value))
        self._on_sync_changed(bool(getattr(edit_state, "sync_current_final", True)))
        self._on_auto_apply_light_changed(bool(getattr(edit_state, "auto_apply_light", True)))




