"""Local file/folder/ZIP import coordinator for the main window."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from image_engine_app.engine.ingest.zip_extract import ZipExtractError, extract_images_only

from PySide6.QtWidgets import QFileDialog


class LocalImportCoordinator:
    """Owns local import actions exposed from the top toolbar."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def import_files(self) -> None:
        if not self._has_controller():
            return

        paths, _selected = QFileDialog.getOpenFileNames(
            self._window,
            "Import Image Files",
            self._default_import_directory(),
            self._window._local_file_dialog_filter(),
        )
        if not paths:
            return

        self._import_sources(
            paths,
            recursive=False,
            preserve_structure=False,
            source_label="Imported files",
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

    def import_zip_archive(self) -> None:
        if not self._has_controller():
            return

        path, _selected = QFileDialog.getOpenFileName(
            self._window,
            "Import ZIP Archive",
            self._default_import_directory(),
            "ZIP Files (*.zip);;All Files (*)",
        )
        if not path:
            return

        zip_path = Path(path)
        try:
            extracted = self._extract_zip_images(zip_path)
        except (ZipExtractError, OSError, ValueError) as exc:
            self._window._show_error("ZIP Import Failed", str(exc))
            self._window._status(f"ZIP import failed: {exc}")
            return

        if not extracted:
            self._window._status(f"ZIP import skipped: no supported images in {zip_path.name}")
            return

        self._import_sources(
            extracted,
            recursive=False,
            preserve_structure=False,
            source_label=f"Imported ZIP: {zip_path.name}",
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
        if not assets and not summary.duplicates and not summary.unsupported:
            parts = [f"{source_label}: no importable files found"]
        self._window._status(" | ".join(parts))

    def _extract_zip_images(self, zip_path: Path) -> list[str]:
        allowed_exts = set(self._window._supported_local_extensions())
        extract_root = self._zip_extract_root()
        extract_root.mkdir(parents=True, exist_ok=True)
        extract_dir = extract_root / f"{zip_path.stem}_{uuid4().hex[:8]}"
        return extract_images_only(str(zip_path), str(extract_dir), allowed_exts=allowed_exts)

    def _zip_extract_root(self) -> Path:
        controller = self._window.controller
        app_paths = getattr(controller, "app_paths", None) if controller is not None else None
        if app_paths is not None:
            return Path(app_paths.cache) / "_local_zip_import"
        return Path.cwd() / ".cache" / "_local_zip_import"

    def _default_import_directory(self) -> str:
        current_export = self._window.export_bar.export_directory()
        if current_export:
            return current_export

        controller = self._window.controller
        app_paths = getattr(controller, "app_paths", None) if controller is not None else None
        if app_paths is not None:
            return str(app_paths.root)
        return str(Path.home())

