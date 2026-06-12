import pandas as pd

from research.surface_markouts import compute_surface_markouts, surface_markout_summary


def test_compute_surface_markouts_uses_future_theo_by_instrument():
    fills = pd.DataFrame(
        [
            {
                "ts_ns": 100,
                "instrument_id": "CALL100",
                "side": 1,
                "qty": 10,
                "price": 5.0,
                "bucket": "atm",
            },
            {
                "ts_ns": 100,
                "instrument_id": "PUT100",
                "side": -1,
                "qty": 5,
                "price": 4.0,
                "bucket": "atm",
            },
        ]
    )
    surface = pd.DataFrame(
        [
            {"ts": 200, "instrument_id": "CALL100", "theo": 6.0},
            {"ts": 200, "instrument_id": "PUT100", "theo": 3.0},
        ]
    )

    markouts = compute_surface_markouts(fills, surface, horizons_ns=[100])

    assert list(markouts["surface_markout"]) == [10.0, 5.0]


def test_surface_markout_summary_groups_buckets():
    markouts = pd.DataFrame(
        [
            {"horizon_ns": 100, "surface_markout": 10.0, "bucket": "atm"},
            {"horizon_ns": 100, "surface_markout": -5.0, "bucket": "atm"},
            {"horizon_ns": 100, "surface_markout": 2.0, "bucket": "wing"},
        ]
    )

    summary = surface_markout_summary(markouts, bucket_cols=["bucket"])

    atm = summary.loc[summary["bucket"] == "atm"].iloc[0]
    assert atm["count"] == 2
    assert atm["win_rate"] == 0.5
    assert atm["surface_markout_mean"] == 2.5
