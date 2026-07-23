import json

import pandas as pd

from hft_cli import main
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.proof import ProofThresholds, write_proof_report
from reports.proof_refresh import (
    ProofRefreshThresholds,
    verify_proof_refresh_report,
    write_proof_refresh_report,
)
from tests.data_readiness_helpers import reseal_experiment_manifest


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
    replay = path.parent / f"_{path.name}_replay"
    replay.mkdir(parents=True, exist_ok=True)
    source = path.parent / f"_{path.name}_source.csv"
    source.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "strategy": strategy,
                "market": market,
                "net_pnl": 10.0 if passed else -1.0,
                "total_costs": 0.0,
                "fills": 10,
                "orders_sent": 10,
                "order_to_trade_ratio": 1.0,
                "otr_breached": False,
                "turnover": 1000.0,
                "maker_share": 1.0,
            }
        ]
    ).to_csv(replay / "summary.csv", index=False)
    write_experiment_manifest(
        replay,
        run_type="proof_refresh_unit_replay",
        inputs={"source": source},
    )
    write_proof_report(
        [replay],
        output_dir=path,
        thresholds=ProofThresholds(
            min_net_pnl=0.0,
            min_fills=1,
        ),
    )
    return source


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
    baseline_source = write_proof(baseline, passed=True)

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
    assert bool(report.summary.iloc[0]["baseline_proof_reported_passed"])
    assert bool(report.summary.iloc[0]["baseline_proof_semantically_verified"])
    assert bool(report.summary.iloc[0]["baseline_proof_passed"])
    assert not bool(report.summary.iloc[0]["authorizes_routing"])
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert config["ready"] is True
    assert config["schema_version"] == 2
    assert config["authority"] == {
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }
    assert config["proof"]["baseline_proof_verification"]["verified"] is True
    assert config["proof"]["baseline_proof_verification"]["passed"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Proof Refresh Runbook" in runbook
    assert "Baseline proof semantically verified: True" in runbook
    assert "No proof-refresh actions." in runbook
    assert "proof_refresh_action_queue.csv" in artifact_paths
    assert "proof_refresh_config.json" in artifact_paths
    assert "proof_refresh_runbook.md" in artifact_paths
    assert {
        "fill_model_drift",
        "baseline_proof",
        "baseline_proof_manifest",
        "baseline_proof_dependencies",
    } <= set(manifest["inputs"])
    assert manifest["inputs"]["baseline_proof"]["kind"] == "directory"
    assert manifest["inputs"]["baseline_proof_manifest"]["kind"] == "file"
    assert manifest["extra"] == {
        "ready": True,
        "proof_source": "baseline",
        "baseline_proof_verified": True,
        "latest_proof_available": False,
        "latest_proof_verified": False,
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }
    verification = verify_proof_refresh_report(out_dir)
    assert verification.verified
    assert verification.ready
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert verification.baseline_proof_verified
    assert not verification.latest_proof_provided
    assert not verification.latest_proof_verified
    assert (
        main(
            [
                "verify-proof-refresh-report",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="proof_refresh_gate",
        require_input_fingerprints=True,
    )
    assert integrity.passed
    baseline_source.write_text(
        "ts,bid,ask\n1,100,101\n2,101,102\n",
        encoding="utf-8",
    )
    stale = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="proof_refresh_gate",
        require_input_fingerprints=True,
    )
    assert not stale.passed
    assert stale.error == "input_drift"


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
    verification = verify_proof_refresh_report(out_dir)
    assert verification.verified
    assert not verification.ready
    assert verification.baseline_proof_verified
    assert not verification.latest_proof_provided


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
    verification = verify_proof_refresh_report(out_dir)
    assert verification.verified
    assert verification.ready
    assert verification.baseline_proof_verified
    assert verification.latest_proof_provided
    assert verification.latest_proof_verified


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


def test_proof_refresh_rejects_resealed_tampered_baseline_proof(tmp_path):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    write_proof(baseline, passed=True)
    summary_path = baseline / "proof_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "total_net_pnl"] = 999999.0
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(baseline)

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
    )

    row = report.summary.iloc[0]
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert bool(row["baseline_proof_reported_passed"])
    assert not bool(row["baseline_proof_semantically_verified"])
    assert not bool(row["baseline_proof_passed"])
    assert bool(row["baseline_proof_manifest_current"])
    assert not bool(row["baseline_proof_artifacts_consistent"])
    assert row["baseline_proof_verification_error"] == (
        "artifacts do not reconstruct from replay inputs"
    )
    assert failed == {"baseline_proof_verified"}
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "recommendation"] == (
        "regenerate_and_verify_baseline_proof"
    )


