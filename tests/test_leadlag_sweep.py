import json

import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds, verify_proof_report
from strategies.run_leadlag_sweep import run_leadlag_sweep


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def write_books(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    ts3 = ns_ist("2026-06-10 09:15:00.000300")
    ts4 = ns_ist("2026-06-10 09:15:00.000400")
    leader = pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    laggard = pd.DataFrame(
        [
            {"ts": ts0, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 50.50, "ask": 50.55, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 50.50, "ask": 50.55, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    leader_path = tmp_path / "leader.csv"
    laggard_path = tmp_path / "laggard.csv"
    leader.to_csv(leader_path, index=False)
    laggard.to_csv(laggard_path, index=False)
    return leader_path, laggard_path


def test_run_leadlag_sweep_writes_runs_proof_and_robust_summary(tmp_path):
    leader_path, laggard_path = write_books(tmp_path)
    out_dir = tmp_path / "sweep"

    result = run_leadlag_sweep(
        leader_path=leader_path,
        laggard_path=laggard_path,
        output_dir=out_dir,
        trigger_ticks_values=[10.0, 1000.0],
        feed_latency_us_values=[0.0],
        order_latency_us_values=[0.0],
        leader_tick=0.05,
        laggard_tick=0.05,
        delta=1.0,
        qty=75,
        flat_after_ns=200_000,
        markout_horizons_ns=[100_000],
        proof_thresholds=ProofThresholds(min_net_pnl=-1000.0, min_fills=1),
    )

    assert len(result.runs) == 2
    assert set(result.runs["strategy"]) == {"lead_lag_taker"}
    assert set(result.runs["market"]) == {"india_nse_index_derivatives"}
    assert result.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert result.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert result.summary.iloc[0]["scenario_count"] == 2
    assert result.summary.iloc[0]["passed_scenarios"] == 1
    assert result.summary.iloc[0]["pass_rate"] == 0.5
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
    assert (out_dir / "runs" / "trigger_10__feed_0us__order_0us" / "summary.csv").exists()
    assert (out_dir / "runs" / "trigger_10__feed_0us__order_0us" / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"


def test_unified_cli_sweep_leadlag_dispatches_and_can_fail_on_breach(tmp_path):
    leader_path, laggard_path = write_books(tmp_path)
    out_dir = tmp_path / "cli_sweep"

    code = main(
        [
            "sweep-leadlag",
            "--leader",
            str(leader_path),
            "--laggard",
            str(laggard_path),
            "--out",
            str(out_dir),
            "--trigger-ticks",
            "10",
            "1000",
            "--leader-tick",
            "0.05",
            "--laggard-tick",
            "0.05",
            "--delta",
            "1",
            "--qty",
            "75",
            "--flat-after-ns",
            "200000",
            "--markout-horizons-ns",
            "100000",
            "--min-net-pnl",
            "-1000",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    summary = pd.read_csv(out_dir / "sweep_summary.csv")
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
