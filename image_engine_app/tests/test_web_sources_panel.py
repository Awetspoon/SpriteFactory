"""Web Sources panel intent and rendering tests."""

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
    SavedWebPage,
    SavedWebsite,
    ScanMergeResult,
    ScanOrigin,
    ScanResults,
    SmartOptions,
    WebDiagnosticsRequest,
    WebDownloadRequest,
    WebIndexLink,
    WebItem,
    WebLinkDiscoveryRequest,
    WebPageBookmark,
    WebRemoveSavedPageRequest,
    WebRemoveSavedWebsiteRequest,
    WebSavePagesRequest,
    WebScanOutcome,
    WebScanRequest,
    WebSourcesState,
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
    def _websites() -> tuple[SavedWebsite, ...]:
        return (
            SavedWebsite(
                id="site_a",
                name="site-a.example",
                pages=(
                    SavedWebPage("page_a", "Sprites A", "https://site-a.example/sprites"),
                    SavedWebPage("page_b", "Sprites B", "https://site-a.example/other"),
                ),
            ),
            SavedWebsite(
                id="site_b",
                name="site-b.example",
                pages=(
                    SavedWebPage("page_c", "Sprites C", "https://site-b.example/sprites"),
                ),
            ),
        )

    def test_panel_has_no_retired_state_store_or_duplicate_scan_signals(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            for name in ("_website", "_area", "_saved_page", "_manual_links", "_store"):
                self.assertFalse(hasattr(panel, name))
            for name in (
                "registry_changed",
                "multi_scan_requested",
                "index_scan_all_requested",
                "index_links_requested",
            ):
                self.assertFalse(hasattr(panel, name))
            self.assertIsNotNone(panel._saved_tree)
            self.assertIsNotNone(panel._results)
        finally:
            self._close(app, owns_app, panel)

    def test_each_more_menu_owns_only_its_section_actions(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_state(WebSourcesState(websites=self._websites()))
            panel._refresh_saved_actions()
            entered = [action.text() for action in panel._entered_more_btn.menu().actions() if action.text()]
            saved = [
                action.text()
                for action in panel._saved_more_btn.menu().actions()
                if action.text() and action.isVisible()
            ]
            linked = [action.text() for action in panel._links_more_btn.menu().actions() if action.text()]
            found = [action.text() for action in panel._results_more_btn.menu().actions() if action.text()]

            self.assertEqual(
                ["Save to Library", "Check First URL", "Include uncertain image links", "Clear Entered URLs"],
                entered,
            )
            self.assertEqual(
                [
                    "Test Highlighted Page",
                    "Remove Highlighted Page",
                ],
                saved,
            )
            self.assertEqual(
                [
                    "Save Selected to Library",
                    "Select Visible Pages",
                    "Clear Page Selection",
                    "Clear Linked Pages",
                ],
                linked,
            )
            self.assertEqual(["Select All Visible Files", "Clear File Selection", "Clear Found Files"], found)
        finally:
            self._close(app, owns_app, panel)

    def test_saved_more_menu_only_shows_actions_relevant_to_the_highlighted_row(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_state(WebSourcesState(websites=self._websites()))
            page = panel._saved_tree.topLevelItem(0).child(0)
            page.setCheckState(0, Qt.CheckState.Checked)
            panel._saved_tree.setCurrentItem(page)
            panel._refresh_saved_actions()
            visible_page_actions = [
                action.text()
                for action in panel._saved_more_btn.menu().actions()
                if action.text() and action.isVisible()
            ]
            self.assertEqual(
                ["Uncheck All Pages", "Test Highlighted Page", "Remove Highlighted Page"],
                visible_page_actions,
            )

            panel._saved_tree.setCurrentItem(panel._saved_tree.topLevelItem(0))
            panel._refresh_saved_actions()
            visible_website_actions = [
                action.text()
                for action in panel._saved_more_btn.menu().actions()
                if action.text() and action.isVisible()
            ]
            self.assertEqual(
                ["Uncheck All Pages", "Remove Highlighted Website"],
                visible_website_actions,
            )
        finally:
            self._close(app, owns_app, panel)

    def test_entered_pages_emit_one_normalized_scan_request(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText(
                "example.com/sprites\nhttps://other.example/art\n"
                "https://other.example/art#duplicate\nnot a url"
            )
            panel._emit_entered_scan()

            self.assertEqual(1, len(requests))
            request = requests[0]
            self.assertIsInstance(request, WebScanRequest)
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

    def test_save_pages_emits_typed_intent_without_mutating_registry(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.save_pages_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText("https://one.example/sprites")
            panel._save_entered_pages()

            self.assertEqual(1, len(requests))
            self.assertIsInstance(requests[0], WebSavePagesRequest)
            self.assertEqual(
                (WebPageBookmark(url="https://one.example/sprites"),),
                requests[0].pages,
            )
            self.assertEqual((), panel._registry)
        finally:
            self._close(app, owns_app, panel)

    def test_saved_tree_scans_checked_pages_across_websites(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_state(WebSourcesState(websites=self._websites()))
            panel._saved_tree.topLevelItem(0).child(0).setCheckState(0, Qt.CheckState.Checked)
            panel._saved_tree.topLevelItem(1).child(0).setCheckState(0, Qt.CheckState.Checked)
            panel._emit_saved_scan()

            request = requests[0]
            self.assertEqual(ScanOrigin.SAVED, request.origin)
            self.assertEqual(
                ("https://site-a.example/sprites", "https://site-b.example/sprites"),
                request.urls,
            )
            self.assertIsNone(request.website_id)
            self.assertIsNone(request.page_id)
        finally:
            self._close(app, owns_app, panel)

    def test_checking_website_selects_all_pages_for_one_scan(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_state(WebSourcesState(websites=self._websites()))
            panel._saved_tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
            panel._emit_saved_scan()

            request = requests[0]
            self.assertEqual(
                (
                    "https://site-a.example/sprites",
                    "https://site-a.example/other",
                ),
                request.urls,
            )
            self.assertEqual("site_a", request.website_id)
            self.assertIsNone(request.page_id)
        finally:
            self._close(app, owns_app, panel)

    def test_saved_tree_requires_checked_pages_and_never_scans_highlight_only(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel.set_state(
                WebSourcesState(
                    websites=self._websites(),
                    selected_website_id="site_a",
                    selected_page_id="page_b",
                )
            )
            panel._emit_saved_scan()
            self.assertEqual([], requests)
            self.assertIn("Check one or more saved pages", panel._status.text())

            panel._saved_tree.topLevelItem(0).child(1).setCheckState(0, Qt.CheckState.Checked)
            panel._emit_saved_scan()
            request = requests[0]
            self.assertEqual(("https://site-a.example/other",), request.urls)
            self.assertEqual("site_a", request.website_id)
            self.assertEqual("page_b", request.page_id)
        finally:
            self._close(app, owns_app, panel)

    def test_discovery_source_combines_entered_and_saved_pages(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.discover_links_requested.connect(requests.append)
        try:
            panel.set_state(WebSourcesState(websites=self._websites()))
            panel._entered_urls.setPlainText("https://entered.example/index")

            self.assertEqual(4, panel._link_source.count())
            self.assertTrue(panel._link_source.itemText(0).startswith("Entered:"))
            self.assertTrue(panel._link_source.itemText(1).startswith("Saved:"))
            panel._link_source.setCurrentIndex(2)
            panel._emit_discover_links()

            request = requests[0]
            self.assertIsInstance(request, WebLinkDiscoveryRequest)
            self.assertEqual("https://site-a.example/other", request.url)
            self.assertEqual("site_a", request.website_id)
            self.assertEqual("page_b", request.page_id)
        finally:
            self._close(app, owns_app, panel)

    def test_discovery_source_accepts_a_direct_page_url(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.discover_links_requested.connect(requests.append)
        try:
            panel._link_source.setCurrentIndex(-1)
            panel._link_source.setEditText("https://example.com/sprite-index")

            self.assertTrue(panel._find_links_btn.isEnabled())
            panel._emit_discover_links()

            self.assertEqual(1, len(requests))
            self.assertEqual("https://example.com/sprite-index", requests[0].url)
            self.assertIsNone(requests[0].website_id)
            self.assertIsNone(requests[0].page_id)
        finally:
            self._close(app, owns_app, panel)

    def test_linked_pages_require_an_explicit_selection_before_scan(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            self.assertEqual("No linked pages yet", panel._links_count.text())
            self.assertFalse(panel._links_search.isEnabled())
            panel.set_index_links(
                (WebIndexLink("Generation 1", "https://example.com/gen-1"),)
            )

            self.assertTrue(panel._links_search.isEnabled())
            self.assertFalse(panel._scan_links_btn.isEnabled())
            self.assertIn("0 selected", panel._links_count.text())
        finally:
            self._close(app, owns_app, panel)

    def test_linked_page_filter_and_selection_emit_unified_scan(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.scan_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText("https://example.com/index")
            panel.set_state(
                WebSourcesState(
                    linked_pages=(
                        WebIndexLink("Generation 1", "https://example.com/gen-1"),
                        WebIndexLink("Generation 2", "https://example.com/gen-2"),
                    )
                )
            )
            panel._clear_link_selection()
            panel._links_search.setText("gen-2")
            panel._select_visible_links()
            panel._emit_linked_scan()

            request = requests[0]
            self.assertEqual(ScanOrigin.LINKED, request.origin)
            self.assertEqual(("https://example.com/gen-2",), request.urls)
        finally:
            self._close(app, owns_app, panel)

    def test_selected_linked_pages_save_to_library_with_discovered_names(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.save_pages_requested.connect(requests.append)
        try:
            panel.set_state(
                WebSourcesState(
                    linked_pages=(
                        WebIndexLink("Generation 1", "https://example.com/gen-1"),
                        WebIndexLink("Generation 2", "https://example.com/gen-2"),
                    )
                )
            )
            panel._clear_link_selection()
            panel._links_search.setText("gen-2")
            panel._select_visible_links()
            panel._save_selected_linked_pages()

            self.assertEqual(1, len(requests))
            self.assertEqual(
                (
                    WebPageBookmark(
                        url="https://example.com/gen-2",
                        label="Generation 2",
                    ),
                ),
                requests[0].pages,
            )
        finally:
            self._close(app, owns_app, panel)

    def test_scan_outcome_renders_accumulated_results_and_keeps_selection(self) -> None:
        app, owns_app, panel = self._setup_panel()
        first = self._item("a.png")
        second = self._item("b.gif")
        try:
            panel.set_state(WebSourcesState(found_files=(first,)))
            panel._results.topLevelItem(0).setSelected(True)
            panel._on_result_selection_changed()
            latest = ScanResults(items=(first, second))
            panel.show_scan_outcome(
                WebScanOutcome(
                    state=WebSourcesState(found_files=(first, second), latest_scan=latest),
                    latest=latest,
                    merge=ScanMergeResult(
                        results=ScanResults(items=(first, second)),
                        added_count=1,
                        duplicate_count=1,
                    ),
                )
            )

            self.assertEqual((first, second), panel.found_items())
            self.assertEqual([first], panel._selected_result_items())
            self.assertIn("Added 1 new item", panel._status.text())
            self.assertIn("ignored 1 duplicate", panel._status.text())
        finally:
            self._close(app, owns_app, panel)

    def test_failed_scan_status_keeps_existing_results_and_details(self) -> None:
        app, owns_app, panel = self._setup_panel()
        first = self._item("a.png")
        latest = ScanResults(
            items=(),
            failed_pages=("https://example.com/slow: Network timeout",),
        )
        try:
            panel.show_scan_outcome(
                WebScanOutcome(
                    state=WebSourcesState(found_files=(first,), latest_scan=latest),
                    latest=latest,
                    merge=ScanMergeResult(results=ScanResults(items=(first,))),
                )
            )
            self.assertEqual((first,), panel.found_items())
            self.assertIn("1 page failed", panel._status.text())
            self.assertIn("example.com/slow", panel._status.toolTip())
        finally:
            self._close(app, owns_app, panel)

    def test_result_search_exclusion_and_file_type_filters_are_independent(self) -> None:
        app, owns_app, panel = self._setup_panel()
        try:
            panel.set_state(
                WebSourcesState(
                    found_files=(
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

    def test_download_emits_typed_request_with_options(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.download_requested.connect(requests.append)
        try:
            panel.set_state(WebSourcesState(found_files=(self._item("a.png"),)))
            panel._results.topLevelItem(0).setSelected(True)
            panel._skip_downloaded_action.setChecked(False)
            panel._allow_zip_action.setChecked(False)
            panel._emit_download()

            request = requests[0]
            self.assertIsInstance(request, WebDownloadRequest)
            self.assertEqual(1, len(request.items))
            self.assertFalse(request.smart.skip_duplicates)
            self.assertFalse(request.smart.allow_zip)
        finally:
            self._close(app, owns_app, panel)

    def test_diagnostics_are_specific_to_entered_or_saved_sections(self) -> None:
        app, owns_app, panel = self._setup_panel()
        requests: list[object] = []
        panel.diagnostics_requested.connect(requests.append)
        try:
            panel._entered_urls.setPlainText("https://entered.example/page")
            panel._diagnose_first_entered_url()
            panel.set_state(
                WebSourcesState(
                    websites=self._websites(),
                    selected_website_id="site_b",
                    selected_page_id="page_c",
                )
            )
            panel._diagnose_current_saved_page()

            self.assertEqual(2, len(requests))
            self.assertEqual("https://entered.example/page", requests[0].url)
            self.assertEqual("https://site-b.example/sprites", requests[1].url)
            self.assertTrue(all(isinstance(request, WebDiagnosticsRequest) for request in requests))
        finally:
            self._close(app, owns_app, panel)

    def test_remove_and_clear_actions_emit_intent_without_local_state_changes(self) -> None:
        app, owns_app, panel = self._setup_panel()
        remove_page_requests: list[object] = []
        remove_website_requests: list[object] = []
        clear_found_calls: list[bool] = []
        clear_link_calls: list[bool] = []
        panel.remove_saved_page_requested.connect(remove_page_requests.append)
        panel.remove_saved_website_requested.connect(remove_website_requests.append)
        panel.clear_found_files_requested.connect(lambda: clear_found_calls.append(True))
        panel.clear_linked_pages_requested.connect(lambda: clear_link_calls.append(True))
        first = self._item("a.png")
        try:
            panel.set_state(
                WebSourcesState(
                    websites=self._websites(),
                    selected_website_id="site_a",
                    selected_page_id="page_a",
                    linked_pages=(WebIndexLink("Page", "https://example.com/page"),),
                    found_files=(first,),
                )
            )
            panel._remove_current_saved_item()
            panel._saved_tree.setCurrentItem(panel._saved_tree.topLevelItem(0))
            panel._remove_current_saved_item()
            panel._clear_linked_pages()
            panel._clear_found_files()

            self.assertIsInstance(remove_page_requests[0], WebRemoveSavedPageRequest)
            self.assertIsInstance(remove_website_requests[0], WebRemoveSavedWebsiteRequest)
            self.assertEqual((first,), panel.found_items())
            self.assertEqual([True], clear_found_calls)
            self.assertEqual([True], clear_link_calls)
        finally:
            self._close(app, owns_app, panel)

    def test_smart_options_emit_preferences_without_hidden_widgets(self) -> None:
        app, owns_app, panel = self._setup_panel()
        changes: list[object] = []
        panel.preferences_changed.connect(changes.append)
        try:
            panel.set_smart_options(SmartOptions(show_likely=False))
            self.assertEqual([], changes)
            panel._include_likely_action.setChecked(True)
            self.assertEqual(1, len(changes))
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
