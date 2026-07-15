"""Local import coordinator tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


try:
    from PySide6.QtWidgets import QFileDialog
except Exception:  # pragma: no cover - optional dependency in some environments
    QFileDialog = None  # type: ignore[assignment]

from image_engine_app.app.ui_controller import LocalImportSummary  # noqa: E402
from image_engine_app.engine.ingest.local_ingest import LocalIngestResult  # noqa: E402
from image_engine_app.engine.ingest.zip_extract import ZipExtractError  # noqa: E402
from image_engine_app.engine.models import AssetRecord, SourceType  # noqa: E402
from image_engine_app.ui.main_window.local_import_coordinator import LocalImportCoordinator  # noqa: E402


class _FakeExportBar:
    def __init__(self, export_dir: str = "") -> None:
        self._export_dir = export_dir

    def export_directory(self) -> str:
        return self._export_dir


class _FakeController:
    def __init__(self, summary: LocalImportSummary) -> None:
        self.summary = summary
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.app_paths = None

    def import_local_sources(self, sources: list[str], **kwargs: object) -> LocalImportSummary:
        self.calls.append((list(sources), dict(kwargs)))
        return self.summary


class _FakeWindow:
    def __init__(self, *, controller: _FakeController | None) -> None:
        self.controller = controller
        self.export_bar = _FakeExportBar("")
        self.status_messages: list[str] = []
        self.error_messages: list[tuple[str, str]] = []
        self.registered_assets: list[tuple[list[AssetRecord], bool]] = []

    @staticmethod
    def _supported_local_extensions() -> list[str]:
        return [".png", ".jpg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff"]

    @staticmethod
    def _local_import_dialog_filter() -> str:
        return "Supported Images and ZIPs (*.png *.jpg *.zip);;All Files (*)"

    def _register_assets(self, assets: list[AssetRecord], *, set_active: bool) -> None:
        self.registered_assets.append((list(assets), bool(set_active)))

    def _status(self, text: str) -> None:
        self.status_messages.append(text)

    def _show_error(self, title: str, message: str) -> None:
        self.error_messages.append((title, message))


def _asset(asset_id: str = "asset-1") -> AssetRecord:
    return AssetRecord(
        id=asset_id,
        source_type=SourceType.FILE,
        source_uri=f"C:/images/{asset_id}.png",
        cache_path=f"C:/images/{asset_id}.png",
        original_name=f"{asset_id}.png",
    )


@unittest.skipIf(QFileDialog is None, "PySide6 not installed")
class LocalImportCoordinatorTests(unittest.TestCase):
    def test_import_files_registers_assets_and_reports_summary(self) -> None:
        summary = LocalImportSummary(
            assets=[_asset("asset-a")],
            duplicates=[Path("C:/images/dupe.png")],
            unsupported=[Path("C:/images/not-image.txt")],
            raw_result=LocalIngestResult(),
        )
        controller = _FakeController(summary)
        window = _FakeWindow(controller=controller)
        coordinator = LocalImportCoordinator(window)

        with patch(
            "image_engine_app.ui.main_window.local_import_coordinator.QFileDialog.getOpenFileNames",
            return_value=(["C:/images/asset-a.png"], ""),
        ):
            coordinator.import_files()

        self.assertEqual(1, len(controller.calls))
        imported_sources, kwargs = controller.calls[0]
        self.assertEqual(["C:/images/asset-a.png"], imported_sources)
        self.assertEqual(False, kwargs.get("recursive"))
        self.assertEqual(False, kwargs.get("preserve_structure"))
        self.assertEqual(True, kwargs.get("flatten"))
        self.assertEqual(True, kwargs.get("dedupe_by_hash"))
        self.assertEqual(1, len(window.registered_assets))
        self.assertIn("Added files: 1 asset(s)", window.status_messages[-1])
        self.assertIn("1 duplicate(s) skipped", window.status_messages[-1])
        self.assertIn("1 unsupported file(s) skipped", window.status_messages[-1])

    def test_import_files_expands_zip_and_regular_images_through_one_call(self) -> None:
        summary = LocalImportSummary(
            assets=[_asset("asset-a")],
            duplicates=[],
            unsupported=[],
            raw_result=LocalIngestResult(),
        )
        controller = _FakeController(summary)
        window = _FakeWindow(controller=controller)
        coordinator = LocalImportCoordinator(window)

        with patch(
            "image_engine_app.ui.main_window.local_import_coordinator.QFileDialog.getOpenFileNames",
            return_value=(["C:/images/direct.png", "C:/images/bundle.zip"], ""),
        ):
            with patch.object(
                coordinator,
                "_extract_zip_images",
                return_value=["C:/cache/unpacked-a.png", "C:/cache/unpacked-b.gif"],
            ):
                coordinator.import_files()

        self.assertEqual(1, len(controller.calls))
        imported_sources, _kwargs = controller.calls[0]
        self.assertEqual(
            ["C:/images/direct.png", "C:/cache/unpacked-a.png", "C:/cache/unpacked-b.gif"],
            imported_sources,
        )

    def test_import_files_reports_zip_extract_error(self) -> None:
        summary = LocalImportSummary(
            assets=[],
            duplicates=[],
            unsupported=[],
            raw_result=LocalIngestResult(),
        )
        controller = _FakeController(summary)
        window = _FakeWindow(controller=controller)
        coordinator = LocalImportCoordinator(window)

        with patch(
            "image_engine_app.ui.main_window.local_import_coordinator.QFileDialog.getOpenFileNames",
            return_value=(["C:/images/broken.zip"], ""),
        ):
            with patch(
                "image_engine_app.ui.main_window.local_import_coordinator.extract_images_only",
                side_effect=ZipExtractError("Bad ZIP file: C:/images/broken.zip"),
            ):
                coordinator.import_files()

        self.assertEqual([], controller.calls)
        self.assertEqual([], window.registered_assets)
        self.assertEqual("Some Files Could Not Be Added", window.error_messages[-1][0])
        self.assertIn("broken.zip", window.error_messages[-1][1])
        self.assertEqual("Add files failed: no supported images were found", window.status_messages[-1])

    def test_import_without_controller_shows_status(self) -> None:
        window = _FakeWindow(controller=None)
        coordinator = LocalImportCoordinator(window)
        coordinator.import_folder()
        self.assertEqual("Import unavailable: controller not configured", window.status_messages[-1])


if __name__ == "__main__":
    unittest.main()



