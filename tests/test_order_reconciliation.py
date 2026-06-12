import pandas as pd

from adapters.order_reconciliation import (
    ReconciliationThresholds,
    evaluate_order_reconciliation,
    write_order_reconciliation,
)
from hft_cli import main


def broker_orders():
    return pd.DataFrame(
        [
            {
                "broker_order_id": "A-1",
                "client_order_id": "STG-1",
                "instrument_id": "CALL_1000_0",
                "side": 1,
                "qty": 75,
                "price": 10.0,
                "ts_signal_ns": 100,
            },
            {
                "broker_order_id": "A-2",
                "client_order_id": "STG-2",
                "instrument_id": "PUT_1000_0",
                "side": -1,
                "qty": 75,
                "price": 11.0,
                "ts_signal_ns": 100,
            },
        ]
    )


def live_fills():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-1",
                "instrument_id": "CALL_1000_0",
                "ts_fill_ns": 150,
                "side": 1,
                "qty": 75,
                "price": 10.05,
            },
            {
                "client_order_id": "STG-2",
                "instrument_id": "PUT_1000_0",
                "ts_fill_ns": 160,
                "side": -1,
                "qty": 75,
                "price": 10.95,
            },
        ]
    )


def write_export(path):
    path.mkdir(parents=True, exist_ok=True)
    broker_orders().to_csv(path / "broker_orders.csv", index=False)


def test_evaluate_order_reconciliation_scores_fill_quality():
    report = evaluate_order_reconciliation(
        broker_orders(),
        live_fills(),
        thresholds=ReconciliationThresholds(
            min_order_fill_rate=1.0,
            max_adverse_slippage=0.05,
        ),
    )

    assert report.passed
    assert report.summary.iloc[0]["filled_orders"] == 2
    assert report.summary.iloc[0]["order_fill_rate"] == 1.0
    assert set(report.orders["fill_status"]) == {"full"}
    assert round(report.summary.iloc[0]["max_adverse_slippage"], 6) == 0.05


def test_write_order_reconciliation_outputs_artifacts_and_manifest(tmp_path):
    export_dir = tmp_path / "export"
    fills_path = tmp_path / "fills.csv"
    out_dir = tmp_path / "reconciliation"
    write_export(export_dir)
    live_fills().to_csv(fills_path, index=False)

    report = write_order_reconciliation(
        export_dir=export_dir,
        fills_path=fills_path,
        output_dir=out_dir,
        thresholds=ReconciliationThresholds(min_order_fill_rate=1.0),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "order_reconciliation.csv").exists()
    assert (out_dir / "unmatched_fills.csv").exists()
    assert (out_dir / "reconciliation_checks.csv").exists()
    assert (out_dir / "reconciliation_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_reconcile_broker_fills_fails_on_unmatched_and_mismatch(tmp_path):
    export_dir = tmp_path / "export"
    fills_path = tmp_path / "fills.csv"
    out_dir = tmp_path / "cli_reconciliation"
    write_export(export_dir)
    bad_fills = pd.concat(
        [
            live_fills().iloc[:1],
            pd.DataFrame(
                [
                    {
                        "client_order_id": "UNKNOWN",
                        "instrument_id": "PUT_1000_0",
                        "ts_fill_ns": 170,
                        "side": -1,
                        "qty": 75,
                        "price": 10.90,
                    },
                    {
                        "client_order_id": "STG-2",
                        "instrument_id": "WRONG",
                        "ts_fill_ns": 180,
                        "side": -1,
                        "qty": 75,
                        "price": 10.90,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    bad_fills.to_csv(fills_path, index=False)

    code = main(
        [
            "reconcile-broker-fills",
            "--export",
            str(export_dir),
            "--fills",
            str(fills_path),
            "--out",
            str(out_dir),
            "--min-order-fill-rate",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "reconciliation_checks.csv").exists()
    assert (out_dir / "unmatched_fills.csv").exists()
