"""Qt signals and passive state shared by the Sprite Factory workspace."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from image_engine_app.engine.models import (
    AssetRecord,
    BackgroundRemovalMode,
    ExportProfile,
    SessionState,
    normalize_background_removal_mode,
)


@dataclass(frozen=True)
class HeavyQueueState:
    """UI-facing heavy queue state used for queued/running feedback."""

    queued_count: int = 0
    running_count: int = 0


class EngineUIState(QObject):
    """Publish UI state and user intent without mutating engine models."""

    session_changed = Signal(object)
    active_asset_changed = Signal(object)
    heavy_queue_state_changed = Signal(object)
    export_prediction_changed = Signal(str)
    status_message_changed = Signal(str)

    edit_setting_requested = Signal(str, str, object)
    edit_settings_reset_requested = Signal(object)
    output_size_requested = Signal(str)
    export_profile_requested = Signal(str)
    apply_requested = Signal()
    final_preview_requested = Signal()
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
        jobs = asset.edit_state.queued_heavy_jobs if asset is not None else ()
        queued = sum(1 for job in jobs if str(getattr(getattr(job, "status", None), "value", "")) == "queued")
        running = sum(1 for job in jobs if str(getattr(getattr(job, "status", None), "value", "")) == "running")
        self.set_heavy_queue_counts(queued_count=queued, running_count=running)

    def request_setting_change(self, group_name: str, field_name: str, value: object) -> None:
        self.edit_setting_requested.emit(str(group_name), str(field_name), value)

    def request_settings_reset(self, field_paths: object) -> None:
        self.edit_settings_reset_requested.emit(field_paths)

    def request_background_removal_mode(self, mode: BackgroundRemovalMode | str) -> None:
        mode_value = normalize_background_removal_mode(mode).value
        self.request_setting_change("alpha", "background_removal_mode", mode_value)

    def request_output_size(self, choice_key: str) -> None:
        self.output_size_requested.emit(str(choice_key))

    def request_export_profile(self, profile: ExportProfile | str) -> None:
        profile_value = profile.value if isinstance(profile, ExportProfile) else ExportProfile(str(profile)).value
        self.export_profile_requested.emit(profile_value)

    def set_export_prediction_text(self, text: str) -> None:
        self._export_prediction_text = text
        self.export_prediction_changed.emit(text)

    def set_heavy_queue_counts(self, *, queued_count: int, running_count: int) -> None:
        self._heavy_queue_state = HeavyQueueState(queued_count=max(0, queued_count), running_count=max(0, running_count))
        self.heavy_queue_state_changed.emit(self._heavy_queue_state)

    def request_apply(self) -> None:
        self.apply_requested.emit()

    def request_final_preview(self) -> None:
        self.final_preview_requested.emit()

    def request_export(self) -> None:
        self.export_requested.emit()

    def request_global_reset(self) -> None:
        self.global_reset_requested.emit()

    def request_reset_view(self) -> None:
        self.reset_view_requested.emit()
