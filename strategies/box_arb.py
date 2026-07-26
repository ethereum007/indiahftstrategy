from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

import pandas as pd

from engine.hft_backtest import OrderType
from engine.multi_engine import (
    IOCOrderIntent,
    MultiInstrumentEngine,
    MultiInstrumentStrategy,
    RoutedFill,
)


BOX_LEGS = (
    "low_call",
    "low_put",
    "high_call",
    "high_put",
)

BOX_EXECUTION_GUARD_COLUMNS = [
    "signal_index",
    "direction",
    "expiry",
    "low_strike",
    "high_strike",
    "signal_ts_ns",
    "decision_ts_ns",
    "signal_age_ns",
    "trigger_instrument_id",
    "low_call_instrument_id",
    "low_put_instrument_id",
    "high_call_instrument_id",
    "high_put_instrument_id",
    "low_call_book_ts_ns",
    "low_put_book_ts_ns",
    "high_call_book_ts_ns",
    "high_put_book_ts_ns",
    "low_call_book_age_ns",
    "low_put_book_age_ns",
    "high_call_book_age_ns",
    "high_put_book_age_ns",
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
    "decision_low_call_side",
    "decision_low_call_price",
    "decision_low_put_side",
    "decision_low_put_price",
    "decision_high_call_side",
    "decision_high_call_price",
    "decision_high_put_side",
    "decision_high_put_price",
    "decision_multiplier_consistent",
    "decision_contract_multiplier",
    "decision_fair_box",
    "decision_edge_per_unit",
    "decision_gross_edge",
    "decision_low_call_cost",
    "decision_low_put_cost",
    "decision_high_call_cost",
    "decision_high_put_cost",
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
class BoxLegMap:
    call_by_contract: dict[tuple[str, float], str]
    put_by_contract: dict[tuple[str, float], str]


@dataclass(frozen=True)
class BoxArbConfig:
    max_signal_age_ns: int = 1_000_000
    max_leg_book_age_ns: int = 1_000_000
    max_leg_book_skew_ns: int = 1_000_000
    max_qty: int | None = None
    fair_value_adjustment: float = 0.0


@dataclass
class BoxSignalExecution:
    signal_index: int
    direction: str
    expiry: str
    low_strike: float
    high_strike: float
    signal_ts_ns: int
    ts_ns: int
    requested_qty: int
    leg_instrument_ids: dict[str, str]
    leg_sides: dict[str, int]
    leg_limit_prices: dict[str, float]
    contract_multiplier: float
    fair_box: float
    decision_net_edge: float
    expected_order_count: int = 4
    order_ids: list[int] = field(default_factory=list)
    order_id_by_leg: dict[str, int] = field(default_factory=dict)
    fill_count: int = 0
    filled_qty_by_order: dict[int, int] = field(default_factory=dict)
    fill_value_by_order: dict[int, float] = field(default_factory=dict)
    fill_cost_by_order: dict[int, float] = field(default_factory=dict)
    first_fill_ts_by_order: dict[int, int] = field(default_factory=dict)
    last_fill_ts_by_order: dict[int, int] = field(default_factory=dict)


class BoxArbTakerStrategy(MultiInstrumentStrategy):
    """Replay scanner box signals as a guarded four-leg IOC package.

    Supported directions:
    - buy_box: buy low call, sell low put, sell high call, buy high put
    - sell_box: sell low call, buy low put, buy high call, sell high put
    """

    def __init__(
        self,
        signals: pd.DataFrame,
        leg_map: BoxLegMap,
        config: BoxArbConfig | None = None,
    ):
        self.signals = signals.sort_values(
            "ts",
            kind="stable",
        ).reset_index(drop=True)
        self.leg_map = leg_map
        self.config = config or BoxArbConfig()
        _validate_config(self.config)
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self.next_signal = 0
        self.executions: list[BoxSignalExecution] = []
        self.order_to_execution: dict[int, int] = {}
        self.execution_guard_decisions: list[dict[str, object]] = []

    def on_start(self, engine: MultiInstrumentEngine):
        self._reset_run_state()

    def on_tick(
        self,
        engine: MultiInstrumentEngine,
        instrument_id: str,
        tick: dict,
    ):
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

    def on_fill(
        self,
        engine: MultiInstrumentEngine,
        fill: RoutedFill,
    ):
        execution_idx = self.order_to_execution.get(fill.oid)
        if execution_idx is None:
            return
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
                for leg in BOX_LEGS
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
                package_value = _box_package_value(
                    {
                        leg: float(evidence["fill_vwap"])
                        for leg, evidence in leg_fills.items()
                    }
                )
                if execution.direction == "buy_box":
                    realized_edge_per_unit = (
                        execution.fair_box - package_value
                    )
                else:
                    realized_edge_per_unit = (
                        package_value - execution.fair_box
                    )
                realized_gross_edge = (
                    realized_edge_per_unit
                    * execution.requested_qty
                    * execution.contract_multiplier
                )
                realized_total_cost = sum(
                    float(leg_fills[leg]["fill_cost"])
                    for leg in BOX_LEGS
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
                    "expiry": execution.expiry,
                    "low_strike": execution.low_strike,
                    "high_strike": execution.high_strike,
                    "signal_ts_ns": execution.signal_ts_ns,
                    "decision_ts_ns": execution.ts_ns,
                    "signal_age_ns": (
                        execution.ts_ns - execution.signal_ts_ns
                    ),
                    "requested_qty": execution.requested_qty,
                    "expected_order_count": (
                        execution.expected_order_count
                    ),
                    "order_count": accepted_orders,
                    "route_rejection_count": (
                        execution.expected_order_count
                        - accepted_orders
                    ),
                    "fill_count": execution.fill_count,
                    "filled_leg_count": filled_legs,
                    "fully_filled_leg_count": fully_filled_legs,
                    "unfilled_leg_count": (
                        execution.expected_order_count
                        - fully_filled_legs
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
                    "fair_box": execution.fair_box,
                    "decision_net_edge": (
                        execution.decision_net_edge
                    ),
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
                    "realized_edge_positive": bool(
                        realized_edge_evaluable
                        and realized_net_edge is not None
                        and realized_net_edge > 0.0
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
            "first_fill_ts_ns",
            "last_fill_ts_ns",
            "fill_span_ns",
        ]
        for leg in BOX_LEGS:
            nullable_integer_columns.extend(
                [
                    f"{leg}_order_id",
                    f"{leg}_filled_qty",
                    f"{leg}_first_fill_ts_ns",
                    f"{leg}_last_fill_ts_ns",
                ]
            )
        for column in nullable_integer_columns:
            if column in frame.columns:
                frame[column] = frame[column].astype("Int64")
        return frame

    def execution_guard_report(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.execution_guard_decisions,
            columns=BOX_EXECUTION_GUARD_COLUMNS,
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
        expiry = str(signal["expiry"])
        low_strike = float(signal["low_strike"])
        high_strike = float(signal["high_strike"])
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
        if high_strike <= low_strike:
            guard["guard_reason"] = "invalid_strike_order"
            self.execution_guard_decisions.append(guard)
            return True
        if direction not in {"buy_box", "sell_box"}:
            guard["guard_reason"] = "unsupported_direction"
            self.execution_guard_decisions.append(guard)
            return True

        low_key = _contract_key(expiry, low_strike)
        high_key = _contract_key(expiry, high_strike)
        leg_instrument_ids = {
            "low_call": self.leg_map.call_by_contract.get(
                low_key,
                "",
            ),
            "low_put": self.leg_map.put_by_contract.get(
                low_key,
                "",
            ),
            "high_call": self.leg_map.call_by_contract.get(
                high_key,
                "",
            ),
            "high_put": self.leg_map.put_by_contract.get(
                high_key,
                "",
            ),
        }
        for leg, instrument_id in leg_instrument_ids.items():
            guard[f"{leg}_instrument_id"] = instrument_id
        missing_mappings = [
            leg
            for leg, instrument_id in leg_instrument_ids.items()
            if not instrument_id
        ]
        if missing_mappings:
            guard["guard_reason"] = "missing_leg_mapping"
            guard["affected_legs"] = ",".join(missing_mappings)
            self.execution_guard_decisions.append(guard)
            return False
        if len(set(leg_instrument_ids.values())) != len(
            leg_instrument_ids
        ):
            guard["guard_reason"] = (
                "duplicate_leg_instrument"
            )
            guard["affected_legs"] = ",".join(BOX_LEGS)
            self.execution_guard_decisions.append(guard)
            return False
        unknown_instruments = [
            leg
            for leg, instrument_id in leg_instrument_ids.items()
            if instrument_id not in engine.instruments
        ]
        if unknown_instruments:
            guard["guard_reason"] = "unknown_leg_instrument"
            guard["affected_legs"] = ",".join(
                unknown_instruments
            )
            self.execution_guard_decisions.append(guard)
            return False

        books = {
            leg: engine.last_tick(instrument_id)
            for leg, instrument_id in leg_instrument_ids.items()
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
        for leg in BOX_LEGS:
            guard[f"{leg}_book_ts_ns"] = book_timestamps[leg]
            guard[f"{leg}_book_age_ns"] = book_ages[leg]
        guard["max_observed_book_age_ns"] = max(
            book_ages.values()
        )
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
            leg: max(
                int(signal["ts"]) - book_timestamps[leg],
                0,
            )
            for leg in BOX_LEGS
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
            guard["affected_legs"] = ",".join(BOX_LEGS)
            self.execution_guard_decisions.append(guard)
            return False

        legs = _execution_legs(
            direction,
            leg_instrument_ids,
            books,
        )
        edge_evidence = _decision_edge_evidence(
            engine,
            direction=direction,
            low_strike=low_strike,
            high_strike=high_strike,
            fair_value_adjustment=(
                self.config.fair_value_adjustment
            ),
            qty=qty,
            leg_instrument_ids=leg_instrument_ids,
            legs=legs,
        )
        guard.update(edge_evidence)
        if (
            edge_evidence[
                "decision_multiplier_consistent"
            ]
            is False
        ):
            guard["guard_reason"] = (
                "instrument_multiplier_mismatch"
            )
            guard["affected_legs"] = ",".join(BOX_LEGS)
            self.execution_guard_decisions.append(guard)
            return False
        if float(edge_evidence["decision_net_edge"]) <= 0.0:
            guard["guard_reason"] = (
                "execution_edge_below_threshold"
            )
            guard["affected_legs"] = ",".join(BOX_LEGS)
            self.execution_guard_decisions.append(guard)
            return False

        preflight = engine.preflight_ioc_batch(
            [
                IOCOrderIntent(
                    instrument_id=instrument_id,
                    side=side,
                    qty=qty,
                    price=price,
                )
                for instrument_id, side, price in legs
            ]
        )
        guard.update(
            _preflight_evidence(preflight)
        )
        if not preflight.passed:
            guard["guard_reason"] = (
                "ioc_batch_preflight_rejected"
            )
            instrument_to_leg = {
                instrument_id: leg
                for leg, instrument_id
                in leg_instrument_ids.items()
            }
            guard["affected_legs"] = instrument_to_leg.get(
                preflight.instrument_id,
                "package",
            )
            self.execution_guard_decisions.append(guard)
            return False

        guard["guard_passed"] = True
        guard["guard_reason"] = "ready"
        guard["orders_requested"] = 4
        execution = BoxSignalExecution(
            signal_index=signal_index,
            direction=direction,
            expiry=expiry,
            low_strike=low_strike,
            high_strike=high_strike,
            signal_ts_ns=int(signal["ts"]),
            ts_ns=now,
            requested_qty=qty,
            leg_instrument_ids=leg_instrument_ids,
            leg_sides={
                leg: int(
                    edge_evidence[f"decision_{leg}_side"]
                )
                for leg in BOX_LEGS
            },
            leg_limit_prices={
                leg: float(
                    edge_evidence[f"decision_{leg}_price"]
                )
                for leg in BOX_LEGS
            },
            contract_multiplier=float(
                edge_evidence["decision_contract_multiplier"]
            ),
            fair_box=float(
                edge_evidence["decision_fair_box"]
            ),
            decision_net_edge=float(
                edge_evidence["decision_net_edge"]
            ),
        )
        self.executions.append(execution)
        execution_idx = len(self.executions) - 1
        for leg, (
            instrument_id,
            side,
            price,
        ) in zip(BOX_LEGS, legs, strict=True):
            oid = engine.send(
                instrument_id,
                side,
                qty,
                price,
                OrderType.IOC,
            )
            if oid is not None:
                execution.order_ids.append(oid)
                execution.order_id_by_leg[leg] = oid
                self.order_to_execution[oid] = execution_idx
        guard["orders_accepted"] = len(execution.order_ids)
        guard["routing_complete"] = (
            len(execution.order_ids) == 4
        )
        guard["routing_status"] = (
            "complete"
            if len(execution.order_ids) == 4
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
        row: dict[str, object] = {
            "signal_index": int(signal_index),
            "direction": str(signal.get("direction", "")),
            "expiry": str(signal.get("expiry", "")),
            "low_strike": float(
                signal.get("low_strike", float("nan"))
            ),
            "high_strike": float(
                signal.get("high_strike", float("nan"))
            ),
            "signal_ts_ns": int(signal["ts"]),
            "decision_ts_ns": int(now),
            "signal_age_ns": int(now - int(signal["ts"])),
            "trigger_instrument_id": str(
                trigger_instrument_id
            ),
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
            "decision_contract_multiplier": None,
            "decision_multiplier_consistent": False,
            "decision_fair_box": None,
            "decision_edge_per_unit": None,
            "decision_gross_edge": None,
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
            "ioc_batch_preflight_visible_capacity_checked": (
                False
            ),
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
        for leg in BOX_LEGS:
            row[f"{leg}_instrument_id"] = ""
            row[f"{leg}_book_ts_ns"] = None
            row[f"{leg}_book_age_ns"] = None
            row[f"decision_{leg}_side"] = 0
            row[f"decision_{leg}_price"] = None
            row[f"decision_{leg}_cost"] = None
        return row


def _contract_key(
    expiry: str,
    strike: float,
) -> tuple[str, float]:
    return str(expiry), float(strike)


def _source_book_ts(tick: dict) -> int:
    return int(tick.get("market_ts", tick["ts"]))


def _execution_legs(
    direction: str,
    leg_instrument_ids: dict[str, str],
    books: dict[str, dict],
) -> list[tuple[str, int, float]]:
    if direction == "buy_box":
        sides = {
            "low_call": 1,
            "low_put": -1,
            "high_call": -1,
            "high_put": 1,
        }
    else:
        sides = {
            "low_call": -1,
            "low_put": 1,
            "high_call": 1,
            "high_put": -1,
        }
    return [
        (
            leg_instrument_ids[leg],
            sides[leg],
            float(
                books[leg]["ask"]
                if sides[leg] > 0
                else books[leg]["bid"]
            ),
        )
        for leg in BOX_LEGS
    ]


def _box_package_value(prices: dict[str, float]) -> float:
    return float(
        prices["low_call"]
        - prices["low_put"]
        - prices["high_call"]
        + prices["high_put"]
    )


def _decision_edge_evidence(
    engine: MultiInstrumentEngine,
    *,
    direction: str,
    low_strike: float,
    high_strike: float,
    fair_value_adjustment: float,
    qty: int,
    leg_instrument_ids: dict[str, str],
    legs: list[tuple[str, int, float]],
) -> dict[str, object]:
    by_instrument = {
        instrument_id: (side, float(price))
        for instrument_id, side, price in legs
    }
    prices: dict[str, float] = {}
    sides: dict[str, int] = {}
    costs: dict[str, float] = {}
    multipliers: dict[str, float] = {}
    for leg in BOX_LEGS:
        instrument_id = leg_instrument_ids[leg]
        side, price = by_instrument[instrument_id]
        instrument_config = engine.instruments[instrument_id]
        sides[leg] = int(side)
        prices[leg] = float(price)
        multipliers[leg] = float(
            instrument_config.instrument.multiplier
        )
        costs[leg] = float(
            instrument_config.costs.cost(
                side,
                price,
                qty,
                instrument_config.instrument,
            )
        )
    multiplier_values = set(multipliers.values())
    multiplier_consistent = len(multiplier_values) == 1
    multiplier = (
        next(iter(multiplier_values))
        if multiplier_values
        else 0.0
    )
    fair_box = (
        high_strike
        - low_strike
        + fair_value_adjustment
    )
    package_value = _box_package_value(prices)
    edge_per_unit = (
        fair_box - package_value
        if direction == "buy_box"
        else package_value - fair_box
    )
    total_cost = sum(costs.values())
    gross_edge = edge_per_unit * qty * multiplier
    return {
        "edge_revalidation_checked": True,
        "edge_revalidation_qty": int(qty),
        **{
            f"decision_{leg}_side": sides[leg]
            for leg in BOX_LEGS
        },
        **{
            f"decision_{leg}_price": prices[leg]
            for leg in BOX_LEGS
        },
        **{
            f"decision_{leg}_cost": costs[leg]
            for leg in BOX_LEGS
        },
        "decision_multiplier_consistent": (
            multiplier_consistent
        ),
        "decision_contract_multiplier": multiplier,
        "decision_fair_box": float(fair_box),
        "decision_edge_per_unit": float(edge_per_unit),
        "decision_gross_edge": float(gross_edge),
        "decision_total_cost": float(total_cost),
        "decision_net_edge": float(gross_edge - total_cost),
        "decision_min_net_edge": 0.0,
    }


def _preflight_evidence(preflight) -> dict[str, object]:
    return {
        "ioc_batch_preflight_attempted": True,
        "ioc_batch_preflight_passed": preflight.passed,
        "ioc_batch_preflight_reason": preflight.reason,
        "ioc_batch_preflight_instrument_id": (
            preflight.instrument_id
        ),
        "ioc_batch_preflight_projected_min": (
            None
            if pd.isna(preflight.projected_min)
            else preflight.projected_min
        ),
        "ioc_batch_preflight_projected_max": (
            None
            if pd.isna(preflight.projected_max)
            else preflight.projected_max
        ),
        "ioc_batch_preflight_limit": (
            None
            if pd.isna(preflight.limit)
            else preflight.limit
        ),
        "ioc_batch_preflight_conflicting_oid": (
            preflight.conflicting_oid
        ),
        "ioc_batch_preflight_visible_capacity_checked": (
            preflight.visible_capacity_checked
        ),
        "ioc_batch_preflight_min_visible_fill_ratio": (
            None
            if pd.isna(preflight.min_visible_fill_ratio)
            else preflight.min_visible_fill_ratio
        ),
        "ioc_batch_preflight_limiting_instrument_id": (
            preflight.limiting_instrument_id
        ),
        "ioc_batch_preflight_requested_qty": (
            preflight.requested_qty
        ),
        "ioc_batch_preflight_available_qty": (
            None
            if pd.isna(preflight.available_qty)
            else preflight.available_qty
        ),
        "ioc_batch_preflight_touch_price": (
            None
            if pd.isna(preflight.touch_price)
            else preflight.touch_price
        ),
        "ioc_batch_preflight_limit_price": (
            None
            if pd.isna(preflight.limit_price)
            else preflight.limit_price
        ),
    }


def _execution_leg_fill(
    execution: BoxSignalExecution,
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
            float(
                execution.fill_cost_by_order.get(
                    order_id,
                    0.0,
                )
            )
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


def _validate_config(config: BoxArbConfig) -> None:
    for name in (
        "max_signal_age_ns",
        "max_leg_book_age_ns",
        "max_leg_book_skew_ns",
    ):
        value = getattr(config, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
        ):
            raise ValueError(
                f"{name} must be a non-negative integer"
            )
    if config.max_qty is not None and (
        isinstance(config.max_qty, bool)
        or not isinstance(config.max_qty, int)
        or config.max_qty <= 0
    ):
        raise ValueError("max_qty must be a positive integer")
    if not isfinite(float(config.fair_value_adjustment)):
        raise ValueError(
            "fair_value_adjustment must be finite"
        )
