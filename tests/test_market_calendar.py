import json

import pandas as pd
import pytest

from adapters.mapped_data import MappedDataConfig, write_mapped_data_normalization
from data.chains import normalize_option_chain
from data.diagnostics import chain_diagnostics, tick_diagnostics
from data.loaders import normalize_ticks, trading_session_mask
from hft_cli import main
from markets.calendars import load_market_calendar
from reports.manifest import file_sha256, verify_experiment_manifest
from reports.market_calendar import write_market_calendar_report


MARKET = "india_nse_index_derivatives"


def _ns(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def _calendar_path(tmp_path):
    path = tmp_path / "nse_calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calendar_id": "nse-fo-test-2026-06",
                "market": MARKET,
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-06-08",
                "valid_to": "2026-06-15",
                "provenance": {
                    "publisher": "test-fixture",
                    "source_url": "https://example.test/nse-calendar",
                    "published_date": "2026-06-01",
                },
                "sessions": [
                    {
                        "date": "2026-06-10",
                        "status": "closed",
                        "label": "exchange holiday",
                    },
                    {
                        "date": "2026-06-13",
                        "status": "open",
                        "open_time": "18:00:00",
                        "close_time": "19:00:00",
                        "label": "special session",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _tick_rows():
    timestamps = [
        _ns("2026-06-09 10:00:00"),
        _ns("2026-06-10 10:00:00"),
        _ns("2026-06-13 10:00:00"),
        _ns("2026-06-13 18:30:00"),
        _ns("2026-06-14 10:00:00"),
        _ns("2026-06-16 10:00:00"),
    ]
    return pd.DataFrame(
        {
            "ts": timestamps,
            "bid": [100.0] * len(timestamps),
            "ask": [100.05] * len(timestamps),
            "bid_qty": [75] * len(timestamps),
            "ask_qty": [75] * len(timestamps),
        }
    )


def _chain_rows():
    ticks = _tick_rows()
    return pd.DataFrame(
        {
            "ts": ticks["ts"],
            "expiry": ["2026-06-25"] * len(ticks),
            "strike": [22500.0] * len(ticks),
            "call_bid": [100.0] * len(ticks),
            "call_ask": [100.5] * len(ticks),
            "call_bid_qty": [75] * len(ticks),
            "call_ask_qty": [75] * len(ticks),
            "put_bid": [90.0] * len(ticks),
            "put_ask": [90.5] * len(ticks),
            "put_bid_qty": [75] * len(ticks),
            "put_ask_qty": [75] * len(ticks),
        }
    )


def test_calendar_masks_holidays_special_sessions_and_coverage(tmp_path):
    calendar_path = _calendar_path(tmp_path)
    timestamps = _tick_rows()["ts"]

    mask = trading_session_mask(
        timestamps,
        market=MARKET,
        market_calendar=calendar_path,
    )

    assert mask.tolist() == [True, False, False, True, False, False]
    null_mask = trading_session_mask(
        pd.Series([timestamps.iloc[0], None]),
        market=MARKET,
        market_calendar=calendar_path,
    )
    assert null_mask.tolist() == [True, False]


def test_calendar_aware_normalization_keeps_reason_specific_quarantine(tmp_path):
    calendar_path = _calendar_path(tmp_path)

    ticks = normalize_ticks(_tick_rows(), market_calendar=calendar_path)
    chain = normalize_option_chain(_chain_rows(), market_calendar=calendar_path)

    for normalized in (ticks, chain):
        assert len(normalized.data) == 2
        assert normalized.quarantine.dropped_non_trading_day_rows == 3
        assert normalized.quarantine.dropped_calendar_closed_rows == 1
        assert normalized.quarantine.dropped_calendar_out_of_range_rows == 1
        assert normalized.quarantine.dropped_out_of_session_rows == 1


def test_calendar_aware_diagnostics_use_distinct_issue_labels(tmp_path):
    calendar_path = _calendar_path(tmp_path)

    tick_result = tick_diagnostics(_tick_rows(), market_calendar=calendar_path)
    chain_result = chain_diagnostics(_chain_rows(), market_calendar=calendar_path)
    tick_summary = tick_result.summary.iloc[0]
    chain_summary = chain_result.summary.loc[
        chain_result.summary["scope"] == "overall"
    ].iloc[0]

    for summary in (tick_summary, chain_summary):
        assert bool(summary["market_calendar_provided"])
        assert summary["market_calendar_id"] == "nse-fo-test-2026-06"
        assert summary["market_calendar_sha256"] == file_sha256(calendar_path)
        assert int(summary["non_trading_day_rows"]) == 3
        assert int(summary["calendar_closed_rows"]) == 1
        assert int(summary["calendar_out_of_range_rows"]) == 1
        assert int(summary["out_of_session_rows"]) == 1
    assert set(tick_result.issues["issue"]) == {
        "calendar_closed",
        "calendar_out_of_range",
        "non_trading_day",
        "out_of_session",
    }
    assert set(chain_result.issues["issue"]) == set(tick_result.issues["issue"])


def test_calendar_loader_rejects_market_timezone_and_open_session_drift(tmp_path):
    calendar_path = _calendar_path(tmp_path)
    payload = json.loads(calendar_path.read_text(encoding="utf-8"))

    payload["market"] = "us_equities_regular"
    calendar_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        load_market_calendar(calendar_path, expected_market=MARKET)

    payload["market"] = MARKET
    payload["sessions"][1].pop("close_time")
    calendar_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="require open_time and close_time"):
        load_market_calendar(calendar_path)

    payload = json.loads(_calendar_path(tmp_path).read_text(encoding="utf-8"))
    payload["schema_version"] = True
    calendar_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_market_calendar(calendar_path)


def test_market_calendar_report_binds_source_fingerprint(tmp_path):
    calendar_path = _calendar_path(tmp_path)
    output_dir = tmp_path / "calendar_report"

    report = write_market_calendar_report(
        calendar_path,
        output_dir,
        expected_market=MARKET,
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report.ready
    assert report.summary.iloc[0]["market_calendar_sha256"] == file_sha256(
        calendar_path
    )
    assert manifest["extra"]["non_authorizing"] is True
    assert manifest["inputs"]["market_calendar"]["sha256"] == file_sha256(
        calendar_path
    )
    integrity = verify_experiment_manifest(
        output_dir / "manifest.json",
        expected_run_type="market_calendar_report",
        require_input_fingerprints=True,
    )
    assert integrity.passed


def test_market_calendar_cli_writes_report(tmp_path):
    calendar_path = _calendar_path(tmp_path)
    output_dir = tmp_path / "calendar_cli"

    code = main(
        [
            "market-calendar-report",
            "--calendar",
            str(calendar_path),
            "--market",
            MARKET,
            "--out",
            str(output_dir),
        ]
    )

    assert code == 0
    summary = pd.read_csv(output_dir / "market_calendar_summary.csv")
    assert summary.loc[0, "market_calendar_id"] == "nse-fo-test-2026-06"


def test_mapped_normalization_manifest_detects_calendar_drift(tmp_path):
    calendar_path = _calendar_path(tmp_path)
    input_path = tmp_path / "ticks.csv"
    mapping_path = tmp_path / "mapping.csv"
    output_dir = tmp_path / "mapped"
    ticks = _tick_rows().iloc[[0]].copy()
    ticks["last"] = 100.05
    ticks["last_qty"] = 75
    ticks.to_csv(input_path, index=False)
    pd.DataFrame(
        [
            {"normalized_column": column, "source_column": column}
            for column in (
                "ts",
                "bid",
                "ask",
                "bid_qty",
                "ask_qty",
                "last",
                "last_qty",
            )
        ]
    ).to_csv(mapping_path, index=False)

    report = write_mapped_data_normalization(
        input_path,
        mapping_path,
        output_dir=output_dir,
        config=MappedDataConfig(
            adapter="normalized",
            kind="ticks",
            market_calendar_path=str(calendar_path),
        ),
    )

    assert report.ready
    assert report.summary.iloc[0]["market_calendar_sha256"] == file_sha256(
        calendar_path
    )
    current = verify_experiment_manifest(
        output_dir / "manifest.json",
        expected_run_type="mapped_data_normalization",
        require_input_fingerprints=True,
    )
    assert current.passed

    calendar_path.write_text(
        calendar_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    drifted = verify_experiment_manifest(
        output_dir / "manifest.json",
        expected_run_type="mapped_data_normalization",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"
