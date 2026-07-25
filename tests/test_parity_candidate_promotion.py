import json

import pandas as pd

from hft_cli import main
from reports.parity_candidate_promotion import (
    ParityCandidatePromotionThresholds,
    evaluate_parity_candidate_promotion,
    write_parity_candidate_promotion,
)
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.parity_edge import PARITY_EDGE_RUN_TYPE
from reports.parity_order_plan import ParityOrderPlanConfig, build_parity_order_plan
from scanners.run_parity_box import PARITY_SCAN_RUN_TYPE
from strategies.run_parity_sweep import PARITY_SWEEP_RUN_TYPE


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
    sweep_source_matches=True,
    sweep_option_tick=0.05,
    scan_depth_fraction=0.25,
):
    scan_dir = root / "scan"
    edge_dir = root / "edge"
    sweep_dir = root / "sweep"
    source_dir = root / "source"
    scan_dir.mkdir(parents=True)
    edge_dir.mkdir(parents=True)
    sweep_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    chain_path = source_dir / "chain.csv"
    futures_path = source_dir / "futures.csv"
    pd.DataFrame([{"ts": 1, "value": 100.0}]).to_csv(
        chain_path,
        index=False,
    )
    pd.DataFrame([{"ts": 1, "value": 101.0}]).to_csv(
        futures_path,
        index=False,
    )
    sweep_futures_path = futures_path
    if not sweep_source_matches:
        sweep_futures_path = source_dir / "other_futures.csv"
        pd.DataFrame([{"ts": 1, "value": 999.0}]).to_csv(
            sweep_futures_path,
            index=False,
        )
    parity_opportunities().to_csv(scan_dir / "parity_opportunities.csv", index=False)
    box_opportunities().to_csv(scan_dir / "box_opportunities.csv", index=False)
    pd.DataFrame([{"opportunities": 2}]).to_csv(
        scan_dir / "opportunity_report.csv",
        index=False,
    )
    pd.DataFrame([{"reason": "fresh"}]).to_csv(
        scan_dir / "parity_futures_join_audit.csv",
        index=False,
    )
    scan_parameters = {
        "market": "india_nse_index_derivatives",
        "chain_column_map": None,
        "futures_column_map": None,
        "timestamp_unit": "ns",
        "timestamp_tz": None,
        "filter_session": True,
        "lot_size": 75,
        "option_tick": 0.05,
        "future_tick": 0.05,
        "asof_latency_ns": 0,
        "max_futures_quote_age_ns": 100_000,
        "depth_fraction": scan_depth_fraction,
    }
    write_experiment_manifest(
        scan_dir,
        run_type=PARITY_SCAN_RUN_TYPE,
        inputs={
            "chain": chain_path,
            "futures": futures_path,
        },
        parameters=scan_parameters,
    )

    pd.DataFrame([{"total_opportunities": 2}]).to_csv(
        edge_dir / "parity_edge_metrics.csv",
        index=False,
    )
    pd.DataFrame([{"check": "fixture", "passed": edge_passed}]).to_csv(
        edge_dir / "parity_edge_checks.csv",
        index=False,
    )
    edge_summary(passed=edge_passed).to_csv(edge_dir / "parity_edge_summary.csv", index=False)
    write_experiment_manifest(
        edge_dir,
        run_type=PARITY_EDGE_RUN_TYPE,
        inputs={
            "scan": scan_dir,
            "scan_manifest": scan_dir / "manifest.json",
        },
        parameters={"thresholds": {}},
    )

    sweep_summary(passed_scenarios=passed_scenarios).to_csv(sweep_dir / "sweep_summary.csv", index=False)
    runs = sweep_runs(proof_passed=bool(passed_scenarios))
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
    robustness = latency_seed_robustness(
        group_passed=bool(passed_scenarios),
        pass_rate=1.0 if passed_scenarios else 0.0,
    )
    if not passed_scenarios:
        robustness.loc[:, "latency_seed_passed_runs"] = 0
    robustness.to_csv(
        sweep_dir / "latency_seed_robustness.csv",
        index=False,
    )
    runs.to_csv(sweep_dir / "sweep_runs.csv", index=False)
    proof_dir = sweep_dir / "proof"
    proof_dir.mkdir()
    pd.DataFrame([{"run": "latency_group__seed_11"}]).to_csv(
        proof_dir / "proof_metrics.csv",
        index=False,
    )
    pd.DataFrame([{"check": "fixture"}]).to_csv(
        proof_dir / "proof_checks.csv",
        index=False,
    )
    pd.DataFrame([{"passed": bool(passed_scenarios)}]).to_csv(
        proof_dir / "proof_summary.csv",
        index=False,
    )
    write_experiment_manifest(
        sweep_dir,
        run_type=PARITY_SWEEP_RUN_TYPE,
        inputs={
            "chain": chain_path,
            "futures": sweep_futures_path,
        },
        parameters={
            "market": "india_nse_index_derivatives",
            "chain_column_map": None,
            "futures_column_map": None,
            "timestamp_unit": "ns",
            "timestamp_tz": None,
            "filter_session": True,
            "lot_size": 75,
            "option_tick": sweep_option_tick,
            "future_tick": 0.05,
            "max_futures_quote_age_ns": 100_000,
            "depth_fraction_values": [0.25],
            "asof_latency_ns_values": [0],
        },
    )
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
    assert config["metrics"]["scan_manifest_current"]
    assert config["metrics"]["edge_manifest_current"]
    assert config["metrics"]["sweep_manifest_current"]
    assert config["metrics"]["scan_edge_manifest_bound"]
    assert config["metrics"]["scan_sweep_source_match"]
    assert config["metrics"]["scan_sweep_static_parameters_match"]
    assert config["metrics"]["scan_sweep_selected_scenario_match"]
    assert set(
        report.checks["check"]
    ).issuperset(
        {
            "scan_manifest_current",
            "edge_manifest_current",
            "sweep_manifest_current",
            "scan_edge_manifest_bound",
            "scan_sweep_source_match",
            "scan_sweep_static_parameters_match",
            "scan_sweep_selected_scenario_match",
        }
    )
    assert manifest["run_type"] == "promotion_report"
    assert manifest["parameters"]["strategy"] == "parity_box"
    assert manifest["extra"]["promotion_source"] == "parity_scan_edge_sweep"
    assert "latency_seed_robustness" in manifest["inputs"]
    assert "scan_manifest" in manifest["inputs"]
    assert "edge_manifest" in manifest["inputs"]
    assert "sweep_manifest" in manifest["inputs"]
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="promotion_report",
        required_artifacts=[
            "promotion_candidate.csv",
            "promotion_checks.csv",
            "promotion_summary.csv",
            "candidate_config.json",
        ],
        require_input_fingerprints=True,
    )
    assert integrity.passed
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()


