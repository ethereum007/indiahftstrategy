import json

import pandas as pd

from adapters.mapped_order_export import (
    MappedOrderExportConfig,
    map_broker_orders,
    write_mapped_order_export,
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


def vendor_mapping():
    return pd.DataFrame(
        [
            {"target_column": "symbol", "source_column": "instrument_id", "required": True, "transform": "string"},
            {"target_column": "transaction_type", "source_column": "side", "required": True, "transform": "side_text"},
            {"target_column": "quantity", "source_column": "qty", "required": True, "transform": "int"},
            {"target_column": "limit_price", "source_column": "price", "required": True, "transform": "float"},
            {"target_column": "product", "default_value": "MIS", "required": True, "transform": "uppercase"},
            {"target_column": "validity", "source_column": "time_in_force", "required": True, "transform": "uppercase"},
        ]
    )


def test_map_broker_orders_applies_mapping_defaults_and_transforms():
    report = map_broker_orders(
        broker_orders(),
        vendor_mapping(),
        config=MappedOrderExportConfig(adapter="arrow_money", output_filename="arrow_orders.csv"),
    )

    assert report.ready
    assert report.orders.columns.tolist() == [
        "symbol",
        "transaction_type",
        "quantity",
        "limit_price",
        "product",
        "validity",
    ]
    assert report.orders["transaction_type"].tolist() == ["BUY", "SELL"]
    assert report.orders["product"].tolist() == ["MIS", "MIS"]
    assert str(report.orders["quantity"].dtype) == "Int64"
    assert report.summary.iloc[0]["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert report.summary.iloc[0]["failed_check_count"] == 0
    assert report.summary.iloc[0]["failed_check_names"] == ""
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.summary.iloc[0]["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_map_broker_orders_fails_closed_for_missing_required_source():
    mapping = vendor_mapping()
    mapping.loc[len(mapping)] = {
        "target_column": "exchange_token",
        "source_column": "vendor_exchange_token",
        "required": True,
        "transform": "string",
    }

    report = map_broker_orders(
        broker_orders(),
        mapping,
        config=MappedOrderExportConfig(adapter="irage"),
    )

    assert not report.ready
    assert int(report.summary.iloc[0]["failed_mappings"]) == 1
    assert report.summary.iloc[0]["failed_check_count"] == 1
    assert report.summary.iloc[0]["failed_check_names"] == "exchange_token"
    assert report.summary.iloc[0]["first_failed_reason"] == "required target has no available source column or default value"
    assert report.summary.iloc[0]["primary_blocker_check"] == "exchange_token"
    assert report.summary.iloc[0]["primary_blocker_value"] == "vendor_exchange_token"
    assert report.summary.iloc[0]["primary_blocker_operator"] == "string"
    assert report.summary.iloc[0]["primary_blocker_threshold"] == "required"
    assert report.summary.iloc[0]["primary_blocker_reason"] == "required target has no available source column or default value"
    assert int(report.summary.iloc[0]["action_queue_count"]) == 1
    assert int(report.summary.iloc[0]["blocked_action_count"]) == 1
    assert report.summary.iloc[0]["next_gate"] == "map-broker-orders"
    assert report.summary.iloc[0]["next_gate_help_command"] == "python -m hft_cli map-broker-orders --help"
    assert report.summary.iloc[0]["primary_action_status"] == "blocked"
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["target_column"] == "exchange_token"
    assert failed["reason"] == "required target has no available source column or default value"
    assert report.action_queue is not None
    assert report.action_queue.loc[0, "check"] == "unmapped_required:exchange_token"
    assert report.action_queue.loc[0, "target_column"] == "exchange_token"
    assert report.action_queue.loc[0, "actual"] == "source_missing_default_missing"


def test_write_mapped_order_export_outputs_vendor_file_and_manifest(tmp_path):
    export_dir = tmp_path / "export"
    mapping_path = tmp_path / "mapping.csv"
    out_dir = tmp_path / "mapped"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    vendor_mapping().to_csv(mapping_path, index=False)

    report = write_mapped_order_export(
        export_dir,
        mapping_path,
        output_dir=out_dir,
        config=MappedOrderExportConfig(adapter="arrow_money", output_filename="vendor_orders.csv"),
    )

    assert report.ready
    assert (out_dir / "vendor_orders.csv").exists()
    assert (out_dir / "mapped_order_checks.csv").exists()
    assert (out_dir / "mapped_order_action_queue.csv").exists()
    assert (out_dir / "mapped_order_config.json").exists()
    assert (out_dir / "mapped_order_runbook.md").exists()
    assert (out_dir / "mapped_order_summary.csv").exists()
    assert (out_dir / "mapped_order_schema.csv").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "mapped_order_action_queue.csv")
    config = json.loads((out_dir / "mapped_order_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "mapped_order_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert action_queue.empty
    assert config["ready"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Mapped Broker Order Export Runbook" in runbook
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "mapped_order_action_queue.csv" in artifact_paths
    assert "mapped_order_config.json" in artifact_paths
    assert "mapped_order_runbook.md" in artifact_paths


def test_cli_map_broker_orders_returns_failure_for_required_mapping_gap(tmp_path):
    export_dir = tmp_path / "export"
    mapping_path = tmp_path / "mapping.csv"
    out_dir = tmp_path / "mapped"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    mapping = vendor_mapping()
    mapping.loc[len(mapping)] = {
        "target_column": "exchange_token",
        "source_column": "vendor_exchange_token",
        "required": True,
        "transform": "string",
    }
    mapping.to_csv(mapping_path, index=False)

    code = main(
        [
            "map-broker-orders",
            "--export",
            str(export_dir),
            "--mapping",
            str(mapping_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "mapped_order_summary.csv")
    action_queue = pd.read_csv(out_dir / "mapped_order_action_queue.csv")
    config = json.loads((out_dir / "mapped_order_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "mapped_order_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert int(summary.loc[0, "failed_mappings"]) == 1
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert summary.loc[0, "failed_check_names"] == "exchange_token"
    assert summary.loc[0, "primary_blocker_check"] == "exchange_token"
    assert summary.loc[0, "primary_blocker_reason"] == "required target has no available source column or default value"
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert action_queue.loc[0, "check"] == "unmapped_required:exchange_token"
    assert action_queue.loc[0, "next_gate"] == "map-broker-orders"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli map-broker-orders --help"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["target_column"] == "exchange_token"
    assert "unmapped_required:exchange_token" in runbook
    assert (out_dir / "mapped_broker_orders.csv").exists()


def test_cli_map_broker_orders_can_fail_on_actions(tmp_path):
    export_dir = tmp_path / "export"
    mapping_path = tmp_path / "mapping.csv"
    out_dir = tmp_path / "mapped"
    export_dir.mkdir()
    broker_orders().to_csv(export_dir / "broker_orders.csv", index=False)
    mapping = vendor_mapping()
    mapping.loc[len(mapping)] = {
        "target_column": "exchange_token",
        "source_column": "vendor_exchange_token",
        "required": True,
        "transform": "string",
    }
    mapping.to_csv(mapping_path, index=False)

    code = main(
        [
            "map-broker-orders",
            "--export",
            str(export_dir),
            "--mapping",
            str(mapping_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--fail-on-actions",
        ]
    )

    assert code == 2
