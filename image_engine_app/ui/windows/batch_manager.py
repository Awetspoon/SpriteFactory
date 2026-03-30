"""Batch Queue Manager dialog shell with run-action signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from image_engine_app.engine.models import BackgroundRemovalMode
from image_engine_app.ui.windows.batch_queue_state import (
    BatchQueueRowState,
    BatchQueueState,
    build_idle_summary,
    build_progress_label,
    build_run_summary,
    format_event_status,
)


@dataclass(frozen=True)
class BatchDialogOptions:
    """UI-selected batch run options."""

    auto_preset: bool
    auto_export: bool
    preview_skip_mode: bool
    export_name_template: str
    avoid_overwrite: bool
    apply_active_edits: bool
    apply_selected_preset: bool
    selected_preset_name: str | None
    background_removal_override: str | None = None
    export_directory: str | None = None
    selected_asset_ids: tuple[str, ...] = field(default_factory=tuple)


class BatchManagerDialog(QDialog):
    """Batch queue UI shell with a launch signal for batch runs."""

    run_requested = Signal(object)
    cancel_run_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Queue Manager")
        self.resize(860, 600)

        self._summary_label = QLabel("", self)
        self._workflow_label = QLabel("", self)
        self._details_label = QLabel("", self)
        self._progress = QProgressBar(self)
        self._progress_label = QLabel("Batch progress: 0%", self)
        self._current_item_label = QLabel("Current item: --", self)
        self._current_stage_label = QLabel("Stage: --", self)
        self._auto_preset_check = QCheckBox("Smart presets by asset type", self)
        self._auto_export_check = QCheckBox("Save files after processing", self)
        self._apply_active_edits_check = QCheckBox("Copy current asset edits", self)
        self._apply_preset_check = QCheckBox("Apply chosen preset", self)
        self._background_combo = QComboBox(self)
        self._batch_preset_combo = QComboBox(self)
        self._export_name_combo = QComboBox(self)
        self._avoid_overwrite_check = QCheckBox("Keep existing files", self)
        self._preview_skip_check = QCheckBox("Fast run (skip extra planning)", self)
        self._export_dir_field = QLineEdit(self)
        self._browse_export_dir_btn = QPushButton("Browse...", self)
        self.queue_list = QListWidget(self)
        self._select_all_btn = QPushButton("Select All", self)
        self._select_failed_btn = QPushButton("Select Failed", self)
        self._clear_selection_btn = QPushButton("Clear Selection", self)
        self._run_btn = QPushButton("Run Selected", self)
        self._cancel_btn = QPushButton("Stop Run", self)

        self._row_item_by_asset_id: dict[str, QListWidgetItem] = {}
        self._queue_state = BatchQueueState()
        self._is_running = False

        self._build_ui()

    def current_options(self) -> BatchDialogOptions:
        """Return current run options from dialog controls."""

        return BatchDialogOptions(
            auto_preset=self._auto_preset_check.isChecked(),
            auto_export=self._auto_export_check.isChecked(),
            preview_skip_mode=self._preview_skip_check.isChecked(),
            export_name_template=str(self._export_name_combo.currentData() or "{stem}"),
            avoid_overwrite=self._avoid_overwrite_check.isChecked(),
            apply_active_edits=self._apply_active_edits_check.isChecked(),
            apply_selected_preset=self._apply_preset_check.isChecked(),
            selected_preset_name=(
                str(self._batch_preset_combo.currentData()).strip()
                if self._batch_preset_combo.currentData()
                else None
            ),
            background_removal_override=(
                str(self._background_combo.currentData()).strip()
                if self._background_combo.currentData()
                else None
            ),
            export_directory=self.export_directory(),
            selected_asset_ids=tuple(self.selected_asset_ids()),
        )

    def export_directory(self) -> str | None:
        """Return selected batch export directory (or None to use app default)."""

        value = self._export_dir_field.text().strip()
        return value or None

    def set_export_directory(self, path: str | Path | None) -> None:
        """Set batch export directory display."""

        value = str(path).strip() if path is not None else ""
        self._export_dir_field.setText(value)
        self._export_dir_field.setToolTip(value or "Use default export folder")

    def set_available_presets(self, preset_names: list[object]) -> None:
        """Set selectable preset list for optional batch-wide preset application."""

        current = self._batch_preset_combo.currentData()
        names: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for raw in preset_names:
            name = str(getattr(raw, "name", raw) or "").strip()
            if (not name) or (name in seen):
                continue
            seen.add(name)
            label = str(getattr(raw, "label", name) or name).strip() or name
            tooltip = str(getattr(raw, "scope_text", "") or "").strip()
            names.append((name, label, tooltip))

        self._batch_preset_combo.blockSignals(True)
        self._batch_preset_combo.clear()
        self._batch_preset_combo.addItem("Choose preset...", None)
        for name, label, tooltip in names:
            self._batch_preset_combo.addItem(label, name)
            item_index = self._batch_preset_combo.count() - 1
            if tooltip:
                self._batch_preset_combo.setItemData(item_index, tooltip, Qt.ItemDataRole.ToolTipRole)

        ordered_names = [name for name, _label, _tooltip in names]
        if current in ordered_names:
            self._batch_preset_combo.setCurrentIndex(ordered_names.index(current) + 1)
        else:
            self._batch_preset_combo.setCurrentIndex(0)
        self._batch_preset_combo.blockSignals(False)
        self._refresh_idle_controls()

    def selected_asset_ids(self) -> list[str]:
        """Return selected asset ids in visible queue order."""

        selected: list[str] = []
        for row in range(self.queue_list.count()):
            item = self.queue_list.item(row)
            if item is None or (not item.isSelected()):
                continue
            asset_id = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(asset_id, str) and asset_id:
                selected.append(asset_id)
        return selected

    def set_queue_assets(self, assets: list[tuple[str, str]]) -> None:
        """Populate queue rows with stable asset-id bindings and default selection."""

        self.queue_list.clear()
        self._row_item_by_asset_id = {}
        for row in self._queue_state.set_assets(assets):
            self._upsert_queue_row(row)

        self.select_all_items()
        self._set_progress(0)
        self._current_item_label.setText("Current item: --")
        self._current_stage_label.setText("Stage: --")
        self._details_label.setText("Latest issue: none")
        self._update_idle_summary()

    def select_all_items(self) -> None:
        """Select every queued item."""

        if self.queue_list.count() <= 0:
            return
        self.queue_list.selectAll()
        self._update_idle_summary()

    def clear_selection(self) -> None:
        """Clear queue selection."""

        self.queue_list.clearSelection()
        self._update_idle_summary()

    def set_running(self, is_running: bool) -> None:
        """Toggle dialog controls for an active batch run."""

        self._is_running = bool(is_running)
        self._cancel_btn.setEnabled(self._is_running)
        self._auto_preset_check.setEnabled(not self._is_running)
        self._auto_export_check.setEnabled(not self._is_running)
        self._preview_skip_check.setEnabled(not self._is_running)
        self._apply_active_edits_check.setEnabled(not self._is_running)
        self._apply_preset_check.setEnabled(not self._is_running)
        self._background_combo.setEnabled(not self._is_running)
        self.queue_list.setEnabled(not self._is_running)
        self._refresh_idle_controls()

    def update_from_report(self, report: object) -> None:
        """Render a BatchRunReport-like object into the list and summary."""

        items = list(getattr(report, "items", []))
        done_count = 0
        issue_text = "Latest issue: none"

        for idx, item in enumerate(items):
            asset_id = str(getattr(item, "asset_id", "") or f"item-{idx + 1:04d}")
            label = self._queue_state.label_for(asset_id) or asset_id
            queue_item = getattr(item, "queue_item", None)
            status_obj = getattr(queue_item, "status", None)
            status = str(getattr(status_obj, "value", str(status_obj)) or "queued")
            if status == "done":
                done_count += 1
            elif issue_text == "Latest issue: none":
                note = getattr(queue_item, "notes", None) or getattr(item, "error", None)
                detail = str(note).strip() if note is not None else ""
                if detail:
                    issue_text = f"Latest issue: {label}: {detail}"

            self._upsert_queue_row(self._queue_state.upsert(asset_id=asset_id, label=label, status=status))

        total = len(items)
        self._queue_state.last_total = total
        percent = int((done_count / total) * 100) if total else 0
        self._set_progress(percent, total=total, processed=done_count)
        self._current_item_label.setText("Current item: complete")
        self._current_stage_label.setText("Stage: complete")
        failed_count = self._to_int(getattr(report, "failed_count", 0), default=0)
        skipped_count = self._to_int(getattr(report, "skipped_count", 0), default=0)
        self._summary_label.setText(
            build_run_summary(processed=done_count, total=total, failed=failed_count, skipped=skipped_count)
        )
        self._details_label.setText(issue_text)
        self._refresh_idle_controls(total=len(self._queue_state.asset_ids), selected=len(self.selected_asset_ids()))

    def update_from_event(self, event: object) -> None:
        """Apply a BatchProgressEvent-like payload to the dialog incrementally."""

        event_type = str(getattr(event, "event_type", ""))
        total_raw = getattr(event, "item_total", self._queue_state.last_total or 0)
        total = max(0, self._to_int(total_raw, default=(self._queue_state.last_total or 0)))
        self._queue_state.last_total = total

        if event_type == "batch_start":
            if self._row_item_by_asset_id:
                for row in self._queue_state.reset_statuses(status="queued"):
                    self._upsert_queue_row(row)
            else:
                self.queue_list.clear()
                self._row_item_by_asset_id = {}
                self._queue_state = BatchQueueState()

            self.set_running(True)
            self._current_item_label.setText("Current item: waiting...")
            self._current_stage_label.setText("Stage: waiting")
            self._details_label.setText("Latest issue: none")
            overall_start = self._to_float(getattr(event, "overall_progress", 0.0), default=0.0)
            self._set_progress(int(max(0.0, min(1.0, overall_start)) * 100), total=total, processed=0)
            self._summary_label.setText(f"Running batch: 0/{total}")
            return

        asset_id = getattr(event, "asset_id", None)
        asset_label = getattr(event, "asset_label", None)
        queue_status = getattr(event, "queue_status", None)
        stage = str(getattr(event, "stage", "") or "")
        queue_progress_raw = getattr(event, "queue_progress", None)
        queue_progress = self._to_float(queue_progress_raw, default=None)

        if isinstance(asset_id, str) and asset_id:
            base_label = str(asset_label or self._queue_state.label_for(asset_id) or asset_id)
            status_text = format_event_status(
                event_type=event_type,
                queue_status=queue_status,
                stage=stage,
                queue_progress=queue_progress_raw,
            )
            self._upsert_queue_row(self._queue_state.upsert(asset_id=asset_id, label=base_label, status=status_text))
            self._current_item_label.setText(f"Current item: {base_label}")

            if stage:
                stage_label = stage.replace("_", " ")
                if queue_progress is not None:
                    self._current_stage_label.setText(f"Stage: {stage_label} ({int(queue_progress * 100)}%)")
                else:
                    self._current_stage_label.setText(f"Stage: {stage_label}")

        overall = self._to_float(getattr(event, "overall_progress", None), default=None)
        processed_raw = getattr(event, "processed_count", None)
        processed = self._to_int(processed_raw, default=0) if processed_raw is not None else None
        if overall is not None:
            overall_pct = int(max(0.0, min(1.0, overall)) * 100)
            self._set_progress(overall_pct, total=total, processed=processed)

        failed_raw = getattr(event, "failed_count", None)
        skipped_raw = getattr(event, "skipped_count", None)
        message = getattr(event, "message", None)
        if processed_raw is not None and failed_raw is not None:
            failed = self._to_int(failed_raw, default=0)
            safe_processed = self._to_int(processed_raw, default=0)
            skipped = self._to_int(skipped_raw, default=0) if skipped_raw is not None else 0
            self._summary_label.setText(
                build_run_summary(processed=safe_processed, total=total, failed=failed, skipped=skipped)
            )
        elif isinstance(message, str) and message:
            self._summary_label.setText(message)

        if event_type == "item_error":
            detail = str(message or "").strip()
            if detail:
                label = str(asset_label or asset_id or "item").strip()
                self._details_label.setText(f"Latest issue: {label}: {detail}")

        if event_type in {"batch_complete", "batch_cancelled"}:
            self.set_running(False)
            if event_type == "batch_complete":
                final_done = total if processed is None else processed
                self._set_progress(100, total=total, processed=final_done)
                self._current_item_label.setText("Current item: complete")
                self._current_stage_label.setText("Stage: complete")
                if not self._details_label.text().strip() or self._details_label.text().strip() == "Latest issue:":
                    self._details_label.setText("Latest issue: none")
            else:
                self._current_item_label.setText("Current item: cancelled")
                self._current_stage_label.setText("Stage: cancelled")
            self._refresh_idle_controls(total=len(self._queue_state.asset_ids), selected=len(self.selected_asset_ids()))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Batch queue: choose the files to process, apply optional batch rules, then export the results.")
        header.setWordWrap(True)
        layout.addWidget(header)

        self._workflow_label.setWordWrap(True)
        self._workflow_label.setStyleSheet("color:#49686d;")
        self._workflow_label.setText(
            "Run order: copy current edits, apply chosen preset, apply background override, run smart presets, process, then export."
        )
        layout.addWidget(self._workflow_label)

        queue_box = QGroupBox("Queue Selection", self)
        queue_layout = QVBoxLayout(queue_box)
        queue_layout.setContentsMargins(10, 12, 10, 10)
        queue_layout.setSpacing(8)

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Selected queue items will be processed.", self))
        self._select_all_btn.clicked.connect(self.select_all_items)
        selection_row.addWidget(self._select_all_btn)
        self._select_failed_btn.clicked.connect(self.select_failed_items)
        selection_row.addWidget(self._select_failed_btn)
        self._clear_selection_btn.clicked.connect(self.clear_selection)
        selection_row.addWidget(self._clear_selection_btn)
        selection_row.addStretch(1)
        queue_layout.addLayout(selection_row)

        self.queue_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.queue_list.setStyleSheet(
            "QListWidget { border:1px solid #b9ced1; background:#ffffff; }"
            "QListWidget::item { padding:2px 4px; }"
            "QListWidget::item:selected { background:#d8ece9; color:#0f3338; }"
            "QListWidget::item:selected:active { background:#b9ced1; color:#0f3338; }"
            "QListWidget::item:focus { outline:none; }"
        )
        queue_layout.addWidget(self.queue_list, 1)
        layout.addWidget(queue_box, 1)

        status_box = QGroupBox("Run Status", self)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(10, 12, 10, 10)
        status_layout.setSpacing(8)

        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(16)
        self._progress.setStyleSheet(
            "QProgressBar { border:1px solid #b9ced1; border-radius:4px; background:#f2f7f7; }"
            "QProgressBar::chunk { background:#2ea38f; border-radius:3px; margin:0px; }"
        )

        self._progress_label.setStyleSheet("color:#37565b;")
        self._progress_label.setMinimumWidth(180)
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        progress_row.addWidget(self._progress, 1)
        progress_row.addWidget(self._progress_label)
        status_layout.addLayout(progress_row)

        self._current_item_label.setStyleSheet("color:#37565b;")
        status_layout.addWidget(self._current_item_label)

        self._current_stage_label.setStyleSheet("color:#37565b;")
        status_layout.addWidget(self._current_stage_label)

        self._summary_label.setStyleSheet("color:#3f5f64;")
        self._summary_label.setText("0 item(s) in batch queue")
        status_layout.addWidget(self._summary_label)

        self._details_label.setWordWrap(True)
        self._details_label.setStyleSheet("color:#7a4f20;")
        self._details_label.setText("Latest issue: none")
        status_layout.addWidget(self._details_label)
        layout.addWidget(status_box)

        rules_row = QHBoxLayout()
        self._auto_preset_check.setChecked(True)
        self._auto_export_check.setChecked(True)
        self._preview_skip_check.setChecked(True)
        self._auto_preset_check.setToolTip("Auto-pick safe batch presets from the asset type, tags, and format.")
        self._auto_export_check.setToolTip("Save processed files to the selected export folder.")
        self._preview_skip_check.setToolTip("Skip extra planning UI steps for a faster queue run.")
        rules_row.addWidget(self._auto_preset_check)
        rules_row.addWidget(self._auto_export_check)
        rules_row.addWidget(self._preview_skip_check)
        rules_row.addStretch(1)

        apply_row = QHBoxLayout()
        self._apply_active_edits_check.setChecked(False)
        self._apply_preset_check.setChecked(False)
        self._apply_active_edits_check.setToolTip("Copy the active asset's edit settings and queued heavy jobs onto the batch clones.")
        self._apply_preset_check.setToolTip("Apply one chosen preset to all compatible selected items before the batch run starts.")
        apply_row.addWidget(self._apply_active_edits_check)
        apply_row.addWidget(self._apply_preset_check)
        apply_row.addWidget(QLabel("Preset:", self))
        self._batch_preset_combo.clear()
        self._batch_preset_combo.addItem("Choose preset...", None)
        self._batch_preset_combo.setMinimumWidth(220)
        self._batch_preset_combo.setToolTip("Only compatible items will receive the chosen preset.")
        apply_row.addWidget(self._batch_preset_combo, 1)
        apply_row.addStretch(1)

        cutout_row = QHBoxLayout()
        cutout_row.addWidget(QLabel("Background override:", self))
        self._background_combo.addItem("Keep each asset setting", None)
        self._background_combo.addItem("Force white cutout", BackgroundRemovalMode.WHITE.value)
        self._background_combo.addItem("Force black cutout", BackgroundRemovalMode.BLACK.value)
        self._background_combo.addItem("Force cutout off", BackgroundRemovalMode.OFF.value)
        self._background_combo.setToolTip(
            "Optional batch-wide override for edge-connected white/black background removal."
        )
        cutout_row.addWidget(self._background_combo, 1)
        cutout_row.addStretch(1)

        rules_box = QGroupBox("Batch Rules", self)
        rules_layout = QVBoxLayout(rules_box)
        rules_layout.setContentsMargins(10, 12, 10, 10)
        rules_layout.setSpacing(8)
        rules_layout.addLayout(rules_row)
        rules_layout.addLayout(apply_row)
        rules_layout.addLayout(cutout_row)

        naming_row = QHBoxLayout()
        naming_row.addWidget(QLabel("File naming:", self))
        self._export_name_combo.clear()
        self._export_name_combo.addItem("Use source name", "{stem}")
        self._export_name_combo.addItem("Prefix 001", "{index:03d}_{stem}")
        self._export_name_combo.addItem("Group + 001", "{group}_{index:03d}_{stem}")
        self._export_name_combo.addItem("Prefix + short id", "{index:03d}_{stem}_{asset_id8}")
        self._export_name_combo.setCurrentIndex(0)
        self._export_name_combo.setToolTip("Choose how exported files should be named.")
        naming_row.addWidget(self._export_name_combo, 1)
        self._avoid_overwrite_check.setChecked(True)
        self._avoid_overwrite_check.setToolTip("Create a unique name instead of replacing an existing file.")
        naming_row.addWidget(self._avoid_overwrite_check)
        naming_row.addStretch(1)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Output folder:", self))
        self._export_dir_field.setReadOnly(True)
        self._export_dir_field.setPlaceholderText("Use main export folder")
        folder_row.addWidget(self._export_dir_field, 1)
        self._browse_export_dir_btn.clicked.connect(self._browse_export_directory)
        folder_row.addWidget(self._browse_export_dir_btn)

        export_box = QGroupBox("Export Output", self)
        export_layout = QVBoxLayout(export_box)
        export_layout.setContentsMargins(10, 12, 10, 10)
        export_layout.setSpacing(8)
        export_layout.addLayout(naming_row)
        export_layout.addLayout(folder_row)

        options_row = QGridLayout()
        options_row.setHorizontalSpacing(10)
        options_row.setVerticalSpacing(0)
        options_row.addWidget(rules_box, 0, 0)
        options_row.addWidget(export_box, 0, 1)
        options_row.setColumnStretch(0, 3)
        options_row.setColumnStretch(1, 2)
        layout.addLayout(options_row)

        self._auto_export_check.toggled.connect(self._on_auto_export_toggled)
        self._apply_preset_check.toggled.connect(self._on_apply_preset_toggled)
        self._batch_preset_combo.currentIndexChanged.connect(self._on_batch_preset_changed)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self._run_btn.clicked.connect(self._emit_run_requested)
        actions.addWidget(self._run_btn)
        self._cancel_btn.clicked.connect(self._emit_cancel_requested)
        self._cancel_btn.setEnabled(False)
        actions.addWidget(self._cancel_btn)
        actions.addWidget(QPushButton("Close", self, clicked=self.close))
        layout.addLayout(actions)

        self._on_auto_export_toggled(self._auto_export_check.isChecked())
        self._update_idle_summary()
        self.set_running(False)

    def _on_auto_export_toggled(self, checked: bool) -> None:
        _ = checked
        self._refresh_idle_controls()

    def _on_apply_preset_toggled(self, checked: bool) -> None:
        _ = checked
        self._refresh_idle_controls()

    def _on_batch_preset_changed(self, _index: int) -> None:
        self._refresh_idle_controls()

    def _on_selection_changed(self) -> None:
        if not self._is_running:
            self._update_idle_summary()

    def _browse_export_directory(self) -> None:
        if self._is_running:
            return
        start_dir = self.export_directory() or ""
        selected = QFileDialog.getExistingDirectory(self, "Select Batch Export Folder", start_dir)
        if not selected:
            return
        self.set_export_directory(selected)

    def _emit_run_requested(self) -> None:
        self.run_requested.emit(self.current_options())

    def _emit_cancel_requested(self) -> None:
        self.cancel_run_requested.emit()

    def select_failed_items(self) -> None:
        """Select only items that failed in the most recent run."""

        failed_ids = self._queue_state.failed_asset_ids()
        if not failed_ids:
            return
        self.queue_list.clearSelection()
        for asset_id in failed_ids:
            row_item = self._row_item_by_asset_id.get(asset_id)
            if row_item is not None:
                row_item.setSelected(True)
        self._update_idle_summary()

    def _upsert_queue_row(self, row: BatchQueueRowState) -> None:
        row_item = self._row_item_by_asset_id.get(row.asset_id)
        text = row.text
        if row_item is None:
            row_item = QListWidgetItem(text)
            row_item.setData(Qt.ItemDataRole.UserRole, row.asset_id)
            self.queue_list.addItem(row_item)
            self._row_item_by_asset_id[row.asset_id] = row_item
            return
        if row_item.text() != text:
            row_item.setText(text)

    def _update_idle_summary(self) -> None:
        total = len(self._queue_state.asset_ids)
        selected = len(self.selected_asset_ids())
        failed = len(self._queue_state.failed_asset_ids())
        skipped = len(self._queue_state.skipped_asset_ids())
        self._summary_label.setText(build_idle_summary(total, selected, failed=failed, skipped=skipped))
        self._refresh_idle_controls(total=total, selected=selected)

    def _refresh_idle_controls(self, *, total: int | None = None, selected: int | None = None) -> None:
        if total is None:
            total = len(self._queue_state.asset_ids)
        if selected is None:
            selected = len(self.selected_asset_ids())

        is_idle = not self._is_running
        has_rows = total > 0
        has_selection = selected > 0
        has_failed = bool(self._queue_state.failed_asset_ids())

        preset_selected = bool(self._batch_preset_combo.currentData())
        preset_ready = (not self._apply_preset_check.isChecked()) or preset_selected

        self._run_btn.setEnabled(is_idle and has_selection and preset_ready)
        self._select_all_btn.setEnabled(is_idle and has_rows)
        self._select_failed_btn.setEnabled(is_idle and has_failed)
        self._clear_selection_btn.setEnabled(is_idle and has_rows)
        self._apply_active_edits_check.setEnabled(is_idle and has_selection)

        allow_export_controls = is_idle and self._auto_export_check.isChecked()
        self._export_name_combo.setEnabled(allow_export_controls)
        self._avoid_overwrite_check.setEnabled(allow_export_controls)
        self._export_dir_field.setEnabled(allow_export_controls)
        self._browse_export_dir_btn.setEnabled(allow_export_controls)

        has_presets = self._batch_preset_combo.count() > 1
        allow_preset_controls = is_idle and has_selection and has_presets
        self._apply_preset_check.setEnabled(allow_preset_controls)
        self._batch_preset_combo.setEnabled(allow_preset_controls and self._apply_preset_check.isChecked())
        self._background_combo.setEnabled(is_idle and has_selection)

    def _set_progress(self, percent: int, *, total: int | None = None, processed: int | None = None) -> None:
        clamped = max(0, min(100, int(percent)))
        self._progress.setValue(clamped)
        self._progress_label.setText(build_progress_label(clamped, total=total, processed=processed))

    @staticmethod
    def _to_float(value: object, *, default: float | None) -> float | None:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _to_int(value: object, *, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

