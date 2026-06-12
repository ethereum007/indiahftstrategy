import pandas as pd

from research.markouts import add_pickoff_flag, compute_markouts, markout_summary


def test_compute_markouts_uses_future_mid_and_fill_side():
    fills = pd.DataFrame(
        [
            {"ts_ns": 100, "side": 1, "qty": 10, "price": 100.0, "bucket": "atm"},
            {"ts_ns": 100, "side": -1, "qty": 5, "price": 100.0, "bucket": "atm"},
        ]
    )
    book = pd.DataFrame(
        [
            {"ts": 100, "bid": 99.9, "ask": 100.1},
            {"ts": 200, "bid": 100.9, "ask": 101.1},
            {"ts": 300, "bid": 98.9, "ask": 99.1},
        ]
    )

    markouts = compute_markouts(fills, book, horizons_ns=[100, 200])

    first_fill = markouts.loc[markouts["fill_id"] == 0]
    second_fill = markouts.loc[markouts["fill_id"] == 1]
    assert list(first_fill["markout"]) == [10.0, -10.0]
    assert list(second_fill["markout"]) == [-5.0, 5.0]


def test_markout_summary_and_pickoff_flag():
    fills = pd.DataFrame(
        [
            {"ts_ns": 100, "side": 1, "qty": 10, "price": 100.0, "bucket": "atm"},
            {"ts_ns": 300, "side": 1, "qty": 10, "price": 100.0, "bucket": "wing"},
        ]
    )
    book = pd.DataFrame(
        [
            {"ts": 200, "bid": 100.9, "ask": 101.1},
            {"ts": 400, "bid": 99.9, "ask": 100.1},
        ]
    )
    marked = compute_markouts(fills, book, horizons_ns=[100])
    summary = markout_summary(marked, bucket_cols=["bucket"])

    assert set(summary["bucket"]) == {"atm", "wing"}
    assert summary.loc[summary["bucket"] == "atm", "win_rate"].iloc[0] == 1.0

    flagged = add_pickoff_flag(
        fills,
        pd.DataFrame([{"ts": 95}, {"ts": 250}]),
        window_ns=10,
    )

    assert list(flagged["pickoff"]) == [True, False]
