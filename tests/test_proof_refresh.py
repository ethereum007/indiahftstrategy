import json

import pandas as pd

from hft_cli import main
from reports.proof_refresh import ProofRefreshThresholds, write_proof_refresh_report


def write_summary(path, filename, row):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(path / filename, index=False)


def write_drift(path, *, passed):
    write_summary(
        path,
        "fill_model_drift_summary.csv",
        {
            "passed": passed,
            "failed_checks": 0 if passed else 1,
            "recommendation": "reuse_existing_proof_assumptions"
            if passed
            else "rerun_calibrated_proof_before_promotion",
        },
    )


def write_proof(path, *, passed, strategy="leadlag", market="india_nse_index_derivatives"):
    write_summary(
        path,
        "proof_summary.csv",
        {
            "run_count": 1,
            "passed_runs": 1 if passed else 0,
            "failed_runs": 0 if passed else 1,
            "all_passed": passed,
            "strategy": strategy,
            "strategy_count": 1 if strategy else 0,
            "market": market,
            "market_count": 1 if market else 0,
            "total_net_pnl": 10.0 if passed else -1.0,
            "total_fills": 10,
        },
    )


def write_calibrated_replay(path, *, ready, strategy="leadlag"):
    write_summary(
        path,
        "calibrated_replay_summary.csv",
        {
            "ready": ready,
            "strategy": strategy,
            "failed_checks": 0 if ready else 1,
            "recommendation": "run_calibrated_replay" if ready else "fix_fill_model_before_replay",
        },
    )


def test_proof_refresh_reuses_baseline_when_drift_passes(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    write_proof(baseline, passed=True)

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
        thresholds=ProofRefreshThresholds(require_calibrated_replay_when_drift_fails=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["proof_source"] == "baseline"
    assert report.summary.iloc[0]["recommendation"] == "reuse_existing_proof"
    assert (out_dir / "proof_refresh_summary.csv").exists()
    assert (out_dir / "proof_refresh_checks.csv").exists()
    assert (out_dir / "proof_refresh_decision.csv").exists()
    assert (out_dir / "proof_refresh_action_queue.csv").exists()
    assert (out_dir / "proof_refresh_config.json").exists()
    assert (out_dir / "proof_refresh_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "proof_refresh_action_queue.csv")
    config = json.loads((out_dir / "proof_refresh_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "proof_refresh_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert queue.empty
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert config["ready"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Proof Refresh Runbook" in runbook
    assert "No proof-refresh actions." in runbook
    assert "proof_refresh_action_queue.csv" in artifact_paths
    assert "proof_refresh_config.json" in artifact_paths
    assert "proof_refresh_runbook.md" in artifact_paths


def test_proof_refresh_requires_latest_when_drift_fails(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
    )

    assert not report.ready
    assert report.summary.iloc[0]["proof_source"] == "none"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"latest_proof_available", "latest_proof_passed"} <= failed
    summary = report.summary.iloc[0]
    assert int(summary["action_queue_count"]) == 2
    assert int(summary["blocked_action_count"]) == 2
    assert summary["next_gate"] == "review-proof-refresh"
    assert summary["next_gate_help_command"] == "python -m hft_cli review-proof-refresh --help"
    assert report.action_queue is not None
    assert set(report.action_queue["check"]) == {"latest_proof_available", "latest_proof_passed"}
    assert set(report.action_queue["component"]) == {"proof_evidence"}


def test_proof_refresh_accepts_latest_calibrated_proof_when_drift_fails(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    latest = tmp_path / "latest_proof"
    calibrated = tmp_path / "calibrated_replay"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)
    write_proof(latest, passed=True)
    write_calibrated_replay(calibrated, ready=True, strategy="leadlag")

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        latest_proof_path=latest,
        calibrated_replay_path=calibrated,
        output_dir=out_dir,
        thresholds=ProofRefreshThresholds(
            require_calibrated_replay_when_drift_fails=True,
            expected_strategy="leadlag",
        ),
    )

    assert report.ready
    assert report.summary.iloc[0]["proof_source"] == "latest"
    assert report.summary.iloc[0]["recommendation"] == "use_latest_calibrated_proof"


def test_proof_refresh_blocks_mixed_strategy_and_market_identities(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    latest = tmp_path / "latest_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    write_proof(
        baseline,
        passed=True,
        strategy="leadlag",
        market="india_nse_index_derivatives",
    )
    write_proof(
        latest,
        passed=True,
        strategy="surface_mm",
        market="us_options_regular",
    )

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        latest_proof_path=latest,
        output_dir=out_dir,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"same_strategy", "same_market"} <= failed
    assert bool(report.summary.iloc[0]["mixed_identity"])
    assert report.summary.iloc[0]["strategy_count"] == 2
    assert report.summary.iloc[0]["market_count"] == 2
    assert report.summary.iloc[0]["proof_source"] == "none"


def test_proof_refresh_blocks_wrong_expected_market(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    write_proof(
        baseline,
        passed=True,
        strategy="leadlag",
        market="us_options_regular",
    )

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
        thresholds=ProofRefreshThresholds(expected_market="india_nse_index_derivatives"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "expected_market" in failed
    assert report.summary.iloc[0]["expected_market"] == "india_nse_index_derivatives"


def test_cli_proof_refresh_fails_on_unready_calibrated_replay(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    latest = tmp_path / "latest_proof"
    calibrated = tmp_path / "calibrated_replay"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)
    write_proof(latest, passed=True)
    write_calibrated_replay(calibrated, ready=False, strategy="leadlag")

    code = main(
        [
            "review-proof-refresh",
            "--drift",
            str(drift),
            "--baseline-proof",
            str(baseline),
            "--latest-proof",
            str(latest),
            "--calibrated-replay",
            str(calibrated),
            "--out",
            str(out_dir),
            "--strategy",
            "leadlag",
            "--market",
            "india_nse_index_derivatives",
            "--require-calibrated-replay",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "proof_refresh_summary.csv")
    queue = pd.read_csv(out_dir / "proof_refresh_action_queue.csv")
    config = json.loads((out_dir / "proof_refresh_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "proof_refresh_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert summary.loc[0, "primary_blocker_check"] == "calibrated_replay_ready"
    assert queue.loc[0, "check"] == "calibrated_replay_ready"
    assert queue.loc[0, "component"] == "calibrated_replay"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-proof-refresh --help"
    assert config["primary_action"]["check"] == "calibrated_replay_ready"
    assert "calibrated_replay_ready" in runbook


def test_cli_proof_refresh_can_fail_on_actions(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)

    code = main(
        [
            "review-proof-refresh",
            "--drift",
            str(drift),
            "--baseline-proof",
            str(baseline),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "proof_refresh_summary.csv")
    queue = pd.read_csv(out_dir / "proof_refresh_action_queue.csv")
    assert code == 2
    assert int(summary.loc[0, "action_queue_count"]) == 2
    assert queue.loc[0, "check"] == "latest_proof_available"
    assert queue.loc[0, "component"] == "proof_evidence"
