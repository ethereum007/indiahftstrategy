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


def test_order_exposure_infers_nse_and_occ_option_metadata():
    orders = pd.DataFrame(
        [
            {
                "instrument_id": "NIFTY24JUN22500CE",
                "side": 1,
                "qty": 75,
                "price": 100.0,
                "forward": 22550.0,
                "implied_vol": 0.2,
            },
            {
                "instrument_id": "SPY250620P00500000",
                "side": -1,
                "qty": 100,
                "price": 5.0,
                "forward": 499.0,
                "implied_vol": 0.25,
            },
        ]
    )

    report = evaluate_order_exposure(orders, config=OrderExposureConfig(require_greeks=True))

    enriched = report.orders.set_index("instrument_id")
    assert report.passed
    assert enriched.loc["NIFTY24JUN22500CE", "option_type"] == "C"
    assert enriched.loc["NIFTY24JUN22500CE", "strike"] == 22500.0
    assert enriched.loc["NIFTY24JUN22500CE", "underlying"] == "NIFTY"
    assert enriched.loc["NIFTY24JUN22500CE", "symbol_format"] == "nse_compact_option"
    assert enriched.loc["SPY250620P00500000", "option_type"] == "P"
    assert enriched.loc["SPY250620P00500000", "strike"] == 500.0
    assert enriched.loc["SPY250620P00500000", "expiry"] == "2025-06-20"
    assert report.summary.iloc[0]["greek_coverage"] == 1.0


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
