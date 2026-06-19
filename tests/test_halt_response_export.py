import json

import pandas as pd

from adapters.halt_response_export import (
    HaltResponseExportConfig,
    export_halt_response_actions,
    write_halt_response_export,
)
from hft_cli import main


def path_tail(value):
    return str(value).replace("\\", "/")


def halt_summary(ready=True, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": "halt",
                "cancel_orders": 1,
                "flatten_orders": 1,
                "scenario_key": "trigger_ticks=2",
                "adapter": adapter,
            }
        ]
    )


def cancel_actions():
    return pd.DataFrame(
        [
            {
                "action_id": "CXL-000000",
                "action": "cancel_order",
                "client_order_id": "STG-1",
                "broker_order_id": "ARW-1",
                "instrument_id": "NIFTY_C_22000",
                "side": 1,
                "side_text": "BUY",
                "open_qty": 50,
                "reason": "guard_halt_open_order",
            }
        ]
    )


def flatten_actions():
    return pd.DataFrame(
        [
            {
                "action_id": "FLT-000000",
                "action": "flatten_position",
                "instrument_id": "NIFTY_C_22000",
                "side": -1,
                "side_text": "SELL",
                "qty": 75,
                "price": 11.2,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "reason": "flatten_residual_position",
            }
        ]
    )


def cancel_mapping():
    return pd.DataFrame(
        [
            {"target_column": "orderRef", "source_column": "broker_order_id", "required": True, "transform": "string"},
            {"target_column": "instruction", "default_value": "cancel", "required": True, "transform": "uppercase"},
        ]
    )


def flatten_mapping():
    return pd.DataFrame(
        [
            {"target_column": "symbol", "source_column": "instrument_id", "required": True},
            {"target_column": "side", "source_column": "side", "required": True, "transform": "side_text"},
            {"target_column": "quantity", "source_column": "qty", "required": True, "transform": "int"},
            {"target_column": "limitPrice", "source_column": "price", "required": True, "transform": "float"},
        ]
    )


