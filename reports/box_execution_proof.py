from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from numbers import Integral
from pathlib import Path
from typing import Any

import pandas as pd


BOX_LEGS = (
    "low_call",
    "low_put",
    "high_call",
    "high_put",
)

_EXPECTED_SIDES = {
    "buy_box": {
        "low_call": 1,
        "low_put": -1,
        "high_call": -1,
        "high_put": 1,
    },
    "sell_box": {
        "low_call": -1,
        "low_put": 1,
        "high_call": 1,
        "high_put": -1,
    },
}


def box_execution_metrics(
    run_dir: Path,
    summary: pd.Series,
    manifest: Mapping[str, Any],
) -> dict[str, int | float | bool]:
    run_detected = (
        str(manifest.get("run_type", "")).strip().lower()
        == "box_replay"
    )
    paths = {
        "signals": run_dir / "signals.csv",
        "guard": run_dir / "box_execution_guard.csv",
        "legging": run_dir / "legging.csv",
        "fills": run_dir / "fills.csv",
        "submissions": run_dir / "order_submissions.csv",
        "arrivals": run_dir / "ioc_arrival_audit.csv",
        "deliveries": run_dir / "feed_deliveries.csv",
    }
    guard_declared = _bool(
        summary.get("box_execution_guard_enabled", False)
    )
    enabled = bool(
        run_detected
        or guard_declared
        or paths["guard"].exists()
    )
    parameters = _mapping(manifest.get("parameters"))
    signals = _read_optional(paths["signals"])
    guard = _read_optional(paths["guard"])
    legging = _read_optional(paths["legging"])
    fills = _read_optional(paths["fills"])
    submissions = _read_optional(paths["submissions"])
    arrivals = _read_optional(paths["arrivals"])
    deliveries = _read_optional(paths["deliveries"])

    max_signal_age_ns = _parameter_int(
        parameters,
        "max_signal_age_ns",
    )
    max_book_age_ns = _parameter_int(
        parameters,
        "max_leg_book_age_ns",
    )
    max_book_skew_ns = _parameter_int(
        parameters,
        "max_leg_book_skew_ns",
    )
    fair_value_adjustment = _parameter_float(
        parameters,
        "fair_value_adjustment",
    )

    guard_metrics = _guard_metrics(
        guard,
        signals,
        max_signal_age_ns=max_signal_age_ns,
        max_book_age_ns=max_book_age_ns,
        max_book_skew_ns=max_book_skew_ns,
        fair_value_adjustment=fair_value_adjustment,
    )
    legging_metrics = _legging_metrics(
        legging,
        guard,
        fills,
        submissions,
        arrivals,
    )
    latency_metrics = _latency_metrics(
        deliveries,
        submissions,
        parameters=parameters,
    )
    return {
        "box_execution_run_detected": run_detected,
        "box_execution_guard_enabled": enabled,
        "box_execution_guard_declared": guard_declared,
        "box_execution_signal_source_causality_declared": _bool(
            summary.get(
                "box_execution_signal_source_causality_enabled",
                False,
            )
        ),
        "box_execution_edge_revalidation_declared": _bool(
            summary.get(
                "box_execution_edge_revalidation_enabled",
                False,
            )
        ),
        "box_execution_ioc_batch_preflight_declared": _bool(
            summary.get(
                "box_execution_ioc_batch_preflight_enabled",
                False,
            )
        ),
        "box_execution_realized_edge_declared": _bool(
            summary.get(
                "box_execution_realized_edge_enabled",
                False,
            )
        ),
        "box_execution_order_timing_declared": _bool(
            summary.get(
                "box_execution_order_timing_enabled",
                False,
            )
        ),
        "box_execution_ioc_arrival_audit_declared": _bool(
            summary.get(
                "box_execution_ioc_arrival_audit_enabled",
                False,
            )
        ),
        "box_latency_sampling_declared": _bool(
            summary.get(
                "box_latency_sampling_audit_enabled",
                False,
            )
        ),
        "box_execution_signals_present": paths["signals"].exists(),
        "box_execution_guard_present": paths["guard"].exists(),
        "box_execution_legging_present": paths["legging"].exists(),
        "box_execution_fills_present": paths["fills"].exists(),
        "box_execution_order_submissions_present": (
            paths["submissions"].exists()
        ),
        "box_execution_ioc_arrival_audit_present": (
            paths["arrivals"].exists()
        ),
        "box_latency_feed_deliveries_present": (
            paths["deliveries"].exists()
        ),
        "box_execution_signal_count": int(len(signals)),
        "box_execution_max_signal_age_ns": max_signal_age_ns,
        "box_execution_max_leg_book_age_ns": max_book_age_ns,
        "box_execution_max_leg_book_skew_ns": max_book_skew_ns,
        **guard_metrics,
        **legging_metrics,
        **latency_metrics,
    }


