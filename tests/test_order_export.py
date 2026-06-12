import json

import pandas as pd

from adapters.order_export import OrderExportConfig, evaluate_order_export, write_order_export
from hft_cli import main


def launch_orders():
    return pd.DataFrame(
        [
            {
                "launch_order_id": "LCH-000001-STG-1",
                "launch_mode": "shadow",
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "client_order_id": "STG-1",
                "instrument_id": "CALL_1000_0",
                "side": 1,
                "side_text": "BUY",
                "qty": 75,
                "price": 10.0,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "ts_signal_ns": 100,
            },
            {
                "launch_order_id": "LCH-000002-STG-2",
                "launch_mode": "shadow",
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "client_order_id": "STG-2",
                "instrument_id": "PUT_1000_0",
                "side": -1,
                "side_text": "SELL",
                "qty": 75,
                "price": 11.0,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "ts_signal_ns": 100,
            },
        ]
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
                "rejected_orders": 0,
                "acceptance_rate": 1.0,
                "total_notional": 1575.0,
                "failed_checks": 0 if ready else 1,
                "recommendation": "paper_or_shadow_launch" if ready else "do_not_launch",
            }
        ]
    )


def launch_config(ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "mode": "shadow",
        "adapter": "arrow_money",
        "scenario_key": "trigger_ticks=2",
        "order_batch": {"accepted_orders": 2, "rejected_orders": 0},
    }


def write_launch_dir(path, *, ready=True, orders=None):
    path.mkdir(parents=True, exist_ok=True)
    (launch_orders() if orders is None else orders).to_csv(path / "launch_orders.csv", index=False)
    launch_summary(ready).to_csv(path / "launch_summary.csv", index=False)
    (path / "launch_config.json").write_text(json.dumps(launch_config(ready), indent=2) + "\n", encoding="utf-8")


def test_evaluate_order_export_labels_placeholder_adapter_schema():
    report = evaluate_order_export(
        launch_orders(),
        launch_summary(True),
        launch_config(True),
        config=OrderExportConfig(adapter="arrow_money", route_tag="shadow_nse"),
    )

    assert report.ready
    assert report.summary.iloc[0]["adapter"] == "arrow_money"
    assert report.summary.iloc[0]["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert set(report.orders["route_tag"]) == {"shadow_nse"}
    assert report.schema["column"].tolist() == list(report.orders.columns)


def test_write_order_export_outputs_broker_files_and_manifest(tmp_path):
    launch_dir = tmp_path / "launch"
    out_dir = tmp_path / "export"
    write_launch_dir(launch_dir)

    report = write_order_export(
        launch_dir,
        output_dir=out_dir,
        config=OrderExportConfig(adapter="irage", max_orders=5),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "broker_orders.csv").exists()
    assert (out_dir / "broker_order_checks.csv").exists()
    assert (out_dir / "broker_order_summary.csv").exists()
    assert (out_dir / "broker_order_schema.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_export_launch_orders_fails_closed_for_unready_launch(tmp_path):
    launch_dir = tmp_path / "launch"
    out_dir = tmp_path / "cli_export"
    write_launch_dir(launch_dir, ready=False)

    code = main(
        [
            "export-launch-orders",
            "--launch",
            str(launch_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "broker_order_checks.csv").exists()
    assert (out_dir / "broker_orders.csv").exists()
