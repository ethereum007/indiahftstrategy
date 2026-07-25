import pandas as pd
import pytest

from data.diagnostics import chain_diagnostics, tick_diagnostics, write_diagnostics
from hft_cli import main


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_tick_diagnostics_reports_quality_issues_and_spread_stats(tmp_path):
    ticks = pd.DataFrame(
        [
            {"ts": ns_ist("2026-06-10 09:15:00"), "bid": 100.0, "ask": 100.05, "bid_qty": 75, "ask_qty": 150},
            {"ts": ns_ist("2026-06-10 09:15:01"), "bid": 101.0, "ask": 100.95, "bid_qty": 75, "ask_qty": 150},
            {"ts": ns_ist("2026-06-10 15:30:01"), "bid": 102.0, "ask": 102.05, "bid_qty": 0, "ask_qty": 150},
        ]
    )

    result = tick_diagnostics(ticks, tick_size=0.05)
    out = write_diagnostics(result, tmp_path)

    summary = result.summary.iloc[0]
    assert summary["rows"] == 3
    assert summary["crossed_quote_rows"] == 1
    assert summary["nonpositive_depth_rows"] == 1
    assert summary["out_of_session_rows"] == 1
    assert summary["median_spread_ticks"] == pytest.approx(1.0)
    assert bool(summary["price_grid_validation_enabled"])
    assert summary["price_grid_tick_size"] == pytest.approx(0.05)
    assert int(summary["off_tick_price_rows"]) == 0
    assert set(result.issues["issue"]) == {"crossed_quote", "nonpositive_depth", "out_of_session"}
    assert (out.output_dir / "diagnostic_summary.csv").exists()
    assert (out.output_dir / "diagnostic_issues.csv").exists()


def test_tick_diagnostics_reports_invalid_supplied_trade_fields():
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 100.05,
                "last_qty": 75,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:01"),
                "bid": 100.05,
                "ask": 100.10,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 0,
                "last_qty": 0,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:02"),
                "bid": 100.10,
                "ask": 100.15,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 100.10,
                "last_qty": -1,
            },
        ]
    )

    result = tick_diagnostics(ticks)

    assert int(result.summary.loc[0, "invalid_trade_rows"]) == 2
    assert list(result.issues["issue"]) == ["invalid_trade", "invalid_trade"]


def test_tick_and_chain_diagnostics_report_off_tick_prices():
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 100.05,
                "last_qty": 75,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:01"),
                "bid": 100.05,
                "ask": 100.07,
                "bid_qty": 75,
                "ask_qty": 150,
                "last": 100.03,
                "last_qty": 75,
            },
        ]
    )
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-25",
                "strike": 22500.0,
                "call_bid": 100.0,
                "call_ask": 100.07,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.05,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
        ]
    )

    tick_result = tick_diagnostics(ticks, tick_size=0.05)
    chain_result = chain_diagnostics(chain, tick_size=0.05)

    tick_summary = tick_result.summary.iloc[0]
    chain_overall = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]
    chain_expiry = chain_result.summary.loc[
        chain_result.summary["scope"] == "expiry"
    ].iloc[0]
    assert int(tick_summary["off_tick_price_rows"]) == 1
    assert set(tick_result.issues.loc[tick_result.issues["row_index"] == 1, "issue"]) >= {
        "off_tick_price"
    }
    assert bool(chain_overall["price_grid_validation_enabled"])
    assert int(chain_overall["off_tick_price_rows"]) == 1
    assert int(chain_expiry["off_tick_price_rows"]) == 1
    assert "off_tick_price" in set(chain_result.issues["issue"])

    with pytest.raises(ValueError, match="tick_size"):
        tick_diagnostics(ticks, tick_size=0)


