"""Tests for batch coordinator worker option handoff."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PySide6.QtCore import QCoreApplication
except Exception:  # pragma: no cover - optional dependency in some environments
    QCoreApplication = None  # type: ignore[assignment]

from engine.models import AssetRecord, ExportFormat  # noqa: E402
from ui.main_window.batch_coordinator import BatchCoordinator, _BatchRunWorker  # noqa: E402


@unittest.skipIf(QCoreApplication is None, "PySide6 not installed")
class BatchCoordinatorWorkerTests(unittest.TestCase):
    def test_worker_forwards_export_options_to_controller(self) -> None:
        app = QCoreApplication.instance()
        owns_app = app is None
        if app is None:
            app = QCoreApplication([])

        class FakeController:
            def __init__(self) -> None:
                self.assets = None
                self.kwargs = None

            def run_batch(self, assets, **kwargs):  # noqa: ANN001
                self.assets = list(assets)
                self.kwargs = dict(kwargs)
                return {"ok": True}

        controller = FakeController()
        worker = _BatchRunWorker(
            controller=controller,
            assets=[AssetRecord(id="asset-1", original_name="sprite.png")],
            preview_skip_mode=False,
            auto_export=True,
            auto_preset=False,
            export_name_template="{group}_{index:03d}_{stem}",
            avoid_overwrite=False,
            export_dir="C:/Exports/Batched",
        )

        finished_reports: list[object] = []
        worker.finished_report.connect(finished_reports.append)
        worker.run()

        self.assertEqual([asset.id for asset in controller.assets], ["asset-1"])
        self.assertIsNotNone(controller.kwargs)
        self.assertEqual(controller.kwargs["preview_skip_mode"], False)
        self.assertEqual(controller.kwargs["auto_export"], True)
        self.assertEqual(controller.kwargs["auto_preset"], False)
        self.assertEqual(controller.kwargs["export_name_template"], "{group}_{index:03d}_{stem}")
        self.assertEqual(controller.kwargs["avoid_overwrite"], False)
        self.assertEqual(controller.kwargs["export_dir"], "C:/Exports/Batched")
        self.assertTrue(finished_reports)

        if owns_app and app is not None:
            app.quit()


class BatchCoordinatorSelectionTests(unittest.TestCase):
    class _FakeController:
        def __init__(self) -> None:
            self.applied_presets: list[tuple[str, str]] = []

        def apply_named_preset(self, asset, preset_name: str):  # noqa: ANN001
            self.applied_presets.append((str(getattr(asset, "id", "")), str(preset_name)))
            return SimpleNamespace(preset_name=preset_name, requires_apply=False, queued_heavy_jobs=0)

    class _FakeExportBar:
        def __init__(self, value: str | None) -> None:
            self._value = value

        def export_directory(self) -> str | None:
            return self._value

    class _FakeExportCoordinator:
        def __init__(self) -> None:
            self.remembered: list[str] = []

        def remember_export_directory(self, path: str) -> None:
            self.remembered.append(path)

    class _FakeUIState:
        def __init__(self, active_asset: AssetRecord | None) -> None:
            self.active_asset = active_asset

    class _FakeDialog:
        def __init__(self) -> None:
            self.running_states: list[bool] = []

        def set_running(self, is_running: bool) -> None:
            self.running_states.append(bool(is_running))

        def update_from_event(self, _event: object) -> None:
            return

        def update_from_report(self, _report: object) -> None:
            return

    class _FakeWindow:
        def __init__(self) -> None:
            self.controller = BatchCoordinatorSelectionTests._FakeController()
            self._workspace_assets = [
                AssetRecord(id="asset-a", original_name="a.png"),
                AssetRecord(id="asset-b", original_name="b.png"),
            ]
            self._batch_thread = None
            self.batch_manager_dialog = BatchCoordinatorSelectionTests._FakeDialog()
            self.export_bar = BatchCoordinatorSelectionTests._FakeExportBar("C:/Exports/FromExportBar")
            self._export_coordinator = BatchCoordinatorSelectionTests._FakeExportCoordinator()
            self.ui_state = BatchCoordinatorSelectionTests._FakeUIState(active_asset=self._workspace_assets[0])
            self.status_messages: list[str] = []

        def _status(self, text: str) -> None:
            self.status_messages.append(text)

        def _refresh_export_prediction(self) -> None:
            return

        def _show_error(self, _title: str, _message: str) -> None:
            return

    def test_on_run_requested_uses_selected_asset_ids_and_export_dir(self) -> None:
        window = self._FakeWindow()
        window.ui_state.active_asset.edit_state.settings.export.format = ExportFormat.PNG
        window._workspace_assets[1].edit_state.settings.export.format = ExportFormat.JPG

        coordinator = BatchCoordinator(window)
        captured: dict[str, object] = {}

        def _capture_start_worker(**kwargs):  # noqa: ANN003
            captured.update(kwargs)

        coordinator.start_worker = _capture_start_worker  # type: ignore[method-assign]

        coordinator.on_run_requested(
            SimpleNamespace(
                auto_preset=True,
                auto_export=True,
                preview_skip_mode=True,
                export_name_template="{stem}",
                avoid_overwrite=True,
                export_directory="C:/Exports/ChosenInBatch",
                selected_asset_ids=("asset-b",),
            )
        )

        self.assertIn("assets", captured)
        selected_assets = captured["assets"]
        self.assertEqual([asset.id for asset in selected_assets], ["asset-b"])
        self.assertEqual(captured["export_dir"], "C:/Exports/ChosenInBatch")
        self.assertEqual(window._workspace_assets[1].edit_state.settings.export.format, ExportFormat.PNG)
        self.assertEqual(window._export_coordinator.remembered[-1], "C:/Exports/ChosenInBatch")
        self.assertTrue(window.batch_manager_dialog.running_states)
        self.assertIn("Batch run started", window.status_messages[-1])

    def test_on_run_requested_can_apply_active_edits_and_selected_preset(self) -> None:
        window = self._FakeWindow()
        active = window._workspace_assets[0]
        target = window._workspace_assets[1]

        active.edit_state.settings.cleanup.denoise = 0.37
        target.edit_state.settings.cleanup.denoise = 0.0

        coordinator = BatchCoordinator(window)
        captured: dict[str, object] = {}

        def _capture_start_worker(**kwargs):  # noqa: ANN003
            captured.update(kwargs)

        coordinator.start_worker = _capture_start_worker  # type: ignore[method-assign]
        coordinator.on_run_requested(
            SimpleNamespace(
                auto_preset=False,
                auto_export=False,
                preview_skip_mode=True,
                export_name_template="{stem}",
                avoid_overwrite=True,
                export_directory=None,
                selected_asset_ids=("asset-b",),
                apply_active_edits=True,
                apply_selected_preset=True,
                selected_preset_name="Photo Recover",
            )
        )

        self.assertIn("assets", captured)
        self.assertEqual([asset.id for asset in captured["assets"]], ["asset-b"])
        self.assertAlmostEqual(target.edit_state.settings.cleanup.denoise, 0.37, places=3)
        self.assertIn(("asset-b", "Photo Recover"), window.controller.applied_presets)

    def test_on_run_requested_skips_when_preset_apply_enabled_without_choice(self) -> None:
        window = self._FakeWindow()
        coordinator = BatchCoordinator(window)
        was_called = {"value": False}

        def _capture_start_worker(**_kwargs):  # noqa: ANN003
            was_called["value"] = True

        coordinator.start_worker = _capture_start_worker  # type: ignore[method-assign]
        coordinator.on_run_requested(
            SimpleNamespace(
                auto_preset=False,
                auto_export=False,
                preview_skip_mode=True,
                export_name_template="{stem}",
                avoid_overwrite=True,
                export_directory=None,
                selected_asset_ids=("asset-b",),
                apply_active_edits=False,
                apply_selected_preset=True,
                selected_preset_name="",
            )
        )

        self.assertFalse(was_called["value"])
        self.assertIn("choose a preset", window.status_messages[-1].lower())

    def test_on_run_requested_uses_export_bar_folder_when_batch_folder_blank(self) -> None:
        window = self._FakeWindow()
        coordinator = BatchCoordinator(window)
        captured: dict[str, object] = {}

        def _capture_start_worker(**kwargs):  # noqa: ANN003
            captured.update(kwargs)

        coordinator.start_worker = _capture_start_worker  # type: ignore[method-assign]
        coordinator.on_run_requested(
            SimpleNamespace(
                auto_preset=True,
                auto_export=True,
                preview_skip_mode=True,
                export_name_template="{stem}",
                avoid_overwrite=True,
                export_directory="",
                selected_asset_ids=("asset-a",),
            )
        )

        self.assertEqual(captured["export_dir"], "C:/Exports/FromExportBar")

    def test_on_run_requested_skips_when_no_items_selected(self) -> None:
        window = self._FakeWindow()
        coordinator = BatchCoordinator(window)
        was_called = {"value": False}

        def _capture_start_worker(**_kwargs):  # noqa: ANN003
            was_called["value"] = True

        coordinator.start_worker = _capture_start_worker  # type: ignore[method-assign]
        coordinator.on_run_requested(
            SimpleNamespace(
                auto_preset=True,
                auto_export=False,
                preview_skip_mode=True,
                export_name_template="{stem}",
                avoid_overwrite=True,
                export_directory=None,
                selected_asset_ids=(),
            )
        )

        self.assertFalse(was_called["value"])
        self.assertIn("select at least one", window.status_messages[-1].lower())


class BatchCoordinatorUiSafetyTests(unittest.TestCase):
    class _ExplodingDialog:
        def set_running(self, _is_running: bool) -> None:
            return

        def update_from_event(self, _event: object) -> None:
            raise RuntimeError("bad event payload")

        def update_from_report(self, _report: object) -> None:
            raise RuntimeError("bad report payload")

    class _Window:
        def __init__(self) -> None:
            self.batch_manager_dialog = BatchCoordinatorUiSafetyTests._ExplodingDialog()
            self.status_messages: list[str] = []
            self._batch_thread = None
            self._batch_worker = None

        def _status(self, text: str) -> None:
            self.status_messages.append(str(text))

        def _refresh_export_prediction(self) -> None:
            return

    def test_ui_update_errors_are_caught_and_reported(self) -> None:
        window = self._Window()
        coordinator = BatchCoordinator(window)

        coordinator.on_progress_event(SimpleNamespace(event_type="item_progress"))
        coordinator.on_run_finished(SimpleNamespace(cancelled=False, processed_count=0, failed_count=0))

        joined = "\n".join(window.status_messages)
        self.assertIn("Batch progress UI warning", joined)
        self.assertIn("Batch report UI warning", joined)


if __name__ == "__main__":
    unittest.main()



