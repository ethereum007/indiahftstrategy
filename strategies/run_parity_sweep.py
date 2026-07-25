from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_parity_replay import run_parity_replay


@dataclass(frozen=True)
class ParitySweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    output_dir: Path | None = None


def run_parity_sweep(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path,
    depth_fraction_values: list[float],
    asof_latency_ns_values: list[int],
    feed_latency_us_values: list[float],
    order_latency_us_values: list[float],
    latency_jitter_us_values: list[float] | None = None,
    latency_seed: int = 17,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    future_tick: float = 0.05,
    max_futures_quote_age_ns: int = 1_000_000,
    max_signal_age_ns: int = 1_000_000,
    max_leg_book_age_ns: int = 1_000_000,
    max_leg_book_skew_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
    proof_thresholds: ProofThresholds | None = None,
) -> ParitySweepResult:
    if not depth_fraction_values:
        raise ValueError("depth_fraction_values must not be empty")
    if not asof_latency_ns_values:
        raise ValueError("asof_latency_ns_values must not be empty")
    if not feed_latency_us_values:
        raise ValueError("feed_latency_us_values must not be empty")
    if not order_latency_us_values:
        raise ValueError("order_latency_us_values must not be empty")
    latency_jitter_us_values = (
        [0.0]
        if latency_jitter_us_values is None
        else list(latency_jitter_us_values)
    )
    if not latency_jitter_us_values:
        raise ValueError("latency_jitter_us_values must not be empty")

    out = Path(output_dir)
    runs_root = out / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    rows = []
    run_dirs: list[Path] = []
    run_names: list[str] = []
    for (
        depth_fraction,
        asof_latency_ns,
        feed_latency_us,
        order_latency_us,
        latency_jitter_us,
    ) in product(
        depth_fraction_values,
        asof_latency_ns_values,
        feed_latency_us_values,
        order_latency_us_values,
        latency_jitter_us_values,
    ):
        run_name = _run_name(
            depth_fraction,
            asof_latency_ns,
            feed_latency_us,
            order_latency_us,
            latency_jitter_us,
        )
        run_dir = runs_root / run_name
        replay = run_parity_replay(
            chain_path=chain_path,
            futures_path=futures_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            lot_size=lot_size,
            option_tick=option_tick,
            future_tick=future_tick,
            asof_latency_ns=asof_latency_ns,
            max_futures_quote_age_ns=max_futures_quote_age_ns,
            depth_fraction=depth_fraction,
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
            latency_jitter_us=latency_jitter_us,
            latency_seed=latency_seed,
            max_signal_age_ns=max_signal_age_ns,
            max_leg_book_age_ns=max_leg_book_age_ns,
            max_leg_book_skew_ns=max_leg_book_skew_ns,
            max_qty=max_qty,
            max_position_lots=max_position_lots,
            signal_limit=signal_limit,
        )
        summary = replay.summary.iloc[0].to_dict()
        legging = _legging_metrics(replay.legging)
        rows.append(
            {
                "run": run_name,
                "run_dir": str(run_dir),
                "depth_fraction": float(depth_fraction),
                "asof_latency_ns": int(asof_latency_ns),
                "feed_latency_us": float(feed_latency_us),
                "order_latency_us": float(order_latency_us),
                "latency_jitter_us": float(latency_jitter_us),
                "latency_seed": int(latency_seed),
                "signal_count": int(len(replay.signals)),
                **legging,
                **summary,
            }
        )
        run_dirs.append(run_dir)
        run_names.append(run_name)

    proof = write_proof_report(
        run_dirs,
        output_dir=out / "proof",
        thresholds=proof_thresholds or ProofThresholds(),
        run_names=run_names,
    )
    runs = _merge_proof_metrics(pd.DataFrame(rows), proof)
    summary = _sweep_summary(runs)
    runs.to_csv(out / "sweep_runs.csv", index=False)
    summary.to_csv(out / "sweep_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="parity_sweep",
        inputs={"chain": chain_path, "futures": futures_path},
        parameters={
            "depth_fraction_values": depth_fraction_values,
            "asof_latency_ns_values": asof_latency_ns_values,
            "feed_latency_us_values": feed_latency_us_values,
            "order_latency_us_values": order_latency_us_values,
            "latency_jitter_us_values": latency_jitter_us_values,
            "latency_seed": latency_seed,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "lot_size": lot_size,
            "option_tick": option_tick,
            "future_tick": future_tick,
            "max_futures_quote_age_ns": max_futures_quote_age_ns,
            "max_signal_age_ns": max_signal_age_ns,
            "max_leg_book_age_ns": max_leg_book_age_ns,
            "max_leg_book_skew_ns": max_leg_book_skew_ns,
            "max_qty": max_qty,
            "max_position_lots": max_position_lots,
            "signal_limit": signal_limit,
            "proof_thresholds": getattr(proof_thresholds, "__dict__", None),
        },
    )
    return ParitySweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)


