import json

import pandas as pd

from hft_cli import main
from reports.scaleup import ScaleUpThresholds, evaluate_scaleup_plan, write_scaleup_plan


def evidence_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_checks": 0 if ready else 1,
                "recommendation": "eligible_for_shadow_scaleup_review" if ready else "evidence_incomplete",
            }
        ]
    )


def shadow_summary(accepted=True):
    return pd.DataFrame(
        [
            {
                "accepted": accepted,
                "session_count": 2,
                "accepted_sessions": 2 if accepted else 1,
                "acceptance_rate": 1.0 if accepted else 0.5,
                "scenario_count": 1,
                "scenario_key": "trigger_ticks=2",
                "median_order_fill_rate": 0.95,
                "worst_order_fill_rate": 0.9,
                "total_failed_component_checks": 0 if accepted else 1,
                "total_unmatched_fills": 0,
                "total_mismatched_orders": 0,
                "total_overfilled_orders": 0,
                "worst_adverse_slippage": 0.04,
            }
        ]
    )


def launch_summary(ready=True, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "mode": "shadow",
                "adapter": adapter,
                "scenario_key": "trigger_ticks=2",
                "accepted_orders": 2,
                "rejected_orders": 0,
                "acceptance_rate": 1.0,
                "total_notional": 1500.0,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def exposure_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "orders": 2,
                "gross_notional": 1500.0,
                "net_delta": 50.0,
                "net_vega": 200.0,
            }
        ]
    )


def proof_refresh_summary(ready=True, proof_source="latest"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "drift_passed": proof_source == "baseline",
                "fresh_proof_required": proof_source != "baseline",
                "proof_source": proof_source if ready else "none",
                "failed_checks": 0 if ready else 1,
                "recommendation": "use_latest_calibrated_proof" if ready else "rerun_calibrated_proof_before_promotion",
            }
        ]
    )


def instrument_metadata_summary(passed=True, parse_coverage=1.0, unparsed_instruments=0):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "instruments": 2,
                "parsed_instruments": 2 - unparsed_instruments,
                "unparsed_instruments": unparsed_instruments,
                "parse_coverage": parse_coverage,
                "min_parse_coverage": 1.0,
                "symbol_formats": "nse_compact_option:1|occ_option:1",
            }
        ]
    )


def broker_readiness_summary(ready=True, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema"
                if adapter != "normalized"
                else "native_normalized",
                "required_components": 3,
                "provided_components": 3,
                "failed_checks": 0 if ready else 1,
                "recommendation": "dry_run_only_until_vendor_schema_review"
                if ready and adapter != "normalized"
                else "fix_broker_readiness_gaps",
            }
        ]
    )


def data_readiness_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "components": 6,
                "required_components": 3,
                "provided_components": 6,
                "ready_components": 6 if ready else 5,
                "failed_checks": 0 if ready else 1,
                "recommendation": "feed_strategy_research" if ready else "fix_data_readiness_gaps",
            }
        ]
    )