def test_tick_and_chain_diagnostics_report_declared_wide_spreads():
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 100.0,
                "ask": 100.10,
                "bid_qty": 75,
                "ask_qty": 150,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:01"),
                "bid": 100.0,
                "ask": 100.25,
                "bid_qty": 75,
                "ask_qty": 150,
            },
        ]
    )
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-25",
                "strike": 22500.0,
                "call_bid": 100.0,
                "call_ask": 100.25,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.05,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
        ]
    )

    tick_result = tick_diagnostics(
        ticks,
        tick_size=0.05,
        max_quote_spread_ticks=2,
    )
    chain_result = chain_diagnostics(
        chain,
        tick_size=0.05,
        max_quote_spread_ticks=2,
    )

    tick_summary = tick_result.summary.iloc[0]
    chain_overall = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]
    chain_expiry = chain_result.summary.loc[
        chain_result.summary["scope"] == "expiry"
    ].iloc[0]
    assert bool(tick_summary["quote_spread_validation_enabled"])
    assert tick_summary["max_quote_spread_ticks"] == pytest.approx(2)
    assert int(tick_summary["wide_spread_rows"]) == 1
    assert list(
        tick_result.issues.loc[
            tick_result.issues["issue"] == "wide_spread",
            "row_index",
        ]
    ) == [1]
    assert bool(chain_overall["quote_spread_validation_enabled"])
    assert chain_overall["max_quote_spread_ticks"] == pytest.approx(2)
    assert int(chain_overall["wide_spread_rows"]) == 1
    assert int(chain_expiry["wide_spread_rows"]) == 1
    assert "wide_spread" in set(chain_result.issues["issue"])

    with pytest.raises(ValueError, match="tick_size"):
        tick_diagnostics(ticks, max_quote_spread_ticks=2)
    with pytest.raises(ValueError, match="max_quote_spread_ticks"):
        chain_diagnostics(
            chain,
            tick_size=0.05,
            max_quote_spread_ticks=-1,
        )


def test_tick_and_chain_diagnostics_report_declared_stale_bbo():
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist(timestamp),
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": bid_qty,
                "ask_qty": 150,
            }
            for timestamp, bid_qty in (
                ("2026-06-10 09:15:00", 75),
                ("2026-06-10 09:15:01", 75),
                ("2026-06-10 09:15:03", 75),
                ("2026-06-10 09:15:04", 150),
                ("2026-06-10 09:15:02", 150),
                ("2026-06-10 09:15:05", 150),
            )
        ]
    )
    chain_rows = []
    for timestamp, strike, call_bid_qty in (
        ("2026-06-10 09:15:00", 22500.0, 75),
        ("2026-06-10 09:15:00", 22600.0, 75),
        ("2026-06-10 09:15:03", 22500.0, 75),
        ("2026-06-10 09:15:01", 22600.0, 75),
        ("2026-06-10 09:15:04", 22500.0, 150),
    ):
        chain_rows.append(
            {
                "ts": ns_ist(timestamp),
                "expiry": "2026-06-25",
                "strike": strike,
                "call_bid": 100.0,
                "call_ask": 100.05,
                "call_bid_qty": call_bid_qty,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.05,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
        )
    chain = pd.DataFrame(chain_rows)

    tick_result = tick_diagnostics(
        ticks,
        max_unchanged_bbo_ns=2_000_000_000,
    )
    chain_result = chain_diagnostics(
        chain,
        max_unchanged_bbo_ns=2_000_000_000,
    )

    tick_summary = tick_result.summary.iloc[0]
    chain_overall = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]
    chain_expiry = chain_result.summary.loc[
        chain_result.summary["scope"] == "expiry"
    ].iloc[0]
    assert bool(tick_summary["bbo_staleness_validation_enabled"])
    assert int(tick_summary["max_unchanged_bbo_ns"]) == 2_000_000_000
    assert int(tick_summary["stale_bbo_rows"]) == 2
    assert int(tick_summary["max_observed_bbo_age_ns"]) == 3_000_000_000
    assert list(
        tick_result.issues.loc[
            tick_result.issues["issue"] == "stale_bbo",
            "row_index",
        ]
    ) == [2, 5]
    assert bool(chain_overall["bbo_staleness_validation_enabled"])
    assert int(chain_overall["stale_bbo_rows"]) == 1
    assert int(chain_overall["max_observed_bbo_age_ns"]) == 3_000_000_000
    assert int(chain_expiry["stale_bbo_rows"]) == 1
    assert int(chain_expiry["max_observed_bbo_age_ns"]) == 3_000_000_000
    assert list(
        chain_result.issues.loc[
            chain_result.issues["issue"] == "stale_bbo",
            "row_index",
        ]
    ) == [2]

    for invalid_limit in (-1, 1.5, True):
        with pytest.raises(ValueError, match="max_unchanged_bbo_ns"):
            tick_diagnostics(
                ticks,
                max_unchanged_bbo_ns=invalid_limit,
            )