def box_execution_checks(
    metrics: Mapping[str, int | float | bool | str],
) -> list[dict[str, int | float | bool | str]]:
    if not bool(metrics["box_execution_guard_enabled"]):
        return []

    run = str(metrics["run"])
    rows: list[dict[str, int | float | bool | str]] = []
    for metric, reason in [
        (
            "box_execution_run_detected",
            "box execution evidence is not bound to a box_replay manifest",
        ),
        (
            "box_execution_guard_declared",
            "box execution guard is not declared by summary.csv",
        ),
        (
            "box_execution_signal_source_causality_declared",
            "box replay lacks the causal source-book declaration",
        ),
        (
            "box_execution_edge_revalidation_declared",
            "box replay lacks decision-time edge revalidation",
        ),
        (
            "box_execution_ioc_batch_preflight_declared",
            "box replay lacks four-leg IOC preflight declaration",
        ),
        (
            "box_execution_realized_edge_declared",
            "box replay lacks realized fill-edge declaration",
        ),
        (
            "box_execution_order_timing_declared",
            "box replay lacks engine-owned order timing declaration",
        ),
        (
            "box_execution_ioc_arrival_audit_declared",
            "box replay lacks IOC arrival-book declaration",
        ),
        (
            "box_latency_sampling_declared",
            "box replay lacks sampled-latency declaration",
        ),
        (
            "box_execution_signals_present",
            "box signals artifact is missing",
        ),
        (
            "box_execution_guard_present",
            "box execution guard artifact is missing",
        ),
        (
            "box_execution_legging_present",
            "box legging artifact is missing",
        ),
        (
            "box_execution_fills_present",
            "box raw fills artifact is missing",
        ),
        (
            "box_execution_order_submissions_present",
            "box order-submission artifact is missing",
        ),
        (
            "box_execution_ioc_arrival_audit_present",
            "box IOC arrival-audit artifact is missing",
        ),
        (
            "box_latency_feed_deliveries_present",
            "box feed-delivery artifact is missing",
        ),
    ]:
        rows.append(
            _boolean_check(
                run,
                metric,
                bool(metrics[metric]),
                reason,
            )
        )

    for metric in [
        "box_execution_max_signal_age_ns",
        "box_execution_max_leg_book_age_ns",
        "box_execution_max_leg_book_skew_ns",
    ]:
        rows.append(
            _numeric_check(
                run,
                metric,
                int(metrics[metric]),
                ">=",
                0,
                "box execution age/skew configuration is invalid",
            )
        )

    signal_count = int(metrics["box_execution_signal_count"])
    guard_rows = int(metrics["box_execution_guard_rows"])
    rows.append(
        _numeric_check(
            run,
            "box_execution_guard_rows",
            guard_rows,
            ">=",
            1 if signal_count > 0 else 0,
            "box signals have no execution-guard evidence",
        )
    )
    for metric, reason in [
        (
            "box_execution_guard_missing_evidence_rows",
            "box guard rows lack required four-leg evidence",
        ),
        (
            "box_execution_guard_consistency_violations",
            "box guard identity, age, or routing evidence is inconsistent",
        ),
        (
            "box_execution_signal_source_consistency_violations",
            "box causal source-book evidence is inconsistent",
        ),
        (
            "box_execution_edge_revalidation_consistency_violations",
            "box decision-time edge or cost evidence is inconsistent",
        ),
        (
            "box_execution_ioc_batch_preflight_consistency_violations",
            "box IOC package preflight evidence is inconsistent",
        ),
        (
            "box_execution_guard_passed_missing_age_rows",
            "passed box guards lack four-leg age/skew evidence",
        ),
        (
            "box_execution_guard_age_violations",
            "passed box guards exceed configured book age",
        ),
        (
            "box_execution_guard_skew_violations",
            "passed box guards exceed configured book skew",
        ),
        (
            "box_execution_routing_incomplete_attempts",
            "a passed box guard routed fewer than four legs",
        ),
        (
            "box_execution_legging_missing_evidence_rows",
            "box legging rows lack required completion evidence",
        ),
        (
            "box_execution_legging_consistency_violations",
            "box legging identity or completion evidence is inconsistent",
        ),
        (
            "box_execution_guard_execution_lineage_violations",
            "passed guards and four-leg executions are not one-to-one",
        ),
        (
            "box_execution_incomplete_count",
            "box packages have incomplete routing or fills",
        ),
        (
            "box_execution_route_rejected_legs",
            "box legs were rejected before routing",
        ),
        (
            "box_execution_unfilled_legs",
            "box legs did not fill completely",
        ),
        (
            "box_execution_fill_evidence_missing_legs",
            "box legs lack raw fill evidence",
        ),
        (
            "box_execution_fill_evidence_consistency_violations",
            "box raw fills disagree with package evidence",
        ),
        (
            "box_execution_order_timing_missing_evidence_legs",
            "box legs lack accepted-order timing evidence",
        ),
        (
            "box_execution_order_timing_duplicate_evidence_legs",
            "box legs map to duplicate accepted-order evidence",
        ),
        (
            "box_execution_order_timing_consistency_violations",
            "box accepted-order timing evidence is inconsistent",
        ),
        (
            "box_execution_ioc_arrival_missing_evidence_legs",
            "box legs lack arrival-time IOC book evidence",
        ),
        (
            "box_execution_ioc_arrival_duplicate_evidence_legs",
            "box legs map to duplicate IOC arrival evidence",
        ),
        (
            "box_execution_ioc_arrival_consistency_violations",
            "box IOC arrival, depth, and fill evidence is inconsistent",
        ),
        (
            "box_execution_realized_edge_missing_rows",
            "completed box packages lack realized edge evidence",
        ),
        (
            "box_execution_realized_edge_consistency_violations",
            "box realized edge does not reconcile to raw fills and costs",
        ),
        (
            "box_execution_realized_edge_nonpositive_count",
            "a completed box package realized no positive net edge",
        ),
        (
            "box_latency_configuration_violations",
            "box latency base, jitter, or seed configuration is invalid",
        ),
        (
            "box_feed_latency_missing_rows",
            "box feed deliveries lack sampled latency",
        ),
        (
            "box_feed_latency_consistency_violations",
            "box feed timestamps disagree with sampled latency",
        ),
        (
            "box_feed_latency_bound_violations",
            "box feed latency falls outside manifest bounds",
        ),
        (
            "box_order_latency_missing_rows",
            "box submissions lack sampled latency",
        ),
        (
            "box_order_latency_consistency_violations",
            "box activation timestamps disagree with sampled latency",
        ),
        (
            "box_order_latency_bound_violations",
            "box order latency falls outside manifest bounds",
        ),
    ]:
        rows.append(
            _numeric_check(
                run,
                metric,
                int(metrics[metric]),
                "==",
                0,
                reason,
            )
        )

    passed_guards = int(
        metrics["box_execution_guard_passed_attempts"]
    )
    complete = int(metrics["box_execution_complete_count"])
    rows.append(
        _numeric_check(
            run,
            "box_execution_complete_count",
            complete,
            "==",
            passed_guards,
            "passed box guards are not fully represented by executions",
        )
    )
    expected_legs = complete * len(BOX_LEGS)
    for metric, reason in [
        (
            "box_execution_fill_evidence_evaluable_legs",
            "completed box packages lack four-leg raw fill evidence",
        ),
        (
            "box_execution_order_timing_evaluable_legs",
            "completed box packages lack four-leg order timing evidence",
        ),
        (
            "box_execution_ioc_arrival_evaluable_legs",
            "completed box packages lack four-leg IOC arrival evidence",
        ),
    ]:
        rows.append(
            _numeric_check(
                run,
                metric,
                int(metrics[metric]),
                ">=",
                expected_legs,
                reason,
            )
        )
    realized = int(
        metrics["box_execution_realized_edge_evaluable_count"]
    )
    rows.append(
        _numeric_check(
            run,
            "box_execution_realized_edge_evaluable_count",
            realized,
            "==",
            complete,
            "completed box packages are not bound to realized edge",
        )
    )
    minimum_edge = float(
        metrics["box_execution_min_realized_net_edge"]
    )
    rows.append(
        _numeric_check(
            run,
            "box_execution_min_realized_net_edge",
            minimum_edge,
            ">",
            0.0,
            "a completed box package has nonpositive realized net edge",
            vacuous=realized == 0,
        )
    )
    feed_samples = int(metrics["box_feed_latency_samples"])
    rows.append(
        _numeric_check(
            run,
            "box_feed_latency_samples",
            feed_samples,
            ">=",
            1,
            "box replay contains no sampled feed latency",
        )
    )
    order_samples = int(metrics["box_order_latency_samples"])
    rows.append(
        _numeric_check(
            run,
            "box_order_latency_samples",
            order_samples,
            ">=",
            expected_legs,
            "completed box packages lack sampled order latency",
        )
    )
    return rows


