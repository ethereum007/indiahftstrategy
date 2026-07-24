import json
from pathlib import Path

import pandas as pd
import pytest

from data.diagnostics import chain_diagnostics
from hft_cli import main
from markets.lot_sizes import (
    DEFAULT_NSE_INDEX_LOT_RULE_PATH,
    load_nse_index_lot_rule,
    resolve_nse_index_lot_size,
    validate_nse_index_lot_size,
)
from markets.profiles import get_market_profile
from reports.data_readiness import (
    DataReadinessThresholds,
    evaluate_data_readiness,
)
from reports.manifest import file_sha256
from reports.market_calendar import build_market_calendar_report
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_pipeline,
)


MARKET = "india_nse_index_derivatives"


def _calendar_path(tmp_path: Path) -> Path:
    path = tmp_path / "market_calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calendar_id": "nse-fo-2026-lot-size-test",
                "market": MARKET,
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-01-01",
                "valid_to": "2026-07-31",
                "provenance": {
                    "publisher": "National Stock Exchange of India Limited",
                    "source_url": (
                        "https://www.nseindia.com/api/"
                        "holiday-master?type=trading"
                    ),
                    "published_date": "2026-01-12",
                },
                "sessions": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _chain(expiries: list[str]) -> pd.DataFrame:
    ts = pd.Timestamp(
        "2026-01-15 09:15:00",
        tz="Asia/Kolkata",
    ).value
    return pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": expiry,
                "strike": 22500.0 + index * 50,
                "call_bid": 100.0,
                "call_ask": 100.5,
                "call_bid_qty": 65,
                "call_ask_qty": 130,
                "put_bid": 90.0,
                "put_ask": 90.5,
                "put_bid_qty": 65,
                "put_ask_qty": 130,
            }
            for index, expiry in enumerate(expiries)
        ]
    )


def _vendor_chain(expiry: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": "2026-01-15 09:15:00",
                "expiry_date": expiry,
                "strike_price": 22500,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 65,
                "ce_ask_qty": 130,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 65,
                "pe_ask_qty": 130,
            }
        ]
    )


def test_pinned_nse_index_lot_rule_binds_circular_and_current_snapshot():
    rule = load_nse_index_lot_rule()
    profile = get_market_profile(MARKET)

    assert rule.rule_id == "nse_fo_index_lot_sizes_from_2026-01_v1"
    assert rule.circular_id == "NSE/FAOP/70616"
    assert rule.circular_date.isoformat() == "2025-10-03"
    assert rule.config_path == DEFAULT_NSE_INDEX_LOT_RULE_PATH.resolve()
    assert rule.authority_source_sha256 == (
        "0718cf0cc7e6c74105dc946497369270fca807f59912586560c9552cad8050ef"
    )
    assert rule.snapshot_as_of.isoformat() == "2026-07-24"
    assert rule.snapshot_sha256 == (
        "3f3d885902d1ac5290dbe18393e68d05f6843592677bf79110b6f00591968f8b"
    )
    assert dict(rule.snapshot_lot_sizes) == {
        "NIFTY": 65,
        "BANKNIFTY": 30,
        "FINNIFTY": 60,
        "MIDCPNIFTY": 120,
        "NIFTYNXT50": 25,
    }
    assert profile.default_lot_size == 65
    assert file_sha256(rule.authority_source_path) == (
        rule.authority_source_sha256
    )
    assert file_sha256(rule.snapshot_path) == rule.snapshot_sha256


def test_nse_index_lot_resolution_covers_declared_cycles_and_fails_closed():
    assert resolve_nse_index_lot_size(
        "NIFTY",
        "2026-01-06",
        cycle="weekly",
    ).lot_size == 65
    expected = {
        "NIFTY": 65,
        "BANKNIFTY": 30,
        "FINNIFTY": 60,
        "MIDCPNIFTY": 120,
        "NIFTYNXT50": 25,
    }
    assert {
        symbol: resolve_nse_index_lot_size(
            symbol,
            "2026-01-27",
            cycle="monthly",
        ).lot_size
        for symbol in expected
    } == expected

    with pytest.raises(ValueError, match="before 2026-01-27"):
        resolve_nse_index_lot_size(
            "NIFTY",
            "2025-12-30",
            cycle="monthly",
        )
    with pytest.raises(ValueError, match="BANKNIFTY weekly"):
        resolve_nse_index_lot_size(
            "BANKNIFTY",
            "2026-01-06",
            cycle="weekly",
        )


def test_nse_index_lot_validation_distinguishes_mismatch_and_coverage():
    valid = validate_nse_index_lot_size(
        "NIFTY",
        "2026-01-27",
        65,
        cycle="monthly",
    )
    mismatch = validate_nse_index_lot_size(
        "NIFTY",
        "2026-01-27",
        75,
        cycle="monthly",
    )
    unsupported = validate_nse_index_lot_size(
        "SENSEX",
        "2026-01-27",
        20,
        cycle="monthly",
    )

    assert valid.valid
    assert valid.covered
    assert valid.expected_lot_size == 65
    assert not mismatch.valid
    assert mismatch.covered
    assert mismatch.reason == "contract_lot_size_mismatch"
    assert mismatch.expected_lot_size == 65
    assert not unsupported.valid
    assert not unsupported.covered
    assert "does not cover SENSEX monthly" in unsupported.reason


