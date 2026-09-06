from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None, name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKETABLE_LIMIT = "MARKETABLE_LIMIT"
    IOC = "IOC"


class BrokerOrderStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    exchange: str
    segment: str
    symbol: str
    underlying: str = ""
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: str | None = None


@dataclass(frozen=True, slots=True)
class Instrument:
    identity: InstrumentIdentity
    instrument_token: str
    trading_symbol: str
    lot_size: int
    tick_size: Decimal

    def __post_init__(self) -> None:
        if not self.instrument_token or not self.trading_symbol:
            raise ValueError("instrument token and trading symbol are required")
        if self.lot_size <= 0 or self.tick_size <= 0:
            raise ValueError("lot size and tick size must be positive")


@dataclass(frozen=True, slots=True)
class TraceContext:
    session_id: str
    strategy_id: str = ""
    signal_id: str = ""
    intent_id: str = ""
    client_order_id: str = ""
    broker_order_id: str = ""
    exchange_order_id: str = ""


@dataclass(frozen=True, slots=True)
class EventTimes:
    exchange_ts: datetime | None = None
    provider_ts: datetime | None = None
    receive_ts: datetime | None = None
    normalized_ts: datetime | None = None
    feature_ts: datetime | None = None
    signal_ts: datetime | None = None
    risk_ts: datetime | None = None
    send_ts: datetime | None = None
    ack_ts: datetime | None = None
    fill_ts: datetime | None = None

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _aware(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int | None = None

    def __post_init__(self) -> None:
        if self.price < 0 or self.quantity < 0 or (self.orders is not None and self.orders < 0):
            raise ValueError("depth values cannot be negative")


@dataclass(frozen=True, slots=True)
class Quote:
    instrument: Instrument
    bid: Decimal | None
    ask: Decimal | None
    bid_quantity: int = 0
    ask_quantity: int = 0
    times: EventTimes = field(default_factory=EventTimes)
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class DepthSnapshot:
    instrument: Instrument
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    times: EventTimes
    trace: TraceContext | None = None
    sequence: int | None = None


@dataclass(frozen=True, slots=True)
class TradePrint:
    instrument: Instrument
    price: Decimal
    quantity: int
    times: EventTimes
    trace: TraceContext | None = None


MarketEvent = Quote | DepthSnapshot | TradePrint


@dataclass(frozen=True, slots=True)
class AlphaForecast:
    instrument: Instrument
    direction: int
    expected_return_bps: Decimal
    confidence: Decimal
    expected_volatility: Decimal
    horizon_ms: int
    expected_decay: Decimal
    capacity: int
    reason_codes: tuple[str, ...]
    feature_snapshot_id: str
    model_version: str
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class OrderIntent:
    instrument: Instrument
    side: Side
    quantity: int
    limit_price: Decimal
    order_type: OrderType
    times: EventTimes
    trace: TraceContext
    expected_edge_bps: Decimal = Decimal(0)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason_codes: tuple[str, ...]
    evaluated_limits: Mapping[str, Decimal | int | bool]
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class ValidatedOrder:
    intent: OrderIntent
    decision: RiskDecision

    def __post_init__(self) -> None:
        if not self.decision.approved:
            raise ValueError("validated order requires an approved risk decision")


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    client_order_id: str
    broker_order_id: str
    exchange_order_id: str
    status: BrokerOrderStatus
    instrument: Instrument
    side: Side
    quantity: int
    filled_quantity: int
    limit_price: Decimal
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class OrderAck:
    client_order_id: str
    broker_order_id: str
    accepted: bool
    reason: str
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class OrderUpdate:
    broker_order_id: str
    exchange_order_id: str
    status: BrokerOrderStatus
    filled_quantity: int
    remaining_quantity: int
    reason: str
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class TradeFill:
    trade_id: str
    broker_order_id: str
    instrument: Instrument
    side: Side
    quantity: int
    price: Decimal
    times: EventTimes
    trace: TraceContext


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    instrument: Instrument
    quantity: int
    average_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    receive_ts: datetime


@dataclass(frozen=True, slots=True)
class MarginSnapshot:
    available: Decimal
    used: Decimal
    required: Decimal
    receive_ts: datetime


@dataclass(frozen=True, slots=True)
class BrokerHealth:
    authenticated: bool
    market_data_connected: bool
    order_stream_connected: bool
    latency_ms: float | None
    checked_ts: datetime
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LatencyEvent:
    stage: str
    start_ts: datetime
    end_ts: datetime
    trace: TraceContext
    instrument: Instrument | None = None
    endpoint: str = ""

    @property
    def duration_ms(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds() * 1000.0


class KillSwitchState(StrEnum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    HALTING = "HALTING"
    HALTED = "HALTED"
    RECONCILING = "RECONCILING"