def test_tick_and_chain_diagnostics_report_daily_observation_spans():
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist(timestamp),
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 150,
            }
            for timestamp in (
                "2026-06-10 09:15:00",
                "2026-06-10 09:15:04",
                "2026-06-11 09:15:00",
                "2026-06-11 09:15:02",
            )
        ]
    )
    chain_rows = []
    for expiry, strike, timestamp in (
        ("2026-06-25", 22500.0, "2026-06-10 09:15:00"),
        ("2026-06-25", 22500.0, "2026-06-10 09:15:05"),
        ("2026-06-25", 22500.0, "2026-06-11 09:15:00"),
        ("2026-06-25", 22500.0, "2026-06-11 09:15:01"),
        ("2026-07-30", 22600.0, "2026-06-10 09:15:00"),
        ("2026-07-30", 22600.0, "2026-06-10 09:15:03"),
    ):
        chain_rows.append(
            {
                "ts": ns_ist(timestamp),
                "expiry": expiry,
                "strike": strike,
                "call_bid": 100.0,
                "call_ask": 100.05,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.05,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
        )

    tick_summary = tick_diagnostics(ticks).summary.iloc[0]
    chain_summary = chain_diagnostics(pd.DataFrame(chain_rows)).summary
    chain_overall = chain_summary.loc[
        chain_summary["scope"] == "overall"
    ].iloc[0]
    june_expiry = chain_summary.loc[
        (chain_summary["scope"] == "expiry")
        & (chain_summary["expiry"] == "2026-06-25")
    ].iloc[0]
    july_expiry = chain_summary.loc[
        (chain_summary["scope"] == "expiry")
        & (chain_summary["expiry"] == "2026-07-30")
    ].iloc[0]

    assert int(tick_summary["observation_days"]) == 2
    assert tick_summary["observation_dates"] == (
        "2026-06-10;2026-06-11"
    )
    assert int(tick_summary["min_daily_observation_span_ns"]) == 2_000_000_000
    assert int(tick_summary["median_daily_observation_span_ns"]) == 3_000_000_000
    assert int(tick_summary["max_daily_observation_span_ns"]) == 4_000_000_000
    assert int(tick_summary["min_daily_rows"]) == 2
    assert float(tick_summary["median_daily_rows"]) == 2.0
    assert int(tick_summary["max_daily_rows"]) == 2
    assert int(tick_summary["min_daily_gap_observations"]) == 1
    assert int(tick_summary["max_daily_observation_gap_ns"]) == 4_000_000_000
    assert int(chain_overall["observation_days"]) == 2
    assert chain_overall["observation_dates"] == (
        "2026-06-10;2026-06-11"
    )
    assert int(chain_overall["min_daily_observation_span_ns"]) == 1_000_000_000
    assert int(chain_overall["median_daily_observation_span_ns"]) == 3_000_000_000
    assert int(chain_overall["max_daily_observation_span_ns"]) == 5_000_000_000
    assert int(chain_overall["min_daily_snapshots"]) == 2
    assert float(chain_overall["median_daily_snapshots"]) == 2.5
    assert int(chain_overall["max_daily_snapshots"]) == 3
    assert int(chain_overall["min_daily_snapshots_per_expiry"]) == 2
    assert int(chain_overall["min_daily_gap_observations"]) == 1
    assert int(chain_overall["max_daily_observation_gap_ns"]) == 3_000_000_000
    assert int(
        chain_overall["min_daily_gap_observations_per_expiry"]
    ) == 1
    assert int(
        chain_overall["max_daily_snapshot_gap_ns_per_expiry"]
    ) == 5_000_000_000
    assert int(june_expiry["observation_days"]) == 2
    assert june_expiry["observation_dates"] == (
        "2026-06-10;2026-06-11"
    )
    assert int(june_expiry["min_daily_observation_span_ns"]) == 1_000_000_000
    assert int(june_expiry["max_daily_observation_span_ns"]) == 5_000_000_000
    assert int(june_expiry["min_daily_snapshots"]) == 2
    assert int(june_expiry["min_daily_gap_observations"]) == 1
    assert int(june_expiry["max_daily_observation_gap_ns"]) == 5_000_000_000
    assert int(july_expiry["observation_days"]) == 1
    assert july_expiry["observation_dates"] == "2026-06-10"
    assert int(july_expiry["min_daily_observation_span_ns"]) == 3_000_000_000
    assert int(july_expiry["min_daily_snapshots"]) == 2
    assert int(july_expiry["min_daily_gap_observations"]) == 1
    assert int(july_expiry["max_daily_observation_gap_ns"]) == 3_000_000_000


def test_chain_daily_density_counts_snapshots_instead_of_strike_rows():
    rows = []
    for timestamp in (
        "2026-06-10 09:15:00",
        "2026-06-10 09:15:01",
    ):
        for strike in (22500.0, 22550.0, 22600.0):
            rows.append(
                {
                    "ts": ns_ist(timestamp),
                    "expiry": "2026-06-25",
                    "strike": strike,
                    "call_bid": 100.0,
                    "call_ask": 100.05,
                    "call_bid_qty": 75,
                    "call_ask_qty": 75,
                    "put_bid": 90.0,
                    "put_ask": 90.05,
                    "put_bid_qty": 75,
                    "put_ask_qty": 75,
                }
            )

    summary = chain_diagnostics(pd.DataFrame(rows)).summary
    overall = summary.loc[summary["scope"] == "overall"].iloc[0]
    expiry = summary.loc[summary["scope"] == "expiry"].iloc[0]

    assert int(overall["min_daily_rows"]) == 6
    assert int(overall["min_daily_snapshots"]) == 2
    assert int(overall["min_daily_snapshots_per_expiry"]) == 2
    assert int(overall["min_daily_gap_observations"]) == 1
    assert int(overall["max_daily_observation_gap_ns"]) == 1_000_000_000
    assert int(overall["max_daily_snapshot_gap_ns_per_expiry"]) == 1_000_000_000
    assert int(expiry["min_daily_rows"]) == 6
    assert int(expiry["min_daily_snapshots"]) == 2


def test_tick_and_chain_diagnostics_apply_timestamp_high_water():
    timestamps = [
        ns_ist("2026-06-10 09:15:04"),
        ns_ist("2026-06-10 09:15:01"),
        ns_ist("2026-06-10 09:15:02"),
        ns_ist("2026-06-10 09:15:04"),
        ns_ist("2026-06-10 09:15:05"),
    ]
    ticks = pd.DataFrame(
        [
            {
                "ts": timestamp,
                "bid": 100.0 + offset * 0.05,
                "ask": 100.05 + offset * 0.05,
                "bid_qty": 75,
                "ask_qty": 150,
            }
            for offset, timestamp in enumerate(timestamps)
        ]
    )
    chain = pd.DataFrame(
        [
            {
                "ts": timestamp,
                "expiry": "2026-06-25",
                "strike": 22500.0 + offset * 50.0,
                "call_bid": 100.0,
                "call_ask": 100.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
            for offset, timestamp in enumerate(timestamps)
        ]
    )

    tick_result = tick_diagnostics(ticks)
    chain_result = chain_diagnostics(chain)

    chain_overall = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]
    chain_expiry = chain_result.summary.loc[
        chain_result.summary["scope"] == "expiry"
    ].iloc[0]
    assert int(tick_result.summary.loc[0, "nonmonotonic_rows"]) == 2
    assert int(chain_overall["nonmonotonic_rows"]) == 2
    assert int(chain_expiry["nonmonotonic_rows"]) == 2
    assert list(
        tick_result.issues.loc[
            tick_result.issues["issue"] == "nonmonotonic_ts",
            "row_index",
        ]
    ) == [1, 2]
    assert list(
        chain_result.issues.loc[
            chain_result.issues["issue"] == "nonmonotonic_ts",
            "row_index",
        ]
    ) == [1, 2]


def test_tick_and_chain_diagnostics_split_non_trading_day_from_intraday_issues():
    timestamps = [
        ns_ist("2026-06-12 08:00:00"),
        ns_ist("2026-06-13 10:00:00"),
    ]
    ticks = pd.DataFrame(
        [
            {
                "ts": timestamp,
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 150,
            }
            for timestamp in timestamps
        ]
    )
    chain = pd.DataFrame(
        [
            {
                "ts": timestamp,
                "expiry": "2026-06-25",
                "strike": 22500.0,
                "call_bid": 100.0,
                "call_ask": 100.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
            for timestamp in timestamps
        ]
    )

    tick_result = tick_diagnostics(ticks)
    chain_result = chain_diagnostics(chain)

    tick_summary = tick_result.summary.iloc[0]
    chain_summary = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]
    assert int(tick_summary["non_trading_day_rows"]) == 1
    assert int(tick_summary["out_of_session_rows"]) == 1
    assert set(tick_result.issues["issue"]) == {
        "non_trading_day",
        "out_of_session",
    }
    assert int(chain_summary["non_trading_day_rows"]) == 1
    assert int(chain_summary["out_of_session_rows"]) == 1
    assert set(chain_result.issues["issue"]) == {
        "non_trading_day",
        "out_of_session",
    }


def test_chain_diagnostics_reports_expiry_coverage_and_issues():
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 40.0,
                "put_ask": 40.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1010.0,
                "call_bid": 55.0,
                "call_ask": 54.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 0.0,
                "put_ask": 41.0,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            },
        ]
    )

    result = chain_diagnostics(chain, tick_size=0.05)

    overall = result.summary.loc[result.summary["scope"] == "overall"].iloc[0]
    expiry = result.summary.loc[result.summary["scope"] == "expiry"].iloc[0]
    assert overall["rows"] == 2
    assert overall["crossed_quote_rows"] == 1
    assert overall["nonpositive_quote_rows"] == 1
    assert bool(overall["price_grid_validation_enabled"])
    assert int(overall["off_tick_price_rows"]) == 0
    assert expiry["strikes"] == 2
    assert expiry["min_strike"] == 1000.0
    assert expiry["max_strike"] == 1010.0


