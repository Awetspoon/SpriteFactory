"""Encoding workflow coordinator for the main window."""

from __future__ import annotations

from typing import Any

from image_engine_app.engine.models import ChromaSubsampling, ExportFormat


class EncodingCoordinator:
    """Owns encoding dialog show/apply actions for the main window."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def show_export_encoding_window(self) -> None:
        asset = self._window.ui_state.active_asset
        if asset is not None:
            self._window.export_encoding_dialog.load_from_asset(asset)
        self._window.export_encoding_dialog.show()
        self._window.export_encoding_dialog.raise_()
        self._window.export_encoding_dialog.activateWindow()

    def on_export_encoding_apply_requested(self, options_obj: object) -> None:
        asset = self._window.ui_state.active_asset
        if asset is None:
            self._window._status("Encoding apply skipped: no active asset")
            return

        export_settings = getattr(getattr(getattr(asset, "edit_state", None), "settings", None), "export", None)
        if export_settings is None:
            self._window._status("Encoding apply skipped: export settings unavailable")
            return

        try:
            fmt_raw = str(
                getattr(
                    options_obj,
                    "format",
                    getattr(export_settings.format, "value", ExportFormat.AUTO.value),
                )
            ).lower()
            export_settings.format = ExportFormat(fmt_raw)

            quality = int(getattr(options_obj, "quality", export_settings.quality))
            export_settings.quality = max(1, min(100, quality))

            compression = int(getattr(options_obj, "compression_level", export_settings.compression_level))
            export_settings.compression_level = max(0, min(9, compression))

            chroma_raw = str(
                getattr(
                    options_obj,
                    "chroma_subsampling",
                    getattr(export_settings.chroma_subsampling, "value", ChromaSubsampling.AUTO.value),
                )
            ).lower()
            export_settings.chroma_subsampling = ChromaSubsampling(chroma_raw)

            export_settings.strip_metadata = bool(getattr(options_obj, "strip_metadata", export_settings.strip_metadata))

            self._window.ui_state.set_active_asset(asset)
            self._window._refresh_export_prediction()
            self._window._status("Applied encoding settings to current asset")
        except Exception as exc:
            self._window._status(f"Encoding apply failed: {exc}")

