"""Web Sources coordinator regression tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


from image_engine_app.app.web_sources_models import Confidence, DownloadReport, ScanResults, WebIndexLink, WebItem  # noqa: E402
from image_engine_app.engine.models import AssetRecord, SourceType  # noqa: E402
from image_engine_app.ui.main_window import web_sources_coordinator as coordinator_module  # noqa: E402
from image_engine_app.ui.main_window.web_sources_coordinator import WebSourcesCoordinator  # noqa: E402


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
        self.LINKED_PAGE_SCAN_CAP = 100
        self.status_messages: list[str] = []
        self.results: ScanResults | None = None
        self.index_links: tuple[WebIndexLink, ...] = ()
        self.sources: list[dict] = []
        self.confirm_large_scan_result = True
        self.confirm_large_scan_calls: list[tuple[int, int]] = []

    def set_status(self, msg: str) -> None:
        self.status_messages.append(str(msg))

    def set_results(self, results: ScanResults) -> None:
        self.results = results

    def set_index_links(self, links: tuple[WebIndexLink, ...]) -> None:
        self.index_links = tuple(links)

    def confirm_large_linked_page_scan(self, page_count: int, *, cap: int | None = None) -> bool:
        self.confirm_large_scan_calls.append((int(page_count), int(cap or 0)))
        return bool(self.confirm_large_scan_result)

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

    def __init__(self) -> None:
        self.scanned_page_urls: list[str] = []

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

    def discover_web_source_index_links(self, *_args, **_kwargs) -> tuple[WebIndexLink, ...]:
        return (
            WebIndexLink(
                label="HOME Sprites: Gen 1",
                url="https://example.com/home-gen-1",
                source_page="https://example.com/index",
            ),
            WebIndexLink(
                label="Animations",
                url="https://example.com/animations",
                source_page="https://example.com/index",
            ),
        )

    def scan_web_source_pages(self, page_urls: list[str], *_args, **_kwargs) -> ScanResults:
        self.scanned_page_urls = list(page_urls)
        return ScanResults(
            items=tuple(
                WebItem(
                    url=f"https://cdn.example.com/{index}.png",
                    name=f"{index}.png",
                    ext=".png",
                    confidence=Confidence.DIRECT,
                    source_page=url,
                )
                for index, url in enumerate(page_urls, start=1)
            ),
            filtered_count=0,
        )

    def download_web_sources_items(self, *_args, **_kwargs) -> DownloadReport:
        asset = AssetRecord(
            source_type=SourceType.WEBPAGE_ITEM,
            source_uri="https://cdn.example.com/a.png",
            cache_path="cache/a.png",
            original_name="a.png",
        )
        return DownloadReport(
            downloaded=("a.png",),
            skipped=(),
            failed=(),
            assets=(asset,),
            cancelled=False,
        )


class _ManyLinksController(_FakeController):
    def discover_web_source_index_links(self, *_args, **_kwargs) -> tuple[WebIndexLink, ...]:
        return tuple(
            WebIndexLink(
                label=f"Page {index}",
                url=f"https://example.com/page-{index}",
                source_page="https://example.com/index",
            )
            for index in range(205)
        )


class _Win10013Controller:
    app_paths = None

    def scan_web_sources_area(self, *_args, **_kwargs) -> ScanResults:
        raise RuntimeError("<urlopen error [WinError 10013] blocked>")


class _Http403Controller:
    app_paths = None

    def scan_web_sources_area(self, *_args, **_kwargs) -> ScanResults:
        raise RuntimeError("HTTP Error 403: Forbidden")


class _MalformedAssetsController(_FakeController):
    def download_web_sources_items(self, *_args, **_kwargs) -> DownloadReport:
        return DownloadReport(
            downloaded=("a.png",),
            skipped=(),
            failed=(),
            assets=("not-an-asset",),  # type: ignore[arg-type]
            cancelled=False,
        )


class _FakeWindow:
    def __init__(self, controller: object | None = None) -> None:
        self.controller = controller if controller is not None else _FakeController()
        self.web_sources_panel = _FakePanel()
        self.status_updates: list[str] = []
        self.register_calls: list[tuple[list[AssetRecord], bool]] = []

    def _status(self, msg: str) -> None:
        self.status_updates.append(str(msg))

    def _register_assets(self, assets: list[AssetRecord], *, set_active: bool) -> None:
        self.register_calls.append((list(assets), bool(set_active)))


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

    def test_index_scan_sets_discovered_links(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_index_links_requested(
                {
                    "index_url": "https://example.com/index",
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

        self.assertEqual(2, len(window.web_sources_panel.index_links))
        self.assertTrue(any("index scan complete" in msg.lower() for msg in window.status_updates))

    def test_multi_scan_sets_merged_results(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_multi_scan_requested(
                {
                    "pages": [
                        {
                            "label": "HOME Sprites: Gen 1",
                            "url": "https://example.com/home-gen-1",
                            "source_page": "https://example.com/index",
                        },
                        {
                            "label": "Animations",
                            "url": "https://example.com/animations",
                            "source_page": "https://example.com/index",
                        },
                    ],
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
        assert window.web_sources_panel.results is not None
        self.assertEqual(2, len(window.web_sources_panel.results.items))
        self.assertTrue(any("multi-page scan complete" in msg.lower() for msg in window.status_updates))

    def test_index_scan_all_discovers_links_and_scans_every_page(self) -> None:
        window = _FakeWindow()
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_index_scan_all_requested(
                {
                    "index_url": "https://example.com/index",
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

        self.assertEqual(2, len(window.web_sources_panel.index_links))
        self.assertIsNotNone(window.web_sources_panel.results)
        assert window.web_sources_panel.results is not None
        self.assertEqual(2, len(window.web_sources_panel.results.items))
        self.assertTrue(any("linked-page scan complete" in msg.lower() for msg in window.status_updates))

    def test_index_scan_all_warns_and_caps_large_link_sets(self) -> None:
        controller = _ManyLinksController()
        window = _FakeWindow(controller=controller)
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_index_scan_all_requested(
                {
                    "index_url": "https://example.com/index",
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

        self.assertEqual([(205, 100)], window.web_sources_panel.confirm_large_scan_calls)
        self.assertEqual(100, len(controller.scanned_page_urls))
        self.assertEqual("https://example.com/page-0", controller.scanned_page_urls[0])
        self.assertEqual("https://example.com/page-99", controller.scanned_page_urls[-1])

    def test_index_scan_all_can_be_cancelled_after_large_link_warning(self) -> None:
        controller = _ManyLinksController()
        window = _FakeWindow(controller=controller)
        window.web_sources_panel.confirm_large_scan_result = False
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_index_scan_all_requested(
                {
                    "index_url": "https://example.com/index",
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

        self.assertEqual([(205, 100)], window.web_sources_panel.confirm_large_scan_calls)
        self.assertEqual([], controller.scanned_page_urls)
        self.assertTrue(any("cancelled before starting" in msg.lower() for msg in window.status_updates))

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

    def test_scan_http_403_maps_to_friendly_message(self) -> None:
        window = _FakeWindow(controller=_Http403Controller())
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
        self.assertIn("HTTP 403 (Forbidden)", latest)

    def test_download_registers_assets_into_workspace(self) -> None:
        window = _FakeWindow(controller=_FakeController())
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_download_requested(
                {
                    "items": [
                        {
                            "url": "https://cdn.example.com/a.png",
                            "name": "a.png",
                            "ext": ".png",
                            "confidence": "direct",
                        }
                    ],
                    "target": "normal",
                    "smart": {
                        "show_likely": False,
                        "auto_sort": False,
                        "skip_duplicates": True,
                        "allow_zip": True,
                    },
                }
            )

        self.assertEqual(1, len(window.register_calls))
        assets, set_active = window.register_calls[0]
        self.assertTrue(set_active)
        self.assertEqual(1, len(assets))
        self.assertIn("workspace loaded 1", window.web_sources_panel.status_messages[-1].lower())

    def test_download_with_malformed_assets_does_not_crash(self) -> None:
        window = _FakeWindow(controller=_MalformedAssetsController())
        coordinator = WebSourcesCoordinator(window)

        with patch.object(coordinator_module, "QProgressDialog", _FakeProgressDialog), patch.object(
            coordinator_module,
            "QApplication",
            _FakeApp,
        ):
            coordinator.on_download_requested(
                {
                    "items": [
                        {
                            "url": "https://cdn.example.com/a.png",
                            "name": "a.png",
                            "ext": ".png",
                            "confidence": "direct",
                        }
                    ],
                    "target": "normal",
                    "smart": {
                        "show_likely": False,
                        "auto_sort": False,
                        "skip_duplicates": True,
                        "allow_zip": True,
                    },
                }
            )

        self.assertEqual([], window.register_calls)
        self.assertIn("workspace loaded 0", window.web_sources_panel.status_messages[-1].lower())

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


