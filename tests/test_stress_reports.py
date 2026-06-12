import pandas as pd

from hft_cli import main
from reports.stress import StressConfig, stress_replay_dirs, write_stress_report


def write_replay(path):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "net_pnl": 100.0,
                "total_costs": 5.0,
                "orders_sent": 2,
                "fills": 2,
                "order_to_trade_ratio": 1.0,
                "otr_limit": 50.0,
                "otr_breached": False,
                "turnover": 2050.0,
                "maker_share": 0.5,
                "portfolio_delta": 0.0,
                "portfolio_vega": 0.0,
            }
        ]
    ).to_csv(path / "summary.csv", index=False)
    pd.DataFrame(
        [
            {"ts": 1, "equity": 60.0},
            {"ts": 2, "equity": 100.0},
        ]
    ).to_csv(path / "equity.csv", index=False)
    pd.DataFrame(
        [
            {
                "ts_ns": 1,
                "instrument_id": "OPT",
                "oid": 1,
                "side": 1,
                "qty": 10,
                "price": 100.0,
                "cost": 2.0,
                "maker": False,
            },
            {
                "ts_ns": 2,
                "instrument_id": "OPT",
                "oid": 2,
                "side": -1,
                "qty": 10,
                "price": 105.0,
                "cost": 3.0,
                "maker": True,
            },
        ]
    ).to_csv(path / "fills.csv", index=False)


def test_stress_replay_dirs_applies_cost_slippage_and_adverse_penalties(tmp_path):
    replay = tmp_path / "replay"
    write_replay(replay)

    report = stress_replay_dirs(
        [replay],
        config=StressConfig(
            cost_multipliers=[2.0],
            slippage_ticks=[1.0],
            adverse_bps=[10.0],
            tick_size=0.05,
            min_net_pnl=90.0,
        ),
    )

    row = report.results.iloc[0]
    assert row["extra_cost"] == 5.0
    assert row["slippage_cost"] == 1.0
    assert row["adverse_cost"] == 2.05
    assert row["pnl_penalty"] == 8.05
    assert row["stressed_net_pnl"] == 91.95
    assert row["passed"]
    assert report.passed


def test_write_stress_report_outputs_results_summary_and_manifest(tmp_path):
    replay = tmp_path / "replay"
    out_dir = tmp_path / "stress"
    write_replay(replay)

    report = write_stress_report(
        [replay],
        output_dir=out_dir,
        config=StressConfig(
            cost_multipliers=[1.0, 2.0],
            slippage_ticks=[0.0],
            adverse_bps=[0.0],
            min_net_pnl=90.0,
        ),
    )

    assert len(report.results) == 2
    assert (out_dir / "stress_results.csv").exists()
    assert (out_dir / "stress_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_stress_replay_can_fail_on_breach(tmp_path):
    replay = tmp_path / "replay"
    out_dir = tmp_path / "stress_cli"
    write_replay(replay)

    code = main(
        [
            "stress-replay",
            "--runs",
            str(replay),
            "--out",
            str(out_dir),
            "--cost-multiplier",
            "20",
            "--slippage-ticks",
            "10",
            "--adverse-bps",
            "100",
            "--min-net-pnl",
            "90",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "stress_results.csv").exists()
    assert (out_dir / "manifest.json").exists()
