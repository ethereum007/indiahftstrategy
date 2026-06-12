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
    assert set(result.issues["issue"]) == {"crossed_quote", "nonpositive_depth", "out_of_session"}
    assert (out.output_dir / "diagnostic_summary.csv").exists()
    assert (out.output_dir / "diagnostic_issues.csv").exists()


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
    assert expiry["strikes"] == 2
    assert expiry["min_strike"] == 1000.0
    assert expiry["max_strike"] == 1010.0


def test_unified_cli_diagnose_ticks(tmp_path):
    ticks = pd.DataFrame(
        [
            {"ts": ns_ist("2026-06-10 09:15:00"), "bid": 100.0, "ask": 100.05, "bid_qty": 75, "ask_qty": 150},
        ]
    )
    path = tmp_path / "ticks.csv"
    out = tmp_path / "diag"
    ticks.to_csv(path, index=False)

    code = main(["diagnose-ticks", "--ticks", str(path), "--out", str(out), "--tick-size", "0.05"])

    assert code == 0
    assert (out / "diagnostic_summary.csv").exists()
    assert (out / "diagnostic_issues.csv").exists()
