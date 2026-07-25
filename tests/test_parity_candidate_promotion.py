import json

import pandas as pd

from hft_cli import main
from reports.parity_candidate_promotion import (
    ParityCandidatePromotionThresholds,
    evaluate_parity_candidate_promotion,
    write_parity_candidate_promotion,
)
from reports.parity_order_plan import ParityOrderPlanConfig, build_parity_order_plan


def parity_opportunities():
    return pd.DataFrame(
        [
            {
                "ts": 200,
                "expiry": "2026-06-30",
                "strike": 25000.0,
                "direction": "buy_synthetic_sell_future",
                "qty": 75,
                "edge_per_unit": 6.0,
                "gross_edge": 450.0,
                "total_cost": 10.0,
                "net_edge": 440.0,
                "displayed_depth": 75,
                "future_ts": 200,
                "futures_lookup_ts": 200,
                "future_asof_age_ns": 0,
                "future_decision_age_ns": 0,
                "regime": "open",
                "call_side": 1,
                "call_price": 105.0,
                "put_side": -1,
                "put_price": 95.0,
                "future_side": -1,
                "future_price": 25020.0,
                "persistence_ticks": 2,
            }
        ]
    )


def box_opportunities(*, net_edge=120.0):
    return pd.DataFrame(
        [
            {
                "ts": 200,
                "expiry": "2026-06-30",
                "low_strike": 25000.0,
                "high_strike": 25100.0,
                "direction": "buy_box",
                "qty": 75,
                "edge_per_unit": 2.0,
                "gross_edge": 150.0,
                "total_cost": 30.0,
                "net_edge": net_edge,
                "displayed_depth": 75,
                "regime": "open",
                "low_call_side": 1,
                "low_call_price": 110.0,
                "low_put_side": -1,
                "low_put_price": 90.0,
                "high_call_side": -1,
                "high_call_price": 50.0,
                "high_put_side": 1,
                "high_put_price": 135.0,
                "persistence_ticks": 1,
            }
        ]
    )


def edge_summary(*, passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "total_opportunities": 2,
                "parity_opportunities": 1,
                "box_opportunities": 1,
                "total_net_edge": 560.0,
                "median_net_edge": 280.0,
                "best_net_edge": 440.0,
                "median_persistence_ticks": 1.5,
            }
        ]
    )


def sweep_summary(*, passed_scenarios=1):
    return pd.DataFrame(
        [
            {
                "scenario_count": 2,
                "passed_scenarios": passed_scenarios,
                "pass_rate": 0.5 if passed_scenarios else 0.0,
                "best_run": "depth_0p25__asof_0ns__feed_0us__order_0us",
                "best_robust_score": 42.0,
                "median_net_pnl": 10.0,
                "min_net_pnl": -1.0,
                "worst_drawdown": 5.0,
                "total_signals": 2,
                "total_partial_executions": 0,
            }
        ]
    )


def sweep_runs(*, proof_passed=True):
    return pd.DataFrame(
        [
            {
                "run": "depth_0p25__asof_0ns__feed_0us__order_0us",
                "run_dir": "runs/parity",
                "depth_fraction": 0.25,
                "asof_latency_ns": 0,
                "parity_futures_max_quote_age_ns": 100_000,
                "parity_execution_max_leg_book_age_ns": 200_000,
                "parity_execution_max_leg_book_skew_ns": 50_000,
                "feed_latency_us": 0.0,
                "order_latency_us": 0.0,
                "latency_jitter_us": 15.0,
                "latency_seed": 2026,
                "signal_count": 1,
                "execution_count": 1,
                "partial_execution_count": 0,
                "net_pnl": 50.0,
                "fills": 3,
                "max_drawdown": 1.0,
                "proof_passed": proof_passed,
                "robust_score": 49.0,
            }
        ]
    )


def latency_seed_robustness(
    *,
    group_passed=True,
    pass_rate=1.0,
    worst_run="latency_group__seed_22",
):
    return pd.DataFrame(
        [
            {
                "latency_seed_group": "latency_group",
                "depth_fraction": 0.25,
                "asof_latency_ns": 0,
                "feed_latency_us": 0.0,
                "order_latency_us": 0.0,
                "latency_jitter_us": 15.0,
                "latency_seed_values": "11,22",
                "latency_seed_runs": 2,
                "latency_seed_expected_runs": 2,
                "latency_seed_count": 2,
                "latency_seed_passed_runs": (
                    2 if group_passed else 1
                ),
                "latency_seed_pass_rate": pass_rate,
                "latency_seed_group_passed": group_passed,
                "latency_seed_worst_run": worst_run,
                "latency_seed_worst_seed": 22,
                "latency_seed_worst_robust_score": 10.0,
                "latency_seed_worst_net_pnl": 11.0,
                "latency_seed_median_net_pnl": 55.5,
                "latency_seed_best_net_pnl": 100.0,
                "latency_seed_min_fills": 3,
                "latency_seed_worst_drawdown": 2.0,
                "latency_seed_bound_violations": 0,
            }
        ]
    )


