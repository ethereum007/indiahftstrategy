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
from reports.parity_edge import (
    PARITY_EDGE_RUN_TYPE,
    write_parity_edge_audit,
)
from reports.parity_order_plan import ParityOrderPlanConfig, build_parity_order_plan
from reports.proof import ProofThresholds
from scanners.run_parity_box import PARITY_SCAN_RUN_TYPE, run_scan
from strategies.run_parity_sweep import (
    PARITY_SWEEP_RUN_TYPE,
    run_parity_sweep,
)


def ns_ist(value):
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def write_actual_parity_books(root):
    timestamps = [
        ns_ist("2026-06-10 09:15:00"),
        ns_ist("2026-06-10 09:15:00.000100"),
        ns_ist("2026-06-10 09:15:00.000200"),
    ]
    chain_path = root / "chain.csv"
    futures_path = root / "futures.csv"
    pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": (
                    300 if index < 2 else 299
                ),
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for index, ts in enumerate(timestamps)
        ]
    ).to_csv(chain_path, index=False)
    pd.DataFrame(
        [
            {
                "ts": ts,
                "bid": 1100.0,
                "ask": 1101.0,
                "bid_qty": 300,
                "ask_qty": 300,
            }
            for ts in timestamps
        ]
    ).to_csv(futures_path, index=False)
    return chain_path, futures_path


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


def write_replay_evidence(
    run_dir,
    *,
    chain_path,
    futures_path,
    latency_seed,
    net_pnl,
    max_drawdown,
    realized_net_edge=5.0,
):
    run_dir.mkdir(parents=True)
    signal = parity_opportunities()
    signal.to_csv(run_dir / "signals.csv", index=False)
    pd.DataFrame(
        [
            {
                "signal_index": 0,
                "direction": "buy_synthetic_sell_future",
                "strike": 25000.0,
                "signal_ts_ns": 200,
                "signal_net_edge": 440.0,
                "edge_revalidation_qty": 75,
                "guard_passed": True,
                "guard_reason": "ready",
            }
        ]
    ).to_csv(
        run_dir / "parity_execution_guard.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "signal_index": 0,
                "direction": "buy_synthetic_sell_future",
                "strike": 25000.0,
                "signal_ts_ns": 200,
                "requested_qty": 75,
                "routing_complete": True,
                "fills_complete": True,
                "partial": False,
                "realized_edge_evaluable": True,
                "realized_net_edge": realized_net_edge,
                "realized_edge_positive": (
                    realized_net_edge > 0.0
                ),
            }
        ]
    ).to_csv(run_dir / "legging.csv", index=False)
    pd.DataFrame(
        [
            {
                "net_pnl": net_pnl,
                "fills": 3,
                "max_drawdown": max_drawdown,
            }
        ]
    ).to_csv(run_dir / "summary.csv", index=False)
    pd.DataFrame(
        [
            {"ts": 0, "equity": 0.0},
            {"ts": 1, "equity": -max_drawdown},
        ]
    ).to_csv(run_dir / "equity.csv", index=False)
    write_experiment_manifest(
        run_dir,
        run_type="parity_replay",
        inputs={
            "chain": chain_path,
            "futures": futures_path,
        },
        parameters={
            "timestamp_unit": "ns",
            "timestamp_tz": None,
            "filter_session": True,
            "lot_size": 75,
            "option_tick": 0.05,
            "future_tick": 0.05,
            "depth_fraction": 0.25,
            "asof_latency_ns": 0,
            "max_futures_quote_age_ns": 100_000,
            "feed_latency_us": 0.0,
            "order_latency_us": 0.0,
            "latency_jitter_us": 15.0,
            "latency_seed": latency_seed,
            "max_signal_age_ns": 1_000_000,
            "max_leg_book_age_ns": 200_000,
            "max_leg_book_skew_ns": 50_000,
            "max_qty": None,
            "max_position_lots": 20,
            "signal_limit": None,
        },
    )


