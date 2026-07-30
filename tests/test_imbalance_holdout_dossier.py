import json

import pandas as pd
import pytest

from engine.costs import ScaledCostModel
from engine.hft_backtest import IndianCostModel, Instrument, Kind
from hft_cli import main
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_walkforward import (
    ImbalanceEdgeWalkForwardThresholds,
)
from reports.imbalance_holdout_dossier import (
    ImbalanceHoldoutThresholds,
    write_imbalance_holdout_dossier,
)
from reports.imbalance_pipeline import write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardThresholds,
)
from reports.manifest import verify_experiment_manifest
from reports.proof import ProofThresholds


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks(day: str) -> pd.DataFrame:
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    ts3 = ns_ist(f"{day} 09:15:00.000300")
    ts4 = ns_ist(f"{day} 09:15:00.000400")
    return pd.DataFrame(
        [
            {
                "ts": ts0,
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
            },
            {
                "ts": ts1,
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
            },
            {
                "ts": ts2,
                "bid": 100.30,
                "ask": 100.35,
                "bid_qty": 100,
                "ask_qty": 900,
            },
            {
                "ts": ts3,
                "bid": 100.30,
                "ask": 100.35,
                "bid_qty": 100,
                "ask_qty": 900,
            },
            {
                "ts": ts4,
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 500,
                "ask_qty": 500,
            },
        ]
    )


def write_ticks(path, day: str) -> None:
    imbalance_ticks(day).to_csv(path, index=False)


def promoted_candidate(tmp_path):
    development_a = tmp_path / "development_a.csv"
    development_b = tmp_path / "development_b.csv"
    pipeline_dir = tmp_path / "pipeline"
    write_ticks(development_a, "2026-06-10")
    write_ticks(development_b, "2026-06-11")
    report = write_imbalance_research_pipeline(
        [development_a, development_b],
        output_dir=pipeline_dir,
        labels=["development_1", "development_2"],
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        cooloff_ns=100_000,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(
            min_sweeps=2,
            min_median_usable_signals=2,
        ),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(
            min_folds=2,
            min_passed_sweeps=2,
        ),
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        replay_walkforward_thresholds=(
            ImbalanceReplayWalkForwardThresholds(
                min_folds=2,
                min_proof_pass_rate=1.0,
                min_total_fills=2,
            )
        ),
    )
    assert report.ready
    return pipeline_dir / "promotion", development_a, development_b


def permissive_thresholds() -> ImbalanceHoldoutThresholds:
    return ImbalanceHoldoutThresholds(
        min_holdout_folds=2,
        min_baseline_profitable_fold_rate=0.5,
        min_baseline_total_net_pnl=0.0,
        min_baseline_total_fills=2,
        min_max_latency_total_net_pnl=-1_000.0,
        min_max_cost_total_net_pnl=-1_000.0,
        min_max_qty_total_net_pnl=-1_000.0,
        max_max_qty_liquidity_shortfall_rate=1.0,
    )


def test_scaled_cost_model_multiplies_complete_cash_cost() -> None:
    instrument = Instrument("NIFTY_OPT", Kind.OPT, lot_size=75, tick=0.05)
    base = IndianCostModel.nse_index_options()
    scaled = ScaledCostModel(base, 1.75)

    assert scaled.cost(1, 100.0, 75, instrument) == pytest.approx(
        1.75 * base.cost(1, 100.0, 75, instrument)
    )
    assert scaled.cost(-1, 100.0, 75, instrument) == pytest.approx(
        1.75 * base.cost(-1, 100.0, 75, instrument)
    )
    assert scaled.round_trip_bps(100.0, instrument) == pytest.approx(
        1.75 * base.round_trip_bps(100.0, instrument)
    )


