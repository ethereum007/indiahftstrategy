import pandas as pd
import pytest

from reports.spread import pair_round_trips, residual_inventory, spread_capture_summary


def test_pair_round_trips_matches_fifo_opposite_sides_with_costs():
    fills = pd.DataFrame(
        [
            {"ts_ns": 100, "instrument_id": "OPT", "side": 1, "qty": 100, "price": 10.0, "cost": 1.0},
            {"ts_ns": 200, "instrument_id": "OPT", "side": -1, "qty": 40, "price": 10.5, "cost": 0.8},
            {"ts_ns": 300, "instrument_id": "OPT", "side": -1, "qty": 60, "price": 10.6, "cost": 1.2},
        ]
    )

    pairs = pair_round_trips(fills)

    assert list(pairs["qty"]) == [40, 60]
    assert pairs.iloc[0]["gross_spread"] == 20.0
    assert pairs.iloc[0]["costs"] == pytest.approx(1.2)
    assert pairs.iloc[0]["net_spread"] == pytest.approx(18.8)
    assert pairs.iloc[1]["gross_spread"] == pytest.approx(36.0)


def test_spread_summary_and_residual_inventory():
    fills = pd.DataFrame(
        [
            {"ts_ns": 100, "instrument_id": "OPT", "side": 1, "qty": 75, "price": 10.0, "cost": 1.0},
            {"ts_ns": 200, "instrument_id": "OPT", "side": -1, "qty": 75, "price": 10.5, "cost": 1.0},
            {"ts_ns": 300, "instrument_id": "FUT", "side": 1, "qty": 75, "price": 100.0, "cost": 2.0},
        ]
    )

    pairs = pair_round_trips(fills)
    summary = spread_capture_summary(pairs)
    residual = residual_inventory(fills)

    assert summary.iloc[0]["round_trips"] == 1
    assert summary.iloc[0]["gross_spread"] == 37.5
    assert summary.iloc[0]["costs"] == 2.0
    fut = residual.loc[residual["instrument_id"] == "FUT"].iloc[0]
    assert fut["position"] == 75
    assert fut["avg_price"] == 100.0
