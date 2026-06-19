import json

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
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.summary.iloc[0]["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty


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
    assert (out_dir / "reconciliation_action_queue.csv").exists()
    assert (out_dir / "reconciliation_config.json").exists()
    assert (out_dir / "reconciliation_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "reconciliation_action_queue.csv")
    config = json.loads((out_dir / "reconciliation_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "reconciliation_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert queue.empty
    assert config["passed"] is True
    assert config["metrics"]["order_fill_rate"] == 1.0
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Broker Fill Reconciliation Runbook" in runbook
    assert "No reconciliation actions." in runbook
    assert "reconciliation_action_queue.csv" in artifact_paths
    assert "reconciliation_config.json" in artifact_paths
    assert "reconciliation_runbook.md" in artifact_paths


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
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "reconciliation_summary.csv")
    queue = pd.read_csv(out_dir / "reconciliation_action_queue.csv")
    config = json.loads((out_dir / "reconciliation_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "reconciliation_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert (out_dir / "reconciliation_checks.csv").exists()
    assert (out_dir / "unmatched_fills.csv").exists()
    assert int(summary.loc[0, "failed_check_count"]) == 2
    assert summary.loc[0, "failed_check_names"] == "mismatched_orders;unmatched_fills"
    assert summary.loc[0, "primary_blocker_check"] == "mismatched_orders"
    assert int(summary.loc[0, "action_queue_count"]) == 2
    assert int(summary.loc[0, "blocked_action_count"]) == 2
    assert summary.loc[0, "next_gate"] == "reconcile-broker-fills"
    assert set(queue["check"]) == {"mismatched_orders", "unmatched_fills"}
    assert queue.loc[0, "component"] == "execution_match"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli reconcile-broker-fills --help"
    assert config["primary_action"]["check"] == "mismatched_orders"
    assert "mismatched_orders" in runbook


def test_cli_reconcile_broker_fills_can_fail_on_actions(tmp_path):
    export_dir = tmp_path / "export"
    fills_path = tmp_path / "fills.csv"
    out_dir = tmp_path / "cli_reconciliation"
    write_export(export_dir)
    bad_fills = live_fills().iloc[:1].copy()
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
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "reconciliation_summary.csv")
    queue = pd.read_csv(out_dir / "reconciliation_action_queue.csv")
    assert code == 2
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert queue.loc[0, "check"] == "order_fill_rate"
    assert queue.loc[0, "component"] == "fill_rate"