def _guard_metrics(
    guard: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    max_signal_age_ns: int,
    max_book_age_ns: int,
    max_book_skew_ns: int,
    fair_value_adjustment: float,
) -> dict[str, int | float]:
    missing_rows = 0
    consistency_violations = 0
    source_violations = 0
    edge_violations = 0
    preflight_violations = 0
    passed_missing_age_rows = 0
    age_violations = 0
    skew_violations = 0
    routing_incomplete = 0
    passed_count = 0
    max_routed_age = 0
    max_routed_skew = 0

    for _, row in guard.iterrows():
        passed = _bool(row.get("guard_passed", False))
        passed_count += int(passed)
        direction = _text(row.get("direction"))
        reason = _text(row.get("guard_reason"))
        signal_index = _integer(row.get("signal_index"))
        signal_ts = _integer(row.get("signal_ts_ns"))
        decision_ts = _integer(row.get("decision_ts_ns"))
        signal_age = _integer(row.get("signal_age_ns"))
        low_strike = _number(row.get("low_strike"))
        high_strike = _number(row.get("high_strike"))
        expiry = _text(row.get("expiry"))
        core_missing = (
            signal_index is None
            or signal_ts is None
            or decision_ts is None
            or signal_age is None
            or not _finite(low_strike)
            or not _finite(high_strike)
            or not expiry
            or direction not in _EXPECTED_SIDES
            or not reason
        )
        missing_rows += int(core_missing)
        if not core_missing:
            inconsistent = (
                high_strike <= low_strike
                or signal_age != decision_ts - signal_ts
                or signal_age < 0
                or signal_age > max_signal_age_ns
                or (passed and reason != "ready")
                or (not passed and reason == "ready")
                or not _signal_matches(
                    signals,
                    signal_index=signal_index,
                    direction=direction,
                    expiry=expiry,
                    low_strike=low_strike,
                    high_strike=high_strike,
                    signal_ts=signal_ts,
                )
            )
            consistency_violations += int(inconsistent)
        if not passed:
            continue

        leg_ids = {
            leg: _text(row.get(f"{leg}_instrument_id"))
            for leg in BOX_LEGS
        }
        book_timestamps = {
            leg: _integer(row.get(f"{leg}_book_ts_ns"))
            for leg in BOX_LEGS
        }
        book_ages = {
            leg: _integer(row.get(f"{leg}_book_age_ns"))
            for leg in BOX_LEGS
        }
        ages_missing = any(
            value is None for value in book_ages.values()
        )
        timestamps_missing = any(
            value is None for value in book_timestamps.values()
        )
        skew = _integer(row.get("leg_book_skew_ns"))
        max_observed = _integer(
            row.get("max_observed_book_age_ns")
        )
        passed_missing_age_rows += int(
            ages_missing
            or timestamps_missing
            or skew is None
            or max_observed is None
        )
        if not ages_missing:
            observed_age = max(
                int(value) for value in book_ages.values()
            )
            max_routed_age = max(max_routed_age, observed_age)
            age_bad = any(
                int(value) < 0
                or int(value) > max_book_age_ns
                for value in book_ages.values()
            )
            age_violations += int(age_bad)
            if max_observed is not None:
                consistency_violations += int(
                    max_observed != observed_age
                )
        if not timestamps_missing:
            observed_skew = (
                max(int(value) for value in book_timestamps.values())
                - min(
                    int(value)
                    for value in book_timestamps.values()
                )
            )
            max_routed_skew = max(
                max_routed_skew,
                observed_skew,
            )
            skew_violations += int(
                observed_skew < 0
                or observed_skew > max_book_skew_ns
            )
            if skew is not None:
                consistency_violations += int(
                    skew != observed_skew
                )
        if (
            decision_ts is not None
            and not timestamps_missing
            and not ages_missing
        ):
            consistency_violations += int(
                any(
                    book_ages[leg]
                    != decision_ts - book_timestamps[leg]
                    for leg in BOX_LEGS
                )
            )
        consistency_violations += int(
            any(not value for value in leg_ids.values())
            or len(set(leg_ids.values())) != len(BOX_LEGS)
            or _integer(row.get("max_leg_book_age_ns"))
            != max_book_age_ns
            or _integer(row.get("max_leg_book_skew_ns"))
            != max_book_skew_ns
        )

        source_missing, source_bad = _guard_source_violation(
            row,
            signal_ts=signal_ts,
            book_timestamps=book_timestamps,
        )
        missing_rows += int(source_missing)
        source_violations += int(source_bad)
        edge_missing, edge_bad = _guard_edge_violation(
            row,
            direction=direction,
            low_strike=low_strike,
            high_strike=high_strike,
            fair_value_adjustment=fair_value_adjustment,
        )
        missing_rows += int(edge_missing)
        edge_violations += int(edge_bad)
        preflight_missing, preflight_bad = (
            _guard_preflight_violation(row)
        )
        missing_rows += int(preflight_missing)
        preflight_violations += int(preflight_bad)

        requested = _integer(row.get("orders_requested"))
        accepted = _integer(row.get("orders_accepted"))
        routing_complete = _bool(
            row.get("routing_complete", False)
        )
        routing_status = _text(row.get("routing_status"))
        routing_bad = (
            requested != len(BOX_LEGS)
            or accepted != len(BOX_LEGS)
            or not routing_complete
            or routing_status != "complete"
        )
        routing_incomplete += int(routing_bad)

    return {
        "box_execution_guard_rows": int(len(guard)),
        "box_execution_guard_passed_attempts": passed_count,
        "box_execution_guard_deferred_attempts": (
            int(len(guard)) - passed_count
        ),
        "box_execution_guard_missing_evidence_rows": missing_rows,
        "box_execution_guard_consistency_violations": (
            consistency_violations
        ),
        "box_execution_signal_source_consistency_violations": (
            source_violations
        ),
        "box_execution_edge_revalidation_consistency_violations": (
            edge_violations
        ),
        "box_execution_ioc_batch_preflight_consistency_violations": (
            preflight_violations
        ),
        "box_execution_guard_passed_missing_age_rows": (
            passed_missing_age_rows
        ),
        "box_execution_guard_age_violations": age_violations,
        "box_execution_guard_skew_violations": skew_violations,
        "box_execution_routing_incomplete_attempts": (
            routing_incomplete
        ),
        "box_execution_max_routed_book_age_ns": max_routed_age,
        "box_execution_max_routed_book_skew_ns": max_routed_skew,
    }


