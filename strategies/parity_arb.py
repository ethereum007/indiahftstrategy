from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.hft_backtest import OrderType
from engine.multi_engine import MultiInstrumentEngine, MultiInstrumentStrategy, RoutedFill


PARITY_EXECUTION_GUARD_COLUMNS = [
    "signal_index",
    "direction",
    "strike",
    "signal_ts_ns",
    "decision_ts_ns",
    "signal_age_ns",
    "trigger_instrument_id",
    "call_instrument_id",
    "put_instrument_id",
    "future_instrument_id",
    "call_book_ts_ns",
    "put_book_ts_ns",
    "future_book_ts_ns",
    "call_book_age_ns",
    "put_book_age_ns",
    "future_book_age_ns",
    "max_observed_book_age_ns",
    "leg_book_skew_ns",
    "max_leg_book_age_ns",
    "max_leg_book_skew_ns",
    "guard_passed",
    "guard_reason",
    "affected_legs",
    "orders_requested",
    "orders_accepted",
    "routing_complete",
    "routing_status",
]


@dataclass(frozen=True)
class ParityLegMap:
    future_id: str
    call_by_strike: dict[float, str]
    put_by_strike: dict[float, str]


@dataclass(frozen=True)
class ParityArbConfig:
    max_signal_age_ns: int = 1_000_000
    max_leg_book_age_ns: int = 1_000_000
    max_leg_book_skew_ns: int = 1_000_000
    max_qty: int | None = None


@dataclass
class SignalExecution:
    signal_index: int
    direction: str
    strike: float
    signal_ts_ns: int
    ts_ns: int
    requested_qty: int
    expected_order_count: int = 3
    order_ids: list[int] = field(default_factory=list)
    fill_count: int = 0
    filled_qty_by_order: dict[int, int] = field(default_factory=dict)