def write_halt_dir(path, *, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    halt_summary(ready).to_csv(path / "halt_response_summary.csv", index=False)
    cancel_actions().to_csv(path / "halt_cancel_orders.csv", index=False)
    flatten_actions().to_csv(path / "halt_flatten_orders.csv", index=False)


def test_export_halt_response_maps_cancel_and_flatten_actions():
    report = export_halt_response_actions(
        halt_summary(),
        cancel_actions(),
        flatten_actions(),
        cancel_mapping=cancel_mapping(),
        flatten_mapping=flatten_mapping(),
        config=HaltResponseExportConfig(adapter="arrow_money"),
    )

    assert report.ready
    assert report.cancel_orders.iloc[0].to_dict() == {"orderRef": "ARW-1", "instruction": "CANCEL"}
    assert report.flatten_orders.iloc[0]["side"] == "SELL"
    assert report.flatten_orders.iloc[0]["quantity"] == 75
    assert report.summary.iloc[0]["failed_check_count"] == 0
    assert report.summary.iloc[0]["failed_check_names"] == ""
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert int(report.summary.iloc[0]["blocked_action_count"]) == 0
    assert report.summary.iloc[0]["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config is not None
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.summary.iloc[0]["recommendation"] == "send_halt_actions_to_broker"


def test_export_halt_response_passthroughs_without_mappings():
    report = export_halt_response_actions(
        halt_summary(),
        cancel_actions(),
        pd.DataFrame(columns=flatten_actions().columns),
        config=HaltResponseExportConfig(adapter="arrow_money"),
    )

    assert report.ready
    assert list(report.cancel_orders.columns) == list(cancel_actions().columns)
    assert report.flatten_orders.empty
    assert set(report.checks["passed"]) == {True}


def test_write_halt_response_export_outputs_artifacts(tmp_path):
    halt_dir = tmp_path / "halt"
    out_dir = tmp_path / "export"
    cancel_mapping_path = tmp_path / "cancel_mapping.csv"
    flatten_mapping_path = tmp_path / "flatten_mapping.csv"
    write_halt_dir(halt_dir)
    cancel_mapping().to_csv(cancel_mapping_path, index=False)
    flatten_mapping().to_csv(flatten_mapping_path, index=False)

    report = write_halt_response_export(
        halt_response_dir=halt_dir,
        output_dir=out_dir,
        cancel_mapping_path=cancel_mapping_path,
        flatten_mapping_path=flatten_mapping_path,
        config=HaltResponseExportConfig(
            adapter="arrow_money",
            cancel_output_filename="arrow_cancel.csv",
            flatten_output_filename="arrow_flatten.csv",
        ),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "arrow_cancel.csv").exists()
    assert (out_dir / "arrow_flatten.csv").exists()
    assert (out_dir / "halt_response_export_checks.csv").exists()
    assert (out_dir / "halt_response_export_summary.csv").exists()
    assert (out_dir / "halt_response_export_schema.csv").exists()
    assert (out_dir / "halt_response_export_action_queue.csv").exists()
    assert (out_dir / "halt_response_export_config.json").exists()
    assert (out_dir / "halt_response_export_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    saved_summary = pd.read_csv(out_dir / "halt_response_export_summary.csv")
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    saved_config = json.loads((out_dir / "halt_response_export_config.json").read_text(encoding="utf-8"))
    assert saved_config["adapter"] == "arrow_money"
    assert saved_config["action_queue_count"] == 0
    assert saved_config["next_actions"] == []
    assert (out_dir / "halt_response_export_runbook.md").read_text(encoding="utf-8").startswith(
        "# Halt Response Export Runbook"
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "halt_response_summary",
        "halt_cancel_orders",
        "halt_flatten_orders",
        "cancel_mapping",
        "flatten_mapping",
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
    assert path_tail(manifest["inputs"]["cancel_mapping"]["path"]).endswith("/cancel_mapping.csv")
    assert path_tail(manifest["inputs"]["flatten_mapping"]["path"]).endswith("/flatten_mapping.csv")
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert any(path.endswith("halt_response_export_action_queue.csv") for path in artifact_paths)
    assert any(path.endswith("halt_response_export_config.json") for path in artifact_paths)
    assert any(path.endswith("halt_response_export_runbook.md") for path in artifact_paths)


def test_cli_halt_response_export_fails_on_missing_required_mapping(tmp_path):
    halt_dir = tmp_path / "halt"
    out_dir = tmp_path / "export"
    cancel_mapping_path = tmp_path / "bad_cancel_mapping.csv"
    write_halt_dir(halt_dir)
    pd.DataFrame(
        [
            {"target_column": "orderRef", "source_column": "missing_source", "required": True},
        ]
    ).to_csv(cancel_mapping_path, index=False)

    code = main(
        [
            "export-halt-response",
            "--halt-response",
            str(halt_dir),
            "--cancel-mapping",
            str(cancel_mapping_path),
            "--adapter",
            "arrow_money",
            "--out",
            str(out_dir),
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "halt_response_export_summary.csv")
    queue = pd.read_csv(out_dir / "halt_response_export_action_queue.csv")
    saved_config = json.loads((out_dir / "halt_response_export_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "failed_check_count"] == 1
    assert summary.loc[0, "failed_check_names"] == "cancel:broker_cancel_orders.csv:orderRef"
    assert summary.loc[0, "first_failed_reason"] == "required target has no available source column or default value"
    assert summary.loc[0, "primary_blocker_check"] == "cancel:broker_cancel_orders.csv:orderRef"
    assert summary.loc[0, "primary_blocker_operator"] == "identity"
    assert summary.loc[0, "primary_blocker_reason"] == "required target has no available source column or default value"
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert summary.loc[0, "next_gate"] == "export-halt-response"
    assert queue.loc[0, "component"] == "cancel_mapping"
    assert queue.loc[0, "check"] == "cancel:broker_cancel_orders.csv:orderRef"
    assert queue.loc[0, "actual"] == "source_missing_default_missing"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli export-halt-response --help"
    assert saved_config["primary_action"]["check"] == "cancel:broker_cancel_orders.csv:orderRef"
    assert saved_config["blocked_actions"][0]["component"] == "cancel_mapping"
    assert "cancel:broker_cancel_orders.csv:orderRef" in (
        out_dir / "halt_response_export_runbook.md"
    ).read_text(encoding="utf-8")


def test_cli_halt_response_export_can_fail_on_actions(tmp_path):
    halt_dir = tmp_path / "halt"
    out_dir = tmp_path / "export"
    cancel_mapping_path = tmp_path / "bad_cancel_mapping.csv"
    write_halt_dir(halt_dir)
    pd.DataFrame(
        [
            {"target_column": "orderRef", "source_column": "missing_source", "required": True},
        ]
    ).to_csv(cancel_mapping_path, index=False)

    code = main(
        [
            "export-halt-response",
            "--halt-response",
            str(halt_dir),
            "--cancel-mapping",
            str(cancel_mapping_path),
            "--adapter",
            "arrow_money",
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    queue = pd.read_csv(out_dir / "halt_response_export_action_queue.csv")
    assert code == 2
    assert len(queue) == 1
    assert queue.loc[0, "check"] == "cancel:broker_cancel_orders.csv:orderRef"
