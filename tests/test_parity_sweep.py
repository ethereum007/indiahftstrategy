import pandas as pd

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
            "parity_execution_guard_artifact_present_runs"
        ]
    ) == 2
    assert int(
        result.summary.iloc[0][
            "parity_execution_legging_artifact_present_runs"
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
