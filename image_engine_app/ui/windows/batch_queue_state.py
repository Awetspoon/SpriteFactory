"""State helpers for the batch queue manager dialog."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BatchQueueRowState:
    """Stable row state for a single batch queue item."""

    asset_id: str
    label: str
    status: str = "queued"

    @property
    def text(self) -> str:
        return format_batch_row_text(self.label, self.status)


@dataclass
class BatchQueueState:
    """In-memory queue row/index state used by the batch manager view."""

    rows_by_id: dict[str, BatchQueueRowState] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    last_total: int = 0

    @property
    def asset_ids(self) -> list[str]:
        return list(self.order)

    def set_assets(self, assets: list[tuple[str, str]]) -> list[BatchQueueRowState]:
        self.rows_by_id = {}
        self.order = []

        seen: set[str] = set()
        for asset_id, label in assets:
            normalized_id = str(asset_id).strip()
            if (not normalized_id) or (normalized_id in seen):
                continue
            seen.add(normalized_id)
            display = str(label).strip() or normalized_id
            row = BatchQueueRowState(asset_id=normalized_id, label=display, status="queued")
            self.rows_by_id[normalized_id] = row
            self.order.append(normalized_id)

        self.last_total = len(self.order)
        return self.rows()

    def rows(self) -> list[BatchQueueRowState]:
        return [self.rows_by_id[asset_id] for asset_id in self.order if asset_id in self.rows_by_id]

    def label_for(self, asset_id: str) -> str | None:
        row = self.rows_by_id.get(asset_id)
        return row.label if row is not None else None

    def upsert(self, *, asset_id: str, label: str, status: str) -> BatchQueueRowState:
        normalized_id = str(asset_id).strip()
        display = str(label).strip() or normalized_id
        next_row = BatchQueueRowState(
            asset_id=normalized_id,
            label=display,
            status=(str(status).strip() or "queued"),
        )
        self.rows_by_id[normalized_id] = next_row
        if normalized_id not in self.order:
            self.order.append(normalized_id)
        return next_row

    def reset_statuses(self, *, status: str = "queued") -> list[BatchQueueRowState]:
        updated: list[BatchQueueRowState] = []
        for asset_id in list(self.order):
            label = self.label_for(asset_id) or asset_id
            updated.append(self.upsert(asset_id=asset_id, label=label, status=status))
        return updated

    def failed_asset_ids(self) -> list[str]:
        return [asset_id for asset_id in self.order if is_failed_status(self.rows_by_id[asset_id].status)]

    def skipped_asset_ids(self) -> list[str]:
        return [asset_id for asset_id in self.order if is_skipped_status(self.rows_by_id[asset_id].status)]


def format_batch_row_text(label: str, status: str) -> str:
    return f"{label} - {status}"


def format_event_status(
    *,
    event_type: str,
    queue_status: object,
    stage: object,
    queue_progress: object,
) -> str:
    status_text = str(queue_status).strip() if isinstance(queue_status, str) and str(queue_status).strip() else "queued"
    if event_type != "item_progress":
        return status_text

    stage_label = str(stage).strip().replace("_", " ")
    if not stage_label:
        return status_text

    progress = _to_float(queue_progress, default=None)
    if progress is None:
        return f"{status_text} ({stage_label})"

    safe_percent = int(max(0.0, min(1.0, progress)) * 100)
    return f"{status_text} ({stage_label} {safe_percent}%)"


def build_idle_summary(total: int, selected: int, *, failed: int = 0, skipped: int = 0) -> str:
    safe_total = max(0, int(total))
    safe_selected = max(0, int(selected))
    summary = f"{safe_total} item(s) in batch queue | selected: {safe_selected}"
    if failed > 0:
        summary = f"{summary} | failed: {max(0, int(failed))}"
    if skipped > 0:
        summary = f"{summary} | skipped: {max(0, int(skipped))}"
    return summary


def build_run_summary(*, processed: int, total: int, failed: int, skipped: int = 0) -> str:
    summary = f"Processed: {max(0, int(processed))}/{max(0, int(total))} | Failed: {max(0, int(failed))}"
    if skipped > 0:
        summary = f"{summary} | Skipped: {max(0, int(skipped))}"
    return summary


def build_progress_label(percent: int, *, total: int | None = None, processed: int | None = None) -> str:
    clamped = max(0, min(100, int(percent)))
    if total is not None and total > 0 and processed is not None:
        safe_processed = max(0, min(int(processed), int(total)))
        return f"Batch progress: {safe_processed}/{int(total)} ({clamped}%)"
    return f"Batch progress: {clamped}%"


def is_failed_status(status: str) -> bool:
    normalized = str(status).strip().lower()
    return ("fail" in normalized) or ("error" in normalized)


def is_skipped_status(status: str) -> bool:
    normalized = str(status).strip().lower()
    return "skip" in normalized


def _to_float(value: object, *, default: float | None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default