def _legging_metrics(legging: pd.DataFrame) -> dict[str, int]:
    if legging.empty or "partial" not in legging.columns:
        return {
            "execution_count": 0,
            "full_execution_count": 0,
            "partial_execution_count": 0,
        }
    partial = legging["partial"].astype(bool)
    return {
        "execution_count": int(len(legging)),
        "full_execution_count": int((~partial).sum()),
        "partial_execution_count": int(partial.sum()),
    }


def _merge_proof_metrics(runs: pd.DataFrame, proof: ProofReport) -> pd.DataFrame:
    proof_passed = (
        proof.checks.groupby("run", dropna=False)["passed"]
        .all()
        .rename("proof_passed")
        .reset_index()
    )
    proof_columns = ["run"] + [col for col in proof.metrics.columns if col not in runs.columns and col != "run"]
    proof_metrics = proof.metrics[proof_columns]
    merged = runs.merge(proof_metrics, on="run", how="left").merge(proof_passed, on="run", how="left")
    merged["robust_score"] = (
        merged["net_pnl"].astype(float)
        - merged["max_drawdown"].fillna(0.0).astype(float)
        - merged["partial_execution_count"].astype(float)
    )
    return merged


def _sweep_summary(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return pd.DataFrame(
            columns=[
                "scenario_count",
                "passed_scenarios",
                "pass_rate",
                "best_run",
                "best_robust_score",
                "median_net_pnl",
                "min_net_pnl",
                "worst_drawdown",
                "total_signals",
                "total_partial_executions",
                "parity_futures_asof_freshness_enabled_runs",
                "total_parity_futures_join_rows",
                "total_parity_futures_fresh_join_rows",
                "total_parity_futures_stale_join_rows",
                "total_parity_futures_unmatched_join_rows",
                "total_parity_futures_signal_count",
                "total_parity_futures_signals_without_age",
                "total_parity_futures_signal_age_violations",
                "max_parity_futures_signal_age_ns",
                "parity_execution_guard_enabled_runs",
                "parity_execution_guard_declared_runs",
                "parity_execution_signal_source_causality_enabled_runs",
                "parity_execution_signal_source_causality_declared_runs",
                "parity_execution_edge_revalidation_enabled_runs",
                "parity_execution_edge_revalidation_declared_runs",
                "parity_execution_realized_edge_enabled_runs",
                "parity_execution_realized_edge_declared_runs",
                "parity_execution_order_timing_enabled_runs",
                "parity_execution_order_timing_declared_runs",
                "parity_execution_ioc_arrival_audit_enabled_runs",
                "parity_execution_ioc_arrival_audit_declared_runs",
                (
                    "parity_execution_ioc_arrival_"
                    "event_lineage_enabled_runs"
                ),
                (
                    "parity_execution_ioc_arrival_"
                    "event_lineage_declared_runs"
                ),
                "parity_execution_ioc_batch_preflight_enabled_runs",
                "parity_execution_ioc_batch_preflight_declared_runs",
                "parity_execution_guard_artifact_present_runs",
                "parity_execution_legging_artifact_present_runs",
                "parity_execution_fills_artifact_present_runs",
                "parity_execution_order_submissions_artifact_present_runs",
                "parity_execution_ioc_arrival_audit_artifact_present_runs",
                "total_parity_execution_guard_attempts",
                "total_parity_execution_guard_passed_attempts",
                "total_parity_execution_guard_deferred_attempts",
                "total_parity_execution_signal_source_checks",
                "total_parity_execution_signal_source_ready_attempts",
                "total_parity_execution_signal_source_pending_attempts",
                "total_parity_execution_signal_source_missing_evidence_rows",
                "total_parity_execution_signal_source_consistency_violations",
                "total_parity_execution_edge_revalidation_attempts",
                "total_parity_execution_edge_revalidation_passed_attempts",
                "total_parity_execution_edge_revalidation_rejected_attempts",
                "total_parity_execution_edge_revalidation_missing_evidence_rows",
                "total_parity_execution_edge_revalidation_consistency_violations",
                "total_parity_execution_realized_edge_evaluable_count",
                "total_parity_execution_realized_edge_positive_count",
                "total_parity_execution_realized_edge_nonpositive_count",
                "total_parity_execution_realized_edge_missing_evidence_rows",
                "total_parity_execution_realized_edge_consistency_violations",
                "total_parity_execution_realized_net_edge",
                "total_parity_execution_fill_timing_evaluable_count",
                "total_parity_execution_negative_fill_latency_count",
                "total_parity_execution_order_timing_evaluable_legs",
                "total_parity_execution_order_timing_missing_evidence_legs",
                "total_parity_execution_order_timing_consistency_violations",
                "total_parity_execution_pre_activation_fill_legs",
                "total_parity_execution_ioc_arrival_evaluable_legs",
                "total_parity_execution_ioc_arrival_missing_evidence_legs",
                "total_parity_execution_ioc_arrival_consistency_violations",
                "total_parity_execution_ioc_arrival_not_marketable_legs",
                "total_parity_execution_ioc_arrival_capacity_shortfall_legs",
                "total_parity_execution_ioc_arrival_negative_lag_legs",
                "total_parity_execution_ioc_arrival_market_events",
                (
                    "total_parity_execution_ioc_arrival_"
                    "competing_depth_events"
                ),
                (
                    "total_parity_execution_ioc_arrival_"
                    "event_depth_consistency_violations"
                ),
                "total_parity_execution_ioc_batch_preflight_attempts",
                "total_parity_execution_ioc_batch_preflight_passed_attempts",
                "total_parity_execution_ioc_batch_preflight_rejected_attempts",
                "total_parity_execution_ioc_batch_preflight_missing_evidence_rows",
                "total_parity_execution_ioc_batch_preflight_consistency_violations",
                "total_parity_execution_ioc_visible_not_marketable_attempts",
                "total_parity_execution_ioc_visible_capacity_shortfall_attempts",
                "total_parity_execution_ioc_visible_capacity_missing_evidence_rows",
                "total_parity_execution_ioc_visible_capacity_consistency_violations",
                "total_parity_execution_guard_missing_evidence_rows",
                "total_parity_execution_guard_unclassified_rows",
                "total_parity_execution_guard_consistency_violations",
                "total_parity_execution_stale_book_attempts",
                "total_parity_execution_negative_book_age_attempts",
                "total_parity_execution_skew_attempts",
                "total_parity_execution_routing_complete_attempts",
                "total_parity_execution_routing_incomplete_attempts",
                "total_parity_execution_signal_expiry_events",
                "total_parity_execution_guard_passed_missing_age_rows",
                "total_parity_execution_guard_age_violations",
                "total_parity_execution_guard_skew_violations",
                "max_parity_execution_routed_book_age_ns",
                "max_parity_execution_routed_book_skew_ns",
                "max_parity_execution_signal_source_lag_ns",
                "min_parity_execution_routed_net_edge",
                "max_parity_execution_observed_edge_decay",
                "min_parity_execution_realized_net_edge",
                "min_parity_execution_realized_vs_decision_net_edge",
                "max_parity_execution_fill_span_ns",
                "min_parity_execution_first_fill_latency_ns",
                "max_parity_execution_completion_latency_ns",
                "min_parity_execution_activation_to_first_fill_latency_ns",
                "max_parity_execution_activation_to_completion_latency_ns",
                "min_parity_execution_ioc_arrival_fill_ratio",
                "max_parity_execution_ioc_arrival_lag_ns",
                "min_parity_execution_routed_visible_fill_ratio",
                "total_parity_execution_count",
                "total_parity_execution_legging_missing_evidence_rows",
                "total_parity_execution_legging_consistency_violations",
                "total_parity_execution_complete_count",
                "total_parity_execution_incomplete_count",
                "total_parity_execution_route_rejected_legs",
                "total_parity_execution_unfilled_legs",
                "total_liquidity_shortfall_events",
                "total_liquidity_shortfall_qty",
                "total_carried_depletion_shortfall_events",
                "total_carried_depletion_shortfall_qty",
                "total_limit_orders_sent",
                "total_queue_initialization_events",
                "total_deferred_queue_initialization_events",
                "total_uninitialized_limit_orders",
                "max_queue_initialization_lag_ns",
                "total_residual_resting_transition_events",
                "total_residual_resting_transition_qty",
                "total_deferred_residual_queue_events",
                "total_unresolved_residual_queue_events",
                "max_residual_queue_initialization_lag_ns",
                "total_passive_price_through_events",
                "total_passive_price_through_requested_qty",
                "total_passive_price_through_filled_qty",
                "total_passive_price_through_shortfall_qty",
                "total_passive_price_through_incomplete_events",
                "total_terminal_liquidation_events",
                "total_terminal_liquidation_requested_qty",
                "total_terminal_liquidation_filled_qty",
                "total_terminal_liquidation_shortfall_qty",
                "total_terminal_liquidation_incomplete_events",
                "total_terminal_residual_position_qty",
                "total_terminal_residual_instruments",
                "total_pretrade_rejections",
                "total_venue_rule_rejections",
                "total_position_risk_rejections",
                "total_self_cross_rejections",
            ]
        )
    best = runs.sort_values(["robust_score", "net_pnl"], ascending=False).iloc[0]
    return pd.DataFrame(
        [
            {
                "scenario_count": int(len(runs)),
                "passed_scenarios": int(runs["proof_passed"].fillna(False).sum()),
                "pass_rate": float(runs["proof_passed"].fillna(False).mean()),
                "best_run": best["run"],
                "best_robust_score": float(best["robust_score"]),
                "median_net_pnl": float(runs["net_pnl"].median()),
                "min_net_pnl": float(runs["net_pnl"].min()),
                "worst_drawdown": float(runs["max_drawdown"].max(skipna=True)),
                "total_signals": int(runs["signal_count"].sum()),
                "total_partial_executions": int(runs["partial_execution_count"].sum()),
                "parity_futures_asof_freshness_enabled_runs": int(
                    runs.get(
                        "parity_futures_asof_freshness_enabled",
                        pd.Series(False, index=runs.index),
                    )
                    .fillna(False)
                    .astype(bool)
                    .sum()
                ),
                "total_parity_futures_join_rows": _sum_int_metric(
                    runs,
                    "parity_futures_join_rows",
                ),
                "total_parity_futures_fresh_join_rows": _sum_int_metric(
                    runs,
                    "parity_futures_fresh_join_rows",
                ),
                "total_parity_futures_stale_join_rows": _sum_int_metric(
                    runs,
                    "parity_futures_stale_join_rows",
                ),
                "total_parity_futures_unmatched_join_rows": _sum_int_metric(
                    runs,
                    "parity_futures_unmatched_join_rows",
                ),
                "total_parity_futures_signal_count": _sum_int_metric(
                    runs,
                    "parity_futures_signal_count",
                ),
                "total_parity_futures_signals_without_age": _sum_int_metric(
                    runs,
                    "parity_futures_signals_without_age",
                ),
                "total_parity_futures_signal_age_violations": _sum_int_metric(
                    runs,
                    "parity_futures_signal_age_violations",
                ),
                "max_parity_futures_signal_age_ns": _max_int_metric(
                    runs,
                    "parity_futures_max_signal_age_ns",
                ),
                "parity_execution_guard_enabled_runs": _sum_bool_metric(
                    runs,
                    "parity_execution_guard_enabled",
                ),
                "parity_execution_guard_declared_runs": _sum_bool_metric(
                    runs,
                    "parity_execution_guard_declared",
                ),
                "parity_execution_signal_source_causality_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_signal_source_causality_enabled",
                    )
                ),
                "parity_execution_signal_source_causality_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_signal_source_causality_declared",
                    )
                ),
                "parity_execution_edge_revalidation_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_edge_revalidation_enabled",
                    )
                ),
                "parity_execution_edge_revalidation_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_edge_revalidation_declared",
                    )
                ),
                "parity_execution_realized_edge_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_realized_edge_enabled",
                    )
                ),
                "parity_execution_realized_edge_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_realized_edge_declared",
                    )
                ),
                "parity_execution_order_timing_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_order_timing_enabled",
                    )
                ),
                "parity_execution_order_timing_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_order_timing_declared",
                    )
                ),
                "parity_execution_ioc_arrival_audit_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_ioc_arrival_audit_enabled",
                    )
                ),
                "parity_execution_ioc_arrival_audit_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_ioc_arrival_audit_declared",
                    )
                ),
                (
                    "parity_execution_ioc_arrival_"
                    "event_lineage_enabled_runs"
                ): _sum_bool_metric(
                    runs,
                    (
                        "parity_execution_ioc_arrival_"
                        "event_lineage_enabled"
                    ),
                ),
                (
                    "parity_execution_ioc_arrival_"
                    "event_lineage_declared_runs"
                ): _sum_bool_metric(
                    runs,
                    (
                        "parity_execution_ioc_arrival_"
                        "event_lineage_declared"
                    ),
                ),
                "parity_execution_ioc_batch_preflight_enabled_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_enabled",
                    )
                ),
                "parity_execution_ioc_batch_preflight_declared_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_declared",
                    )
                ),
                "parity_execution_guard_artifact_present_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_guard_present",
                    )
                ),
                "parity_execution_legging_artifact_present_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_legging_present",
                    )
                ),
                "parity_execution_fills_artifact_present_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_fills_present",
                    )
                ),
                "parity_execution_order_submissions_artifact_present_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_order_submissions_present",
                    )
                ),
                "parity_execution_ioc_arrival_audit_artifact_present_runs": (
                    _sum_bool_metric(
                        runs,
                        "parity_execution_ioc_arrival_audit_present",
                    )
                ),
                "total_parity_execution_guard_attempts": _sum_int_metric(
                    runs,
                    "parity_execution_guard_attempts",
                ),
                "total_parity_execution_guard_passed_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_passed_attempts",
                    )
                ),
                "total_parity_execution_guard_deferred_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_deferred_attempts",
                    )
                ),
                "total_parity_execution_signal_source_checks": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_source_checks",
                    )
                ),
                "total_parity_execution_signal_source_ready_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_source_ready_attempts",
                    )
                ),
                "total_parity_execution_signal_source_pending_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_source_pending_attempts",
                    )
                ),
                "total_parity_execution_signal_source_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_source_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_signal_source_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_source_consistency_violations",
                    )
                ),
                "total_parity_execution_edge_revalidation_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_edge_revalidation_attempts",
                    )
                ),
                "total_parity_execution_edge_revalidation_passed_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_edge_revalidation_passed_attempts",
                    )
                ),
                "total_parity_execution_edge_revalidation_rejected_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_edge_revalidation_rejected_attempts",
                    )
                ),
                "total_parity_execution_edge_revalidation_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_edge_revalidation_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_edge_revalidation_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_edge_revalidation_consistency_violations",
                    )
                ),
                "total_parity_execution_realized_edge_evaluable_count": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_realized_edge_evaluable_count",
                    )
                ),
                "total_parity_execution_realized_edge_positive_count": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_realized_edge_positive_count",
                    )
                ),
                "total_parity_execution_realized_edge_nonpositive_count": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_realized_edge_nonpositive_count",
                    )
                ),
                "total_parity_execution_realized_edge_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_realized_edge_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_realized_edge_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_realized_edge_consistency_violations",
                    )
                ),
                "total_parity_execution_realized_net_edge": (
                    _sum_float_metric(
                        runs,
                        "parity_execution_total_realized_net_edge",
                    )
                ),
                "total_parity_execution_fill_timing_evaluable_count": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_fill_timing_evaluable_count",
                    )
                ),
                "total_parity_execution_negative_fill_latency_count": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_negative_fill_latency_count",
                    )
                ),
                "total_parity_execution_order_timing_evaluable_legs": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_order_timing_evaluable_legs",
                    )
                ),
                "total_parity_execution_order_timing_missing_evidence_legs": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_"
                            "order_timing_missing_evidence_legs"
                        ),
                    )
                ),
                "total_parity_execution_order_timing_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_"
                            "order_timing_consistency_violations"
                        ),
                    )
                ),
                "total_parity_execution_pre_activation_fill_legs": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_pre_activation_fill_legs",
                    )
                ),
                "total_parity_execution_ioc_arrival_evaluable_legs": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_arrival_evaluable_legs",
                    )
                ),
                "total_parity_execution_ioc_arrival_missing_evidence_legs": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_arrival_missing_evidence_legs",
                    )
                ),
                "total_parity_execution_ioc_arrival_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_ioc_arrival_"
                            "consistency_violations"
                        ),
                    )
                ),
                "total_parity_execution_ioc_arrival_not_marketable_legs": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_ioc_arrival_"
                            "not_marketable_legs"
                        ),
                    )
                ),
                "total_parity_execution_ioc_arrival_capacity_shortfall_legs": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_ioc_arrival_"
                            "capacity_shortfall_legs"
                        ),
                    )
                ),
                "total_parity_execution_ioc_arrival_negative_lag_legs": (
                    _sum_int_metric(
                        runs,
                        (
                            "parity_execution_ioc_arrival_"
                            "negative_lag_legs"
                        ),
                    )
                ),
                "total_parity_execution_ioc_arrival_market_events": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_arrival_market_events",
                    )
                ),
                (
                    "total_parity_execution_ioc_arrival_"
                    "competing_depth_events"
                ): _sum_int_metric(
                    runs,
                    (
                        "parity_execution_ioc_arrival_"
                        "competing_depth_events"
                    ),
                ),
                (
                    "total_parity_execution_ioc_arrival_"
                    "event_depth_consistency_violations"
                ): _sum_int_metric(
                    runs,
                    (
                        "parity_execution_ioc_arrival_"
                        "event_depth_consistency_violations"
                    ),
                ),
                "total_parity_execution_ioc_batch_preflight_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_attempts",
                    )
                ),
                "total_parity_execution_ioc_batch_preflight_passed_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_passed_attempts",
                    )
                ),
                "total_parity_execution_ioc_batch_preflight_rejected_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_rejected_attempts",
                    )
                ),
                "total_parity_execution_ioc_batch_preflight_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_ioc_batch_preflight_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_batch_preflight_consistency_violations",
                    )
                ),
                "total_parity_execution_ioc_visible_not_marketable_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_visible_not_marketable_attempts",
                    )
                ),
                "total_parity_execution_ioc_visible_capacity_shortfall_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_visible_capacity_shortfall_attempts",
                    )
                ),
                "total_parity_execution_ioc_visible_capacity_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_visible_capacity_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_ioc_visible_capacity_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_ioc_visible_capacity_consistency_violations",
                    )
                ),
                "total_parity_execution_guard_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_guard_unclassified_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_unclassified_rows",
                    )
                ),
                "total_parity_execution_guard_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_consistency_violations",
                    )
                ),
                "total_parity_execution_stale_book_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_stale_book_attempts",
                    )
                ),
                "total_parity_execution_negative_book_age_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_negative_book_age_attempts",
                    )
                ),
                "total_parity_execution_skew_attempts": _sum_int_metric(
                    runs,
                    "parity_execution_skew_attempts",
                ),
                "total_parity_execution_routing_complete_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_routing_complete_attempts",
                    )
                ),
                "total_parity_execution_routing_incomplete_attempts": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_routing_incomplete_attempts",
                    )
                ),
                "total_parity_execution_signal_expiry_events": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_signal_expiry_events",
                    )
                ),
                "total_parity_execution_guard_passed_missing_age_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_passed_missing_age_rows",
                    )
                ),
                "total_parity_execution_guard_age_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_age_violations",
                    )
                ),
                "total_parity_execution_guard_skew_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_guard_skew_violations",
                    )
                ),
                "max_parity_execution_routed_book_age_ns": (
                    _max_int_metric(
                        runs,
                        "parity_execution_max_routed_book_age_ns",
                    )
                ),
                "max_parity_execution_routed_book_skew_ns": (
                    _max_int_metric(
                        runs,
                        "parity_execution_max_routed_book_skew_ns",
                    )
                ),
                "max_parity_execution_signal_source_lag_ns": (
                    _max_int_metric(
                        runs,
                        "parity_execution_max_signal_source_lag_ns",
                    )
                ),
                "min_parity_execution_routed_visible_fill_ratio": (
                    _min_routed_metric(
                        runs,
                        "parity_execution_min_routed_visible_fill_ratio",
                    )
                ),
                "min_parity_execution_routed_net_edge": (
                    _min_routed_metric(
                        runs,
                        "parity_execution_min_routed_net_edge",
                    )
                ),
                "max_parity_execution_observed_edge_decay": (
                    _max_float_metric(
                        runs,
                        "parity_execution_max_observed_edge_decay",
                    )
                ),
                "min_parity_execution_realized_net_edge": (
                    _min_metric_where(
                        runs,
                        "parity_execution_min_realized_net_edge",
                        "parity_execution_realized_edge_evaluable_count",
                    )
                ),
                "min_parity_execution_realized_vs_decision_net_edge": (
                    _min_metric_where(
                        runs,
                        "parity_execution_min_realized_vs_decision_net_edge",
                        "parity_execution_realized_edge_evaluable_count",
                    )
                ),
                "max_parity_execution_fill_span_ns": _max_int_metric(
                    runs,
                    "parity_execution_max_fill_span_ns",
                ),
                "min_parity_execution_first_fill_latency_ns": (
                    _min_metric_where(
                        runs,
                        "parity_execution_min_first_fill_latency_ns",
                        "parity_execution_fill_timing_evaluable_count",
                    )
                ),
                "max_parity_execution_completion_latency_ns": (
                    _max_int_metric(
                        runs,
                        "parity_execution_max_completion_latency_ns",
                    )
                ),
                "min_parity_execution_activation_to_first_fill_latency_ns": (
                    _min_metric_where(
                        runs,
                        (
                            "parity_execution_"
                            "min_activation_to_first_fill_latency_ns"
                        ),
                        "parity_execution_order_timing_evaluable_legs",
                    )
                ),
                "max_parity_execution_activation_to_completion_latency_ns": (
                    _max_int_metric(
                        runs,
                        (
                            "parity_execution_"
                            "max_activation_to_completion_latency_ns"
                        ),
                    )
                ),
                "min_parity_execution_ioc_arrival_fill_ratio": (
                    _min_metric_where(
                        runs,
                        "parity_execution_min_ioc_arrival_fill_ratio",
                        "parity_execution_ioc_arrival_evaluable_legs",
                    )
                ),
                "max_parity_execution_ioc_arrival_lag_ns": (
                    _max_int_metric(
                        runs,
                        "parity_execution_max_ioc_arrival_lag_ns",
                    )
                ),
                "total_parity_execution_count": _sum_int_metric(
                    runs,
                    "parity_execution_count",
                ),
                "total_parity_execution_legging_missing_evidence_rows": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_legging_missing_evidence_rows",
                    )
                ),
                "total_parity_execution_legging_consistency_violations": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_legging_consistency_violations",
                    )
                ),
                "total_parity_execution_complete_count": _sum_int_metric(
                    runs,
                    "parity_execution_complete_count",
                ),
                "total_parity_execution_incomplete_count": _sum_int_metric(
                    runs,
                    "parity_execution_incomplete_count",
                ),
                "total_parity_execution_route_rejected_legs": (
                    _sum_int_metric(
                        runs,
                        "parity_execution_route_rejected_legs",
                    )
                ),
                "total_parity_execution_unfilled_legs": _sum_int_metric(
                    runs,
                    "parity_execution_unfilled_legs",
                ),
                "total_liquidity_shortfall_events": int(
                    pd.to_numeric(
                        runs.get(
                            "liquidity_shortfall_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_liquidity_shortfall_qty": int(
                    pd.to_numeric(
                        runs.get(
                            "liquidity_shortfall_qty",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_carried_depletion_shortfall_events": int(
                    pd.to_numeric(
                        runs.get(
                            "carried_depletion_shortfall_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_carried_depletion_shortfall_qty": int(
                    pd.to_numeric(
                        runs.get(
                            "carried_depletion_shortfall_qty",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_limit_orders_sent": int(
                    pd.to_numeric(
                        runs.get(
                            "limit_orders_sent",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_queue_initialization_events": int(
                    pd.to_numeric(
                        runs.get(
                            "queue_initialization_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_deferred_queue_initialization_events": int(
                    pd.to_numeric(
                        runs.get(
                            "deferred_queue_initialization_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_uninitialized_limit_orders": int(
                    pd.to_numeric(
                        runs.get(
                            "uninitialized_limit_orders",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "max_queue_initialization_lag_ns": int(
                    pd.to_numeric(
                        runs.get(
                            "max_queue_initialization_lag_ns",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).max()
                ),
                "total_residual_resting_transition_events": _sum_int_metric(
                    runs,
                    "residual_resting_transition_events",
                ),
                "total_residual_resting_transition_qty": _sum_int_metric(
                    runs,
                    "residual_resting_transition_qty",
                ),
                "total_deferred_residual_queue_events": _sum_int_metric(
                    runs,
                    "deferred_residual_queue_events",
                ),
                "total_unresolved_residual_queue_events": _sum_int_metric(
                    runs,
                    "unresolved_residual_queue_events",
                ),
                "max_residual_queue_initialization_lag_ns": int(
                    pd.to_numeric(
                        runs.get(
                            "max_residual_queue_initialization_lag_ns",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).max()
                ),
                "total_passive_price_through_events": _sum_int_metric(
                    runs,
                    "passive_price_through_events",
                ),
                "total_passive_price_through_requested_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_requested_qty",
                ),
                "total_passive_price_through_filled_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_filled_qty",
                ),
                "total_passive_price_through_shortfall_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_shortfall_qty",
                ),
                "total_passive_price_through_incomplete_events": _sum_int_metric(
                    runs,
                    "passive_price_through_incomplete_events",
                ),
                "total_terminal_liquidation_events": _sum_int_metric(
                    runs,
                    "terminal_liquidation_events",
                ),
                "total_terminal_liquidation_requested_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_requested_qty",
                ),
                "total_terminal_liquidation_filled_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_filled_qty",
                ),
                "total_terminal_liquidation_shortfall_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_shortfall_qty",
                ),
                "total_terminal_liquidation_incomplete_events": _sum_int_metric(
                    runs,
                    "terminal_liquidation_incomplete_events",
                ),
                "total_terminal_residual_position_qty": _sum_int_metric(
                    runs,
                    "terminal_residual_position_qty",
                ),
                "total_terminal_residual_instruments": _sum_int_metric(
                    runs,
                    "terminal_residual_instruments",
                ),
                "total_pretrade_rejections": int(
                    runs["pretrade_rejections"].sum()
                ),
                "total_venue_rule_rejections": _sum_int_metric(
                    runs,
                    "venue_rule_rejections",
                ),
                "total_position_risk_rejections": int(
                    runs["position_risk_rejections"].sum()
                ),
                "total_self_cross_rejections": int(
                    runs["self_cross_rejections"].sum()
                ),
            }
        ]
    )


def _sum_int_metric(runs: pd.DataFrame, column: str) -> int:
    values = runs.get(column, pd.Series(0, index=runs.index))
    return int(pd.to_numeric(values, errors="coerce").fillna(0).sum())


def _sum_float_metric(runs: pd.DataFrame, column: str) -> float:
    values = runs.get(column, pd.Series(0.0, index=runs.index))
    return float(
        pd.to_numeric(values, errors="coerce").fillna(0.0).sum()
    )


def _max_int_metric(runs: pd.DataFrame, column: str) -> int:
    values = runs.get(column, pd.Series(0, index=runs.index))
    return int(pd.to_numeric(values, errors="coerce").fillna(0).max())


def _min_routed_metric(
    runs: pd.DataFrame,
    column: str,
) -> float:
    routed = pd.to_numeric(
        runs.get(
            "parity_execution_guard_passed_attempts",
            pd.Series(0, index=runs.index),
        ),
        errors="coerce",
    ).fillna(0).gt(0)
    values = pd.to_numeric(
        runs.get(
            column,
            pd.Series(float("nan"), index=runs.index),
        ),
        errors="coerce",
    ).loc[routed].dropna()
    return float(values.min()) if not values.empty else 0.0


def _min_metric_where(
    runs: pd.DataFrame,
    column: str,
    count_column: str,
) -> float:
    present = pd.to_numeric(
        runs.get(
            count_column,
            pd.Series(0, index=runs.index),
        ),
        errors="coerce",
    ).fillna(0).gt(0)
    values = pd.to_numeric(
        runs.get(
            column,
            pd.Series(float("nan"), index=runs.index),
        ),
        errors="coerce",
    ).loc[present].dropna()
    return float(values.min()) if not values.empty else 0.0


def _max_float_metric(runs: pd.DataFrame, column: str) -> float:
    values = runs.get(
        column,
        pd.Series(float("nan"), index=runs.index),
    )
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.max()) if not numeric.empty else 0.0


def _sum_bool_metric(runs: pd.DataFrame, column: str) -> int:
    values = runs.get(column, pd.Series(False, index=runs.index))
    if values.dtype == bool:
        return int(values.fillna(False).sum())
    return int(
        values.map(
            lambda value: (
                value.strip().lower() in {"1", "true", "yes", "y"}
                if isinstance(value, str)
                else bool(value) if not pd.isna(value) else False
            )
        ).sum()
    )


def _run_name(
    depth_fraction: float,
    asof_latency_ns: int,
    feed_latency_us: float,
    order_latency_us: float,
    latency_jitter_us: float = 0.0,
) -> str:
    name = (
        f"depth_{_label_number(depth_fraction)}"
        f"__asof_{int(asof_latency_ns)}ns"
        f"__feed_{_label_number(feed_latency_us)}us"
        f"__order_{_label_number(order_latency_us)}us"
    )
    if float(latency_jitter_us) != 0.0:
        name += (
            f"__jitter_{_label_number(latency_jitter_us)}us"
        )
    return name


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _float_list(values: list[str]) -> list[float]:
    return [float(value) for value in values]


def _int_list(values: list[str]) -> list[int]:
    return [int(value) for value in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a parity replay robustness sweep.")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--futures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--option-tick", type=float, default=0.05)
    parser.add_argument("--future-tick", type=float, default=0.05)
    parser.add_argument("--depth-fraction", nargs="+", required=True)
    parser.add_argument("--asof-latency-ns", nargs="+", default=["0"])
    parser.add_argument("--feed-latency-us", nargs="+", default=["0"])
    parser.add_argument("--order-latency-us", nargs="+", default=["0"])
    parser.add_argument(
        "--latency-jitter-us",
        nargs="+",
        default=["0"],
    )
    parser.add_argument("--latency-seed", type=int, default=17)
    parser.add_argument(
        "--max-futures-quote-age-ns",
        type=int,
        default=1_000_000,
    )
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
    parser.add_argument("--min-net-pnl", type=float, default=0.0)
    parser.add_argument("--min-fills", type=int, default=1)
    parser.add_argument("--max-drawdown", type=float, default=None)
    parser.add_argument("--max-otr", type=float, default=None)
    parser.add_argument("--min-spread-net", type=float, default=None)
    parser.add_argument("--fail-on-breach", action="store_true")
    args = parser.parse_args(argv)

    result = run_parity_sweep(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        depth_fraction_values=_float_list(args.depth_fraction),
        asof_latency_ns_values=_int_list(args.asof_latency_ns),
        feed_latency_us_values=_float_list(args.feed_latency_us),
        order_latency_us_values=_float_list(args.order_latency_us),
        latency_jitter_us_values=_float_list(
            args.latency_jitter_us
        ),
        latency_seed=args.latency_seed,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        option_tick=args.option_tick,
        future_tick=args.future_tick,
        max_futures_quote_age_ns=args.max_futures_quote_age_ns,
        max_signal_age_ns=args.max_signal_age_ns,
        max_leg_book_age_ns=args.max_leg_book_age_ns,
        max_leg_book_skew_ns=args.max_leg_book_skew_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
        proof_thresholds=ProofThresholds(
            min_net_pnl=args.min_net_pnl,
            min_fills=args.min_fills,
            max_drawdown=args.max_drawdown,
            max_otr=args.max_otr,
            min_spread_net=args.min_spread_net,
        ),
    )
    print(result.summary.to_string(index=False))
    return 2 if args.fail_on_breach and not bool(result.proof.passed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
