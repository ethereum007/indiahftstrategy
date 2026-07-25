import json

import pandas as pd
import pytest

from hft_cli import main
from reports.proof import ProofThresholds, verify_proof_report
from strategies.run_parity_sweep import run_parity_sweep


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def write_parity_books(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for ts in [ts0, ts1]
        ]
    )
    futures = pd.DataFrame(
        [
            {"ts": ts, "bid": 1100.0, "ask": 1101.0, "bid_qty": 300, "ask_qty": 300}
            for ts in [ts0, ts1]
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)
    return chain_path, futures_path


def test_run_parity_sweep_writes_runs_proof_and_robust_summary(tmp_path):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "parity_sweep"

    result = run_parity_sweep(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction_values=[0.25],
        asof_latency_ns_values=[0, 200_000],
        feed_latency_us_values=[0.0],
        order_latency_us_values=[0.0],
        signal_limit=1,
        proof_thresholds=ProofThresholds(min_net_pnl=-1_000_000.0, min_fills=1),
    )

    assert len(result.runs) == 2
    assert result.summary.iloc[0]["scenario_count"] == 2
    assert result.summary.iloc[0]["passed_scenarios"] == 1
    assert result.summary.iloc[0]["pass_rate"] == 0.5
    assert result.runs["signal_count"].sum() == 1
    assert result.runs["parity_futures_asof_freshness_enabled"].all()
    assert int(
        result.summary.iloc[0][
            "parity_futures_asof_freshness_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0]["total_parity_futures_join_rows"]
    ) == 4
    assert int(
        result.summary.iloc[0]["total_parity_futures_fresh_join_rows"]
    ) == 2
    assert int(
        result.summary.iloc[0]["total_parity_futures_stale_join_rows"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_parity_futures_unmatched_join_rows"]
    ) == 2
    assert int(
        result.summary.iloc[0]["total_parity_futures_signal_count"]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_futures_signals_without_age"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_futures_signal_age_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0]["max_parity_futures_signal_age_ns"]
    ) == 0
    assert result.runs["parity_execution_guard_enabled"].all()
    assert int(
        result.summary.iloc[0]["parity_execution_guard_enabled_runs"]
    ) == 2
    assert int(
        result.summary.iloc[0]["parity_execution_guard_declared_runs"]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_edge_revalidation_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_signal_source_causality_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_signal_source_causality_declared_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_edge_revalidation_declared_runs"
        ]
    ) == 2
    assert result.runs[
        "parity_execution_realized_edge_enabled"
    ].all()
    assert int(
        result.summary.iloc[0][
            "parity_execution_realized_edge_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_realized_edge_declared_runs"
        ]
    ) == 2
    assert result.runs[
        "parity_execution_order_timing_enabled"
    ].all()
    assert int(
        result.summary.iloc[0][
            "parity_execution_order_timing_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_order_timing_declared_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_order_submissions_artifact_present_runs"
        ]
    ) == 2
    assert result.runs[
        "parity_execution_ioc_arrival_audit_enabled"
    ].all()
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_arrival_audit_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_arrival_audit_declared_runs"
        ]
    ) == 2
    assert result.runs[
        "parity_execution_ioc_arrival_event_lineage_enabled"
    ].all()
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_arrival_event_lineage_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_arrival_event_lineage_declared_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_arrival_audit_artifact_present_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_arrival_evaluable_legs"
        ]
    ) == 3
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_arrival_market_events"
        ]
    ) == 3
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_arrival_competing_depth_events"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_arrival_event_depth_consistency_violations"
        ]
    ) == 0
    assert float(
        result.summary.iloc[0][
            "min_parity_execution_ioc_arrival_fill_ratio"
        ]
    ) == 1.0
    assert result.runs[
        "parity_execution_ioc_batch_preflight_enabled"
    ].all()
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_batch_preflight_enabled_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_ioc_batch_preflight_declared_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_guard_artifact_present_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_legging_artifact_present_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_fills_artifact_present_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0]["total_parity_execution_guard_attempts"]
    ) == 3
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_passed_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_deferred_attempts"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_edge_revalidation_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_source_checks"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_source_ready_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_source_pending_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_source_consistency_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_signal_source_lag_ns"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_edge_revalidation_passed_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_edge_revalidation_rejected_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 0
    assert float(
        result.summary.iloc[0][
            "min_parity_execution_routed_net_edge"
        ]
    ) > 7_800.0
    assert float(
        result.summary.iloc[0][
            "max_parity_execution_observed_edge_decay"
        ]
    ) == 0.0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_realized_edge_evaluable_count"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_realized_edge_positive_count"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_realized_edge_nonpositive_count"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_realized_edge_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_realized_edge_consistency_violations"
        ]
    ) == 0
    assert float(
        result.summary.iloc[0][
            "total_parity_execution_realized_net_edge"
        ]
    ) == 7821.51938925
    assert float(
        result.summary.iloc[0][
            "min_parity_execution_realized_net_edge"
        ]
    ) == 7821.51938925
    assert float(
        result.summary.iloc[0][
            "min_parity_execution_realized_vs_decision_net_edge"
        ]
    ) == 0.0
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_fill_span_ns"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_fill_timing_evaluable_count"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_negative_fill_latency_count"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "min_parity_execution_first_fill_latency_ns"
        ]
    ) == 100_000
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_completion_latency_ns"
        ]
    ) == 100_000
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_order_timing_evaluable_legs"
        ]
    ) == 3
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_order_timing_missing_evidence_legs"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_order_timing_consistency_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_pre_activation_fill_legs"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "min_parity_execution_activation_to_first_fill_latency_ns"
        ]
    ) == 100_000
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_activation_to_completion_latency_ns"
        ]
    ) == 100_000
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_passed_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_consistency_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_visible_not_marketable_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_shortfall_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 0
    assert (
        float(
            result.summary.iloc[0][
                "min_parity_execution_routed_visible_fill_ratio"
            ]
        )
        == 4.0
    )
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_unclassified_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_consistency_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_stale_book_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_negative_book_age_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_parity_execution_skew_attempts"]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_routing_complete_attempts"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_routing_incomplete_attempts"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_signal_expiry_events"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_passed_missing_age_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_age_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_guard_skew_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_routed_book_age_ns"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "max_parity_execution_routed_book_skew_ns"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_parity_execution_count"]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_legging_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_legging_consistency_violations"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_complete_count"
        ]
    ) == 1
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_incomplete_count"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_route_rejected_legs"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_parity_execution_unfilled_legs"
        ]
    ) == 0
    assert int(result.summary.iloc[0]["total_pretrade_rejections"]) == 0
    assert int(result.summary.iloc[0]["total_venue_rule_rejections"]) == 0
    assert int(result.summary.iloc[0]["total_position_risk_rejections"]) == 0
    assert int(result.summary.iloc[0]["total_self_cross_rejections"]) == 0
    assert int(result.summary.iloc[0]["total_carried_depletion_shortfall_events"]) == 0
    assert int(result.summary.iloc[0]["total_carried_depletion_shortfall_qty"]) == 0
    assert int(result.summary.iloc[0]["total_limit_orders_sent"]) == 0
    assert int(result.summary.iloc[0]["total_queue_initialization_events"]) == 0
    assert int(result.summary.iloc[0]["total_deferred_queue_initialization_events"]) == 0
    assert int(result.summary.iloc[0]["total_uninitialized_limit_orders"]) == 0
    assert int(result.summary.iloc[0]["max_queue_initialization_lag_ns"]) == 0
    assert int(
        result.summary.iloc[0]["total_residual_resting_transition_events"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_residual_resting_transition_qty"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_deferred_residual_queue_events"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_unresolved_residual_queue_events"]
    ) == 0
    assert int(
        result.summary.iloc[0]["max_residual_queue_initialization_lag_ns"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_passive_price_through_events"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_passive_price_through_requested_qty"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_passive_price_through_filled_qty"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_passive_price_through_shortfall_qty"]
    ) == 0
    assert int(
        result.summary.iloc[0][
            "total_passive_price_through_incomplete_events"
        ]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_terminal_liquidation_events"]
    ) == int(result.runs["terminal_liquidation_events"].sum())
    assert int(
        result.summary.iloc[0]["total_terminal_liquidation_requested_qty"]
    ) == int(result.runs["terminal_liquidation_requested_qty"].sum())
    assert int(
        result.summary.iloc[0]["total_terminal_liquidation_filled_qty"]
    ) == int(result.runs["terminal_liquidation_filled_qty"].sum())
    assert int(
        result.summary.iloc[0]["total_terminal_liquidation_shortfall_qty"]
    ) == 0
    assert int(
        result.summary.iloc[0]["total_terminal_residual_position_qty"]
    ) == 0
    assert result.runs["pending_order_risk_reservation_enabled"].all()
    assert result.runs["aggressive_self_cross_prevention_enabled"].all()
    assert result.runs[
        "terminal_liquidation_depth_constrained_enabled"
    ].all()
    assert result.runs["terminal_liquidation_complete"].all()
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "sweep_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "proof" / "proof_checks.csv").exists()
    assert (out_dir / "proof" / "manifest.json").exists()
    assert verify_proof_report(out_dir / "proof").verified
    assert (
        out_dir
        / "runs"
        / "depth_0p25__asof_0ns__feed_0us__order_0us"
        / "parity_futures_join_audit.csv"
    ).exists()
    assert (
        out_dir
        / "runs"
        / "depth_0p25__asof_0ns__feed_0us__order_0us"
        / "parity_execution_guard.csv"
    ).exists()
    assert (out_dir / "runs" / "depth_0p25__asof_0ns__feed_0us__order_0us" / "summary.csv").exists()
    assert (out_dir / "runs" / "depth_0p25__asof_0ns__feed_0us__order_0us" / "manifest.json").exists()


def test_run_parity_sweep_expands_latency_jitter_dimension(tmp_path):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "jitter_sweep"

    result = run_parity_sweep(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction_values=[0.25],
        asof_latency_ns_values=[0],
        feed_latency_us_values=[10.0],
        order_latency_us_values=[10.0],
        latency_jitter_us_values=[0.0, 5.0],
        latency_seed=123,
        signal_limit=1,
        proof_thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    assert len(result.runs) == 2
    assert set(result.runs["latency_jitter_us"]) == {0.0, 5.0}
    assert set(result.runs["latency_seed"]) == {123}
    assert (
        result.runs["parity_feed_latency_bound_violations"] == 0
    ).all()
    assert (
        result.runs["parity_order_latency_bound_violations"] == 0
    ).all()
    assert (
        out_dir
        / "runs"
        / (
            "depth_0p25__asof_0ns__feed_10us__order_10us"
            "__jitter_5us"
        )
        / "feed_deliveries.csv"
    ).exists()
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["parameters"]["latency_jitter_us_values"] == [
        0.0,
        5.0,
    ]
    assert manifest["parameters"]["latency_seed"] == 123


def test_run_parity_sweep_aggregates_latency_seed_replications(
    tmp_path,
):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "seed_sweep"

    result = run_parity_sweep(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction_values=[0.25],
        asof_latency_ns_values=[0],
        feed_latency_us_values=[10.0],
        order_latency_us_values=[10.0],
        latency_jitter_us_values=[5.0],
        latency_seed_values=[101, 202, 303],
        signal_limit=1,
        proof_thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    assert len(result.runs) == 3
    assert set(result.runs["latency_seed"]) == {101, 202, 303}
    assert result.runs["run"].str.contains("__seed_").all()
    assert len(result.seed_robustness) == 1
    robustness = result.seed_robustness.iloc[0]
    assert robustness["latency_seed_values"] == "101,202,303"
    assert int(robustness["latency_seed_runs"]) == 3
    assert int(robustness["latency_seed_expected_runs"]) == 3
    assert int(robustness["latency_seed_count"]) == 3
    assert int(robustness["latency_seed_passed_runs"]) == 3
    assert float(robustness["latency_seed_pass_rate"]) == 1.0
    assert bool(robustness["latency_seed_group_passed"])
    assert robustness["latency_seed_worst_run"] in set(
        result.runs["run"]
    )
    summary = result.summary.iloc[0]
    assert int(summary["scenario_count"]) == 3
    assert int(summary["latency_seed_group_count"]) == 1
    assert int(summary["latency_seed_passed_groups"]) == 1
    assert float(summary["latency_seed_group_pass_rate"]) == 1.0
    assert summary["best_run"] == robustness[
        "latency_seed_worst_run"
    ]
    assert (out_dir / "latency_seed_robustness.csv").exists()
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["parameters"]["latency_seed"] is None
    assert manifest["parameters"]["latency_seed_values"] == [
        101,
        202,
        303,
    ]
    with pytest.raises(
        ValueError,
        match="latency_seed_values must be unique",
    ):
        run_parity_sweep(
            chain_path=chain_path,
            futures_path=futures_path,
            output_dir=tmp_path / "duplicate_seeds",
            depth_fraction_values=[0.25],
            asof_latency_ns_values=[0],
            feed_latency_us_values=[10.0],
            order_latency_us_values=[10.0],
            latency_seed_values=[101, 101],
        )


def test_unified_cli_sweep_parity_dispatches_and_can_fail_on_breach(tmp_path):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "cli_parity_sweep"

    code = main(
        [
            "sweep-parity",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--depth-fraction",
            "0.25",
            "--asof-latency-ns",
            "0",
            "200000",
            "--signal-limit",
            "1",
            "--max-leg-book-age-ns",
            "500000",
            "--max-leg-book-skew-ns",
            "250000",
            "--latency-jitter-us",
            "5",
            "--latency-seeds",
            "99",
            "100",
            "--min-net-pnl",
            "-1000000",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    runs = pd.read_csv(out_dir / "sweep_runs.csv")
    assert set(runs["parity_execution_max_leg_book_age_ns"]) == {500_000}
    assert set(runs["parity_execution_max_leg_book_skew_ns"]) == {250_000}
    assert set(runs["latency_jitter_us"]) == {5.0}
    assert set(runs["latency_seed"]) == {99, 100}
    assert (out_dir / "latency_seed_robustness.csv").exists()
