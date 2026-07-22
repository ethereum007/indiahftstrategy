import pandas as pd

from hft_cli import main
from reports.market_profile import (
    MarketProfileReportConfig,
    build_market_profile_report,
    write_market_profile_report,
)


def test_market_profile_report_lists_india_and_us_sessions():
    report = build_market_profile_report()

    assert set(report.profiles["market"]) == {
        "india_nse_index_derivatives",
        "us_equities_regular",
        "us_options_regular",
    }
    us_equities = report.profiles.loc[report.profiles["market"] == "us_equities_regular"].iloc[0]
    assert us_equities["timezone"] == "America/New_York"
    assert us_equities["open_time"] == "09:30:00"
    assert us_equities["close_time"] == "16:00:00"
    assert us_equities["trading_day_policy"] == "weekday_only_no_holiday_calendar"
    assert us_equities["trading_weekdays"] == "Mon|Tue|Wed|Thu|Fri"
    assert int(us_equities["trading_weekday_count"]) == 5
    assert report.summary.iloc[0]["markets"] == 3
    assert report.summary.iloc[0]["weekday_only_markets"] == 3


def test_market_profile_report_calculates_explicit_generic_cost_examples():
    report = build_market_profile_report(
        MarketProfileReportConfig(
            markets=("us_options_regular",),
            price=5.0,
            qty=100,
            buy_notional_rate=0.00001,
            sell_notional_rate=0.00002,
            per_contract_fee=0.10,
            per_order_fee=0.25,
        )
    )

    row = report.cost_examples.iloc[0]
    assert row["market"] == "us_options_regular"
    assert row["instrument_kind"] == "OPT"
    assert row["buy_cost"] == 0.005 + 0.10 + 0.25
    assert row["sell_cost"] == 0.010 + 0.10 + 0.25
    assert report.summary.iloc[0]["explicit_fee_model"]


def test_write_market_profile_report_outputs_files_and_manifest(tmp_path):
    out_dir = tmp_path / "market_profile"

    report = write_market_profile_report(
        out_dir,
        config=MarketProfileReportConfig(markets=("india_nse_index_derivatives",), price=100.0),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "market_profiles.csv").exists()
    assert (out_dir / "market_cost_examples.csv").exists()
    assert (out_dir / "market_profile_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_market_profile_report_writes_us_profile(tmp_path):
    out_dir = tmp_path / "cli_market_profile"

    code = main(
        [
            "market-profile-report",
            "--market",
            "us_equities_regular",
            "--out",
            str(out_dir),
            "--price",
            "100",
            "--qty",
            "10",
            "--per-order-fee",
            "0.25",
        ]
    )

    profiles = pd.read_csv(out_dir / "market_profiles.csv")
    costs = pd.read_csv(out_dir / "market_cost_examples.csv")
    assert code == 0
    assert profiles.loc[0, "market"] == "us_equities_regular"
    assert costs.loc[0, "instrument_kind"] == "EQ"
    assert costs.loc[0, "round_trip_cost"] == 0.50
