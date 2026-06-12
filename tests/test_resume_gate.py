import json

import pandas as pd

from hft_cli import main
from reports.resume import ResumeGateThresholds, evaluate_resume_gate, write_resume_gate_report


def incident_summary(passed=True, scenario_key="trigger_ticks=2", adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "incident_status": "halt_completed" if passed else "halt_incomplete",
                "scenario_key": scenario_key,
                "adapter": adapter,
                "failed_checks": 0 if passed else 1,
                "recommendation": "resume_only_after_new_scaleup_review" if passed else "keep_trading_disabled",
            }
        ]
    )


def scaleup_summary(ready=True, scenario_key="trigger_ticks=2", adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": "shadow",
                "scenario_key": scenario_key,
                "adapter": adapter,
                "max_orders_per_session": 10,
                "max_notional_per_session": 100_000.0,
                "failed_checks": 0 if ready else 1,
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def scaleup_config(scenario_key="trigger_ticks=2", adapter="arrow_money"):
    return {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "scenario_key": scenario_key,
        "adapter": adapter,
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "max_scale_multiplier": 1.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": {
            "max_total_failed_component_checks": 0,
            "max_total_unmatched_fills": 0,
            "max_total_mismatched_orders": 0,
            "max_total_overfilled_orders": 0,
            "max_worst_adverse_slippage": 0.05,
        },
    }


def scaleup_checks():
    return pd.DataFrame([{"check": "scaleup_ready", "passed": True, "reason": ""}])


def operator_review(approved=True):
    return pd.DataFrame([{"reviewer": "ops", "approved": approved, "reason": "incident closed"}])


def write_inputs(root, *, incident_passed=True, scaleup_ready=True):
    incident = root / "incident"
    scaleup = root / "scaleup"
    incident.mkdir(parents=True, exist_ok=True)
    scaleup.mkdir(parents=True, exist_ok=True)
    incident_summary(incident_passed).to_csv(incident / "halt_incident_summary.csv", index=False)
    scaleup_summary(scaleup_ready).to_csv(scaleup / "scaleup_summary.csv", index=False)
    scaleup_checks().to_csv(scaleup / "scaleup_checks.csv", index=False)
    (scaleup / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    return incident, scaleup


def test_resume_gate_authorizes_clean_incident_and_scaleup():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(),
        scaleup_summary=scaleup_summary(),
        scaleup_checks=scaleup_checks(),
        scaleup_config=scaleup_config(),
    )

    assert report.ready
    assert report.authorization.iloc[0]["max_orders_per_session"] == 10
    assert report.summary.iloc[0]["recommendation"] == "resume_with_scaleup_controls"
    assert report.config["ready"]


def test_resume_gate_blocks_scenario_mismatch():
    report = evaluate_resume_gate(
        incident_summary=incident_summary(scenario_key="trigger_ticks=2"),
        scaleup_summary=scaleup_summary(scenario_key="trigger_ticks=3"),
        scaleup_config=scaleup_config(scenario_key="trigger_ticks=3"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "scenario_match" in failed


def test_write_resume_gate_outputs_artifacts(tmp_path):
    incident, scaleup = write_inputs(tmp_path)
    out_dir = tmp_path / "resume"
    review_path = tmp_path / "operator_review.csv"
    operator_review().to_csv(review_path, index=False)

    report = write_resume_gate_report(
        incident_dir=incident,
        scaleup_dir=scaleup,
        operator_review_path=review_path,
        output_dir=out_dir,
        thresholds=ResumeGateThresholds(require_operator_approval=True),
    )

    assert report.output_dir == out_dir
    assert report.ready
    assert (out_dir / "resume_authorization.csv").exists()
    assert (out_dir / "resume_checks.csv").exists()
    assert (out_dir / "resume_summary.csv").exists()
    assert (out_dir / "resume_config.json").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_resume_gate_fails_when_operator_approval_required(tmp_path):
    incident, scaleup = write_inputs(tmp_path)
    out_dir = tmp_path / "resume"

    code = main(
        [
            "review-resume-gate",
            "--incident",
            str(incident),
            "--scaleup",
            str(scaleup),
            "--out",
            str(out_dir),
            "--require-operator-approval",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "resume_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
