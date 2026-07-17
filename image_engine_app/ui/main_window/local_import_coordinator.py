"""Local file and folder import coordinator for the main window."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog


class LocalImportCoordinator:
    """Owns the File menu's two distinct add workflows."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def import_files(self) -> None:
        if not self._has_controller():
            return

        paths, _selected = QFileDialog.getOpenFileNames(
            self._window,
            "Add Files to Workspace",
            self._default_import_directory(),
            self._window._local_import_dialog_filter(),
        )
        if not paths:
            return

        self._import_sources(
            paths,
            recursive=False,
            preserve_structure=False,
            source_label="Added files",
        )

    def import_folder(self) -> None:
        if not self._has_controller():
            return

        path = QFileDialog.getExistingDirectory(
            self._window,
            "Import Folder",
            self._default_import_directory(),
        )
        if not path:
            return

        self._import_sources(
            [path],
            recursive=True,
            preserve_structure=True,
            source_label="Imported folder",
        )

    def _has_controller(self) -> bool:
        if self._window.controller is not None:
            return True
        self._window._status("Import unavailable: controller not configured")
        return False

    def _import_sources(
        self,
        sources: list[str],
        *,
        recursive: bool,
        preserve_structure: bool,
        source_label: str,
    ) -> None:
        controller = self._window.controller
        if controller is None:
            self._window._status("Import unavailable: controller not configured")
            return

        try:
            summary = controller.import_local_sources(
                sources,
                recursive=recursive,
                preserve_structure=preserve_structure,
                flatten=not preserve_structure,
                dedupe_by_hash=True,
            )
        except Exception as exc:
            self._window._show_error("Import Failed", str(exc))
            self._window._status(f"Import failed: {exc}")
            return

        assets = list(summary.assets)
        if assets:
            self._window._register_assets(assets, set_active=True)

        parts = [f"{source_label}: {len(assets)} asset(s)"]
        if summary.duplicates:
            parts.append(f"{len(summary.duplicates)} duplicate(s) skipped")
        if summary.unsupported:
            parts.append(f"{len(summary.unsupported)} unsupported file(s) skipped")
        if summary.failed:
            parts.append(f"{len(summary.failed)} source(s) failed")
            self._window._show_error(
                "Some Sources Could Not Be Added",
                "\n".join(summary.failed[:20]),
            )
        if not assets and not summary.duplicates and not summary.unsupported and not summary.failed:
            parts = [f"{source_label}: no importable files found"]
        self._window._status(" | ".join(parts))

    def _default_import_directory(self) -> str:
        current_export = self._window.export_bar.export_directory()
        if current_export:
            return current_export

        controller = self._window.controller
        app_paths = getattr(controller, "app_paths", None) if controller is not None else None
        if app_paths is not None:
            return str(app_paths.root)
        return str(Path.home())

