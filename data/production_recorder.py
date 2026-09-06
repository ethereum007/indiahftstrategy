from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast


def _json(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _json(v) for k, v in asdict(cast(Any, value)).items()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_json(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    return value


class AppendOnlyRecorder:
    def __init__(self, root: str | Path, session_id: str) -> None:
        self.root = Path(root)
        self.session_id = session_id

    def record_raw(
        self, provider_message: bytes | str, metadata: dict[str, Any], *, receive_ts: datetime, monotonic_ns: int
    ) -> Path:
        path = self.root / "raw" / f"session_id={self.session_id}" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": self.session_id,
            "receive_ts": receive_ts.isoformat(),
            "monotonic_ns": monotonic_ns,
            "provider_message": provider_message.hex() if isinstance(provider_message, bytes) else provider_message,
            "metadata": metadata,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")
        return path

    def record_normalized(self, event: Any) -> Path:
        instrument = event.instrument
        times = event.times
        stamp = times.exchange_ts or times.receive_ts
        if stamp is None:
            raise ValueError("normalized event requires exchange_ts or receive_ts")
        ident = instrument.identity
        safe = ident.symbol.replace("/", "_")
        path = (
            self.root
            / "normalized"
            / f"date={stamp.date().isoformat()}"
            / f"exchange={ident.exchange}"
            / f"segment={ident.segment}"
            / f"instrument={safe}"
            / "events.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_json(event), sort_keys=True) + "\n")
        return path


class DataQualityMonitor:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.last_ts: dict[str, datetime] = {}
        self.counts: dict[str, int] = {}

    def inspect(self, event: Any) -> tuple[str, ...]:
        issues = []
        key = event.instrument.instrument_token
        ts = event.times.exchange_ts or event.times.receive_ts
        fingerprint = json.dumps(_json(event), sort_keys=True)
        if fingerprint in self.seen:
            issues.append("duplicate_event")
        self.seen.add(fingerprint)
        if ts and key in self.last_ts and ts < self.last_ts[key]:
            issues.append("timestamp_regression")
        if ts:
            self.last_ts[key] = ts
        if hasattr(event, "bids") and hasattr(event, "asks"):
            if not event.bids or not event.asks:
                issues.append("zero_depth")
            elif event.bids[0].price >= event.asks[0].price:
                issues.append("crossed_book")
            if any(level.price <= 0 for level in (*event.bids, *event.asks)):
                issues.append("invalid_price")
        for issue in issues:
            self.counts[issue] = self.counts.get(issue, 0) + 1
        return tuple(issues)

    def record_condition(self, condition: str, count: int = 1) -> None:
        supported = {
            "stale_period",
            "data_gap",
            "session_violation",
            "reconnect_window",
        }
        if condition not in supported or count < 0:
            raise ValueError("unsupported data-quality condition")
        self.counts[condition] = self.counts.get(condition, 0) + count

    def report(self) -> dict[str, int]:
        names = (
            "duplicate_event",
            "timestamp_regression",
            "stale_period",
            "data_gap",
            "crossed_book",
            "invalid_price",
            "zero_depth",
            "session_violation",
            "reconnect_window",
        )
        return {name: self.counts.get(name, 0) for name in names}
