import json

import pandas as pd

from hft_cli import main
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.proof import (
    ProofThresholds,
    evaluate_replay_dirs,
    verify_proof_report,
    write_proof_report,
)
from tests.data_readiness_helpers import reseal_experiment_manifest


def write_run(
    path,
    *,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    net_pnl=120.0,
    fills=12,
    turnover=6000.0,
    total_costs=6.0,
    maker_share=0.75,
    otr=3.0,
    otr_breached=False,
    equity_values=(0.0, 80.0, 65.0, 150.0),
    regime_changes=(50.0, 70.0),
    spread_net=40.0,
    markouts=(10.0, -2.0, 4.0),
):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "strategy": strategy,
                "market": market,
                "scenario_key": f"strategy={strategy}|market={market}|trigger_ticks=2",
                "net_pnl": net_pnl,
                "total_costs": total_costs,
                "orders_sent": 20,
                "fills": fills,
                "order_to_trade_ratio": otr,
                "otr_limit": 50.0,
                "otr_breached": otr_breached,
                "pending_order_risk_reservation_enabled": True,
                "aggressive_self_cross_prevention_enabled": True,
                "venue_order_validation_enabled": True,
                "shared_event_liquidity_enabled": True,
                "persistent_displayed_liquidity_enabled": True,
                "arrival_queue_initialization_enabled": True,
                "limit_orders_sent": 4,
                "queue_initialization_events": 4,
                "deferred_queue_initialization_events": 3,
                "uninitialized_limit_orders": 0,
                "max_queue_initialization_lag_ns": 125_000,
                "residual_resting_transition_events": 2,
                "residual_resting_transition_qty": 50,
                "deferred_residual_queue_events": 1,
                "unresolved_residual_queue_events": 0,
                "max_residual_queue_initialization_lag_ns": 2_000,
                "passive_price_through_depth_constrained_enabled": True,
                "passive_price_through_events": 3,
                "passive_price_through_requested_qty": 225,
                "passive_price_through_filled_qty": 150,
                "passive_price_through_shortfall_qty": 75,
                "passive_price_through_incomplete_events": 1,
                "terminal_liquidation_depth_constrained_enabled": True,
                "terminal_liquidation_events": 1,
                "terminal_liquidation_requested_qty": 75,
                "terminal_liquidation_filled_qty": 75,
                "terminal_liquidation_shortfall_qty": 0,
                "terminal_liquidation_incomplete_events": 0,
                "terminal_residual_position_qty": 0,
                "terminal_residual_instruments": 0,
                "terminal_liquidation_complete": True,
                "liquidity_shortfall_events": 2,
                "liquidity_shortfall_qty": 75,
                "displayed_liquidity_shortfall_events": 1,
                "displayed_liquidity_shortfall_qty": 50,
                "trade_print_shortfall_events": 1,
                "trade_print_shortfall_qty": 25,
                "carried_depletion_shortfall_events": 1,
                "carried_depletion_shortfall_qty": 50,
                "pretrade_rejections": 0,
                "venue_rule_rejections": 0,
                "position_risk_rejections": 0,
                "self_cross_rejections": 0,
                "turnover": turnover,
                "maker_share": maker_share,
                "portfolio_delta": 0.0,
                "portfolio_vega": 0.0,
            }
        ]
    ).to_csv(path / "summary.csv", index=False)
    pd.DataFrame(
        [{"ts": idx, "equity": value} for idx, value in enumerate(equity_values)]
    ).to_csv(path / "equity.csv", index=False)
    pd.DataFrame(
        [{"regime": f"r{idx}", "equity_change": value} for idx, value in enumerate(regime_changes)]
    ).to_csv(path / "equity_by_regime.csv", index=False)
    pd.DataFrame([{"instrument_id": "OPT", "net_spread": spread_net}]).to_csv(
        path / "spread_summary.csv",
        index=False,
    )
    pd.DataFrame([{"horizon_ns": 100, "markout": value} for value in markouts]).to_csv(
        path / "markouts.csv",
        index=False,
    )
    source = path.parent / f"{path.name}_source.csv"
    source.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    write_experiment_manifest(
        path,
        run_type="unit_replay",
        inputs={"source": source},
    )
    return source


