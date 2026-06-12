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
    failed = report.checks.loc[~report.checks["passed"].astype(bool)].iloc[0]
    assert failed["target_column"] == "exchange_token"
    assert failed["reason"] == "required target has no available source column or default value"


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
    assert (out_dir / "mapped_order_summary.csv").exists()
    assert (out_dir / "mapped_order_schema.csv").exists()
    assert (out_dir / "manifest.json").exists()


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
        ]
    )

    summary = pd.read_csv(out_dir / "mapped_order_summary.csv")
    assert code == 2
    assert int(summary.loc[0, "failed_mappings"]) == 1
    assert (out_dir / "mapped_broker_orders.csv").exists()
