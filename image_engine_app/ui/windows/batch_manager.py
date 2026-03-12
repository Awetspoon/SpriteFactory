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
        self._progress = QProgressBar(self)
        self._progress_label = QLabel("Batch progress: 0%", self)
        self._current_item_label = QLabel("Current item: --", self)
        self._current_stage_label = QLabel("Stage: --", self)
        self._auto_preset_check = QCheckBox("Auto preset by classification", self)
        self._auto_export_check = QCheckBox("Auto export selected items", self)
        self._apply_active_edits_check = QCheckBox("Apply active asset edits to selected items", self)
        self._apply_preset_check = QCheckBox("Apply preset to selected items", self)
        self._batch_preset_combo = QComboBox(self)
        self._export_name_combo = QComboBox(self)
        self._avoid_overwrite_check = QCheckBox("Avoid overwriting existing files", self)
        self._preview_skip_check = QCheckBox("Preview skip mode", self)
        self._export_dir_field = QLineEdit(self)
        self._browse_export_dir_btn = QPushButton("Browse...", self)
        self.queue_list = QListWidget(self)
        self._select_all_btn = QPushButton("Select All", self)
        self._clear_selection_btn = QPushButton("Clear Selection", self)
        self._run_btn = QPushButton("Run Batch", self)
        self._cancel_btn = QPushButton("Cancel Run", self)

        self._row_label_by_asset_id: dict[str, str] = {}
        self._row_item_by_asset_id: dict[str, QListWidgetItem] = {}
        self._queue_asset_ids: list[str] = []
        self._last_total = 0
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

    def set_available_presets(self, preset_names: list[str]) -> None:
        """Set selectable preset list for optional batch-wide preset application."""

        current = self._batch_preset_combo.currentData()
        names: list[str] = []
        seen: set[str] = set()
        for raw in preset_names:
            name = str(raw or "").strip()
            if (not name) or (name in seen):
                continue
            seen.add(name)
            names.append(name)

        self._batch_preset_combo.blockSignals(True)
        self._batch_preset_combo.clear()
        self._batch_preset_combo.addItem("Choose preset...", None)
        for name in names:
            self._batch_preset_combo.addItem(name, name)

        if current in names:
            self._batch_preset_combo.setCurrentIndex(names.index(current) + 1)
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
        self._row_label_by_asset_id = {}
        self._row_item_by_asset_id = {}
        self._queue_asset_ids = []

        seen: set[str] = set()
        for asset_id, label in assets:
            normalized_id = str(asset_id).strip()
            if (not normalized_id) or (normalized_id in seen):
                continue
            seen.add(normalized_id)
            display = str(label).strip() or normalized_id
            row_item = QListWidgetItem(self._format_row_text(display, "queued"))
            row_item.setData(Qt.ItemDataRole.UserRole, normalized_id)
            self.queue_list.addItem(row_item)
            self._row_label_by_asset_id[normalized_id] = display
            self._row_item_by_asset_id[normalized_id] = row_item
            self._queue_asset_ids.append(normalized_id)

        self._last_total = len(self._queue_asset_ids)
        self.select_all_items()
        self._set_progress(0)
        self._current_item_label.setText("Current item: --")
        self._current_stage_label.setText("Stage: --")
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
        self.queue_list.setEnabled(not self._is_running)
        self._refresh_idle_controls()

    def update_from_report(self, report: object) -> None:
        """Render a BatchRunReport-like object into the list and summary."""

        items = list(getattr(report, "items", []))
        done_count = 0

        for idx, item in enumerate(items):
            asset_id = str(getattr(item, "asset_id", "") or f"item-{idx + 1:04d}")
            queue_item = getattr(item, "queue_item", None)
            status_obj = getattr(queue_item, "status", None)
            status = str(getattr(status_obj, "value", str(status_obj)) or "queued")
            if status == "done":
                done_count += 1

            label = self._row_label_by_asset_id.get(asset_id, asset_id)
            self._upsert_queue_row(asset_id=asset_id, label=label, status=status)

        total = len(items)
        percent = int((done_count / total) * 100) if total else 0
        self._set_progress(percent, total=total, processed=done_count)
        self._current_item_label.setText("Current item: complete")
        self._current_stage_label.setText("Stage: complete")
        failed_count = self._to_int(getattr(report, "failed_count", 0), default=0)
        self._summary_label.setText(f"Processed: {done_count}/{total} | Failed: {failed_count}")

    def update_from_event(self, event: object) -> None:
        """Apply a BatchProgressEvent-like payload to the dialog incrementally."""

        event_type = str(getattr(event, "event_type", ""))
        total_raw = getattr(event, "item_total", self._last_total or 0)
        total = max(0, self._to_int(total_raw, default=(self._last_total or 0)))
        self._last_total = total

        if event_type == "batch_start":
            if self._row_item_by_asset_id:
                for asset_id, row_item in self._row_item_by_asset_id.items():
                    label = self._row_label_by_asset_id.get(asset_id, asset_id)
                    row_item.setText(self._format_row_text(label, "queued"))
            else:
                self.queue_list.clear()
                self._row_label_by_asset_id = {}
                self._row_item_by_asset_id = {}
                self._queue_asset_ids = []

            self.set_running(True)
            self._current_item_label.setText("Current item: waiting...")
            self._current_stage_label.setText("Stage: waiting")
            overall_start = self._to_float(getattr(event, "overall_progress", 0.0), default=0.0)
            self._set_progress(int(max(0.0, min(1.0, overall_start)) * 100), total=total, processed=0)
            self._summary_label.setText(f"Running batch: 0/{total}")
            return

        asset_id = getattr(event, "asset_id", None)
        asset_label = getattr(event, "asset_label", None)
        queue_status = getattr(event, "queue_status", None)
        stage = str(getattr(event, "stage", "") or "")
        queue_progress = self._to_float(getattr(event, "queue_progress", None), default=None)

        if isinstance(asset_id, str) and asset_id:
            base_label = str(asset_label or self._row_label_by_asset_id.get(asset_id) or asset_id)
            self._row_label_by_asset_id[asset_id] = base_label

            status_text = "queued"
            if isinstance(queue_status, str) and queue_status:
                status_text = queue_status
                if event_type == "item_progress" and stage:
                    stage_label = stage.replace("_", " ")
                    if queue_progress is not None:
                        status_text = f"{queue_status} ({stage_label} {int(queue_progress * 100)}%)"
                    else:
                        status_text = f"{queue_status} ({stage_label})"

            self._upsert_queue_row(asset_id=asset_id, label=base_label, status=status_text)
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
        message = getattr(event, "message", None)
        if processed_raw is not None and failed_raw is not None:
            failed = self._to_int(failed_raw, default=0)
            safe_processed = self._to_int(processed_raw, default=0)
            self._summary_label.setText(f"Processed: {safe_processed}/{total} | Failed: {failed}")
        elif isinstance(message, str) and message:
            self._summary_label.setText(message)

        if event_type in {"batch_complete", "batch_cancelled"}:
            self.set_running(False)
            if event_type == "batch_complete":
                final_done = total if processed is None else processed
                self._set_progress(100, total=total, processed=final_done)
                self._current_item_label.setText("Current item: complete")
                self._current_stage_label.setText("Stage: complete")
            else:
                self._current_item_label.setText("Current item: cancelled")
                self._current_stage_label.setText("Stage: cancelled")
            self._refresh_idle_controls(total=len(self._queue_asset_ids), selected=len(self.selected_asset_ids()))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel("Batch editor: select queued assets, monitor progress, and export one-by-one automatically.")
        header.setWordWrap(True)
        layout.addWidget(header)

        selection_row = QHBoxLayout()
        selection_row.addWidget(QLabel("Queue", self))
        self._select_all_btn.clicked.connect(self.select_all_items)
        selection_row.addWidget(self._select_all_btn)
        self._clear_selection_btn.clicked.connect(self.clear_selection)
        selection_row.addWidget(self._clear_selection_btn)
        selection_row.addStretch(1)
        layout.addLayout(selection_row)

        self.queue_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.queue_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.queue_list.setStyleSheet(
            "QListWidget { border:1px solid #b9ced1; background:#ffffff; }"
            "QListWidget::item { padding:2px 4px; }"
            "QListWidget::item:selected { background:#d8ece9; color:#0f3338; }"
            "QListWidget::item:selected:active { background:#b9ced1; color:#0f3338; }"
            "QListWidget::item:focus { outline:none; }"
        )
        layout.addWidget(self.queue_list, 1)

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
        layout.addLayout(progress_row)

        self._current_item_label.setStyleSheet("color:#37565b;")
        layout.addWidget(self._current_item_label)

        self._current_stage_label.setStyleSheet("color:#37565b;")
        layout.addWidget(self._current_stage_label)

        self._summary_label.setStyleSheet("color:#3f5f64;")
        self._summary_label.setText("0 item(s) in batch queue")
        layout.addWidget(self._summary_label)

        rules_row = QHBoxLayout()
        self._auto_preset_check.setChecked(True)
        self._auto_export_check.setChecked(True)
        self._preview_skip_check.setChecked(True)
        rules_row.addWidget(self._auto_preset_check)
        rules_row.addWidget(self._auto_export_check)
        rules_row.addWidget(self._preview_skip_check)
        rules_row.addStretch(1)
        layout.addLayout(rules_row)

        apply_row = QHBoxLayout()
        self._apply_active_edits_check.setChecked(False)
        self._apply_preset_check.setChecked(False)
        apply_row.addWidget(self._apply_active_edits_check)
        apply_row.addWidget(self._apply_preset_check)
        apply_row.addWidget(QLabel("Preset:", self))
        self._batch_preset_combo.clear()
        self._batch_preset_combo.addItem("Choose preset...", None)
        self._batch_preset_combo.setMinimumWidth(220)
        apply_row.addWidget(self._batch_preset_combo, 1)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)

        naming_row = QHBoxLayout()
        naming_row.addWidget(QLabel("Export naming:", self))
        self._export_name_combo.clear()
        self._export_name_combo.addItem("source_name", "{stem}")
        self._export_name_combo.addItem("001_name", "{index:03d}_{stem}")
        self._export_name_combo.addItem("group_001_name", "{group}_{index:03d}_{stem}")
        self._export_name_combo.addItem("001_name_id", "{index:03d}_{stem}_{asset_id8}")
        self._export_name_combo.setCurrentIndex(0)
        naming_row.addWidget(self._export_name_combo, 1)
        self._avoid_overwrite_check.setChecked(True)
        naming_row.addWidget(self._avoid_overwrite_check)
        naming_row.addStretch(1)
        layout.addLayout(naming_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Export folder:", self))
        self._export_dir_field.setReadOnly(True)
        self._export_dir_field.setPlaceholderText("Use current export folder")
        folder_row.addWidget(self._export_dir_field, 1)
        self._browse_export_dir_btn.clicked.connect(self._browse_export_directory)
        folder_row.addWidget(self._browse_export_dir_btn)
        layout.addLayout(folder_row)

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

    def _upsert_queue_row(self, *, asset_id: str, label: str, status: str) -> None:
        row_item = self._row_item_by_asset_id.get(asset_id)
        text = self._format_row_text(label, status)
        if row_item is None:
            row_item = QListWidgetItem(text)
            row_item.setData(Qt.ItemDataRole.UserRole, asset_id)
            self.queue_list.addItem(row_item)
            self._row_item_by_asset_id[asset_id] = row_item
            self._row_label_by_asset_id[asset_id] = label
            self._queue_asset_ids.append(asset_id)
            return
        if row_item.text() != text:
            row_item.setText(text)

    def _update_idle_summary(self) -> None:
        total = len(self._queue_asset_ids)
        selected = len(self.selected_asset_ids())
        self._summary_label.setText(f"{total} item(s) in batch queue | selected: {selected}")
        self._refresh_idle_controls(total=total, selected=selected)

    def _refresh_idle_controls(self, *, total: int | None = None, selected: int | None = None) -> None:
        if total is None:
            total = len(self._queue_asset_ids)
        if selected is None:
            selected = len(self.selected_asset_ids())

        is_idle = not self._is_running
        has_rows = total > 0
        has_selection = selected > 0

        preset_selected = bool(self._batch_preset_combo.currentData())
        preset_ready = (not self._apply_preset_check.isChecked()) or preset_selected

        self._run_btn.setEnabled(is_idle and has_selection and preset_ready)
        self._select_all_btn.setEnabled(is_idle and has_rows)
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

    def _set_progress(self, percent: int, *, total: int | None = None, processed: int | None = None) -> None:
        clamped = max(0, min(100, int(percent)))
        self._progress.setValue(clamped)

        if total is not None and total > 0 and processed is not None:
            safe_processed = max(0, min(int(processed), int(total)))
            self._progress_label.setText(f"Batch progress: {safe_processed}/{int(total)} ({clamped}%)")
            return

        self._progress_label.setText(f"Batch progress: {clamped}%")

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

    @staticmethod
    def _format_row_text(label: str, status: str) -> str:
        return f"{label} - {status}"














