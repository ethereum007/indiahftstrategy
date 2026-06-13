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


def test_write_broker_readiness_outputs_artifacts(tmp_path):
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

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        thresholds=BrokerReadinessThresholds(adapter="arrow_money", require_reviewed_schema=False),
    )

    assert report.ready
    assert report.output_dir == out_dir
    assert report.summary.iloc[0]["recommendation"] == "dry_run_only_until_vendor_schema_review"
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
