import pandas as pd

from hft_cli import main
from reports.halt_incident import (
    HaltIncidentThresholds,
    evaluate_halt_incident,
    write_halt_incident_report,
)


def guard_summary(action="halt"):
    return pd.DataFrame(
        [
            {
                "guard_action": action,
                "halted": action == "halt",
                "failed_checks": 1 if action == "halt" else 0,
                "failed_check_names": "orders_sent" if action == "halt" else "",
                "first_failed_reason": "orders_sent: limit breached" if action == "halt" else "",
                "failed_check_reasons": "orders_sent: limit breached" if action == "halt" else "",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "orders_sent": 12,
                "recommendation": "stop_routing_and_investigate" if action == "halt" else "continue_with_controls",
            }
        ]
    )


def guard_checks():
    return pd.DataFrame([{"check": "orders_sent", "passed": False, "reason": "limit breached"}])


def response_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": "halt",
                "cancel_orders": 1,
                "flatten_orders": 1,
                "open_risk_items": 2,
                "failed_checks": 0 if ready else 1,
                "guard_failed_check_names": "orders_sent",
                "guard_first_failed_reason": "orders_sent: limit breached",
                "guard_failed_check_reasons": "orders_sent: limit breached",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "recommendation": "submit_cancel_and_flatten" if ready else "do_not_execute_response_until_inputs_fixed",
            }
        ]
    )


def export_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "cancel_orders": 1,
                "flatten_orders": 1,
                "failed_checks": 0 if ready else 1,
                "recommendation": "send_halt_actions_to_broker" if ready else "fix_halt_action_export",
            }
        ]
    )


def execution_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "cancel_actions": 1,
                "cancel_acked": 1 if passed else 0,
                "flatten_actions": 1,
                "flatten_filled": 1 if passed else 0,
                "nonflat_positions": 0 if passed else 1,
                "failed_checks": 0 if passed else 2,
                "recommendation": "halt_completed" if passed else "continue_halt_investigation",
            }
        ]
    )


def passing_checks():
    return pd.DataFrame([{"check": "component_ready", "passed": True, "reason": ""}])


def write_inputs(root, *, execution_passed=True, include_export=True):
    guard = root / "guard"
    response = root / "response"
    export = root / "export"
    execution = root / "execution"
    for path in (guard, response, execution):
        path.mkdir(parents=True, exist_ok=True)
    if include_export:
        export.mkdir(parents=True, exist_ok=True)
    guard_summary().to_csv(guard / "runtime_guard_summary.csv", index=False)
    guard_checks().to_csv(guard / "runtime_guard_checks.csv", index=False)
    response_summary().to_csv(response / "halt_response_summary.csv", index=False)
    passing_checks().to_csv(response / "halt_response_checks.csv", index=False)
    if include_export:
        export_summary().to_csv(export / "halt_response_export_summary.csv", index=False)
        passing_checks().to_csv(export / "halt_response_export_checks.csv", index=False)
    execution_summary(execution_passed).to_csv(execution / "halt_execution_summary.csv", index=False)
    passing_checks().to_csv(execution / "halt_execution_checks.csv", index=False)
    return guard, response, export, execution


def test_halt_incident_accepts_completed_halt_with_export():
    report = evaluate_halt_incident(
        guard_summary=guard_summary(),
        guard_checks=guard_checks(),
        halt_response_summary=response_summary(),
        halt_response_checks=passing_checks(),
        halt_export_summary=export_summary(),
        halt_export_checks=passing_checks(),
        halt_execution_summary=execution_summary(),
        halt_execution_checks=passing_checks(),
        thresholds=HaltIncidentThresholds(require_export_ready=True),
    )

    assert report.passed
    assert report.summary.iloc[0]["incident_status"] == "halt_completed"
    assert report.summary.iloc[0]["guard_failed_check_names"] == "orders_sent"
    assert report.summary.iloc[0]["guard_first_failed_reason"] == "orders_sent: limit breached"
    assert report.timeline.loc[0, "failed_check_names"] == "orders_sent"
    assert report.timeline.loc[1, "guard_failed_check_names"] == "orders_sent"
    assert report.timeline["component"].tolist() == [
        "runtime_guard",
        "halt_response",
        "halt_export",
        "halt_execution",
    ]


def test_halt_incident_fails_when_execution_is_incomplete():
    report = evaluate_halt_incident(
        guard_summary=guard_summary(),
        halt_response_summary=response_summary(),
        halt_execution_summary=execution_summary(False),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "halt_execution_passed" in failed


def test_write_halt_incident_report_outputs_artifacts(tmp_path):
    guard, response, export, execution = write_inputs(tmp_path)
    out_dir = tmp_path / "incident"

    report = write_halt_incident_report(
        guard_dir=guard,
        halt_response_dir=response,
        halt_export_dir=export,
        halt_execution_dir=execution,
        output_dir=out_dir,
        thresholds=HaltIncidentThresholds(require_export_ready=True),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "halt_incident_timeline.csv").exists()
    assert (out_dir / "halt_incident_checks.csv").exists()
    assert (out_dir / "halt_incident_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_halt_incident_can_require_export(tmp_path):
    guard, response, _, execution = write_inputs(tmp_path, include_export=False)
    out_dir = tmp_path / "incident"

    code = main(
        [
            "review-halt-incident",
            "--guard",
            str(guard),
            "--halt-response",
            str(response),
            "--halt-execution",
            str(execution),
            "--out",
            str(out_dir),
            "--require-export",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "halt_incident_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
