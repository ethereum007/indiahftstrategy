from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.hft_backtest import OrderType
from engine.multi_engine import (
    IOCOrderIntent,
    MultiInstrumentEngine,
    MultiInstrumentStrategy,
    RoutedFill,
)


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
    "signal_source_causality_enabled",
    "signal_source_books_checked",
    "signal_source_books_ready",
    "signal_source_max_lag_ns",
    "edge_revalidation_enabled",
    "edge_revalidation_checked",
    "edge_revalidation_qty",
    "signal_net_edge",
    "decision_call_side",
    "decision_call_price",
    "decision_put_side",
    "decision_put_price",
    "decision_future_side",
    "decision_future_price",
    "decision_contract_multiplier",
    "decision_edge_per_unit",
    "decision_gross_edge",
    "decision_call_cost",
    "decision_put_cost",
    "decision_future_cost",
    "decision_total_cost",
    "decision_net_edge",
    "decision_min_net_edge",
    "ioc_batch_preflight_enabled",
    "ioc_batch_preflight_attempted",
    "ioc_batch_preflight_passed",
    "ioc_batch_preflight_reason",
    "ioc_batch_preflight_instrument_id",
    "ioc_batch_preflight_projected_min",
    "ioc_batch_preflight_projected_max",
    "ioc_batch_preflight_limit",
    "ioc_batch_preflight_conflicting_oid",
    "ioc_batch_preflight_visible_capacity_checked",
    "ioc_batch_preflight_min_visible_fill_ratio",
    "ioc_batch_preflight_limiting_instrument_id",
    "ioc_batch_preflight_requested_qty",
    "ioc_batch_preflight_available_qty",
    "ioc_batch_preflight_touch_price",
    "ioc_batch_preflight_limit_price",
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
    leg_instrument_ids: dict[str, str]
    leg_sides: dict[str, int]
    leg_limit_prices: dict[str, float]
    contract_multiplier: float
    decision_net_edge: float
    expected_order_count: int = 3
    order_ids: list[int] = field(default_factory=list)
    order_id_by_leg: dict[str, int] = field(default_factory=dict)
    fill_count: int = 0
    filled_qty_by_order: dict[int, int] = field(default_factory=dict)
    fill_value_by_order: dict[int, float] = field(default_factory=dict)
    fill_cost_by_order: dict[int, float] = field(default_factory=dict)
    first_fill_ts_by_order: dict[int, int] = field(default_factory=dict)
    last_fill_ts_by_order: dict[int, int] = field(default_factory=dict)


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
            execution.fill_value_by_order[fill.oid] = (
                execution.fill_value_by_order.get(fill.oid, 0.0)
                + fill.price * fill.qty
            )
            execution.fill_cost_by_order[fill.oid] = (
                execution.fill_cost_by_order.get(fill.oid, 0.0)
                + fill.cost
            )
            execution.first_fill_ts_by_order[fill.oid] = min(
                execution.first_fill_ts_by_order.get(
                    fill.oid,
                    fill.ts_ns,
                ),
                fill.ts_ns,
            )
            execution.last_fill_ts_by_order[fill.oid] = max(
                execution.last_fill_ts_by_order.get(
                    fill.oid,
                    fill.ts_ns,
                ),
                fill.ts_ns,
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
            leg_fills = {
                leg: _execution_leg_fill(execution, leg)
                for leg in ("call", "put", "future")
            }
            realized_edge_evaluable = (
                routing_complete and fills_complete
            )
            realized_edge_per_unit = None
            realized_gross_edge = None
            realized_total_cost = None
            realized_net_edge = None
            realized_vs_decision_net_edge = None
            if realized_edge_evaluable:
                call_price = float(leg_fills["call"]["fill_vwap"])
                put_price = float(leg_fills["put"]["fill_vwap"])
                future_price = float(
                    leg_fills["future"]["fill_vwap"]
                )
                if (
                    execution.direction
                    == "buy_synthetic_sell_future"
                ):
                    realized_edge_per_unit = (
                        future_price
                        - (
                            call_price
                            - put_price
                            + execution.strike
                        )
                    )
                else:
                    realized_edge_per_unit = (
                        call_price
                        - put_price
                        + execution.strike
                        - future_price
                    )
                realized_gross_edge = (
                    realized_edge_per_unit
                    * execution.requested_qty
                    * execution.contract_multiplier
                )
                realized_total_cost = sum(
                    float(leg_fills[leg]["fill_cost"])
                    for leg in ("call", "put", "future")
                )
                realized_net_edge = (
                    realized_gross_edge - realized_total_cost
                )
                realized_vs_decision_net_edge = (
                    realized_net_edge - execution.decision_net_edge
                )
            observed_first_fill_timestamps = [
                int(evidence["first_fill_ts_ns"])
                for evidence in leg_fills.values()
                if evidence["first_fill_ts_ns"] is not None
            ]
            observed_last_fill_timestamps = [
                int(evidence["last_fill_ts_ns"])
                for evidence in leg_fills.values()
                if evidence["last_fill_ts_ns"] is not None
            ]
            first_fill_ts_ns = (
                min(observed_first_fill_timestamps)
                if observed_first_fill_timestamps
                else None
            )
            last_fill_ts_ns = (
                max(observed_last_fill_timestamps)
                if observed_last_fill_timestamps
                else None
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
                    "realized_edge_evidence_enabled": True,
                    **{
                        f"{leg}_{key}": value
                        for leg, evidence in leg_fills.items()
                        for key, value in evidence.items()
                    },
                    "contract_multiplier": (
                        execution.contract_multiplier
                    ),
                    "decision_net_edge": execution.decision_net_edge,
                    "realized_edge_evaluable": (
                        realized_edge_evaluable
                    ),
                    "realized_edge_per_unit": (
                        realized_edge_per_unit
                    ),
                    "realized_gross_edge": realized_gross_edge,
                    "realized_total_cost": realized_total_cost,
                    "realized_net_edge": realized_net_edge,
                    "realized_vs_decision_net_edge": (
                        realized_vs_decision_net_edge
                    ),
                    "realized_edge_positive": (
                        bool(
                            realized_edge_evaluable
                            and realized_net_edge is not None
                            and realized_net_edge > 0.0
                        )
                    ),
                    "first_fill_ts_ns": first_fill_ts_ns,
                    "last_fill_ts_ns": last_fill_ts_ns,
                    "fill_span_ns": (
                        last_fill_ts_ns - first_fill_ts_ns
                        if (
                            first_fill_ts_ns is not None
                            and last_fill_ts_ns is not None
                        )
                        else None
                    ),
                }
            )
        frame = pd.DataFrame(rows)
        nullable_integer_columns = [
            "signal_index",
            "signal_ts_ns",
            "decision_ts_ns",
            "signal_age_ns",
            "requested_qty",
            "expected_order_count",
            "order_count",
            "route_rejection_count",
            "fill_count",
            "filled_leg_count",
            "fully_filled_leg_count",
            "unfilled_leg_count",
            "call_order_id",
            "call_filled_qty",
            "call_first_fill_ts_ns",
            "call_last_fill_ts_ns",
            "put_order_id",
            "put_filled_qty",
            "put_first_fill_ts_ns",
            "put_last_fill_ts_ns",
            "future_order_id",
            "future_filled_qty",
            "future_first_fill_ts_ns",
            "future_last_fill_ts_ns",
            "first_fill_ts_ns",
            "last_fill_ts_ns",
            "fill_span_ns",
        ]
        for column in nullable_integer_columns:
            if column in frame.columns:
                frame[column] = frame[column].astype("Int64")
        return frame

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
        signal_source_lags = {
            leg: max(int(signal["ts"]) - book_timestamps[leg], 0)
            for leg in ("call", "put")
        }
        guard["signal_source_books_checked"] = True
        guard["signal_source_max_lag_ns"] = max(
            signal_source_lags.values()
        )
        pending_signal_source_legs = [
            leg
            for leg, lag in signal_source_lags.items()
            if lag > 0
        ]
        guard["signal_source_books_ready"] = (
            not pending_signal_source_legs
        )
        if pending_signal_source_legs:
            guard["guard_reason"] = "signal_source_books_pending"
            guard["affected_legs"] = ",".join(
                pending_signal_source_legs
            )
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

        edge_evidence = _decision_edge_evidence(
            engine,
            direction=direction,
            strike=strike,
            qty=qty,
            call_id=call_id,
            put_id=put_id,
            future_id=future_id,
            legs=legs,
        )
        guard.update(edge_evidence)
        if float(edge_evidence["decision_net_edge"]) <= 0.0:
            guard["guard_reason"] = "execution_edge_below_threshold"
            guard["affected_legs"] = "call,put,future"
            self.execution_guard_decisions.append(guard)
            return False

        preflight = engine.preflight_ioc_batch(
            [
                IOCOrderIntent(
                    instrument_id=leg_instrument_id,
                    side=side,
                    qty=qty,
                    price=price,
                )
                for leg_instrument_id, side, price in legs
            ]
        )
        guard["ioc_batch_preflight_attempted"] = True
        guard["ioc_batch_preflight_passed"] = preflight.passed
        guard["ioc_batch_preflight_reason"] = preflight.reason
        guard["ioc_batch_preflight_instrument_id"] = (
            preflight.instrument_id
        )
        guard["ioc_batch_preflight_projected_min"] = (
            None
            if pd.isna(preflight.projected_min)
            else preflight.projected_min
        )
        guard["ioc_batch_preflight_projected_max"] = (
            None
            if pd.isna(preflight.projected_max)
            else preflight.projected_max
        )
        guard["ioc_batch_preflight_limit"] = (
            None
            if pd.isna(preflight.limit)
            else preflight.limit
        )
        guard["ioc_batch_preflight_conflicting_oid"] = (
            preflight.conflicting_oid
        )
        guard["ioc_batch_preflight_visible_capacity_checked"] = (
            preflight.visible_capacity_checked
        )
        guard["ioc_batch_preflight_min_visible_fill_ratio"] = (
            None
            if pd.isna(preflight.min_visible_fill_ratio)
            else preflight.min_visible_fill_ratio
        )
        guard["ioc_batch_preflight_limiting_instrument_id"] = (
            preflight.limiting_instrument_id
        )
        guard["ioc_batch_preflight_requested_qty"] = (
            preflight.requested_qty
        )
        guard["ioc_batch_preflight_available_qty"] = (
            None
            if pd.isna(preflight.available_qty)
            else preflight.available_qty
        )
        guard["ioc_batch_preflight_touch_price"] = (
            None
            if pd.isna(preflight.touch_price)
            else preflight.touch_price
        )
        guard["ioc_batch_preflight_limit_price"] = (
            None
            if pd.isna(preflight.limit_price)
            else preflight.limit_price
        )
        if not preflight.passed:
            guard["guard_reason"] = "ioc_batch_preflight_rejected"
            instrument_to_leg = {
                call_id: "call",
                put_id: "put",
                future_id: "future",
            }
            guard["affected_legs"] = instrument_to_leg.get(
                preflight.instrument_id,
                "package",
            )
            self.execution_guard_decisions.append(guard)
            return False

        guard["guard_passed"] = True
        guard["guard_reason"] = "ready"
        guard["orders_requested"] = 3
        execution = SignalExecution(
            signal_index=signal_index,
            direction=direction,
            strike=strike,
            signal_ts_ns=int(signal["ts"]),
            ts_ns=now,
            requested_qty=qty,
            leg_instrument_ids={
                "call": call_id,
                "put": put_id,
                "future": future_id,
            },
            leg_sides={
                "call": int(edge_evidence["decision_call_side"]),
                "put": int(edge_evidence["decision_put_side"]),
                "future": int(
                    edge_evidence["decision_future_side"]
                ),
            },
            leg_limit_prices={
                "call": float(
                    edge_evidence["decision_call_price"]
                ),
                "put": float(
                    edge_evidence["decision_put_price"]
                ),
                "future": float(
                    edge_evidence["decision_future_price"]
                ),
            },
            contract_multiplier=float(
                edge_evidence["decision_contract_multiplier"]
            ),
            decision_net_edge=float(
                edge_evidence["decision_net_edge"]
            ),
        )
        self.executions.append(execution)
        execution_idx = len(self.executions) - 1
        for leg, (
            leg_instrument_id,
            side,
            price,
        ) in zip(("call", "put", "future"), legs, strict=True):
            oid = engine.send(leg_instrument_id, side, qty, price, OrderType.IOC)
            if oid is not None:
                execution.order_ids.append(oid)
                execution.order_id_by_leg[leg] = oid
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
            "signal_source_causality_enabled": True,
            "signal_source_books_checked": False,
            "signal_source_books_ready": False,
            "signal_source_max_lag_ns": None,
            "edge_revalidation_enabled": True,
            "edge_revalidation_checked": False,
            "edge_revalidation_qty": 0,
            "signal_net_edge": (
                None
                if pd.isna(signal.get("net_edge"))
                else float(signal.get("net_edge"))
            ),
            "decision_call_side": 0,
            "decision_call_price": None,
            "decision_put_side": 0,
            "decision_put_price": None,
            "decision_future_side": 0,
            "decision_future_price": None,
            "decision_contract_multiplier": None,
            "decision_edge_per_unit": None,
            "decision_gross_edge": None,
            "decision_call_cost": None,
            "decision_put_cost": None,
            "decision_future_cost": None,
            "decision_total_cost": None,
            "decision_net_edge": None,
            "decision_min_net_edge": 0.0,
            "ioc_batch_preflight_enabled": True,
            "ioc_batch_preflight_attempted": False,
            "ioc_batch_preflight_passed": False,
            "ioc_batch_preflight_reason": "not_attempted",
            "ioc_batch_preflight_instrument_id": "",
            "ioc_batch_preflight_projected_min": None,
            "ioc_batch_preflight_projected_max": None,
            "ioc_batch_preflight_limit": None,
            "ioc_batch_preflight_conflicting_oid": None,
            "ioc_batch_preflight_visible_capacity_checked": False,
            "ioc_batch_preflight_min_visible_fill_ratio": None,
            "ioc_batch_preflight_limiting_instrument_id": "",
            "ioc_batch_preflight_requested_qty": 0,
            "ioc_batch_preflight_available_qty": None,
            "ioc_batch_preflight_touch_price": None,
            "ioc_batch_preflight_limit_price": None,
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


