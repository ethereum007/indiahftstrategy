import pandas as pd

from adapters.broker_readiness import (
    BrokerReadinessThresholds,
    evaluate_broker_readiness,
    write_broker_readiness_report,
)
from hft_cli import main


def schema_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": "orders",
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "missing_required_columns": 0 if ready else 1,
                "all_required_present": ready,
            }
        ]
    )


def order_export_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def upload_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0 if ready else 1,
                "recommendation": "internal_upload_ready" if adapter == "normalized" else "dry_run_or_paper_review",
            }
        ]
    )


def runtime_session_summary(adapter="normalized", ready=True, halted=False):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "target_mode": "shadow",
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "failed_checks": 1 if halted else 0,
                "recommendation": "stop_routing_and_execute_halt_response" if halted else "continue_with_controls",
            }
        ]
    )


def resume_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "incident_strategy": "surface_mm",
                "incident_market": "india_nse_index_derivatives",
                "proof_refresh_ready": ready,
                "proof_refresh_strategy": "surface_mm",
                "proof_refresh_market": "india_nse_index_derivatives",
                "incident_proof_refresh_strategy": "surface_mm",
                "incident_proof_refresh_market": "india_nse_index_derivatives",
                "failed_checks": 0 if ready else 1,
                "recommendation": "resume_with_scaleup_controls" if ready else "keep_trading_disabled",
            }
        ]
    )


def dispatch_roundtrip_summary(
    adapter="normalized",
    passed=True,
    failed_checks=None,
    route_provided=True,
    route_ready=True,
    route_target_mode="live_dryrun",
    route_strategy="lead_lag_taker",
    route_market="india_nse_index_derivatives",
    route_scenario_key="trigger_ticks=2",
    route_batch_id="BDP-0",
    route_requests=2,
    route_acked_orders=2,
    route_missing_request_acks=0,
    route_rejected_orders=0,
    route_unmatched_acks=0,
):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "adapter": adapter,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "dispatch_batch_id": "BDP-1",
                "dispatch_orders": 2,
                "send_requests": 2,
                "acked_orders": 2 if passed else 1,
                "missing_request_acks": 0 if passed else 1,
                "rejected_orders": 0,
                "duplicate_ack_orders": 0,
                "unmatched_acks": 0,
                "route_dispatch_roundtrip_required": True,
                "route_dispatch_roundtrip_provided": route_provided,
                "route_dispatch_roundtrip_ready": route_ready,
                "route_dispatch_roundtrip_target_mode": route_target_mode,
                "route_dispatch_roundtrip_strategy": route_strategy,
                "route_dispatch_roundtrip_market": route_market,
                "route_dispatch_roundtrip_scenario_key": route_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_batch_id,
                "route_dispatch_roundtrip_requests": route_requests,
                "route_dispatch_roundtrip_acked_orders": route_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_unmatched_acks,
                "failed_checks": (0 if passed else 1) if failed_checks is None else failed_checks,
                "recommendation": "broker_dry_run_roundtrip_proved"
                if passed
                else "investigate_broker_dry_run_roundtrip",
            }
        ]
    )


def test_broker_readiness_accepts_ready_normalized_artifacts():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized"),
    )

    assert report.ready
    assert report.summary.iloc[0]["recommendation"] == "broker_integration_ready"
    assert set(report.checks["passed"]) == {True}


def test_broker_readiness_accepts_required_runtime_session():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        runtime_session_summary=runtime_session_summary("normalized", ready=True, halted=False),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert report.ready
    runtime_item = report.items.loc[report.items["component"] == "runtime_session"].iloc[0]
    assert bool(runtime_item["ready"])
    assert runtime_item["runtime_guard_action"] == "continue"
    assert runtime_item["runtime_target_mode"] == "shadow"
    assert runtime_item["runtime_strategy"] == "surface_mm"
    assert runtime_item["runtime_market"] == "india_nse_index_derivatives"
    summary = report.summary.iloc[0]
    assert bool(summary["runtime_session_provided"])
    assert bool(summary["runtime_session_ready"])
    assert summary["runtime_guard_action"] == "continue"
    assert not bool(summary["runtime_guard_halted"])
    assert summary["runtime_target_mode"] == "shadow"
    assert summary["runtime_strategy"] == "surface_mm"
    assert summary["runtime_market"] == "india_nse_index_derivatives"


def test_broker_readiness_accepts_required_resume_gate():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        resume_summary=resume_summary("normalized", ready=True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_resume_gate=True),
    )

    assert report.ready
    resume_item = report.items.loc[report.items["component"] == "resume_gate"].iloc[0]
    assert bool(resume_item["ready"])
    assert resume_item["resume_strategy"] == "surface_mm"
    assert resume_item["resume_proof_refresh_strategy"] == "surface_mm"
    summary = report.summary.iloc[0]
    assert bool(summary["resume_gate_provided"])
    assert bool(summary["resume_gate_ready"])
    assert bool(summary["resume_proof_refresh_ready"])
    assert summary["resume_strategy"] == "surface_mm"
    assert summary["resume_incident_market"] == "india_nse_index_derivatives"
    assert summary["resume_proof_refresh_market"] == "india_nse_index_derivatives"