def test_holdout_dossier_builds_latency_cost_and_capacity_proof(tmp_path):
    candidate, _, _ = promoted_candidate(tmp_path)
    holdout_a = tmp_path / "holdout_a.csv"
    holdout_b = tmp_path / "holdout_b.csv"
    out_dir = tmp_path / "holdout_proof"
    write_ticks(holdout_a, "2026-06-12")
    write_ticks(holdout_b, "2026-06-15")

    report = write_imbalance_holdout_dossier(
        candidate,
        [holdout_a, holdout_b],
        output_dir=out_dir,
        labels=["holdout_1", "holdout_2"],
        baseline_latency_us=0.0,
        latency_us_values=[0.0, 50.0],
        cost_multipliers=[1.0, 2.0],
        qty_multipliers=[1.0, 2.0],
        thresholds=permissive_thresholds(),
    )

    assert report.passed
    assert len(report.scenarios) == 8
    assert report.latency_curve["total_latency_us"].tolist() == [0.0, 50.0]
    assert report.cost_curve["cost_multiplier"].tolist() == [1.0, 2.0]
    assert report.capacity_curve["qty"].tolist() == [75, 150]
    assert bool(report.summary.loc[0, "selection_isolated"])
    assert bool(report.summary.loc[0, "non_authorizing"])
    assert report.summary.loc[0, "recommendation"] == "shadow_review_candidate"
    baseline_costs = report.cost_curve.loc[
        report.cost_curve["cost_multiplier"] == 1.0,
        "total_costs",
    ].iloc[0]
    doubled_costs = report.cost_curve.loc[
        report.cost_curve["cost_multiplier"] == 2.0,
        "total_costs",
    ].iloc[0]
    assert doubled_costs == pytest.approx(2.0 * baseline_costs)
    assert (out_dir / "RESEARCH_PROOF.md").exists()
    assert (out_dir / "research_proof.json").exists()
    assert (out_dir / "holdout_scenarios.csv").exists()
    assert (out_dir / "latency_curve.csv").exists()
    assert (out_dir / "cost_curve.csv").exists()
    assert (out_dir / "capacity_curve.csv").exists()
    markdown = (out_dir / "RESEARCH_PROOF.md").read_text(encoding="utf-8")
    assert "## Gate Checks" in markdown
    assert "candidate_manifest_current" in markdown
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="imbalance_holdout_dossier",
        required_artifacts=(
            "RESEARCH_PROOF.md",
            "research_proof.json",
            "holdout_summary.csv",
            "holdout_checks.csv",
            "latency_curve.csv",
            "cost_curve.csv",
            "capacity_curve.csv",
        ),
        require_input_fingerprints=True,
    )
    assert integrity.passed
    proof = json.loads(
        (out_dir / "research_proof.json").read_text(encoding="utf-8")
    )
    assert proof["summary"][0]["passed"]
    assert proof["limitations"]


def test_holdout_dossier_blocks_development_data_reuse_before_replay(
    tmp_path,
):
    candidate, development_a, _ = promoted_candidate(tmp_path)
    out_dir = tmp_path / "overlap_proof"

    report = write_imbalance_holdout_dossier(
        candidate,
        [development_a],
        output_dir=out_dir,
        baseline_latency_us=0.0,
        latency_us_values=[0.0],
        cost_multipliers=[1.0],
        qty_multipliers=[1.0],
        thresholds=ImbalanceHoldoutThresholds(min_holdout_folds=1),
    )

    checks = report.checks.set_index("check")
    assert not report.passed
    assert not bool(report.summary.loc[0, "evaluated"])
    assert not bool(checks.loc["selection_isolated", "passed"])
    assert report.scenarios.empty
    assert not (out_dir / "runs").exists()
    assert "holdout data overlaps" in str(
        checks.loc["selection_isolated", "reason"]
    )
    assert (out_dir / "manifest.json").exists()


def test_cli_prove_imbalance_holdout_writes_non_authorizing_verdict(tmp_path):
    candidate, _, _ = promoted_candidate(tmp_path)
    holdout_a = tmp_path / "holdout_a.csv"
    holdout_b = tmp_path / "holdout_b.csv"
    out_dir = tmp_path / "cli_proof"
    write_ticks(holdout_a, "2026-06-12")
    write_ticks(holdout_b, "2026-06-15")

    code = main(
        [
            "prove-imbalance-holdout",
            "--candidate",
            str(candidate),
            "--holdout-ticks",
            str(holdout_a),
            str(holdout_b),
            "--out",
            str(out_dir),
            "--baseline-latency-us",
            "0",
            "--latency-us",
            "0",
            "--cost-multiplier",
            "1",
            "--qty-multiplier",
            "1",
            "--min-holdout-folds",
            "2",
            "--min-baseline-profitable-fold-rate",
            "0.5",
            "--min-baseline-total-fills",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "holdout_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "passed"])
    assert bool(summary.loc[0, "non_authorizing"])
