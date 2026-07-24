import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from adapters.nse_market_calendar import (
    NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA,
    NSE_SESSION_SOURCE_COLUMNS,
    normalize_nse_fo_holiday_snapshot,
)
from hft_cli import main
from reports.data_readiness import (
    DataReadinessThresholds,
    verify_data_readiness_report,
    write_data_readiness_report,
)
from reports.manifest import file_sha256
from reports.market_calendar import (
    verify_market_calendar_report,
    write_market_calendar_from_sessions,
)


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "data"
    / "calendars"
    / "nse_holiday_master_trading_2026-07-23.json"
)
SESSIONS = (
    ROOT
    / "data"
    / "calendars"
    / "nse_fo_2026_h1_sessions.csv"
)
MARKET = "india_nse_index_derivatives"
CALENDAR_ID = "nse-fo-2026-h1-api-20260723-v1"
SOURCE_URL = (
    "https://www.nseindia.com/api/holiday-master?type=trading"
)


def _build(output, *, snapshot=SNAPSHOT, sessions=SESSIONS):
    return write_market_calendar_from_sessions(
        sessions,
        output,
        calendar_id=CALENDAR_ID,
        market=MARKET,
        valid_from="2026-01-01",
        valid_to="2026-06-30",
        publisher="National Stock Exchange of India Limited",
        source_url=SOURCE_URL,
        published_date="2026-01-12",
        authority_source_path=snapshot,
        authority_source_schema=NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA,
    )


def test_tracked_nse_fo_h1_snapshot_normalizes_to_sessions():
    normalized = normalize_nse_fo_holiday_snapshot(
        SNAPSHOT,
        valid_from="2026-01-01",
        valid_to="2026-06-30",
    )
    actual = pd.read_csv(
        SESSIONS,
        dtype=str,
        keep_default_na=False,
    )
    expected = [
        {
            column: row.get(column, "")
            for column in NSE_SESSION_SOURCE_COLUMNS
        }
        for row in normalized.sessions
    ]

    assert file_sha256(SNAPSHOT) == (
        "798c545acc5351eb9ed84f353c1fcc665a26967426e3761b7097e7f3c7042424"
    )
    assert tuple(actual.columns) == NSE_SESSION_SOURCE_COLUMNS
    assert actual.to_dict(orient="records") == expected
    assert normalized.source_rows == 20
    assert normalized.selected_rows == 12
    assert normalized.skipped_weekend_rows == 2
    assert actual["date"].tolist()[0] == "2026-01-15"
    assert len(actual) == 10


def test_authority_bound_nse_calendar_builds_and_verifies(tmp_path):
    output = tmp_path / "calendar"

    report = _build(output)

    summary = report.summary.iloc[0]
    payload = json.loads(
        (output / "market_calendar.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (output / "manifest.json").read_text(encoding="utf-8")
    )
    assert report.ready
    assert summary["market_calendar_id"] == CALENDAR_ID
    assert int(summary["closed_dates"]) == 10
    assert bool(summary["authority_source_bound"])
    assert (
        summary["authority_source_schema"]
        == NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA
    )
    assert int(summary["authority_source_rows"]) == 20
    assert int(summary["authority_selected_rows"]) == 12
    assert int(summary["authority_skipped_weekend_rows"]) == 2
    assert (
        payload["provenance"]["authority_source_file_sha256"]
        == file_sha256(SNAPSHOT)
    )
    assert set(manifest["inputs"]) == {
        "market_calendar_authority_source",
        "market_calendar_sessions_source",
    }
    verification = verify_market_calendar_report(output)
    assert verification.verified
    assert verification.ready
    assert verification.source_current
    assert verification.authority_source_current
    assert verification.authority_source_path == SNAPSHOT.resolve()


def test_authority_bound_calendar_detects_snapshot_drift(tmp_path):
    snapshot = tmp_path / SNAPSHOT.name
    shutil.copy2(SNAPSHOT, snapshot)
    output = tmp_path / "calendar"
    _build(output, snapshot=snapshot)

    snapshot.write_text(
        snapshot.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    verification = verify_market_calendar_report(output)
    assert not verification.verified
    assert not verification.ready
    assert not verification.manifest_current
    assert not verification.source_current
    assert not verification.authority_source_current
    assert verification.error == "input_drift"


def test_authority_bound_calendar_requires_manifested_snapshot(tmp_path):
    output = tmp_path / "calendar"
    _build(output)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["inputs"].pop("market_calendar_authority_source")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verification = verify_market_calendar_report(output)
    assert not verification.verified
    assert not verification.ready
    assert verification.manifest_current
    assert not verification.source_current
    assert not verification.authority_source_current
    assert (
        verification.error
        == "market-calendar manifest lacks the "
        "market_calendar_authority_source file input"
    )


def test_data_readiness_rechecks_bound_nse_authority_source(tmp_path):
    snapshot = tmp_path / SNAPSHOT.name
    shutil.copy2(SNAPSHOT, snapshot)
    calendar_output = tmp_path / "calendar"
    _build(calendar_output, snapshot=snapshot)
    readiness_output = tmp_path / "readiness"
    readiness = write_data_readiness_report(
        output_dir=readiness_output,
        market_calendar_dir=calendar_output,
        thresholds=DataReadinessThresholds(
            require_market_calendar=True,
            require_tick_diagnostics=False,
        ),
    )
    assert readiness.ready
    assert verify_data_readiness_report(readiness_output).verified

    snapshot.write_text(
        snapshot.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    verification = verify_data_readiness_report(readiness_output)
    assert not verification.verified
    assert not verification.ready
    assert not verification.artifacts_consistent


def test_authority_binding_rejects_missing_amendment_row(tmp_path):
    sessions = tmp_path / "sessions.csv"
    frame = pd.read_csv(SESSIONS, dtype=str, keep_default_na=False)
    frame.loc[frame["date"] != "2026-01-15"].to_csv(
        sessions,
        index=False,
    )
    output = tmp_path / "calendar"

    with pytest.raises(
        ValueError,
        match="does not match the authority source normalization",
    ):
        _build(output, sessions=sessions)

    assert not output.exists()


def test_nse_normalizer_blocks_unresolved_muhurat_session():
    with pytest.raises(
        ValueError,
        match="does not provide its open and close times",
    ):
        normalize_nse_fo_holiday_snapshot(
            SNAPSHOT,
            valid_from="2026-01-01",
            valid_to="2026-12-31",
        )


def test_market_calendar_cli_accepts_nse_authority_source(tmp_path):
    output = tmp_path / "calendar"

    code = main(
        [
            "build-market-calendar",
            "--sessions",
            str(SESSIONS),
            "--authority-source",
            str(SNAPSHOT),
            "--authority-source-schema",
            NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA,
            "--calendar-id",
            CALENDAR_ID,
            "--market",
            MARKET,
            "--valid-from",
            "2026-01-01",
            "--valid-to",
            "2026-06-30",
            "--publisher",
            "National Stock Exchange of India Limited",
            "--source-url",
            SOURCE_URL,
            "--published-date",
            "2026-01-12",
            "--out",
            str(output),
        ]
    )

    assert code == 0
    assert verify_market_calendar_report(output).verified
