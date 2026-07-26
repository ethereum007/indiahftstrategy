import json

import pandas as pd

from adapters.order_upload_pack import (
    OrderUploadPackConfig,
    build_order_upload_pack,
    verify_order_upload_pack_evidence,
    write_order_upload_pack,
)
from hft_cli import main
from reports.manifest import verify_experiment_manifest, write_experiment_manifest


def broker_orders():
    return pd.DataFrame(
        [
            {
                "broker_order_id": "ARROW_MONEY-000000-STG-1",
                "client_order_id": "STG-1",
                "instrument_id": "NIFTY24JUN22500CE",
                "side": 1,
                "side_text": "BUY",
                "qty": 75,
                "price": 10.0,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "route_tag": "shadow_nse",
                "lifecycle_action": "submit",
                "lifecycle_action_id": "ACT-000001",
                "lifecycle_reason": "new_quote",
                "lifecycle_message_count": 1,
                "quote_age_ns": 0,
                "replaces_order_id": "",
            },
            {
                "broker_order_id": "ARROW_MONEY-000001-STG-2",
                "client_order_id": "STG-2",
                "instrument_id": "NIFTY24JUN22500PE",
                "side": -1,
                "side_text": "SELL",
                "qty": 150,
                "price": 11.5,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "route_tag": "shadow_nse",
                "lifecycle_action": "replace",
                "lifecycle_action_id": "ACT-000002",
                "lifecycle_reason": "price_or_qty_change",
                "lifecycle_message_count": 2,
                "quote_age_ns": 100,
                "replaces_order_id": "QLF-000001",
            },
        ]
    )


def resolved_broker_orders():
    orders = broker_orders()
    orders["research_instrument_id"] = [
        "NIFTY_20260630_22500C",
        "NIFTY_20260630_22500P",
    ]
    orders["broker_instrument_token"] = ["10001", "10002"]
    orders["instrument_resolution_method"] = [
        "semantic_option_identity",
        "semantic_option_identity",
    ]
    orders["instrument_resolution_status"] = ["resolved", "resolved"]
    orders["leg_group_id"] = ["PARITY-1", "PARITY-1"]
    orders["leg_role"] = ["CALL", "PUT"]
    orders["leg_count"] = [2, 2]
    return orders


def write_export(path):
    path.mkdir(parents=True, exist_ok=True)
    broker_orders().to_csv(path / "broker_orders.csv", index=False)