def refresh_manifest(
    run_dir,
    *,
    parameter_updates=None,
    input_updates=None,
):
    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    def restore_input(value):
        if isinstance(value, dict):
            if "path" in value:
                return value["path"]
            return {
                key: restore_input(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [restore_input(item) for item in value]
        return value

    inputs = {
        key: restore_input(value)
        for key, value in manifest["inputs"].items()
    }
    inputs.update(input_updates or {})
    parameters = dict(manifest["parameters"])
    parameters.update(parameter_updates or {})
    write_experiment_manifest(
        run_dir,
        run_type=manifest["run_type"],
        inputs=inputs,
        parameters=parameters,
        extra=manifest["extra"],
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
    for run in (first, second):
        run_dir = sweep_dir / "runs" / str(run["run"])
        run["run_dir"] = str(run_dir.resolve())
        write_replay_evidence(
            run_dir,
            chain_path=chain_path,
            futures_path=sweep_futures_path,
            latency_seed=int(run["latency_seed"]),
            net_pnl=float(run["net_pnl"]),
            max_drawdown=float(run["max_drawdown"]),
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
            "max_signal_age_ns": 1_000_000,
            "max_leg_book_age_ns": 200_000,
            "max_leg_book_skew_ns": 50_000,
            "max_qty": None,
            "max_position_lots": 20,
            "signal_limit": None,
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


def test_parity_candidate_promotion_binds_real_worst_seed_replay(
    tmp_path,
):
    chain_path, futures_path = write_actual_parity_books(
        tmp_path
    )
    scan_dir = tmp_path / "scan"
    edge_dir = tmp_path / "edge"
    sweep_dir = tmp_path / "sweep"
    run_scan(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=scan_dir,
        depth_fraction=0.25,
    )
    edge = write_parity_edge_audit(
        scan_dir,
        output_dir=edge_dir,
    )
    sweep = run_parity_sweep(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=sweep_dir,
        depth_fraction_values=[0.25],
        asof_latency_ns_values=[0],
        feed_latency_us_values=[0.0],
        order_latency_us_values=[0.0],
        latency_jitter_us_values=[0.0],
        latency_seed_values=[17],
        proof_thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    assert edge.passed
    assert sweep.proof.passed
    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["selected_replay_manifest_current"])
    assert bool(summary["selected_replay_source_match"])
    assert bool(summary["selected_replay_parameters_match"])
    assert bool(summary["selected_replay_summary_match"])
    assert int(summary["candidate_replay_signal_match_count"]) == 1
    assert int(summary["candidate_replay_guard_passed_attempts"]) == 1
    assert bool(summary["candidate_replay_execution_complete"])
    assert bool(summary["candidate_replay_realized_edge_positive"])


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
    assert config["metrics"]["selected_replay_run"] == (
        "latency_group__seed_22"
    )
    assert config["metrics"]["selected_replay_run_dir_bound"]
    assert config["metrics"]["selected_replay_manifest_current"]
    assert config["metrics"]["selected_replay_source_match"]
    assert config["metrics"]["selected_replay_parameters_match"]
    assert config["metrics"]["selected_replay_summary_match"]
    assert len(config["metrics"]["candidate_opportunity_id"]) == 64
    assert config["metrics"][
        "candidate_replay_signal_match_count"
    ] == 1
    assert config["metrics"]["candidate_replay_signal_index"] == 0
    assert config["metrics"][
        "candidate_replay_guard_passed_attempts"
    ] == 1
    assert config["metrics"]["candidate_replay_execution_count"] == 1
    assert config["metrics"]["candidate_replay_execution_complete"]
    assert config["metrics"][
        "candidate_replay_realized_edge_positive"
    ]
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
            "selected_replay_run_dir_bound",
            "selected_replay_manifest_current",
            "selected_replay_source_match",
            "selected_replay_parameters_match",
            "selected_replay_summary_match",
            "candidate_replay_signal_unique",
            "candidate_replay_guard_attempted",
            "candidate_replay_guard_passed",
            "candidate_replay_execution_unique",
            "candidate_replay_execution_complete",
            "candidate_replay_realized_edge_positive",
        }
    )
    assert manifest["run_type"] == "promotion_report"
    assert manifest["parameters"]["strategy"] == "parity_box"
    assert manifest["extra"]["promotion_source"] == "parity_scan_edge_sweep"
    assert "latency_seed_robustness" in manifest["inputs"]
    assert "scan_manifest" in manifest["inputs"]
    assert "edge_manifest" in manifest["inputs"]
    assert "sweep_manifest" in manifest["inputs"]
    assert "selected_replay_manifest" in manifest["inputs"]
    assert "selected_replay_signals" in manifest["inputs"]
    assert "selected_replay_execution_guard" in manifest["inputs"]
    assert "selected_replay_legging" in manifest["inputs"]
    assert "selected_replay_summary" in manifest["inputs"]
    assert "selected_replay_equity" in manifest["inputs"]
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


def test_parity_candidate_promotion_rejects_unbound_replay_evidence(
    tmp_path,
):
    scan_dir, edge_dir, sweep_dir = write_inputs(tmp_path)
    runs_path = sweep_dir / "sweep_runs.csv"
    runs = pd.read_csv(runs_path)
    selected = runs["run"].eq("latency_group__seed_22")
    runs.loc[selected, "run_dir"] = str(
        (
            sweep_dir
            / "runs"
            / "latency_group__seed_11"
        ).resolve()
    )
    runs.to_csv(runs_path, index=False)
    refresh_manifest(sweep_dir)

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert "selected_replay_run_dir_bound" in failed
    assert not bool(
        report.summary.loc[
            0,
            "selected_replay_run_dir_bound",
        ]
    )


def test_parity_candidate_promotion_rejects_candidate_evidence_mismatch(
    tmp_path,
):
    cases = [
        (
            "signal",
            "signals.csv",
            {"qty": 74},
            False,
            "candidate_replay_signal_unique",
        ),
        (
            "duplicate_signal",
            "signals.csv",
            {},
            True,
            "candidate_replay_signal_unique",
        ),
        (
            "guard",
            "parity_execution_guard.csv",
            {"guard_passed": False},
            False,
            "candidate_replay_guard_passed",
        ),
        (
            "guard_qty",
            "parity_execution_guard.csv",
            {"edge_revalidation_qty": 50},
            False,
            "candidate_replay_guard_passed",
        ),
        (
            "fills",
            "legging.csv",
            {"fills_complete": False},
            False,
            "candidate_replay_execution_complete",
        ),
        (
            "realized_edge",
            "legging.csv",
            {
                "realized_net_edge": -1.0,
                "realized_edge_positive": False,
            },
            False,
            "candidate_replay_realized_edge_positive",
        ),
        (
            "summary",
            "summary.csv",
            {"net_pnl": 999.0},
            False,
            "selected_replay_summary_match",
        ),
        (
            "equity",
            "equity.csv",
            {"equity": -999.0},
            False,
            "selected_replay_summary_match",
        ),
    ]
    for (
        name,
        artifact,
        updates,
        duplicate,
        failed_check,
    ) in cases:
        root = tmp_path / name
        scan_dir, edge_dir, sweep_dir = write_inputs(root)
        replay_dir = (
            sweep_dir
            / "runs"
            / "latency_group__seed_22"
        )
        artifact_path = replay_dir / artifact
        frame = pd.read_csv(artifact_path)
        for column, value in updates.items():
            frame.loc[0, column] = value
        if duplicate:
            frame = pd.concat(
                [frame, frame.iloc[[0]]],
                ignore_index=True,
            )
        frame.to_csv(artifact_path, index=False)
        refresh_manifest(replay_dir)
        refresh_manifest(sweep_dir)

        report = write_parity_candidate_promotion(
            scan_dir,
            edge_audit_dir=edge_dir,
            sweep_dir=sweep_dir,
            output_dir=root / "promotion",
        )

        failed = set(
            report.checks.loc[
                ~report.checks["passed"].astype(bool),
                "check",
            ]
        )
        assert not report.ready
        assert bool(
            report.summary.loc[
                0,
                "selected_replay_manifest_current",
            ]
        )
        assert failed_check in failed


def test_parity_candidate_promotion_rejects_replay_lineage_mismatch(
    tmp_path,
):
    cases = [
        (
            "source",
            {},
            {"futures": "other_futures.csv"},
            "selected_replay_source_match",
        ),
        (
            "parameters",
            {"latency_seed": 999},
            {},
            "selected_replay_parameters_match",
        ),
    ]
    for name, parameter_updates, input_names, failed_check in cases:
        root = tmp_path / name
        scan_dir, edge_dir, sweep_dir = write_inputs(root)
        replay_dir = (
            sweep_dir
            / "runs"
            / "latency_group__seed_22"
        )
        input_updates = {}
        if input_names:
            other_futures = root / "source" / input_names[
                "futures"
            ]
            pd.DataFrame(
                [{"ts": 1, "value": 999.0}]
            ).to_csv(other_futures, index=False)
            input_updates["futures"] = other_futures
        refresh_manifest(
            replay_dir,
            parameter_updates=parameter_updates,
            input_updates=input_updates,
        )
        refresh_manifest(sweep_dir)

        report = write_parity_candidate_promotion(
            scan_dir,
            edge_audit_dir=edge_dir,
            sweep_dir=sweep_dir,
            output_dir=root / "promotion",
        )

        failed = set(
            report.checks.loc[
                ~report.checks["passed"].astype(bool),
                "check",
            ]
        )
        assert not report.ready
        assert bool(
            report.summary.loc[
                0,
                "selected_replay_manifest_current",
            ]
        )
        assert failed_check in failed


def test_parity_candidate_promotion_rejects_replay_artifact_drift(
    tmp_path,
):
    scan_dir, edge_dir, sweep_dir = write_inputs(tmp_path)
    replay_dir = (
        sweep_dir
        / "runs"
        / "latency_group__seed_22"
    )
    summary_path = replay_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "net_pnl"] = 999.0
    summary.to_csv(summary_path, index=False)

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert "selected_replay_manifest_current" in failed
    assert report.summary.loc[
        0,
        "selected_replay_manifest_error",
    ] == "artifact_drift"


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