def test_proof_refresh_rejects_latest_proof_with_stale_replay_manifest(
    tmp_path,
):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    latest = tmp_path / "latest_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)
    latest_source = write_proof(latest, passed=True)
    latest_source.write_text(
        "ts,bid,ask\n1,100,101\n2,101,102\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(latest)

    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        latest_proof_path=latest,
        output_dir=out_dir,
    )

    row = report.summary.iloc[0]
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert bool(row["latest_proof_reported_passed"])
    assert not bool(row["latest_proof_semantically_verified"])
    assert not bool(row["latest_proof_passed"])
    assert bool(row["latest_proof_manifest_current"])
    assert bool(row["latest_proof_inputs_current"])
    assert not bool(row["latest_proof_replay_manifests_current"])
    assert row["latest_proof_verification_error"] == (
        "replay manifests are missing, stale, or unfingerprinted"
    )
    assert failed == {"latest_proof_verified"}
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "recommendation"] == (
        "regenerate_and_verify_latest_proof"
    )


def test_verify_proof_refresh_rejects_resealed_ready_tampering(
    tmp_path,
):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=False)
    write_proof(baseline, passed=True)
    write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
    )
    summary_path = out_dir / "proof_refresh_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "ready"] = True
    summary.loc[0, "proof_source"] = "latest"
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(out_dir)

    verification = verify_proof_refresh_report(out_dir)

    assert not verification.verified
    assert not verification.ready
    assert verification.manifest_current
    assert verification.inputs_current
    assert not verification.artifacts_consistent
    assert verification.error == (
        "artifacts do not reconstruct from inputs"
    )
    assert (
        main(
            [
                "verify-proof-refresh-report",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_verify_proof_refresh_rejects_resealed_extra_sidecar(
    tmp_path,
):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    write_proof(baseline, passed=True)
    write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
    )
    pd.DataFrame(
        [{"instrument_id": "NIFTY", "side": "BUY"}]
    ).to_csv(out_dir / "orders.csv", index=False)
    reseal_experiment_manifest(out_dir)

    verification = verify_proof_refresh_report(out_dir)

    assert not verification.verified
    assert verification.manifest_current
    assert verification.inputs_current
    assert not verification.artifacts_consistent
    assert verification.manifest_artifact_count == 7
    assert verification.error == (
        "artifacts do not reconstruct from inputs"
    )


def test_verify_proof_refresh_rejects_outer_reseal_after_source_drift(
    tmp_path,
):
    drift = tmp_path / "drift"
    baseline = tmp_path / "baseline_proof"
    out_dir = tmp_path / "refresh"
    write_drift(drift, passed=True)
    source = write_proof(baseline, passed=True)
    write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=out_dir,
    )
    source.write_text(
        "ts,bid,ask\n1,100,101\n2,101,102\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(out_dir)

    verification = verify_proof_refresh_report(out_dir)

    assert not verification.verified
    assert not verification.ready
    assert verification.manifest_current
    assert verification.inputs_current
    assert not verification.baseline_proof_verified
    assert not verification.artifacts_consistent
    assert verification.error == (
        "artifacts do not reconstruct from inputs"
    )


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
