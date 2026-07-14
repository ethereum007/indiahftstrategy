from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


MAX_EVENT_COUNT = 100_000
FAULT_MODES = {
    "none",
    "invalid_quote",
    "non_monotonic_timestamp",
}
SYMBOL_RE = re.compile(r"^[A-Z0-9._-]{1,64}$")
TELEMETRY_COLUMNS = (
    "sequence",
    "ts_ns",
    "local_timestamp",
    "source_mode",
    "provider",
    "adapter",
    "transport",
    "market",
    "exchange",
    "session_id",
    "symbol",
    "bid_price",
    "ask_price",
    "bid_qty",
    "ask_qty",
    "mid_price",
    "spread",
    "accepted",
    "breach_code",
)


class MarketDataObservationSimulationError(ValueError):
    """Raised when a bounded simulation contract is invalid."""


@dataclass(frozen=True)
class BoundedMarketDataSimulationConfig:
    event_count: int = 100
    interval_ms: int = 100
    start_offset_seconds: int = 0
    symbol: str = "NIFTY-SIM"
    base_mid_price: float = 25_000.0
    spread: float = 0.05
    quantity: int = 100
    price_step: float = 0.05
    fault_mode: str = "none"
    fault_at_event: int = 0


@dataclass(frozen=True)
class BoundedMarketDataSimulationResult:
    telemetry: pd.DataFrame
    requested_event_count: int
    attempted_event_count: int
    accepted_event_count: int
    completed: bool
    halted: bool
    halt_reason: str
    session_open_ts_ns: int
    session_close_ts_ns: int
    first_attempt_ts_ns: int
    last_attempt_ts_ns: int


def simulate_bounded_market_data_session(
    *,
    config: BoundedMarketDataSimulationConfig,
    provider: str,
    adapter: str,
    transport: str,
    market: str,
    exchange: str,
    session_id: str,
    trading_date: str,
    timezone_name: str,
    open_local: str,
    close_local: str,
    kill_switch_enabled: bool,
) -> BoundedMarketDataSimulationResult:
    _validate_config(config)
    identity = {
        "provider": _required_identity(provider, "provider"),
        "adapter": _required_identity(adapter, "adapter"),
        "transport": _required_identity(transport, "transport"),
        "market": _required_identity(market, "market"),
        "exchange": _required_identity(exchange, "exchange").upper(),
        "session_id": _required_text(session_id, "session_id"),
    }
    symbol = str(config.symbol).strip().upper()
    if kill_switch_enabled is not True:
        raise MarketDataObservationSimulationError(
            "market-data simulation requires an armed kill switch"
        )
    session_open, session_close = _session_window(
        trading_date=trading_date,
        timezone_name=timezone_name,
        open_local=open_local,
        close_local=close_local,
    )
    open_ns = _datetime_ns(session_open)
    close_ns = _datetime_ns(session_close)
    start_ns = open_ns + (config.start_offset_seconds * 1_000_000_000)
    interval_ns = config.interval_ms * 1_000_000
    previous_accepted_ts_ns: int | None = None
    rows: list[dict[str, object]] = []
    halt_reason = ""

    for sequence in range(1, config.event_count + 1):
        ts_ns = start_ns + ((sequence - 1) * interval_ns)
        if (
            config.fault_mode == "non_monotonic_timestamp"
            and sequence == config.fault_at_event
            and previous_accepted_ts_ns is not None
        ):
            ts_ns = previous_accepted_ts_ns
        bid, ask, mid = _quote(config, sequence)
        bid_qty, ask_qty = _depth(config.quantity, sequence)
        if (
            config.fault_mode == "invalid_quote"
            and sequence == config.fault_at_event
        ):
            ask = bid
        breach = _breach_code(
            ts_ns=ts_ns,
            previous_accepted_ts_ns=previous_accepted_ts_ns,
            session_open_ts_ns=open_ns,
            session_close_ts_ns=close_ns,
            bid=bid,
            ask=ask,
            bid_qty=bid_qty,
            ask_qty=ask_qty,
        )
        accepted = not breach
        rows.append(
            {
                "sequence": sequence,
                "ts_ns": ts_ns,
                "local_timestamp": _local_timestamp(ts_ns, timezone_name),
                "source_mode": "deterministic_simulation",
                **identity,
                "symbol": symbol,
                "bid_price": bid,
                "ask_price": ask,
                "bid_qty": bid_qty,
                "ask_qty": ask_qty,
                "mid_price": mid,
                "spread": round(ask - bid, 10),
                "accepted": accepted,
                "breach_code": breach,
            }
        )
        if breach:
            halt_reason = breach
            break
        previous_accepted_ts_ns = ts_ns

    telemetry = pd.DataFrame(rows, columns=TELEMETRY_COLUMNS)
    attempted = len(telemetry)
    accepted = int(telemetry["accepted"].astype(bool).sum()) if attempted else 0
    halted = bool(halt_reason)
    return BoundedMarketDataSimulationResult(
        telemetry=telemetry,
        requested_event_count=config.event_count,
        attempted_event_count=attempted,
        accepted_event_count=accepted,
        completed=bool(not halted and accepted == config.event_count),
        halted=halted,
        halt_reason=halt_reason,
        session_open_ts_ns=open_ns,
        session_close_ts_ns=close_ns,
        first_attempt_ts_ns=(int(telemetry.iloc[0]["ts_ns"]) if attempted else 0),
        last_attempt_ts_ns=(int(telemetry.iloc[-1]["ts_ns"]) if attempted else 0),
    )


