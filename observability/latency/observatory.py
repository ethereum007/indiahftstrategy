from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev

from trading.contracts import LatencyEvent


@dataclass(frozen=True, slots=True)
class LatencySummary:
    count: int
    p50: float
    p90: float
    p95: float
    p99: float
    p999: float
    maximum: float
    jitter: float


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


class LatencyObservatory:
    def __init__(self) -> None:
        self.events: list[LatencyEvent] = []

    def record(self, event: LatencyEvent) -> None:
        if event.duration_ms < 0:
            raise ValueError("latency timestamps regressed")
        self.events.append(event)

    def summarize(self, **dimensions: str) -> LatencySummary:
        values = []
        for event in self.events:
            if dimensions.get("stage") and event.stage != dimensions["stage"]:
                continue
            if dimensions.get("endpoint") and event.endpoint != dimensions["endpoint"]:
                continue
            if dimensions.get("strategy") and event.trace.strategy_id != dimensions["strategy"]:
                continue
            if dimensions.get("symbol") and (
                event.instrument is None or event.instrument.identity.symbol != dimensions["symbol"]
            ):
                continue
            if dimensions.get("segment") and (
                event.instrument is None or event.instrument.identity.segment != dimensions["segment"]
            ):
                continue
            values.append(event.duration_ms)
        return LatencySummary(
            len(values),
            percentile(values, 0.5),
            percentile(values, 0.9),
            percentile(values, 0.95),
            percentile(values, 0.99),
            percentile(values, 0.999),
            max(values, default=0.0),
            pstdev(values) if len(values) > 1 else 0.0,
        )
