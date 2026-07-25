import numpy as np
import pandas as pd

from data.chains import normalize_option_chain
from scanners.run_parity_box import run_scan


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def chain_rows():
    return pd.DataFrame(
        [
            {
                "time": ns_ist("2026-06-10 09:15:00"),
                "expiry_date": "2026-06-30",
                "k": 1000.0,
                "cb": 54.0,
                "ca": 55.0,
                "cbq": 300,
                "caq": 300,
                "pb": 60.0,
                "pa": 61.0,
                "pbq": 300,
                "paq": 300,
            },
            {
                "time": ns_ist("2026-06-10 15:30:01"),
                "expiry_date": "2026-06-30",
                "k": 1010.0,
                "cb": 44.0,
                "ca": 45.0,
                "cbq": 300,
                "caq": 300,
                "pb": 60.0,
                "pa": 61.0,
                "pbq": 300,
                "paq": 300,
            },
        ]
    )


def chain_map():
    return {
        "ts": "time",
        "expiry": "expiry_date",
        "strike": "k",
        "call_bid": "cb",
        "call_ask": "ca",
        "call_bid_qty": "cbq",
        "call_ask_qty": "caq",
        "put_bid": "pb",
        "put_ask": "pa",
        "put_bid_qty": "pbq",
        "put_ask_qty": "paq",
    }


def test_option_chain_normalizer_maps_vendor_columns_and_filters_session():
    normalized = normalize_option_chain(chain_rows(), column_map=chain_map())

    assert len(normalized.data) == 1
    assert normalized.data.iloc[0]["strike"] == 1000.0
    assert normalized.data.iloc[0]["regime"] == "post_stt_hike"
    assert normalized.quarantine.total_rows == 2
    assert normalized.quarantine.dropped_out_of_session_rows == 1


def test_option_chain_normalizer_separates_weekend_and_intraday_quarantine():
    rows = chain_rows()
    weekend = rows.iloc[[0]].copy()
    weekend["time"] = ns_ist("2026-06-13 10:00:00")
    rows = pd.concat([rows, weekend], ignore_index=True)

    normalized = normalize_option_chain(rows, column_map=chain_map())

    assert len(normalized.data) == 1
    assert normalized.quarantine.dropped_non_trading_day_rows == 1
    assert normalized.quarantine.dropped_out_of_session_rows == 1


def test_option_chain_normalizer_quarantines_nonfinite_numeric_values():
    valid = chain_rows().iloc[[0]].copy()
    nonfinite_strike = valid.copy()
    nonfinite_strike["k"] = np.inf
    nonfinite_depth = valid.copy()
    nonfinite_depth["cbq"] = -np.inf
    nonfinite_timestamp = valid.copy()
    nonfinite_timestamp["time"] = np.inf

    normalized = normalize_option_chain(
        pd.concat(
            [valid, nonfinite_strike, nonfinite_depth, nonfinite_timestamp],
            ignore_index=True,
        ),
        column_map=chain_map(),
        filter_session=False,
    )

    assert len(normalized.data) == 1
    assert normalized.quarantine.dropped_nonfinite_rows == 3
    assert normalized.quarantine.dropped_null_rows == 0
    assert normalized.quarantine.dropped_negative_depth_rows == 0


def test_option_chain_normalizer_quarantines_nonintegral_depth_and_timestamp():
    valid = chain_rows().iloc[[0]].copy()
    valid["k"] = 1000.5
    fractional_depth = valid.copy()
    fractional_depth["cbq"] = 300.5
    fractional_timestamp = valid.copy()
    fractional_timestamp["time"] = 1.5

    normalized = normalize_option_chain(
        pd.concat([valid, fractional_depth, fractional_timestamp], ignore_index=True),
        column_map=chain_map(),
        filter_session=False,
        add_regime=False,
    )

    assert len(normalized.data) == 1
    assert normalized.data.loc[0, "strike"] == 1000.5
    assert normalized.quarantine.dropped_nonintegral_rows == 2
    assert normalized.quarantine.dropped_nonfinite_rows == 0
    assert normalized.quarantine.dropped_negative_depth_rows == 0


def test_option_chain_normalizer_quarantines_nonpositive_strikes():
    valid = chain_rows().iloc[[0]].copy()
    zero_strike = valid.copy()
    zero_strike["k"] = 0
    negative_strike = valid.copy()
    negative_strike["k"] = -50

    normalized = normalize_option_chain(
        pd.concat([valid, zero_strike, negative_strike], ignore_index=True),
        column_map=chain_map(),
        filter_session=False,
        add_regime=False,
    )

    assert list(normalized.data["strike"]) == [1000.0]
    assert normalized.quarantine.dropped_nonpositive_strike_rows == 2
    assert normalized.quarantine.dropped_nonpositive_quote_rows == 0


def test_option_chain_normalizer_quarantines_int64_overflow_before_casts():
    valid = chain_rows().iloc[[0]].copy()
    valid["time"] = 1
    depth_overflow = valid.copy()
    depth_overflow["cbq"] = 10**30
    timestamp_overflow = valid.copy()
    timestamp_overflow["time"] = 10_000_000_000

    normalized = normalize_option_chain(
        pd.concat([valid, depth_overflow, timestamp_overflow], ignore_index=True),
        column_map=chain_map(),
        timestamp_unit="s",
        filter_session=False,
        add_regime=False,
    )

    assert len(normalized.data) == 1
    assert normalized.data.loc[0, "ts"] == 1_000_000_000
    assert normalized.quarantine.dropped_integer_overflow_rows == 2
    assert normalized.quarantine.dropped_nonfinite_rows == 0
    assert normalized.quarantine.dropped_nonintegral_rows == 0


def test_option_chain_normalizer_quarantines_every_row_below_the_high_water_mark():
    base = chain_rows().iloc[0].to_dict()
    rows = []
    for offset, timestamp in enumerate([100, 50, 75, 100, 125]):
        rows.append(
            {
                **base,
                "time": timestamp,
                "k": 1000.0 + offset * 10.0,
            }
        )

    normalized = normalize_option_chain(
        pd.DataFrame(rows),
        column_map=chain_map(),
        filter_session=False,
        add_regime=False,
    )

    assert list(normalized.data["ts"]) == [100, 100, 125]
    assert normalized.quarantine.dropped_nonmonotonic_rows == 2


def test_parity_box_runner_writes_outputs(tmp_path):
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 1200,
                "call_ask_qty": 1200,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 1200,
                "put_ask_qty": 1200,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1010.0,
                "call_bid": 45.0,
                "call_ask": 46.0,
                "call_bid_qty": 1200,
                "call_ask_qty": 1200,
                "put_bid": 45.0,
                "put_ask": 46.0,
                "put_bid_qty": 1200,
                "put_ask_qty": 1200,
            },
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 1008.0,
                "ask": 1009.0,
                "bid_qty": 1200,
                "ask_qty": 1200,
            }
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "reports"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    result = run_scan(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        asof_latency_ns=0,
        depth_fraction=1.0,
    )

    assert not result.parity.empty
    assert (out_dir / "parity_opportunities.csv").exists()
    assert (out_dir / "box_opportunities.csv").exists()
    assert (out_dir / "opportunity_report.csv").exists()
    assert "post_stt_hike" in set(result.report["regime"])
