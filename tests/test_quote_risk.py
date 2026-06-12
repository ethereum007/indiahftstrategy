import pandas as pd

from hft_cli import main
from reports.quote_risk import QuoteRiskThresholds, evaluate_quote_risk, write_quote_risk_report


def safe_quotes():
    return pd.DataFrame(
        [
            {
                "ts": 1,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000",
                "side": 1,
                "price": 10.0,
                "qty": 75,
                "theo": 10.20,
                "quote_edge": 0.20,
                "marketable": False,
                "market_spread_ticks": 4.0,
            },
            {
                "ts": 1,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000",
                "side": -1,
                "price": 10.45,
                "qty": 75,
                "theo": 10.20,
                "quote_edge": 0.25,
                "marketable": False,
                "market_spread_ticks": 4.0,
            },
            {
                "ts": 1,
                "expiry": "2026-06-30",
                "instrument_id": "PUT_1000",
                "side": 1,
                "price": 9.8,
                "qty": 75,
                "theo": 10.00,
                "quote_edge": 0.20,
                "marketable": False,
                "market_spread_ticks": 5.0,
            },
            {
                "ts": 1,
                "expiry": "2026-06-30",
                "instrument_id": "PUT_1000",
                "side": -1,
                "price": 10.25,
                "qty": 75,
                "theo": 10.00,
                "quote_edge": 0.25,
                "marketable": False,
                "market_spread_ticks": 5.0,
            },
        ]
    )


def test_evaluate_quote_risk_passes_balanced_nonmarketable_quotes():
    report = evaluate_quote_risk(
        safe_quotes(),
        thresholds=QuoteRiskThresholds(
            min_quotes=4,
            min_instruments=2,
            min_quote_edge=0.10,
            max_market_spread_ticks=5.0,
            max_quotes_per_instrument=2,
        ),
    )

    assert report.passed
    assert report.summary.iloc[0]["bid_share"] == 0.5
    assert report.summary.iloc[0]["marketable_quotes"] == 0
    assert set(report.by_instrument["instrument_id"]) == {"CALL_1000", "PUT_1000"}


def test_quote_risk_fails_marketable_negative_edge_quotes():
    quotes = safe_quotes()
    quotes.loc[0, "marketable"] = True
    quotes.loc[1, "quote_edge"] = -0.05

    report = evaluate_quote_risk(quotes, thresholds=QuoteRiskThresholds(min_quote_edge=0.0))

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert failed == {"marketable_quotes", "min_quote_edge"}


def test_write_quote_risk_report_outputs_checks_summary_and_manifest(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "quote_review"
    safe_quotes().to_csv(quotes_path, index=False)

    report = write_quote_risk_report(
        quotes_path,
        output_dir=out_dir,
        thresholds=QuoteRiskThresholds(min_quotes=4, min_instruments=2, min_quote_edge=0.1),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "quote_risk_summary.csv").exists()
    assert (out_dir / "quote_risk_checks.csv").exists()
    assert (out_dir / "quote_risk_by_instrument.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_review_quotes_can_fail_on_breach(tmp_path):
    quotes = safe_quotes()
    quotes.loc[0, "marketable"] = True
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "cli_quote_review"
    quotes.to_csv(quotes_path, index=False)

    code = main(
        [
            "review-quotes",
            "--quotes",
            str(quotes_path),
            "--out",
            str(out_dir),
            "--min-quotes",
            "4",
            "--min-instruments",
            "2",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "quote_risk_checks.csv").exists()
    assert (out_dir / "manifest.json").exists()
