import pandas as pd

from hft_cli import main
from reports.shadow_session import (
    ShadowSessionThresholds,
    evaluate_shadow_session,
    write_shadow_session_report,
)


def launch_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "mode": "shadow",
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "accepted_orders": 2,
                "failed_checks": 0 if ready else 1,
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
                "orders": 2,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def reconciliation_summary(passed=True, *, fill_rate=1.0, unmatched=0, mismatches=0):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "orders": 2,
                "filled_orders": int(2 * fill_rate),
                "unfilled_orders": 2 - int(2 * fill_rate),
                "partial_orders": 0,
                "overfilled_orders": 0,
                "mismatched_orders": mismatches,
                "unmatched_fills": unmatched,
                "order_fill_rate": fill_rate,
                "requested_qty": 150.0,
                "live_qty": 150.0 * fill_rate,
                "max_adverse_slippage": 0.03,
                "avg_adverse_slippage": 0.02,
                "avg_latency_ns": 100.0,
            }
        ]
    )


def checks(passed=True):
    return pd.DataFrame(
        [
            {
                "check": "ready",
                "value": passed,
                "operator": "is",
                "threshold": True,
                "passed": passed,
                "reason": "" if passed else "failed",
            }
        ]
    )


def write_component_dirs(tmp_path, *, accepted=True):
    launch_dir = tmp_path / "launch"
    export_dir = tmp_path / "export"
    reconciliation_dir = tmp_path / "reconciliation"
    launch_dir.mkdir()
    export_dir.mkdir()
    reconciliation_dir.mkdir()
    launch_summary(accepted).to_csv(launch_dir / "launch_summary.csv", index=False)
    checks(accepted).to_csv(launch_dir / "launch_checks.csv", index=False)
    export_summary(accepted).to_csv(export_dir / "broker_order_summary.csv", index=False)
    checks(accepted).to_csv(export_dir / "broker_order_checks.csv", index=False)
    reconciliation_summary(accepted, fill_rate=1.0 if accepted else 0.5).to_csv(
        reconciliation_dir / "reconciliation_summary.csv",
        index=False,
    )
    checks(accepted).to_csv(reconciliation_dir / "reconciliation_checks.csv", index=False)
    return launch_dir, export_dir, reconciliation_dir


def test_evaluate_shadow_session_accepts_clean_shadow_loop():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        thresholds=ShadowSessionThresholds(min_order_fill_rate=1.0, max_adverse_slippage=0.05),
    )

    assert report.accepted
    assert report.metrics.iloc[0]["total_failed_component_checks"] == 0
    assert report.summary.iloc[0]["recommendation"] == "continue_shadow_or_promote"


def test_write_shadow_session_report_outputs_metrics_checks_summary_and_manifest(tmp_path):
    launch_dir, export_dir, reconciliation_dir = write_component_dirs(tmp_path, accepted=True)
    out_dir = tmp_path / "session"

    report = write_shadow_session_report(
        launch_dir=launch_dir,
        export_dir=export_dir,
        reconciliation_dir=reconciliation_dir,
        output_dir=out_dir,
        thresholds=ShadowSessionThresholds(min_order_fill_rate=1.0),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "shadow_session_metrics.csv").exists()
    assert (out_dir / "shadow_session_checks.csv").exists()
    assert (out_dir / "shadow_session_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_shadow_session_fails_on_component_breach(tmp_path):
    launch_dir, export_dir, reconciliation_dir = write_component_dirs(tmp_path, accepted=False)
    out_dir = tmp_path / "cli_session"

    code = main(
        [
            "shadow-session-report",
            "--launch",
            str(launch_dir),
            "--export",
            str(export_dir),
            "--reconciliation",
            str(reconciliation_dir),
            "--out",
            str(out_dir),
            "--min-order-fill-rate",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "shadow_session_checks.csv").exists()
    assert (out_dir / "shadow_session_summary.csv").exists()
