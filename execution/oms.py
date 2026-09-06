from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class OMSState(StrEnum):
    CREATED = "CREATED"
    RISK_REJECTED = "RISK_REJECTED"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    MODIFY_PENDING = "MODIFY_PENDING"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


ALLOWED = {
    OMSState.CREATED: {OMSState.RISK_REJECTED, OMSState.APPROVED},
    OMSState.APPROVED: {OMSState.QUEUED},
    OMSState.QUEUED: {OMSState.SUBMITTING},
    OMSState.SUBMITTING: {OMSState.SUBMITTED, OMSState.UNKNOWN},
    OMSState.SUBMITTED: {
        OMSState.ACKNOWLEDGED,
        OMSState.OPEN,
        OMSState.PARTIALLY_FILLED,
        OMSState.FILLED,
        OMSState.REJECTED,
        OMSState.UNKNOWN,
    },
    OMSState.ACKNOWLEDGED: {
        OMSState.OPEN,
        OMSState.PARTIALLY_FILLED,
        OMSState.FILLED,
        OMSState.CANCEL_PENDING,
        OMSState.REJECTED,
    },
    OMSState.OPEN: {
        OMSState.PARTIALLY_FILLED,
        OMSState.FILLED,
        OMSState.CANCEL_PENDING,
        OMSState.MODIFY_PENDING,
        OMSState.UNKNOWN,
    },
    OMSState.PARTIALLY_FILLED: {OMSState.FILLED, OMSState.CANCEL_PENDING, OMSState.CANCELLED, OMSState.UNKNOWN},
    OMSState.CANCEL_PENDING: {OMSState.CANCELLED, OMSState.PARTIALLY_FILLED, OMSState.FILLED, OMSState.UNKNOWN},
    OMSState.MODIFY_PENDING: {
        OMSState.OPEN,
        OMSState.PARTIALLY_FILLED,
        OMSState.FILLED,
        OMSState.REJECTED,
        OMSState.UNKNOWN,
    },
    OMSState.UNKNOWN: {OMSState.RECONCILIATION_REQUIRED},
    OMSState.RECONCILIATION_REQUIRED: {OMSState.OPEN, OMSState.FILLED, OMSState.CANCELLED, OMSState.REJECTED},
}


@dataclass(frozen=True, slots=True)
class OMSEvent:
    sequence: int
    client_order_id: str
    state: OMSState
    event_type: str
    ts: str
    payload: dict[str, object]


class OrderJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: OMSEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**asdict(event), "state": event.state.value}, sort_keys=True) + "\n")
            handle.flush()

    def read(self) -> list[OMSEvent]:
        if not self.path.exists():
            return []
        return [
            OMSEvent(**{**row, "state": OMSState(row["state"])})
            for row in map(json.loads, self.path.read_text(encoding="utf-8").splitlines())
        ]


class OMS:
    def __init__(self, journal: OrderJournal) -> None:
        self.journal = journal
        self.states: dict[str, OMSState] = {}
        self.submission_keys: set[str] = set()
        self._sequence = 0
        self.rebuild()

    def rebuild(self) -> None:
        for event in self.journal.read():
            self.states[event.client_order_id] = event.state
            self._sequence = max(self._sequence, event.sequence)
            if event.event_type == "submission_reserved":
                self.submission_keys.add(event.client_order_id)

    def create(self, client_order_id: str) -> OMSEvent:
        if client_order_id in self.states:
            raise ValueError("duplicate client_order_id")
        return self._record(client_order_id, OMSState.CREATED, "created", {})

    def transition(
        self, client_order_id: str, state: OMSState, event_type: str, payload: dict[str, object] | None = None
    ) -> OMSEvent:
        current = self.states[client_order_id]
        if state not in ALLOWED.get(current, set()):
            raise ValueError(f"invalid OMS transition {current}->{state}")
        return self._record(client_order_id, state, event_type, payload or {})

    def reserve_submission(self, client_order_id: str) -> bool:
        if client_order_id in self.submission_keys:
            return False
        self.submission_keys.add(client_order_id)
        self._record(client_order_id, self.states[client_order_id], "submission_reserved", {})
        return True

    def _record(self, oid: str, state: OMSState, event_type: str, payload: dict[str, object]) -> OMSEvent:
        self._sequence += 1
        event = OMSEvent(self._sequence, oid, state, event_type, datetime.now(UTC).isoformat(), payload)
        self.journal.append(event)
        self.states[oid] = state
        return event