def test_evaluate_replay_dirs_passes_explicit_proof_thresholds(tmp_path):
    run_dir = tmp_path / "leadlag_pass"
    write_run(run_dir)

    report = evaluate_replay_dirs(
        [run_dir],
        thresholds=ProofThresholds(
            min_net_pnl=50.0,
            min_fills=5,
            max_drawdown=20.0,
            max_otr=10.0,
            min_maker_share=0.5,
            min_worst_regime_equity_change=0.0,
            min_markout_mean=0.0,
            min_spread_net=10.0,
        ),
    )

    assert report.passed
    assert report.metrics.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.metrics.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.metrics.iloc[0]["max_drawdown"] == 15.0
    assert report.metrics.iloc[0]["worst_regime_equity_change"] == 50.0
    assert report.metrics.iloc[0]["markout_mean"] == 4.0
    assert bool(
        report.metrics.iloc[0]["pending_order_risk_reservation_enabled"]
    )
    assert bool(
        report.metrics.iloc[0]["aggressive_self_cross_prevention_enabled"]
    )
    assert bool(report.metrics.iloc[0]["venue_order_validation_enabled"])
    assert bool(report.metrics.iloc[0]["shared_event_liquidity_enabled"])
    assert bool(
        report.metrics.iloc[0]["persistent_displayed_liquidity_enabled"]
    )
    assert bool(report.metrics.iloc[0]["arrival_queue_initialization_enabled"])
    assert int(report.metrics.iloc[0]["limit_orders_sent"]) == 4
    assert int(report.metrics.iloc[0]["queue_initialization_events"]) == 4
    assert int(
        report.metrics.iloc[0]["deferred_queue_initialization_events"]
    ) == 3
    assert int(report.metrics.iloc[0]["uninitialized_limit_orders"]) == 0
    assert int(report.metrics.iloc[0]["max_queue_initialization_lag_ns"]) == 125_000
    assert int(
        report.metrics.iloc[0]["residual_resting_transition_events"]
    ) == 2
    assert int(report.metrics.iloc[0]["residual_resting_transition_qty"]) == 50
    assert int(report.metrics.iloc[0]["deferred_residual_queue_events"]) == 1
    assert int(report.metrics.iloc[0]["unresolved_residual_queue_events"]) == 0
    assert int(
        report.metrics.iloc[0]["max_residual_queue_initialization_lag_ns"]
    ) == 2_000
    assert bool(
        report.metrics.iloc[0][
            "passive_price_through_depth_constrained_enabled"
        ]
    )
    assert int(report.metrics.iloc[0]["passive_price_through_events"]) == 3
    assert int(
        report.metrics.iloc[0]["passive_price_through_requested_qty"]
    ) == 225
    assert int(
        report.metrics.iloc[0]["passive_price_through_filled_qty"]
    ) == 150
    assert int(
        report.metrics.iloc[0]["passive_price_through_shortfall_qty"]
    ) == 75
    assert int(
        report.metrics.iloc[0]["passive_price_through_incomplete_events"]
    ) == 1
    assert bool(
        report.metrics.iloc[0][
            "terminal_liquidation_depth_constrained_enabled"
        ]
    )
    assert int(report.metrics.iloc[0]["terminal_liquidation_events"]) == 1
    assert int(
        report.metrics.iloc[0]["terminal_liquidation_requested_qty"]
    ) == 75
    assert int(report.metrics.iloc[0]["terminal_liquidation_filled_qty"]) == 75
    assert int(
        report.metrics.iloc[0]["terminal_liquidation_shortfall_qty"]
    ) == 0
    assert bool(report.metrics.iloc[0]["terminal_liquidation_complete"])
    assert int(report.metrics.iloc[0]["liquidity_shortfall_events"]) == 2
    assert int(report.metrics.iloc[0]["liquidity_shortfall_qty"]) == 75
    assert int(report.metrics.iloc[0]["carried_depletion_shortfall_events"]) == 1
    assert int(report.metrics.iloc[0]["carried_depletion_shortfall_qty"]) == 50
    assert int(report.metrics.iloc[0]["pretrade_rejections"]) == 0
    assert int(report.metrics.iloc[0]["venue_rule_rejections"]) == 0
    assert report.checks["passed"].all()


def test_proof_report_rejects_incomplete_terminal_liquidation(tmp_path):
    run_dir = tmp_path / "residual_inventory"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "terminal_liquidation_filled_qty"] = 25
    summary.loc[0, "terminal_liquidation_shortfall_qty"] = 50
    summary.loc[0, "terminal_liquidation_incomplete_events"] = 1
    summary.loc[0, "terminal_residual_position_qty"] = 50
    summary.loc[0, "terminal_residual_instruments"] = 1
    summary.loc[0, "terminal_liquidation_complete"] = False
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == ["terminal_liquidation_complete"]
    assert failed.iloc[0]["reason"] == (
        "terminal liquidation left residual inventory"
    )


