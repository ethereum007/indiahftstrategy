from __future__ import annotations

import pandas as pd

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


def _ns(value: str, *, timezone: str = "Asia/Kolkata") -> int:
    return pd.Timestamp(value, tz=timezone).value


def _chain(
    expiries: list[str],
    *,
    timestamp: int | None = None,
) -> pd.DataFrame:
    ts = timestamp or _ns("2026-06-10 09:15:00")
    return pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": expiry,
                "strike": 22500.0 + index * 50,
                "call_bid": 100.0,
                "call_ask": 100.5,
                "call_bid_qty": 75,
                "call_ask_qty": 150,
                "put_bid": 90.0,
                "put_ask": 90.5,
                "put_bid_qty": 75,
                "put_ask_qty": 150,
            }
            for index, expiry in enumerate(expiries)
        ]
    )


def _vendor_chain(expiries: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "expiry_date": expiry,
                "strike_price": 22500 + index * 50,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
            for index, expiry in enumerate(expiries)
        ]
    )


def test_chain_diagnostics_reports_zero_dte_post_expiry_and_parse_failures():
    result = chain_diagnostics(
        _chain(["2026-06-10", "2026-06-09", "not-a-date"])
    )

    overall = result.summary.loc[
        result.summary["scope"] == "overall"
    ].iloc[0]
    by_expiry = result.summary.loc[
        result.summary["scope"] == "expiry"
    ].set_index("expiry")

    assert bool(overall["contract_horizon_validation_enabled"])
    assert overall["contract_horizon_market_timezone"] == "Asia/Kolkata"
    assert int(overall["parseable_contract_expiry_rows"]) == 2
    assert int(overall["unparseable_contract_expiry_rows"]) == 1
    assert int(overall["expired_contract_rows"]) == 1
    assert int(overall["zero_dte_rows"]) == 1
    assert float(overall["min_calendar_dte_days"]) == -1.0
    assert float(overall["median_calendar_dte_days"]) == -0.5
    assert float(overall["max_calendar_dte_days"]) == 0.0
    assert int(by_expiry.loc["2026-06-10", "zero_dte_rows"]) == 1
    assert int(by_expiry.loc["2026-06-09", "expired_contract_rows"]) == 1
    assert pd.isna(
        by_expiry.loc["not-a-date", "median_calendar_dte_days"]
    )
    assert set(result.issues["issue"]) == {
        "expired_contract_observation",
        "unparseable_contract_expiry",
    }


def test_contract_horizon_uses_the_selected_market_timezone():
    timestamp = pd.Timestamp(
        "2026-06-10 00:30:00",
        tz="UTC",
    ).value

    result = chain_diagnostics(
        _chain(["2026-06-09"], timestamp=timestamp),
        market="us_options_regular",
    )

    overall = result.summary.loc[
        result.summary["scope"] == "overall"
    ].iloc[0]
    assert overall["contract_horizon_market_timezone"] == (
        "America/New_York"
    )
    assert int(overall["zero_dte_rows"]) == 1
    assert int(overall["expired_contract_rows"]) == 0
    assert float(overall["median_calendar_dte_days"]) == 0.0


def test_data_readiness_fails_closed_on_contract_horizon_defects():
    diagnostics = chain_diagnostics(
        _chain(["2026-06-09", "not-a-date"])
    )

    strict = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
        ),
    )
    budgeted = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
            max_unparseable_contract_expiry_rows=1,
            max_expired_contract_rows=1,
        ),
    )

    assert not strict.ready
    assert budgeted.ready
    failed = set(
        strict.checks.loc[
            ~strict.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert {
        "chain_unparseable_contract_expiry_rows",
        "chain_expired_contract_rows",
    } <= failed
    assert strict.summary.loc[0, "next_gate"] == "diagnose-chain"


def test_vendor_pipeline_and_cli_enforce_contract_horizon_budgets(tmp_path):
    source = tmp_path / "chain.csv"
    _vendor_chain(["2026-06-09", "not-a-date"]).to_csv(
        source,
        index=False,
    )

    strict = write_vendor_market_data_pipeline(
        source,
        output_dir=tmp_path / "strict",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )
    cli_out = tmp_path / "budgeted_cli"
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
            "--max-unparseable-contract-expiry-rows",
            "1",
            "--max-expired-contract-rows",
            "1",
            "--fail-on-breach",
        ]
    )

    assert not strict.ready
    assert int(strict.summary.loc[0, "expired_contract_rows"]) == 1
    assert int(
        strict.summary.loc[0, "unparseable_contract_expiry_rows"]
    ) == 1
    assert code == 0
    cli_summary = pd.read_csv(
        cli_out / "vendor_market_data_pipeline_summary.csv"
    )
    assert bool(cli_summary.loc[0, "ready"])
    assert int(cli_summary.loc[0, "expired_contract_rows"]) == 1
    assert int(
        cli_summary.loc[0, "unparseable_contract_expiry_rows"]
    ) == 1
