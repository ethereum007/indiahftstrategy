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
            if dimensions.get("hour") and f"{event.start_ts.hour:02d}" != dimensions["hour"]:
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

    def group_by(self, *dimensions: str) -> dict[tuple[str, ...], LatencySummary]:
        supported = {"stage", "endpoint", "strategy", "symbol", "segment", "hour"}
        if not dimensions or any(name not in supported for name in dimensions):
            raise ValueError("unsupported latency grouping")
        keys = {tuple(self._value(event, name) for name in dimensions) for event in self.events}
        return {key: self.summarize(**dict(zip(dimensions, key))) for key in sorted(keys)}

    @staticmethod
    def _value(event: LatencyEvent, dimension: str) -> str:
        if dimension == "stage":
            return event.stage
        if dimension == "endpoint":
            return event.endpoint
        if dimension == "strategy":
            return event.trace.strategy_id
        if dimension == "hour":
            return f"{event.start_ts.hour:02d}"
        if event.instrument is None:
            return ""
        return event.instrument.identity.symbol if dimension == "symbol" else event.instrument.identity.segment
