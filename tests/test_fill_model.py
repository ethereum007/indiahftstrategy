import json

import pandas as pd

from hft_cli import main
from reports.fill_model import (
    FillModelCalibrationThresholds,
    evaluate_fill_model_calibration,
    write_fill_model_calibration,
)


def reconciliation_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "A",
                "instrument_id": "NIFTY_C_22000",
                "qty": 100,
                "live_qty": 100,
                "filled_live": True,
                "fill_status": "full",
                "latency_ns": 1_000,
                "adverse_slippage": 0.02,
                "mismatch": False,
            },
            {
                "client_order_id": "B",
                "instrument_id": "NIFTY_C_22000",
                "qty": 100,
                "live_qty": 50,
                "filled_live": True,
                "fill_status": "partial",
                "latency_ns": 3_000,
                "adverse_slippage": 0.08,
                "mismatch": False,
            },
            {
                "client_order_id": "C",
                "instrument_id": "NIFTY_P_22000",
                "qty": 100,
                "live_qty": 0,
                "filled_live": False,
                "fill_status": "unfilled",
                "latency_ns": None,
                "adverse_slippage": None,
                "mismatch": False,
            },
        ]
    )


def reconciliation_summary(unmatched_fills=0):
    return pd.DataFrame(
        [
            {
                "orders": 3,
                "filled_orders": 2,
                "unmatched_fills": unmatched_fills,
                "order_fill_rate": 2 / 3,
                "max_adverse_slippage": 0.08,
            }
        ]
    )


def write_reconciliation(path, *, unmatched_fills=0, orders=None):
    path.mkdir(parents=True, exist_ok=True)
    (reconciliation_orders() if orders is None else orders).to_csv(path / "order_reconciliation.csv", index=False)
    reconciliation_summary(unmatched_fills).to_csv(path / "reconciliation_summary.csv", index=False)


def test_fill_model_calibration_recommends_conservative_parameters():
    report = evaluate_fill_model_calibration(
        reconciliation_orders(),
        reconciliation_summary(),
        thresholds=FillModelCalibrationThresholds(
            tick_size=0.05,
            min_orders=3,
            min_live_fill_rate=0.5,
            max_adverse_slippage_ticks=2.0,
            base_edge_ticks=1.0,
        ),
    )

    assert report.ready
    overall = report.recommendations.loc[report.recommendations["instrument_id"] == "ALL"].iloc[0]
    assert overall["recommended_queue_conservatism"] == 4.0
    assert overall["recommended_slippage_ticks"] == 2.0
    assert overall["recommended_min_edge_ticks"] == 3.0
    assert report.summary.iloc[0]["recommendation"] == "use_recommended_fill_model"
    assert report.config["global"]["queue_conservatism"] == 4.0


def test_fill_model_calibration_fails_on_mismatch_and_unmatched_fills():
    orders = reconciliation_orders()
    orders.loc[0, "mismatch"] = True

    report = evaluate_fill_model_calibration(
        orders,
        reconciliation_summary(unmatched_fills=1),
        thresholds=FillModelCalibrationThresholds(max_mismatch_rate=0.0, max_unmatched_fills=0),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"mismatch_rate", "unmatched_fills"} <= failed


def test_write_fill_model_calibration_outputs_artifacts(tmp_path):
    reconciliation_dir = tmp_path / "reconciliation"
    out_dir = tmp_path / "fill_model"
    write_reconciliation(reconciliation_dir)

    report = write_fill_model_calibration(
        reconciliation_dir=reconciliation_dir,
        output_dir=out_dir,
        thresholds=FillModelCalibrationThresholds(min_orders=3),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "fill_model_metrics.csv").exists()
    assert (out_dir / "fill_model_recommendations.csv").exists()
    assert (out_dir / "fill_model_checks.csv").exists()
    assert (out_dir / "fill_model_summary.csv").exists()
    assert (out_dir / "fill_model_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    config = json.loads((out_dir / "fill_model_config.json").read_text(encoding="utf-8"))
    assert config["global"]["order_latency_us"] > 0


def test_cli_fill_model_calibration_can_fail_on_sample_size(tmp_path):
    reconciliation_dir = tmp_path / "reconciliation"
    out_dir = tmp_path / "fill_model"
    write_reconciliation(reconciliation_dir)

    code = main(
        [
            "calibrate-fill-model",
            "--reconciliation",
            str(reconciliation_dir),
            "--out",
            str(out_dir),
            "--min-orders",
            "5",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "fill_model_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