def test_chain_diagnostics_reports_lot_provenance_and_mismatch_rows(
    tmp_path,
):
    calendar = _calendar_path(tmp_path)
    valid = chain_diagnostics(
        _chain(["2026-01-27"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
        underlying="NIFTY",
        lot_size=65,
    )
    mismatch = chain_diagnostics(
        _chain(["2026-01-27"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
        underlying="NIFTY",
        lot_size=75,
    )

    valid_overall = valid.summary.loc[
        valid.summary["scope"] == "overall"
    ].iloc[0]
    mismatch_overall = mismatch.summary.loc[
        mismatch.summary["scope"] == "overall"
    ].iloc[0]
    mismatch_expiry = mismatch.summary.loc[
        mismatch.summary["scope"] == "expiry"
    ].iloc[0]
    assert bool(valid_overall["contract_lot_validation_enabled"])
    assert valid_overall["contract_lot_underlying"] == "NIFTY"
    assert int(valid_overall["contract_lot_size"]) == 65
    assert valid_overall["contract_lot_rule_id"] == (
        "nse_fo_index_lot_sizes_from_2026-01_v1"
    )
    assert valid_overall["contract_lot_snapshot_sha256"] == (
        "3f3d885902d1ac5290dbe18393e68d05f6843592677bf79110b6f00591968f8b"
    )
    assert int(valid_overall["invalid_contract_lot_rows"]) == 0
    assert int(mismatch_overall["invalid_contract_lot_rows"]) == 1
    assert int(mismatch_overall["uncovered_contract_lot_rows"]) == 0
    assert int(mismatch_expiry["contract_lot_expected"]) == 65
    assert mismatch_expiry["contract_lot_reason"] == (
        "contract_lot_size_mismatch"
    )
    assert set(mismatch.issues["issue"]) == {"invalid_contract_lot_size"}


def test_data_readiness_requires_current_validated_contract_lot(tmp_path):
    calendar = _calendar_path(tmp_path)
    calendar_summary = build_market_calendar_report(calendar).summary
    valid = chain_diagnostics(
        _chain(["2026-01-27"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
        underlying="NIFTY",
        lot_size=65,
    )
    mismatch = chain_diagnostics(
        _chain(["2026-01-27"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
        underlying="NIFTY",
        lot_size=75,
    )
    thresholds = DataReadinessThresholds(
        require_tick_diagnostics=False,
        require_contract_lot_validation=True,
    )

    accepted = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=valid.summary,
        thresholds=thresholds,
    )
    rejected = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=mismatch.summary,
        thresholds=thresholds,
    )
    stale_snapshot = tmp_path / "stale_lot_snapshot.csv"
    stale_snapshot.write_text("stale\n", encoding="utf-8")
    stale_summary = valid.summary.copy()
    overall_mask = stale_summary["scope"] == "overall"
    stale_summary.loc[
        overall_mask,
        "contract_lot_snapshot_path",
    ] = str(stale_snapshot)
    stale = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=stale_summary,
        thresholds=thresholds,
    )

    assert accepted.ready
    assert not rejected.ready
    assert not stale.ready
    assert "chain_invalid_contract_lot_rows" in set(
        rejected.checks.loc[
            ~rejected.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert "chain_contract_lot_snapshot_current" in set(
        stale.checks.loc[
            ~stale.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert rejected.summary.loc[0, "next_gate"] == "diagnose-chain"


def test_vendor_chain_pipeline_and_cli_enforce_declared_contract_lot(
    tmp_path,
):
    calendar = _calendar_path(tmp_path)
    source_path = tmp_path / "chain.csv"
    normalized_path = tmp_path / "normalized_chain.csv"
    _vendor_chain("2026-01-27").to_csv(source_path, index=False)
    _chain(["2026-01-27"]).to_csv(normalized_path, index=False)

    valid = write_vendor_market_data_pipeline(
        source_path,
        output_dir=tmp_path / "valid_pipeline",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            market_calendar_path=str(calendar),
            expiry_cycle="monthly",
            underlying="NIFTY",
            lot_size=65,
            tick_size=0.05,
        ),
    )
    mismatch = write_vendor_market_data_pipeline(
        source_path,
        output_dir=tmp_path / "mismatch_pipeline",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            market_calendar_path=str(calendar),
            expiry_cycle="monthly",
            underlying="NIFTY",
            lot_size=75,
            tick_size=0.05,
        ),
    )
    cli_out = tmp_path / "cli_diagnostics"
    code = main(
        [
            "diagnose-chain",
            "--chain",
            str(normalized_path),
            "--out",
            str(cli_out),
            "--market-calendar",
            str(calendar),
            "--expiry-cycle",
            "monthly",
            "--underlying",
            "NIFTY",
            "--lot-size",
            "75",
        ]
    )

    assert valid.ready
    assert bool(valid.summary.loc[0, "contract_lot_validation_enabled"])
    manifest = json.loads(
        (
            tmp_path
            / "valid_pipeline"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        "contract_lot_rule",
        "contract_lot_authority_source",
        "contract_lot_snapshot",
    } <= set(manifest["inputs"])
    assert not mismatch.ready
    assert int(mismatch.summary.loc[0, "invalid_contract_lot_rows"]) == 1
    assert code == 0
    cli_summary = pd.read_csv(cli_out / "diagnostic_summary.csv")
    cli_overall = cli_summary.loc[cli_summary["scope"] == "overall"].iloc[0]
    assert int(cli_overall["invalid_contract_lot_rows"]) == 1


def test_vendor_pipeline_requires_complete_contract_lot_declaration(tmp_path):
    calendar = _calendar_path(tmp_path)
    source_path = tmp_path / "chain.csv"
    _vendor_chain("2026-01-27").to_csv(source_path, index=False)

    with pytest.raises(ValueError, match="lot_size must be a positive integer"):
        write_vendor_market_data_pipeline(
            source_path,
            output_dir=tmp_path / "invalid_pipeline",
            config=VendorMarketDataPipelineConfig(
                kind="chain",
                timestamp_unit="datetime",
                market_calendar_path=str(calendar),
                expiry_cycle="monthly",
                underlying="NIFTY",
            ),
        )