def _guard_source_violation(
    row: pd.Series,
    *,
    signal_ts: int | None,
    book_timestamps: Mapping[str, int | None],
) -> tuple[bool, bool]:
    lag = _integer(row.get("signal_source_max_lag_ns"))
    missing = (
        signal_ts is None
        or lag is None
        or any(
            value is None for value in book_timestamps.values()
        )
    )
    if missing:
        return True, False
    expected_lag = max(
        max(
            signal_ts - int(book_timestamps[leg]),
            0,
        )
        for leg in BOX_LEGS
    )
    bad = (
        not _bool(
            row.get("signal_source_causality_enabled", False)
        )
        or not _bool(
            row.get("signal_source_books_checked", False)
        )
        or not _bool(
            row.get("signal_source_books_ready", False)
        )
        or lag != expected_lag
        or lag != 0
    )
    return False, bad


def _guard_edge_violation(
    row: pd.Series,
    *,
    direction: str,
    low_strike: float,
    high_strike: float,
    fair_value_adjustment: float,
) -> tuple[bool, bool]:
    if (
        direction not in _EXPECTED_SIDES
        or not _finite(low_strike)
        or not _finite(high_strike)
    ):
        return True, False
    qty = _integer(row.get("edge_revalidation_qty"))
    multiplier = _number(
        row.get("decision_contract_multiplier")
    )
    fair_box = _number(row.get("decision_fair_box"))
    edge_per_unit = _number(
        row.get("decision_edge_per_unit")
    )
    gross_edge = _number(row.get("decision_gross_edge"))
    total_cost = _number(row.get("decision_total_cost"))
    net_edge = _number(row.get("decision_net_edge"))
    minimum_edge = _number(
        row.get("decision_min_net_edge")
    )
    prices = {
        leg: _number(row.get(f"decision_{leg}_price"))
        for leg in BOX_LEGS
    }
    costs = {
        leg: _number(row.get(f"decision_{leg}_cost"))
        for leg in BOX_LEGS
    }
    sides = {
        leg: _integer(row.get(f"decision_{leg}_side"))
        for leg in BOX_LEGS
    }
    missing = (
        qty is None
        or any(value is None for value in sides.values())
        or not all(_finite(value) for value in prices.values())
        or not all(_finite(value) for value in costs.values())
        or not all(
            _finite(value)
            for value in [
                multiplier,
                fair_box,
                edge_per_unit,
                gross_edge,
                total_cost,
                net_edge,
                minimum_edge,
            ]
        )
    )
    if missing:
        return True, False
    package_value = _box_value(prices)
    expected_fair_box = (
        high_strike
        - low_strike
        + fair_value_adjustment
    )
    expected_edge = (
        expected_fair_box - package_value
        if direction == "buy_box"
        else package_value - expected_fair_box
    )
    expected_cost = sum(float(value) for value in costs.values())
    expected_gross = expected_edge * qty * multiplier
    expected_net = expected_gross - expected_cost
    bad = (
        not _bool(row.get("edge_revalidation_enabled", False))
        or not _bool(row.get("edge_revalidation_checked", False))
        or not _bool(
            row.get("decision_multiplier_consistent", False)
        )
        or qty <= 0
        or multiplier <= 0
        or any(float(value) <= 0 for value in prices.values())
        or any(float(value) < 0 for value in costs.values())
        or sides != _EXPECTED_SIDES[direction]
        or not _close(fair_box, expected_fair_box)
        or not _close(edge_per_unit, expected_edge)
        or not _close(total_cost, expected_cost)
        or not _close(gross_edge, expected_gross)
        or not _close(net_edge, expected_net)
        or net_edge <= minimum_edge
        or minimum_edge < 0
    )
    return False, bad


