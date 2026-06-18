import json

import pandas as pd

from hft_cli import main
from reports.halt_execution import (
    HaltExecutionThresholds,
    evaluate_halt_execution,
    write_halt_execution_report,
)


def path_tail(value):
    return str(value).replace("\\", "/")


def halt_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": "halt",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "cancel_orders": 1,
                "flatten_orders": 1,
            }
        ]
    )


def cancel_actions():
    return pd.DataFrame(
        [
            {
                "action_id": "CXL-000000",
                "client_order_id": "STG-1",
                "broker_order_id": "ARW-1",
                "instrument_id": "NIFTY_C_22000",
                "open_qty": 50,
            }
        ]
    )


def flatten_actions():
    return pd.DataFrame(
        [
            {
                "action_id": "FLT-000000",
                "instrument_id": "NIFTY_C_22000",
                "side": -1,
                "qty": 75,
                "price": 11.2,
            }
        ]
    )


def cancel_acks():
    return pd.DataFrame(
        [
            {
                "broker_order_id": "ARW-1",
                "cancel_status": "cancelled",
                "ack_ts_ns": 1_000,
            }
        ]
    )


def flatten_fills(qty=75):
    return pd.DataFrame(
        [
            {
                "action_id": "FLT-000000",
                "instrument_id": "NIFTY_C_22000",
                "side": "SELL",
                "qty": qty,
                "price": 11.15,
                "status": "filled",
            }
        ]
    )


def positions(net_qty=0):
    return pd.DataFrame([{"instrument_id": "NIFTY_C_22000", "net_qty": net_qty}])


def write_halt_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    halt_summary().to_csv(path / "halt_response_summary.csv", index=False)
    cancel_actions().to_csv(path / "halt_cancel_orders.csv", index=False)
    flatten_actions().to_csv(path / "halt_flatten_orders.csv", index=False)


def test_halt_execution_accepts_cancel_ack_flatten_fill_and_flat_positions():
    report = evaluate_halt_execution(
        halt_summary(),
        cancel_actions(),
        flatten_actions(),
        cancel_acks=cancel_acks(),
        flatten_fills=flatten_fills(),
        positions=positions(),
    )

    assert report.passed
    assert report.cancel_execution.iloc[0]["acked"]
    assert report.flatten_execution.iloc[0]["complete"]
    assert report.summary.iloc[0]["recommendation"] == "halt_completed"


def test_halt_execution_fails_when_cancel_ack_is_missing():
    report = evaluate_halt_execution(
        halt_summary(),
        cancel_actions(),
        flatten_actions(),
        cancel_acks=pd.DataFrame(),
        flatten_fills=flatten_fills(),
        positions=positions(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "cancel_acks_complete" in failed
    summary = report.summary.iloc[0]
    assert summary["failed_check_count"] == 1
    assert summary["failed_check_names"] == "cancel_acks_complete"
    assert summary["first_failed_reason"] == "not all cancel actions have terminal acknowledgements"
    assert summary["primary_blocker_check"] == "cancel_acks_complete"
    assert summary["primary_blocker_operator"] == "=="
    assert summary["primary_blocker_threshold"] == "1"
    assert summary["primary_blocker_reason"] == "not all cancel actions have terminal acknowledgements"


def test_write_halt_execution_report_outputs_artifacts(tmp_path):
    halt_dir = tmp_path / "halt"
    out_dir = tmp_path / "execution"
    cancel_acks_path = tmp_path / "cancel_acks.csv"
    flatten_fills_path = tmp_path / "flatten_fills.csv"
    positions_path = tmp_path / "positions.csv"
    write_halt_dir(halt_dir)
    cancel_acks().to_csv(cancel_acks_path, index=False)
    flatten_fills().to_csv(flatten_fills_path, index=False)
    positions().to_csv(positions_path, index=False)

    report = write_halt_execution_report(
        halt_response_dir=halt_dir,
        cancel_acks_path=cancel_acks_path,
        flatten_fills_path=flatten_fills_path,
        positions_path=positions_path,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "halt_cancel_execution.csv").exists()
    assert (out_dir / "halt_flatten_execution.csv").exists()
    assert (out_dir / "halt_position_execution.csv").exists()
    assert (out_dir / "halt_execution_checks.csv").exists()
    assert (out_dir / "halt_execution_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "halt_response_summary",
        "halt_cancel_orders",
        "halt_flatten_orders",
        "cancel_acks",
        "flatten_fills",
        "positions",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["halt_response_summary"]["path"]).endswith(
        "/halt/halt_response_summary.csv"
    )
    assert path_tail(manifest["inputs"]["halt_cancel_orders"]["path"]).endswith(
        "/halt/halt_cancel_orders.csv"
    )
    assert path_tail(manifest["inputs"]["halt_flatten_orders"]["path"]).endswith(
        "/halt/halt_flatten_orders.csv"
    )
    assert path_tail(manifest["inputs"]["cancel_acks"]["path"]).endswith("/cancel_acks.csv")
    assert path_tail(manifest["inputs"]["flatten_fills"]["path"]).endswith("/flatten_fills.csv")
    assert path_tail(manifest["inputs"]["positions"]["path"]).endswith("/positions.csv")


def test_cli_halt_execution_fails_on_residual_position(tmp_path):
    halt_dir = tmp_path / "halt"
    out_dir = tmp_path / "execution"
    cancel_acks_path = tmp_path / "cancel_acks.csv"
    flatten_fills_path = tmp_path / "flatten_fills.csv"
    positions_path = tmp_path / "positions.csv"
    write_halt_dir(halt_dir)
    cancel_acks().to_csv(cancel_acks_path, index=False)
    flatten_fills().to_csv(flatten_fills_path, index=False)
    positions(25).to_csv(positions_path, index=False)

    code = main(
        [
            "reconcile-halt-execution",
            "--halt-response",
            str(halt_dir),
            "--cancel-acks",
            str(cancel_acks_path),
            "--flatten-fills",
            str(flatten_fills_path),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "halt_execution_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert summary.loc[0, "failed_check_count"] == 1
    assert summary.loc[0, "failed_check_names"] == "final_positions_flat"
    assert summary.loc[0, "primary_blocker_check"] == "final_positions_flat"
    assert summary.loc[0, "primary_blocker_reason"] == "final position snapshot is missing or contains residual positions"
