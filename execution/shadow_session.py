from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from execution.shadow import ShadowResult


@dataclass(frozen=True, slots=True)
class ShadowSessionSummary:
    events: int
    approved: int
    rejected: int
    hypothetical_fills: int
    total_pnl: Decimal
    average_slippage_bps: Decimal
    average_markout_bps: Decimal


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"unsupported shadow record value: {type(value).__name__}")


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"), sort_keys=True)


class ShadowSessionRecorder:
    """Hash-chained append-only evidence for a credential-free shadow session."""

    def __init__(self, path: str | Path, session_id: str) -> None:
        if not session_id.strip():
            raise ValueError("session_id is required")
        self.path = Path(path)
        self.session_id = session_id
        try:
            rows = self.read()
            if rows and not self.verify():
                raise ValueError("existing shadow journal failed integrity verification")
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("existing shadow journal failed integrity verification") from exc
        self._sequence = len(rows)
        self._last_hash = str(rows[-1]["event_hash"]) if rows else ""

    def record(self, result: ShadowResult) -> dict[str, Any]:
        rows = self.read()
        if rows and not self.verify():
            raise ValueError("shadow journal changed after initialization")
        self._sequence = len(rows)
        self._last_hash = str(rows[-1]["event_hash"]) if rows else ""
        body = {
            "session_id": self.session_id,
            "sequence": self._sequence + 1,
            "recorded_ts": datetime.now(UTC),
            "previous_hash": self._last_hash,
            "result": asdict(result),
        }
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        envelope = {**body, "event_hash": digest}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(_canonical(envelope) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._sequence += 1
        self._last_hash = digest
        return envelope

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]

    def verify(self) -> bool:
        previous = ""
        for sequence, row in enumerate(self.read(), 1):
            claimed = row.get("event_hash")
            body = {key: value for key, value in row.items() if key != "event_hash"}
            if (
                row.get("session_id") != self.session_id
                or row.get("sequence") != sequence
                or row.get("previous_hash") != previous
                or claimed != hashlib.sha256(_canonical(body).encode()).hexdigest()
            ):
                return False
            previous = str(claimed)
        return True

    def summarize(self) -> ShadowSessionSummary:
        results = [row["result"] for row in self.read()]
        approved = sum(bool(row["decision"]["approved"]) for row in results)
        fills = [row for row in results if int(row["hypothetical_fill_quantity"]) > 0]
        pnl = sum((Decimal(str(row["pnl"])) for row in results), Decimal(0))
        slippage = sum((Decimal(str(row["slippage_bps"])) for row in fills), Decimal(0))
        markout = sum((Decimal(str(row["markout_bps"])) for row in fills), Decimal(0))
        count = Decimal(len(fills))
        return ShadowSessionSummary(
            len(results),
            approved,
            len(results) - approved,
            len(fills),
            pnl,
            slippage / count if fills else Decimal(0),
            markout / count if fills else Decimal(0),
        )