def write_inputs(root, *, evidence_ready=True, shadow_accepted=True, launch_ready=True, exposure_passed=True):
    evidence = root / "evidence"
    shadow = root / "shadow"
    launch = root / "launch"
    exposure = root / "exposure"
    for path in (evidence, shadow, launch, exposure):
        path.mkdir(parents=True, exist_ok=True)
    evidence_summary(evidence_ready).to_csv(evidence / "strategy_evidence_summary.csv", index=False)
    shadow_summary(shadow_accepted).to_csv(shadow / "shadow_session_comparison_summary.csv", index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    exposure_summary(exposure_passed).to_csv(exposure / "order_exposure_summary.csv", index=False)
    return evidence, shadow, launch, exposure


def test_scaleup_plan_accepts_clean_shadow_scaleup():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        order_exposure_summary=exposure_summary(True),
        thresholds=ScaleUpThresholds(
            target_mode="shadow",
            max_scale_multiplier=1.5,
            min_shadow_sessions=2,
            min_worst_order_fill_rate=0.9,
            max_worst_adverse_slippage=0.05,
            max_orders_per_session=3,
            max_session_notional=2000.0,
            max_gross_notional=2000.0,
            max_abs_net_delta=100.0,
            max_abs_net_vega=250.0,
            max_telemetry_age_ns=5_000_000_000,
            max_open_order_count=2,
            max_open_order_qty=75.0,
            max_gross_position_qty=150.0,
            max_abs_net_position_qty=75.0,
            stop_loss=500.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert report.ready
    plan = report.plan.iloc[0]
    assert plan["max_orders_per_session"] == 3
    assert plan["max_notional_per_session"] == 2000.0
    assert report.summary.iloc[0]["recommendation"] == "scale_up_with_controls"
    assert report.config["kill_switches"]["max_worst_adverse_slippage"] == 0.05
    assert report.config["kill_switches"]["max_telemetry_age_ns"] == 5_000_000_000
    assert report.config["kill_switches"]["max_open_order_count"] == 2
    assert report.config["kill_switches"]["max_gross_position_qty"] == 150.0


def test_scaleup_plan_accepts_required_ready_proof_refresh():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        proof_refresh_summary=proof_refresh_summary(True, proof_source="latest"),
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["proof_refresh_ready"]
    assert report.summary.iloc[0]["proof_source"] == "latest"
    assert report.config["proof_freshness"]["required"]
    assert report.config["proof_freshness"]["ready"]
    assert report.config["proof_freshness"]["proof_source"] == "latest"


def test_scaleup_plan_accepts_required_instrument_metadata():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(True, parse_coverage=1.0),
        thresholds=ScaleUpThresholds(require_instrument_metadata=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["instrument_metadata_passed"]
    assert report.summary.iloc[0]["instrument_parse_coverage"] == 1.0
    assert report.config["instrument_metadata"]["required"]
    assert report.config["instrument_metadata"]["passed"]


def test_scaleup_plan_accepts_required_broker_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(True),
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["broker_readiness_ready"]
    assert report.config["broker_readiness"]["required"]
    assert report.config["broker_readiness"]["ready"]


def test_scaleup_plan_accepts_required_data_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        data_readiness_summary=data_readiness_summary(True),
        thresholds=ScaleUpThresholds(require_data_readiness=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["data_readiness_ready"]
    assert report.config["data_readiness"]["required"]
    assert report.config["data_readiness"]["ready"]


def test_scaleup_plan_fails_on_instrument_metadata_gap():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(False, parse_coverage=0.5, unparsed_instruments=1),
        thresholds=ScaleUpThresholds(min_instrument_parse_coverage=1.0),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"instrument_metadata_passed", "instrument_parse_coverage"}.issubset(failed)
    assert report.config["instrument_metadata"]["unparsed_instruments"] == 1


def test_scaleup_plan_fails_on_incomplete_evidence_and_adapter_gap():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(False),
        shadow_comparison_summary=shadow_summary(False),
        launch_summary=launch_summary(True, adapter="irage"),
        thresholds=ScaleUpThresholds(
            min_shadow_sessions=2,
            min_shadow_acceptance_rate=1.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "evidence_ready" in failed
    assert "shadow_comparison_accepted" in failed
    assert "acceptance_rate" in failed
    assert "adapter_allowed" in failed


def test_write_scaleup_plan_outputs_artifacts(tmp_path):
    evidence, shadow, launch, exposure = write_inputs(tmp_path)
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    instrument_metadata_summary(True).to_csv(metadata / "instrument_metadata_summary.csv", index=False)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        order_exposure_dir=exposure,
        instrument_metadata_dir=metadata,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(allowed_adapters=("arrow_money",), stop_loss=500.0),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert config["limits"]["stop_loss"] == 500.0
    assert config["instrument_metadata"]["provided"]
    assert (out_dir / "scaleup_plan.csv").exists()
    assert (out_dir / "scaleup_checks.csv").exists()
    assert (out_dir / "scaleup_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_scaleup_plan_can_fail_on_breach(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path, evidence_ready=False)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--allowed-adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == 1


def test_cli_scaleup_plan_can_require_proof_refresh(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-proof-refresh",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "proof_refresh_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_instrument_metadata(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-instrument-metadata",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "instrument_metadata_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_broker_readiness(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "broker_readiness_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_data_readiness(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-data-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "data_readiness_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_writes_runtime_freshness_kill_switch(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--max-telemetry-age-ns",
            "5000000000",
            "--max-open-order-count",
            "2",
            "--max-open-order-qty",
            "75",
            "--max-gross-position-qty",
            "150",
            "--max-abs-net-position-qty",
            "75",
        ]
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert config["kill_switches"]["max_telemetry_age_ns"] == 5_000_000_000
    assert config["kill_switches"]["max_open_order_count"] == 2
    assert config["kill_switches"]["max_open_order_qty"] == 75.0
    assert config["kill_switches"]["max_gross_position_qty"] == 150.0
    assert config["kill_switches"]["max_abs_net_position_qty"] == 75.0