def test_build_order_upload_pack_maps_arrow_money_template_for_dry_run():
    report = build_order_upload_pack(
        broker_orders(),
        config=OrderUploadPackConfig(adapter="arrow_money", require_reviewed_schema=False),
    )

    assert report.ready
    assert report.orders.columns.tolist() == [
        "exchange",
        "tradingsymbol",
        "transaction_type",
        "quantity",
        "order_type",
        "product",
        "price",
        "validity",
        "client_order_id",
        "tag",
        "lifecycle_action",
        "lifecycle_action_id",
        "lifecycle_reason",
        "lifecycle_message_count",
        "quote_age_ns",
        "replaces_order_id",
    ]
    assert report.orders["exchange"].tolist() == ["NFO", "NFO"]
    assert report.orders["transaction_type"].tolist() == ["BUY", "SELL"]
    assert report.orders["product"].tolist() == ["MIS", "MIS"]
    assert str(report.orders["quantity"].dtype) == "Int64"
    assert report.orders["lifecycle_action"].tolist() == ["submit", "replace"]
    assert report.orders.loc[1, "replaces_order_id"] == "QLF-000001"
    assert int(report.summary.loc[0, "replace_orders"]) == 1
    assert int(report.summary.loc[0, "failed_check_count"]) == 0
    assert report.summary.loc[0, "failed_check_names"] == ""
    assert report.summary.loc[0, "primary_blocker_check"] == ""
    assert report.summary.iloc[0]["recommendation"] == "dry_run_or_paper_review"
    assert int(report.summary.loc[0, "action_queue_count"]) == 0
    assert int(report.summary.loc[0, "blocked_action_count"]) == 0
    assert report.summary.loc[0, "next_gate"] == ""
    assert report.summary.loc[0, "next_gate_help_command"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_order_upload_pack_fails_closed_for_placeholder_schema_by_default():
    report = build_order_upload_pack(
        broker_orders(),
        config=OrderUploadPackConfig(adapter="arrow_money"),
    )

    assert not report.ready
    assert not report.orders.empty
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["check"] == "schema_reviewed"
    assert "placeholder" in failed["reason"]
    summary = report.summary.iloc[0]
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "schema_reviewed"
    assert summary["first_failed_reason"] == "adapter schema is still a placeholder; review vendor sample before live upload"
    assert summary["primary_blocker_check"] == "schema_reviewed"
    assert summary["primary_blocker_value"] == "placeholder_normalized_pending_vendor_schema"
    assert summary["primary_blocker_operator"] == "!="
    assert summary["primary_blocker_threshold"] == "placeholder"
    assert summary["primary_blocker_reason"] == "adapter schema is still a placeholder; review vendor sample before live upload"
    assert int(summary["action_queue_count"]) == 1
    assert int(summary["blocked_action_count"]) == 1
    assert summary["next_gate"] == "pack-broker-upload"
    assert summary["next_gate_help_command"] == "python -m hft_cli pack-broker-upload --help"
    assert summary["primary_action_status"] == "blocked"
    assert report.action_queue is not None
    action = report.action_queue.iloc[0]
    assert action["check"] == "schema_reviewed"
    assert action["component"] == "schema_review"
    assert action["recommendation"] == "review_real_broker_upload_schema_or_allow_placeholder_for_dry_run"


def test_order_upload_pack_writes_broker_contract_identity_sidecar():
    report = build_order_upload_pack(
        resolved_broker_orders(),
        config=OrderUploadPackConfig(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_instrument_resolution=True,
        ),
    )

    assert report.ready
    assert bool(report.summary.loc[0, "instrument_resolution_ready"])
    assert report.summary.loc[0, "upload_identity_match_orders"] == 2
    assert report.summary.loc[0, "broker_instrument_token_orders"] == 2
    assert report.contract_identity["upload_instrument_id"].tolist() == [
        "NIFTY24JUN22500CE",
        "NIFTY24JUN22500PE",
    ]
    assert report.contract_identity["broker_instrument_token"].tolist() == [
        "10001",
        "10002",
    ]
    assert report.contract_identity["resolution_row_ready"].all()


def test_order_upload_pack_blocks_resolved_order_with_missing_token():
    orders = resolved_broker_orders()
    orders.loc[1, "broker_instrument_token"] = ""

    report = build_order_upload_pack(
        orders,
        config=OrderUploadPackConfig(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_instrument_resolution=True,
        ),
    )

    failed = report.checks.loc[
        ~report.checks["passed"].astype(bool)
    ].set_index("check")
    assert not report.ready
    assert "broker_instrument_token_complete" in failed.index
    assert (
        report.action_queue.iloc[0]["next_gate"]
        == "resolve-broker-instruments"
    )


def test_order_upload_pack_surfaces_first_failed_mapping_field():
    orders = broker_orders().drop(columns=["price"])

    report = build_order_upload_pack(
        orders,
        config=OrderUploadPackConfig(adapter="arrow_money", require_reviewed_schema=False),
    )

    assert not report.ready
    summary = report.summary.iloc[0]
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "mapping_ready"
    assert summary["first_failed_reason"] == "price: required target has no available source column or default value"
    assert summary["primary_blocker_check"] == "mapping_ready"
    assert summary["primary_blocker_value"] == "1"
    assert summary["primary_blocker_operator"] == "=="
    assert summary["primary_blocker_threshold"] == "0"
    assert summary["primary_blocker_reason"] == "price: required target has no available source column or default value"
    assert int(summary["action_queue_count"]) == 1
    assert int(summary["blocked_action_count"]) == 1
    assert summary["next_gate"] == "pack-broker-upload"
    assert report.action_queue is not None
    action = report.action_queue.iloc[0]
    assert action["check"] == "mapping_ready"
    assert action["component"] == "mapping"
    assert "price" in action["reason"]


def test_write_order_upload_pack_outputs_files_and_manifest(tmp_path):
    export_dir = tmp_path / "export"
    out_dir = tmp_path / "upload"
    write_export(export_dir)

    report = write_order_upload_pack(
        export_dir,
        output_dir=out_dir,
        config=OrderUploadPackConfig(
            adapter="irage",
            require_reviewed_schema=False,
            output_filename="irage_upload_orders.csv",
        ),
    )

    assert report.ready
    assert report.output_dir == out_dir
    assert (out_dir / "irage_upload_orders.csv").exists()
    assert (out_dir / "broker_upload_mapping.csv").exists()
    assert (out_dir / "broker_upload_checks.csv").exists()
    assert (out_dir / "broker_upload_summary.csv").exists()
    assert (out_dir / "broker_upload_schema.csv").exists()
    assert (out_dir / "broker_upload_contract_identity.csv").exists()
    assert (out_dir / "broker_upload_action_queue.csv").exists()
    assert (out_dir / "broker_upload_config.json").exists()
    assert (out_dir / "broker_upload_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "broker_upload_action_queue.csv")
    assert queue.empty
    config = json.loads((out_dir / "broker_upload_config.json").read_text(encoding="utf-8"))
    assert config["ready"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    runbook = (out_dir / "broker_upload_runbook.md").read_text(encoding="utf-8")
    assert "# Broker Upload Pack Runbook" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "broker_upload_action_queue.csv" in artifact_paths
    assert "broker_upload_config.json" in artifact_paths
    assert "broker_upload_runbook.md" in artifact_paths
    assert "broker_upload_contract_identity.csv" in artifact_paths
    integrity = verify_order_upload_pack_evidence(out_dir)
    assert integrity.passed
    assert integrity.manifest_current
    assert integrity.artifacts_consistent
    assert integrity.rebuilt_artifact_count == 9
    assert integrity.rebuilt_artifact_match_count == 9


def test_order_upload_pack_verifier_rejects_remanifested_sidecar_tamper(
    tmp_path,
):
    export_dir = tmp_path / "export"
    out_dir = tmp_path / "upload"
    write_export(export_dir)
    config = OrderUploadPackConfig(
        adapter="arrow_money",
        require_reviewed_schema=False,
    )
    write_order_upload_pack(
        export_dir,
        output_dir=out_dir,
        config=config,
    )
    identity_path = out_dir / "broker_upload_contract_identity.csv"
    identity = pd.read_csv(identity_path)
    identity.loc[0, "broker_instrument_id"] = "FORGED-CONTRACT"
    identity.to_csv(identity_path, index=False)
    write_experiment_manifest(
        out_dir,
        run_type="order_upload_pack",
        parameters={"config": config.__dict__},
        inputs={"broker_orders": export_dir / "broker_orders.csv"},
    )

    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="order_upload_pack",
        require_input_fingerprints=True,
    ).passed
    integrity = verify_order_upload_pack_evidence(out_dir)
    assert integrity.manifest_current
    assert not integrity.artifacts_consistent
    assert not integrity.passed
    assert (
        "artifact_content_mismatch:broker_upload_contract_identity.csv"
        in integrity.consistency_error
    )

    borrowed = out_dir / "borrowed_contract_identity.csv"
    borrowed.write_bytes(identity_path.read_bytes())
    borrowed_integrity = verify_order_upload_pack_evidence(borrowed)
    assert not borrowed_integrity.artifacts_consistent
    assert not borrowed_integrity.passed
    assert (
        "contract_identity_path_not_manifest_bound"
        in borrowed_integrity.consistency_error
    )


def test_cli_pack_broker_upload_returns_failure_until_schema_allowed(tmp_path):
    export_dir = tmp_path / "export"
    out_dir = tmp_path / "upload"
    write_export(export_dir)

    code = main(
        [
            "pack-broker-upload",
            "--export",
            str(export_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_upload_summary.csv")
    queue = pd.read_csv(out_dir / "broker_upload_action_queue.csv")
    config = json.loads((out_dir / "broker_upload_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_upload_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert summary.loc[0, "failed_check_names"] == "schema_reviewed"
    assert summary.loc[0, "primary_blocker_check"] == "schema_reviewed"
    assert summary.loc[0, "primary_blocker_reason"] == "adapter schema is still a placeholder; review vendor sample before live upload"
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert summary.loc[0, "next_gate"] == "pack-broker-upload"
    assert queue.loc[0, "check"] == "schema_reviewed"
    assert queue.loc[0, "component"] == "schema_review"
    assert config["primary_action"]["check"] == "schema_reviewed"
    assert "adapter schema is still a placeholder" in runbook
    assert (out_dir / "broker_upload_orders.csv").exists()


def test_cli_pack_broker_upload_can_fail_on_actions(tmp_path):
    export_dir = tmp_path / "export"
    out_dir = tmp_path / "upload"
    write_export(export_dir)

    code = main(
        [
            "pack-broker-upload",
            "--export",
            str(export_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_upload_summary.csv")
    assert code == 2
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert summary.loc[0, "primary_action_status"] == "blocked"
