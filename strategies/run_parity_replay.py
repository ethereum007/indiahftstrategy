from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv, normalize_option_chain
from data.loaders import load_tick_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiBacktestResult, MultiInstrumentEngine, VenueConfig
from reports.replay import (
    input_quarantine_frame,
    replay_summary,
    write_replay_outputs,
)
from scanners.parity_box import (
    ScannerCosts,
    ScannerInstruments,
    scan_parity_with_audit,
)
from strategies.parity_arb import ParityArbConfig, ParityArbTakerStrategy, ParityLegMap


@dataclass(frozen=True)
class ParityReplayResult:
    result: MultiBacktestResult
    signals: pd.DataFrame
    summary: pd.DataFrame
    legging: pd.DataFrame
    execution_guard: pd.DataFrame
    input_quarantine: pd.DataFrame
    futures_join_audit: pd.DataFrame
    output_dir: Path | None = None


def run_parity_replay(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    future_tick: float = 0.05,
    asof_latency_ns: int = 0,
    max_futures_quote_age_ns: int = 1_000_000,
    depth_fraction: float = 0.25,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    max_signal_age_ns: int = 1_000_000,
    max_leg_book_age_ns: int = 1_000_000,
    max_leg_book_skew_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
) -> ParityReplayResult:
    normalized_chain = load_option_chain_csv(
        chain_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    )
    normalized_futures = load_tick_csv(
        futures_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    )
    chain = normalized_chain.data
    futures = normalized_futures.data
    input_quarantine = input_quarantine_frame(
        {
            "chain": normalized_chain.quarantine,
            "futures": normalized_futures.quarantine,
        },
        dataset_types={
            "chain": "option_chain",
            "futures": "l1_ticks",
        },
    )

    option = Instrument("INDEX-OPT", Kind.OPT, lot_size=lot_size, tick=option_tick)
    future = Instrument("INDEX-FUT", Kind.FUT, lot_size=lot_size, tick=future_tick)
    option_costs = IndianCostModel.nse_index_options()
    future_costs = IndianCostModel.nse_index_futures()
    parity_scan = scan_parity_with_audit(
        chain,
        futures,
        instruments=ScannerInstruments(option=option, future=future),
        costs=ScannerCosts(option=option_costs, future=future_costs),
        asof_latency_ns=asof_latency_ns,
        tolerance_ns=max_futures_quote_age_ns,
        depth_fraction=depth_fraction,
    )
    signals = parity_scan.opportunities
    futures_join_audit = parity_scan.futures_join_audit
    if signal_limit is not None:
        signals = signals.head(signal_limit).copy()

    instruments, leg_map = _build_instruments(
        chain=chain,
        futures=futures,
        lot_size=lot_size,
        option_tick=option_tick,
        future_tick=future_tick,
        option_costs=option_costs,
        future_costs=future_costs,
        max_position_lots=max_position_lots,
    )
    strategy = ParityArbTakerStrategy(
        signals,
        leg_map,
        ParityArbConfig(
            max_signal_age_ns=max_signal_age_ns,
            max_leg_book_age_ns=max_leg_book_age_ns,
            max_leg_book_skew_ns=max_leg_book_skew_ns,
            max_qty=max_qty,
        ),
    )
    engine = MultiInstrumentEngine(
        instruments=instruments,
        venues={
            "NSE": VenueConfig(
                "NSE",
                LatencyModel(
                    feed_us=feed_latency_us,
                    order_us=order_latency_us,
                    jitter_us=0,
                    _rng=np.random.default_rng(17),
                ),
            )
        },
        strategy=strategy,
    )
    result = engine.run()
    strategy_order_ids = [oid for execution in strategy.executions for oid in execution.order_ids]
    summary = replay_summary(
        result,
        strategy_orders=strategy_order_ids,
        input_quarantine=input_quarantine,
    )
    for key, value in _futures_freshness_metrics(
        futures_join_audit,
        signals,
        max_futures_quote_age_ns=max_futures_quote_age_ns,
    ).items():
        summary[key] = value
    legging = strategy.legging_report()
    execution_guard = strategy.execution_guard_report()
    for key, value in _execution_guard_metrics(
        execution_guard,
        legging,
        max_leg_book_age_ns=max_leg_book_age_ns,
        max_leg_book_skew_ns=max_leg_book_skew_ns,
    ).items():
        summary[key] = value
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        write_replay_outputs(
            result=result,
            output_dir=out_dir,
            summary=summary,
            strategy_order_ids=strategy_order_ids,
            extra_frames={
                "signals": signals,
                "legging": legging,
                "parity_execution_guard": execution_guard,
                "input_quarantine": input_quarantine,
                "parity_futures_join_audit": futures_join_audit,
            },
            manifest_run_type="parity_replay",
            manifest_inputs={"chain": chain_path, "futures": futures_path},
            manifest_parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "lot_size": lot_size,
                "option_tick": option_tick,
                "future_tick": future_tick,
                "asof_latency_ns": asof_latency_ns,
                "max_futures_quote_age_ns": max_futures_quote_age_ns,
                "depth_fraction": depth_fraction,
                "feed_latency_us": feed_latency_us,
                "order_latency_us": order_latency_us,
                "max_signal_age_ns": max_signal_age_ns,
                "max_leg_book_age_ns": max_leg_book_age_ns,
                "max_leg_book_skew_ns": max_leg_book_skew_ns,
                "max_qty": max_qty,
                "max_position_lots": max_position_lots,
                "signal_limit": signal_limit,
            },
        )
    return ParityReplayResult(
        result=result,
        signals=signals,
        summary=summary,
        legging=legging,
        execution_guard=execution_guard,
        input_quarantine=input_quarantine,
        futures_join_audit=futures_join_audit,
        output_dir=out_dir,
    )


