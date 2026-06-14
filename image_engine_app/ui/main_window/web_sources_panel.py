"""Web Sources panel (scaffold).

This is a thin UI shell.
- UI emits scan/download requests.
- Controller performs scan/download and calls set_results()/set_status().

Keeping UI dumb makes patches safer.
"""

from __future__ import annotations

from dataclasses import asdict
import unicodedata
from urllib.parse import quote, unquote, urlparse

from PySide6.QtCore import Qt, Signal
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
        self._scan_btn = QPushButton("Scan Current Page", self)
        self._diagnose_btn = QPushButton("Network Check", self)
        self._source_more_btn = QToolButton(self)
        self._custom_url = QLineEdit(self)
        self._add_site_btn = QPushButton("Add Website URL", self)
        self._selected_page_hint = QLabel("Choose a website and page to scan.", self)

        self._find_index_links_btn = QPushButton("Find Pages", self)
        self._scan_index_all_btn = QPushButton("Find + Scan First 100", self)
        self._scan_selected_pages_btn = QPushButton("Scan Selected", self)
        self._index_more_btn = QToolButton(self)
        self._index_keyword = QLineEdit(self)
        self._index_links = QListWidget(self)
        self._select_index_visible_btn = QToolButton(self)
        self._clear_index_sel_btn = QToolButton(self)
        self._manual_links = QPlainTextEdit(self)
        self._manual_count = QLabel("0 valid URL(s)", self)
        self._scan_manual_links_btn = QPushButton("Scan List", self)
        self._clear_manual_links_btn = QToolButton(self)

        self._search = QLineEdit(self)
        self._filter_png = QCheckBox("PNG", self)
        self._filter_gif = QCheckBox("GIF", self)
        self._filter_webp = QCheckBox("WEBP", self)
        self._filter_jpg = QCheckBox("JPG", self)
        self._filter_zip = QCheckBox("ZIP", self)

        self._show_likely = QCheckBox("Show likely links", self)
        self._skip_dupes = QCheckBox("Skip duplicates", self)
        self._allow_zip = QCheckBox("Allow ZIP imports", self)

        self._results = QListWidget(self)
        self._selection_detail = QLabel("Select an item to see its source URL.", self)
        self._status = QLabel("", self)

        self._destination_hint = QLabel("Auto destination: Sprite Factory routes downloads into Main / Shiny / Animated / Items.", self)
        self._download_btn = QPushButton("Download Selected", self)

        self._select_all_btn = QToolButton(self)
        self._clear_sel_btn = QToolButton(self)

        self._items: list[WebItem] = []
        self._index_link_items: list[WebIndexLink] = []
        self._syncing_saved_page = False
        self._apply_web_sources_object_names()

        self._build_ui()
        self._set_index_controls_enabled(False)

    # --- Public API for controller ---

    def set_sources(self, *, websites: list[dict], selected_website_id: str | None = None, selected_area_id: str | None = None) -> None:
        """Populate Website + Area dropdowns.

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
        if not self._items and int(results.filtered_count or 0) > 0:
            self._status.setText(
                f"Found 0 item(s); filtered out {results.filtered_count}. Try enabling 'Show likely links'."
            )
            return
        self._status.setText(f"Found {len(self._items)} item(s); filtered out {results.filtered_count}")

    def set_index_links(self, links: tuple[WebIndexLink, ...] | list[WebIndexLink]) -> None:
        self._index_link_items = list(links)
        self._refresh_index_link_list()
        count = len(self._index_link_items)
        self._set_index_controls_enabled(count > 0)
        if count:
            self._status.setText(
                f"Found {count} linked page(s). Use Filter found pages, select what you want, then Scan Selected Pages."
            )
        else:
            self._status.setText("Found 0 linked pages. Try a broader index page or use Scan Current Page for this page.")

    def set_status(self, msg: str) -> None:
        self._status.setText(msg)

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
            self._find_index_links_btn,
            self._scan_selected_pages_btn,
            self._scan_manual_links_btn,
            self._download_btn,
        ):
            button.setObjectName("webSourcesPrimaryAction")
        self._index_links.setObjectName("webSourcesIndexList")
        self._manual_links.setObjectName("webSourcesManualList")
        self._results.setObjectName("webSourcesResultsList")

    def _build_ui(self) -> None:
        self.setObjectName("webSourcesCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(7)

        outer.addWidget(self._build_source_section())
        outer.addWidget(self._build_pages_section())
        outer.addWidget(self._build_results_section(), 1)
        outer.addLayout(self._build_download_footer())

        self._status.setObjectName("shellHint")
        outer.addWidget(self._status)

        self._website.currentIndexChanged.connect(lambda _=None: self._on_website_changed())
        self._saved_page.currentIndexChanged.connect(lambda _=None: self._select_saved_page())
        self._website.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._website.customContextMenuRequested.connect(self._show_website_context_menu)
        self._area.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._area.customContextMenuRequested.connect(self._show_area_context_menu)
        self._area.currentIndexChanged.connect(lambda _=None: self._sync_saved_page_from_selection())

    def _build_source_section(self) -> QFrame:
        section, body = self._section_card(
            "1. Choose Saved Page",
            "Pick any saved page, then scan it directly.",
        )

        picker_row = QHBoxLayout()
        picker_row.setSpacing(6)

        saved_box = self._labeled_control("Saved page", self._saved_page)
        picker_row.addLayout(saved_box, 1)

        self._scan_btn.clicked.connect(self._emit_scan)
        picker_row.addWidget(self._scan_btn)

        self._diagnose_btn.clicked.connect(self._emit_network_diagnostics)
        self._configure_more_button(
            self._source_more_btn,
            [
                ("Network Check", self._emit_network_diagnostics),
                ("Remove Saved Page", self._remove_selected_area),
                ("Remove Website", self._remove_selected_website),
            ],
        )
        picker_row.addWidget(self._source_more_btn)

        body.addLayout(picker_row)

        self._selected_page_hint.setObjectName("shellHint")
        body.addWidget(self._selected_page_hint)

        custom = QHBoxLayout()
        custom.setSpacing(6)
        self._custom_url.setPlaceholderText("Paste direct page or index URL, e.g. https://example.com/sprites")
        self._custom_url.textChanged.connect(lambda _=None: self._update_selected_page_hint())
        self._add_site_btn.clicked.connect(self._add_custom_website)
        custom.addWidget(QLabel("URL:", self))
        custom.addWidget(self._custom_url, 1)
        self._add_site_btn.setText("Save Page")
        custom.addWidget(self._add_site_btn)
        body.addLayout(custom)

        return section

    def _build_pages_section(self) -> QFrame:
        section, body = self._section_card(
            "2. Pages to Scan",
            "Find category pages from an index, or paste a manual list.",
        )

        index_header = QHBoxLayout()
        index_title = QLabel("Index pages", self)
        index_title.setObjectName("shellTitle")
        index_header.addWidget(index_title)
        index_hint = QLabel("Find page links, filter them, then scan only what you need.", self)
        index_hint.setObjectName("shellHint")
        index_header.addWidget(index_hint, 1)
        self._find_index_links_btn.clicked.connect(self._emit_index_links_scan)
        self._scan_index_all_btn.clicked.connect(self._emit_index_scan_all)
        self._scan_selected_pages_btn.clicked.connect(self._emit_multi_page_scan)
        index_header.addWidget(self._find_index_links_btn)
        index_header.addWidget(self._scan_selected_pages_btn)
        self._configure_more_button(
            self._index_more_btn,
            [
                ("Find + Scan First 100", self._emit_index_scan_all),
            ],
        )
        index_header.addWidget(self._index_more_btn)
        body.addLayout(index_header)

        index_filter = QHBoxLayout()
        self._index_keyword.setPlaceholderText("Filter found pages: gen 1, home, animation...")
        self._index_keyword.textChanged.connect(lambda _=None: self._refresh_index_link_list())
        self._select_index_visible_btn.setText("Select")
        self._select_index_visible_btn.clicked.connect(self._select_visible_index_links)
        self._clear_index_sel_btn.setText("Clear")
        self._clear_index_sel_btn.clicked.connect(self._index_links.clearSelection)
        index_filter.addWidget(self._index_keyword, 1)
        index_filter.addWidget(self._select_index_visible_btn)
        index_filter.addWidget(self._clear_index_sel_btn)
        body.addLayout(index_filter)

        self._index_links.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._index_links.setFixedHeight(68)
        body.addWidget(self._index_links)

        manual_header = QHBoxLayout()
        manual_title = QLabel("Manual page URLs", self)
        manual_title.setObjectName("shellTitle")
        manual_header.addWidget(manual_title)
        manual_hint = QLabel("One URL per line.", self)
        manual_hint.setObjectName("shellHint")
        manual_header.addWidget(manual_hint, 1)
        self._manual_count.setObjectName("shellHint")
        manual_header.addWidget(self._manual_count)
        self._scan_manual_links_btn.clicked.connect(self._emit_manual_page_scan)
        manual_header.addWidget(self._scan_manual_links_btn)
        self._clear_manual_links_btn.setText("Clear")
        self._clear_manual_links_btn.clicked.connect(self._clear_manual_links)
        manual_header.addWidget(self._clear_manual_links_btn)
        body.addLayout(manual_header)

        self._manual_links.setPlaceholderText(
            "https://example.com/sprites/gen-1\nhttps://example.com/sprites/gen-2"
        )
        self._manual_links.setFixedHeight(50)
        self._manual_links.textChanged.connect(self._update_manual_link_count)
        body.addWidget(self._manual_links)

        return section

    def _build_results_section(self) -> QFrame:
        section, body = self._section_card(
            "3. Found Files",
            "Filter scan results, select the files you want, then download them into the workspace.",
        )

        options = QHBoxLayout()
        options.setSpacing(8)
        self._show_likely.setChecked(False)
        self._skip_dupes.setChecked(True)
        self._allow_zip.setChecked(True)
        options.addWidget(self._show_likely)
        options.addWidget(self._skip_dupes)
        options.addWidget(self._allow_zip)
        options.addStretch(1)
        body.addLayout(options)

        filt = QHBoxLayout()
        filt.setSpacing(6)
        self._search.setPlaceholderText("Search filename, URL, source page...")
        self._search.textChanged.connect(lambda _: self._refresh_list())
        for cb in (self._filter_png, self._filter_gif, self._filter_webp, self._filter_jpg, self._filter_zip):
            cb.setChecked(True)
            cb.stateChanged.connect(lambda _=None: self._refresh_list())

        filt.addWidget(QLabel("Filter:", self))
        filt.addWidget(self._filter_png)
        filt.addWidget(self._filter_gif)
        filt.addWidget(self._filter_webp)
        filt.addWidget(self._filter_jpg)
        filt.addWidget(self._filter_zip)
        filt.addSpacing(10)
        filt.addWidget(self._search, 1)

        self._select_all_btn.setText("Select All")
        self._select_all_btn.clicked.connect(self._select_all_visible)
        filt.addWidget(self._select_all_btn)

        self._clear_sel_btn.setText("Clear")
        self._clear_sel_btn.clicked.connect(self._clear_selection)
        filt.addWidget(self._clear_sel_btn)

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

        self._download_btn.clicked.connect(self._emit_download)
        bottom.addWidget(self._download_btn)

        return bottom

    def _section_card(self, title: str, hint: str) -> tuple[QFrame, QVBoxLayout]:
        section = QFrame(self)
        section.setObjectName("webSourcesSectionCard")
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
            self.set_status(f"Scanning custom URL: {normalized[0]}")
            self.scan_requested.emit(payload)
            return

        a = self._area.currentData()
        if not isinstance(a, dict) or not a.get("url"):
            self.set_status("Pick a Website + Area first.")
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "area_url": str(a["url"]),
            "website_id": website_id,
            "area_id": area_id,
            "smart": asdict(self.smart_options()),
        }
        self.set_status("Scanning...")
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
        self.set_status(f"Finding and scanning linked pages: {payload['index_url']}")
        self.index_scan_all_requested.emit(payload)

    def _emit_multi_page_scan(self) -> None:
        if not self._index_link_items:
            self.set_status("Click Find Pages From Index first, then select pages to scan.")
            return

        selected_links = self._selected_index_link_payloads()
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
        self.set_status(f"{message}...")
        self.multi_scan_requested.emit(payload)

    def _emit_network_diagnostics(self) -> None:
        custom_url = self._custom_url.text().strip()
        if custom_url:
            normalized = self._normalize_custom_url(custom_url)
            if normalized is None:
                self.set_status("Invalid URL. Use http(s)://domain/path.")
                return
            payload = {
                "area_url": normalized[0],
                "website_id": None,
                "area_id": None,
            }
            self.set_status(f"Running network diagnostics for custom URL: {normalized[0]}")
            self.network_diagnostics_requested.emit(payload)
            return

        a = self._area.currentData()
        if not isinstance(a, dict) or not a.get("url"):
            self.set_status("Enter a custom URL or pick a Website + Area first.")
            return

        website_id, area_id = self.selected_source_ids()
        payload = {
            "area_url": str(a["url"]),
            "website_id": website_id,
            "area_id": area_id,
        }
        self.set_status(f"Running network diagnostics for area: {str(a['url'])}")
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
            self.set_status(f"Enter a custom URL or pick a Website + Area to {status_action}.")
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

        created_count = 0
        selected_area_id: str | None = None
        for candidate in self._build_area_candidates(normalized_url):
            candidate_url = str(candidate.get("url", "")).strip()
            if not candidate_url:
                continue

            if candidate_url in existing_urls:
                if candidate_url == normalized_url:
                    existing_match = next(
                        (
                            area
                            for area in areas
                            if isinstance(area, dict) and str(area.get("url", "")).strip() == candidate_url
                        ),
                        None,
                    )
                    if isinstance(existing_match, dict):
                        selected_area_id = str(existing_match.get("id", "")).strip() or selected_area_id
                continue

            area_base = str(candidate.get("base", "")).strip() or "area"
            area_id = self._next_unique_id(area_base, existing_area_ids)
            area_label = str(candidate.get("label", "")).strip() or "Area"

            areas.append({"id": area_id, "label": area_label, "url": candidate_url})
            existing_area_ids.add(area_id)
            existing_urls.add(candidate_url)
            created_count += 1

            if candidate_url == normalized_url:
                selected_area_id = area_id

        if selected_area_id is None:
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

        source_id = str(source.get("id", "")).strip()
        self.set_sources(websites=sources, selected_website_id=source_id, selected_area_id=selected_area_id)
        self._custom_url.clear()
        self.registry_changed.emit(self.sources_registry())

        if created_count > 0:
            self.set_status(f"Added custom website with {created_count} area(s): {normalized_url}")
        else:
            self.set_status("Website URL already exists in the list.")

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

    @classmethod
    def _build_area_candidates(cls, normalized_url: str) -> list[dict]:
        parsed = urlparse(normalized_url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        if not netloc:
            return []

        path_parts = [part for part in str(parsed.path or "").split("/") if part]
        candidates: list[dict] = [
            {
                "base": "root",
                "label": "Root",
                "url": f"{scheme}://{netloc}/",
            }
        ]

        for index in range(1, len(path_parts) + 1):
            prefix_parts = path_parts[:index]
            encoded_parts = [quote(part, safe="-._~") for part in prefix_parts]
            area_url = f"{scheme}://{netloc}/{'/'.join(encoded_parts)}"
            label = cls._path_label_from_parts(prefix_parts)
            base_parts = [cls._slugify(part) for part in prefix_parts]
            base = "_".join(part for part in base_parts if part) or f"area_{index}"
            candidates.append(
                {
                    "base": base,
                    "label": label,
                    "url": area_url,
                }
            )

        if parsed.query:
            query_path = parsed.path or "/"
            query_url = f"{scheme}://{netloc}{query_path}?{parsed.query}"
            if path_parts:
                query_label = f"{cls._path_label_from_parts(path_parts)} (Query)"
                query_base_parts = [cls._slugify(part) for part in path_parts]
                query_base = "_".join(part for part in query_base_parts if part) or "root"
            else:
                query_label = "Root (Query)"
                query_base = "root"
            candidates.append(
                {
                    "base": f"{query_base}_query",
                    "label": query_label,
                    "url": query_url,
                }
            )

        deduped: list[dict] = []
        seen_urls: set[str] = set()
        for candidate in candidates:
            url_value = str(candidate.get("url", "")).strip()
            if not url_value or url_value in seen_urls:
                continue
            seen_urls.add(url_value)
            deduped.append(candidate)
        return deduped

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

    def _select_visible_index_links(self) -> None:
        self._index_links.selectAll()

    def _set_index_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._index_keyword,
            self._scan_selected_pages_btn,
            self._select_index_visible_btn,
            self._clear_index_sel_btn,
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











