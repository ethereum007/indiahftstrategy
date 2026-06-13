import json

import pandas as pd

from hft_cli import main
from reports.imbalance_candidate_promotion import (
    ImbalanceCandidatePromotionThresholds,
    evaluate_imbalance_candidate_promotion,
    write_imbalance_candidate_promotion,
)
from reports.launch import evaluate_launch_bundle


def walkforward_summary(*, passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "fold_count": 2,
                "proof_passed_folds": 2 if passed else 1,
                "proof_pass_rate": 1.0 if passed else 0.5,
                "total_net_pnl": 42.0,
                "median_net_pnl": 21.0,
                "min_net_pnl": 20.0,
                "total_fills": 4,
                "median_fills": 2.0,
                "worst_drawdown": 0.0,
                "median_markout_mean": 0.15,
                "median_robust_score": 20.0,
            }
        ]
    )


def candidate_config(*, ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": "imbalance",
        "source_run_type": "imbalance_replay_walkforward",
        "failed_checks": [] if ready else ["proof_pass_rate"],
        "replay_defaults": {
            "tick_size": 0.05,
            "market": "india_nse_index_derivatives",
            "instrument_id": "NIFTY_20260610_25000C",
            "instrument_kind": "OPT",
            "lot_size": 75,
            "qty": 75,
            "entry_imbalance": 0.6,
            "exit_imbalance": 0.15,
            "min_microprice_edge_ticks": 0.25,
            "max_spread_ticks": 2.0,
            "min_depth": 1,
            "hold_ns": 1_000_000,
            "cooloff_ns": 1000,
            "markout_horizons_ns": [100_000],
        },
    }


def write_walkforward(path, *, passed=True, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    walkforward_summary(passed=passed).to_csv(path / "imbalance_replay_walkforward_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(candidate_config(ready=ready), indent=2) + "\n",
        encoding="utf-8",
    )


def staged_summary():
    return pd.DataFrame(
        [
            {
                "total_orders": 1,
                "accepted_orders": 1,
                "rejected_orders": 0,
                "acceptance_rate": 1.0,
                "total_notional": 750.0,
                "max_order_notional": 750.0,
            }
        ]
    )


def staged_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-000001",
                "instrument_id": "BOOK",
                "side": 1,
                "qty": 75,
                "price": 10.0,
            }
        ]
    )


def test_evaluate_imbalance_candidate_promotion_outputs_launch_compatible_config():
    report = evaluate_imbalance_candidate_promotion(
        walkforward_summary(),
        candidate_config(),
        thresholds=ImbalanceCandidatePromotionThresholds(min_total_fills=4, min_median_markout_mean=0.1),
    )

    assert report.ready
    assert report.summary.iloc[0]["candidate_scenario_key"] == (
        "strategy=imbalance|market=india_nse_index_derivatives|entry_imbalance=0.6|"
        "min_microprice_edge_ticks=0.25|hold_ns=1000000"
    )
    assert report.candidate_config["ready"]
    assert report.candidate_config["strategy"] == "imbalance"
    assert report.candidate_config["parameters"]["instrument_id"] == "NIFTY_20260610_25000C"
    assert report.candidate_config["parameters"]["qty"] == 75
    assert report.candidate_config["parameters"]["entry_imbalance"] == 0.6
    assert report.candidate_config["parameters"]["max_spread_ticks"] == 2.0

    launch = evaluate_launch_bundle(
        promotion_summary=report.summary,
        candidate_config=report.candidate_config,
        staged_summary=staged_summary(),
        staged_orders=staged_orders(),
    )
    assert launch.ready
    assert launch.summary.iloc[0]["scenario_key"] == report.summary.iloc[0]["candidate_scenario_key"]


def test_write_imbalance_candidate_promotion_outputs_artifacts(tmp_path):
    walkforward_dir = tmp_path / "replay_walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir)

    report = write_imbalance_candidate_promotion(walkforward_dir, output_dir=out_dir)

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert report.ready
    assert config["ready"]
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_promote_imbalance_candidate_can_fail_on_breach(tmp_path):
    walkforward_dir = tmp_path / "replay_walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir, passed=False)

    code = main(
        [
            "promote-imbalance-candidate",
            "--walkforward",
            str(walkforward_dir),
            "--out",
            str(out_dir),
            "--min-proof-pass-rate",
            "1",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "promotion_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "walkforward_passed" in config["failed_checks"]
