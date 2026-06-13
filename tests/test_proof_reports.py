import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds, evaluate_replay_dirs, write_proof_report


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
    assert report.checks["passed"].all()


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

    assert pass_code == 0
    assert fail_code == 2
    assert (pass_out / "proof_summary.csv").exists()
    assert (fail_out / "proof_checks.csv").exists()
