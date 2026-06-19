import json

import pandas as pd

from adapters.mapped_order_export import MappedOrderExportConfig, map_broker_orders
from adapters.order_mapping_draft import (
    OrderMappingDraftConfig,
    draft_order_mapping,
    write_order_mapping_draft,
)
from hft_cli import main


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
            },
        ]
    )


def test_order_mapping_draft_suggests_reviewable_vendor_upload_mapping():
    report = draft_order_mapping(
        broker_orders(),
        ["symbol", "transaction_type", "quantity", "limit_price", "product", "validity"],
        config=OrderMappingDraftConfig(
            adapter="arrow_money",
            default_values={"product": "MIS"},
        ),
    )

    rows = report.mapping.set_index("target_column")
    assert report.ready
    assert rows.loc["symbol", "source_column"] == "instrument_id"
    assert rows.loc["transaction_type", "transform"] == "side_text"
    assert rows.loc["quantity", "transform"] == "int"
    assert rows.loc["limit_price", "transform"] == "float"
    assert rows.loc["product", "default_value"] == "MIS"
    assert rows.loc["validity", "source_column"] == "time_in_force"
    assert int(report.summary.loc[0, "defaulted_columns"]) == 1
    assert int(report.summary.loc[0, "failed_check_count"]) == 0
    assert report.summary.loc[0, "failed_check_names"] == ""
    assert report.summary.loc[0, "primary_blocker_check"] == ""
    assert int(report.summary.loc[0, "action_queue_count"]) == 0
    assert report.summary.loc[0, "next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty

    mapped = map_broker_orders(
        broker_orders(),
        report.mapping,
        config=MappedOrderExportConfig(adapter="arrow_money", output_filename="arrow_orders.csv"),
    )
    assert mapped.ready
    assert mapped.orders["transaction_type"].tolist() == ["BUY", "SELL"]
    assert mapped.orders["product"].tolist() == ["MIS", "MIS"]


def test_order_mapping_draft_fails_closed_for_unmapped_required_vendor_columns():
    report = draft_order_mapping(
        broker_orders(),
        ["symbol", "exchange_token"],
        config=OrderMappingDraftConfig(adapter="irage"),
    )

    rows = report.mapping.set_index("target_column")
    assert not report.ready
    assert rows.loc["exchange_token", "status"] == "unmapped_required"
    assert int(report.summary.loc[0, "unmapped_required_columns"]) == 1
    summary = report.summary.iloc[0]
    assert int(summary["failed_check_count"]) == 1
    assert summary["failed_check_names"] == "unmapped_required:exchange_token"
    assert summary["first_failed_reason"] == "required vendor column is not mapped to a source or default"
    assert summary["primary_blocker_check"] == "unmapped_required:exchange_token"
    assert summary["primary_blocker_value"] == "exchange_token"
    assert summary["primary_blocker_operator"] == "mapped"
    assert summary["primary_blocker_threshold"] == "source_or_default"
    assert summary["primary_blocker_reason"] == "required vendor column is not mapped to a source or default"
    assert int(summary["action_queue_count"]) == 1
    assert int(summary["blocked_action_count"]) == 1
    assert summary["next_gate"] == "draft-order-mapping"
    assert summary["next_gate_help_command"] == "python -m hft_cli draft-order-mapping --help"
    assert summary["primary_action_status"] == "blocked"
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["target_column"] == "exchange_token"
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "queue_status"] == "blocked"
    assert report.action_queue.loc[0, "check"] == "unmapped_required:exchange_token"
    assert report.action_queue.loc[0, "target_column"] == "exchange_token"
    assert report.action_queue.loc[0, "actual"] == "source_missing_default_missing"


def test_write_order_mapping_draft_outputs_files_and_manifest(tmp_path):
    export_dir = tmp_path / "export"
    sample = tmp_path / "arrow_order_sample.csv"
    out_dir = tmp_path / "mapping_draft"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    pd.DataFrame(columns=["symbol", "transaction_type", "quantity", "product"]).to_csv(sample, index=False)

    report = write_order_mapping_draft(
        export_dir,
        sample,
        output_dir=out_dir,
        config=OrderMappingDraftConfig(adapter="arrow_money", default_values={"product": "MIS"}),
    )

    assert report.ready
    assert (out_dir / "order_mapping_draft.csv").exists()
    assert (out_dir / "order_mapping_draft_checks.csv").exists()
    assert (out_dir / "order_mapping_draft_action_queue.csv").exists()
    assert (out_dir / "order_mapping_draft_config.json").exists()
    assert (out_dir / "order_mapping_draft_runbook.md").exists()
    assert (out_dir / "order_mapping_draft_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "order_mapping_draft_action_queue.csv")
    config = json.loads((out_dir / "order_mapping_draft_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "order_mapping_draft_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert action_queue.empty
    assert config["ready"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Order Mapping Draft Runbook" in runbook
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "order_mapping_draft_action_queue.csv" in artifact_paths
    assert "order_mapping_draft_config.json" in artifact_paths
    assert "order_mapping_draft_runbook.md" in artifact_paths


def test_cli_draft_order_mapping_returns_failure_for_unmapped_required_column(tmp_path):
    export_dir = tmp_path / "export"
    sample = tmp_path / "irage_order_sample.csv"
    out_dir = tmp_path / "mapping_draft"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    pd.DataFrame(columns=["symbol", "transaction_type", "exchange_token"]).to_csv(sample, index=False)

    code = main(
        [
            "draft-order-mapping",
            "--export",
            str(export_dir),
            "--sample",
            str(sample),
            "--out",
            str(out_dir),
            "--adapter",
            "irage",
            "--fail-on-unmapped",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "order_mapping_draft_summary.csv")
    mapping = pd.read_csv(out_dir / "order_mapping_draft.csv")
    action_queue = pd.read_csv(out_dir / "order_mapping_draft_action_queue.csv")
    config = json.loads((out_dir / "order_mapping_draft_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "order_mapping_draft_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert int(summary.loc[0, "unmapped_required_columns"]) == 1
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert summary.loc[0, "failed_check_names"] == "unmapped_required:exchange_token"
    assert summary.loc[0, "primary_blocker_check"] == "unmapped_required:exchange_token"
    assert summary.loc[0, "primary_blocker_reason"] == "required vendor column is not mapped to a source or default"
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert action_queue.loc[0, "check"] == "unmapped_required:exchange_token"
    assert action_queue.loc[0, "next_gate"] == "draft-order-mapping"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli draft-order-mapping --help"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["target_column"] == "exchange_token"
    assert "unmapped_required:exchange_token" in runbook
    assert "unmapped_required" in set(mapping["status"])


def test_cli_draft_order_mapping_can_fail_on_actions(tmp_path):
    export_dir = tmp_path / "export"
    sample = tmp_path / "irage_order_sample.csv"
    out_dir = tmp_path / "mapping_draft"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    pd.DataFrame(columns=["symbol", "exchange_token"]).to_csv(sample, index=False)

    code = main(
        [
            "draft-order-mapping",
            "--export",
            str(export_dir),
            "--sample",
            str(sample),
            "--out",
            str(out_dir),
            "--adapter",
            "irage",
            "--fail-on-actions",
        ]
    )

    assert code == 2
