import json

import pandas as pd

from hft_cli import main
from reports.surface_quality import (
    SurfaceQualityThresholds,
    evaluate_surface_quality,
    write_surface_quality_report,
)


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def quotes(theo=11.0):
    ts = ns_ist("2026-06-10 09:15:00")
    return pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000_0",
                "strike": 1000.0,
                "option_type": "C",
                "side": 1,
                "price": 9.9,
                "qty": 75,
                "theo": theo,
                "market_bid": 9.9,
                "market_ask": 10.1,
            },
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000_0",
                "strike": 1000.0,
                "option_type": "C",
                "side": -1,
                "price": 10.1,
                "qty": 75,
                "theo": theo,
                "market_bid": 9.9,
                "market_ask": 10.1,
            },
        ]
    )


def chain(future_call_mid=11.1):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:01")
    return pd.DataFrame(
        [
            {
                "ts": ts0,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 9.9,
                "call_ask": 10.1,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 9.9,
                "put_ask": 10.1,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            },
            {
                "ts": ts1,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": future_call_mid - 0.1,
                "call_ask": future_call_mid + 0.1,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 9.9,
                "put_ask": 10.1,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            },
        ]
    )


def test_surface_quality_passes_when_theo_beats_current_mid():
    report = evaluate_surface_quality(
        quotes(theo=11.0),
        chain(future_call_mid=11.1),
        horizons_ns=[1_000_000_000],
        thresholds=SurfaceQualityThresholds(min_mae_improvement=0.5, min_improvement_rate=1.0),
    )

    row = report.summary.iloc[0]
    assert report.passed
    assert row["observations"] == 1
    assert row["mae_improvement"] > 0.5
    assert row["improvement_rate"] == 1.0


def test_surface_quality_fails_when_theo_is_worse_than_mid():
    report = evaluate_surface_quality(
        quotes(theo=8.0),
        chain(future_call_mid=11.1),
        horizons_ns=[1_000_000_000],
        thresholds=SurfaceQualityThresholds(min_mae_improvement=0.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert "mae_improvement" in failed


def test_write_surface_quality_report_outputs_artifacts_and_manifest(tmp_path):
    quotes_path = tmp_path / "quotes.csv"
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "surface_quality"
    quotes(theo=11.0).to_csv(quotes_path, index=False)
    chain(future_call_mid=11.1).to_csv(chain_path, index=False)

    report = write_surface_quality_report(
        quotes_path,
        chain_path,
        output_dir=out_dir,
        horizons_ns=[1_000_000_000],
        thresholds=SurfaceQualityThresholds(min_mae_improvement=0.5),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.summary.iloc[0]["strategy"] == "surface_mm"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert (out_dir / "surface_quality_details.csv").exists()
    assert (out_dir / "surface_quality_summary.csv").exists()
    assert (out_dir / "surface_quality_checks.csv").exists()
    assert manifest["run_type"] == "surface_quality_report"
    assert manifest["parameters"]["strategy"] == "surface_mm"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"


def test_unified_cli_review_surface_quality_dispatches(tmp_path):
    quotes_path = tmp_path / "quotes.csv"
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "surface_quality_cli"
    quotes(theo=11.0).to_csv(quotes_path, index=False)
    chain(future_call_mid=11.1).to_csv(chain_path, index=False)

    code = main(
        [
            "review-surface-quality",
            "--quotes",
            str(quotes_path),
            "--chain",
            str(chain_path),
            "--out",
            str(out_dir),
            "--horizon-ns",
            "1000000000",
            "--min-mae-improvement",
            "0.5",
            "--fail-on-breach",
        ]
    )

    assert code == 0
    assert (out_dir / "surface_quality_summary.csv").exists()
