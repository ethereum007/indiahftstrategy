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


def _ns(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def _row(
    *,
    ts: int,
    strike: float,
    call_bid: float = 100.0,
) -> dict[str, object]:
    return {
        "ts": ts,
        "expiry": "2026-06-30",
        "strike": strike,
        "call_bid": call_bid,
        "call_ask": call_bid + 0.5,
        "call_bid_qty": 75,
        "call_ask_qty": 150,
        "put_bid": 90.0,
        "put_ask": 90.5,
        "put_bid_qty": 75,
        "put_ask_qty": 150,
    }


def _chain_with_key_collisions() -> pd.DataFrame:
    ts = _ns("2026-06-10 09:15:00")
    exact = _row(ts=ts, strike=22500.0)
    return pd.DataFrame(
        [
            exact,
            dict(exact),
            _row(ts=ts, strike=22550.0, call_bid=110.0),
            _row(ts=ts, strike=22550.0, call_bid=111.0),
            _row(ts=ts + 1, strike=22550.0, call_bid=111.0),
        ]
    )


def _vendor_chain_with_key_collisions() -> pd.DataFrame:
    normalized = _chain_with_key_collisions()
    return normalized.rename(
        columns={
            "ts": "exchange_ts",
            "expiry": "expiry_date",
            "strike": "strike_price",
            "call_bid": "ce_bid",
            "call_ask": "ce_ask",
            "call_bid_qty": "ce_bid_qty",
            "call_ask_qty": "ce_ask_qty",
            "put_bid": "pe_bid",
            "put_ask": "pe_ask",
            "put_bid_qty": "pe_bid_qty",
            "put_ask_qty": "pe_ask_qty",
        }
    ).assign(
        exchange_ts=[
            "2026-06-10 09:15:00.000000000",
            "2026-06-10 09:15:00.000000000",
            "2026-06-10 09:15:00.000000000",
            "2026-06-10 09:15:00.000000000",
            "2026-06-10 09:15:00.000000001",
        ]
    )


def test_chain_diagnostics_classifies_exact_and_conflicting_keys():
    result = chain_diagnostics(_chain_with_key_collisions())

    overall = result.summary.loc[
        result.summary["scope"] == "overall"
    ].iloc[0]
    expiry = result.summary.loc[
        result.summary["scope"] == "expiry"
    ].iloc[0]

    assert bool(overall["contract_key_validation_enabled"])
    assert int(overall["duplicate_contract_key_rows"]) == 4
    assert int(overall["duplicate_contract_key_excess_rows"]) == 2
    assert int(overall["duplicate_contract_key_groups"]) == 2
    assert int(overall["exact_duplicate_contract_key_rows"]) == 2
    assert int(overall["exact_duplicate_contract_key_groups"]) == 1
    assert int(overall["conflicting_contract_key_rows"]) == 2
    assert int(overall["conflicting_contract_key_groups"]) == 1
    assert int(expiry["duplicate_contract_key_rows"]) == 4
    assert int(expiry["conflicting_contract_key_groups"]) == 1
    assert len(result.issues) == 4
    assert set(result.issues["issue"]) == {
        "duplicate_contract_observation",
        "conflicting_contract_observation",
    }


def test_data_readiness_separates_duplicate_and_conflict_budgets():
    diagnostics = chain_diagnostics(_chain_with_key_collisions())

    strict = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
        ),
    )
    exact_budget_only = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
            max_duplicate_contract_key_rows=4,
        ),
    )
    fully_budgeted = evaluate_data_readiness(
        chain_diagnostic_summary=diagnostics.summary,
        thresholds=DataReadinessThresholds(
            require_tick_diagnostics=False,
            require_chain_diagnostics=True,
            max_duplicate_contract_key_rows=4,
            max_conflicting_contract_key_rows=2,
        ),
    )

    assert not strict.ready
    assert not exact_budget_only.ready
    assert fully_budgeted.ready
    strict_failed = set(
        strict.checks.loc[
            ~strict.checks["passed"].astype(bool),
            "check",
        ]
    )
    exact_budget_failed = set(
        exact_budget_only.checks.loc[
            ~exact_budget_only.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert {
        "chain_duplicate_contract_key_rows",
        "chain_conflicting_contract_key_rows",
    } <= strict_failed
    assert "chain_duplicate_contract_key_rows" not in exact_budget_failed
    assert "chain_conflicting_contract_key_rows" in exact_budget_failed
    assert strict.summary.loc[0, "next_gate"] == "diagnose-chain"


def test_vendor_pipeline_and_cli_enforce_contract_key_budgets(tmp_path):
    source = tmp_path / "chain.csv"
    _vendor_chain_with_key_collisions().to_csv(source, index=False)

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
            "--max-duplicate-contract-key-rows",
            "4",
            "--max-conflicting-contract-key-rows",
            "2",
            "--fail-on-breach",
        ]
    )

    assert not strict.ready
    assert int(strict.summary.loc[0, "duplicate_contract_key_rows"]) == 4
    assert int(
        strict.summary.loc[0, "conflicting_contract_key_rows"]
    ) == 2
    assert code == 0
    cli_summary = pd.read_csv(
        cli_out / "vendor_market_data_pipeline_summary.csv"
    )
    assert bool(cli_summary.loc[0, "ready"])
    assert int(cli_summary.loc[0, "duplicate_contract_key_rows"]) == 4
    assert int(
        cli_summary.loc[0, "conflicting_contract_key_rows"]
    ) == 2
