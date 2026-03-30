"""Lightweight Qt state bindings for engine state -> UI integration (Prompt 16)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal

from image_engine_app.engine.models import (
    ApplyTarget,
    AssetRecord,
    BackgroundRemovalMode,
    EditMode,
    ExportProfile,
    SessionState,
    normalize_background_removal_mode,
)


@dataclass(frozen=True)
class HeavyQueueState:
    """UI-facing heavy queue state used for queued/running badge feedback."""

    queued_count: int = 0
    running_count: int = 0


class EngineUIState(QObject):
    """
    Lightweight UI binding store.

    This intentionally does not implement the processing engine. It tracks active session/asset,
    UI selections, and emits signals so the Prompt 16 UI shell can stay decoupled from later engine
    wiring.
    """

    session_changed = Signal(object)
    active_asset_changed = Signal(object)
    mode_changed = Signal(str)
    apply_target_changed = Signal(str)
    sync_changed = Signal(bool)
    auto_apply_light_changed = Signal(bool)
    background_removal_mode_changed = Signal(str)
    performance_mode_changed = Signal(str)
    heavy_queue_state_changed = Signal(object)
    export_prediction_changed = Signal(str)
    export_profile_changed = Signal(str)
    status_message_changed = Signal(str)
    preset_requested = Signal(str)
    apply_requested = Signal()
    light_preview_requested = Signal()
    export_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    global_reset_requested = Signal()
    reset_view_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._session: SessionState | None = None
        self._active_asset: AssetRecord | None = None
        self._performance_mode: str = "cpu"
        self._heavy_queue_state = HeavyQueueState()
        self._export_prediction_text = "Size --"

    @property
    def session(self) -> SessionState | None:
        return self._session

    @property
    def active_asset(self) -> AssetRecord | None:
        return self._active_asset
    @property
    def performance_mode(self) -> str:
        return self._performance_mode

    @property
    def heavy_queue_state(self) -> HeavyQueueState:
        return self._heavy_queue_state

    @property
    def export_prediction_text(self) -> str:
        return self._export_prediction_text

    def set_session(self, session: SessionState | None) -> None:
        self._session = session
        self.session_changed.emit(session)

    def set_active_asset(self, asset: AssetRecord | None) -> None:
        self._active_asset = asset
        self.active_asset_changed.emit(asset)
        if asset is None:
            self.mode_changed.emit(EditMode.SIMPLE.value)
            self.apply_target_changed.emit(ApplyTarget.BOTH.value)
            self.sync_changed.emit(True)
            self.auto_apply_light_changed.emit(True)
            self.background_removal_mode_changed.emit(BackgroundRemovalMode.OFF.value)
            self.set_heavy_queue_counts(queued_count=0, running_count=0)
            return

        self._emit_asset_mode_and_controls()
        self.set_heavy_queue_counts(queued_count=len(asset.edit_state.queued_heavy_jobs), running_count=0)

    def set_mode(self, mode: EditMode | str) -> None:
        asset = self._active_asset
        mode_enum = mode if isinstance(mode, EditMode) else EditMode(str(mode))
        if asset is not None:
            asset.edit_state.mode = mode_enum
        self.mode_changed.emit(mode_enum.value)

    def set_apply_target(self, target: ApplyTarget | str) -> None:
        asset = self._active_asset
        target_enum = target if isinstance(target, ApplyTarget) else ApplyTarget(str(target))
        if asset is not None:
            asset.edit_state.apply_target = target_enum
        self.apply_target_changed.emit(target_enum.value)

    def set_sync_current_final(self, enabled: bool) -> None:
        asset = self._active_asset
        if asset is not None:
            asset.edit_state.sync_current_final = bool(enabled)
        self.sync_changed.emit(bool(enabled))

    def set_auto_apply_light(self, enabled: bool) -> None:
        asset = self._active_asset
        if asset is not None:
            asset.edit_state.auto_apply_light = bool(enabled)
        self.auto_apply_light_changed.emit(bool(enabled))

    def set_background_removal_mode(self, mode: BackgroundRemovalMode | str) -> None:
        asset = self._active_asset
        mode_value = normalize_background_removal_mode(mode).value
        if asset is not None:
            alpha_settings = asset.edit_state.settings.alpha
            alpha_settings.background_removal_mode = mode_value
            alpha_settings.remove_white_bg = (mode_value == BackgroundRemovalMode.WHITE.value)
        self.background_removal_mode_changed.emit(mode_value)
        if asset is not None:
            self.request_light_preview()

    def set_performance_mode(
        self,
        mode_key: str,
        *,
        announce: bool = True,
        status_message: str | None = None,
    ) -> None:
        normalized = "gpu" if str(mode_key).strip().lower() == "gpu" else "cpu"
        changed = self._performance_mode != normalized
        self._performance_mode = normalized
        if changed:
            self.performance_mode_changed.emit(normalized)
        if announce:
            self.status_message_changed.emit(status_message or f"Performance mode set to {normalized.upper()}")

    def set_export_profile(self, profile: ExportProfile | str) -> None:
        asset = self._active_asset
        if asset is None:
            return
        profile_enum = profile if isinstance(profile, ExportProfile) else ExportProfile(str(profile))
        asset.edit_state.settings.export.export_profile = profile_enum
        self.export_profile_changed.emit(profile_enum.value)
        self.status_message_changed.emit(f"Export profile set to {profile_enum.value}")

    def set_export_prediction_text(self, text: str) -> None:
        self._export_prediction_text = text
        self.export_prediction_changed.emit(text)

    def set_heavy_queue_counts(self, *, queued_count: int, running_count: int) -> None:
        self._heavy_queue_state = HeavyQueueState(queued_count=max(0, queued_count), running_count=max(0, running_count))
        self.heavy_queue_state_changed.emit(self._heavy_queue_state)

    def request_apply(self) -> None:
        self.apply_requested.emit()
        self.status_message_changed.emit("Apply requested.")

    def request_light_preview(self) -> None:
        """Request a light-only preview refresh without running heavy queues."""
        self.light_preview_requested.emit()

    def request_export(self) -> None:
        self.export_requested.emit()
        self.status_message_changed.emit("Export requested.")

    def request_undo(self) -> None:
        self.undo_requested.emit()
        self.status_message_changed.emit("Undo requested.")

    def request_redo(self) -> None:
        self.redo_requested.emit()
        self.status_message_changed.emit("Redo requested.")

    def request_global_reset(self) -> None:
        self.global_reset_requested.emit()
        self.status_message_changed.emit("Global reset requested.")

    def request_reset_view(self) -> None:
        self.reset_view_requested.emit()
        self.status_message_changed.emit("Reset view requested.")

    def request_preset(self, preset_name: str) -> None:
        self.preset_requested.emit(preset_name)
        self.status_message_changed.emit(f"Preset selected: {preset_name}")

    def _emit_asset_mode_and_controls(self) -> None:
        asset = self._active_asset
        if asset is None:
            return
        self.mode_changed.emit(asset.edit_state.mode.value)
        self.apply_target_changed.emit(asset.edit_state.apply_target.value)
        self.sync_changed.emit(asset.edit_state.sync_current_final)
        self.auto_apply_light_changed.emit(asset.edit_state.auto_apply_light)
        mode_value = normalize_background_removal_mode(
            getattr(asset.edit_state.settings.alpha, "background_removal_mode", None),
            remove_white_bg=bool(getattr(asset.edit_state.settings.alpha, "remove_white_bg", False)),
        ).value
        self.background_removal_mode_changed.emit(mode_value)




