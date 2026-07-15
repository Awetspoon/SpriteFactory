"""Qt signals and state shared by the Sprite Factory workspace controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal

from image_engine_app.engine.models import (
    AssetRecord,
    BackgroundRemovalMode,
    EditMode,
    ExportProfile,
    SessionState,
    normalize_background_removal_mode,
    normalize_edit_mode,
)
from image_engine_app.engine.export.profiles import get_profile_rule


@dataclass(frozen=True)
class HeavyQueueState:
    """UI-facing heavy queue state used for queued/running badge feedback."""

    queued_count: int = 0
    running_count: int = 0


class EngineUIState(QObject):
    """Track active UI state without taking ownership of engine processing."""

    session_changed = Signal(object)
    active_asset_changed = Signal(object)
    mode_changed = Signal(str)
    background_removal_mode_changed = Signal(str)
    heavy_queue_state_changed = Signal(object)
    export_prediction_changed = Signal(str)
    export_profile_changed = Signal(str)
    status_message_changed = Signal(str)
    apply_requested = Signal()
    light_preview_requested = Signal()
    export_requested = Signal()
    global_reset_requested = Signal()
    reset_view_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._session: SessionState | None = None
        self._active_asset: AssetRecord | None = None
        self._heavy_queue_state = HeavyQueueState()
        self._export_prediction_text = "Estimate --"

    @property
    def session(self) -> SessionState | None:
        return self._session

    @property
    def active_asset(self) -> AssetRecord | None:
        return self._active_asset

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
            self.mode_changed.emit(EditMode.ADVANCED.value)
            self.background_removal_mode_changed.emit(BackgroundRemovalMode.OFF.value)
            self.set_heavy_queue_counts(queued_count=0, running_count=0)
            return

        self._emit_asset_mode_and_controls()
        self.set_heavy_queue_counts(queued_count=len(asset.edit_state.queued_heavy_jobs), running_count=0)

    def set_mode(self, mode: EditMode | str) -> None:
        asset = self._active_asset
        mode_enum = normalize_edit_mode(mode)
        if asset is not None:
            asset.edit_state.mode = mode_enum
        self.mode_changed.emit(mode_enum.value)

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

    def set_export_profile(self, profile: ExportProfile | str) -> None:
        asset = self._active_asset
        if asset is None:
            return
        profile_enum = profile if isinstance(profile, ExportProfile) else ExportProfile(str(profile))
        export = asset.edit_state.settings.export
        rule = get_profile_rule(profile_enum)
        export.export_profile = profile_enum
        export.format = rule.default_format
        export.quality = rule.default_quality
        export.compression_level = rule.default_compression_level
        export.strip_metadata = rule.strip_metadata
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
        self.status_message_changed.emit("Heavy processing requested.")

    def request_light_preview(self) -> None:
        """Request a light-only preview refresh without running heavy queues."""
        self.light_preview_requested.emit()

    def request_export(self) -> None:
        self.export_requested.emit()
        self.status_message_changed.emit("Export requested.")

    def request_global_reset(self) -> None:
        self.global_reset_requested.emit()
        self.status_message_changed.emit("Global reset requested.")

    def request_reset_view(self) -> None:
        self.reset_view_requested.emit()
        self.status_message_changed.emit("Reset view requested.")

    def _emit_asset_mode_and_controls(self) -> None:
        asset = self._active_asset
        if asset is None:
            return
        self.mode_changed.emit(asset.edit_state.mode.value)
        mode_value = normalize_background_removal_mode(
            getattr(asset.edit_state.settings.alpha, "background_removal_mode", None),
            remove_white_bg=bool(getattr(asset.edit_state.settings.alpha, "remove_white_bg", False)),
        ).value
        self.background_removal_mode_changed.emit(mode_value)