def test_write_proof_report_outputs_metrics_checks_and_summary(tmp_path):
    run_dir = tmp_path / "parity_pass"
    out_dir = tmp_path / "proof"
    write_run(run_dir, net_pnl=25.0, fills=4)

    report = write_proof_report(
        [run_dir],
        output_dir=out_dir,
        thresholds=ProofThresholds(min_net_pnl=10.0, min_fills=1),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "proof_metrics.csv").exists()
    assert (out_dir / "proof_checks.csv").exists()
    assert (out_dir / "proof_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "proof_summary.csv")
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    verification = verify_proof_report(out_dir)
    assert bool(summary.loc[0, "non_authorizing"])
    assert not bool(summary.loc[0, "authorizes_routing"])
    assert not bool(summary.loc[0, "authorizes_submission"])
    assert manifest["parameters"]["run_names"] is None
    assert set(manifest["inputs"]) == {
        "run_dependencies",
        "run_dirs",
        "run_manifests",
    }
    assert manifest["extra"] == {
        "all_passed": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "non_authorizing": True,
    }
    assert verification.verified
    assert verification.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.replay_manifests_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert verification.replay_manifest_count == 1
    assert verification.replay_manifest_current_count == 1


def test_proof_report_blocks_mixed_strategy_or_market_runs(tmp_path):
    leadlag = tmp_path / "leadlag_pass"
    imbalance = tmp_path / "imbalance_pass"
    write_run(leadlag, strategy="leadlag", market="india_nse_index_derivatives")
    write_run(imbalance, strategy="imbalance", market="us_equities_regular")

    report = evaluate_replay_dirs(
        [leadlag, imbalance],
        thresholds=ProofThresholds(min_net_pnl=1.0, min_fills=1),
    )

    assert not report.passed
    summary = report.summary.iloc[0]
    assert bool(summary["mixed_identity"])
    assert int(summary["strategy_count"]) == 2
    assert int(summary["market_count"]) == 2
    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert {"same_strategy", "same_market"} <= failed


def test_proof_report_fails_with_actionable_reasons(tmp_path):
    run_dir = tmp_path / "bad_run"
    write_run(
        run_dir,
        net_pnl=-5.0,
        fills=0,
        otr=75.0,
        otr_breached=True,
        equity_values=(0.0, 20.0, -20.0),
        regime_changes=(-15.0,),
        markouts=(-3.0, -1.0),
    )

    report = evaluate_replay_dirs(
        [run_dir],
        thresholds=ProofThresholds(
            min_net_pnl=1.0,
            min_fills=1,
            max_drawdown=10.0,
            max_otr=50.0,
            min_worst_regime_equity_change=0.0,
            min_markout_mean=0.0,
        ),
    )

    failed_checks = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert failed_checks == {
        "net_pnl",
        "fills",
        "otr_not_breached",
        "max_drawdown",
        "order_to_trade_ratio",
        "worst_regime_equity_change",
        "markout_mean",
    }
    assert report.summary.iloc[0]["failed_runs"] == 1
    assert report.checks.loc[~report.checks["passed"], "reason"].str.len().min() > 0


def test_unified_cli_proof_report_dispatch_and_fail_on_breach(tmp_path):
    pass_run = tmp_path / "pass_run"
    fail_run = tmp_path / "fail_run"
    pass_out = tmp_path / "pass_proof"
    fail_out = tmp_path / "fail_proof"
    write_run(pass_run, net_pnl=20.0, fills=3)
    write_run(fail_run, net_pnl=-1.0, fills=0)

    pass_code = main(
        [
            "proof-report",
            "--runs",
            str(pass_run),
            "--out",
            str(pass_out),
            "--min-net-pnl",
            "1",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )
    fail_code = main(
        [
            "proof-report",
            "--runs",
            str(fail_run),
            "--out",
            str(fail_out),
            "--min-net-pnl",
            "1",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )
    failed_proof_verification = verify_proof_report(fail_out)
    failed_verify_code = main(
        [
            "verify-proof-report",
            "--report",
            str(fail_out),
            "--fail-on-breach",
        ]
    )

    assert pass_code == 0
    assert fail_code == 2
    assert failed_proof_verification.verified
    assert not failed_proof_verification.passed
    assert failed_verify_code == 0
    assert (pass_out / "proof_summary.csv").exists()
    assert (fail_out / "proof_checks.csv").exists()


def test_proof_verifier_rejects_resealed_artifact_tampering(tmp_path):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    write_run(run_dir)
    write_proof_report(
        [run_dir],
        output_dir=out_dir,
        thresholds=ProofThresholds(min_net_pnl=1.0, min_fills=1),
    )
    summary_path = out_dir / "proof_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "total_net_pnl"] = 999999.0
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)
    code = main(
        [
            "verify-proof-report",
            "--report",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    assert generic.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.replay_manifests_current
    assert not verification.artifacts_consistent
    assert not verification.verified
    assert verification.error == (
        "artifacts do not reconstruct from replay inputs"
    )
    assert code == 2


def test_proof_verifier_rejects_resealed_extra_order_sidecar(tmp_path):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    write_run(run_dir)
    write_proof_report([run_dir], output_dir=out_dir)
    pd.DataFrame(
        [{"instrument_id": "NIFTY", "side": "BUY", "qty": 1}]
    ).to_csv(out_dir / "unexpected_orders.csv", index=False)
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)

    assert generic.passed
    assert generic.artifact_count == 4
    assert not verification.artifacts_consistent
    assert not verification.verified


def test_proof_verifier_rejects_resealed_outer_manifest_after_source_drift(
    tmp_path,
):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    source = write_run(run_dir)
    write_proof_report([run_dir], output_dir=out_dir)
    source.write_text("ts,bid,ask\n1,99,102\n", encoding="utf-8")
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)

    assert generic.passed
    assert verification.inputs_current
    assert not verification.replay_manifests_current
    assert verification.replay_manifest_count == 1
    assert verification.replay_manifest_current_count == 0
    assert not verification.verified
    assert verification.error == (
        "replay manifests are missing, stale, or unfingerprinted"
    )