def test_chain_diagnostics_reports_nonpositive_strikes():
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-25",
                "strike": strike,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 40.0,
                "put_ask": 40.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
            for strike in (22500.0, 0.0, -50.0)
        ]
    )

    result = chain_diagnostics(chain)

    overall = result.summary.loc[result.summary["scope"] == "overall"].iloc[0]
    expiry = result.summary.loc[result.summary["scope"] == "expiry"].iloc[0]
    assert int(overall["nonpositive_strike_rows"]) == 2
    assert int(expiry["nonpositive_strike_rows"]) == 2
    assert list(
        result.issues.loc[
            result.issues["issue"] == "nonpositive_strike",
            "row_index",
        ]
    ) == [1, 2]


def test_chain_diagnostics_reports_declared_strike_grid_violations():
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-25",
                "strike": strike,
                "call_bid": 50.0,
                "call_ask": 50.5,
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 40.0,
                "put_ask": 40.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
            for strike in (22500.0, 22525.0, 22550.0)
        ]
    )

    result = chain_diagnostics(chain, strike_step=50.0)

    overall = result.summary.loc[result.summary["scope"] == "overall"].iloc[0]
    expiry = result.summary.loc[result.summary["scope"] == "expiry"].iloc[0]
    assert bool(overall["strike_grid_validation_enabled"])
    assert overall["strike_grid_step"] == pytest.approx(50.0)
    assert int(overall["off_grid_strike_rows"]) == 1
    assert int(expiry["off_grid_strike_rows"]) == 1
    assert list(
        result.issues.loc[
            result.issues["issue"] == "off_grid_strike",
            "row_index",
        ]
    ) == [1]

    with pytest.raises(ValueError, match="strike_step"):
        chain_diagnostics(chain, strike_step=0)