def _guard_preflight_violation(
    row: pd.Series,
) -> tuple[bool, bool]:
    requested = _integer(
        row.get("ioc_batch_preflight_requested_qty")
    )
    available = _number(
        row.get("ioc_batch_preflight_available_qty")
    )
    ratio = _number(
        row.get(
            "ioc_batch_preflight_min_visible_fill_ratio"
        )
    )
    missing = (
        requested is None
        or not _finite(available)
        or not _finite(ratio)
    )
    if missing:
        return True, False
    bad = (
        not _bool(
            row.get("ioc_batch_preflight_enabled", False)
        )
        or not _bool(
            row.get("ioc_batch_preflight_attempted", False)
        )
        or not _bool(
            row.get("ioc_batch_preflight_passed", False)
        )
        or not _bool(
            row.get(
                "ioc_batch_preflight_visible_capacity_checked",
                False,
            )
        )
        or _text(
            row.get("ioc_batch_preflight_reason")
        )
        != "passed"
        or requested <= 0
        or available < requested
        or ratio < 1.0
    )
    return False, bad


def _legging_metrics(
    legging: pd.DataFrame,
    guard: pd.DataFrame,
    fills: pd.DataFrame,
    submissions: pd.DataFrame,
    arrivals: pd.DataFrame,
) -> dict[str, int | float]:
    missing_rows = 0
    consistency_violations = 0
    lineage_violations = 0
    incomplete = 0
    route_rejected = 0
    unfilled = 0
    fill_missing = 0
    fill_violations = 0
    fill_evaluable = 0
    timing_missing = 0
    timing_duplicates = 0
    timing_violations = 0
    timing_evaluable = 0
    arrival_missing = 0
    arrival_duplicates = 0
    arrival_violations = 0
    arrival_evaluable = 0
    realized_evaluable = 0
    realized_positive = 0
    realized_nonpositive = 0
    realized_missing = 0
    realized_violations = 0
    realized_edges: list[float] = []

    passed_guard = guard.loc[
        _bool_series(guard, "guard_passed")
    ].copy()
    guard_signal_indexes = _integer_series(
        passed_guard,
        "signal_index",
    )
    execution_signal_indexes = _integer_series(
        legging,
        "signal_index",
    )
    lineage_violations += _lineage_violations(
        guard_signal_indexes,
        execution_signal_indexes,
    )

    for _, row in legging.iterrows():
        signal_index = _integer(row.get("signal_index"))
        matching_guard = passed_guard.loc[
            guard_signal_indexes.eq(signal_index)
        ]
        if signal_index is None or len(matching_guard) != 1:
            lineage_violations += 1
            guard_row = None
        else:
            guard_row = matching_guard.iloc[0]

        direction = _text(row.get("direction"))
        requested_qty = _integer(row.get("requested_qty"))
        expected_orders = _integer(
            row.get("expected_order_count")
        )
        order_count = _integer(row.get("order_count"))
        fully_filled = _integer(
            row.get("fully_filled_leg_count")
        )
        route_rejection_count = _integer(
            row.get("route_rejection_count")
        )
        unfilled_count = _integer(
            row.get("unfilled_leg_count")
        )
        core_missing = (
            direction not in _EXPECTED_SIDES
            or requested_qty is None
            or expected_orders is None
            or order_count is None
            or fully_filled is None
            or route_rejection_count is None
            or unfilled_count is None
        )
        missing_rows += int(core_missing)
        row_incomplete = (
            core_missing
            or requested_qty <= 0
            or expected_orders != len(BOX_LEGS)
            or order_count != len(BOX_LEGS)
            or fully_filled != len(BOX_LEGS)
            or route_rejection_count != 0
            or unfilled_count != 0
            or not _bool(row.get("routing_complete", False))
            or not _bool(row.get("fills_complete", False))
            or _bool(row.get("partial", True))
        )
        incomplete += int(row_incomplete)
        route_rejected += max(route_rejection_count or 0, 0)
        unfilled += max(unfilled_count or 0, 0)
        if guard_row is not None:
            consistency_violations += int(
                not _execution_identity_matches_guard(
                    row,
                    guard_row,
                )
            )

        leg_fill_values: dict[str, float] = {}
        leg_fill_costs: dict[str, float] = {}
        order_ids: list[int] = []
        for leg in BOX_LEGS:
            oid = _integer(row.get(f"{leg}_order_id"))
            instrument_id = _text(
                row.get(f"{leg}_instrument_id")
            )
            side = _integer(row.get(f"{leg}_side"))
            limit_price = _number(
                row.get(f"{leg}_limit_price")
            )
            filled_qty = _integer(
                row.get(f"{leg}_filled_qty")
            )
            fill_vwap = _number(row.get(f"{leg}_fill_vwap"))
            fill_cost = _number(row.get(f"{leg}_fill_cost"))
            leg_missing = (
                direction not in _EXPECTED_SIDES
                or requested_qty is None
                or oid is None
                or not instrument_id
                or side is None
                or not _finite(limit_price)
                or filled_qty is None
                or not _finite(fill_vwap)
                or not _finite(fill_cost)
            )
            missing_rows += int(leg_missing)
            if leg_missing:
                continue
            order_ids.append(oid)
            leg_fill_values[leg] = fill_vwap
            leg_fill_costs[leg] = fill_cost
            consistency_violations += int(
                side != _EXPECTED_SIDES[direction][leg]
                or filled_qty != requested_qty
                or limit_price <= 0
                or fill_vwap <= 0
                or fill_cost < 0
            )

            raw_fill = _raw_fill_evidence(
                fills,
                oid=oid,
                instrument_id=instrument_id,
                side=side,
                expected_qty=requested_qty,
                expected_vwap=fill_vwap,
                expected_cost=fill_cost,
                row=row,
                leg=leg,
            )
            fill_missing += raw_fill["missing"]
            fill_violations += raw_fill["violations"]
            fill_evaluable += raw_fill["evaluable"]

            timing = _order_timing_evidence(
                submissions,
                oid=oid,
                instrument_id=instrument_id,
                side=side,
                qty=requested_qty,
                limit_price=limit_price,
                decision_ts=_integer(row.get("decision_ts_ns")),
            )
            timing_missing += timing["missing"]
            timing_duplicates += timing["duplicates"]
            timing_violations += timing["violations"]
            timing_evaluable += timing["evaluable"]

            arrival = _arrival_evidence(
                arrivals,
                oid=oid,
                instrument_id=instrument_id,
                side=side,
                qty=requested_qty,
                limit_price=limit_price,
                filled_qty=filled_qty,
            )
            arrival_missing += arrival["missing"]
            arrival_duplicates += arrival["duplicates"]
            arrival_violations += arrival["violations"]
            arrival_evaluable += arrival["evaluable"]

        consistency_violations += int(
            len(order_ids) != len(set(order_ids))
        )
        realized = _realized_edge_evidence(
            row,
            direction=direction,
            prices=leg_fill_values,
            costs=leg_fill_costs,
            qty=requested_qty,
        )
        realized_evaluable += realized["evaluable"]
        realized_positive += realized["positive"]
        realized_nonpositive += realized["nonpositive"]
        realized_missing += realized["missing"]
        realized_violations += realized["violations"]
        if realized["edge"] is not None:
            realized_edges.append(float(realized["edge"]))

    return {
        "box_execution_count": int(len(legging)),
        "box_execution_complete_count": int(len(legging) - incomplete),
        "box_execution_incomplete_count": incomplete,
        "box_execution_route_rejected_legs": route_rejected,
        "box_execution_unfilled_legs": unfilled,
        "box_execution_legging_missing_evidence_rows": missing_rows,
        "box_execution_legging_consistency_violations": (
            consistency_violations
        ),
        "box_execution_guard_execution_lineage_violations": (
            lineage_violations
        ),
        "box_execution_fill_evidence_evaluable_legs": (
            fill_evaluable
        ),
        "box_execution_fill_evidence_missing_legs": fill_missing,
        "box_execution_fill_evidence_consistency_violations": (
            fill_violations
        ),
        "box_execution_order_timing_evaluable_legs": (
            timing_evaluable
        ),
        "box_execution_order_timing_missing_evidence_legs": (
            timing_missing
        ),
        "box_execution_order_timing_duplicate_evidence_legs": (
            timing_duplicates
        ),
        "box_execution_order_timing_consistency_violations": (
            timing_violations
        ),
        "box_execution_ioc_arrival_evaluable_legs": (
            arrival_evaluable
        ),
        "box_execution_ioc_arrival_missing_evidence_legs": (
            arrival_missing
        ),
        "box_execution_ioc_arrival_duplicate_evidence_legs": (
            arrival_duplicates
        ),
        "box_execution_ioc_arrival_consistency_violations": (
            arrival_violations
        ),
        "box_execution_realized_edge_evaluable_count": (
            realized_evaluable
        ),
        "box_execution_realized_edge_positive_count": (
            realized_positive
        ),
        "box_execution_realized_edge_nonpositive_count": (
            realized_nonpositive
        ),
        "box_execution_realized_edge_missing_rows": realized_missing,
        "box_execution_realized_edge_consistency_violations": (
            realized_violations
        ),
        "box_execution_min_realized_net_edge": (
            min(realized_edges) if realized_edges else 0.0
        ),
        "box_execution_total_realized_net_edge": sum(
            realized_edges
        ),
    }


