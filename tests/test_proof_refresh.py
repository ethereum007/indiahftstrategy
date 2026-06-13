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
    assert (out_dir / "manifest.json").exists()


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
        ]
    )

    summary = pd.read_csv(out_dir / "proof_refresh_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
