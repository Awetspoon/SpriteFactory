"""Undo/redo history, debounced slider grouping, snapshots, and branches (Prompt 15)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from engine.models import HistoryAffectsView, HistoryState, HistoryStep


@dataclass(frozen=True)
class NamedStateSnapshot:
    """Named snapshot of a serialized edit-state subset."""

    name: str
    created_at: datetime
    state_snapshot: dict[str, Any]


@dataclass(frozen=True)
class BranchEditPath:
    """Captured redo branch when a new edit is recorded after undoing."""

    name: str
    created_at: datetime
    base_pointer: int
    abandoned_steps: list[HistoryStep]


class HistoryEngine:
    """Manages history timeline behavior on top of the `HistoryState` model."""

    def __init__(
        self,
        history_state: HistoryState | None = None,
        *,
        debounce_window_ms: int = 250,
    ) -> None:
        self.history_state = deepcopy(history_state) if history_state is not None else HistoryState()
        self.debounce_window = timedelta(milliseconds=debounce_window_ms)
        self.named_snapshots: dict[str, NamedStateSnapshot] = {}
        self.named_branches: dict[str, BranchEditPath] = {}
        self._branch_counter = 0

    def record_apply(
        self,
        *,
        label: str,
        state_snapshot: dict[str, Any],
        affects_view: HistoryAffectsView,
        timestamp: datetime | None = None,
    ) -> HistoryStep:
        """Record a committed apply event as a new history step."""

        return self._append_step(
            label=label,
            state_snapshot=state_snapshot,
            affects_view=affects_view,
            timestamp=timestamp,
        )

    def record_slider_update(
        self,
        *,
        control_key: str,
        state_snapshot: dict[str, Any],
        affects_view: HistoryAffectsView,
        timestamp: datetime | None = None,
    ) -> HistoryStep:
        """
        Record a slider edit and debounce/group rapid changes into a single step.

        Grouping only applies when:
        - pointer is at the latest step (no redo branch active)
        - previous step has the same generated label and affects_view
        - the timestamp is within the debounce window
        """

        ts = timestamp or datetime.now()
        label = f"Adjust {control_key}"

        last = self._current_step()
        if (
            last is not None
            and self.history_state.pointer == len(self.history_state.steps) - 1
            and last.label == label
            and last.affects_view is affects_view
            and ts - last.timestamp <= self.debounce_window
        ):
            last.timestamp = ts
            last.state_snapshot = deepcopy(state_snapshot)
            return deepcopy(last)

        return self._append_step(
            label=label,
            state_snapshot=state_snapshot,
            affects_view=affects_view,
            timestamp=ts,
        )

    def undo(self) -> dict[str, Any] | None:
        """Move pointer backward and return the new current snapshot (or None at start)."""

        if self.history_state.pointer < 0:
            return None
        self.history_state.pointer -= 1
        return self.current_snapshot()

    def redo(self) -> dict[str, Any] | None:
        """Move pointer forward if possible and return the current snapshot."""

        if self.history_state.pointer + 1 >= len(self.history_state.steps):
            return self.current_snapshot()
        self.history_state.pointer += 1
        return self.current_snapshot()

    def current_step(self) -> HistoryStep | None:
        """Return a copy of the current history step."""

        step = self._current_step()
        return deepcopy(step) if step is not None else None

    def current_snapshot(self) -> dict[str, Any] | None:
        """Return a copy of the current serialized state snapshot."""

        step = self._current_step()
        if step is None:
            return None
        return deepcopy(step.state_snapshot)

    def save_named_snapshot(
        self,
        name: str,
        state_snapshot: dict[str, Any],
        *,
        timestamp: datetime | None = None,
    ) -> NamedStateSnapshot:
        """Save/overwrite a named snapshot."""

        snapshot = NamedStateSnapshot(
            name=name,
            created_at=timestamp or datetime.now(),
            state_snapshot=deepcopy(state_snapshot),
        )
        self.named_snapshots[name] = snapshot
        return snapshot

    def get_named_snapshot(self, name: str) -> NamedStateSnapshot | None:
        """Return a named snapshot copy, if present."""

        snapshot = self.named_snapshots.get(name)
        return deepcopy(snapshot) if snapshot is not None else None

    def list_named_snapshots(self) -> list[NamedStateSnapshot]:
        """Return named snapshots sorted by creation time ascending."""

        return sorted((deepcopy(item) for item in self.named_snapshots.values()), key=lambda s: s.created_at)

    def list_named_branches(self) -> list[BranchEditPath]:
        """Return captured branches sorted by creation time ascending."""

        return sorted((deepcopy(item) for item in self.named_branches.values()), key=lambda b: b.created_at)

    def _append_step(
        self,
        *,
        label: str,
        state_snapshot: dict[str, Any],
        affects_view: HistoryAffectsView,
        timestamp: datetime | None,
    ) -> HistoryStep:
        ts = timestamp or datetime.now()
        self._capture_branch_if_needed(created_at=ts)

        step = HistoryStep(
            id=str(uuid4()),
            timestamp=ts,
            label=label,
            state_snapshot=deepcopy(state_snapshot),
            affects_view=affects_view,
        )
        self.history_state.steps.append(step)
        self.history_state.pointer = len(self.history_state.steps) - 1
        return deepcopy(step)

    def _capture_branch_if_needed(self, *, created_at: datetime) -> None:
        pointer = self.history_state.pointer
        if pointer >= len(self.history_state.steps) - 1:
            return

        abandoned = deepcopy(self.history_state.steps[pointer + 1 :])
        if abandoned:
            self._branch_counter += 1
            branch_name = f"branch_{self._branch_counter:03d}"
            self.named_branches[branch_name] = BranchEditPath(
                name=branch_name,
                created_at=created_at,
                base_pointer=pointer,
                abandoned_steps=abandoned,
            )

        self.history_state.steps = self.history_state.steps[: pointer + 1]

    def _current_step(self) -> HistoryStep | None:
        pointer = self.history_state.pointer
        if pointer < 0 or pointer >= len(self.history_state.steps):
            return None
        return self.history_state.steps[pointer]