def test_broker_readiness_accepts_required_dispatch_roundtrip():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["ready"])
    assert item["dispatch_roundtrip_target_mode"] == "live_dryrun"
    assert item["dispatch_roundtrip_strategy"] == "lead_lag_taker"
    assert int(item["dispatch_roundtrip_acked_orders"]) == 2
    summary = report.summary.iloc[0]
    assert bool(summary["dispatch_roundtrip_provided"])
    assert bool(summary["dispatch_roundtrip_ready"])
    assert summary["dispatch_roundtrip_batch_id"] == "BDP-1"
    assert int(summary["dispatch_roundtrip_requests"]) == 2
    assert int(summary["dispatch_roundtrip_missing_request_acks"]) == 0
    assert int(summary["dispatch_roundtrip_failed_checks"]) == 0
    assert bool(summary["route_dispatch_roundtrip_provided"])
    assert bool(summary["route_dispatch_roundtrip_ready"])
    assert summary["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert int(summary["route_dispatch_roundtrip_requests"]) == 2


def test_broker_readiness_fails_for_missing_route_dispatch_roundtrip_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_provided=False,
            route_ready=False,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert not bool(report.summary.iloc[0]["route_dispatch_roundtrip_provided"])


def test_broker_readiness_fails_for_dirty_route_dispatch_roundtrip_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_ready=False,
            route_target_mode="shadow",
            route_strategy="surface_mm",
            route_market="us_options_regular",
            route_scenario_key="wrong-scenario",
            route_requests=1,
            route_acked_orders=1,
            route_missing_request_acks=1,
            route_rejected_orders=1,
            route_unmatched_acks=1,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_target_mode_matches",
        "route_dispatch_roundtrip_strategy_matches",
        "route_dispatch_roundtrip_market_matches",
        "route_dispatch_roundtrip_scenario_matches",
        "route_dispatch_roundtrip_request_count_matches",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert int(report.summary.iloc[0]["route_dispatch_roundtrip_missing_request_acks"]) == 1


def test_broker_readiness_blocks_halted_runtime_session():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        runtime_session_summary=runtime_session_summary("normalized", ready=False, halted=True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert not report.ready
    runtime_item = report.items.loc[report.items["component"] == "runtime_session"].iloc[0]
    assert bool(runtime_item["runtime_guard_halted"])
    summary = report.summary.iloc[0]
    assert bool(summary["runtime_session_provided"])
    assert not bool(summary["runtime_session_ready"])
    assert summary["runtime_guard_action"] == "halt"
    assert bool(summary["runtime_guard_halted"])
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_session_ready" in failed


def test_broker_readiness_fails_when_required_dispatch_roundtrip_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_provided" in failed


def test_broker_readiness_fails_for_failed_dispatch_roundtrip():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", False),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert not bool(item["ready"])
    assert int(item["dispatch_roundtrip_missing_request_acks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_ready" in failed


def test_broker_readiness_fails_for_inconsistent_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True, failed_checks=1),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert not bool(item["ready"])
    assert int(report.summary.iloc[0]["dispatch_roundtrip_failed_checks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_ready" in failed


def test_broker_readiness_fails_closed_for_placeholder_broker_schema():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(adapter="arrow_money"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "schema_reviewed" in failed
    assert report.summary.iloc[0]["recommendation"] == "obtain_vendor_schema_samples"


def test_broker_readiness_fails_when_required_upload_pack_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "upload_pack_provided" in failed


def test_broker_readiness_fails_when_required_runtime_session_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_session_provided" in failed


def test_broker_readiness_fails_when_required_resume_gate_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_resume_gate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "resume_gate_provided" in failed


def test_write_broker_readiness_outputs_artifacts(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    resume_dir = tmp_path / "resume"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    schema_dir.mkdir()
    export_dir.mkdir()
    upload_dir.mkdir()
    resume_dir.mkdir()
    roundtrip_dir.mkdir()
    schema_summary("arrow_money", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("arrow_money", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("arrow_money", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    resume_summary("arrow_money", True).to_csv(resume_dir / "resume_summary.csv", index=False)
    dispatch_roundtrip_summary("arrow_money", True).to_csv(
        roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        resume_dir=resume_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_resume_gate=True,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    assert report.output_dir == out_dir
    assert report.summary.iloc[0]["recommendation"] == "dry_run_only_until_vendor_schema_review"
    assert report.summary.iloc[0]["resume_strategy"] == "surface_mm"
    assert bool(report.summary.iloc[0]["resume_gate_ready"])
    assert bool(report.summary.iloc[0]["dispatch_roundtrip_ready"])
    assert (out_dir / "broker_readiness_items.csv").exists()
    assert (out_dir / "broker_readiness_checks.csv").exists()
    assert (out_dir / "broker_readiness_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_broker_readiness_can_fail_on_placeholder_schema(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    schema_dir.mkdir()
    export_dir.mkdir()
    upload_dir.mkdir()
    schema_summary("arrow_money", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("arrow_money", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("arrow_money", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "schema_reviewed" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_broker_readiness_can_require_runtime_session(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed


def test_cli_broker_readiness_can_require_resume_gate(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-resume-gate",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "resume_gate_provided" in failed


def test_cli_broker_readiness_can_require_dispatch_roundtrip(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "dispatch_roundtrip_provided" in failed
