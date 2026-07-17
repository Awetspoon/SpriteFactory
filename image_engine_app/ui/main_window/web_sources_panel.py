"""Web Sources workspace.

The panel only collects user intent and renders state. Network work, persistence,
downloads, and workspace imports are owned by the coordinator and services.
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.app.web_sources_models import (
    ImportTarget,
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
from image_engine_app.app.services.web_sources_registry import normalize_page_url
from image_engine_app.ui.common.shell_tokens import SHELL_GEOMETRY


class WebSourcesPanel(QFrame):
    """Clear four-step UI for scanning pages and importing discovered files."""

    PAGE_SCAN_CAP = 100
    _ROLE_KIND = int(Qt.ItemDataRole.UserRole)
    _ROLE_DATA = int(Qt.ItemDataRole.UserRole) + 1

    scan_requested = Signal(object)
    discover_links_requested = Signal(object)
    download_requested = Signal(object)
    diagnostics_requested = Signal(object)
    save_pages_requested = Signal(object)
    remove_saved_page_requested = Signal(object)
    remove_saved_website_requested = Signal(object)
    clear_linked_pages_requested = Signal()
    clear_found_files_requested = Signal()
    preferences_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._entered_urls = QPlainTextEdit(self)
        self._entered_count = QLabel("0 valid URLs", self)
        self._scan_entered_btn = QPushButton("Scan Pages", self)
        self._entered_more_btn = QToolButton(self)

        self._saved_tree = QTreeWidget(self)
        self._saved_count = QLabel("0 pages in library", self)
        self._scan_saved_btn = QPushButton("Scan Checked", self)
        self._saved_more_btn = QToolButton(self)

        self._link_source = QComboBox(self)
        self._find_links_btn = QPushButton("Find Pages", self)
        self._scan_links_btn = QPushButton("Scan Selected", self)
        self._links_more_btn = QToolButton(self)
        self._links_search = QLineEdit(self)
        self._links_count = QLabel("0 linked pages", self)
        self._links = QListWidget(self)

        self._results_search = QLineEdit(self)
        self._exclude_words = QLineEdit(self)
        self._filters_btn = QToolButton(self)
        self._results_more_btn = QToolButton(self)
        self._results_count = QLabel("0 files", self)
        self._results = QTreeWidget(self)
        self._selection_detail = QLabel("Select a file to see its source URL.", self)

        self._destination_hint = QLabel(
            "Downloads are routed automatically into Main, Shiny, Animated, or Items.",
            self,
        )
        self._download_options_btn = QToolButton(self)
        self._download_btn = QPushButton("Download Selected", self)
        self._status = QLabel("Paste one or more page URLs to begin.", self)

        self._include_likely_action = self._checkable_action("Include uncertain image links", False)
        self._skip_downloaded_action = self._checkable_action("Skip files already downloaded", True)
        self._allow_zip_action = self._checkable_action("Allow ZIP extraction", True)
        self._format_actions = {
            ".png": self._checkable_action("PNG", True),
            ".gif": self._checkable_action("GIF", True),
            ".webp": self._checkable_action("WEBP", True),
            ".jpg": self._checkable_action("JPG / JPEG", True),
            ".zip": self._checkable_action("ZIP", True),
        }

        self._registry: tuple[SavedWebsite, ...] = ()
        self._found_files: tuple[WebItem, ...] = ()
        self._linked_items: list[WebIndexLink] = []
        self._selected_link_urls: set[str] = set()
        self._selected_file_urls: set[str] = set()

        self._apply_object_names()
        self._build_ui()
        self._connect_state_actions()
        self._refresh_entered_state()
        self._refresh_saved_tree()
        self._refresh_link_sources()
        self._refresh_link_list(capture_selection=False)
        self._refresh_results(capture_selection=False)

    # --- Public coordinator boundary ---

    def set_state(self, state: WebSourcesState) -> None:
        if not isinstance(state, WebSourcesState):
            raise TypeError("Web Sources panel requires WebSourcesState")
        self.set_sources(
            websites=state.websites,
            selected_website_id=state.selected_website_id,
            selected_page_id=state.selected_page_id,
        )
        self.set_smart_options(state.smart)
        self.set_index_links(state.linked_pages)
        self.set_results(ScanResults(items=state.found_files))

    def set_sources(
        self,
        *,
        websites: tuple[SavedWebsite, ...],
        selected_website_id: str | None = None,
        selected_page_id: str | None = None,
    ) -> None:
        checked_urls = {page["url"] for page in self._checked_saved_pages()}
        self._registry = tuple(websites)
        self._refresh_saved_tree(
            selected_website_id=selected_website_id,
            selected_page_id=selected_page_id,
            checked_urls=checked_urls,
        )
        self._refresh_link_sources()

    def selected_source_ids(self) -> tuple[str | None, str | None]:
        item = self._saved_tree.currentItem()
        payload = self._saved_item_payload(item)
        if payload is None:
            return None, None
        return payload.get("website_id"), payload.get("page_id")

    def smart_options(self) -> SmartOptions:
        return SmartOptions(
            show_likely=self._include_likely_action.isChecked(),
            auto_sort=True,
            skip_duplicates=self._skip_downloaded_action.isChecked(),
            allow_zip=self._allow_zip_action.isChecked(),
        )

    def set_smart_options(self, options: SmartOptions | dict | None) -> None:
        if isinstance(options, SmartOptions):
            smart = options
        elif isinstance(options, dict):
            smart = SmartOptions(
                show_likely=bool(options.get("show_likely", False)),
                auto_sort=True,
                skip_duplicates=bool(options.get("skip_duplicates", True)),
                allow_zip=bool(options.get("allow_zip", True)),
            )
        else:
            return

        for action, checked in (
            (self._include_likely_action, smart.show_likely),
            (self._skip_downloaded_action, smart.skip_duplicates),
            (self._allow_zip_action, smart.allow_zip),
        ):
            action.blockSignals(True)
            action.setChecked(bool(checked))
            action.blockSignals(False)

    def set_results(self, results: ScanResults) -> None:
        self._found_files = tuple(results.items)
        available = {item.url for item in self._found_files}
        self._selected_file_urls.intersection_update(available)
        self._refresh_results(capture_selection=False)

    def show_scan_outcome(self, outcome: WebScanOutcome) -> None:
        if not isinstance(outcome, WebScanOutcome):
            raise TypeError("Web Sources panel requires WebScanOutcome")
        self._capture_result_selection()
        self.set_state(outcome.state)
        self._refresh_results(capture_selection=False)
        self._show_scan_status(outcome.latest, merge=outcome.merge)

    def found_items(self) -> tuple[WebItem, ...]:
        return self._found_files

    def set_index_links(self, links: tuple[WebIndexLink, ...] | list[WebIndexLink]) -> None:
        self._linked_items = list(links)
        available = {link.url for link in self._linked_items}
        self._selected_link_urls.intersection_update(available)
        if self._linked_items and not self._selected_link_urls:
            self._selected_link_urls = set(available)
        self._refresh_link_list(capture_selection=False)

    def set_status(self, message: str) -> None:
        text = " ".join(str(message or "").split())
        self._set_status_text(text, text if len(text) > 140 else "")

    def confirm_large_page_scan(self, page_count: int, *, cap: int | None = None) -> bool:
        limit = int(cap or self.PAGE_SCAN_CAP)
        if int(page_count) <= limit:
            return True
        answer = QMessageBox.question(
            self,
            "Large page scan",
            (
                f"You selected {page_count} pages.\n\n"
                "Scanning too many pages together may make the app or website unstable.\n"
                f"Sprite Factory will scan the first {limit} pages only.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    # --- UI construction ---

    def _apply_object_names(self) -> None:
        self.setObjectName("webSourcesCard")
        for button in (
            self._scan_entered_btn,
            self._scan_saved_btn,
            self._find_links_btn,
            self._scan_links_btn,
            self._download_btn,
        ):
            button.setObjectName("webSourcesPrimaryAction")
        for label in (self._entered_count, self._saved_count, self._links_count, self._results_count):
            label.setObjectName("webSourcesCountBadge")
        self._entered_urls.setObjectName("webSourcesUrlList")
        self._saved_tree.setObjectName("webSourcesSavedTree")
        self._links.setObjectName("webSourcesIndexList")
        self._results.setObjectName("webSourcesResultsTree")

    def _build_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
            SHELL_GEOMETRY.panel_margin,
        )
        outer.setSpacing(SHELL_GEOMETRY.gap)

        source_row = QHBoxLayout()
        source_row.setSpacing(SHELL_GEOMETRY.gap)
        source_row.addWidget(self._build_entered_section(), 3)
        source_row.addWidget(self._build_saved_section(), 2)
        outer.addLayout(source_row)
        outer.addWidget(self._build_links_section())
        outer.addWidget(self._build_results_section(), 1)

        self._status.setObjectName("shellHint")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

    def _build_entered_section(self) -> QFrame:
        section, body = self._section_card(
            "1. Scan Pages",
            "Paste one page URL or one full URL per line, including pages from different websites.",
        )
        self._entered_urls.setPlaceholderText(
            "https://example.com/sprites\nhttps://another-site.example/characters"
        )
        self._entered_urls.setFixedHeight(SHELL_GEOMETRY.web_short_list_height)
        self._entered_urls.textChanged.connect(self._refresh_entered_state)
        body.addWidget(self._entered_urls)

        actions = QHBoxLayout()
        actions.addWidget(self._entered_count)
        actions.addStretch(1)
        self._scan_entered_btn.clicked.connect(self._emit_entered_scan)
        actions.addWidget(self._scan_entered_btn)

        entered_menu = QMenu(self._entered_more_btn)
        entered_menu.addAction(self._action("Save to Library", self._save_entered_pages))
        entered_menu.addAction(self._action("Check First URL", self._diagnose_first_entered_url))
        entered_menu.addSeparator()
        entered_menu.addAction(self._include_likely_action)
        entered_menu.addSeparator()
        entered_menu.addAction(self._action("Clear Entered URLs", self._clear_entered_urls))
        self._set_menu(self._entered_more_btn, entered_menu)
        actions.addWidget(self._entered_more_btn)
        body.addLayout(actions)
        return section

    def _build_saved_section(self) -> QFrame:
        section, body = self._section_card(
            "2. Saved Library",
            "Websites contain the pages you keep. Check any pages or a whole website, then scan them together.",
        )
        self._saved_tree.setHeaderHidden(True)
        self._saved_tree.setFixedHeight(SHELL_GEOMETRY.web_short_list_height)
        self._saved_tree.currentItemChanged.connect(
            lambda _current, _previous: self._on_saved_current_changed()
        )
        self._saved_tree.itemChanged.connect(lambda _item, _column: self._refresh_saved_actions())
        body.addWidget(self._saved_tree)

        actions = QHBoxLayout()
        actions.addWidget(self._saved_count)
        actions.addStretch(1)
        self._scan_saved_btn.clicked.connect(self._emit_saved_scan)
        actions.addWidget(self._scan_saved_btn)

        saved_menu = QMenu(self._saved_more_btn)
        self._saved_clear_action = self._action("Uncheck All Pages", self._clear_checked_saved_pages)
        self._saved_test_action = self._action("Test Highlighted Page", self._diagnose_current_saved_page)
        self._saved_remove_action = self._action("Remove Highlighted Page", self._remove_current_saved_item)
        saved_menu.addAction(self._saved_clear_action)
        saved_menu.addAction(self._saved_test_action)
        self._saved_remove_separator = saved_menu.addSeparator()
        saved_menu.addAction(self._saved_remove_action)
        saved_menu.aboutToShow.connect(self._refresh_saved_actions)
        self._saved_more_btn.setToolTip("Options for the highlighted saved page or website")
        self._set_menu(self._saved_more_btn, saved_menu)
        actions.addWidget(self._saved_more_btn)
        body.addLayout(actions)
        return section

    def _build_links_section(self) -> QFrame:
        section, body = self._section_card(
            "3. Find Linked Pages",
            "Optional. Choose an index or category page, find its page links, then scan only the ones you select.",
        )

        source_row = QHBoxLayout()
        source_label = QLabel("Discover from", self)
        source_label.setObjectName("shellHint")
        source_row.addWidget(source_label)
        source_row.addWidget(self._link_source, 1)
        self._find_links_btn.clicked.connect(self._emit_discover_links)
        source_row.addWidget(self._find_links_btn)
        self._scan_links_btn.clicked.connect(self._emit_linked_scan)
        source_row.addWidget(self._scan_links_btn)

        links_menu = QMenu(self._links_more_btn)
        self._links_save_action = self._action(
            "Save Selected to Library",
            self._save_selected_linked_pages,
        )
        self._links_select_visible_action = self._action(
            "Select Visible Pages",
            self._select_visible_links,
        )
        self._links_clear_selection_action = self._action(
            "Clear Page Selection",
            self._clear_link_selection,
        )
        self._links_clear_results_action = self._action(
            "Clear Linked Pages",
            self._clear_linked_pages,
        )
        links_menu.addAction(self._links_save_action)
        links_menu.addSeparator()
        links_menu.addAction(self._links_select_visible_action)
        links_menu.addAction(self._links_clear_selection_action)
        links_menu.addSeparator()
        links_menu.addAction(self._links_clear_results_action)
        links_menu.aboutToShow.connect(self._refresh_link_actions)
        self._set_menu(self._links_more_btn, links_menu)
        source_row.addWidget(self._links_more_btn)
        body.addLayout(source_row)

        filter_row = QHBoxLayout()
        self._links_search.setPlaceholderText("Search linked pages by name or URL...")
        self._links_search.textChanged.connect(lambda _text: self._refresh_link_list())
        filter_row.addWidget(self._links_search, 1)
        filter_row.addWidget(self._links_count)
        body.addLayout(filter_row)

        self._links.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._links.setFixedHeight(SHELL_GEOMETRY.web_link_list_height)
        self._links.itemSelectionChanged.connect(self._capture_link_selection)
        body.addWidget(self._links)
        return section

    def _build_results_section(self) -> QFrame:
        section, body = self._section_card(
            "4. Found Files",
            "Results stay here across scans. Search, filter, select, then download them into the workspace.",
        )

        filter_row = QHBoxLayout()
        self._results_search.setPlaceholderText("Search filename, URL, or source page...")
        self._results_search.textChanged.connect(lambda _text: self._refresh_results())
        filter_row.addWidget(self._results_search, 2)
        self._exclude_words.setPlaceholderText("Hide words, e.g. shiny, thumb")
        self._exclude_words.textChanged.connect(lambda _text: self._refresh_results())
        filter_row.addWidget(self._exclude_words, 1)

        filters_menu = QMenu(self._filters_btn)
        for action in self._format_actions.values():
            filters_menu.addAction(action)
        filters_menu.addSeparator()
        filters_menu.addAction(self._action("Reset File Filters", self._reset_file_filters))
        self._filters_btn.setText("File Types")
        self._set_menu(self._filters_btn, filters_menu)
        filter_row.addWidget(self._filters_btn)

        results_menu = QMenu(self._results_more_btn)
        results_menu.addAction(self._action("Select All Visible Files", self._select_all_visible_results))
        results_menu.addAction(self._action("Clear File Selection", self._clear_result_selection))
        results_menu.addSeparator()
        results_menu.addAction(self._action("Clear Found Files", self._clear_found_files))
        self._set_menu(self._results_more_btn, results_menu)
        filter_row.addWidget(self._results_more_btn)
        filter_row.addWidget(self._results_count)
        body.addLayout(filter_row)

        self._results.setHeaderLabels(["File", "Type", "Source page"])
        self._results.setRootIsDecorated(False)
        self._results.setAlternatingRowColors(True)
        self._results.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        header = self._results.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._results.itemSelectionChanged.connect(self._on_result_selection_changed)
        body.addWidget(self._results, 1)

        self._selection_detail.setObjectName("shellHint")
        self._selection_detail.setWordWrap(True)
        body.addWidget(self._selection_detail)

        download_row = QHBoxLayout()
        self._destination_hint.setObjectName("shellHint")
        download_row.addWidget(self._destination_hint, 1)

        download_menu = QMenu(self._download_options_btn)
        download_menu.addAction(self._skip_downloaded_action)
        download_menu.addAction(self._allow_zip_action)
        self._download_options_btn.setText("Download Options")
        self._set_menu(self._download_options_btn, download_menu)
        download_row.addWidget(self._download_options_btn)
        self._download_btn.clicked.connect(self._emit_download)
        download_row.addWidget(self._download_btn)
        body.addLayout(download_row)
        return section

    @staticmethod
    def _section_card(title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame()
        section.setObjectName("webSourcesSectionCard")
        section.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
            SHELL_GEOMETRY.card_margin,
            SHELL_GEOMETRY.compact_gap,
        )
        layout.setSpacing(SHELL_GEOMETRY.compact_gap)

        header = QHBoxLayout()
        title_label = QLabel(title, section)
        title_label.setObjectName("shellTitle")
        header.addWidget(title_label)
        hint_label = QLabel(hint, section)
        hint_label.setObjectName("shellHint")
        hint_label.setWordWrap(True)
        header.addWidget(hint_label, 1)
        layout.addLayout(header)
        return section, layout

    def _action(self, label: str, callback) -> QAction:  # noqa: ANN001
        action = QAction(label, self)
        action.triggered.connect(callback)
        return action

    def _checkable_action(self, label: str, checked: bool) -> QAction:
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(bool(checked))
        return action

    @staticmethod
    def _set_menu(button: QToolButton, menu: QMenu) -> None:
        if not button.text():
            button.setText("More")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)

    def _connect_state_actions(self) -> None:
        for action in (
            self._include_likely_action,
            self._skip_downloaded_action,
            self._allow_zip_action,
        ):
            action.toggled.connect(lambda _checked, self=self: self.preferences_changed.emit(self.smart_options()))
        for action in self._format_actions.values():
            action.toggled.connect(lambda _checked, self=self: self._refresh_results())

    # --- Entered pages ---

    def _entered_url_values(self) -> tuple[tuple[str, ...], int, int]:
        urls: list[str] = []
        seen: set[str] = set()
        invalid = 0
        duplicates = 0
        for raw_line in self._entered_urls.toPlainText().splitlines():
            raw = raw_line.strip()
            if not raw:
                continue
            normalized = normalize_page_url(raw)
            if normalized is None:
                invalid += 1
                continue
            key = normalized.casefold()
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            urls.append(normalized)
        return tuple(urls), invalid, duplicates

    def _refresh_entered_state(self) -> None:
        urls, invalid, duplicates = self._entered_url_values()
        detail = f"{len(urls)} valid URL{'s' if len(urls) != 1 else ''}"
        skipped: list[str] = []
        if invalid:
            skipped.append(f"{invalid} invalid")
        if duplicates:
            skipped.append(f"{duplicates} duplicate")
        if skipped:
            detail += f"; {', '.join(skipped)} skipped"
        self._entered_count.setText(detail)
        self._scan_entered_btn.setEnabled(bool(urls))
        self._refresh_link_sources()

    def _emit_entered_scan(self) -> None:
        urls, _, _ = self._entered_url_values()
        if not urls:
            self.set_status("Enter at least one valid http or https page URL.")
            return
        self.scan_requested.emit(
            WebScanRequest(urls=urls, smart=self.smart_options(), origin=ScanOrigin.ENTERED)
        )

    def _clear_entered_urls(self) -> None:
        self._entered_urls.clear()
        self.set_status("Entered URLs cleared. Found Files were kept.")

    def _diagnose_first_entered_url(self) -> None:
        urls, _, _ = self._entered_url_values()
        if not urls:
            self.set_status("Enter a valid URL before checking its connection.")
            return
        self.diagnostics_requested.emit(WebDiagnosticsRequest(url=urls[0]))

    def _save_entered_pages(self) -> None:
        urls, _, _ = self._entered_url_values()
        if not urls:
            self.set_status("Enter at least one valid URL before saving pages.")
            return
        self.save_pages_requested.emit(
            WebSavePagesRequest(
                pages=tuple(WebPageBookmark(url=url) for url in urls),
            )
        )

    # --- Saved pages ---

    def _refresh_saved_tree(
        self,
        *,
        selected_website_id: str | None = None,
        selected_page_id: str | None = None,
        checked_urls: set[str] | None = None,
    ) -> None:
        checked = checked_urls or set()
        self._saved_tree.blockSignals(True)
        self._saved_tree.clear()
        page_count = 0
        selected_item: QTreeWidgetItem | None = None
        first_page: QTreeWidgetItem | None = None

        for website in self._registry:
            website_id = website.id
            website_name = website.name
            website_item = QTreeWidgetItem(
                [f"{website_name} ({len(website.pages)})"]
            )
            website_item.setData(0, self._ROLE_KIND, "website")
            website_item.setData(0, self._ROLE_DATA, {"website_id": website_id, "page_id": None})
            website_item.setToolTip(0, f"{website_name}: {len(website.pages)} saved page(s)")
            website_item.setFlags(
                website_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            website_item.setCheckState(0, Qt.CheckState.Unchecked)
            self._saved_tree.addTopLevelItem(website_item)
            if website_id == selected_website_id and not selected_page_id:
                selected_item = website_item

            for page in website.pages:
                page_id = page.id
                label = page.label
                url = page.url
                if not page_id or not url:
                    continue
                child = QTreeWidgetItem([label])
                payload = {
                    "website_id": website_id,
                    "page_id": page_id,
                    "website_name": website_name,
                    "label": label,
                    "url": url,
                }
                child.setData(0, self._ROLE_KIND, "page")
                child.setData(0, self._ROLE_DATA, payload)
                child.setToolTip(0, url)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked if url in checked else Qt.CheckState.Unchecked)
                website_item.addChild(child)
                page_count += 1
                first_page = first_page or child
                if website_id == selected_website_id and page_id == selected_page_id:
                    selected_item = child

            website_item.setExpanded(True)

        if page_count == 0:
            empty_item = QTreeWidgetItem(["Save pages here for quick scanning"])
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._saved_tree.addTopLevelItem(empty_item)

        self._saved_tree.setCurrentItem(selected_item or first_page)
        self._saved_tree.blockSignals(False)
        website_count = len(self._registry)
        self._saved_count.setText(
            f"{page_count} page{'s' if page_count != 1 else ''} in "
            f"{website_count} website{'s' if website_count != 1 else ''}"
        )
        self._scan_saved_btn.setEnabled(False)
        self._saved_more_btn.setEnabled(page_count > 0)
        self._refresh_saved_actions()

    def _saved_item_payload(self, item: QTreeWidgetItem | None) -> dict | None:
        if item is None:
            return None
        payload = item.data(0, self._ROLE_DATA)
        return payload if isinstance(payload, dict) else None

    def _on_saved_current_changed(self) -> None:
        self._refresh_link_sources()
        self._refresh_saved_actions()

    def _refresh_saved_actions(self) -> None:
        item = self._saved_tree.currentItem()
        kind = str(item.data(0, self._ROLE_KIND) or "") if item is not None else ""
        has_checked_pages = bool(self._checked_saved_pages())
        is_page = kind == "page"
        is_website = kind == "website"

        self._saved_clear_action.setVisible(has_checked_pages)
        self._saved_clear_action.setEnabled(has_checked_pages)
        self._saved_test_action.setVisible(is_page)
        self._saved_test_action.setEnabled(is_page)
        self._saved_remove_action.setVisible(is_page or is_website)
        self._saved_remove_action.setEnabled(is_page or is_website)
        self._saved_remove_action.setText(
            "Remove Highlighted Website" if is_website else "Remove Highlighted Page"
        )
        self._saved_remove_separator.setVisible(is_page or is_website)
        self._scan_saved_btn.setEnabled(has_checked_pages)

    def _checked_saved_pages(self) -> list[dict]:
        pages: list[dict] = []
        for top_index in range(self._saved_tree.topLevelItemCount()):
            website = self._saved_tree.topLevelItem(top_index)
            for child_index in range(website.childCount()):
                child = website.child(child_index)
                if child.checkState(0) == Qt.CheckState.Checked:
                    payload = self._saved_item_payload(child)
                    if payload is not None:
                        pages.append(payload)
        return pages

    def _emit_saved_scan(self) -> None:
        pages = self._checked_saved_pages()
        if not pages:
            self.set_status("Check one or more saved pages before scanning.")
            return
        website_ids = {str(page.get("website_id", "")) for page in pages}
        page_ids = {str(page.get("page_id", "")) for page in pages}
        self.scan_requested.emit(
            WebScanRequest(
                urls=tuple(str(page["url"]) for page in pages),
                smart=self.smart_options(),
                origin=ScanOrigin.SAVED,
                website_id=next(iter(website_ids)) if len(website_ids) == 1 else None,
                page_id=next(iter(page_ids)) if len(page_ids) == 1 else None,
            )
        )

    def _clear_checked_saved_pages(self) -> None:
        for top_index in range(self._saved_tree.topLevelItemCount()):
            self._saved_tree.topLevelItem(top_index).setCheckState(0, Qt.CheckState.Unchecked)
        self.set_status("Saved-page checks cleared.")

    def _diagnose_current_saved_page(self) -> None:
        payload = self._saved_item_payload(self._saved_tree.currentItem())
        if payload is None or not payload.get("url"):
            self.set_status("Choose a saved page before checking its connection.")
            return
        self.diagnostics_requested.emit(WebDiagnosticsRequest(url=str(payload["url"])))

    def _remove_current_saved_item(self) -> None:
        item = self._saved_tree.currentItem()
        payload = self._saved_item_payload(item)
        kind = str(item.data(0, self._ROLE_KIND) or "") if item is not None else ""
        if payload is None:
            self.set_status("Highlight a saved page or website before removing it.")
            return
        if kind == "page" and payload.get("page_id"):
            self.remove_saved_page_requested.emit(
                WebRemoveSavedPageRequest(
                    website_id=str(payload.get("website_id", "")),
                    page_id=str(payload.get("page_id", "")),
                )
            )
            return
        if kind == "website" and payload.get("website_id"):
            self.remove_saved_website_requested.emit(
                WebRemoveSavedWebsiteRequest(website_id=str(payload["website_id"]))
            )
            return
        self.set_status("Highlight a saved page or website before removing it.")

    # --- Linked pages ---

    def _refresh_link_sources(self) -> None:
        if not hasattr(self, "_link_source"):
            return
        current_data = self._link_source.currentData()
        current_url = str(current_data.get("url", "")) if isinstance(current_data, dict) else ""
        candidates: list[dict] = []
        seen: set[str] = set()

        entered, _, _ = self._entered_url_values()
        for url in entered:
            key = url.casefold()
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"label": f"Entered: {self._short_url(url)}", "url": url})

        for website in self._registry:
            website_id = website.id
            website_name = website.name
            for page in website.pages:
                url = page.url
                if not url or url.casefold() in seen:
                    continue
                seen.add(url.casefold())
                candidates.append(
                    {
                        "label": f"Saved: {website_name} / {page.label}",
                        "url": url,
                        "website_id": website_id,
                        "page_id": page.id,
                    }
                )

        self._link_source.blockSignals(True)
        self._link_source.clear()
        if not candidates:
            self._link_source.addItem("Enter or save a page first", None)
        else:
            selected_index = 0
            for index, candidate in enumerate(candidates):
                self._link_source.addItem(candidate["label"], candidate)
                self._link_source.setItemData(index, candidate["url"], Qt.ItemDataRole.ToolTipRole)
                if candidate["url"] == current_url:
                    selected_index = index
            self._link_source.setCurrentIndex(selected_index)
        self._link_source.blockSignals(False)
        self._find_links_btn.setEnabled(bool(candidates))

    def _emit_discover_links(self) -> None:
        payload = self._link_source.currentData()
        if not isinstance(payload, dict) or not payload.get("url"):
            self.set_status("Choose a page in Discover from before finding linked pages.")
            return
        self.discover_links_requested.emit(
            WebLinkDiscoveryRequest(
                url=str(payload["url"]),
                website_id=str(payload.get("website_id")) if payload.get("website_id") else None,
                page_id=str(payload.get("page_id")) if payload.get("page_id") else None,
            )
        )

    def _refresh_link_list(self, *, capture_selection: bool = True) -> None:
        if capture_selection:
            self._capture_link_selection()
        query = self._links_search.text().strip().casefold()
        self._links.blockSignals(True)
        self._links.clear()
        visible_count = 0
        for link in self._linked_items:
            haystack = f"{link.label} {link.url} {link.source_page or ''}".casefold()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(f"{link.label}\n{link.url}")
            item.setData(Qt.ItemDataRole.UserRole, link)
            item.setToolTip(link.url)
            self._links.addItem(item)
            item.setSelected(link.url in self._selected_link_urls)
            visible_count += 1
        self._links.blockSignals(False)
        selected_count = len(self._selected_link_urls)
        total = len(self._linked_items)
        self._links_count.setText(f"{visible_count}/{total} shown; {selected_count} selected")
        self._scan_links_btn.setEnabled(selected_count > 0)
        self._refresh_link_actions()

    def _capture_link_selection(self) -> None:
        visible_urls: set[str] = set()
        selected_urls: set[str] = set()
        for row in range(self._links.count()):
            item = self._links.item(row)
            link = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(link, WebIndexLink):
                continue
            visible_urls.add(link.url)
            if item.isSelected():
                selected_urls.add(link.url)
        self._selected_link_urls.difference_update(visible_urls)
        self._selected_link_urls.update(selected_urls)
        if hasattr(self, "_links_count"):
            self._links_count.setText(
                f"{self._links.count()}/{len(self._linked_items)} shown; {len(self._selected_link_urls)} selected"
            )
            self._scan_links_btn.setEnabled(bool(self._selected_link_urls))
            self._refresh_link_actions()

    def _selected_link_items(self) -> list[WebIndexLink]:
        self._capture_link_selection()
        return [link for link in self._linked_items if link.url in self._selected_link_urls]

    def _refresh_link_actions(self) -> None:
        if not hasattr(self, "_links_save_action"):
            return
        has_links = bool(self._linked_items)
        has_visible = self._links.count() > 0
        has_selection = bool(self._selected_link_urls)
        self._links_save_action.setEnabled(has_selection)
        self._links_select_visible_action.setEnabled(has_visible)
        self._links_clear_selection_action.setEnabled(has_selection)
        self._links_clear_results_action.setEnabled(has_links)

    def _save_selected_linked_pages(self) -> None:
        selected = self._selected_link_items()
        if not selected:
            self.set_status("Select one or more linked pages before saving them.")
            return
        self.save_pages_requested.emit(
            WebSavePagesRequest(
                pages=tuple(
                    WebPageBookmark(url=link.url, label=link.label)
                    for link in selected
                ),
            )
        )

    def _emit_linked_scan(self) -> None:
        selected = self._selected_link_items()
        if not selected:
            self.set_status("Select one or more linked pages before scanning.")
            return
        source = self._link_source.currentData()
        self.scan_requested.emit(
            WebScanRequest(
                urls=tuple(link.url for link in selected),
                smart=self.smart_options(),
                origin=ScanOrigin.LINKED,
                website_id=(str(source.get("website_id")) if isinstance(source, dict) and source.get("website_id") else None),
                page_id=(str(source.get("page_id")) if isinstance(source, dict) and source.get("page_id") else None),
            )
        )

    def _select_visible_links(self) -> None:
        for row in range(self._links.count()):
            self._links.item(row).setSelected(True)
        self._capture_link_selection()

    def _clear_link_selection(self) -> None:
        self._selected_link_urls.clear()
        self._links.clearSelection()
        self._refresh_link_list(capture_selection=False)

    def _clear_linked_pages(self) -> None:
        self.clear_linked_pages_requested.emit()

    # --- Found files ---

    def _refresh_results(self, *, capture_selection: bool = True) -> None:
        if capture_selection:
            self._capture_result_selection()
        query = self._results_search.text().strip().casefold()
        excluded = self._excluded_terms()
        allowed = {ext for ext, action in self._format_actions.items() if action.isChecked()}

        self._results.blockSignals(True)
        self._results.clear()
        visible_count = 0
        for file_item in self._found_files:
            ext = (file_item.ext or "").lower()
            filter_ext = ".jpg" if ext == ".jpeg" else ext
            haystack = " ".join(
                (file_item.name, file_item.url, file_item.source_page or "", ext)
            ).casefold()
            if filter_ext not in allowed:
                continue
            if query and query not in haystack:
                continue
            if excluded and any(term in haystack for term in excluded):
                continue

            source = self._short_url(file_item.source_page or file_item.url)
            row = QTreeWidgetItem([file_item.name or "download", ext.lstrip(".").upper(), source])
            row.setData(0, Qt.ItemDataRole.UserRole, file_item)
            row.setToolTip(0, file_item.url)
            row.setToolTip(2, file_item.source_page or file_item.url)
            self._results.addTopLevelItem(row)
            row.setSelected(file_item.url in self._selected_file_urls)
            visible_count += 1
        self._results.blockSignals(False)
        total = len(self._found_files)
        selected = len(self._selected_file_urls)
        self._results_count.setText(f"{visible_count}/{total} shown; {selected} selected")
        self._download_btn.setEnabled(selected > 0)
        self._update_selection_detail()
        if total and visible_count == 0:
            self.set_status(
                f"Found Files contains {total} item(s), but the current search or file-type filters hide all stored results."
            )

    def _capture_result_selection(self) -> None:
        visible_urls: set[str] = set()
        selected_urls: set[str] = set()
        for row_index in range(self._results.topLevelItemCount()):
            row = self._results.topLevelItem(row_index)
            file_item = row.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(file_item, WebItem):
                continue
            visible_urls.add(file_item.url)
            if row.isSelected():
                selected_urls.add(file_item.url)
        self._selected_file_urls.difference_update(visible_urls)
        self._selected_file_urls.update(selected_urls)

    def _on_result_selection_changed(self) -> None:
        self._capture_result_selection()
        self._results_count.setText(
            f"{self._results.topLevelItemCount()}/{len(self._found_files)} shown; "
            f"{len(self._selected_file_urls)} selected"
        )
        self._download_btn.setEnabled(bool(self._selected_file_urls))
        self._update_selection_detail()

    def _update_selection_detail(self) -> None:
        selected = self._selected_result_items()
        if not selected:
            self._selection_detail.setText("Select a file to see its source URL.")
            return
        first = selected[0]
        prefix = f"{len(selected)} selected. " if len(selected) > 1 else ""
        self._selection_detail.setText(
            f"{prefix}{first.name} | {first.ext or 'unknown type'} | {first.confidence.value} | {first.url}"
        )

    def _selected_result_items(self) -> list[WebItem]:
        self._capture_result_selection()
        return [item for item in self._found_files if item.url in self._selected_file_urls]

    def _select_all_visible_results(self) -> None:
        self._results.selectAll()
        self._on_result_selection_changed()

    def _clear_result_selection(self) -> None:
        self._selected_file_urls.clear()
        self._results.clearSelection()
        self._refresh_results(capture_selection=False)

    def _clear_found_files(self) -> None:
        self.clear_found_files_requested.emit()

    def _reset_file_filters(self) -> None:
        self._results_search.clear()
        self._exclude_words.clear()
        for action in self._format_actions.values():
            action.setChecked(True)
        self._refresh_results()

    def _emit_download(self) -> None:
        selected = self._selected_result_items()
        if not selected:
            self.set_status("Select at least one found file before downloading.")
            return
        website_id, page_id = self.selected_source_ids()
        self.download_requested.emit(
            WebDownloadRequest(
                items=tuple(selected),
                smart=self.smart_options(),
                target=ImportTarget.NORMAL,
                website_id=website_id,
                page_id=page_id,
            )
        )

    def _show_scan_status(self, latest: ScanResults, *, merge: ScanMergeResult | None = None) -> None:
        total = len(self._found_files)
        failed = tuple(latest.failed_pages or ())
        failure_note = self._scan_failure_note(failed)
        tooltip = self._scan_failure_tooltip(failed)
        if merge is None:
            text = f"Found Files contains {total} item(s); scanner filtered out {latest.filtered_count}."
        else:
            text = f"Added {merge.added_count} new item(s); {total} total"
            if merge.duplicate_count:
                text += f"; ignored {merge.duplicate_count} duplicate(s)"
            if latest.filtered_count:
                text += f"; scanner filtered out {latest.filtered_count}"
            text += "."
        if failed:
            text += f" {failure_note}"
        if total and self._results.topLevelItemCount() == 0:
            text += " Current search or file-type filters hide all stored results."
        self._set_status_text(text, tooltip)

    def _excluded_terms(self) -> list[str]:
        normalized = self._exclude_words.text().strip().casefold().replace(",", " ").replace(";", " ")
        return [term for term in normalized.split() if term]

    # --- Shared helpers ---

    def _set_status_text(self, text: str, tooltip: str = "") -> None:
        self._status.setText(str(text))
        self._status.setToolTip(str(tooltip or ""))

    @staticmethod
    def _short_url(url: str, *, limit: int = 72) -> str:
        parsed = urlparse(str(url or ""))
        text = f"{parsed.netloc}{unquote(parsed.path or '/')}"
        if parsed.query:
            text += "?" + parsed.query
        if len(text) > limit:
            return text[: limit - 3].rstrip() + "..."
        return text or str(url or "")

    @staticmethod
    def _scan_failure_note(failed_pages: tuple[str, ...]) -> str:
        if not failed_pages:
            return ""
        noun = "page" if len(failed_pages) == 1 else "pages"
        return f"{len(failed_pages)} {noun} failed; hover for details."

    @staticmethod
    def _scan_failure_tooltip(failed_pages: tuple[str, ...]) -> str:
        if not failed_pages:
            return ""
        lines = ["Failed page details:"]
        lines.extend(f"- {' '.join(str(page).split())}" for page in failed_pages[:10])
        if len(failed_pages) > 10:
            lines.append(f"- ...and {len(failed_pages) - 10} more")
        return "\n".join(lines)