def _futures_freshness_metrics(
    audit: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    max_futures_quote_age_ns: int,
) -> dict[str, int | bool]:
    reasons = (
        audit["reason"].astype(str)
        if "reason" in audit.columns
        else pd.Series(dtype="object")
    )
    signal_ages = pd.to_numeric(
        signals.get(
            "future_asof_age_ns",
            pd.Series(index=signals.index, dtype="float64"),
        ),
        errors="coerce",
    )
    observed_join_ages = pd.to_numeric(
        audit.get(
            "future_asof_age_ns",
            pd.Series(index=audit.index, dtype="float64"),
        ),
        errors="coerce",
    ).dropna()
    observed_signal_ages = signal_ages.dropna()
    signal_age_violations = (
        signal_ages.lt(0) | signal_ages.gt(max_futures_quote_age_ns)
    )
    return {
        "parity_futures_asof_freshness_enabled": True,
        "parity_futures_max_quote_age_ns": int(
            max_futures_quote_age_ns
        ),
        "parity_futures_join_rows": int(len(audit)),
        "parity_futures_fresh_join_rows": int((reasons == "fresh").sum()),
        "parity_futures_stale_join_rows": int(
            reasons.isin(
                {
                    "stale_future_quote",
                    "negative_future_quote_age",
                }
            ).sum()
        ),
        "parity_futures_unmatched_join_rows": int(
            reasons.isin(
                {
                    "no_prior_future_quote",
                    "incomplete_future_quote",
                }
            ).sum()
        ),
        "parity_futures_max_observed_join_age_ns": int(
            observed_join_ages.max()
        )
        if not observed_join_ages.empty
        else 0,
        "parity_futures_signal_count": int(len(signals)),
        "parity_futures_signals_without_age": int(signal_ages.isna().sum()),
        "parity_futures_signal_age_violations": int(
            signal_age_violations.sum()
        ),
        "parity_futures_max_signal_age_ns": int(
            observed_signal_ages.max()
        )
        if not observed_signal_ages.empty
        else 0,
    }