def _raw_fill_evidence(
    fills: pd.DataFrame,
    *,
    oid: int,
    instrument_id: str,
    side: int,
    expected_qty: int,
    expected_vwap: float,
    expected_cost: float,
    row: pd.Series,
    leg: str,
) -> dict[str, int]:
    matches = _match_oid(fills, oid)
    if matches.empty:
        return {"missing": 1, "violations": 0, "evaluable": 0}
    quantities = _numeric_series(matches, "qty")
    prices = _numeric_series(matches, "price")
    costs = _numeric_series(matches, "cost")
    timestamps = _numeric_series(matches, "ts_ns")
    missing = bool(
        quantities.isna().any()
        or prices.isna().any()
        or costs.isna().any()
        or timestamps.isna().any()
    )
    if missing:
        return {"missing": 1, "violations": 0, "evaluable": 0}
    qty = int(quantities.sum())
    vwap = float(
        (prices * quantities).sum() / qty
        if qty > 0
        else math.nan
    )
    cost = float(costs.sum())
    first_ts = _integer(row.get(f"{leg}_first_fill_ts_ns"))
    last_ts = _integer(row.get(f"{leg}_last_fill_ts_ns"))
    violation = (
        qty != expected_qty
        or not _close(vwap, expected_vwap)
        or not _close(cost, expected_cost)
        or first_ts != int(timestamps.min())
        or last_ts != int(timestamps.max())
        or not matches.get(
            "instrument_id",
            pd.Series("", index=matches.index),
        ).astype(str).eq(instrument_id).all()
        or not _numeric_series(matches, "side").eq(side).all()
    )
    return {
        "missing": 0,
        "violations": int(violation),
        "evaluable": 1,
    }


def _order_timing_evidence(
    submissions: pd.DataFrame,
    *,
    oid: int,
    instrument_id: str,
    side: int,
    qty: int,
    limit_price: float,
    decision_ts: int | None,
) -> dict[str, int]:
    matches = _match_oid(submissions, oid)
    if matches.empty:
        return {"missing": 1, "duplicates": 0, "violations": 0, "evaluable": 0}
    if len(matches) != 1:
        return {"missing": 0, "duplicates": 1, "violations": 0, "evaluable": 0}
    row = matches.iloc[0]
    sent = _integer(row.get("ts_sent_ns"))
    active = _integer(row.get("ts_active_ns"))
    latency = _integer(row.get("order_latency_ns"))
    observed_side = _integer(row.get("side"))
    observed_qty = _integer(row.get("qty"))
    observed_price = _number(row.get("price"))
    missing = (
        decision_ts is None
        or sent is None
        or active is None
        or latency is None
        or observed_side is None
        or observed_qty is None
        or not _finite(observed_price)
    )
    if missing:
        return {"missing": 1, "duplicates": 0, "violations": 0, "evaluable": 0}
    violation = (
        sent != decision_ts
        or active < sent
        or latency < 0
        or active - sent != latency
        or _text(row.get("instrument_id")) != instrument_id
        or observed_side != side
        or observed_qty != qty
        or not _close(observed_price, limit_price)
        or _text(row.get("order_type")) != "IOC"
    )
    return {
        "missing": 0,
        "duplicates": 0,
        "violations": int(violation),
        "evaluable": 1,
    }


