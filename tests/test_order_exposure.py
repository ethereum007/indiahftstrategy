import pandas as pd

from hft_cli import main
from reports.order_exposure import OrderExposureConfig, evaluate_order_exposure, write_order_exposure_report


def balanced_orders():
    return pd.DataFrame(
        [
            {
                "instrument_id": "CALL_1000_0",
                "option_type": "C",
                "strike": 1000.0,
                "side": 1,
                "qty": 75,
                "price": 20.0,
                "forward": 1000.0,
                "implied_vol": 0.2,
            },
            {
                "instrument_id": "PUT_1000_0",
                "option_type": "P",
                "strike": 1000.0,
                "side": -1,
                "qty": 75,
                "price": 20.0,
                "forward": 1000.0,
                "implied_vol": 0.2,
            },
        ]
    )


def test_evaluate_order_exposure_computes_delta_vega_and_concentration():
    report = evaluate_order_exposure(
        balanced_orders(),
        config=OrderExposureConfig(
            tte_years=30 / 365,
            max_abs_net_delta=100.0,
            max_gross_notional=5_000.0,
            max_side_imbalance=0.0,
            max_instrument_concentration=0.5,
        ),
    )

    assert report.passed
    assert report.summary.iloc[0]["orders"] == 2
    assert report.summary.iloc[0]["gross_notional"] == 3000.0
    assert report.summary.iloc[0]["greek_coverage"] == 1.0
    assert set(report.by_instrument["instrument_id"]) == {"CALL_1000_0", "PUT_1000_0"}


def test_write_order_exposure_report_outputs_artifacts_and_manifest(tmp_path):
    orders_path = tmp_path / "orders.csv"
    out_dir = tmp_path / "exposure"
    balanced_orders().to_csv(orders_path, index=False)

    report = write_order_exposure_report(
        orders_path,
        output_dir=out_dir,
        config=OrderExposureConfig(tte_years=30 / 365, max_gross_notional=5_000.0),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "order_exposure.csv").exists()
    assert (out_dir / "order_exposure_by_instrument.csv").exists()
    assert (out_dir / "order_exposure_checks.csv").exists()
    assert (out_dir / "order_exposure_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_review_order_exposure_can_fail_on_skew(tmp_path):
    orders = balanced_orders().iloc[:1].copy()
    orders_path = tmp_path / "orders.csv"
    out_dir = tmp_path / "cli_exposure"
    orders.to_csv(orders_path, index=False)

    code = main(
        [
            "review-order-exposure",
            "--orders",
            str(orders_path),
            "--out",
            str(out_dir),
            "--tte-years",
            str(30 / 365),
            "--max-side-imbalance",
            "0.25",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "order_exposure_checks.csv").exists()
    assert (out_dir / "order_exposure_summary.csv").exists()
