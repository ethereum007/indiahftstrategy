import json

import pandas as pd

from hft_cli import main
from reports.settlement_convergence import (
    SettlementConvergenceThresholds,
    evaluate_settlement_convergence,
    write_settlement_convergence_audit,
)


def index_ticks():
    return pd.DataFrame(
        [
            {"ts": 100, "bid": 99.95, "ask": 100.05},
            {"ts": 200, "bid": 103.95, "ask": 104.05},
            {"ts": 300, "bid": 105.95, "ask": 106.05},
        ]
    )


def option_chain(call_ask=1.0):
    return pd.DataFrame(
        [
            {
                "ts": 200,
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


def test_settlement_convergence_audit_finds_touch_price_edge():
    report = evaluate_settlement_convergence(
        index_ticks(),
        option_chain(),
        window_start_ns=100,
        window_end_ns=300,
        min_known_fraction=0.5,
        min_gross_edge_ticks=10.0,
        min_net_edge=100.0,
        thresholds=SettlementConvergenceThresholds(
            min_opportunities=1,
            min_total_net_edge=100.0,
            min_best_net_edge=100.0,
            min_median_known_fraction=0.5,
        ),
    )

    best = report.opportunities.iloc[0]
    assert report.passed
    assert best["option_type"] == "C"
    assert best["direction"] == "buy_underpriced"
    assert best["projected_settlement"] == 103.0
    assert best["projected_intrinsic"] == 3.0
    assert best["gross_edge_ticks"] == 40.0
    assert best["net_edge"] > 100.0
    assert report.candidate_config["ready"]
    assert report.candidate_config["strategy"] == "settlement_convergence"


def test_write_settlement_convergence_audit_outputs_manifest_and_candidate(tmp_path):
    index_path = tmp_path / "index.csv"
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "settlement"
    index_ticks().to_csv(index_path, index=False)
    option_chain().to_csv(chain_path, index=False)

    report = write_settlement_convergence_audit(
        index_path,
        chain_path,
        output_dir=out_dir,
        window_start_ns=100,
        window_end_ns=300,
        min_known_fraction=0.5,
        min_gross_edge_ticks=10.0,
        min_net_edge=100.0,
        thresholds=SettlementConvergenceThresholds(min_best_net_edge=100.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.passed
    assert config["ready"]
    assert (out_dir / "settlement_running_average.csv").exists()
    assert (out_dir / "settlement_convergence_opportunities.csv").exists()
    assert (out_dir / "settlement_convergence_checks.csv").exists()
    assert (out_dir / "settlement_convergence_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_settlement_convergence_audit_fails_closed_without_edge(tmp_path):
    index_path = tmp_path / "index.csv"
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "settlement_cli"
    index_ticks().to_csv(index_path, index=False)
    option_chain(call_ask=4.0).to_csv(chain_path, index=False)

    code = main(
        [
            "audit-settlement-convergence",
            "--index-ticks",
            str(index_path),
            "--chain",
            str(chain_path),
            "--out",
            str(out_dir),
            "--window-start-ns",
            "100",
            "--window-end-ns",
            "300",
            "--min-gross-edge-ticks",
            "10",
            "--min-net-edge",
            "100",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_convergence_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not config["ready"]