class ParityArbTakerStrategy(MultiInstrumentStrategy):
    """Replay scanner parity signals as three IOC legs.

    Supported directions:
    - buy_synthetic_sell_future: buy call, sell put, sell future
    - sell_synthetic_buy_future: sell call, buy put, buy future
    """

    def __init__(
        self,
        signals: pd.DataFrame,
        leg_map: ParityLegMap,
        config: ParityArbConfig | None = None,
    ):
        self.signals = signals.sort_values("ts").reset_index(drop=True)
        self.leg_map = leg_map
        self.config = config or ParityArbConfig()
        _validate_config(self.config)
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self.next_signal = 0
        self.executions: list[SignalExecution] = []
        self.order_to_execution: dict[int, int] = {}
        self.execution_guard_decisions: list[dict[str, object]] = []

    def on_start(self, engine: MultiInstrumentEngine):
        self._reset_run_state()

    def on_tick(self, engine: MultiInstrumentEngine, instrument_id: str, tick: dict):
        now = int(tick["ts"])
        while self.next_signal < len(self.signals):
            signal = self.signals.iloc[self.next_signal]
            signal_ts = int(signal["ts"])
            if signal_ts > now:
                break
            if now - signal_ts > self.config.max_signal_age_ns:
                self.execution_guard_decisions.append(
                    self._guard_row(
                        signal_index=self.next_signal,
                        signal=signal,
                        now=now,
                        trigger_instrument_id=instrument_id,
                        guard_reason="signal_age_exceeded",
                    )
                )
                self.next_signal += 1
                continue
            routed = self._try_execute(
                engine,
                self.next_signal,
                signal,
                now,
                trigger_instrument_id=instrument_id,
            )
            if not routed:
                break
            self.next_signal += 1

    def on_fill(self, engine: MultiInstrumentEngine, fill: RoutedFill):
        execution_idx = self.order_to_execution.get(fill.oid)
        if execution_idx is not None:
            execution = self.executions[execution_idx]
            execution.fill_count += 1
            execution.filled_qty_by_order[fill.oid] = (
                execution.filled_qty_by_order.get(fill.oid, 0) + fill.qty
            )

    def on_end(self, engine: MultiInstrumentEngine):
        pass

    def legging_report(self) -> pd.DataFrame:
        rows = []
        for execution in self.executions:
            accepted_orders = len(execution.order_ids)
            filled_legs = sum(
                execution.filled_qty_by_order.get(oid, 0) > 0
                for oid in execution.order_ids
            )
            fully_filled_legs = sum(
                execution.filled_qty_by_order.get(oid, 0)
                >= execution.requested_qty
                for oid in execution.order_ids
            )
            routing_complete = (
                accepted_orders == execution.expected_order_count
            )
            fills_complete = (
                fully_filled_legs == execution.expected_order_count
            )
            rows.append(
                {
                    "signal_index": execution.signal_index,
                    "direction": execution.direction,
                    "strike": execution.strike,
                    "signal_ts_ns": execution.signal_ts_ns,
                    "decision_ts_ns": execution.ts_ns,
                    "signal_age_ns": (
                        execution.ts_ns - execution.signal_ts_ns
                    ),
                    "requested_qty": execution.requested_qty,
                    "expected_order_count": execution.expected_order_count,
                    "order_count": accepted_orders,
                    "route_rejection_count": (
                        execution.expected_order_count - accepted_orders
                    ),
                    "fill_count": execution.fill_count,
                    "filled_leg_count": filled_legs,
                    "fully_filled_leg_count": fully_filled_legs,
                    "unfilled_leg_count": (
                        execution.expected_order_count - fully_filled_legs
                    ),
                    "routing_complete": routing_complete,
                    "fills_complete": fills_complete,
                    "partial": not (
                        routing_complete and fills_complete
                    ),
                }
            )
        return pd.DataFrame(rows)

    def execution_guard_report(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.execution_guard_decisions,
            columns=PARITY_EXECUTION_GUARD_COLUMNS,
        )

    def _try_execute(
        self,
        engine: MultiInstrumentEngine,
        signal_index: int,
        signal: pd.Series,
        now: int,
        *,
        trigger_instrument_id: str,
    ) -> bool:
        strike = float(signal["strike"])
        qty = int(signal["qty"])
        if self.config.max_qty is not None:
            qty = min(qty, self.config.max_qty)
        direction = str(signal["direction"])
        guard = self._guard_row(
            signal_index=signal_index,
            signal=signal,
            now=now,
            trigger_instrument_id=trigger_instrument_id,
        )
        if qty <= 0:
            guard["guard_reason"] = "nonpositive_quantity"
            self.execution_guard_decisions.append(guard)
            return True
        if direction not in {
            "buy_synthetic_sell_future",
            "sell_synthetic_buy_future",
        }:
            guard["guard_reason"] = "unsupported_direction"
            self.execution_guard_decisions.append(guard)
            return True
        call_id = self.leg_map.call_by_strike.get(strike)
        put_id = self.leg_map.put_by_strike.get(strike)
        future_id = self.leg_map.future_id
        guard["call_instrument_id"] = call_id or ""
        guard["put_instrument_id"] = put_id or ""
        guard["future_instrument_id"] = future_id or ""
        missing_mappings = [
            leg
            for leg, instrument_id in [
                ("call", call_id),
                ("put", put_id),
                ("future", future_id),
            ]
            if not instrument_id
        ]
        if missing_mappings:
            guard["guard_reason"] = "missing_leg_mapping"
            guard["affected_legs"] = ",".join(missing_mappings)
            self.execution_guard_decisions.append(guard)
            return False
        unknown_instruments = [
            leg
            for leg, instrument_id in [
                ("call", call_id),
                ("put", put_id),
                ("future", future_id),
            ]
            if instrument_id not in engine.instruments
        ]
        if unknown_instruments:
            guard["guard_reason"] = "unknown_leg_instrument"
            guard["affected_legs"] = ",".join(unknown_instruments)
            self.execution_guard_decisions.append(guard)
            return False
        call = engine.last_tick(call_id)
        put = engine.last_tick(put_id)
        future = engine.last_tick(future_id)
        books = {
            "call": call,
            "put": put,
            "future": future,
        }
        missing_books = [
            leg for leg, tick in books.items() if tick is None
        ]
        if missing_books:
            guard["guard_reason"] = "missing_leg_book"
            guard["affected_legs"] = ",".join(missing_books)
            self.execution_guard_decisions.append(guard)
            return False

        book_timestamps = {
            leg: _source_book_ts(tick)
            for leg, tick in books.items()
        }
        book_ages = {
            leg: now - ts
            for leg, ts in book_timestamps.items()
        }
        for leg in ("call", "put", "future"):
            guard[f"{leg}_book_ts_ns"] = book_timestamps[leg]
            guard[f"{leg}_book_age_ns"] = book_ages[leg]
        guard["max_observed_book_age_ns"] = max(book_ages.values())
        guard["leg_book_skew_ns"] = (
            max(book_timestamps.values())
            - min(book_timestamps.values())
        )
        negative_age_legs = [
            leg for leg, age in book_ages.items() if age < 0
        ]
        if negative_age_legs:
            guard["guard_reason"] = "negative_leg_book_age"
            guard["affected_legs"] = ",".join(negative_age_legs)
            self.execution_guard_decisions.append(guard)
            return False
        stale_legs = [
            leg
            for leg, age in book_ages.items()
            if age > self.config.max_leg_book_age_ns
        ]
        if stale_legs:
            guard["guard_reason"] = "stale_leg_book"
            guard["affected_legs"] = ",".join(stale_legs)
            self.execution_guard_decisions.append(guard)
            return False
        if (
            int(guard["leg_book_skew_ns"])
            > self.config.max_leg_book_skew_ns
        ):
            guard["guard_reason"] = "leg_book_skew_exceeded"
            guard["affected_legs"] = "call,put,future"
            self.execution_guard_decisions.append(guard)
            return False

        guard["guard_passed"] = True
        guard["guard_reason"] = "ready"
        guard["orders_requested"] = 3
        if direction == "buy_synthetic_sell_future":
            legs = [
                (call_id, +1, call["ask"]),
                (put_id, -1, put["bid"]),
                (future_id, -1, future["bid"]),
            ]
        else:
            legs = [
                (call_id, -1, call["bid"]),
                (put_id, +1, put["ask"]),
                (future_id, +1, future["ask"]),
            ]

        execution = SignalExecution(
            signal_index=signal_index,
            direction=direction,
            strike=strike,
            signal_ts_ns=int(signal["ts"]),
            ts_ns=now,
            requested_qty=qty,
        )
        self.executions.append(execution)
        execution_idx = len(self.executions) - 1
        for leg_instrument_id, side, price in legs:
            oid = engine.send(leg_instrument_id, side, qty, price, OrderType.IOC)
            if oid is not None:
                execution.order_ids.append(oid)
                self.order_to_execution[oid] = execution_idx
        guard["orders_accepted"] = len(execution.order_ids)
        guard["routing_complete"] = len(execution.order_ids) == 3
        guard["routing_status"] = (
            "complete"
            if len(execution.order_ids) == 3
            else "partial"
            if execution.order_ids
            else "rejected"
        )
        self.execution_guard_decisions.append(guard)
        if not execution.order_ids:
            self.executions.pop()
            return False
        return True

    def _guard_row(
        self,
        *,
        signal_index: int,
        signal: pd.Series,
        now: int,
        trigger_instrument_id: str,
        guard_reason: str = "pending",
    ) -> dict[str, object]:
        return {
            "signal_index": int(signal_index),
            "direction": str(signal.get("direction", "")),
            "strike": float(signal.get("strike", float("nan"))),
            "signal_ts_ns": int(signal["ts"]),
            "decision_ts_ns": int(now),
            "signal_age_ns": int(now - int(signal["ts"])),
            "trigger_instrument_id": str(trigger_instrument_id),
            "call_instrument_id": "",
            "put_instrument_id": "",
            "future_instrument_id": str(self.leg_map.future_id or ""),
            "call_book_ts_ns": None,
            "put_book_ts_ns": None,
            "future_book_ts_ns": None,
            "call_book_age_ns": None,
            "put_book_age_ns": None,
            "future_book_age_ns": None,
            "max_observed_book_age_ns": None,
            "leg_book_skew_ns": None,
            "max_leg_book_age_ns": int(
                self.config.max_leg_book_age_ns
            ),
            "max_leg_book_skew_ns": int(
                self.config.max_leg_book_skew_ns
            ),
            "guard_passed": False,
            "guard_reason": guard_reason,
            "affected_legs": "",
            "orders_requested": 0,
            "orders_accepted": 0,
            "routing_complete": False,
            "routing_status": "not_attempted",
        }


def _source_book_ts(tick: dict) -> int:
    return int(tick.get("market_ts", tick["ts"]))


def _validate_config(config: ParityArbConfig) -> None:
    for name in (
        "max_signal_age_ns",
        "max_leg_book_age_ns",
        "max_leg_book_skew_ns",
    ):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