def write_inputs(
    root,
    *,
    edge_passed=True,
    passed_scenarios=1,
    include_seed_robustness=False,
):
    scan_dir = root / "scan"
    edge_dir = root / "edge"
    sweep_dir = root / "sweep"
    scan_dir.mkdir(parents=True)
    edge_dir.mkdir(parents=True)
    sweep_dir.mkdir(parents=True)
    parity_opportunities().to_csv(scan_dir / "parity_opportunities.csv", index=False)
    box_opportunities().to_csv(scan_dir / "box_opportunities.csv", index=False)
    edge_summary(passed=edge_passed).to_csv(edge_dir / "parity_edge_summary.csv", index=False)
    sweep_summary(passed_scenarios=passed_scenarios).to_csv(sweep_dir / "sweep_summary.csv", index=False)
    runs = sweep_runs(proof_passed=bool(passed_scenarios))
    if include_seed_robustness:
        first = runs.iloc[0].to_dict()
        first.update(
            {
                "run": "latency_group__seed_11",
                "latency_seed_group": "latency_group",
                "latency_seed": 11,
                "robust_score": 100.0,
                "net_pnl": 100.0,
            }
        )
        second = dict(first)
        second.update(
            {
                "run": "latency_group__seed_22",
                "latency_seed": 22,
                "robust_score": 10.0,
                "net_pnl": 11.0,
                "max_drawdown": 2.0,
            }
        )
        runs = pd.DataFrame([first, second])
        latency_seed_robustness().to_csv(
            sweep_dir / "latency_seed_robustness.csv",
            index=False,
        )
    runs.to_csv(sweep_dir / "sweep_runs.csv", index=False)
    return scan_dir, edge_dir, sweep_dir


def test_parity_candidate_promotion_passes_and_feeds_order_plan():
    report = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        sweep_runs(),
        thresholds=ParityCandidatePromotionThresholds(min_candidate_net_edge=400.0),
    )

    config = report.candidate_config
    assert report.ready
    assert report.summary.loc[0, "strategy"] == "parity_box"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert config["ready"]
    assert config["strategy"] == "parity_box"
    assert config["parameters"]["direction"] == "buy_synthetic_sell_future"
    assert config["parameters"]["call_price"] == 105.0
    assert config["parameters"]["put_price"] == 95.0
    assert config["parameters"]["future_price"] == 25020.0
    assert config["parameters"]["futures_lookup_ts"] == 200
    assert config["parameters"]["future_asof_age_ns"] == 0
    assert config["parameters"]["future_decision_age_ns"] == 0
    assert config["replay_defaults"]["depth_fraction"] == 0.25
    assert config["replay_defaults"]["max_futures_quote_age_ns"] == 100_000
    assert config["replay_defaults"]["max_leg_book_age_ns"] == 200_000
    assert config["replay_defaults"]["max_leg_book_skew_ns"] == 50_000
    assert config["replay_defaults"]["latency_jitter_us"] == 15.0
    assert config["replay_defaults"]["latency_seed"] == 2026

    order_plan = build_parity_order_plan(
        report.summary,
        config,
        config=ParityOrderPlanConfig(max_order_qty=75, max_notional=2_000_000),
    )
    assert order_plan.ready
    assert order_plan.summary.loc[0, "orders"] == 3
    assert set(order_plan.orders["leg_role"]) == {"CALL", "PUT", "FUTURE"}


