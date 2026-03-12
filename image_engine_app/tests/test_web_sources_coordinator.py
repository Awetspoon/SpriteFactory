"""Web Sources coordinator regression tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.web_sources_models import Confidence, ScanResults, WebItem  # noqa: E402
from ui.main_window import web_sources_coordinator as coordinator_module  # noqa: E402
from ui.main_window.web_sources_coordinator import WebSourcesCoordinator  # noqa: E402


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:  # noqa: ANN001
        self._callbacks.append(callback)

    def disconnect(self, callback) -> None:  # noqa: ANN001
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def emit(self) -> None:
        for callback in tuple(self._callbacks):
            callback()


class _FakeProgressDialog:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        self.canceled = _FakeSignal()
        self._max = 1
        self._value = 0

    def setWindowTitle(self, _title: str) -> None:
        return

    def setWindowModality(self, _modality) -> None:  # noqa: ANN001
        return

    def setMinimumDuration(self, _ms: int) -> None:
        return

    def setAutoClose(self, _enabled: bool) -> None:
        return

    def setAutoReset(self, _enabled: bool) -> None:
        return

    def setLabelText(self, _text: str) -> None:
        return

    def setValue(self, value: int) -> None:
        self._value = int(value)

    def value(self) -> int:
        return self._value

    def setMaximum(self, value: int) -> None:
        self._max = int(value)

    def maximum(self) -> int:
        return self._max

    def show(self) -> None:
        return

    def hide(self) -> None:
        return

    def deleteLater(self) -> None:
        return

    def close(self) -> None:
        # Backward-compatible noop for older coordinator behavior.
        return


class _FakeApp:
    @staticmethod
    def processEvents() -> None:
        return


class _FakePanel:
    def __init__(self) -> None:
        self.status_messages: list[str] = []
        self.results: ScanResults | None = None
        self.sources: list[dict] = []

    def set_status(self, msg: str) -> None:
        self.status_messages.append(str(msg))

    def set_results(self, results: ScanResults) -> None:
        self.results = results

    def set_sources(
        self,
        *,
        websites: list[dict],
        selected_website_id: str | None = None,
        selected_area_id: str | None = None,
    ) -> None:
        _ = (selected_website_id, selected_area_id)
        self.sources = list(websites)

    def selected_source_ids(self) -> tuple[str | None, str | None]:
        return None, None

    def smart_options(self):  # noqa: ANN001
        raise AssertionError("smart_options should not be called in this test")

    def sources_registry(self) -> list[dict]:
        return list(self.sources)


class _FakeController:
    app_paths = None

    def load_web_sources_registry(self, registry=None):  # noqa: ANN001
        if registry is None:
            return []
        if isinstance(registry, list):
            return list(registry)
        return []

    def scan_web_sources_area(self, *_args, **_kwargs) -> ScanResults:
        return ScanResults(
            items=(
                WebItem(
                    url="https://cdn.example.com/a.png",
                    name="a.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                ),
            ),
            filtered_count=0,
        )


class _Win10013Controller:
    app_paths = None

    def scan_web_sources_area(self, *_args, **_kwargs) -> ScanResults:
        raise RuntimeError("<urlopen error [WinError 10013] blocked>")


class _FakeWindow:
    def __init__(self, controller: object | None = None) -> None:
        self.controller = controller if controller is not None else _FakeController()
        self.web_sources_panel = _FakePanel()
        self.status_updates: list[str] = []

    def _status(self, msg: str) -> None:
        self.status_updates.append(str(msg))


class WebSourcesCoordinatorRegressionTests(unittest.TestCase):
    def test_scan_not_marked_cancelled_when_progress_close_emits_canceled_signal(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_scan_requested(
                {
                    "area_url": "https://example.com/gallery",
                    "website_id": None,
                    "area_id": None,
                    "smart": {
                        "show_likely": False,
                        "auto_sort": False,
                        "skip_duplicates": True,
                        "allow_zip": True,
                    },
                }
            )

        self.assertIsNotNone(window.web_sources_panel.results)
        self.assertTrue(any("scan complete" in msg.lower() for msg in window.status_updates))
        self.assertFalse(any("scan cancelled" in msg.lower() for msg in window.status_updates))

    def test_scan_winerror_10013_maps_to_friendly_message(self) -> None:
        window = _FakeWindow(controller=_Win10013Controller())
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_scan_requested(
                {
                    "area_url": "https://example.com/gallery",
                    "website_id": None,
                    "area_id": None,
                    "smart": {
                        "show_likely": False,
                        "auto_sort": False,
                        "skip_duplicates": True,
                        "allow_zip": True,
                    },
                }
            )

        self.assertTrue(window.web_sources_panel.status_messages)
        latest = window.web_sources_panel.status_messages[-1]
        self.assertIn("Scan failed:", latest)
        self.assertIn("Windows blocked network access (WinError 10013)", latest)

    def test_network_diagnostics_updates_status(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(
            WebSourcesCoordinator,
            "_diagnostics_summary_for_url",
            return_value="Network diagnostics OK: DNS + TCP + HTTP 200 for example.com:443",
        ):
            coordinator.on_network_diagnostics_requested({"area_url": "https://example.com/sprites"})

        self.assertTrue(window.web_sources_panel.status_messages)
        self.assertIn("Network diagnostics OK", window.web_sources_panel.status_messages[-1])
        self.assertTrue(window.status_updates)
        self.assertIn("Network diagnostics OK", window.status_updates[-1])

    def test_network_diagnostics_error_is_mapped(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(
            WebSourcesCoordinator,
            "_diagnostics_summary_for_url",
            side_effect=RuntimeError("<urlopen error [WinError 10013] blocked>"),
        ):
            coordinator.on_network_diagnostics_requested({"area_url": "https://example.com/sprites"})

        self.assertTrue(window.web_sources_panel.status_messages)
        self.assertIn("Network diagnostics failed", window.web_sources_panel.status_messages[-1])
        self.assertIn("WinError 10013", window.web_sources_panel.status_messages[-1])



    def test_registry_changed_allows_empty_list_and_clears_sources(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        coordinator.on_registry_changed([])

        self.assertEqual([], window.web_sources_panel.sources)
        self.assertFalse(
            any("empty after validation" in msg.lower() for msg in window.web_sources_panel.status_messages)
        )

if __name__ == "__main__":
    unittest.main()







