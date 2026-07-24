import numpy as np
import pandas as pd

from data.loaders import normalize_ticks, tag_regime, trading_session_mask
from data.synthetic import correlated_futures_options


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_normalize_ticks_maps_vendor_columns_and_quarantines_bad_rows():
    raw = pd.DataFrame(
        {
            "exchange_time": [
                ns_ist("2026-06-10 09:15:00"),
                ns_ist("2026-06-10 09:15:01"),
                ns_ist("2026-06-10 09:15:02"),
                ns_ist("2026-06-10 09:14:59"),
                ns_ist("2026-06-10 15:30:01"),
            ],
            "best_bid": [100.00, 0.00, 100.20, 101.00, 102.00],
            "best_ask": [100.05, 100.10, 100.15, 101.05, 102.05],
            "bid_size": [75, 75, 75, 75, 75],
            "ask_size": [150, 150, 150, 150, 150],
        }
    )

    normalized = normalize_ticks(
        raw,
        column_map={
            "ts": "exchange_time",
            "bid": "best_bid",
            "ask": "best_ask",
            "bid_qty": "bid_size",
            "ask_qty": "ask_size",
        },
    )

    assert list(normalized.data["ts"]) == [ns_ist("2026-06-10 09:15:00")]
    assert normalized.data.iloc[0]["last_qty"] == 0
    assert normalized.data.iloc[0]["regime"] == "post_stt_hike"
    assert normalized.quarantine.total_rows == 5
    assert normalized.quarantine.kept_rows == 1
    assert normalized.quarantine.dropped_nonpositive_quote_rows == 1
    assert normalized.quarantine.dropped_crossed_quote_rows == 1
    assert normalized.quarantine.dropped_nonmonotonic_rows == 1
    assert normalized.quarantine.dropped_out_of_session_rows == 1


def test_normalize_ticks_accepts_datetime_strings_and_units():
    raw = pd.DataFrame(
        {
            "ts": ["2026-06-10 09:15:00", "2026-06-10 09:15:01"],
            "bid": [100.00, 100.05],
            "ask": [100.05, 100.10],
            "bid_qty": [75, 75],
            "ask_qty": [75, 75],
        }
    )

    normalized = normalize_ticks(raw, timestamp_unit="datetime", timestamp_tz="Asia/Kolkata")

    assert list(normalized.data["ts"]) == [
        ns_ist("2026-06-10 09:15:00"),
        ns_ist("2026-06-10 09:15:01"),
    ]

    seconds = pd.DataFrame(
        {
            "ts": [1, 1.5, 2],
            "bid": [100.00, 100.025, 100.05],
            "ask": [100.05, 100.075, 100.10],
            "bid_qty": [75, 75, 75],
            "ask_qty": [75, 75, 75],
        }
    )
    normalized_seconds = normalize_ticks(seconds, timestamp_unit="s", filter_session=False)

    assert list(normalized_seconds.data["ts"]) == [
        1_000_000_000,
        1_500_000_000,
        2_000_000_000,
    ]


def test_normalize_ticks_quarantines_nonfinite_numeric_values_before_casts():
    timestamp = ns_ist("2026-06-10 09:15:00")
    rows = [
        {
            "ts": timestamp,
            "bid": 100.0,
            "ask": 100.05,
            "bid_qty": 75,
            "ask_qty": 150,
            "last": 100.05,
            "last_qty": 75,
        }
    ]
    for column, value in (
        ("ts", np.inf),
        ("bid", -np.inf),
        ("bid_qty", np.inf),
        ("last", -np.inf),
        ("last_qty", np.inf),
    ):
        row = rows[0].copy()
        row[column] = value
        rows.append(row)

    normalized = normalize_ticks(pd.DataFrame(rows), filter_session=False)

    assert len(normalized.data) == 1
    assert normalized.quarantine.dropped_nonfinite_rows == 5
    assert normalized.quarantine.dropped_null_rows == 0
    assert normalized.quarantine.dropped_nonpositive_quote_rows == 0


def test_normalize_ticks_quarantines_nonintegral_integer_fields_before_casts():
    valid = {
        "ts": 1.0,
        "bid": 100.0,
        "ask": 100.05,
        "bid_qty": 75.0,
        "ask_qty": 150.0,
        "last": 100.05,
        "last_qty": 75.0,
    }
    rows = [valid]
    for column in ("ts", "bid_qty", "ask_qty", "last_qty"):
        row = valid.copy()
        row[column] += 0.5
        rows.append(row)

    normalized = normalize_ticks(
        pd.DataFrame(rows),
        filter_session=False,
        add_regime=False,
    )

    assert len(normalized.data) == 1
    assert normalized.quarantine.dropped_nonintegral_rows == 4
    assert normalized.quarantine.dropped_nonfinite_rows == 0
    assert normalized.quarantine.dropped_nonpositive_quote_rows == 0


def test_session_mask_and_regime_boundaries():
    timestamps = pd.Series(
        [
            ns_ist("2026-06-10 09:14:59"),
            ns_ist("2026-06-10 09:15:00"),
            ns_ist("2026-06-10 15:30:00"),
            ns_ist("2026-06-10 15:30:01"),
        ]
    )

    assert list(trading_session_mask(timestamps)) == [False, True, True, False]

    regimes = tag_regime(
        pd.Series(
            [
                ns_ist("2024-11-19 10:00:00"),
                ns_ist("2024-11-20 10:00:00"),
                ns_ist("2025-09-01 10:00:00"),
                ns_ist("2026-04-01 10:00:00"),
            ]
        )
    )

    assert list(regimes) == [
        "pre_weekly_consolidation",
        "weekly_consolidated",
        "expiry_swap",
        "post_stt_hike",
    ]


def test_correlated_synthetic_generator_is_deterministic_and_lagged():
    market_a = correlated_futures_options(n_ticks=100, n_options=2, lag_ticks=[0, 5], seed=11)
    market_b = correlated_futures_options(n_ticks=100, n_options=2, lag_ticks=[0, 5], seed=11)

    pd.testing.assert_frame_equal(market_a.futures, market_b.futures)
    pd.testing.assert_frame_equal(market_a.options["OPT00"], market_b.options["OPT00"])
    assert set(market_a.options) == {"OPT00", "OPT01"}
    assert market_a.deltas["OPT00"] < market_a.deltas["OPT01"]

    futures_mid = 0.5 * (market_a.futures["bid"] + market_a.futures["ask"])
    opt_no_lag = 0.5 * (market_a.options["OPT00"]["bid"] + market_a.options["OPT00"]["ask"])
    opt_lagged = 0.5 * (market_a.options["OPT01"]["bid"] + market_a.options["OPT01"]["ask"])
    leader_move = futures_mid.diff().fillna(0).to_numpy()
    no_lag_move = opt_no_lag.diff().fillna(0).to_numpy()
    lagged_move = opt_lagged.diff().fillna(0).to_numpy()

    no_lag_corr = np.corrcoef(leader_move[10:], no_lag_move[10:])[0, 1]
    planted_lag_corr = np.corrcoef(leader_move[10:-5], lagged_move[15:])[0, 1]
    wrong_lag_corr = np.corrcoef(leader_move[10:-5], lagged_move[10:-5])[0, 1]

    assert no_lag_corr > 0.70
    assert planted_lag_corr > wrong_lag_corr
