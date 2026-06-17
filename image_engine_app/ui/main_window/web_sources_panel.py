"""Web Sources panel.

This is a thin UI shell.
- UI emits scan/download requests.
- Controller performs scan/download and calls set_results()/set_status().

Keeping UI simple makes the scan/download workflow safer to maintain.
"""

from __future__ import annotations

from dataclasses import asdict
import re
import unicodedata
from urllib.parse import unquote, urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.app.web_sources_models import Confidence, ImportTarget, ScanResults, SmartOptions, WebIndexLink, WebItem


class WebSourcesPanel(QFrame):
    """Main-window tab panel for Website/Area scanning + importing."""

    LINKED_PAGE_SCAN_CAP = 100

    scan_requested = Signal(object)      # payload dict
    index_links_requested = Signal(object)  # payload dict
    index_scan_all_requested = Signal(object)  # payload dict
    multi_scan_requested = Signal(object)  # payload dict
    download_requested = Signal(object)  # payload dict
    registry_changed = Signal(object)    # payload list[dict]
    network_diagnostics_requested = Signal(object)  # payload dict

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._website = QComboBox(self)
        self._area = QComboBox(self)
        self._saved_page = QComboBox(self)
        self._scan_btn = QPushButton("Scan Page", self)
        self._scan_saved_btn = QPushButton("Scan Saved", self)
        self._source_more_btn = QToolButton(self)
        self._url_more_btn = QToolButton(self)
        self._custom_url = QLineEdit(self)
        self._selected_page_hint = QLabel("Choose a website and page to scan.", self)

        self._find_index_links_btn = QPushButton("Find Pages", self)
        self._index_more_btn = QToolButton(self)
        self._index_keyword = QLineEdit(self)
        self._index_links = QListWidget(self)
        self._manual_links = QPlainTextEdit(self)
        self._manual_count = QLabel("0 valid URL(s)", self)
        self._scan_manual_links_btn = QPushButton("Scan List", self)

        self._search = QLineEdit(self)
        self._exclude_keywords = QLineEdit(self)
        self._filter_png = QCheckBox("PNG", self)
        self._filter_gif = QCheckBox("GIF", self)
        self._filter_webp = QCheckBox("WEBP", self)
        self._filter_jpg = QCheckBox("JPG", self)
        self._filter_zip = QCheckBox("ZIP", self)

        self._show_likely = QCheckBox("Show likely links", self)
        self._skip_dupes = QCheckBox("Skip duplicates", self)
        self._allow_zip = QCheckBox("Allow ZIP imports", self)
        self._filters_btn = QToolButton(self)

        self._results = QListWidget(self)
        self._selection_detail = QLabel("Select an item to see its source URL.", self)
        self._status = QLabel("", self)

        self._destination_hint = QLabel("Auto destination: Sprite Factory routes downloads into Main / Shiny / Animated / Items.", self)
        self._download_btn = QPushButton("Download", self)

        self._download_more_btn = QToolButton(self)

        self._items: list[WebItem] = []
        self._index_link_items: list[WebIndexLink] = []
        self._syncing_saved_page = False
        self._apply_web_sources_object_names()

        self._build_ui()
        self._set_index_controls_enabled(False)

    # --- Public API for controller ---

    def set_sources(self, *, websites: list[dict], selected_website_id: str | None = None, selected_area_id: str | None = None) -> None:
        """Populate saved website/page dropdowns.

        websites format (dict):
        {"id": str, "name": str, "areas": [{"id": str, "label": str, "url": str}, ...]}
        """
        self._website.blockSignals(True)
        self._area.blockSignals(True)
        self._saved_page.blockSignals(True)

        self._website.clear()
        for w in websites:
            self._website.addItem(str(w.get("name", "Website")), w)

        # select website
        if selected_website_id:
            for i in range(self._website.count()):
                w = self._website.itemData(i)
                if isinstance(w, dict) and w.get("id") == selected_website_id:
                    self._website.setCurrentIndex(i)
                    break

        self._rebuild_areas(selected_area_id)
        self._rebuild_saved_pages()
        self._sync_saved_page_from_selection()

        self._website.blockSignals(False)
        self._area.blockSignals(False)
        self._saved_page.blockSignals(False)
        self._update_selected_page_hint()

    def set_results(self, results: ScanResults) -> None:
        """Render scan results into the list."""
        self._items = list(results.items)
        self._refresh_list()
        visible_count = self._results.count()
        failed_pages = tuple(getattr(results, "failed_pages", ()) or ())
        failure_note = self._scan_failure_note(failed_pages)
        failure_tooltip = self._scan_failure_tooltip(failed_pages)
        if not self._items and int(results.filtered_count or 0) > 0:
            self._set_status_text(
                (
                    f"Found 0 item(s); filtered out {results.filtered_count}. "
                    f"Open Filters and enable 'Show likely links'.{f' {failure_note}' if failure_note else ''}"
                ),
                failure_tooltip,
            )
            return
        if not self._items and failed_pages:
            self._set_status_text(f"Found 0 item(s). {failure_note}", failure_tooltip)
            return
        if self._items and visible_count == 0:
            self._set_status_text(
                (
                    f"Found {len(self._items)} item(s), but current search/filter options hide them."
                    f"{f' {failure_note}' if failure_note else ''}"
                ),
                failure_tooltip,
            )
            return
        self._set_status_text(
            (
                f"Found {len(self._items)} item(s); filtered out {results.filtered_count}."
                f"{f' {failure_note}' if failure_note else ''}"
            ),
            failure_tooltip,
        )

    def set_index_links(self, links: tuple[WebIndexLink, ...] | list[WebIndexLink]) -> None:
        self._index_link_items = list(links)
        self._refresh_index_link_list()
        count = len(self._index_link_items)
        self._set_index_controls_enabled(count > 0)
        if count:
            self._select_visible_index_links()
            self._status.setText(
                f"Found {count} linked page(s). Filter the list, select what you want, then scan selected pages."
            )
        else:
            self._status.setText("Found 0 linked pages. Try Scan Page for this page or choose a broader index page.")

    def set_status(self, msg: str) -> None:
        text = str(msg)
        self._set_status_text(text, text if len(text) > 120 else "")

    def _set_status_text(self, text: str, tooltip: str = "") -> None:
        self._status.setText(str(text))
        self._status.setToolTip(str(tooltip or ""))

    def sources_registry(self) -> list[dict]:
        registry: list[dict] = []
        for index in range(self._website.count()):
            source = self._website.itemData(index)
            if not isinstance(source, dict):
                continue
            source_id = str(source.get("id", "")).strip()
            name = str(source.get("name", "")).strip()
            areas_raw = source.get("areas")
            if not source_id or not name or not isinstance(areas_raw, list):
                continue
            areas: list[dict] = []
            for area in areas_raw:
                if not isinstance(area, dict):
                    continue
                area_id = str(area.get("id", "")).strip()
                label = str(area.get("label", "")).strip()
                url = str(area.get("url", "")).strip()
                if not area_id or not label or not url:
                    continue
                areas.append({"id": area_id, "label": label, "url": url})
            if not areas:
                continue
            registry.append({"id": source_id, "name": name, "areas": areas})
        return registry

    def smart_options(self) -> SmartOptions:
        return SmartOptions(
            show_likely=bool(self._show_likely.isChecked()),
            auto_sort=True,
            skip_duplicates=bool(self._skip_dupes.isChecked()),
            allow_zip=bool(self._allow_zip.isChecked()),
        )

    def set_smart_options(self, options: SmartOptions | dict | None) -> None:
        if options is None:
            return
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

        self._show_likely.setChecked(smart.show_likely)
        self._skip_dupes.setChecked(smart.skip_duplicates)
        self._allow_zip.setChecked(smart.allow_zip)

    def selected_source_ids(self) -> tuple[str | None, str | None]:
        website = self._website.currentData()
        area = self._area.currentData()
        website_id = str(website.get("id")) if isinstance(website, dict) and website.get("id") else None
        area_id = str(area.get("id")) if isinstance(area, dict) and area.get("id") else None
        return website_id, area_id

    # --- Internals ---

    def _apply_web_sources_object_names(self) -> None:
        for button in (
            self._scan_btn,
            self._scan_saved_btn,
            self._find_index_links_btn,
            self._scan_manual_links_btn,
            self._download_btn,
        ):
            button.setObjectName("webSourcesPrimaryAction")
        self._index_links.setObjectName("webSourcesIndexList")
        self._manual_links.setObjectName("webSourcesManualList")
        self._results.setObjectName("webSourcesResultsList")

    def _build_ui(self) -> None:
        self.setObjectName("webSourcesCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        outer.addWidget(self._build_source_section())
        outer.addWidget(self._build_saved_section())
        outer.addWidget(self._build_pages_section())
        outer.addWidget(self._build_results_section(), 1)
        outer.addLayout(self._build_download_footer())

        self._status.setObjectName("shellHint")
        outer.addWidget(self._status)

        # These controls are internal state for menus/filters, not direct layout widgets.
        # Hide them so Qt never paints a stray control at (0, 0).
        for orphan in (
            self._saved_page,
            self._show_likely,
            self._skip_dupes,
            self._allow_zip,
            self._filter_png,
            self._filter_gif,
            self._filter_webp,
            self._filter_jpg,
            self._filter_zip,
        ):
            orphan.hide()

        self._website.currentIndexChanged.connect(lambda _=None: self._on_website_changed())
        self._saved_page.currentIndexChanged.connect(lambda _=None: self._select_saved_page())
        self._website.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._website.customContextMenuRequested.connect(self._show_website_context_menu)
        self._area.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._area.customContextMenuRequested.connect(self._show_area_context_menu)
        self._area.currentIndexChanged.connect(lambda _=None: self._sync_saved_page_from_selection())

    def _build_source_section(self) -> QFrame:
        section, body = self._section_card(
            "1. Scan Pages",
            "Start here. Scan one page, or scan many page URLs at once.",
        )

        single_title = QLabel("Single page", self)
        single_title.setObjectName("shellTitle")
        body.addWidget(single_title)

        custom = QHBoxLayout()
        custom.setSpacing(8)
        self._custom_url.setPlaceholderText("Paste one page URL, e.g. https://example.com/sprites")
        self._custom_url.textChanged.connect(lambda _=None: self._update_selected_page_hint())
        self._scan_btn.clicked.connect(self._emit_url_scan)
        custom.addWidget(self._custom_url, 1)
        custom.addWidget(self._scan_btn)
        self._configure_more_button(
            self._url_more_btn,
            [
                ("Save URL as Page", self._add_custom_website),
                ("Clear URL", self._clear_url),
                ("Clear Page List", self._clear_manual_links),
                ("Check Pasted URL", self._emit_custom_url_network_diagnostics),
            ],
        )
        custom.addWidget(self._url_more_btn)
        body.addLayout(custom)

        manual_header = QHBoxLayout()
        manual_title = QLabel("Multiple pages", self)
        manual_title.setObjectName("shellTitle")
        manual_header.addWidget(manual_title)
        manual_hint = QLabel("Paste one full URL per line. These do not need to be saved first.", self)
        manual_hint.setObjectName("shellHint")
        manual_header.addWidget(manual_hint, 1)
        self._manual_count.setObjectName("shellHint")
        manual_header.addWidget(self._manual_count)
        body.addLayout(manual_header)

        self._manual_links.setPlaceholderText(
            "https://example.com/sprites/gen-1\nhttps://another-site.example/sprites"
        )
        self._manual_links.setFixedHeight(76)
        self._manual_links.textChanged.connect(self._update_manual_link_count)
        body.addWidget(self._manual_links)

        manual_actions = QHBoxLayout()
        manual_actions.addStretch(1)
        self._scan_manual_links_btn.clicked.connect(self._emit_manual_page_scan)
        manual_actions.addWidget(self._scan_manual_links_btn)
        body.addLayout(manual_actions)

        return section

    def _build_saved_section(self) -> QFrame:
        section, body = self._section_card(
            "2. Saved Shortcuts",
            "Reusable pages you saved from the URL box.",
        )

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_row.addLayout(self._labeled_control("Website", self._website), 1)
        picker_row.addLayout(self._labeled_control("Saved page", self._area), 2)

        self._scan_saved_btn.clicked.connect(self._emit_saved_page_scan)
        picker_row.addWidget(self._scan_saved_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self._configure_more_button(
            self._source_more_btn,
            [
                ("Scan All Saved", self._emit_saved_pages_scan),
                ("Remove Saved Page", self._remove_selected_area),
                ("Remove Website", self._remove_selected_website),
                ("Check Saved Page", self._emit_saved_page_network_diagnostics),
            ],
        )
        picker_row.addWidget(self._source_more_btn, 0, Qt.AlignmentFlag.AlignBottom)
        body.addLayout(picker_row)

        self._selected_page_hint.setObjectName("shellHint")
        body.addWidget(self._selected_page_hint)
        return section

    def _build_pages_section(self) -> QFrame:
        section, body = self._section_card(
            "3. Find Linked Pages",
            "Optional. Use this when a page is an index and you want to choose pages inside it.",
        )

        index_header = QHBoxLayout()
        index_title = QLabel("Linked pages", self)
        index_title.setObjectName("shellTitle")
        index_header.addWidget(index_title)
        index_hint = QLabel("Uses the pasted URL first, otherwise the selected saved page.", self)
        index_hint.setObjectName("shellHint")
        index_header.addWidget(index_hint, 1)
        self._find_index_links_btn.clicked.connect(self._emit_index_links_scan)
        index_header.addWidget(self._find_index_links_btn)
        self._configure_more_button(
            self._index_more_btn,
            [
                ("Scan Selected Links", self._emit_multi_page_scan),
                ("Find and Scan First 100", self._emit_index_scan_all),
                ("Select Visible Links", self._select_visible_index_links),
                ("Clear Link Selection", self._index_links.clearSelection),
                ("Clear Linked Pages", self._clear_found_pages),
            ],
        )
        index_header.addWidget(self._index_more_btn)
        body.addLayout(index_header)

        index_filter = QHBoxLayout()
        self._index_keyword.setPlaceholderText("Search linked pages, e.g. gen 1, home, animation...")
        self._index_keyword.textChanged.connect(lambda _=None: self._refresh_index_link_list())
        index_filter.addWidget(self._index_keyword, 1)
        body.addLayout(index_filter)

        self._index_links.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._index_links.setFixedHeight(96)
        body.addWidget(self._index_links)

        return section

    def _build_results_section(self) -> QFrame:
        section, body = self._section_card(
            "4. Found Files",
            "Search scan results, select the files you want, then download them into the workspace.",
        )

        options = QHBoxLayout()
        options.setSpacing(8)
        self._show_likely.setChecked(False)
        self._skip_dupes.setChecked(True)
        self._allow_zip.setChecked(True)

        filt = QHBoxLayout()
        filt.setSpacing(6)
        self._search.setPlaceholderText("Search results by filename, URL, or source page...")
        self._search.textChanged.connect(lambda _: self._refresh_list())
        self._exclude_keywords.setPlaceholderText("Exclude words, e.g. shiny, thumb")
        self._exclude_keywords.textChanged.connect(lambda _: self._refresh_list())
        for cb in (self._filter_png, self._filter_gif, self._filter_webp, self._filter_jpg, self._filter_zip):
            cb.setChecked(True)
            cb.stateChanged.connect(lambda _=None: self._refresh_list())

        search_label = QLabel("Search results", self)
        search_label.setObjectName("shellHint")
        filt.addWidget(search_label)
        filt.addWidget(self._search, 1)
        exclude_label = QLabel("Exclude words", self)
        exclude_label.setObjectName("shellHint")
        filt.addWidget(exclude_label)
        filt.addWidget(self._exclude_keywords, 0)

        filters_menu = QMenu(self._filters_btn)
        filters_menu.addAction(self._show_likely_action())
        filters_menu.addSeparator()
        filters_menu.addAction(self._checkbox_action(self._filter_png))
        filters_menu.addAction(self._checkbox_action(self._filter_gif))
        filters_menu.addAction(self._checkbox_action(self._filter_webp))
        filters_menu.addAction(self._checkbox_action(self._filter_jpg))
        filters_menu.addAction(self._checkbox_action(self._filter_zip))
        filters_menu.addSeparator()
        filters_menu.addAction(self._checkbox_action(self._skip_dupes))
        filters_menu.addAction(self._checkbox_action(self._allow_zip))
        self._filters_btn.setText("Filters")
        self._filters_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._filters_btn.setMenu(filters_menu)
        filt.addWidget(self._filters_btn)

        body.addLayout(filt)

        self._results.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._results.itemSelectionChanged.connect(self._update_preview)
        body.addWidget(self._results, 1)

        self._selection_detail.setWordWrap(True)
        self._selection_detail.setObjectName("shellHint")
        body.addWidget(self._selection_detail)

        return section

    def _build_download_footer(self) -> QHBoxLayout:
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._destination_hint.setObjectName("shellHint")
        bottom.addWidget(self._destination_hint, 1)

        self._configure_more_button(
            self._download_more_btn,
            [
                ("Select All Results", self._select_all_visible),
                ("Clear Result Selection", self._clear_selection),
                ("Clear Found Files", self._clear_found_files),
            ],
        )
        bottom.addWidget(self._download_more_btn)

        self._download_btn.clicked.connect(self._emit_download)
        bottom.addWidget(self._download_btn)

        return bottom

    def _section_card(self, title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame(self)
        section.setObjectName("webSourcesSectionCard")
        section.setFrameShape(QFrame.Shape.NoFrame)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_label = QLabel(title, self)
        title_label.setObjectName("shellTitle")
        header.addWidget(title_label)
        hint_label = QLabel(hint, self)
        hint_label.setObjectName("shellHint")
        header.addWidget(hint_label, 1)
        layout.addLayout(header)

        return section, layout

    def _labeled_control(self, label: str, widget: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        text = QLabel(label, self)
        text.setObjectName("shellHint")
        layout.addWidget(text)
        layout.addWidget(widget)
        return layout

    def _configure_more_button(self, button: QToolButton, actions: list[tuple[str, object]]) -> None:
        button.setText("More")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for label, callback in actions:
            menu.addAction(label, callback)  # type: ignore[arg-type]
        button.setMenu(menu)

    def _checkbox_action(self, checkbox: QCheckBox):
        action = QAction(checkbox.text(), self)
        action.setCheckable(True)
        action.setChecked(checkbox.isChecked())
        action.toggled.connect(checkbox.setChecked)
        checkbox.stateChanged.connect(lambda _=None, action=action, checkbox=checkbox: action.setChecked(checkbox.isChecked()))
        return action

    def _show_likely_action(self):
        action = self._checkbox_action(self._show_likely)
        action.setText("Show likely links")
        return action

    def _rebuild_areas(self, selected_area_id: str | None = None) -> None:
        self._area.clear()
        w = self._website.currentData()
        if not isinstance(w, dict):
            return
        for a in (w.get("areas") or []):
            label = self._compact_area_label(
                str(a.get("label", "Area")),
                str(a.get("url", "")),
            )
            self._area.addItem(label, a)
            index = self._area.count() - 1
            self._area.setItemData(index, str(a.get("url", "")), Qt.ItemDataRole.ToolTipRole)

        if selected_area_id:
            for i in range(self._area.count()):
                a = self._area.itemData(i)
                if isinstance(a, dict) and a.get("id") == selected_area_id:
                    self._area.setCurrentIndex(i)
                    break
        self._update_selected_page_hint()

    def _on_website_changed(self) -> None:
        self._rebuild_areas()
        self._sync_saved_page_from_selection()

    def _rebuild_saved_pages(self) -> None:
        self._saved_page.clear()
        for website_index in range(self._website.count()):
            website = self._website.itemData(website_index)
            if not isinstance(website, dict):
                continue
            website_id = str(website.get("id", "")).strip()
            website_name = str(website.get("name", "")).strip() or "Website"
            for area in website.get("areas") or []:
                if not isinstance(area, dict):
                    continue
                area_id = str(area.get("id", "")).strip()
                area_url = str(area.get("url", "")).strip()
                if not website_id or not area_id or not area_url:
                    continue
                area_label = self._compact_area_label(str(area.get("label", "")), area_url)
                combo_label = f"{website_name} - {area_label}"
                self._saved_page.addItem(
                    combo_label,
                    {
                        "website_id": website_id,
                        "area_id": area_id,
                        "url": area_url,
                    },
                )
                self._saved_page.setItemData(
                    self._saved_page.count() - 1,
                    area_url,
                    Qt.ItemDataRole.ToolTipRole,
                )

        if self._saved_page.count() == 0:
            self._saved_page.addItem("No saved pages yet", None)

    def _select_saved_page(self) -> None:
        if self._syncing_saved_page:
            return

        selection = self._saved_page.currentData()
        if not isinstance(selection, dict):
            self._update_selected_page_hint()
            return

        website_id = str(selection.get("website_id", "")).strip()
        area_id = str(selection.get("area_id", "")).strip()
        if not website_id or not area_id:
            self._update_selected_page_hint()
            return

        self._syncing_saved_page = True
        try:
            for website_index in range(self._website.count()):
                website = self._website.itemData(website_index)
                if isinstance(website, dict) and str(website.get("id", "")).strip() == website_id:
                    self._website.setCurrentIndex(website_index)
                    self._rebuild_areas(area_id)
                    break
        finally:
            self._syncing_saved_page = False
        self._update_selected_page_hint()

    def _sync_saved_page_from_selection(self) -> None:
        if self._syncing_saved_page:
            self._update_selected_page_hint()
            return

        website_id, area_id = self.selected_source_ids()
        self._syncing_saved_page = True
        self._saved_page.blockSignals(True)
        try:
            for index in range(self._saved_page.count()):
                data = self._saved_page.itemData(index)
                if (
                    isinstance(data, dict)
                    and str(data.get("website_id", "")).strip() == str(website_id or "")
                    and str(data.get("area_id", "")).strip() == str(area_id or "")
                ):
                    self._saved_page.setCurrentIndex(index)
                    break
        finally:
            self._saved_page.blockSignals(False)
            self._syncing_saved_page = False
        self._update_selected_page_hint()

    def _update_selected_page_hint(self) -> None:
        custom_url = self._custom_url.text().strip()
        if custom_url:
            self._selected_page_hint.setText(f"Pasted URL will be used for scan: {custom_url}")
            return

        area = self._area.currentData()
        if not isinstance(area, dict) or not area.get("url"):
            self._selected_page_hint.setText("Choose a website and page to scan.")
            return

        label = self._compact_area_label(str(area.get("label", "Page")), str(area.get("url", "")))
        self._selected_page_hint.setText(f"Selected page: {label} - {area['url']}")

    def _emit_scan(self) -> None:
        custom_url = self._custom_url.text().strip()
        if custom_url:
            self._emit_url_scan()
            return

        self._emit_saved_page_scan()

    def _emit_url_scan(self) -> None:
        custom_url = self._custom_url.text().strip()
        if not custom_url:
            self.set_status("Paste a URL first, or use Scan Saved for saved pages.")
            return

        normalized = self._normalize_custom_url(custom_url)
        if normalized is None:
            self.set_status("Invalid URL. Use http(s)://domain/path.")
            return

        payload = {
            "area_url": normalized[0],
            "website_id": None,
            "area_id": None,
            "smart": asdict(self.smart_options()),
        }
        self._clear_result_text_filters()
        self.set_status(f"Scanning URL: {normalized[0]}")
        self.scan_requested.emit(payload)

    def _emit_saved_page_scan(self) -> None:
        a = self._area.currentData()
        if not isinstance(a, dict) or not a.get("url"):
            self.set_status("Choose a saved page first.")
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "area_url": str(a["url"]),
            "website_id": website_id,
            "area_id": area_id,
            "smart": asdict(self.smart_options()),
        }
        self._clear_result_text_filters()
        self.set_status(f"Scanning saved page: {str(a['url'])}")
        self.scan_requested.emit(payload)

    def _emit_index_links_scan(self) -> None:
        area_payload = self._current_area_payload(status_action="find linked pages")
        if area_payload is None:
            return

        payload = {
            "index_url": area_payload["area_url"],
            "website_id": area_payload.get("website_id"),
            "area_id": area_payload.get("area_id"),
            "smart": asdict(self.smart_options()),
        }
        self._index_link_items = []
        self._refresh_index_link_list()
        self._set_index_controls_enabled(False)
        self.set_status(f"Finding linked pages: {payload['index_url']}")
        self.index_links_requested.emit(payload)

    def _emit_saved_pages_scan(self) -> None:
        links: list[dict] = []
        seen_urls: set[str] = set()
        for website_index in range(self._website.count()):
            website = self._website.itemData(website_index)
            if not isinstance(website, dict):
                continue
            areas = website.get("areas")
            if not isinstance(areas, list):
                continue
            for area in areas:
                if not isinstance(area, dict):
                    continue
                url = str(area.get("url", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                links.append(
                    {
                        "label": str(area.get("label", "")).strip() or self._compact_area_label("", url),
                        "url": url,
                        "source_page": None,
                    }
                )

        if not links:
            self.set_status("Save at least one website page before scanning all saved pages.")
            return

        original_count = len(links)
        links = self._cap_link_payloads_with_warning(links)
        if not links:
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "pages": links,
            "website_id": website_id,
            "area_id": area_id,
            "smart": asdict(self.smart_options()),
        }
        if original_count > len(links):
            self.set_status(f"Scanning first {len(links)} of {original_count} saved page(s)...")
        else:
            self.set_status(f"Scanning {len(links)} saved page(s)...")
        self._clear_result_text_filters()
        self.multi_scan_requested.emit(payload)

    def _emit_index_scan_all(self) -> None:
        area_payload = self._current_area_payload(status_action="scan linked pages")
        if area_payload is None:
            return

        payload = {
            "index_url": area_payload["area_url"],
            "website_id": area_payload.get("website_id"),
            "area_id": area_payload.get("area_id"),
            "smart": asdict(self.smart_options()),
        }
        self._index_link_items = []
        self._refresh_index_link_list()
        self._set_index_controls_enabled(False)
        self._clear_result_text_filters()
        self.set_status(f"Finding and scanning linked pages: {payload['index_url']}")
        self.index_scan_all_requested.emit(payload)

    def _emit_multi_page_scan(self) -> None:
        if not self._index_link_items:
            self.set_status("Click Find Pages first, then scan the linked pages you want.")
            return

        selected_links = self._selected_index_link_payloads()
        if not selected_links:
            selected_links = self._visible_index_link_payloads()
        if not selected_links:
            self.set_status("Select one or more linked pages first.")
            return
        original_count = len(selected_links)
        selected_links = self._cap_link_payloads_with_warning(selected_links)
        if not selected_links:
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "pages": selected_links,
            "website_id": website_id,
            "area_id": area_id,
            "smart": asdict(self.smart_options()),
        }
        if original_count > len(selected_links):
            self.set_status(f"Scanning first {len(selected_links)} of {original_count} linked page(s)...")
        else:
            self.set_status(f"Scanning {len(selected_links)} linked page(s)...")
        self._clear_result_text_filters()
        self.multi_scan_requested.emit(payload)

    def _emit_manual_page_scan(self) -> None:
        links, invalid_count, duplicate_count = self._manual_index_links()
        if not links:
            self.set_status("Paste one or more valid page URLs to scan manually.")
            return

        payload_links = [asdict(link) for link in links]
        original_count = len(payload_links)
        payload_links = self._cap_link_payloads_with_warning(payload_links)
        if not payload_links:
            return

        skipped_parts: list[str] = []
        if invalid_count:
            skipped_parts.append(f"{invalid_count} invalid")
        if duplicate_count:
            skipped_parts.append(f"{duplicate_count} duplicate")

        website_id, area_id = self.selected_source_ids()
        payload = {
            "pages": payload_links,
            "website_id": website_id,
            "area_id": area_id,
            "smart": asdict(self.smart_options()),
        }

        if original_count > len(payload_links):
            message = f"Scanning first {len(payload_links)} of {original_count} manual page URL(s)"
        else:
            message = f"Scanning {len(payload_links)} manual page URL(s)"
        if skipped_parts:
            message = f"{message}; skipped {', '.join(skipped_parts)}"
        self._clear_result_text_filters()
        self.set_status(f"{message}...")
        self.multi_scan_requested.emit(payload)

    def _emit_custom_url_network_diagnostics(self) -> None:
        custom_url = self._custom_url.text().strip()
        if not custom_url:
            self.set_status("Paste a URL before running a pasted URL network check.")
            return

        normalized = self._normalize_custom_url(custom_url)
        if normalized is None:
            self.set_status("Invalid URL. Use http(s)://domain/path.")
            return
        payload = {
            "area_url": normalized[0],
            "website_id": None,
            "area_id": None,
        }
        self.set_status(f"Running network diagnostics for pasted URL: {normalized[0]}")
        self.network_diagnostics_requested.emit(payload)

    def _emit_saved_page_network_diagnostics(self) -> None:
        a = self._area.currentData()
        if not isinstance(a, dict) or not a.get("url"):
            self.set_status("Choose a saved page before running a saved page network check.")
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "area_url": str(a["url"]),
            "website_id": website_id,
            "area_id": area_id,
        }
        self.set_status(f"Running network diagnostics for saved page: {str(a['url'])}")
        self.network_diagnostics_requested.emit(payload)

    def _current_area_payload(self, *, status_action: str) -> dict | None:
        custom_url = self._custom_url.text().strip()
        if custom_url:
            normalized = self._normalize_custom_url(custom_url)
            if normalized is None:
                self.set_status("Invalid URL. Use http(s)://domain/path.")
                return None
            return {
                "area_url": normalized[0],
                "website_id": None,
                "area_id": None,
            }

        area = self._area.currentData()
        if not isinstance(area, dict) or not area.get("url"):
            self.set_status(f"Enter a URL or pick a saved page to {status_action}.")
            return None

        website_id, area_id = self.selected_source_ids()
        return {
            "area_url": str(area["url"]),
            "website_id": website_id,
            "area_id": area_id,
        }

    def _manual_index_links(self) -> tuple[list[WebIndexLink], int, int]:
        links: list[WebIndexLink] = []
        seen_urls: set[str] = set()
        invalid_count = 0
        duplicate_count = 0

        for raw_line in self._manual_links.toPlainText().splitlines():
            raw_url = raw_line.strip()
            if not raw_url:
                continue

            normalized = self._normalize_custom_url(raw_url)
            if normalized is None:
                invalid_count += 1
                continue

            url = normalized[0]
            if url in seen_urls:
                duplicate_count += 1
                continue

            seen_urls.add(url)
            links.append(
                WebIndexLink(
                    label=self._compact_area_label("", url),
                    url=url,
                    source_page=None,
                )
            )

        return links, invalid_count, duplicate_count

    def _update_manual_link_count(self) -> None:
        links, invalid_count, duplicate_count = self._manual_index_links()
        detail = f"{len(links)} valid URL(s)"
        skipped: list[str] = []
        if invalid_count:
            skipped.append(f"{invalid_count} invalid")
        if duplicate_count:
            skipped.append(f"{duplicate_count} duplicate")
        if skipped:
            detail = f"{detail}; {', '.join(skipped)} skipped"
        self._manual_count.setText(detail)

    def _clear_manual_links(self) -> None:
        self._manual_links.clear()
        self._update_manual_link_count()

    def _clear_url(self) -> None:
        self._custom_url.clear()
        self._update_selected_page_hint()
        self.set_status("URL cleared.")

    def _clear_found_pages(self) -> None:
        self._index_link_items = []
        self._refresh_index_link_list()
        self._set_index_controls_enabled(False)
        self.set_status("Linked pages cleared.")

    def _clear_found_files(self) -> None:
        self._items = []
        self._refresh_list()
        self._selection_detail.setText("Select an item to see its source URL.")
        self.set_status("Found files cleared.")

    def _emit_download(self) -> None:
        selected = self._selected_items_payloads()
        if not selected:
            self.set_status("Select at least one item to download.")
            return

        website_id, area_id = self.selected_source_ids()
        area = self._area.currentData()
        area_url = str(area.get("url", "")).strip() if isinstance(area, dict) else ""
        area_label = str(area.get("label", "")).strip() if isinstance(area, dict) else ""

        payload = {
            "items": [asdict(x) for x in selected],
            "target": ImportTarget.NORMAL.value,
            "website_id": website_id,
            "area_id": area_id,
            "area_url": area_url or None,
            "area_label": area_label or None,
            "smart": asdict(self.smart_options()),
        }
        self.set_status("Downloading with smart routing...")
        self.download_requested.emit(payload)

    def _add_custom_website(self) -> None:
        raw_url = self._custom_url.text().strip()
        if not raw_url:
            self.set_status("Enter a website URL to add.")
            return

        normalized = self._normalize_custom_url(raw_url)
        if normalized is None:
            self.set_status("Invalid URL. Use http(s)://domain/path.")
            return

        normalized_url, host = normalized
        sources = self.sources_registry()
        source = self._find_source_by_host(sources, host)

        if source is None:
            existing_ids = {str(item.get("id", "")).strip() for item in sources if isinstance(item, dict)}
            source_id = self._next_unique_id(self._slugify(host) or "custom_site", existing_ids)
            source = {"id": source_id, "name": host, "areas": []}
            sources.append(source)

        areas = source.get("areas")
        if not isinstance(areas, list):
            areas = []
            source["areas"] = areas

        existing_area_ids = {str(a.get("id", "")).strip() for a in areas if isinstance(a, dict)}
        existing_urls = {str(a.get("url", "")).strip() for a in areas if isinstance(a, dict)}

        selected_area_id: str | None = None
        created = False
        if normalized_url in existing_urls:
            selected_area = next(
                (
                    area
                    for area in areas
                    if isinstance(area, dict) and str(area.get("url", "")).strip() == normalized_url
                ),
                None,
            )
            if isinstance(selected_area, dict):
                selected_area_id = str(selected_area.get("id", "")).strip() or None
        else:
            parsed = urlparse(normalized_url)
            path_parts = [part for part in str(parsed.path or "").split("/") if part]
            area_label = self._path_label_from_parts(path_parts)
            if parsed.query:
                area_label = f"{area_label} (Query)"
            area_id = self._next_unique_id(self._slugify(area_label) or "page", existing_area_ids)
            areas.append({"id": area_id, "label": area_label, "url": normalized_url})
            selected_area_id = area_id
            created = True

        source_id = str(source.get("id", "")).strip()
        self.set_sources(websites=sources, selected_website_id=source_id, selected_area_id=selected_area_id)
        self._custom_url.clear()
        self.registry_changed.emit(self.sources_registry())

        if created:
            self.set_status(f"Saved page: {normalized_url}")
        else:
            self.set_status("Page URL already exists in the saved list.")

    @staticmethod
    def _normalize_custom_url(raw_url: str) -> tuple[str, str] | None:
        candidate = (raw_url or "").strip()
        if not candidate:
            return None

        if "://" not in candidate:
            candidate = f"https://{candidate}"

        parsed = urlparse(candidate)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            return None

        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        return candidate, host

    @staticmethod
    def _friendly_path_segment(segment: str) -> str:
        raw = WebSourcesPanel._ascii_clean(unquote(segment or "")).strip().replace("-", " ").replace("_", " ")
        words = [word for word in raw.split() if word]
        if not words:
            return "Area"
        return " ".join(word.capitalize() for word in words)

    @classmethod
    def _path_label_from_parts(cls, path_parts: list[str]) -> str:
        friendly_parts = [cls._friendly_path_segment(part) for part in path_parts if str(part or "").strip()]
        if not friendly_parts:
            return "Root"
        if len(friendly_parts) > 3:
            friendly_parts = ["..."] + friendly_parts[-3:]
        return " / ".join(friendly_parts)

    @classmethod
    def _compact_area_label(cls, label: str, url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        path_parts = [part for part in str(parsed.path or "").split("/") if part]
        clean = cls._path_label_from_parts(path_parts)
        if parsed.query:
            clean = f"{clean} (Query)"

        if not path_parts:
            fallback = " ".join(cls._ascii_clean(unquote(label or "")).split())
            clean = fallback or "Root"

        max_len = 72
        if len(clean) > max_len:
            clean = f"{clean[: max_len - 3].rstrip()}..."
        return clean or "Area"

    @staticmethod
    def _ascii_clean(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        return normalized.encode("ascii", "ignore").decode("ascii")

    @staticmethod
    def _slugify(value: str) -> str:
        out = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or ""))
        return "_".join(part for part in out.split("_") if part)

    @staticmethod
    def _next_unique_id(base: str, existing: set[str]) -> str:
        candidate = base.strip() or "custom"
        if candidate not in existing:
            return candidate
        index = 2
        while True:
            next_candidate = f"{candidate}_{index}"
            if next_candidate not in existing:
                return next_candidate
            index += 1

    @staticmethod
    def _find_source_by_host(sources: list[dict], host: str) -> dict | None:
        for source in sources:
            if not isinstance(source, dict):
                continue
            areas = source.get("areas")
            if not isinstance(areas, list):
                continue
            for area in areas:
                if not isinstance(area, dict):
                    continue
                parsed = urlparse(str(area.get("url", "")).strip())
                netloc = parsed.netloc.lower()
                if netloc.startswith("www."):
                    netloc = netloc[4:]
                if netloc and netloc == host:
                    return source
        return None
    def _show_website_context_menu(self, pos) -> None:  # noqa: ANN001
        menu = QMenu(self)
        remove_action = menu.addAction("Remove Website")
        chosen = menu.exec(self._website.mapToGlobal(pos))
        if chosen is remove_action:
            self._remove_selected_website()
    def _show_area_context_menu(self, pos) -> None:  # noqa: ANN001
        menu = QMenu(self)
        remove_action = menu.addAction("Remove URL")
        chosen = menu.exec(self._area.mapToGlobal(pos))
        if chosen is remove_action:
            self._remove_selected_area()
    def _remove_selected_website(self) -> None:
        source = self._website.currentData()
        if not isinstance(source, dict):
            self.set_status("No website selected.")
            return

        source_id = str(source.get("id", "")).strip()
        source_name = str(source.get("name", source_id or "Website")).strip() or "Website"
        if not source_id:
            self.set_status("No website selected.")
            return

        sources = self.sources_registry()
        remove_index = next(
            (
                index
                for index, item in enumerate(sources)
                if isinstance(item, dict) and str(item.get("id", "")).strip() == source_id
            ),
            None,
        )
        if remove_index is None:
            self.set_status("Website not found.")
            return

        sources.pop(remove_index)

        selected_website_id: str | None = None
        selected_area_id: str | None = None
        if sources:
            next_index = min(remove_index, len(sources) - 1)
            next_source = sources[next_index] if isinstance(sources[next_index], dict) else None
            if isinstance(next_source, dict):
                selected_website_id = str(next_source.get("id", "")).strip() or None
                next_areas = next_source.get("areas")
                if isinstance(next_areas, list) and next_areas:
                    first_area = next_areas[0]
                    if isinstance(first_area, dict):
                        selected_area_id = str(first_area.get("id", "")).strip() or None

        self.set_sources(
            websites=sources,
            selected_website_id=selected_website_id,
            selected_area_id=selected_area_id,
        )
        self._clear_results_for_registry_change()
        self.registry_changed.emit(self.sources_registry())
        self.set_status(f"Removed website: {source_name}")

    def _remove_selected_area(self) -> None:
        source = self._website.currentData()
        area = self._area.currentData()
        if not isinstance(source, dict) or not isinstance(area, dict):
            self.set_status("No URL selected.")
            return

        source_id = str(source.get("id", "")).strip()
        source_name = str(source.get("name", source_id or "Website")).strip() or "Website"
        area_id = str(area.get("id", "")).strip()
        area_label = str(area.get("label", "URL")).strip() or "URL"
        if not source_id or not area_id:
            self.set_status("No URL selected.")
            return

        sources = self.sources_registry()
        source_index = next(
            (
                index
                for index, item in enumerate(sources)
                if isinstance(item, dict) and str(item.get("id", "")).strip() == source_id
            ),
            None,
        )
        if source_index is None:
            self.set_status("Selected website not found.")
            return

        target_source = sources[source_index]
        if not isinstance(target_source, dict):
            self.set_status("Selected website not found.")
            return

        areas = target_source.get("areas")
        if not isinstance(areas, list):
            self.set_status("Selected URL not found.")
            return

        remove_area_index = next(
            (
                index
                for index, item in enumerate(areas)
                if isinstance(item, dict) and str(item.get("id", "")).strip() == area_id
            ),
            None,
        )
        if remove_area_index is None:
            self.set_status("Selected URL not found.")
            return

        areas.pop(remove_area_index)

        selected_website_id: str | None = source_id
        selected_area_id: str | None = None
        if areas:
            next_area_index = min(remove_area_index, len(areas) - 1)
            next_area = areas[next_area_index]
            if isinstance(next_area, dict):
                selected_area_id = str(next_area.get("id", "")).strip() or None
        else:
            sources.pop(source_index)
            if sources:
                next_source_index = min(source_index, len(sources) - 1)
                next_source = sources[next_source_index] if isinstance(sources[next_source_index], dict) else None
                if isinstance(next_source, dict):
                    selected_website_id = str(next_source.get("id", "")).strip() or None
                    next_areas = next_source.get("areas")
                    if isinstance(next_areas, list) and next_areas:
                        first_area = next_areas[0]
                        if isinstance(first_area, dict):
                            selected_area_id = str(first_area.get("id", "")).strip() or None
            else:
                selected_website_id = None
                selected_area_id = None

        self.set_sources(
            websites=sources,
            selected_website_id=selected_website_id,
            selected_area_id=selected_area_id,
        )
        self._clear_results_for_registry_change()
        self.registry_changed.emit(self.sources_registry())
        self.set_status(f"Removed URL: {area_label} ({source_name})")

    def _clear_results_for_registry_change(self) -> None:
        self._items = []
        self._index_link_items = []
        self._refresh_list()
        self._refresh_index_link_list()
        self._set_index_controls_enabled(False)
        self._selection_detail.setText("Select an item to see its source URL.")

    def _refresh_list(self) -> None:
        self._results.clear()
        query = self._search.text().strip().lower()
        excluded_terms = self._excluded_result_terms()

        allow = set()
        if self._filter_png.isChecked():
            allow.add(".png")
        if self._filter_gif.isChecked():
            allow.add(".gif")
        if self._filter_webp.isChecked():
            allow.add(".webp")
        if self._filter_jpg.isChecked():
            allow.add(".jpg")
            allow.add(".jpeg")
        if self._filter_zip.isChecked():
            allow.add(".zip")

        for item in self._items:
            name = item.name or ""
            ext = (item.ext or "").lower()
            haystack = " ".join(
                (
                    name,
                    ext,
                    item.url or "",
                    item.source_page or "",
                )
            ).lower()
            if allow and ext and ext not in allow:
                continue
            if query and query not in haystack:
                continue
            if excluded_terms and any(term in haystack for term in excluded_terms):
                continue

            badge = "DIRECT"
            if item.confidence == Confidence.LIKELY:
                badge = "LIKELY"
            elif item.confidence == Confidence.UNKNOWN:
                badge = "UNKNOWN"

            label = f"[{badge}] {name}  ({ext.lstrip('.') if ext else 'file'})"
            lw = QListWidgetItem(label)
            lw.setToolTip(item.url)
            lw.setData(Qt.ItemDataRole.UserRole, item)
            self._results.addItem(lw)

    def _excluded_result_terms(self) -> list[str]:
        raw = self._exclude_keywords.text().strip().lower()
        if not raw:
            return []
        normalized = raw.replace(",", " ").replace(";", " ")
        return [term for term in normalized.split() if term]

    @staticmethod
    def _scan_failure_note(failed_pages: tuple[str, ...]) -> str:
        if not failed_pages:
            return ""
        reason = WebSourcesPanel._scan_failure_reason(failed_pages[0])
        suffix = f" ({reason})" if reason else ""
        noun = "page" if len(failed_pages) == 1 else "pages"
        return f"{len(failed_pages)} {noun} failed{suffix}. Hover for details."

    @staticmethod
    def _scan_failure_tooltip(failed_pages: tuple[str, ...]) -> str:
        if not failed_pages:
            return ""
        lines = ["Failed page details:"]
        for page in failed_pages[:10]:
            lines.append(f"- {' '.join(str(page).split())}")
        if len(failed_pages) > 10:
            lines.append(f"- ...and {len(failed_pages) - 10} more")
        return "\n".join(lines)

    @staticmethod
    def _scan_failure_reason(failure: str) -> str:
        text = " ".join(str(failure or "").split())
        http_match = re.search(r"HTTP\s+(\d{3})(?:\s*\(([^)]+)\))?", text, flags=re.IGNORECASE)
        if http_match:
            code = http_match.group(1)
            label = " ".join(str(http_match.group(2) or "").split())
            return f"HTTP {code}{f' {label}' if label else ''}"
        if "timeout" in text.lower() or "timed out" in text.lower():
            return "timeout"
        return ""

    def _refresh_index_link_list(self) -> None:
        self._index_links.clear()
        query = self._index_keyword.text().strip().lower()

        for link in self._index_link_items:
            haystack = f"{link.label} {link.url} {link.source_page or ''}".lower()
            if query and query not in haystack:
                continue

            item = QListWidgetItem(f"{link.label}\n{link.url}")
            item.setToolTip(link.url)
            item.setData(Qt.ItemDataRole.UserRole, link)
            self._index_links.addItem(item)

    def _selected_index_link_payloads(self) -> list[dict]:
        selected = self._index_links.selectedItems()
        if not selected:
            return []

        out: list[dict] = []
        for item in selected:
            link = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(link, WebIndexLink):
                out.append(asdict(link))
        return out

    def _visible_index_link_payloads(self) -> list[dict]:
        out: list[dict] = []
        for row in range(self._index_links.count()):
            item = self._index_links.item(row)
            if item is None:
                continue
            link = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(link, WebIndexLink):
                out.append(asdict(link))
        return out

    def _select_visible_index_links(self) -> None:
        self._index_links.selectAll()

    def _clear_result_text_filters(self) -> None:
        if self._search.text():
            self._search.clear()
        if self._exclude_keywords.text():
            self._exclude_keywords.clear()

    def _set_index_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._index_keyword,
        ):
            widget.setEnabled(bool(enabled))

    def confirm_large_linked_page_scan(self, page_count: int, *, cap: int | None = None) -> bool:
        limit = int(cap or self.LINKED_PAGE_SCAN_CAP)
        if int(page_count) <= limit:
            return True

        answer = QMessageBox.question(
            self,
            "Large linked-page scan",
            (
                f"This index has {page_count} linked pages.\n\n"
                "Scanning too many pages at once can make the app slow or unstable.\n"
                f"Sprite Factory will scan the first {limit} pages only.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _cap_link_payloads_with_warning(self, links: list[dict]) -> list[dict]:
        cap = int(self.LINKED_PAGE_SCAN_CAP)
        if len(links) <= cap:
            return links
        if not self.confirm_large_linked_page_scan(len(links), cap=cap):
            self.set_status("Linked-page scan cancelled before starting.")
            return []
        return links[:cap]

    def _selected_items_payloads(self) -> list[WebItem]:
        selected = self._results.selectedItems()
        if not selected:
            return []
        out: list[WebItem] = []
        for lw in selected:
            meta = lw.data(Qt.ItemDataRole.UserRole)
            if isinstance(meta, WebItem):
                out.append(meta)
        return out

    def _update_preview(self) -> None:
        selected = self._selected_items_payloads()
        if not selected:
            self._selection_detail.setText("Select an item to see its source URL.")
            return
        item = selected[0]
        self._selection_detail.setText(
            f"Selected: {item.name}  |  {item.ext}  |  {item.confidence.value}  |  {item.url}"
        )

    def _select_all_visible(self) -> None:
        self._results.selectAll()

    def _clear_selection(self) -> None:
        self._results.clearSelection()











