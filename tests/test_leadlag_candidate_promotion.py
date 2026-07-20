import json

import pandas as pd

from hft_cli import main
from reports.launch import evaluate_launch_bundle
from reports.leadlag_candidate_promotion import (
    LeadLagCandidatePromotionThresholds,
    evaluate_leadlag_candidate_promotion,
    write_leadlag_candidate_promotion,
)
from reports.manifest import write_experiment_manifest


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
        "strategy": "lead_lag_taker",
        "source_run_type": "leadlag_replay_walkforward",
        "failed_checks": [] if ready else ["proof_pass_rate"],
        "edge_audit": {
            "passed": True,
            "measurement_manifest_current": True,
            "measurement_manifest_sha256": "a" * 64,
            "max_profitable_latency_ns": 100_000,
            "metrics": {
                "max_profitable_latency_ns": 100_000,
                "best_latency_avg_net_edge": 5.0,
                "best_latency_cost_drag_ratio": 0.2,
                "best_latency_net_edge_bps": 2.0,
            },
        },
        "replay_defaults": {
            "market": "india_nse_index_derivatives",
            "leader_tick": 0.05,
            "laggard_tick": 0.05,
            "delta": 1.0,
            "trigger_ticks": 10.0,
            "qty": 75,
            "flat_after_ns": 200_000,
            "feed_latency_us": 25.0,
            "order_latency_us": 25.0,
            "markout_horizons_ns": [100_000],
        },
        "replay_walkforward": {
            "edge_audit_bound": True,
            "edge_latency_budget_ns": 100_000,
            "total_replay_latency_ns": 50_000,
            "edge_latency_headroom_ns": 50_000,
        },
    }


def write_walkforward(path, *, passed=True, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    source_path = path.parent / f"{path.name}_source.csv"
    source_path.write_text("ts,bid,ask\n0,1,2\n", encoding="utf-8")
    walkforward_summary(passed=passed).to_csv(path / "leadlag_replay_walkforward_summary.csv", index=False)
    pd.DataFrame([{"fold": "day1", "proof_passed": passed}]).to_csv(
        path / "leadlag_replay_walkforward_folds.csv", index=False
    )
    pd.DataFrame(
        [{"check": "proof_pass_rate", "passed": passed}]
    ).to_csv(path / "leadlag_replay_walkforward_checks.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(candidate_config(ready=ready), indent=2) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        path,
        run_type="leadlag_replay_walkforward",
        inputs={"source": source_path},
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
                "instrument_id": "LAGGARD",
                "side": 1,
                "qty": 75,
                "price": 10.0,
            }
        ]
    )


def test_evaluate_leadlag_candidate_promotion_outputs_launch_compatible_config():
    report = evaluate_leadlag_candidate_promotion(
        walkforward_summary(),
        candidate_config(),
        thresholds=LeadLagCandidatePromotionThresholds(min_total_fills=4, min_median_markout_mean=0.1),
    )

    assert report.ready
    assert report.summary.iloc[0]["candidate_scenario_key"] == (
        "strategy=lead_lag_taker|market=india_nse_index_derivatives|trigger_ticks=10|"
        "delta=1|leader_tick=0.05|laggard_tick=0.05"
    )
    assert report.candidate_config["ready"]
    assert report.candidate_config["strategy"] == "lead_lag_taker"
    assert report.candidate_config["parameters"]["trigger_ticks"] == 10.0
    assert report.summary.iloc[0]["edge_audit_bound"]
    assert report.summary.iloc[0]["edge_latency_headroom_ns"] == 50_000
    assert report.candidate_config["edge_audit"]["max_profitable_latency_ns"] == 100_000
    assert report.candidate_config["metrics"]["edge_best_latency_avg_net_edge"] == 5.0

    launch = evaluate_launch_bundle(
        promotion_summary=report.summary,
        candidate_config=report.candidate_config,
        staged_summary=staged_summary(),
        staged_orders=staged_orders(),
    )
    assert launch.ready
    assert launch.summary.iloc[0]["scenario_key"] == report.summary.iloc[0]["candidate_scenario_key"]


def test_leadlag_candidate_promotion_requires_bound_edge_audit():
    unbound = candidate_config()
    unbound.pop("edge_audit")

    report = evaluate_leadlag_candidate_promotion(
        walkforward_summary(),
        unbound,
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert failed == {"edge_audit_bound", "edge_latency_budget_respected"}

    research_override = evaluate_leadlag_candidate_promotion(
        walkforward_summary(),
        unbound,
        thresholds=LeadLagCandidatePromotionThresholds(
            require_edge_audit_bound=False
        ),
    )
    assert research_override.ready


def test_write_leadlag_candidate_promotion_outputs_artifacts(tmp_path):
    walkforward_dir = tmp_path / "replay_walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir)

    report = write_leadlag_candidate_promotion(walkforward_dir, output_dir=out_dir)

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert report.ready
    assert config["ready"]
    assert bool(report.summary.iloc[0]["walkforward_manifest_current"])
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_write_leadlag_candidate_promotion_blocks_walkforward_artifact_drift(tmp_path):
    walkforward_dir = tmp_path / "replay_walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir)
    config_path = walkforward_dir / "candidate_config.json"
    drifted = json.loads(config_path.read_text(encoding="utf-8"))
    drifted["replay_defaults"]["trigger_ticks"] = 99.0
    config_path.write_text(json.dumps(drifted, indent=2) + "\n", encoding="utf-8")

    report = write_leadlag_candidate_promotion(
        walkforward_dir,
        output_dir=out_dir,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert failed == {"walkforward_manifest_current"}
    assert report.summary.iloc[0]["walkforward_manifest_error"] == "artifact_drift"
    assert "walkforward_manifest_current" in report.candidate_config["failed_checks"]


def test_cli_promote_leadlag_candidate_can_fail_on_breach(tmp_path):
    walkforward_dir = tmp_path / "replay_walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir, passed=False)

    code = main(
        [
            "promote-leadlag-candidate",
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
