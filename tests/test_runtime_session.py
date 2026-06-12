import json

import pandas as pd

from hft_cli import main
from reports.runtime_session import write_runtime_session_monitor


def scaleup_config(**kill_switch_overrides):
    kill_switches = {
        "max_total_failed_component_checks": 0,
        "max_total_unmatched_fills": 0,
        "max_total_mismatched_orders": 0,
        "max_total_overfilled_orders": 0,
        "max_worst_adverse_slippage": 0.05,
        "max_open_order_count": 2,
        "max_open_order_qty": 100,
        "max_gross_position_qty": 200,
        "max_abs_net_position_qty": 100,
    }
    kill_switches.update(kill_switch_overrides)
    return {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "scenario_key": "surface_mm:demo",
        "adapter": "arrow_money",
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": kill_switches,
    }


def write_scaleup_dir(path, config=None):
    path.mkdir()
    (path / "scaleup_config.json").write_text(
        json.dumps(config or scaleup_config(), indent=2) + "\n",
        encoding="utf-8",
    )


def open_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-1",
                "broker_order_id": "ARW-1",
                "instrument_id": "NIFTY_C_22000",
                "side": 1,
                "qty": 75,
                "filled_qty": 25,
                "status": "PARTIAL",
            }
        ]
    )


def positions():
    return pd.DataFrame(
        [
            {
                "instrument_id": "NIFTY_C_22000",
                "net_qty": 75,
                "unit_delta": 0.75,
                "unit_vega": 12.0,
                "market_bid": 11.2,
                "market_ask": 11.5,
            },
        ]
    )


def upload_summary():
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": "arrow_money",
                "orders": 4,
                "lifecycle_orders": 3,
                "replace_orders": 2,
                "failed_checks": 0,
            }
        ]
    )


def test_runtime_session_monitor_continues_when_guard_passes(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir)

    report = write_runtime_session_monitor(
        scaleup_dir=scaleup_dir,
        output_dir=out_dir,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )

    assert report.ready
    assert (out_dir / "01_telemetry" / "runtime_telemetry.csv").exists()
    assert (out_dir / "02_guard" / "runtime_guard_summary.csv").exists()
    assert not (out_dir / "03_halt_response").exists()
    assert (out_dir / "runtime_session_steps.csv").exists()
    assert (out_dir / "runtime_session_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert report.summary.loc[0, "guard_action"] == "continue"
    assert report.steps["step"].tolist() == ["telemetry", "runtime_guard"]


def test_cli_runtime_session_monitor_builds_halt_response_on_guard_halt(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_open_order_count=0))
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--open-orders",
            str(open_orders_path),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_session_summary.csv")
    steps = pd.read_csv(out_dir / "runtime_session_steps.csv")
    response = pd.read_csv(out_dir / "03_halt_response" / "halt_response_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "halt_response_created"])
    assert bool(summary.loc[0, "halt_response_ready"])
    assert summary.loc[0, "recommendation"] == "stop_routing_and_execute_halt_response"
    assert steps["step"].tolist() == ["telemetry", "runtime_guard", "halt_response"]
    assert response.loc[0, "recommendation"] == "submit_cancel_and_flatten"


def test_cli_runtime_session_monitor_halts_on_upload_pack_replace_limit(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "session"
    write_scaleup_dir(scaleup_dir, scaleup_config(max_replace_orders=1))
    upload_dir.mkdir()
    upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_session_summary.csv")
    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(telemetry.loc[0, "replace_orders"]) == 2
    assert "replace_orders" in failed


def test_cli_runtime_session_monitor_halts_on_live_greek_limit(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "session"
    positions_path = tmp_path / "positions.csv"
    write_scaleup_dir(
        scaleup_dir,
        scaleup_config(max_gross_notional=500, max_abs_net_delta=40, max_abs_net_vega=500),
    )
    positions().to_csv(positions_path, index=False)

    code = main(
        [
            "monitor-runtime-session",
            "--scaleup",
            str(scaleup_dir),
            "--positions",
            str(positions_path),
            "--out",
            str(out_dir),
            "--skip-halt-response",
            "--fail-on-breach",
        ]
    )

    telemetry = pd.read_csv(out_dir / "01_telemetry" / "runtime_telemetry.csv")
    checks = pd.read_csv(out_dir / "02_guard" / "runtime_guard_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert telemetry.loc[0, "gross_position_notional"] == 851.25
    assert telemetry.loc[0, "abs_net_delta"] == 56.25
    assert telemetry.loc[0, "abs_net_vega"] == 900.0
    assert {"gross_position_notional", "abs_net_delta", "abs_net_vega"} <= failed