def test_parity_candidate_promotion_rejects_lucky_seed_and_selects_worst_seed():
    first = sweep_runs().iloc[0].to_dict()
    first.update(
        {
            "run": "latency_group__seed_11",
            "latency_seed_group": "latency_group",
            "latency_seed": 11,
            "proof_passed": True,
            "robust_score": 100.0,
            "net_pnl": 100.0,
        }
    )
    second = dict(first)
    second.update(
        {
            "run": "latency_group__seed_22",
            "latency_seed": 22,
            "proof_passed": False,
            "robust_score": 10.0,
            "net_pnl": 11.0,
            "max_drawdown": 2.0,
        }
    )
    runs = pd.DataFrame([first, second])

    rejected = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        runs,
        latency_seed_robustness=latency_seed_robustness(),
        thresholds=ParityCandidatePromotionThresholds(
            min_candidate_net_edge=400.0
        ),
    )

    assert not rejected.ready
    assert {
        "latency_seed_robust_group_available",
        "latency_seed_group_passed",
        "latency_seed_pass_rate",
    }.issubset(set(rejected.candidate_config["failed_checks"]))

    runs.loc[:, "proof_passed"] = True
    robust = latency_seed_robustness()
    robust["latency_seed"] = 11
    promoted = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        runs,
        latency_seed_robustness=robust,
        thresholds=ParityCandidatePromotionThresholds(
            min_candidate_net_edge=400.0
        ),
    )

    assert promoted.ready
    config = promoted.candidate_config
    assert config["replay_defaults"]["latency_seed"] == 22
    assert config["metrics"]["latency_seed_values"] == "11,22"
    assert config["metrics"]["latency_seed_expected_runs"] == 2
    assert config["metrics"]["latency_seed_count"] == 2
    assert config["metrics"]["latency_seed_pass_rate"] == 1.0
    assert config["metrics"]["latency_seed_group_passed"]
    assert config["metrics"]["latency_seed_worst_run"] == (
        "latency_group__seed_22"
    )

    tampered_parameters = latency_seed_robustness()
    tampered_parameters.loc[:, "depth_fraction"] = 0.99
    parameter_rejected = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        runs,
        latency_seed_robustness=tampered_parameters,
    )
    assert not parameter_rejected.ready

    incomplete = latency_seed_robustness()
    incomplete.loc[:, "latency_seed_expected_runs"] = 3
    incomplete_rejected = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        runs,
        latency_seed_robustness=incomplete,
    )
    assert not incomplete_rejected.ready

    runs_with_bound_breach = runs.copy()
    runs_with_bound_breach[
        "parity_feed_latency_bound_violations"
    ] = [0, 1]
    bound_rejected = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(),
        edge_summary(),
        sweep_summary(),
        runs_with_bound_breach,
        latency_seed_robustness=latency_seed_robustness(),
    )
    assert not bound_rejected.ready


def test_parity_candidate_promotion_can_promote_best_box_opportunity():
    report = evaluate_parity_candidate_promotion(
        parity_opportunities(),
        box_opportunities(net_edge=500.0),
        edge_summary(),
        sweep_summary(),
        sweep_runs(),
    )

    config = report.candidate_config
    assert report.ready
    assert config["parameters"]["direction"] == "buy_box"
    assert config["parameters"]["low_call_price"] == 110.0
    assert config["parameters"]["high_put_price"] == 135.0


def test_write_parity_candidate_promotion_outputs_launch_compatible_files(tmp_path):
    scan_dir, edge_dir, sweep_dir = write_inputs(
        tmp_path,
        include_seed_robustness=True,
    )
    out_dir = tmp_path / "promotion"

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=out_dir,
        thresholds=ParityCandidatePromotionThresholds(min_candidate_net_edge=400.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert config["ready"]
    assert config["parameters"]["market"] == "india_nse_index_derivatives"
    assert config["replay_defaults"]["latency_seed"] == 22
    assert config["metrics"]["latency_seed_count"] == 2
    assert manifest["run_type"] == "promotion_report"
    assert manifest["parameters"]["strategy"] == "parity_box"
    assert manifest["extra"]["promotion_source"] == "parity_scan_edge_sweep"
    assert "latency_seed_robustness" in manifest["inputs"]
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()


def test_cli_promote_parity_candidate_fails_closed_for_weak_evidence(tmp_path):
    scan_dir, edge_dir, sweep_dir = write_inputs(tmp_path, edge_passed=False, passed_scenarios=0)
    out_dir = tmp_path / "promotion"

    code = main(
        [
            "promote-parity-candidate",
            "--scan",
            str(scan_dir),
            "--edge-audit",
            str(edge_dir),
            "--sweep",
            str(sweep_dir),
            "--out",
            str(out_dir),
            "--min-passed-scenarios",
            "1",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "promotion_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not config["ready"]
    assert "edge_audit_passed" in config["failed_checks"]
    assert "passed_scenarios" in config["failed_checks"]
