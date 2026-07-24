from __future__ import annotations

import pandas as pd
import pytest

from data.diagnostics import chain_diagnostics
from hft_cli import main
from reports.data_readiness import (
    DataReadinessThresholds,
    evaluate_data_readiness,
)
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_pipeline,
)


def _ns(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def _row(
    *,
    ts: int,
    expiry: str,
    strike: float,
) -> dict[str, object]:
    return {
        "ts": ts,
        "expiry": expiry,
        "strike": strike,
        "call_bid": 100.0,
        "call_ask": 100.5,
        "call_bid_qty": 75,
        "call_ask_qty": 150,
        "put_bid": 90.0,
        "put_ask": 90.5,
        "put_bid_qty": 75,
        "put_ask_qty": 150,
    }


def _chain() -> pd.DataFrame:
    t0 = _ns("2026-06-10 09:15:00")
    t1 = t0 + 1_000_000_000
    t3 = t0 + 3_000_000_000
    rows: list[dict[str, object]] = []
    for strike in (22450.0, 22500.0, 22550.0):
        rows.append(
            _row(ts=t0, expiry="2026-06-30", strike=strike)
        )
    for strike in (22500.0, 22550.0):
        rows.append(
            _row(ts=t1, expiry="2026-06-30", strike=strike)
        )
    for strike in (22450.0, 22500.0, 22550.0, 22600.0):
        rows.append(
            _row(ts=t3, expiry="2026-06-30", strike=strike)
        )
    for ts in (t0, t3):
        for strike in (22500.0, 22550.0):
            rows.append(
                _row(ts=ts, expiry="2026-07-07", strike=strike)
            )
    return (
        pd.DataFrame(rows)
        .sort_values(["ts", "expiry", "strike"], kind="mergesort")
        .reset_index(drop=True)
    )


def _vendor_chain() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for timestamp in (
        "2026-06-10 09:15:00",
        "2026-06-10 09:15:01",
    ):
        for strike in (22500.0, 22550.0):
            rows.append(
                {
                    "exchange_ts": timestamp,
                    "expiry_date": "2026-06-30",
                    "strike_price": strike,
                    "ce_bid": 100.0,
                    "ce_ask": 100.5,
                    "ce_bid_qty": 75,
                    "ce_ask_qty": 150,
                    "pe_bid": 90.0,
                    "pe_ask": 90.5,
                    "pe_bid_qty": 75,
                    "pe_ask_qty": 150,
                }
            )
    return pd.DataFrame(rows)


def test_chain_diagnostics_reports_snapshot_breadth_and_cadence():
    result = chain_diagnostics(_chain())

    overall = result.summary.loc[
        result.summary["scope"] == "overall"
    ].iloc[0]
    by_expiry = result.summary.loc[
        result.summary["scope"] == "expiry"
    ].set_index("expiry")

    assert bool(overall["chain_snapshot_validation_enabled"])
    assert int(overall["observation_timestamps"]) == 3
    assert int(overall["expiry_snapshots"]) == 5
    assert int(overall["min_snapshots_per_expiry"]) == 2
    assert float(overall["median_snapshots_per_expiry"]) == 2.5
    assert int(overall["max_snapshots_per_expiry"]) == 3
    assert int(overall["min_snapshot_strikes"]) == 2
    assert float(overall["median_snapshot_strikes"]) == 2.0
    assert int(overall["max_snapshot_strikes"]) == 4
    assert int(overall["snapshot_gap_observations"]) == 3
    assert float(overall["median_snapshot_gap_ns"]) == 2_000_000_000
    assert float(overall["p99_snapshot_gap_ns"]) == pytest.approx(
        2_980_000_000
    )
    assert float(overall["max_snapshot_gap_ns"]) == 3_000_000_000
    assert int(by_expiry.loc["2026-06-30", "expiry_snapshots"]) == 3
    assert int(
        by_expiry.loc["2026-06-30", "min_snapshot_strikes"]
    ) == 2
    assert float(
        by_expiry.loc["2026-06-30", "p99_snapshot_gap_ns"]
    ) == pytest.approx(1_990_000_000)
    assert int(by_expiry.loc["2026-07-07", "expiry_snapshots"]) == 2


def test_data_readiness_enforces_snapshot_coverage_and_cadence():
    diagnostics = chain_diagnostics(_chain())

    rejected = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
            min_chain_expiry_snapshots=6,
            min_chain_snapshots_per_expiry=3,
            min_chain_snapshot_strikes=3,
            max_chain_snapshot_p99_gap_ns=2_500_000_000,
        ),
    )
    accepted = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
            min_chain_expiry_snapshots=5,
            min_chain_snapshots_per_expiry=2,
            min_chain_snapshot_strikes=2,
            max_chain_snapshot_p99_gap_ns=3_000_000_000,
        ),
    )

    assert not rejected.ready
    assert accepted.ready
    failed = set(
        rejected.checks.loc[
            ~rejected.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert {
        "chain_expiry_snapshots",
        "chain_snapshots_per_expiry",
        "chain_snapshot_strikes",
        "chain_snapshot_p99_gap_ns",
    } <= failed
    assert rejected.summary.loc[0, "next_gate"] == "diagnose-chain"


def test_vendor_pipeline_and_cli_enforce_snapshot_requirements(tmp_path):
    source = tmp_path / "chain.csv"
    _vendor_chain().to_csv(source, index=False)

    rejected = write_vendor_market_data_pipeline(
        source,
        output_dir=tmp_path / "rejected",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_chain_expiry_snapshots=3,
            min_chain_snapshots_per_expiry=3,
            min_chain_snapshot_strikes=3,
            max_chain_snapshot_p99_gap_ns=500_000_000,
        ),
    )
    cli_out = tmp_path / "accepted_cli"
    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(source),
            "--out",
            str(cli_out),
            "--adapter",
            "arrow_money",
            "--kind",
            "chain",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-chain-expiry-snapshots",
            "2",
            "--min-chain-snapshots-per-expiry",
            "2",
            "--min-chain-snapshot-strikes",
            "2",
            "--max-chain-snapshot-p99-gap-ns",
            "1000000000",
            "--fail-on-breach",
        ]
    )

    assert not rejected.ready
    assert int(rejected.summary.loc[0, "expiry_snapshots"]) == 2
    assert int(rejected.summary.loc[0, "min_snapshot_strikes"]) == 2
    assert code == 0
    cli_summary = pd.read_csv(
        cli_out / "vendor_market_data_pipeline_summary.csv"
    )
    assert bool(cli_summary.loc[0, "ready"])
    assert int(cli_summary.loc[0, "expiry_snapshots"]) == 2
    assert float(cli_summary.loc[0, "p99_snapshot_gap_ns"]) == (
        1_000_000_000
    )
