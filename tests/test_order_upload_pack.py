import pandas as pd

from adapters.order_upload_pack import (
    OrderUploadPackConfig,
    build_order_upload_pack,
    write_order_upload_pack,
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
    assert report.summary.iloc[0]["recommendation"] == "dry_run_or_paper_review"


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
    assert (out_dir / "manifest.json").exists()


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
        ]
    )

    summary = pd.read_csv(out_dir / "broker_upload_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert (out_dir / "broker_upload_orders.csv").exists()
