"""Web Sources panel (scaffold).

This is a thin UI shell.
- UI emits scan/download requests.
- Controller performs scan/download and calls set_results()/set_status().

Keeping UI dumb makes patches safer.
"""

from __future__ import annotations

from dataclasses import asdict
from urllib.parse import quote, urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.app.web_sources_models import Confidence, ImportTarget, ScanResults, SmartOptions, WebItem


class WebSourcesPanel(QFrame):
    """Main-window tab panel for Website/Area scanning + importing."""

    scan_requested = Signal(object)      # payload dict
    download_requested = Signal(object)  # payload dict
    registry_changed = Signal(object)    # payload list[dict]
    network_diagnostics_requested = Signal(object)  # payload dict

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._website = QComboBox(self)
        self._area = QComboBox(self)
        self._scan_btn = QPushButton("Scan Area", self)
        self._diagnose_btn = QPushButton("Network Check", self)
        self._custom_url = QLineEdit(self)
        self._add_site_btn = QPushButton("Add Website URL", self)

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
        self._preview = QLabel("Select an item to preview its URL.", self)
        self._status = QLabel("", self)

        self._destination_hint = QLabel("Auto destination: Sprite Factory routes downloads into Main / Shiny / Animated / Items.", self)
        self._download_btn = QPushButton("Download Selected", self)

        self._select_all_btn = QToolButton(self)
        self._clear_sel_btn = QToolButton(self)

        self._items: list[WebItem] = []

        self._build_ui()

    # --- Public API for controller ---

    def set_sources(self, *, websites: list[dict], selected_website_id: str | None = None, selected_area_id: str | None = None) -> None:
        """Populate Website + Area dropdowns.

        websites format (dict):
        {"id": str, "name": str, "areas": [{"id": str, "label": str, "url": str}, ...]}
        """
        self._website.blockSignals(True)
        self._area.blockSignals(True)

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

        self._website.blockSignals(False)
        self._area.blockSignals(False)

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

    def _build_ui(self) -> None:
        self.setObjectName("webSourcesCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # Top: source picker
        top = QHBoxLayout()
        top.setSpacing(10)

        picker = QFormLayout()
        picker.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        picker.addRow("Website", self._website)
        picker.addRow("Area", self._area)
        top.addLayout(picker, 1)

        self._scan_btn.clicked.connect(self._emit_scan)
        top.addWidget(self._scan_btn)

        self._diagnose_btn.clicked.connect(self._emit_network_diagnostics)
        top.addWidget(self._diagnose_btn)

        outer.addLayout(top)

        # Add custom website row
        custom = QHBoxLayout()
        custom.setSpacing(8)
        self._custom_url.setPlaceholderText("https://example.com/sprites")
        self._add_site_btn.clicked.connect(self._add_custom_website)
        custom.addWidget(QLabel("Custom Website URL:", self))
        custom.addWidget(self._custom_url, 1)
        custom.addWidget(self._add_site_btn)
        outer.addLayout(custom)

        # Options row
        opt = QHBoxLayout()
        opt.setSpacing(12)
        self._show_likely.setChecked(False)
        self._skip_dupes.setChecked(True)
        self._allow_zip.setChecked(True)
        opt.addWidget(self._show_likely)
        opt.addWidget(self._skip_dupes)
        opt.addWidget(self._allow_zip)
        opt.addStretch(1)
        outer.addLayout(opt)

        # Filters row
        filt = QHBoxLayout()
        self._search.setPlaceholderText("Search filename...")
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

        outer.addLayout(filt)

        # Splitter: results + preview
        split = QSplitter(self)
        split.setOrientation(Qt.Orientation.Horizontal)

        self._results.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._results.itemSelectionChanged.connect(self._update_preview)
        self._results.setObjectName("shellListPanel")
        split.addWidget(self._results)

        self._preview.setWordWrap(True)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._preview.setObjectName("shellInsetCard")
        split.addWidget(self._preview)

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        outer.addWidget(split, 1)

        # Bottom import bar
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self._destination_hint.setObjectName("shellHint")
        bottom.addWidget(self._destination_hint, 1)

        self._download_btn.clicked.connect(self._emit_download)
        bottom.addWidget(self._download_btn)

        outer.addLayout(bottom)

        self._status.setObjectName("shellHint")
        outer.addWidget(self._status)

        # Dropdown dependency
        self._website.currentIndexChanged.connect(lambda _=None: self._rebuild_areas())
        self._website.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._website.customContextMenuRequested.connect(self._show_website_context_menu)
        self._area.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._area.customContextMenuRequested.connect(self._show_area_context_menu)

    def _rebuild_areas(self, selected_area_id: str | None = None) -> None:
        self._area.clear()
        w = self._website.currentData()
        if not isinstance(w, dict):
            return
        for a in (w.get("areas") or []):
            self._area.addItem(str(a.get("label", "Area")), a)

        if selected_area_id:
            for i in range(self._area.count()):
                a = self._area.itemData(i)
                if isinstance(a, dict) and a.get("id") == selected_area_id:
                    self._area.setCurrentIndex(i)
                    break

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
            label = " / ".join(cls._friendly_path_segment(part) for part in prefix_parts)
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
                leaf_label = " / ".join(cls._friendly_path_segment(part) for part in path_parts)
                query_label = f"{leaf_label} (Query)"
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
        raw = (segment or "").strip().replace("-", " ").replace("_", " ")
        words = [word for word in raw.split() if word]
        if not words:
            return "Area"
        return " ".join(word.capitalize() for word in words)

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
        self._refresh_list()
        self._preview.setText("Select an item to preview its URL.")

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
            if allow and ext and ext not in allow:
                continue
            if query and query not in name.lower():
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
            self._preview.setText("Select an item to preview its URL.")
            return
        item = selected[0]
        self._preview.setText(
            f"Name: {item.name}\nType: {item.ext}\nConfidence: {item.confidence.value}\n\nURL:\n{item.url}"
        )

    def _select_all_visible(self) -> None:
        self._results.selectAll()

    def _clear_selection(self) -> None:
        self._results.clearSelection()