def _arrival_evidence(
    arrivals: pd.DataFrame,
    *,
    oid: int,
    instrument_id: str,
    side: int,
    qty: int,
    limit_price: float,
    filled_qty: int,
) -> dict[str, int]:
    matches = _match_oid(arrivals, oid)
    if matches.empty:
        return {"missing": 1, "duplicates": 0, "violations": 0, "evaluable": 0}
    if len(matches) != 1:
        return {"missing": 0, "duplicates": 1, "violations": 0, "evaluable": 0}
    row = matches.iloc[0]
    requested = _integer(row.get("requested_qty"))
    observed_fill = _integer(row.get("filled_qty"))
    available = _number(row.get("available_qty"))
    sent = _integer(row.get("ts_sent_ns"))
    active = _integer(row.get("ts_active_ns"))
    arrival = _integer(row.get("arrival_ts_ns"))
    arrival_lag = _integer(row.get("arrival_lag_ns"))
    missing = (
        requested is None
        or observed_fill is None
        or not _finite(available)
        or sent is None
        or active is None
        or arrival is None
        or arrival_lag is None
    )
    if missing:
        return {"missing": 1, "duplicates": 0, "violations": 0, "evaluable": 0}
    violation = (
        _text(row.get("instrument_id")) != instrument_id
        or _integer(row.get("side")) != side
        or _text(row.get("order_type")) != "IOC"
        or not _close(_number(row.get("limit_price")), limit_price)
        or requested != qty
        or observed_fill != filled_qty
        or available < qty
        or sent > active
        or arrival < active
        or arrival_lag != arrival - active
        or arrival_lag < 0
        or not _bool(row.get("marketable", False))
        or not _bool(row.get("complete", False))
    )
    return {
        "missing": 0,
        "duplicates": 0,
        "violations": int(violation),
        "evaluable": 1,
    }


def _realized_edge_evidence(
    row: pd.Series,
    *,
    direction: str,
    prices: Mapping[str, float],
    costs: Mapping[str, float],
    qty: int | None,
) -> dict[str, int | float | None]:
    multiplier = _number(row.get("contract_multiplier"))
    fair_box = _number(row.get("fair_box"))
    edge_per_unit = _number(
        row.get("realized_edge_per_unit")
    )
    gross_edge = _number(row.get("realized_gross_edge"))
    total_cost = _number(row.get("realized_total_cost"))
    net_edge = _number(row.get("realized_net_edge"))
    missing = (
        direction not in _EXPECTED_SIDES
        or qty is None
        or len(prices) != len(BOX_LEGS)
        or len(costs) != len(BOX_LEGS)
        or not all(
            _finite(value)
            for value in [
                multiplier,
                fair_box,
                edge_per_unit,
                gross_edge,
                total_cost,
                net_edge,
            ]
        )
    )
    if missing:
        return {
            "evaluable": 0,
            "positive": 0,
            "nonpositive": 0,
            "missing": 1,
            "violations": 0,
            "edge": None,
        }
    package_value = _box_value(prices)
    expected_edge = (
        fair_box - package_value
        if direction == "buy_box"
        else package_value - fair_box
    )
    expected_cost = sum(costs.values())
    expected_gross = expected_edge * qty * multiplier
    expected_net = expected_gross - expected_cost
    positive = expected_net > 0
    violation = (
        not _bool(
            row.get("realized_edge_evidence_enabled", False)
        )
        or not _bool(row.get("realized_edge_evaluable", False))
        or _bool(row.get("realized_edge_positive", False))
        != positive
        or qty <= 0
        or multiplier <= 0
        or not _close(edge_per_unit, expected_edge)
        or not _close(total_cost, expected_cost)
        or not _close(gross_edge, expected_gross)
        or not _close(net_edge, expected_net)
    )
    return {
        "evaluable": 1,
        "positive": int(positive),
        "nonpositive": int(not positive),
        "missing": 0,
        "violations": int(violation),
        "edge": expected_net,
    }


def _latency_metrics(
    deliveries: pd.DataFrame,
    submissions: pd.DataFrame,
    *,
    parameters: Mapping[str, Any],
) -> dict[str, int | float | bool]:
    feed_base = _parameter_float(parameters, "feed_latency_us")
    order_base = _parameter_float(
        parameters,
        "order_latency_us",
    )
    jitter = _parameter_float(
        parameters,
        "latency_jitter_us",
    )
    seed = _parameter_int(parameters, "latency_seed")
    configuration_violations = int(
        not _finite(feed_base)
        or not _finite(order_base)
        or not _finite(jitter)
        or feed_base < 0
        or order_base < 0
        or jitter < 0
        or seed < 0
    )
    feed_min, feed_max = _latency_bounds(feed_base, jitter)
    order_min, order_max = _latency_bounds(
        order_base,
        jitter,
    )
    feed = _sampled_latency(
        deliveries,
        latency_column="feed_latency_ns",
        start_column="market_ts_ns",
        end_column="strategy_ts_ns",
        minimum=feed_min,
        maximum=feed_max,
    )
    order = _sampled_latency(
        submissions,
        latency_column="order_latency_ns",
        start_column="ts_sent_ns",
        end_column="ts_active_ns",
        minimum=order_min,
        maximum=order_max,
    )
    return {
        "box_latency_sampling_enabled": True,
        "box_latency_configuration_violations": (
            configuration_violations
        ),
        "box_latency_seed": seed,
        "box_expected_min_feed_latency_ns": feed_min,
        "box_expected_max_feed_latency_ns": feed_max,
        "box_feed_latency_samples": feed["samples"],
        "box_feed_latency_missing_rows": feed["missing"],
        "box_feed_latency_consistency_violations": (
            feed["consistency"]
        ),
        "box_feed_latency_bound_violations": feed["bounds"],
        "box_expected_min_order_latency_ns": order_min,
        "box_expected_max_order_latency_ns": order_max,
        "box_order_latency_samples": order["samples"],
        "box_order_latency_missing_rows": order["missing"],
        "box_order_latency_consistency_violations": (
            order["consistency"]
        ),
        "box_order_latency_bound_violations": order["bounds"],
    }


