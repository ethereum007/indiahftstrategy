import pandas as pd
import pytest

from research.calibration import calibration_summary, compare_simulated_to_live


def test_compare_simulated_to_live_measures_fill_latency_and_slippage():
    simulated = pd.DataFrame(
        [
            {
                "client_order_id": "a",
                "instrument_id": "OPT",
                "ts_sent_ns": 100,
                "side": 1,
                "qty": 75,
                "price": 100.0,
            },
            {
                "client_order_id": "b",
                "instrument_id": "OPT",
                "ts_sent_ns": 200,
                "side": -1,
                "qty": 75,
                "price": 101.0,
            },
        ]
    )
    live = pd.DataFrame(
        [
            {
                "client_order_id": "a",
                "instrument_id": "OPT",
                "ts_fill_ns": 150,
                "side": 1,
                "qty": 75,
                "price": 100.1,
            }
        ]
    )

    comparison = compare_simulated_to_live(simulated, live)

    filled = comparison.loc[comparison["client_order_id"] == "a"].iloc[0]
    missed = comparison.loc[comparison["client_order_id"] == "b"].iloc[0]
    assert bool(filled["filled_live"])
    assert filled["latency_error_ns"] == 50
    assert filled["price_slippage"] == pytest.approx(0.1)
    assert not bool(missed["filled_live"])
    assert missed["live_qty"] == 0


def test_calibration_summary_groups_by_instrument():
    comparison = pd.DataFrame(
        [
            {
                "client_order_id": "a",
                "instrument_id": "OPT",
                "filled_live": True,
                "live_qty": 75,
                "fill_qty_diff": 0,
                "latency_error_ns": 50,
                "price_slippage": 0.1,
            },
            {
                "client_order_id": "b",
                "instrument_id": "OPT",
                "filled_live": False,
                "live_qty": 0,
                "fill_qty_diff": -75,
                "latency_error_ns": None,
                "price_slippage": None,
            },
        ]
    )

    summary = calibration_summary(comparison)

    assert summary.iloc[0]["orders"] == 2
    assert summary.iloc[0]["live_fill_rate"] == 0.5
    assert summary.iloc[0]["avg_live_qty"] == 37.5
    assert summary.iloc[0]["avg_qty_diff"] == -37.5
