import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.data_readiness_comparison import (
    write_data_readiness_comparison as write_data_readiness_comparison_report,
)
from reports.evidence import EvidenceThresholds, evaluate_strategy_evidence, evidence_profile_run_types
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_walkforward import ImbalanceEdgeWalkForwardThresholds
from reports.imbalance_launch_pipeline import ImbalanceLaunchPipelineConfig, write_imbalance_launch_pipeline
from reports.imbalance_pipeline import write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import ImbalanceReplayWalkForwardThresholds
from reports.market_portability import MarketPortabilityReportConfig, write_market_portability_report
from reports.proof import ProofThresholds
from tests.data_readiness_helpers import (
    reseal_experiment_manifest,
    write_manifest_bound_data_readiness,
)


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks(day: str):
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    ts3 = ns_ist(f"{day} 09:15:00.000300")
    ts4 = ns_ist(f"{day} 09:15:00.000400")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts4, "bid": 100.00, "ask": 100.05, "bid_qty": 500, "ask_qty": 500},
        ]
    )


def write_ticks(path, day: str):
    imbalance_ticks(day).to_csv(path, index=False)


def write_data_readiness_comparison(path, *, accepted=True):
    readiness_dir = path.parent / f"{path.name}_source"
    write_manifest_bound_data_readiness(
        readiness_dir,
        {
            "ready": accepted,
            "components": 1,
            "required_components": 1,
            "provided_components": 1,
            "ready_components": 1 if accepted else 0,
            "failed_checks": 0 if accepted else 1,
            "recommendation": "compare_data_readiness",
        },
    )
    write_data_readiness_comparison_report(
        [readiness_dir],
        output_dir=path,
    )
    return readiness_dir


def test_imbalance_research_pipeline_promotes_candidate_end_to_end(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")

    report = write_imbalance_research_pipeline(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        cooloff_ns=100_000,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(min_sweeps=2, min_median_usable_signals=2),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(min_folds=2, min_passed_sweeps=2),
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
            min_folds=2,
            min_proof_pass_rate=1.0,
            min_total_fills=2,
        ),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    edge_summary = pd.read_csv(out_dir / "edge_walkforward" / "imbalance_edge_walkforward_summary.csv")
    replay_summary = pd.read_csv(out_dir / "replay_walkforward" / "imbalance_replay_walkforward_summary.csv")
    promotion_summary = pd.read_csv(out_dir / "promotion" / "promotion_summary.csv")
    assert report.ready
    assert report.replay is not None
    assert report.promotion is not None
    assert report.summary.loc[0, "strategy"] == "imbalance"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert edge_summary.loc[0, "strategy"] == "imbalance"
    assert edge_summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert replay_summary.loc[0, "strategy"] == "imbalance"
    assert replay_summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert promotion_summary.loc[0, "strategy"] == "imbalance"
    assert promotion_summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "imbalance"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert int(report.summary.loc[0, "edge_selectable_scenarios"]) >= 1
    assert int(report.summary.loc[0, "replay_total_fills"]) >= 2
    assert set(report.stages["stage"]) == {"edge_walkforward", "replay_walkforward", "promotion"}
    assert config["ready"]
    assert config["source_run_type"] == "imbalance_research_pipeline"
    assert config["strategy"] == "imbalance"
    assert (out_dir / "edge_walkforward" / "candidate_config.json").exists()
    assert (out_dir / "replay_walkforward" / "imbalance_replay_walkforward_summary.csv").exists()
    assert (out_dir / "promotion" / "promotion_summary.csv").exists()
    assert (out_dir / "imbalance_pipeline_stages.csv").exists()
    assert (out_dir / "imbalance_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_imbalance_pipeline_artifacts_satisfy_imbalance_evidence_profile(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    out_dir = tmp_path / "pipeline_evidence"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")

    write_imbalance_research_pipeline(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        cooloff_ns=100_000,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(min_sweeps=2, min_median_usable_signals=2),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(min_folds=2, min_passed_sweeps=2),
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
            min_folds=2,
            min_proof_pass_rate=1.0,
            min_total_fills=2,
        ),
    )
    write_imbalance_launch_pipeline(
        out_dir / "promotion",
        output_dir=out_dir / "launch_pipeline",
        config=ImbalanceLaunchPipelineConfig(
            adapter="normalized",
            instrument_id="BOOK",
            reference_price=100.0,
            max_order_qty=75,
            max_notional=10_000,
            max_orders=2,
        ),
    )

    catalog = catalog_experiment_runs([out_dir]).catalog
    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=evidence_profile_run_types("microprice_imbalance"),
            allow_dirty_git=True,
            require_same_strategy=True,
            require_same_market=True,
            expected_strategy="imbalance",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == set(evidence_profile_run_types("imbalance"))
    assert review.summary.loc[0, "strategy"] == "imbalance"
    assert review.summary.loc[0, "market"] == "india_nse_index_derivatives"


