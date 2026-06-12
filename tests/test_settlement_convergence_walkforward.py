import json

import pandas as pd

from hft_cli import main
from reports.settlement_convergence import SettlementConvergenceThresholds
from reports.settlement_convergence_walkforward import (
    SettlementConvergenceWalkForwardThresholds,
    write_settlement_convergence_walkforward,
)


def index_ticks(offset=0):
    return pd.DataFrame(
        [
            {"ts": offset + 100, "bid": 99.95, "ask": 100.05},
            {"ts": offset + 200, "bid": 103.95, "ask": 104.05},
            {"ts": offset + 300, "bid": 105.95, "ask": 106.05},
        ]
    )


def option_chain(offset=0, call_ask=1.0):
    return pd.DataFrame(
        [
            {
                "ts": offset + 200,
                "expiry": "2026-06-10",
                "strike": 100.0,
                "call_bid": max(call_ask - 0.05, 0.05),
                "call_ask": call_ask,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 0.05,
                "put_ask": 0.10,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
        ]
    )


def write_fold(tmp_path, name, *, offset=0, call_ask=1.0):
    index_path = tmp_path / f"{name}_index.csv"
    chain_path = tmp_path / f"{name}_chain.csv"
    index_ticks(offset).to_csv(index_path, index=False)
    option_chain(offset, call_ask=call_ask).to_csv(chain_path, index=False)
    return index_path, chain_path


def write_data_readiness_comparison(path, *, accepted=True):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "accepted": accepted,
                "dataset_count": 2,
                "ready_datasets": 2 if accepted else 1,
                "failed_datasets": 0 if accepted else 1,
                "ready_rate": 1.0 if accepted else 0.5,
                "total_failed_checks": 0 if accepted else 1,
                "recommendation": "feed_walkforward_research" if accepted else "collect_or_fix_data",
            }
        ]
    ).to_csv(path / "data_readiness_comparison_summary.csv", index=False)


def test_settlement_convergence_walkforward_passes_repeated_expiry_edges(tmp_path):
    idx_a, chain_a = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    idx_b, chain_b = write_fold(tmp_path, "day2", offset=1000, call_ask=1.1)
    out_dir = tmp_path / "walkforward"

    report = write_settlement_convergence_walkforward(
        [idx_a, idx_b],
        [chain_a, chain_b],
        output_dir=out_dir,
        labels=["nifty_tue_1", "nifty_tue_2"],
        window_start_ns=[100, 1100],
        window_end_ns=[300, 1300],
        min_known_fraction=0.5,
        min_gross_edge_ticks=10.0,
        min_net_edge=100.0,
        audit_thresholds=SettlementConvergenceThresholds(min_best_net_edge=100.0),
        thresholds=SettlementConvergenceWalkForwardThresholds(
            min_folds=2,
            min_pass_rate=1.0,
            min_total_opportunities=2,
            min_total_net_edge=200.0,
            min_median_best_net_edge=100.0,
            min_median_known_fraction=0.5,
        ),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.passed
    assert int(report.summary.loc[0, "fold_count"]) == 2
    assert int(report.summary.loc[0, "passed_folds"]) == 2
    assert int(report.summary.loc[0, "total_opportunities"]) == 2
    assert config["ready"]
    assert config["source_run_type"] == "settlement_convergence_walkforward"
    assert (out_dir / "settlement_convergence_walkforward_folds.csv").exists()
    assert (out_dir / "settlement_convergence_walkforward_checks.csv").exists()
    assert (out_dir / "settlement_convergence_walkforward_summary.csv").exists()
    assert (out_dir / "runs" / "01_nifty_tue_1" / "settlement_convergence_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_settlement_convergence_walkforward_can_require_data_readiness_comparison(tmp_path):
    idx_a, chain_a = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    idx_b, chain_b = write_fold(tmp_path, "day2", offset=1000, call_ask=1.1)
    comparison_dir = tmp_path / "data_readiness_comparison"
    out_dir = tmp_path / "walkforward_ready_data"
    write_data_readiness_comparison(comparison_dir, accepted=True)

    report = write_settlement_convergence_walkforward(
        [idx_a, idx_b],
        [chain_a, chain_b],
        output_dir=out_dir,
        data_readiness_comparison_dir=comparison_dir,
        require_data_readiness_comparison=True,
        labels=["nifty_tue_1", "nifty_tue_2"],
        window_start_ns=[100, 1100],
        window_end_ns=[300, 1300],
        min_known_fraction=0.5,
        min_gross_edge_ticks=10.0,
        min_net_edge=100.0,
        audit_thresholds=SettlementConvergenceThresholds(min_best_net_edge=100.0),
        thresholds=SettlementConvergenceWalkForwardThresholds(
            min_folds=2,
            min_pass_rate=1.0,
            min_total_opportunities=2,
            min_total_net_edge=200.0,
            min_median_best_net_edge=100.0,
            min_median_known_fraction=0.5,
        ),
    )

    checks = report.checks.set_index("check")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.passed
    assert bool(checks.loc["data_readiness_comparison", "passed"])
    assert config["ready"]
    assert config["research_defaults"]["require_data_readiness_comparison"]
    assert config["research_defaults"]["data_readiness_comparison"]["accepted"]
    assert (out_dir / "manifest.json").exists()


def test_cli_settlement_convergence_walkforward_fails_closed_on_weak_fold(tmp_path):
    idx_a, chain_a = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    idx_b, chain_b = write_fold(tmp_path, "day2", offset=1000, call_ask=4.0)
    out_dir = tmp_path / "walkforward_cli"

    code = main(
        [
            "walkforward-settlement-convergence",
            "--index-ticks",
            str(idx_a),
            str(idx_b),
            "--chains",
            str(chain_a),
            str(chain_b),
            "--out",
            str(out_dir),
            "--window-start-ns",
            "100",
            "1100",
            "--window-end-ns",
            "300",
            "1300",
            "--min-known-fraction",
            "0.5",
            "--min-gross-edge-ticks",
            "10",
            "--min-net-edge",
            "100",
            "--min-fold-best-net-edge",
            "100",
            "--min-total-opportunities",
            "2",
            "--min-pass-rate",
            "1",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_convergence_walkforward_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert float(summary.loc[0, "pass_rate"]) == 0.5
    assert not config["ready"]


def test_cli_settlement_convergence_walkforward_requires_data_readiness_comparison(tmp_path):
    idx_a, chain_a = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    out_dir = tmp_path / "walkforward_cli_data_gate"

    code = main(
        [
            "walkforward-settlement-convergence",
            "--index-ticks",
            str(idx_a),
            "--chains",
            str(chain_a),
            "--out",
            str(out_dir),
            "--window-start-ns",
            "100",
            "--window-end-ns",
            "300",
            "--require-data-readiness-comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_convergence_walkforward_summary.csv")
    checks = pd.read_csv(out_dir / "settlement_convergence_walkforward_checks.csv")
    folds = pd.read_csv(out_dir / "settlement_convergence_walkforward_folds.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert checks.loc[0, "check"] == "data_readiness_comparison"
    assert not bool(checks.loc[0, "passed"])
    assert folds.empty
    assert not config["ready"]
    assert "data_readiness_comparison" in config["failed_checks"]