def _validate_config(config: BoundedMarketDataSimulationConfig) -> None:
    if isinstance(config.event_count, bool) or not isinstance(config.event_count, int):
        raise MarketDataObservationSimulationError("event_count must be an integer")
    if not 1 <= config.event_count <= MAX_EVENT_COUNT:
        raise MarketDataObservationSimulationError(
            f"event_count must be between 1 and {MAX_EVENT_COUNT}"
        )
    for name, value in {
        "interval_ms": config.interval_ms,
        "start_offset_seconds": config.start_offset_seconds,
        "quantity": config.quantity,
        "fault_at_event": config.fault_at_event,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise MarketDataObservationSimulationError(f"{name} must be an integer")
    if config.interval_ms <= 0:
        raise MarketDataObservationSimulationError("interval_ms must be positive")
    if config.start_offset_seconds < 0:
        raise MarketDataObservationSimulationError(
            "start_offset_seconds must be non-negative"
        )
    if config.quantity <= 0:
        raise MarketDataObservationSimulationError("quantity must be positive")
    if not SYMBOL_RE.fullmatch(str(config.symbol).strip().upper()):
        raise MarketDataObservationSimulationError("symbol is invalid")
    for name, value in {
        "base_mid_price": config.base_mid_price,
        "spread": config.spread,
        "price_step": config.price_step,
    }.items():
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise MarketDataObservationSimulationError(f"{name} must be finite")
    if config.base_mid_price <= 0 or config.spread <= 0:
        raise MarketDataObservationSimulationError(
            "base_mid_price and spread must be positive"
        )
    if config.price_step < 0:
        raise MarketDataObservationSimulationError(
            "price_step must be non-negative"
        )
    if config.fault_mode not in FAULT_MODES:
        raise MarketDataObservationSimulationError("fault_mode is invalid")
    if config.fault_mode == "none" and config.fault_at_event != 0:
        raise MarketDataObservationSimulationError(
            "fault_at_event must be zero when fault_mode is none"
        )
    if config.fault_mode != "none" and not (
        2 <= config.fault_at_event <= config.event_count
    ):
        raise MarketDataObservationSimulationError(
            "fault_at_event must be between 2 and event_count"
        )


def _session_window(
    *,
    trading_date: str,
    timezone_name: str,
    open_local: str,
    close_local: str,
) -> tuple[datetime, datetime]:
    try:
        day = date.fromisoformat(str(trading_date).strip())
        open_time = time.fromisoformat(str(open_local).strip())
        close_time = time.fromisoformat(str(close_local).strip())
        zone = ZoneInfo(str(timezone_name).strip())
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise MarketDataObservationSimulationError(
            "session date, timezone, or local time is invalid"
        ) from exc
    session_open = datetime.combine(day, open_time, tzinfo=zone)
    session_close = datetime.combine(day, close_time, tzinfo=zone)
    if session_close <= session_open:
        raise MarketDataObservationSimulationError(
            "session close must be after session open"
        )
    return session_open, session_close


def _quote(
    config: BoundedMarketDataSimulationConfig,
    sequence: int,
) -> tuple[float, float, float]:
    base = Decimal(str(config.base_mid_price))
    step = Decimal(str(config.price_step))
    half_spread = Decimal(str(config.spread)) / Decimal("2")
    phase = Decimal(((sequence - 1) % 9) - 4)
    mid = base + (phase * step)
    bid = mid - half_spread
    ask = mid + half_spread
    return (
        round(float(bid), 10),
        round(float(ask), 10),
        round(float(mid), 10),
    )


def _depth(base_quantity: int, sequence: int) -> tuple[int, int]:
    cycle = (
        (9, 1),
        (9, 1),
        (11, 9),
        (1, 9),
        (1, 9),
        (9, 11),
        (1, 1),
        (1, 1),
    )
    bid_multiplier, ask_multiplier = cycle[(sequence - 1) % len(cycle)]
    return base_quantity * bid_multiplier, base_quantity * ask_multiplier


def _breach_code(
    *,
    ts_ns: int,
    previous_accepted_ts_ns: int | None,
    session_open_ts_ns: int,
    session_close_ts_ns: int,
    bid: float,
    ask: float,
    bid_qty: int,
    ask_qty: int,
) -> str:
    if ts_ns < session_open_ts_ns or ts_ns >= session_close_ts_ns:
        return "outside_session_window"
    if previous_accepted_ts_ns is not None and ts_ns <= previous_accepted_ts_ns:
        return "non_monotonic_timestamp"
    if not (
        math.isfinite(bid)
        and math.isfinite(ask)
        and bid > 0
        and ask > bid
        and bid_qty > 0
        and ask_qty > 0
    ):
        return "invalid_quote"
    return ""


def _datetime_ns(value: datetime) -> int:
    utc_value = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc_value - epoch
    return (
        (delta.days * 86_400 * 1_000_000_000)
        + (delta.seconds * 1_000_000_000)
        + (delta.microseconds * 1_000)
    )


def _local_timestamp(ts_ns: int, timezone_name: str) -> str:
    seconds, nanoseconds = divmod(ts_ns, 1_000_000_000)
    value = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(
        ZoneInfo(str(timezone_name).strip())
    )
    offset = value.strftime("%z")
    formatted_offset = f"{offset[:3]}:{offset[3:]}"
    return (
        f"{value.strftime('%Y-%m-%dT%H:%M:%S')}."
        f"{nanoseconds:09d}{formatted_offset}"
    )


def _required_identity(value: object, name: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        raise MarketDataObservationSimulationError(f"{name} is required")
    return normalized


def _required_text(value: object, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise MarketDataObservationSimulationError(f"{name} is required")
    return normalized