def test_imbalance_research_pipeline_can_require_data_readiness_comparison(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    comparison_dir = tmp_path / "data_readiness_comparison"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")
    write_data_readiness_comparison(comparison_dir, accepted=True)

    report = write_imbalance_research_pipeline(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        data_readiness_comparison_dir=comparison_dir,
        require_data_readiness_comparison=True,
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        cooloff_ns=100_000,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(min_sweeps=2, min_median_usable_signals=2),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(min_folds=2, min_passed_sweeps=2),
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
            min_folds=2,
            min_proof_pass_rate=1.0,
            min_total_fills=2,
        ),
    )

    stages = report.stages.set_index("stage")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert bool(stages.loc["data_readiness_comparison", "status"])
    assert bool(stages.loc["data_readiness_comparison", "manifest_current"])
    assert bool(
        stages.loc[
            "data_readiness_comparison",
            "semantically_verified",
        ]
    )
    assert bool(
        stages.loc[
            "data_readiness_comparison",
            "verification_non_authorizing",
        ]
    )
    assert bool(stages.loc["edge_walkforward", "status"])
    assert config["pipeline"]["stages"][0]["stage"] == "data_readiness_comparison"
    assert config["pipeline"]["stages"][0]["lineage"]["manifest_current"]
    assert config["pipeline"]["stages"][0]["lineage"][
        "semantically_verified"
    ]
    assert "data_readiness_comparison_manifest" in manifest["inputs"]


def test_imbalance_pipeline_blocks_tampered_data_readiness_comparison(tmp_path):
    fold = tmp_path / "fold.csv"
    comparison_dir = tmp_path / "data_readiness_comparison"
    out_dir = tmp_path / "pipeline_tampered_data"
    write_ticks(fold, "2026-06-10")
    write_data_readiness_comparison(comparison_dir, accepted=True)
    summary_path = comparison_dir / "data_readiness_comparison_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "recommendation"] = "tampered_after_manifest"
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(comparison_dir)

    report = write_imbalance_research_pipeline(
        [fold],
        output_dir=out_dir,
        data_readiness_comparison_dir=comparison_dir,
        require_data_readiness_comparison=True,
        entry_imbalance_values=[0.6],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
    )

    stages = report.stages.set_index("stage")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    comparison = stages.loc["data_readiness_comparison"]
    assert not report.ready
    assert not bool(comparison["status"])
    assert bool(comparison["manifest_current"])
    assert not bool(comparison["semantically_verified"])
    assert not bool(comparison["verification_artifacts_consistent"])
    assert comparison["reason"] == (
        "data_readiness_comparison_"
        "artifacts_do_not_reconstruct_from_inputs"
    )
    assert comparison["manifest_error"] == ""
    assert comparison["verification_error"] == (
        "artifacts do not reconstruct from inputs"
    )
    assert bool(stages.loc["edge_walkforward", "skipped"])
    lineage = config["pipeline"]["stages"][0]["lineage"]
    assert lineage["manifest_current"]
    assert not lineage["semantically_verified"]
    assert lineage["verification_error"] == (
        "artifacts do not reconstruct from inputs"
    )


def test_imbalance_pipeline_blocks_nonportable_market_pair(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    portability_dir = tmp_path / "portability"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
        ),
    )

    report = write_imbalance_research_pipeline(
        [fold_a],
        output_dir=out_dir,
        market_portability_dir=portability_dir,
        require_market_portability=True,
        market="us_equities_regular",
        filter_session=False,
        entry_imbalance_values=[0.6],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
    )

    stages = report.stages.set_index("stage")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert not bool(stages.loc["market_portability", "status"])
    assert bool(stages.loc["edge_walkforward", "skipped"])
    assert stages.loc["edge_walkforward", "recommendation"] == "market_portability_not_ready"
    assert config["failed_checks"] == ["market_portability", "edge_walkforward", "replay_walkforward", "promotion"]


def test_cli_imbalance_research_pipeline_fails_closed_when_edge_gate_fails(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")

    code = main(
        [
            "pipeline-imbalance-research",
            "--ticks",
            str(fold_a),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--min-signals",
            "2",
            "--min-direction-count",
            "2",
            "--min-mean-forward-edge-ticks",
            "1",
            "--min-win-rate",
            "0.5",
            "--min-edge-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "imbalance_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(stages.loc[stages["stage"] == "replay_walkforward", "skipped"].iloc[0])
    assert "edge_walkforward" in config["failed_checks"]


def test_cli_imbalance_pipeline_requires_data_readiness_comparison(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")

    code = main(
        [
            "pipeline-imbalance-research",
            "--ticks",
            str(fold_a),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--require-data-readiness-comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "imbalance_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    failed = stages.loc[~stages["status"].astype(bool), "stage"].astype(str).tolist()
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "data_readiness_comparison" in failed
    assert bool(stages.loc[stages["stage"] == "edge_walkforward", "skipped"].iloc[0])
    assert "data_readiness_comparison" in config["failed_checks"]


def test_cli_imbalance_pipeline_requires_market_portability(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    portability_dir = tmp_path / "portability"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")
    write_market_portability_report(
        portability_dir,
        config=MarketPortabilityReportConfig(
            markets=("us_equities_regular",),
            strategies=("microprice_imbalance",),
        ),
    )

    code = main(
        [
            "pipeline-imbalance-research",
            "--ticks",
            str(fold_a),
            "--out",
            str(out_dir),
            "--market",
            "us_equities_regular",
            "--no-filter-session",
            "--market-portability",
            str(portability_dir),
            "--require-market-portability",
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "imbalance_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    failed = stages.loc[~stages["status"].astype(bool), "stage"].astype(str).tolist()
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "market_portability" in failed
    assert bool(stages.loc[stages["stage"] == "edge_walkforward", "skipped"].iloc[0])
    assert "market_portability" in config["failed_checks"]
