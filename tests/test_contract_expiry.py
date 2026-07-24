import json
from pathlib import Path

import pandas as pd

from data.diagnostics import chain_diagnostics
from hft_cli import main
from markets.expiries import (
    DEFAULT_NSE_FO_EXPIRY_RULE_PATH,
    load_nse_fo_expiry_rule,
    resolve_nse_fo_expiry,
    validate_nse_fo_expiry,
)
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
                "calendar_id": "nse-fo-2026-h1-expiry-test",
                "market": MARKET,
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-01-01",
                "valid_to": "2026-06-30",
                "provenance": {
                    "publisher": "National Stock Exchange of India Limited",
                    "source_url": (
                        "https://www.nseindia.com/api/"
                        "holiday-master?type=trading"
                    ),
                    "published_date": "2026-01-12",
                },
                "sessions": [
                    {
                        "date": "2026-03-03",
                        "status": "closed",
                        "label": "Holi",
                    },
                    {
                        "date": "2026-03-31",
                        "status": "closed",
                        "label": "Shri Mahavir Jayanti",
                    },
                ],
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
        "2026-06-10 09:15:00",
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
                "call_bid_qty": 75,
                "call_ask_qty": 75,
                "put_bid": 90.0,
                "put_ask": 90.5,
                "put_bid_qty": 75,
                "put_ask_qty": 75,
            }
            for index, expiry in enumerate(expiries)
        ]
    )


def _vendor_chain(expiry: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "expiry_date": expiry,
                "strike_price": 22500,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
        ]
    )


def test_pinned_nse_expiry_rule_binds_official_circular():
    rule = load_nse_fo_expiry_rule()

    assert rule.rule_id == "nse_fo_tuesday_expiry_from_2025-09-01_v1"
    assert rule.circular_id == "NSE/FAOP/68747"
    assert rule.effective_from.isoformat() == "2025-09-01"
    assert rule.expiry_weekday == 1
    assert rule.cycles == ("weekly", "monthly")
    assert rule.config_path == DEFAULT_NSE_FO_EXPIRY_RULE_PATH.resolve()
    assert rule.authority_source_sha256 == (
        "e1b56024a511135ffd5c6c3c097881dd0ac2c37b15b5f61e94fe84e51cf66762"
    )
    assert file_sha256(rule.authority_source_path) == (
        rule.authority_source_sha256
    )


def test_nse_expiry_resolution_applies_weekly_and_monthly_holiday_rollback(
    tmp_path,
):
    calendar = _calendar_path(tmp_path)

    weekly = resolve_nse_fo_expiry(
        "2026-03-02",
        cycle="weekly",
        market_calendar=calendar,
    )
    monthly = resolve_nse_fo_expiry(
        "2026-03-15",
        cycle="monthly",
        market_calendar=calendar,
    )
    ordinary = resolve_nse_fo_expiry(
        "2026-06-01",
        cycle="monthly",
        market_calendar=calendar,
    )

    assert weekly.nominal_expiry.isoformat() == "2026-03-03"
    assert weekly.actual_expiry.isoformat() == "2026-03-02"
    assert weekly.rollback_days == 1
    assert weekly.adjusted
    assert monthly.nominal_expiry.isoformat() == "2026-03-31"
    assert monthly.actual_expiry.isoformat() == "2026-03-30"
    assert monthly.adjusted
    assert ordinary.actual_expiry.isoformat() == "2026-06-30"
    assert not ordinary.adjusted


def test_nse_expiry_validation_fails_closed_for_wrong_or_uncovered_dates(
    tmp_path,
):
    calendar = _calendar_path(tmp_path)

    adjusted = validate_nse_fo_expiry(
        "2026-03-30",
        cycle="monthly",
        market_calendar=calendar,
    )
    holiday = validate_nse_fo_expiry(
        "2026-03-31",
        cycle="monthly",
        market_calendar=calendar,
    )
    wrong_weekday = validate_nse_fo_expiry(
        "2026-06-25",
        cycle="monthly",
        market_calendar=calendar,
    )
    uncovered = validate_nse_fo_expiry(
        "2026-07-28",
        cycle="monthly",
        market_calendar=calendar,
    )

    assert adjusted.valid
    assert adjusted.covered
    assert adjusted.reason == "valid_adjusted_expiry"
    assert not holiday.valid
    assert holiday.covered
    assert holiday.expected_expiry.isoformat() == "2026-03-30"
    assert not wrong_weekday.valid
    assert wrong_weekday.covered
    assert wrong_weekday.expected_expiry.isoformat() == "2026-06-30"
    assert not uncovered.valid
    assert not uncovered.covered
    assert "does not cover" in uncovered.reason