def _execution_guard_metrics(
    guard: pd.DataFrame,
    legging: pd.DataFrame,
    *,
    max_leg_book_age_ns: int,
    max_leg_book_skew_ns: int,
) -> dict[str, int | float | bool]:
    passed = (
        guard["guard_passed"].fillna(False).astype(bool)
        if "guard_passed" in guard.columns
        else pd.Series(False, index=guard.index)
    )
    reasons = (
        guard["guard_reason"].astype(str)
        if "guard_reason" in guard.columns
        else pd.Series("", index=guard.index)
    )
    routing_status = (
        guard["routing_status"].astype(str)
        if "routing_status" in guard.columns
        else pd.Series("", index=guard.index)
    )
    preflight_enabled_raw = guard.get(
        "ioc_batch_preflight_enabled",
        pd.Series(np.nan, index=guard.index),
    )
    preflight_attempted_raw = guard.get(
        "ioc_batch_preflight_attempted",
        pd.Series(np.nan, index=guard.index),
    )
    preflight_passed_raw = guard.get(
        "ioc_batch_preflight_passed",
        pd.Series(np.nan, index=guard.index),
    )
    preflight_reasons = (
        guard.get(
            "ioc_batch_preflight_reason",
            pd.Series(pd.NA, index=guard.index, dtype="string"),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )
    preflight_enabled = preflight_enabled_raw.fillna(False).astype(
        bool
    )
    preflight_attempted = preflight_attempted_raw.fillna(False).astype(
        bool
    )
    preflight_passed = preflight_passed_raw.fillna(False).astype(bool)
    edge_metrics = _edge_revalidation_metrics(
        guard,
        passed=passed,
        reasons=reasons,
        preflight_attempted=preflight_attempted,
    )
    signal_source_metrics = _signal_source_metrics(
        guard,
        passed=passed,
        reasons=reasons,
        preflight_attempted=preflight_attempted,
    )
    capacity_checked_raw = guard.get(
        "ioc_batch_preflight_visible_capacity_checked",
        pd.Series(np.nan, index=guard.index),
    )
    capacity_checked = capacity_checked_raw.fillna(False).astype(bool)
    capacity_ratio = pd.to_numeric(
        guard.get(
            "ioc_batch_preflight_min_visible_fill_ratio",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    capacity_instrument_raw = guard.get(
        "ioc_batch_preflight_limiting_instrument_id",
        pd.Series(pd.NA, index=guard.index, dtype="string"),
    )
    capacity_instruments = (
        capacity_instrument_raw.astype("string").fillna("").str.strip()
    )
    capacity_requested = pd.to_numeric(
        guard.get(
            "ioc_batch_preflight_requested_qty",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    capacity_available = pd.to_numeric(
        guard.get(
            "ioc_batch_preflight_available_qty",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    capacity_touch_price = pd.to_numeric(
        guard.get(
            "ioc_batch_preflight_touch_price",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    capacity_limit_price = pd.to_numeric(
        guard.get(
            "ioc_batch_preflight_limit_price",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    capacity_passed = preflight_attempted & preflight_passed
    capacity_not_marketable = preflight_reasons.eq(
        "visible_ioc_not_marketable"
    )
    capacity_shortfall = preflight_reasons.eq(
        "visible_ioc_capacity_shortfall"
    )
    capacity_relevant = (
        capacity_passed
        | capacity_not_marketable
        | capacity_shortfall
    )
    capacity_missing_evidence = capacity_relevant & (
        capacity_checked_raw.isna()
        | capacity_ratio.isna()
        | capacity_instrument_raw.isna()
        | capacity_instruments.eq("")
        | capacity_requested.isna()
        | capacity_available.isna()
        | capacity_touch_price.isna()
        | capacity_limit_price.isna()
    )
    capacity_consistency_violation = (
        ~capacity_checked
        | capacity_requested.le(0)
        | capacity_available.lt(0)
        | (
            capacity_passed
            & (
                capacity_ratio.lt(1.0)
                | capacity_available.lt(capacity_requested)
            )
        )
        | (
            capacity_not_marketable
            & capacity_ratio.ne(0.0)
        )
        | (
            capacity_shortfall
            & (
                capacity_ratio.ge(1.0)
                | capacity_available.ge(capacity_requested)
            )
        )
    )
    routed_capacity_ratios = capacity_ratio.loc[
        capacity_passed
    ].dropna()
    preflight_missing_evidence = (
        preflight_enabled_raw.isna()
        | preflight_attempted_raw.isna()
        | preflight_passed_raw.isna()
        | preflight_reasons.eq("")
    )
    preflight_consistency_violation = (
        ~preflight_enabled
        | (
            preflight_attempted
            & preflight_passed
            & ~preflight_reasons.eq("passed")
        )
        | (
            preflight_attempted
            & ~preflight_passed
            & preflight_reasons.isin({"passed", "not_attempted"})
        )
        | (
            ~preflight_attempted
            & (
                preflight_passed
                | ~preflight_reasons.eq("not_attempted")
            )
        )
        | (
            passed
            & (
                ~preflight_attempted
                | ~preflight_passed
                | ~preflight_reasons.eq("passed")
            )
        )
        | (
            reasons.eq("ioc_batch_preflight_rejected")
            & (
                ~preflight_attempted
                | preflight_passed
                | preflight_reasons.isin(
                    {"passed", "not_attempted"}
                )
            )
        )
        | (
            ~passed
            & ~reasons.eq("ioc_batch_preflight_rejected")
            & (
                preflight_attempted
                | preflight_passed
                | ~preflight_reasons.eq("not_attempted")
            )
        )
    )
    passed_rows = guard.loc[passed]
    leg_age_columns = [
        "call_book_age_ns",
        "put_book_age_ns",
        "future_book_age_ns",
    ]
    leg_ages = pd.DataFrame(
        {
            column: pd.to_numeric(
                passed_rows.get(
                    column,
                    pd.Series(index=passed_rows.index, dtype="float64"),
                ),
                errors="coerce",
            )
            for column in leg_age_columns
        },
        index=passed_rows.index,
    )
    skew = pd.to_numeric(
        passed_rows.get(
            "leg_book_skew_ns",
            pd.Series(index=passed_rows.index, dtype="float64"),
        ),
        errors="coerce",
    )
    observed_max_age = (
        leg_ages.max(axis=1).dropna()
        if not leg_ages.empty
        else pd.Series(dtype="float64")
    )
    observed_skew = skew.dropna()
    missing_guard_age_rows = (
        leg_ages.isna().any(axis=1) | skew.isna()
    )
    partial = (
        legging["partial"].fillna(True).astype(bool)
        if "partial" in legging.columns
        else pd.Series(True, index=legging.index)
    )
    route_rejections = pd.to_numeric(
        legging.get(
            "route_rejection_count",
            pd.Series(index=legging.index, dtype="float64"),
        ),
        errors="coerce",
    ).fillna(0)
    unfilled_legs = pd.to_numeric(
        legging.get(
            "unfilled_leg_count",
            pd.Series(index=legging.index, dtype="float64"),
        ),
        errors="coerce",
    ).fillna(0)
    return {
        "parity_execution_guard_enabled": True,
        "parity_execution_max_leg_book_age_ns": int(
            max_leg_book_age_ns
        ),
        "parity_execution_max_leg_book_skew_ns": int(
            max_leg_book_skew_ns
        ),
        "parity_execution_guard_attempts": int(len(guard)),
        "parity_execution_guard_passed_attempts": int(passed.sum()),
        "parity_execution_guard_deferred_attempts": int((~passed).sum()),
        **signal_source_metrics,
        **edge_metrics,
        "parity_execution_ioc_batch_preflight_enabled": True,
        "parity_execution_ioc_batch_preflight_attempts": int(
            preflight_attempted.sum()
        ),
        "parity_execution_ioc_batch_preflight_passed_attempts": int(
            (preflight_attempted & preflight_passed).sum()
        ),
        "parity_execution_ioc_batch_preflight_rejected_attempts": int(
            (preflight_attempted & ~preflight_passed).sum()
        ),
        "parity_execution_ioc_batch_preflight_missing_evidence_rows": (
            int(preflight_missing_evidence.sum())
        ),
        "parity_execution_ioc_batch_preflight_consistency_violations": (
            int(
                (
                    preflight_consistency_violation
                    & ~preflight_missing_evidence
                ).sum()
            )
        ),
        "parity_execution_ioc_visible_not_marketable_attempts": int(
            capacity_not_marketable.sum()
        ),
        "parity_execution_ioc_visible_capacity_shortfall_attempts": (
            int(capacity_shortfall.sum())
        ),
        "parity_execution_ioc_visible_capacity_missing_evidence_rows": (
            int(capacity_missing_evidence.sum())
        ),
        "parity_execution_ioc_visible_capacity_consistency_violations": (
            int(
                (
                    capacity_relevant
                    & capacity_consistency_violation
                    & ~capacity_missing_evidence
                ).sum()
            )
        ),
        "parity_execution_min_routed_visible_fill_ratio": (
            float(routed_capacity_ratios.min())
            if not routed_capacity_ratios.empty
            else 0.0
        ),
        "parity_execution_signal_expiry_events": int(
            (reasons == "signal_age_exceeded").sum()
        ),
        "parity_execution_stale_book_attempts": int(
            (reasons == "stale_leg_book").sum()
        ),
        "parity_execution_negative_book_age_attempts": int(
            (reasons == "negative_leg_book_age").sum()
        ),
        "parity_execution_skew_attempts": int(
            (reasons == "leg_book_skew_exceeded").sum()
        ),
        "parity_execution_routing_complete_attempts": int(
            (passed & routing_status.eq("complete")).sum()
        ),
        "parity_execution_routing_incomplete_attempts": int(
            (passed & ~routing_status.eq("complete")).sum()
        ),
        "parity_execution_guard_passed_missing_age_rows": int(
            missing_guard_age_rows.sum()
        ),
        "parity_execution_guard_age_violations": int(
            (
                leg_ages.lt(0)
                | leg_ages.gt(max_leg_book_age_ns)
            ).any(axis=1).sum()
        ),
        "parity_execution_guard_skew_violations": int(
            (
                skew.lt(0)
                | skew.gt(max_leg_book_skew_ns)
            ).sum()
        ),
        "parity_execution_max_routed_book_age_ns": int(
            observed_max_age.max()
        )
        if not observed_max_age.empty
        else 0,
        "parity_execution_max_routed_book_skew_ns": int(
            observed_skew.max()
        )
        if not observed_skew.empty
        else 0,
        "parity_execution_count": int(len(legging)),
        "parity_execution_complete_count": int((~partial).sum()),
        "parity_execution_incomplete_count": int(partial.sum()),
        "parity_execution_route_rejected_legs": int(
            route_rejections.sum()
        ),
        "parity_execution_unfilled_legs": int(unfilled_legs.sum()),
    }


def _signal_source_metrics(
    guard: pd.DataFrame,
    *,
    passed: pd.Series,
    reasons: pd.Series,
    preflight_attempted: pd.Series,
) -> dict[str, int | bool]:
    enabled_raw = guard.get(
        "signal_source_causality_enabled",
        pd.Series(np.nan, index=guard.index),
    )
    checked_raw = guard.get(
        "signal_source_books_checked",
        pd.Series(np.nan, index=guard.index),
    )
    ready_raw = guard.get(
        "signal_source_books_ready",
        pd.Series(np.nan, index=guard.index),
    )
    enabled = enabled_raw.fillna(False).astype(bool)
    checked = checked_raw.fillna(False).astype(bool)
    ready = ready_raw.fillna(False).astype(bool)
    signal_age = _numeric_guard_column(guard, "signal_age_ns")
    call_age = _numeric_guard_column(guard, "call_book_age_ns")
    put_age = _numeric_guard_column(guard, "put_book_age_ns")
    reported_lag = _numeric_guard_column(
        guard,
        "signal_source_max_lag_ns",
    )
    edge_checked = (
        guard.get(
            "edge_revalidation_checked",
            pd.Series(False, index=guard.index),
        )
        .fillna(False)
        .astype(bool)
    )
    pending = reasons.eq("signal_source_books_pending")
    relevant = (
        checked
        | edge_checked
        | preflight_attempted
        | passed
        | pending
    )
    missing = relevant & (
        enabled_raw.isna()
        | checked_raw.isna()
        | ready_raw.isna()
        | signal_age.isna()
        | call_age.isna()
        | put_age.isna()
        | reported_lag.isna()
    )
    expected_lag = pd.concat(
        [
            call_age.sub(signal_age),
            put_age.sub(signal_age),
            pd.Series(0.0, index=guard.index),
        ],
        axis=1,
    ).max(axis=1)
    expected_ready = expected_lag.eq(0.0)
    consistency_violation = (
        ~enabled
        | ~checked
        | reported_lag.lt(0)
        | reported_lag.mod(1).ne(0)
        | reported_lag.ne(expected_lag)
        | ready.ne(expected_ready)
        | (
            pending
            & ready
        )
        | (
            ~ready
            & ~pending
        )
        | (
            (
                edge_checked
                | preflight_attempted
                | passed
            )
            & ~ready
        )
    )
    observed_lags = reported_lag.loc[checked].dropna()
    return {
        "parity_execution_signal_source_causality_enabled": True,
        "parity_execution_signal_source_checks": int(checked.sum()),
        "parity_execution_signal_source_ready_attempts": int(
            (checked & ready).sum()
        ),
        "parity_execution_signal_source_pending_attempts": int(
            pending.sum()
        ),
        "parity_execution_signal_source_missing_evidence_rows": int(
            missing.sum()
        ),
        "parity_execution_signal_source_consistency_violations": int(
            (
                relevant
                & consistency_violation
                & ~missing
            ).sum()
        ),
        "parity_execution_max_signal_source_lag_ns": (
            int(observed_lags.max())
            if not observed_lags.empty
            else 0
        ),
    }


def _edge_revalidation_metrics(
    guard: pd.DataFrame,
    *,
    passed: pd.Series,
    reasons: pd.Series,
    preflight_attempted: pd.Series,
) -> dict[str, int | float | bool]:
    enabled_raw = guard.get(
        "edge_revalidation_enabled",
        pd.Series(np.nan, index=guard.index),
    )
    checked_raw = guard.get(
        "edge_revalidation_checked",
        pd.Series(np.nan, index=guard.index),
    )
    enabled = enabled_raw.fillna(False).astype(bool)
    checked = checked_raw.fillna(False).astype(bool)
    directions = guard.get(
        "direction",
        pd.Series("", index=guard.index),
    ).astype(str)
    strike = _numeric_guard_column(guard, "strike")
    qty = _numeric_guard_column(guard, "edge_revalidation_qty")
    signal_net_edge = _numeric_guard_column(guard, "signal_net_edge")
    call_side = _numeric_guard_column(guard, "decision_call_side")
    call_price = _numeric_guard_column(guard, "decision_call_price")
    put_side = _numeric_guard_column(guard, "decision_put_side")
    put_price = _numeric_guard_column(guard, "decision_put_price")
    future_side = _numeric_guard_column(
        guard,
        "decision_future_side",
    )
    future_price = _numeric_guard_column(
        guard,
        "decision_future_price",
    )
    multiplier = _numeric_guard_column(
        guard,
        "decision_contract_multiplier",
    )
    edge_per_unit = _numeric_guard_column(
        guard,
        "decision_edge_per_unit",
    )
    gross_edge = _numeric_guard_column(guard, "decision_gross_edge")
    call_cost = _numeric_guard_column(guard, "decision_call_cost")
    put_cost = _numeric_guard_column(guard, "decision_put_cost")
    future_cost = _numeric_guard_column(
        guard,
        "decision_future_cost",
    )
    total_cost = _numeric_guard_column(guard, "decision_total_cost")
    net_edge = _numeric_guard_column(guard, "decision_net_edge")
    threshold = _numeric_guard_column(
        guard,
        "decision_min_net_edge",
    )

    buy_synthetic = directions.eq("buy_synthetic_sell_future")
    sell_synthetic = directions.eq("sell_synthetic_buy_future")
    direction_valid = buy_synthetic | sell_synthetic
    expected_call_side = pd.Series(0, index=guard.index, dtype="int64")
    expected_put_side = pd.Series(0, index=guard.index, dtype="int64")
    expected_future_side = pd.Series(
        0,
        index=guard.index,
        dtype="int64",
    )
    expected_call_side.loc[buy_synthetic] = 1
    expected_put_side.loc[buy_synthetic] = -1
    expected_future_side.loc[buy_synthetic] = -1
    expected_call_side.loc[sell_synthetic] = -1
    expected_put_side.loc[sell_synthetic] = 1
    expected_future_side.loc[sell_synthetic] = 1
    expected_edge_per_unit = pd.Series(
        np.nan,
        index=guard.index,
        dtype="float64",
    )
    expected_edge_per_unit.loc[buy_synthetic] = (
        future_price
        - (call_price - put_price + strike)
    )
    expected_edge_per_unit.loc[sell_synthetic] = (
        call_price - put_price + strike - future_price
    )
    expected_gross_edge = expected_edge_per_unit * qty * multiplier
    expected_total_cost = call_cost + put_cost + future_cost
    expected_net_edge = expected_gross_edge - expected_total_cost

    rejected = reasons.eq("execution_edge_below_threshold")
    relevant = checked | preflight_attempted | rejected
    required = [
        enabled_raw,
        checked_raw,
        strike,
        qty,
        signal_net_edge,
        call_side,
        call_price,
        put_side,
        put_price,
        future_side,
        future_price,
        multiplier,
        edge_per_unit,
        gross_edge,
        call_cost,
        put_cost,
        future_cost,
        total_cost,
        net_edge,
        threshold,
    ]
    missing = relevant & pd.concat(required, axis=1).isna().any(axis=1)
    numeric_values = [
        strike,
        qty,
        signal_net_edge,
        call_price,
        put_price,
        future_price,
        multiplier,
        edge_per_unit,
        gross_edge,
        call_cost,
        put_cost,
        future_cost,
        total_cost,
        net_edge,
        threshold,
    ]
    nonfinite = pd.concat(
        [~np.isfinite(values) for values in numeric_values],
        axis=1,
    ).any(axis=1)
    consistency_violation = (
        ~enabled
        | ~checked
        | ~direction_valid
        | qty.le(0)
        | qty.mod(1).ne(0)
        | signal_net_edge.le(0)
        | multiplier.le(0)
        | call_cost.lt(0)
        | put_cost.lt(0)
        | future_cost.lt(0)
        | total_cost.lt(0)
        | call_side.ne(expected_call_side)
        | put_side.ne(expected_put_side)
        | future_side.ne(expected_future_side)
        | nonfinite
        | edge_per_unit.sub(expected_edge_per_unit).abs().gt(1e-9)
        | gross_edge.sub(expected_gross_edge).abs().gt(1e-9)
        | total_cost.sub(expected_total_cost).abs().gt(1e-9)
        | net_edge.sub(expected_net_edge).abs().gt(1e-9)
        | (
            checked
            & ~preflight_attempted
            & ~rejected
        )
        | (
            preflight_attempted
            & net_edge.le(threshold)
        )
        | (
            rejected
            & net_edge.gt(threshold)
        )
    )
    routed_net_edges = net_edge.loc[passed].dropna()
    observed_decay = (
        signal_net_edge.loc[checked] - net_edge.loc[checked]
    ).dropna()
    return {
        "parity_execution_edge_revalidation_enabled": True,
        "parity_execution_edge_revalidation_attempts": int(
            checked.sum()
        ),
        "parity_execution_edge_revalidation_passed_attempts": int(
            preflight_attempted.sum()
        ),
        "parity_execution_edge_revalidation_rejected_attempts": int(
            rejected.sum()
        ),
        "parity_execution_edge_revalidation_missing_evidence_rows": int(
            missing.sum()
        ),
        "parity_execution_edge_revalidation_consistency_violations": int(
            (
                relevant
                & consistency_violation
                & ~missing
            ).sum()
        ),
        "parity_execution_min_routed_net_edge": (
            float(routed_net_edges.min())
            if not routed_net_edges.empty
            else 0.0
        ),
        "parity_execution_max_observed_edge_decay": (
            max(float(observed_decay.max()), 0.0)
            if not observed_decay.empty
            else 0.0
        ),
    }


def _numeric_guard_column(
    guard: pd.DataFrame,
    column: str,
) -> pd.Series:
    return pd.to_numeric(
        guard.get(
            column,
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )


def _build_instruments(
    *,
    chain: pd.DataFrame,
    futures: pd.DataFrame,
    lot_size: int,
    option_tick: float,
    future_tick: float,
    option_costs: IndianCostModel,
    future_costs: IndianCostModel,
    max_position_lots: int,
) -> tuple[dict[str, InstrumentConfig], ParityLegMap]:
    instruments: dict[str, InstrumentConfig] = {}
    call_by_strike: dict[float, str] = {}
    put_by_strike: dict[float, str] = {}
    for strike, group in chain.groupby("strike", sort=True):
        strike_float = float(strike)
        strike_label = _strike_label(strike_float)
        call_id = f"CALL_{strike_label}"
        put_id = f"PUT_{strike_label}"
        call_by_strike[strike_float] = call_id
        put_by_strike[strike_float] = put_id
        instruments[call_id] = InstrumentConfig(
            Instrument(call_id, Kind.OPT, lot_size=lot_size, tick=option_tick),
            "NSE",
            _option_side_book(group, "call"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
        instruments[put_id] = InstrumentConfig(
            Instrument(put_id, Kind.OPT, lot_size=lot_size, tick=option_tick),
            "NSE",
            _option_side_book(group, "put"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
    instruments["FUT"] = InstrumentConfig(
        Instrument("FUT", Kind.FUT, lot_size=lot_size, tick=future_tick),
        "NSE",
        futures,
        costs=future_costs,
        max_position_lots=max_position_lots,
    )
    return instruments, ParityLegMap("FUT", call_by_strike, put_by_strike)


def _option_side_book(group: pd.DataFrame, side: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": group["ts"].to_numpy(),
            "bid": group[f"{side}_bid"].to_numpy(),
            "ask": group[f"{side}_ask"].to_numpy(),
            "bid_qty": group[f"{side}_bid_qty"].to_numpy(),
            "ask_qty": group[f"{side}_ask_qty"].to_numpy(),
            "last": np.nan,
            "last_qty": 0,
        }
    )


def _strike_label(strike: float) -> str:
    return str(strike).replace(".", "_")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay executable parity scanner signals.")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--futures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--asof-latency-ns", type=int, default=0)
    parser.add_argument(
        "--max-futures-quote-age-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument("--depth-fraction", type=float, default=0.25)
    parser.add_argument("--feed-latency-us", type=float, default=0.0)
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    parser.add_argument("--max-signal-age-ns", type=int, default=1_000_000)
    parser.add_argument(
        "--max-leg-book-age-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument(
        "--max-leg-book-skew-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument("--max-qty", type=int, default=None)
    parser.add_argument("--signal-limit", type=int, default=None)
    args = parser.parse_args(argv)
    replay = run_parity_replay(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        asof_latency_ns=args.asof_latency_ns,
        max_futures_quote_age_ns=args.max_futures_quote_age_ns,
        depth_fraction=args.depth_fraction,
        feed_latency_us=args.feed_latency_us,
        order_latency_us=args.order_latency_us,
        max_signal_age_ns=args.max_signal_age_ns,
        max_leg_book_age_ns=args.max_leg_book_age_ns,
        max_leg_book_skew_ns=args.max_leg_book_skew_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
    )
    print(replay.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