def _execution_leg_fill(
    execution: SignalExecution,
    leg: str,
) -> dict[str, object]:
    order_id = execution.order_id_by_leg.get(leg)
    filled_qty = (
        execution.filled_qty_by_order.get(order_id, 0)
        if order_id is not None
        else 0
    )
    fill_value = (
        execution.fill_value_by_order.get(order_id, 0.0)
        if order_id is not None
        else 0.0
    )
    return {
        "instrument_id": execution.leg_instrument_ids[leg],
        "order_id": order_id,
        "side": execution.leg_sides[leg],
        "limit_price": execution.leg_limit_prices[leg],
        "filled_qty": int(filled_qty),
        "fill_vwap": (
            float(fill_value / filled_qty)
            if filled_qty > 0
            else None
        ),
        "fill_cost": (
            float(execution.fill_cost_by_order.get(order_id, 0.0))
            if order_id is not None
            else None
        ),
        "first_fill_ts_ns": (
            execution.first_fill_ts_by_order.get(order_id)
            if order_id is not None
            else None
        ),
        "last_fill_ts_ns": (
            execution.last_fill_ts_by_order.get(order_id)
            if order_id is not None
            else None
        ),
    }


def _decision_edge_evidence(
    engine: MultiInstrumentEngine,
    *,
    direction: str,
    strike: float,
    qty: int,
    call_id: str,
    put_id: str,
    future_id: str,
    legs: list[tuple[str, int, float]],
) -> dict[str, object]:
    by_instrument = {
        instrument_id: (side, float(price))
        for instrument_id, side, price in legs
    }
    call_side, call_price = by_instrument[call_id]
    put_side, put_price = by_instrument[put_id]
    future_side, future_price = by_instrument[future_id]
    if direction == "buy_synthetic_sell_future":
        edge_per_unit = (
            future_price - (call_price - put_price + strike)
        )
    else:
        edge_per_unit = (
            call_price - put_price + strike - future_price
        )

    call_cfg = engine.instruments[call_id]
    put_cfg = engine.instruments[put_id]
    future_cfg = engine.instruments[future_id]
    multiplier = float(call_cfg.instrument.multiplier)
    call_cost = call_cfg.costs.cost(
        call_side,
        call_price,
        qty,
        call_cfg.instrument,
    )
    put_cost = put_cfg.costs.cost(
        put_side,
        put_price,
        qty,
        put_cfg.instrument,
    )
    future_cost = future_cfg.costs.cost(
        future_side,
        future_price,
        qty,
        future_cfg.instrument,
    )
    total_cost = call_cost + put_cost + future_cost
    gross_edge = edge_per_unit * qty * multiplier
    return {
        "edge_revalidation_checked": True,
        "edge_revalidation_qty": int(qty),
        "decision_call_side": int(call_side),
        "decision_call_price": call_price,
        "decision_put_side": int(put_side),
        "decision_put_price": put_price,
        "decision_future_side": int(future_side),
        "decision_future_price": future_price,
        "decision_contract_multiplier": multiplier,
        "decision_edge_per_unit": float(edge_per_unit),
        "decision_gross_edge": float(gross_edge),
        "decision_call_cost": float(call_cost),
        "decision_put_cost": float(put_cost),
        "decision_future_cost": float(future_cost),
        "decision_total_cost": float(total_cost),
        "decision_net_edge": float(gross_edge - total_cost),
        "decision_min_net_edge": 0.0,
    }


def _validate_config(config: ParityArbConfig) -> None:
    for name in (
        "max_signal_age_ns",
        "max_leg_book_age_ns",
        "max_leg_book_skew_ns",
    ):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