def test_chain_diagnostics_reports_rule_provenance_and_invalid_expiry_rows(
    tmp_path,
):
    calendar = _calendar_path(tmp_path)

    result = chain_diagnostics(
        _chain(["2026-06-30", "2026-06-25"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
    )

    overall = result.summary.loc[result.summary["scope"] == "overall"].iloc[0]
    expiry_rows = result.summary.loc[
        result.summary["scope"] == "expiry"
    ].set_index("expiry")
    assert bool(overall["contract_expiry_validation_enabled"])
    assert overall["contract_expiry_cycle"] == "monthly"
    assert overall["contract_expiry_rule_id"] == (
        "nse_fo_tuesday_expiry_from_2025-09-01_v1"
    )
    assert overall["contract_expiry_authority_source_sha256"] == (
        "e1b56024a511135ffd5c6c3c097881dd0ac2c37b15b5f61e94fe84e51cf66762"
    )
    assert int(overall["invalid_contract_expiry_rows"]) == 1
    assert int(overall["uncovered_contract_expiry_rows"]) == 0
    assert bool(expiry_rows.loc["2026-06-30", "contract_expiry_valid"])
    assert not bool(
        expiry_rows.loc["2026-06-25", "contract_expiry_valid"]
    )
    assert (
        expiry_rows.loc["2026-06-25", "contract_expiry_expected"]
        == "2026-06-30"
    )
    assert set(result.issues["issue"]) == {"invalid_contract_expiry"}


def test_data_readiness_requires_validated_exchange_expiries(tmp_path):
    calendar = _calendar_path(tmp_path)
    calendar_summary = build_market_calendar_report(calendar).summary
    valid = chain_diagnostics(
        _chain(["2026-06-30"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
    )
    invalid = chain_diagnostics(
        _chain(["2026-06-25"]),
        market_calendar=calendar,
        expiry_cycle="monthly",
    )
    thresholds = DataReadinessThresholds(
        require_tick_diagnostics=False,
        require_contract_expiry_validation=True,
    )

    accepted = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=valid.summary,
        thresholds=thresholds,
    )
    rejected = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=invalid.summary,
        thresholds=thresholds,
    )
    stale_rule = tmp_path / "stale_expiry_rule.json"
    stale_rule.write_text("{}\n", encoding="utf-8")
    stale_summary = valid.summary.copy()
    overall_mask = stale_summary["scope"] == "overall"
    stale_summary.loc[
        overall_mask,
        "contract_expiry_rule_path",
    ] = str(stale_rule)
    stale = evaluate_data_readiness(
        market_calendar_summary=calendar_summary,
        chain_diagnostic_summary=stale_summary,
        thresholds=thresholds,
    )

    assert accepted.ready
    assert not rejected.ready
    assert not stale.ready
    failed = set(
        rejected.checks.loc[
            ~rejected.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert "chain_invalid_contract_expiry_rows" in failed
    assert "chain_contract_expiry_rule_current" in set(
        stale.checks.loc[
            ~stale.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert rejected.summary.loc[0, "next_gate"] == "diagnose-chain"


def test_vendor_chain_pipeline_and_cli_enforce_declared_expiry_cycle(tmp_path):
    calendar = _calendar_path(tmp_path)
    valid_path = tmp_path / "valid_chain.csv"
    invalid_path = tmp_path / "invalid_chain.csv"
    normalized_invalid_path = tmp_path / "normalized_invalid_chain.csv"
    _vendor_chain("2026-06-30").to_csv(valid_path, index=False)
    _vendor_chain("2026-06-25").to_csv(invalid_path, index=False)
    _chain(["2026-06-25"]).to_csv(normalized_invalid_path, index=False)

    valid = write_vendor_market_data_pipeline(
        valid_path,
        output_dir=tmp_path / "valid_pipeline",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            market_calendar_path=str(calendar),
            expiry_cycle="monthly",
            tick_size=0.05,
        ),
    )
    invalid = write_vendor_market_data_pipeline(
        invalid_path,
        output_dir=tmp_path / "invalid_pipeline",
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            market_calendar_path=str(calendar),
            expiry_cycle="monthly",
            tick_size=0.05,
        ),
    )
    cli_out = tmp_path / "cli_diagnostics"
    code = main(
        [
            "diagnose-chain",
            "--chain",
            str(normalized_invalid_path),
            "--out",
            str(cli_out),
            "--market-calendar",
            str(calendar),
            "--expiry-cycle",
            "monthly",
        ]
    )

    assert valid.ready
    assert bool(
        valid.summary.loc[0, "contract_expiry_validation_enabled"]
    )
    manifest = json.loads(
        (
            tmp_path
            / "valid_pipeline"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert {
        "contract_expiry_rule",
        "contract_expiry_authority_source",
    } <= set(manifest["inputs"])
    assert not invalid.ready
    assert int(invalid.summary.loc[0, "invalid_contract_expiry_rows"]) == 1
    assert code == 0
    cli_summary = pd.read_csv(cli_out / "diagnostic_summary.csv")
    cli_overall = cli_summary.loc[cli_summary["scope"] == "overall"].iloc[0]
    assert int(cli_overall["invalid_contract_expiry_rows"]) == 1
