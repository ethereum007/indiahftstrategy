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


def runtime_session_summary(
    ready=True,
    proof_refresh_required=False,
    proof_refresh_ready=True,
    proof_refresh_strategy="lead_lag_taker",
    proof_refresh_market="india_nse_index_derivatives",
    proof_refresh_mixed_identity=False,
    broker_resume_gate_required=False,
    broker_resume_gate_ready=True,
    broker_resume_strategy="lead_lag_taker",
    broker_resume_market="india_nse_index_derivatives",
    broker_resume_proof_refresh_ready=True,
    broker_resume_proof_refresh_strategy="lead_lag_taker",
    broker_resume_proof_refresh_market="india_nse_index_derivatives",
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": "continue" if ready else "halt",
                "halted": not ready,
                "target_mode": "shadow",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "orders_sent": 2,
                "proof_refresh_required": proof_refresh_required,
                "proof_refresh_provided": proof_refresh_required,
                "proof_refresh_ready": proof_refresh_ready,
                "proof_refresh_strategy": proof_refresh_strategy,
                "proof_refresh_market": proof_refresh_market,
                "proof_refresh_mixed_identity": proof_refresh_mixed_identity,
                "proof_source": "latest" if proof_refresh_required else "",
                "broker_resume_gate_required": broker_resume_gate_required,
                "broker_resume_gate_provided": broker_resume_gate_required,
                "broker_resume_gate_ready": broker_resume_gate_ready,
                "broker_resume_strategy": broker_resume_strategy,
                "broker_resume_market": broker_resume_market,
                "broker_resume_proof_refresh_ready": broker_resume_proof_refresh_ready,
                "broker_resume_proof_refresh_strategy": broker_resume_proof_refresh_strategy,
                "broker_resume_proof_refresh_market": broker_resume_proof_refresh_market,
                "telemetry_ready": ready,
                "failed_steps": 0 if ready else 1,
                "failed_checks": 0 if ready else 1,
                "recommendation": "continue_with_controls" if ready else "stop_routing_and_execute_halt_response",
            }
        ]
    )


def broker_readiness_summary(
    ready=True,
    adapter="arrow_money",
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_gap_pairs=0,
    dispatch_roundtrip_provided=True,
    dispatch_roundtrip_ready=True,
    dispatch_roundtrip_strategy="lead_lag_taker",
    dispatch_roundtrip_market="india_nse_index_derivatives",
    dispatch_roundtrip_scenario_key="trigger_ticks=2",
    dispatch_roundtrip_missing_request_acks=0,
    dispatch_roundtrip_rejected_orders=0,
    dispatch_roundtrip_unmatched_acks=0,
    route_dispatch_roundtrip_provided=True,
    route_dispatch_roundtrip_ready=True,
    route_dispatch_roundtrip_strategy="lead_lag_taker",
    route_dispatch_roundtrip_market="india_nse_index_derivatives",
    route_dispatch_roundtrip_scenario_key="trigger_ticks=2",
    broker_vendor_data_readiness_provided=True,
    broker_vendor_data_readiness_ready=True,
    broker_vendor_data_readiness_failed_checks=0,
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "reviewed_vendor_schema",
                "schema_reviewed": True,
                "schema_review_mode": "native_schema",
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "dispatch_roundtrip_provided": dispatch_roundtrip_provided,
                "dispatch_roundtrip_ready": dispatch_roundtrip_ready,
                "dispatch_roundtrip_target_mode": "live_dryrun",
                "dispatch_roundtrip_strategy": dispatch_roundtrip_strategy,
                "dispatch_roundtrip_market": dispatch_roundtrip_market,
                "dispatch_roundtrip_scenario_key": dispatch_roundtrip_scenario_key,
                "dispatch_roundtrip_missing_request_acks": dispatch_roundtrip_missing_request_acks,
                "dispatch_roundtrip_rejected_orders": dispatch_roundtrip_rejected_orders,
                "dispatch_roundtrip_unmatched_acks": dispatch_roundtrip_unmatched_acks,
                "route_dispatch_roundtrip_provided": route_dispatch_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_dispatch_roundtrip_ready,
                "route_dispatch_roundtrip_strategy": route_dispatch_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_dispatch_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_dispatch_roundtrip_scenario_key,
                "broker_vendor_data_readiness_provided": broker_vendor_data_readiness_provided,
                "broker_vendor_data_readiness_ready": broker_vendor_data_readiness_ready,
                "broker_vendor_data_readiness_failed_checks": broker_vendor_data_readiness_failed_checks,
                "failed_checks": 0 if ready else 1,
                "recommendation": "broker_integration_ready" if ready else "fix_broker_readiness_gaps",
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


def test_evaluate_shadow_session_accepts_runtime_guard_continue_evidence():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True),
    )

    row = report.metrics.iloc[0]
    assert report.accepted
    assert bool(row["runtime_session_provided"])
    assert row["runtime_guard_action"] == "continue"
    assert row["runtime_strategy"] == "lead_lag_taker"
    assert row["runtime_market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"


def test_evaluate_shadow_session_carries_runtime_proof_refresh_evidence():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True, proof_refresh_required=True),
    )

    row = report.metrics.iloc[0]
    summary = report.summary.iloc[0]
    assert report.accepted
    assert bool(row["runtime_proof_refresh_required"])
    assert bool(row["runtime_proof_refresh_ready"])
    assert row["runtime_proof_refresh_strategy"] == "lead_lag_taker"
    assert summary["runtime_proof_source"] == "latest"
    assert bool(summary["runtime_proof_refresh_provided"])