def _sampled_latency(
    frame: pd.DataFrame,
    *,
    latency_column: str,
    start_column: str,
    end_column: str,
    minimum: int,
    maximum: int,
) -> dict[str, int]:
    latency = _numeric_series(frame, latency_column)
    start = _numeric_series(frame, start_column)
    end = _numeric_series(frame, end_column)
    missing = latency.isna() | start.isna() | end.isna()
    integral = latency.mod(1).eq(0)
    consistency = (
        ~missing
        & (
            ~integral
            | latency.lt(0)
            | end.sub(start).ne(latency)
        )
    )
    bounds = (
        ~missing
        & (
            ~integral
            | latency.lt(minimum)
            | latency.gt(maximum)
        )
    )
    return {
        "samples": int(len(frame)),
        "missing": int(missing.sum()),
        "consistency": int(consistency.sum()),
        "bounds": int(bounds.sum()),
    }


def _execution_identity_matches_guard(
    execution: pd.Series,
    guard: pd.Series,
) -> bool:
    text_columns = [
        "direction",
        "expiry",
        *[
            f"{leg}_instrument_id"
            for leg in BOX_LEGS
        ],
    ]
    if any(
        _text(execution.get(column))
        != _text(guard.get(column))
        for column in text_columns
    ):
        return False
    shared_integer_columns = [
        "signal_index",
        "signal_ts_ns",
        "decision_ts_ns",
        "signal_age_ns",
    ]
    if any(
        _integer(execution.get(column))
        != _integer(guard.get(column))
        for column in shared_integer_columns
    ):
        return False
    shared_numeric_columns = [
        "low_strike",
        "high_strike",
    ]
    if not all(
        _close(
            _number(execution.get(column)),
            _number(guard.get(column)),
        )
        for column in shared_numeric_columns
    ):
        return False
    return all(
        _close(
            _number(execution.get(f"{leg}_side")),
            _number(guard.get(f"decision_{leg}_side")),
        )
        and _close(
            _number(
                execution.get(f"{leg}_limit_price")
            ),
            _number(
                guard.get(f"decision_{leg}_price")
            ),
        )
        for leg in BOX_LEGS
    )


def _signal_matches(
    signals: pd.DataFrame,
    *,
    signal_index: int,
    direction: str,
    expiry: str,
    low_strike: float,
    high_strike: float,
    signal_ts: int,
) -> bool:
    if signal_index < 0 or signal_index >= len(signals):
        return False
    row = signals.iloc[signal_index]
    return bool(
        _text(row.get("direction")) == direction
        and _text(row.get("expiry")) == expiry
        and _close(_number(row.get("low_strike")), low_strike)
        and _close(_number(row.get("high_strike")), high_strike)
        and _integer(row.get("ts")) == signal_ts
    )


def _lineage_violations(
    guards: pd.Series,
    executions: pd.Series,
) -> int:
    guard_values = guards.dropna().astype(int)
    execution_values = executions.dropna().astype(int)
    guard_counts = guard_values.value_counts()
    execution_counts = execution_values.value_counts()
    keys = set(guard_counts.index) | set(execution_counts.index)
    missing_values = (
        int(guards.isna().sum())
        + int(executions.isna().sum())
    )
    return missing_values + sum(
        abs(
            int(guard_counts.get(key, 0))
            - int(execution_counts.get(key, 0))
        )
        for key in keys
    )


def _match_oid(frame: pd.DataFrame, oid: int) -> pd.DataFrame:
    if "oid" not in frame.columns:
        return frame.iloc[0:0]
    return frame.loc[
        pd.to_numeric(frame["oid"], errors="coerce").eq(oid)
    ]


def _box_value(prices: Mapping[str, float]) -> float:
    return float(
        prices["low_call"]
        - prices["low_put"]
        - prices["high_call"]
        + prices["high_put"]
    )


def _latency_bounds(
    base_us: float,
    jitter_us: float,
) -> tuple[int, int]:
    if not _finite(base_us) or not _finite(jitter_us):
        return 0, 0
    return (
        int(max(base_us - jitter_us, 0.0) * 1_000),
        int((base_us + jitter_us) * 1_000),
    )


def _boolean_check(
    run: str,
    metric: str,
    value: bool,
    reason: str,
) -> dict[str, int | float | bool | str]:
    return {
        "run": run,
        "check": metric,
        "value": value,
        "operator": "is",
        "threshold": True,
        "passed": value,
        "reason": "" if value else reason,
    }


def _numeric_check(
    run: str,
    metric: str,
    value: int | float,
    operator: str,
    threshold: int | float,
    reason: str,
    *,
    vacuous: bool = False,
) -> dict[str, int | float | bool | str]:
    if vacuous:
        passed = True
    elif operator == "==":
        passed = value == threshold
    elif operator == ">=":
        passed = value >= threshold
    elif operator == ">":
        passed = value > threshold
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    return {
        "run": run,
        "check": metric,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": passed,
        "reason": "" if passed else reason,
    }


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parameter_float(
    parameters: Mapping[str, Any],
    name: str,
) -> float:
    return _number(parameters.get(name))


def _parameter_int(
    parameters: Mapping[str, Any],
    name: str,
) -> int:
    value = _integer(parameters.get(name))
    return value if value is not None else -1


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _integer(value: Any) -> int | None:
    if isinstance(value, Integral):
        return int(value)
    if value is None or pd.isna(value):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return int(number)


def _finite(value: Any) -> bool:
    return math.isfinite(_number(value))


def _close(left: Any, right: Any) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    return bool(
        math.isfinite(left_number)
        and math.isfinite(right_number)
        and math.isclose(
            left_number,
            right_number,
            rel_tol=1e-9,
            abs_tol=1e-7,
        )
    )


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }
    if value is None or pd.isna(value):
        return False
    return bool(value)


def _bool_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return frame[column].map(_bool).astype(bool)


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            math.nan,
            index=frame.index,
            dtype="float64",
        )
    return pd.to_numeric(frame[column], errors="coerce")


def _integer_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    values = _numeric_series(frame, column)
    return values.where(values.mod(1).eq(0))