def test_parity_candidate_promotion_rejects_cross_source_and_parameter_mismatch(
    tmp_path,
):
    cases = [
        (
            "source",
            {"sweep_source_matches": False},
            "scan_sweep_source_match",
        ),
        (
            "static",
            {"sweep_option_tick": 0.1},
            "scan_sweep_static_parameters_match",
        ),
        (
            "selected",
            {"scan_depth_fraction": 0.5},
            "scan_sweep_selected_scenario_match",
        ),
    ]
    for name, kwargs, failed_check in cases:
        scan_dir, edge_dir, sweep_dir = write_inputs(
            tmp_path / name,
            **kwargs,
        )
        report = write_parity_candidate_promotion(
            scan_dir,
            edge_audit_dir=edge_dir,
            sweep_dir=sweep_dir,
            output_dir=tmp_path / name / "promotion",
        )

        assert not report.ready
        assert failed_check in set(
            report.checks.loc[
                ~report.checks["passed"].astype(bool),
                "check",
            ]
        )


def test_parity_candidate_promotion_rejects_sweep_artifact_drift(
    tmp_path,
):
    scan_dir, edge_dir, sweep_dir = write_inputs(
        tmp_path,
    )
    runs_path = sweep_dir / "sweep_runs.csv"
    runs = pd.read_csv(runs_path)
    runs.loc[0, "net_pnl"] = 999.0
    runs.to_csv(runs_path, index=False)

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    assert not report.ready
    assert "sweep_manifest_current" in set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert report.summary.loc[0, "sweep_manifest_error"] == (
        "artifact_drift"
    )


def test_parity_candidate_promotion_rejects_edge_from_another_scan(
    tmp_path,
):
    _, edge_a, _ = write_inputs(
        tmp_path / "run_a",
    )
    scan_b, _, sweep_b = write_inputs(
        tmp_path / "run_b",
    )

    report = write_parity_candidate_promotion(
        scan_b,
        edge_audit_dir=edge_a,
        sweep_dir=sweep_b,
        output_dir=tmp_path / "promotion",
    )

    assert not report.ready
    assert bool(report.summary.loc[0, "scan_manifest_current"])
    assert bool(report.summary.loc[0, "edge_manifest_current"])
    assert not bool(
        report.summary.loc[0, "scan_edge_manifest_bound"]
    )
    assert "scan_edge_manifest_bound" in set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )


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