def test_unified_cli_diagnose_ticks(tmp_path):
    ticks = pd.DataFrame(
        [
            {"ts": ns_ist("2026-06-10 09:15:00"), "bid": 100.0, "ask": 100.05, "bid_qty": 75, "ask_qty": 150},
        ]
    )
    path = tmp_path / "ticks.csv"
    out = tmp_path / "diag"
    ticks.to_csv(path, index=False)

    code = main(
        [
            "diagnose-ticks",
            "--ticks",
            str(path),
            "--out",
            str(out),
            "--tick-size",
            "0.05",
            "--max-quote-spread-ticks",
            "1",
            "--max-unchanged-bbo-ns",
            "2000000000",
        ]
    )

    assert code == 0
    assert (out / "diagnostic_summary.csv").exists()
    assert (out / "diagnostic_issues.csv").exists()
    summary = pd.read_csv(out / "diagnostic_summary.csv").iloc[0]
    assert bool(summary["quote_spread_validation_enabled"])
    assert summary["max_quote_spread_ticks"] == pytest.approx(1)
    assert int(summary["wide_spread_rows"]) == 0
    assert bool(summary["bbo_staleness_validation_enabled"])
    assert int(summary["max_unchanged_bbo_ns"]) == 2_000_000_000
    assert int(summary["stale_bbo_rows"]) == 0