def test_evaluate_shadow_session_blocks_bad_runtime_proof_refresh_evidence():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(
            True,
            proof_refresh_required=True,
            proof_refresh_ready=False,
            proof_refresh_strategy="surface_mm",
            proof_refresh_market="us_options_regular",
            proof_refresh_mixed_identity=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {
        "runtime_proof_refresh_ready",
        "runtime_proof_refresh_identity_consistent",
        "runtime_proof_refresh_strategy_matches",
        "runtime_proof_refresh_market_matches",
    } <= failed


def test_evaluate_shadow_session_carries_runtime_broker_resume_gate_evidence():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True, broker_resume_gate_required=True),
    )

    row = report.metrics.iloc[0]
    summary = report.summary.iloc[0]
    assert report.accepted
    assert bool(row["runtime_broker_resume_gate_required"])
    assert bool(row["runtime_broker_resume_gate_ready"])
    assert row["runtime_broker_resume_strategy"] == "lead_lag_taker"
    assert bool(row["runtime_broker_resume_proof_refresh_ready"])
    assert row["runtime_broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"
    assert bool(summary["runtime_broker_resume_gate_provided"])
    assert summary["runtime_broker_resume_proof_refresh_strategy"] == "lead_lag_taker"


def test_evaluate_shadow_session_carries_broker_readiness_route_proof():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True),
        broker_readiness_summary=broker_readiness_summary(True),
        thresholds=ShadowSessionThresholds(require_broker_readiness=True),
    )

    row = report.metrics.iloc[0]
    summary = report.summary.iloc[0]
    assert report.accepted
    assert bool(row["broker_readiness_provided"])
    assert bool(row["broker_route_readiness_ready"])
    assert row["broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(row["broker_route_readiness_gap_pairs"]) == 0
    assert bool(summary["broker_dispatch_roundtrip_ready"])
    assert bool(summary["broker_route_dispatch_roundtrip_ready"])
    assert bool(row["broker_vendor_data_readiness_ready"])
    assert int(summary["broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["broker_schema_review_mode"] == "native_schema"


def test_evaluate_shadow_session_blocks_bad_broker_readiness_route_proof():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            route_readiness_ready=False,
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
            route_readiness_gap_pairs=2,
            dispatch_roundtrip_strategy="surface_mm",
            dispatch_roundtrip_market="us_options_regular",
            dispatch_roundtrip_scenario_key="wrong-scenario",
            dispatch_roundtrip_missing_request_acks=1,
            dispatch_roundtrip_rejected_orders=1,
            dispatch_roundtrip_unmatched_acks=1,
            route_dispatch_roundtrip_ready=False,
            route_dispatch_roundtrip_strategy="surface_mm",
            route_dispatch_roundtrip_market="us_options_regular",
            route_dispatch_roundtrip_scenario_key="wrong-scenario",
        ),
        thresholds=ShadowSessionThresholds(require_broker_readiness=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {
        "broker_route_readiness_ready",
        "broker_route_readiness_strategy_matches",
        "broker_route_readiness_market_matches",
        "broker_route_readiness_gap_pairs",
        "broker_dispatch_roundtrip_strategy_matches",
        "broker_dispatch_roundtrip_market_matches",
        "broker_dispatch_roundtrip_scenario_matches",
        "broker_dispatch_roundtrip_missing_request_acks",
        "broker_dispatch_roundtrip_rejected_orders",
        "broker_dispatch_roundtrip_unmatched_acks",
        "broker_route_dispatch_roundtrip_ready",
        "broker_route_dispatch_roundtrip_strategy_matches",
        "broker_route_dispatch_roundtrip_market_matches",
        "broker_route_dispatch_roundtrip_scenario_matches",
    } <= failed


def test_evaluate_shadow_session_blocks_bad_broker_vendor_data_readiness():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            broker_vendor_data_readiness_ready=False,
            broker_vendor_data_readiness_failed_checks=1,
        ),
        thresholds=ShadowSessionThresholds(require_broker_readiness=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.accepted
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary["broker_vendor_data_readiness_provided"])
    assert not bool(summary["broker_vendor_data_readiness_ready"])
    assert int(summary["broker_vendor_data_readiness_failed_checks"]) == 1


def test_evaluate_shadow_session_blocks_bad_runtime_broker_resume_gate_evidence():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(
            True,
            broker_resume_gate_required=True,
            broker_resume_gate_ready=False,
            broker_resume_strategy="surface_mm",
            broker_resume_market="us_options_regular",
            broker_resume_proof_refresh_ready=False,
            broker_resume_proof_refresh_strategy="surface_mm",
            broker_resume_proof_refresh_market="us_options_regular",
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {
        "runtime_broker_resume_gate_ready",
        "runtime_broker_resume_strategy_matches",
        "runtime_broker_resume_market_matches",
        "runtime_broker_resume_proof_refresh_ready",
        "runtime_broker_resume_proof_refresh_strategy_matches",
        "runtime_broker_resume_proof_refresh_market_matches",
    } <= failed


def test_evaluate_shadow_session_blocks_halted_runtime_guard():
    report = evaluate_shadow_session(
        launch_summary=launch_summary(True),
        launch_checks=checks(True),
        export_summary=export_summary(True),
        export_checks=checks(True),
        reconciliation_summary=reconciliation_summary(True),
        reconciliation_checks=checks(True),
        runtime_session_summary=runtime_session_summary(False),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert {"runtime_session_ready", "runtime_guard_continue", "total_failed_component_checks"} <= failed


def test_write_shadow_session_report_outputs_metrics_checks_summary_and_manifest(tmp_path):
    launch_dir, export_dir, reconciliation_dir = write_component_dirs(tmp_path, accepted=True)
    broker_dir = tmp_path / "broker"
    out_dir = tmp_path / "session"
    broker_dir.mkdir()
    broker_readiness_summary(True).to_csv(broker_dir / "broker_readiness_summary.csv", index=False)

    report = write_shadow_session_report(
        launch_dir=launch_dir,
        export_dir=export_dir,
        reconciliation_dir=reconciliation_dir,
        broker_readiness_dir=broker_dir,
        output_dir=out_dir,
        thresholds=ShadowSessionThresholds(min_order_fill_rate=1.0, require_broker_readiness=True),
    )

    assert report.output_dir == out_dir
    assert report.accepted
    assert bool(report.summary.iloc[0]["broker_readiness_ready"])
    assert bool(report.summary.iloc[0]["broker_vendor_data_readiness_ready"])
    assert (out_dir / "shadow_session_metrics.csv").exists()
    assert (out_dir / "shadow_session_checks.csv").exists()
    assert (out_dir / "shadow_session_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_shadow_session_requires_runtime_session_when_requested(tmp_path):
    launch_dir, export_dir, reconciliation_dir = write_component_dirs(tmp_path, accepted=True)
    out_dir = tmp_path / "cli_session_missing_runtime"

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
            "--require-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks_out = pd.read_csv(out_dir / "shadow_session_checks.csv")
    failed = set(checks_out.loc[~checks_out["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed


def test_unified_cli_shadow_session_requires_broker_readiness_when_requested(tmp_path):
    launch_dir, export_dir, reconciliation_dir = write_component_dirs(tmp_path, accepted=True)
    out_dir = tmp_path / "cli_session_missing_broker"

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
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    checks_out = pd.read_csv(out_dir / "shadow_session_checks.csv")
    failed = set(checks_out.loc[~checks_out["passed"].astype(bool), "check"])
    assert code == 2
    assert "broker_readiness_provided" in failed


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
