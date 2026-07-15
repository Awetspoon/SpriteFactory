"""Web Sources panel workflow tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
except Exception:  # pragma: no cover - optional UI dependency
    Qt = None  # type: ignore[assignment]
    QApplication = None  # type: ignore[assignment]
    QMessageBox = None  # type: ignore[assignment]

from image_engine_app.app.web_sources_models import (
    Confidence,
    ScanOrigin,
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebIndexLink,
    WebItem,
    WebLinkDiscoveryRequest,
    WebScanRequest,
)
from image_engine_app.ui.main_window.web_sources_panel import WebSourcesPanel


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class WebSourcesPanelTests(unittest.TestCase):
    def _setup_panel(self) -> tuple[QApplication, bool, WebSourcesPanel]:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance()
        owns_app = app is None
        if app is None:
            app = QApplication([])
        return app, owns_app, WebSourcesPanel()

    @staticmethod
    def _close(app: QApplication, owns_app: bool, panel: WebSourcesPanel) -> None:
        panel.close()
        if owns_app:
            app.quit()

    @staticmethod
    def _item(name: str, *, source: str = "https://example.com/page") -> WebItem:
        return WebItem(
            url=f"https://cdn.example.com/{name}",
            name=name,
            ext="." + name.rsplit(".", 1)[-1].lower(),
            confidence=Confidence.DIRECT,
            source_page=source,
        )

    @staticmethod
    def _registry() -> list[dict]:
        return [
            {
                "id": "site_a",
                "name": "site-a.example",
                "areas": [
                    {"id": "page_a", "label": "Sprites A", "url": "https://site-a.example/sprites"},
                    {"id": "page_b", "label": "Sprites B", "url": "https://site-a.example/other"},
                ],
            },
            {
                "id": "site_b",
                "name": "site-b.example",
                "areas": [
                    {"id": "page_c", "label": "Sprites C", "url": "https://site-b.example/sprites"},
                ],
            },
        ]

    def test_rebuild_has_no_retired_hidden_controls_or_scan_signals(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            for name in ("_website", "_area", "_saved_page", "_manual_links"):
                self.assertFalse(hasattr(panel, name))
            for name in ("multi_scan_requested", "index_scan_all_requested", "index_links_requested"):
                self.assertFalse(hasattr(panel, name))
            self.assertIsNotNone(panel._saved_tree)
            self.assertIsNotNone(panel._results)
        finally:
            self._close(app, owns_app, panel)

    def test_each_more_menu_owns_only_its_section_actions(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            entered = [action.text() for action in panel._entered_more_btn.menu().actions() if action.text()]
            saved = [action.text() for action in panel._saved_more_btn.menu().actions() if action.text()]
            linked = [action.text() for action in panel._links_more_btn.menu().actions() if action.text()]
            found = [action.text() for action in panel._results_more_btn.menu().actions() if action.text()]

            self.assertEqual(
                ["Save Entered Pages", "Check First URL", "Include uncertain image links", "Clear Entered URLs"],
                entered,
            )
            self.assertEqual(
                [
                    "Check Current Page",
                    "Clear Checked Pages",
                    "Check Current Page Connection",
                    "Remove Current Page",
                    "Remove Current Website",
                ],
                saved,
            )
            self.assertEqual(
                ["Select Visible Pages", "Clear Page Selection", "Clear Linked Pages"],
                linked,
            )
            self.assertEqual(
                ["Select All Visible Files", "Clear File Selection", "Clear Found Files"],
                found,
            )
        finally:
            self._close(app, owns_app, panel)

    def test_entered_pages_accept_multiple_domains_and_emit_one_scan_request(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText(
                "example.com/sprites\nhttps://other.example/art\nhttps://other.example/art#duplicate\nnot a url"
            )
            panel._emit_entered_scan()

            self.assertEqual(1, len(requests))
            request = requests[0]
            self.assertIsInstance(request, WebScanRequest)
            if isinstance(request, WebScanRequest):
                self.assertEqual(ScanOrigin.ENTERED, request.origin)
                self.assertEqual(
                    ("https://example.com/sprites", "https://other.example/art"),
                    request.urls,
                )
            self.assertIn("2 valid URLs", panel._entered_count.text())
            self.assertIn("1 invalid", panel._entered_count.text())
            self.assertIn("1 duplicate", panel._entered_count.text())
        finally:
            self._close(app, owns_app, panel)

    def test_save_entered_pages_groups_by_host_and_dedupes(self) -> None:
        app, owns_app, panel = self._setup_panel()
        changes: list[object] = []
        panel.registry_changed.connect(changes.append)
        try:
            panel._entered_urls.setPlainText(
                "https://one.example/sprites/gen-1\nhttps://two.example/art\nhttps://one.example/sprites/gen-1"
            )
            panel._save_entered_pages()
            panel._save_entered_pages()

            registry = panel.sources_registry()
            self.assertEqual(2, len(registry))
            self.assertEqual(2, sum(len(site["areas"]) for site in registry))
            self.assertEqual(2, len(changes))
            self.assertIn("skipped 2 already saved", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_saved_tree_scans_checked_pages_across_websites_through_same_call(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_sources(websites=self._registry())
            panel._saved_tree.topLevelItem(0).child(0).setCheckState(0, Qt.CheckState.Checked)
            panel._saved_tree.topLevelItem(1).child(0).setCheckState(0, Qt.CheckState.Checked)
            panel._emit_saved_scan()

            request = requests[0]
            self.assertIsInstance(request, WebScanRequest)
            if isinstance(request, WebScanRequest):
                self.assertEqual(ScanOrigin.SAVED, request.origin)
                self.assertEqual(
                    ("https://site-a.example/sprites", "https://site-b.example/sprites"),
                    request.urls,
                )
                self.assertIsNone(request.website_id)
                self.assertIsNone(request.area_id)
        finally:
            self._close(app, owns_app, panel)

    def test_saved_tree_falls_back_to_current_page_when_none_are_checked(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_sources(websites=self._registry(), selected_website_id="site_a", selected_area_id="page_b")
            panel._emit_saved_scan()
            request = requests[0]
            self.assertIsInstance(request, WebScanRequest)
            if isinstance(request, WebScanRequest):
                self.assertEqual(("https://site-a.example/other",), request.urls)
                self.assertEqual("site_a", request.website_id)
                self.assertEqual("page_b", request.area_id)
        finally:
            self._close(app, owns_app, panel)

    def test_discover_from_dropdown_exposes_entered_and_saved_pages(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.discover_links_requested.connect(requests.append)
        try:
            panel.set_sources(websites=self._registry())
            panel._entered_urls.setPlainText("https://entered.example/index")

            self.assertEqual(4, panel._link_source.count())
            self.assertTrue(panel._link_source.itemText(0).startswith("Entered:"))
            self.assertTrue(panel._link_source.itemText(1).startswith("Saved:"))

            panel._link_source.setCurrentIndex(2)
            panel._emit_discover_links()
            request = requests[0]
            self.assertIsInstance(request, WebLinkDiscoveryRequest)
            if isinstance(request, WebLinkDiscoveryRequest):
                self.assertEqual("https://site-a.example/other", request.url)
                self.assertEqual("site_a", request.website_id)
                self.assertEqual("page_b", request.area_id)
        finally:
            self._close(app, owns_app, panel)

    def test_linked_pages_filter_and_selection_emit_unified_scan_request(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText("https://example.com/index")
            panel.set_index_links(
                (
                    WebIndexLink("Generation 1", "https://example.com/gen-1"),
                    WebIndexLink("Generation 2", "https://example.com/gen-2"),
                )
            )
            panel._clear_link_selection()
            panel._links_search.setText("gen-2")
            panel._select_visible_links()
            panel._emit_linked_scan()

            request = requests[0]
            self.assertIsInstance(request, WebScanRequest)
            if isinstance(request, WebScanRequest):
                self.assertEqual(ScanOrigin.LINKED, request.origin)
                self.assertEqual(("https://example.com/gen-2",), request.urls)
        finally:
            self._close(app, owns_app, panel)

    def test_linked_scan_requires_real_selection_instead_of_hidden_fallback(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_index_links((WebIndexLink("Page", "https://example.com/page"),))
            panel._clear_link_selection()
            panel._emit_linked_scan()
            self.assertEqual([], requests)
            self.assertIn("Select one or more linked pages", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_results_accumulate_dedupe_and_keep_selection(self) -> None:
        app, owns_app, panel = self._setup_panel()
        first = self._item("a.png")
        second = self._item("b.png")
        try:
            panel.set_results(ScanResults(items=(first,)))
            panel._results.topLevelItem(0).setSelected(True)
            panel._on_result_selection_changed()
            panel.add_results(
                ScanResults(
                    items=(
                        WebItem(
                            url="HTTPS://CDN.EXAMPLE.COM/a.png#preview",
                            name="duplicate.png",
                            ext=".png",
                            confidence=Confidence.DIRECT,
                        ),
                        second,
                    )
                )
            )

            self.assertEqual((first, second), panel.found_items())
            self.assertEqual([first], panel._selected_result_items())
            self.assertIn("Added 1 new item", panel._status.text())
            self.assertIn("ignored 1 duplicate", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_failed_scan_keeps_previous_results_and_reports_details(self) -> None:
        app, owns_app, panel = self._setup_panel()
        first = self._item("a.png")
        try:
            panel.add_results(ScanResults(items=(first,)))
            panel.add_results(
                ScanResults(items=(), failed_pages=("https://example.com/slow: Network timeout",))
            )
            self.assertEqual((first,), panel.found_items())
            self.assertIn("1 page failed", panel._status.text())
            self.assertIn("example.com/slow", panel._status.toolTip())
        finally:
            self._close(app, owns_app, panel)

    def test_result_search_exclusion_and_file_type_filters_are_independent(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_results(
                ScanResults(
                    items=(
                        self._item("bulbasaur.png", source="https://example.com/gen-1"),
                        self._item("bulbasaur_shiny.gif", source="https://example.com/gen-1"),
                        self._item("charmander.png", source="https://example.com/gen-2"),
                    )
                )
            )
            panel._results_search.setText("gen-1")
            self.assertEqual(2, panel._results.topLevelItemCount())
            panel._exclude_words.setText("shiny")
            self.assertEqual(1, panel._results.topLevelItemCount())
            panel._format_actions[".png"].setChecked(False)
            self.assertEqual(0, panel._results.topLevelItemCount())
            self.assertIn("hide all stored results", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_download_emits_typed_request_with_download_options(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.download_requested.connect(requests.append)
        try:
            panel.set_results(ScanResults(items=(self._item("a.png"),)))
            panel._results.topLevelItem(0).setSelected(True)
            panel._skip_downloaded_action.setChecked(False)
            panel._allow_zip_action.setChecked(False)
            panel._emit_download()

            request = requests[0]
            self.assertIsInstance(request, WebDownloadRequest)
            if isinstance(request, WebDownloadRequest):
                self.assertEqual(1, len(request.items))
                self.assertFalse(request.smart.skip_duplicates)
                self.assertFalse(request.smart.allow_zip)
        finally:
            self._close(app, owns_app, panel)

    def test_diagnostics_calls_are_specific_to_entered_or_saved_section(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.diagnostics_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText("https://entered.example/page")
            panel._diagnose_first_entered_url()
            panel.set_sources(websites=self._registry(), selected_website_id="site_b", selected_area_id="page_c")
            panel._diagnose_current_saved_page()

            self.assertEqual(2, len(requests))
            self.assertEqual("https://entered.example/page", requests[0].url)
            self.assertEqual("https://site-b.example/sprites", requests[1].url)
            self.assertTrue(all(isinstance(request, WebDiagnosticsRequest) for request in requests))
        finally:
            self._close(app, owns_app, panel)

    def test_removing_saved_data_does_not_clear_found_files(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_sources(websites=self._registry(), selected_website_id="site_a", selected_area_id="page_a")
            panel.set_results(ScanResults(items=(self._item("a.png"),)))
            panel._remove_current_saved_page()
            self.assertEqual(1, len(panel.found_items()))
            self.assertIn("Found Files were kept", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_clear_found_files_is_the_only_result_reset(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.add_results(ScanResults(items=(self._item("a.png"),)))
            panel._clear_entered_urls()
            panel._clear_linked_pages()
            self.assertEqual(1, len(panel.found_items()))
            panel._clear_found_files()
            self.assertEqual((), panel.found_items())
        finally:
            self._close(app, owns_app, panel)

    def test_smart_option_actions_emit_preferences_without_hidden_widgets(self) -> None:
        app, owns_app, panel = self._setup_panel()
        changes: list[object] = []
        panel.preferences_changed.connect(changes.append)
        try:
            panel.set_smart_options(
                SmartOptions(show_likely=False, skip_duplicates=True, allow_zip=True)
            )
            self.assertEqual([], changes)
            panel._include_likely_action.setChecked(True)
            self.assertEqual(1, len(changes))
            self.assertIsInstance(changes[0], SmartOptions)
            self.assertTrue(changes[0].show_likely)
        finally:
            self._close(app, owns_app, panel)

    def test_large_scan_confirmation_is_capped_and_can_be_cancelled(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                self.assertFalse(panel.confirm_large_page_scan(200, cap=100))
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                self.assertTrue(panel.confirm_large_page_scan(200, cap=100))
            self.assertTrue(panel.confirm_large_page_scan(100, cap=100))
        finally:
            self._close(app, owns_app, panel)


if __name__ == "__main__":
    unittest.main()
