import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.data_readiness_comparison import (
    write_data_readiness_comparison as write_data_readiness_comparison_report,
)
from reports.evidence import EvidenceThresholds, evaluate_strategy_evidence, evidence_profile_run_types
from reports.settlement_candidate_promotion import (
    SettlementCandidatePromotionThresholds,
    write_settlement_candidate_promotion,
)
from reports.settlement_convergence import SettlementConvergenceThresholds
from reports.settlement_convergence_walkforward import (
    SettlementConvergenceWalkForwardThresholds,
    write_settlement_convergence_walkforward,
)
from reports.settlement_launch_pipeline import SettlementLaunchPipelineConfig, write_settlement_launch_pipeline


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
    readiness_dir = path.parent / f"{path.name}_source"
    readiness_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": accepted,
                "components": 1,
                "required_components": 1,
                "provided_components": 1,
                "ready_components": 1 if accepted else 0,
                "failed_checks": 0 if accepted else 1,
                "recommendation": "compare_data_readiness",
            }
        ]
    ).to_csv(readiness_dir / "data_readiness_summary.csv", index=False)
    write_data_readiness_comparison_report(
        [readiness_dir],
        output_dir=path,
    )
    return readiness_dir


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
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.summary.loc[0, "strategy"] == "settlement_convergence"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "settlement_convergence"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
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


def test_settlement_artifacts_satisfy_settlement_evidence_profile(tmp_path):
    idx_a, chain_a = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    idx_b, chain_b = write_fold(tmp_path, "day2", offset=1000, call_ask=1.1)
    walkforward_dir = tmp_path / "walkforward"
    promotion_dir = tmp_path / "promotion"
    launch_dir = tmp_path / "launch"

    write_settlement_convergence_walkforward(
        [idx_a, idx_b],
        [chain_a, chain_b],
        output_dir=walkforward_dir,
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
    write_settlement_candidate_promotion(
        walkforward_dir,
        output_dir=promotion_dir,
        thresholds=SettlementCandidatePromotionThresholds(min_total_net_edge=200.0),
    )
    write_settlement_launch_pipeline(
        promotion_dir,
        output_dir=launch_dir,
        config=SettlementLaunchPipelineConfig(
            require_reviewed_schema=False,
            max_order_qty=75,
            max_notional=10_000,
            max_orders=1,
        ),
    )

    catalog = catalog_experiment_runs([tmp_path]).catalog
    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("settlement_convergence"),
            allow_dirty_git=True,
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="settlement_convergence",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(evidence_profile_run_types("settlement"))
    assert review.summary.loc[0, "strategy"] == "settlement_convergence"
    assert review.summary.loc[0, "market"] == "india_nse_index_derivatives"


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
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert bool(checks.loc["data_readiness_comparison", "passed"])
    assert bool(checks.loc["data_readiness_comparison", "manifest_current"])
    assert config["ready"]
    assert config["research_defaults"]["require_data_readiness_comparison"]
    assert config["research_defaults"]["data_readiness_comparison"]["accepted"]
    assert config["research_defaults"]["data_readiness_comparison"]["manifest_current"]
    assert "data_readiness_comparison_manifest" in manifest["inputs"]
    assert (out_dir / "manifest.json").exists()


def test_settlement_walkforward_blocks_drifted_readiness_source(tmp_path):
    index_path, chain_path = write_fold(tmp_path, "day1", offset=0, call_ask=1.0)
    comparison_dir = tmp_path / "data_readiness_comparison"
    out_dir = tmp_path / "walkforward_drifted_data"
    readiness_dir = write_data_readiness_comparison(comparison_dir, accepted=True)
    readiness_path = readiness_dir / "data_readiness_summary.csv"
    readiness = pd.read_csv(readiness_path)
    readiness.loc[0, "recommendation"] = "changed_after_comparison"
    readiness.to_csv(readiness_path, index=False)

    report = write_settlement_convergence_walkforward(
        [index_path],
        [chain_path],
        output_dir=out_dir,
        data_readiness_comparison_dir=comparison_dir,
        require_data_readiness_comparison=True,
        window_start_ns=100,
        window_end_ns=300,
    )

    check = report.checks.set_index("check").loc["data_readiness_comparison"]
    comparison = report.candidate_config["research_defaults"]["data_readiness_comparison"]
    assert not report.passed
    assert report.folds.empty
    assert check["reason"] == "data_readiness_comparison_manifest_input_drift"
    assert check["manifest_error"] == "input_drift"
    assert not comparison["manifest_current"]
    assert comparison["manifest_error"] == "input_drift"


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
