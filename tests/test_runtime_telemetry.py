import json

import pandas as pd

from hft_cli import main
from reports.runtime_telemetry import evaluate_runtime_telemetry, write_runtime_telemetry_snapshot


def scaleup_config(scenario_key="trigger_ticks=2", adapter="arrow_money"):
    return {
        "schema_version": 1,
        "ready": True,
        "target_mode": "shadow",
        "scenario_key": scenario_key,
        "adapter": adapter,
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "stop_loss": 5_000.0,
        },
        "kill_switches": {
            "max_total_failed_component_checks": 0,
            "max_total_unmatched_fills": 0,
            "max_total_mismatched_orders": 0,
            "max_total_overfilled_orders": 0,
            "max_worst_adverse_slippage": 0.05,
        },
    }


def export_summary():
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": "arrow_money",
                "scenario_key": "trigger_ticks=2",
                "orders": 4,
                "total_notional": 40_000.0,
                "failed_checks": 1,
            }
        ]
    )


def reconciliation_summary():
    return pd.DataFrame(
        [
            {
                "passed": False,
                "orders": 4,
                "unmatched_fills": 1,
                "mismatched_orders": 0,
                "overfilled_orders": 0,
                "max_adverse_slippage": 0.03,
            }
        ]
    )


def reconciliation_checks():
    return pd.DataFrame(
        [
            {"check": "unmatched_fills", "passed": False, "reason": "one stray fill"},
            {"check": "mismatched_orders", "passed": True, "reason": ""},
        ]
    )


def pnl_snapshot():
    return pd.DataFrame(
        [
            {"ts_ns": 100, "realized_pnl": -10.0},
            {"ts_ns": 200, "realized_pnl": -125.5},
        ]
    )


def open_orders():
    return pd.DataFrame(
        [
            {"client_order_id": "A", "qty": 75, "filled_qty": 25, "status": "partial"},
            {"client_order_id": "B", "qty": 75, "filled_qty": 75, "status": "filled"},
        ]
    )


def positions():
    return pd.DataFrame(
        [
            {"instrument_id": "NIFTY_C_22000", "net_qty": 75},
            {"instrument_id": "NIFTY_P_22000", "net_qty": -25},
        ]
    )


def test_runtime_telemetry_combines_operational_artifacts():
    report = evaluate_runtime_telemetry(
        scaleup_config(),
        export_summary=export_summary(),
        reconciliation_summary=reconciliation_summary(),
        reconciliation_checks=reconciliation_checks(),
        pnl_snapshot=pnl_snapshot(),
        open_orders=open_orders(),
        positions=positions(),
    )

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["orders_sent"] == 4
    assert row["session_notional"] == 40_000.0
    assert row["realized_pnl"] == -125.5
    assert row["total_failed_component_checks"] == 2
    assert row["unmatched_fills"] == 1
    assert row["worst_adverse_slippage"] == 0.03
    assert row["open_order_count"] == 1
    assert row["gross_position_qty"] == 100.0
    assert report.summary.iloc[0]["recommendation"] == "feed_runtime_guard"


def test_runtime_telemetry_defaults_to_scaleup_config_without_optional_inputs():
    report = evaluate_runtime_telemetry(scaleup_config())

    row = report.telemetry.iloc[0]
    assert report.ready
    assert row["scenario_key"] == "trigger_ticks=2"
    assert row["adapter"] == "arrow_money"
    assert row["orders_sent"] == 0
    assert row["total_failed_component_checks"] == 0


def test_write_runtime_telemetry_snapshot_outputs_artifacts(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    export_dir = tmp_path / "export"
    reconciliation_dir = tmp_path / "reconciliation"
    out_dir = tmp_path / "telemetry"
    pnl_path = tmp_path / "pnl.csv"
    open_orders_path = tmp_path / "open_orders.csv"
    positions_path = tmp_path / "positions.csv"
    scaleup_dir.mkdir()
    export_dir.mkdir()
    reconciliation_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(json.dumps(scaleup_config(), indent=2) + "\n", encoding="utf-8")
    export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)
    reconciliation_summary().to_csv(reconciliation_dir / "reconciliation_summary.csv", index=False)
    reconciliation_checks().to_csv(reconciliation_dir / "reconciliation_checks.csv", index=False)
    pnl_snapshot().to_csv(pnl_path, index=False)
    open_orders().to_csv(open_orders_path, index=False)
    positions().to_csv(positions_path, index=False)

    report = write_runtime_telemetry_snapshot(
        scaleup_dir=scaleup_dir,
        export_dir=export_dir,
        reconciliation_dir=reconciliation_dir,
        pnl_path=pnl_path,
        open_orders_path=open_orders_path,
        positions_path=positions_path,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "runtime_telemetry.csv").exists()
    assert (out_dir / "runtime_telemetry_sources.csv").exists()
    assert (out_dir / "runtime_telemetry_checks.csv").exists()
    assert (out_dir / "runtime_telemetry_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_runtime_telemetry_can_fail_on_missing_identity(tmp_path):
    scaleup_dir = tmp_path / "scaleup"
    out_dir = tmp_path / "telemetry"
    scaleup_dir.mkdir()
    (scaleup_dir / "scaleup_config.json").write_text(
        json.dumps(scaleup_config(scenario_key="", adapter=""), indent=2) + "\n",
        encoding="utf-8",
    )

    code = main(
        [
            "build-runtime-telemetry",
            "--scaleup",
            str(scaleup_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "runtime_telemetry_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
