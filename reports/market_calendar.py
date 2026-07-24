from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import pandas as pd

from adapters.nse_market_calendar import (
    NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA,
    NseHolidayNormalization,
    normalize_nse_fo_holiday_snapshot,
)
from markets.calendars import (
    MARKET_CALENDAR_POLICY,
    MarketCalendar,
    load_market_calendar,
    market_calendar_summary,
    resolve_market_calendar,
)
from markets.profiles import get_market_profile
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


MARKET_CALENDAR_REPORT_RUN_TYPE = "market_calendar_report"
MARKET_CALENDAR_FILE = "market_calendar.json"
MARKET_CALENDAR_SESSIONS_FILE = "market_calendar_sessions.csv"
MARKET_CALENDAR_CHECKS_FILE = "market_calendar_checks.csv"
MARKET_CALENDAR_SUMMARY_FILE = "market_calendar_summary.csv"
MARKET_CALENDAR_RUNBOOK_FILE = "market_calendar_runbook.md"
MARKET_CALENDAR_REPORT_ARTIFACTS = (
    MARKET_CALENDAR_SESSIONS_FILE,
    MARKET_CALENDAR_CHECKS_FILE,
    MARKET_CALENDAR_SUMMARY_FILE,
    MARKET_CALENDAR_RUNBOOK_FILE,
)
MARKET_CALENDAR_SESSION_SOURCE_SCHEMA = "market_calendar_sessions_csv_v1"
MARKET_CALENDAR_SESSION_SOURCE_COLUMNS = (
    "date",
    "status",
    "open_time",
    "close_time",
    "label",
)


@dataclass(frozen=True)
class MarketCalendarReport:
    sessions: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and self.summary.iloc[0].get("ready", False)
        )


@dataclass(frozen=True)
class MarketCalendarReportVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    source_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    manifest_path: Path
    source_path: Path | None = None
    authority_source_path: Path | None = None
    authority_source_current: bool = False
    compiled_from_sessions: bool = False
    error: str = ""


@dataclass(frozen=True)
class _CompiledCalendarDocument:
    text: str
    source_sha256: str
    source_rows: int
    market: str
    timezone: str
    authority_source_schema: str = ""
    authority_source_sha256: str = ""
    authority_source_rows: int = 0
    authority_selected_rows: int = 0
    authority_skipped_weekend_rows: int = 0


def build_market_calendar_report(
    calendar_path: str | Path,
    *,
    expected_market: str | None = None,
) -> MarketCalendarReport:
    calendar = (
        resolve_market_calendar(calendar_path, market=expected_market)
        if expected_market
        else load_market_calendar(calendar_path)
    )
    if calendar is None:
        raise ValueError("market calendar is required")
    return _build_report(calendar)


def _build_report(calendar: MarketCalendar) -> MarketCalendarReport:
    sessions = _session_rows(calendar)
    checks = _checks(calendar)
    summary = _summary(calendar, checks)
    return MarketCalendarReport(sessions=sessions, checks=checks, summary=summary)


def write_market_calendar_report(
    calendar_path: str | Path,
    output_dir: str | Path,
    *,
    expected_market: str | None = None,
) -> MarketCalendarReport:
    report = build_market_calendar_report(
        calendar_path,
        expected_market=expected_market,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write_report_artifacts(report, out)
    write_experiment_manifest(
        out,
        run_type=MARKET_CALENDAR_REPORT_RUN_TYPE,
        parameters={"expected_market": expected_market or ""},
        inputs={"market_calendar": Path(calendar_path)},
        extra=_report_manifest_extra(report),
    )
    return MarketCalendarReport(
        sessions=report.sessions,
        checks=report.checks,
        summary=report.summary,
        output_dir=out,
    )


def write_market_calendar_from_sessions(
    sessions_path: str | Path,
    output_dir: str | Path,
    *,
    calendar_id: str,
    market: str,
    valid_from: str,
    valid_to: str,
    publisher: str,
    source_url: str,
    published_date: str,
    authority_source_path: str | Path | None = None,
    authority_source_schema: str = "",
) -> MarketCalendarReport:
    source = Path(sessions_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(
            f"market calendar sessions source not found: {source}"
        )
    out = Path(output_dir).resolve()
    try:
        source.relative_to(out)
    except ValueError:
        pass
    else:
        raise ValueError(
            "market calendar output must not contain the source sessions file"
        )
    authority_source = _optional_authority_source(
        authority_source_path,
        authority_source_schema=authority_source_schema,
        output_dir=out,
    )

    document = _compiled_calendar_document(
        source,
        calendar_id=calendar_id,
        market=market,
        valid_from=valid_from,
        valid_to=valid_to,
        publisher=publisher,
        source_url=source_url,
        published_date=published_date,
        authority_source=authority_source,
        authority_source_schema=authority_source_schema,
    )
    with TemporaryDirectory(prefix="market-calendar-") as temp_dir:
        validation_path = Path(temp_dir) / MARKET_CALENDAR_FILE
        validation_path.write_text(document.text, encoding="utf-8")
        load_market_calendar(
            validation_path,
            expected_market=document.market,
            expected_timezone=document.timezone,
        )
    out.mkdir(parents=True, exist_ok=True)
    calendar_path = out / MARKET_CALENDAR_FILE
    calendar_path.write_text(document.text, encoding="utf-8")
    calendar = load_market_calendar(
        calendar_path,
        expected_market=document.market,
        expected_timezone=document.timezone,
    )
    base_report = _build_report(calendar)
    report = _compiled_report(
        base_report,
        source=source,
        document=document,
        authority_source=authority_source,
    )
    _write_report_artifacts(report, out)
    parameters = _compiled_parameters(
        calendar_id=calendar_id,
        market=document.market,
        timezone=document.timezone,
        valid_from=valid_from,
        valid_to=valid_to,
        publisher=publisher,
        source_url=source_url,
        published_date=published_date,
        authority_source_schema=authority_source_schema,
    )
    inputs: dict[str, Path] = {
        "market_calendar_sessions_source": source,
    }
    if authority_source is not None:
        inputs["market_calendar_authority_source"] = authority_source
    write_experiment_manifest(
        out,
        run_type=MARKET_CALENDAR_REPORT_RUN_TYPE,
        parameters=parameters,
        inputs=inputs,
        extra=_compiled_manifest_extra(report, document),
    )
    return MarketCalendarReport(
        sessions=report.sessions,
        checks=report.checks,
        summary=report.summary,
        output_dir=out,
    )


def verify_market_calendar_report(
    report_dir: str | Path,
) -> MarketCalendarReportVerification:
    requested = Path(report_dir)
    root = requested.parent if requested.is_file() else requested
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    source_path: Path | None = None
    authority_source_path: Path | None = None
    authority_source_current = False
    source_current = False
    compiled_from_sessions = False
    required_artifacts = MARKET_CALENDAR_REPORT_ARTIFACTS
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=MARKET_CALENDAR_REPORT_RUN_TYPE,
        required_artifacts=required_artifacts,
        require_input_fingerprints=True,
    )
    try:
        manifest = _read_json_object(
            manifest_path,
            "market-calendar report manifest",
        )
        parameters = _mapping(manifest.get("parameters"))
        inputs = _mapping(manifest.get("inputs"))
        compiled_from_sessions = (
            parameters.get("compiled_from_sessions") is True
        )
        if compiled_from_sessions:
            required_artifacts = (
                *MARKET_CALENDAR_REPORT_ARTIFACTS,
                MARKET_CALENDAR_FILE,
            )
            source_path = _manifest_file_input(
                inputs,
                "market_calendar_sessions_source",
            )
            source_current = _manifest_file_input_current(
                inputs,
                "market_calendar_sessions_source",
                source_path,
            )
            expected_parameters = _compiled_parameters_from_manifest(parameters)
            authority_source_schema = str(
                expected_parameters.get("authority_source_schema", "")
            )
            if authority_source_schema:
                source_current = False
                authority_source_path = _manifest_file_input(
                    inputs,
                    "market_calendar_authority_source",
                )
                authority_source_current = _manifest_file_input_current(
                    inputs,
                    "market_calendar_authority_source",
                    authority_source_path,
                )
                source_current = bool(
                    source_current and authority_source_current
                )
            document = _compiled_calendar_document(
                source_path,
                calendar_id=str(expected_parameters["calendar_id"]),
                market=str(expected_parameters["market"]),
                valid_from=str(expected_parameters["valid_from"]),
                valid_to=str(expected_parameters["valid_to"]),
                publisher=str(expected_parameters["publisher"]),
                source_url=str(expected_parameters["source_url"]),
                published_date=str(expected_parameters["published_date"]),
                authority_source=authority_source_path,
                authority_source_schema=authority_source_schema,
            )
            calendar_path = root / MARKET_CALENDAR_FILE
            if calendar_path.read_text(encoding="utf-8") != document.text:
                raise ValueError(
                    "generated market calendar does not match the session source"
                )
            calendar = load_market_calendar(
                calendar_path,
                expected_market=document.market,
                expected_timezone=document.timezone,
            )
            expected_report = _compiled_report(
                _build_report(calendar),
                source=source_path,
                document=document,
                authority_source=authority_source_path,
            )
            expected_extra = _compiled_manifest_extra(
                expected_report,
                document,
            )
            expected_input_name = "market_calendar_sessions_source"
            expected_inputs = {
                expected_input_name: source_path,
                **(
                    {
                        "market_calendar_authority_source": (
                            authority_source_path
                        )
                    }
                    if authority_source_path is not None
                    else {}
                ),
            }
        else:
            expected_parameters = _report_parameters_from_manifest(parameters)
            source_path = _manifest_file_input(inputs, "market_calendar")
            source_current = _manifest_file_input_current(
                inputs,
                "market_calendar",
                source_path,
            )
            expected_market = str(expected_parameters["expected_market"])
            expected_report = build_market_calendar_report(
                source_path,
                expected_market=expected_market or None,
            )
            expected_extra = _report_manifest_extra(expected_report)
            expected_input_name = "market_calendar"
            expected_inputs = {expected_input_name: source_path}

        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type=MARKET_CALENDAR_REPORT_RUN_TYPE,
            required_artifacts=required_artifacts,
            require_input_fingerprints=True,
        )
        source_current = all(
            _manifest_file_input_current(inputs, name, path)
            for name, path in expected_inputs.items()
        )
        artifacts_consistent = bool(
            _report_artifacts_consistent(root, expected_report)
            and _mapping(manifest.get("parameters")) == expected_parameters
            and _mapping(manifest.get("extra")) == expected_extra
            and _manifest_input_contract_current(inputs, expected_inputs)
        )
        actual_summary = _read_csv_frame(
            root / MARKET_CALENDAR_SUMMARY_FILE,
            "market-calendar summary",
        )
        non_authorizing = bool(
            len(actual_summary) == 1
            and _truthy(actual_summary.iloc[0].get("non_authorizing", False))
            and _mapping(manifest.get("extra")).get("non_authorizing") is True
        )
        ready = bool(expected_report.ready)
        verified = bool(
            integrity.passed
            and source_current
            and artifacts_consistent
            and non_authorizing
        )
        return MarketCalendarReportVerification(
            verified=verified,
            ready=bool(verified and ready),
            manifest_current=integrity.passed,
            source_current=source_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            source_path=source_path,
            authority_source_path=authority_source_path,
            authority_source_current=authority_source_current,
            compiled_from_sessions=compiled_from_sessions,
            error=""
            if verified
            else (
                integrity.error
                or "market-calendar report semantic verification failed"
            ),
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return MarketCalendarReportVerification(
            verified=False,
            ready=False,
            manifest_current=integrity.passed,
            source_current=source_current,
            artifacts_consistent=False,
            non_authorizing=False,
            output_dir=root,
            manifest_path=manifest_path,
            source_path=source_path,
            authority_source_path=authority_source_path,
            authority_source_current=authority_source_current,
            compiled_from_sessions=compiled_from_sessions,
            error=integrity.error or str(exc),
        )


def _compiled_calendar_document(
    source: Path,
    *,
    calendar_id: str,
    market: str,
    valid_from: str,
    valid_to: str,
    publisher: str,
    source_url: str,
    published_date: str,
    authority_source: Path | None = None,
    authority_source_schema: str = "",
) -> _CompiledCalendarDocument:
    source_rows = _read_session_source(source)
    source_sha256 = file_sha256(source)
    authority = _authority_normalization(
        authority_source,
        authority_source_schema=authority_source_schema,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    if (
        authority is not None
        and source_rows != list(authority.sessions)
    ):
        raise ValueError(
            "market calendar sessions CSV does not match the "
            "authority source normalization"
        )
    profile = get_market_profile(market)
    authority_provenance: dict[str, object] = {}
    authority_sha256 = ""
    if authority_source is not None and authority is not None:
        authority_sha256 = file_sha256(authority_source)
        authority_provenance = {
            "authority_source_schema": authority_source_schema,
            "authority_source_file_name": authority_source.name,
            "authority_source_file_sha256": authority_sha256,
            "authority_source_rows": authority.source_rows,
            "authority_selected_rows": authority.selected_rows,
            "authority_skipped_weekend_rows": (
                authority.skipped_weekend_rows
            ),
        }
    payload = {
        "schema_version": 1,
        "calendar_id": calendar_id,
        "market": profile.name,
        "timezone": profile.session.timezone,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "provenance": {
            "publisher": publisher,
            "source_url": source_url,
            "published_date": published_date,
            "source_schema": MARKET_CALENDAR_SESSION_SOURCE_SCHEMA,
            "source_file_name": source.name,
            "source_file_sha256": source_sha256,
            **authority_provenance,
        },
        "sessions": sorted(source_rows, key=lambda row: row["date"]),
    }
    return _CompiledCalendarDocument(
        text=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        source_sha256=source_sha256,
        source_rows=len(source_rows),
        market=profile.name,
        timezone=profile.session.timezone,
        authority_source_schema=authority_source_schema,
        authority_source_sha256=authority_sha256,
        authority_source_rows=(
            authority.source_rows if authority is not None else 0
        ),
        authority_selected_rows=(
            authority.selected_rows if authority is not None else 0
        ),
        authority_skipped_weekend_rows=(
            authority.skipped_weekend_rows
            if authority is not None
            else 0
        ),
    )


def _compiled_report(
    base_report: MarketCalendarReport,
    *,
    source: Path,
    document: _CompiledCalendarDocument,
    authority_source: Path | None = None,
) -> MarketCalendarReport:
    summary = base_report.summary.assign(
        compiled_from_sessions=True,
        session_source_schema=MARKET_CALENDAR_SESSION_SOURCE_SCHEMA,
        session_source_path=str(source),
        session_source_sha256=document.source_sha256,
        session_source_rows=document.source_rows,
    )
    if document.authority_source_schema:
        if authority_source is None:
            raise ValueError(
                "compiled market calendar lacks its authority source"
            )
        summary = summary.assign(
            authority_source_bound=True,
            authority_source_schema=document.authority_source_schema,
            authority_source_path=str(authority_source),
            authority_source_sha256=document.authority_source_sha256,
            authority_source_rows=document.authority_source_rows,
            authority_selected_rows=document.authority_selected_rows,
            authority_skipped_weekend_rows=(
                document.authority_skipped_weekend_rows
            ),
        )
    return MarketCalendarReport(
        sessions=base_report.sessions,
        checks=base_report.checks,
        summary=summary,
    )


def _compiled_parameters(
    *,
    calendar_id: str,
    market: str,
    timezone: str,
    valid_from: str,
    valid_to: str,
    publisher: str,
    source_url: str,
    published_date: str,
    authority_source_schema: str = "",
) -> dict[str, object]:
    parameters: dict[str, object] = {
        "compiled_from_sessions": True,
        "session_source_schema": MARKET_CALENDAR_SESSION_SOURCE_SCHEMA,
        "calendar_id": calendar_id,
        "market": market,
        "timezone": timezone,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "publisher": publisher,
        "source_url": source_url,
        "published_date": published_date,
    }
    if authority_source_schema:
        parameters.update(
            {
                "authority_source_bound": True,
                "authority_source_schema": authority_source_schema,
            }
        )
    return parameters


def _compiled_parameters_from_manifest(
    parameters: Mapping[str, Any],
) -> dict[str, object]:
    base_fields = {
        "compiled_from_sessions",
        "session_source_schema",
        "calendar_id",
        "market",
        "timezone",
        "valid_from",
        "valid_to",
        "publisher",
        "source_url",
        "published_date",
    }
    authority_fields = {
        "authority_source_bound",
        "authority_source_schema",
    }
    if set(parameters) not in {
        frozenset(base_fields),
        frozenset(base_fields | authority_fields),
    }:
        raise ValueError(
            "compiled market-calendar manifest parameters are incomplete"
        )
    if parameters.get("compiled_from_sessions") is not True:
        raise ValueError(
            "compiled market-calendar manifest flag must be true"
        )
    if (
        parameters.get("session_source_schema")
        != MARKET_CALENDAR_SESSION_SOURCE_SCHEMA
    ):
        raise ValueError(
            "compiled market-calendar session source schema is invalid"
        )
    authority_source_schema = ""
    if authority_fields <= set(parameters):
        if parameters.get("authority_source_bound") is not True:
            raise ValueError(
                "compiled market-calendar authority source flag must be true"
            )
        authority_source_schema = str(
            parameters.get("authority_source_schema", "")
        )
        if authority_source_schema != NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA:
            raise ValueError(
                "compiled market-calendar authority source schema is invalid"
            )
    expected = _compiled_parameters(
        calendar_id=str(parameters["calendar_id"]),
        market=str(parameters["market"]),
        timezone=str(parameters["timezone"]),
        valid_from=str(parameters["valid_from"]),
        valid_to=str(parameters["valid_to"]),
        publisher=str(parameters["publisher"]),
        source_url=str(parameters["source_url"]),
        published_date=str(parameters["published_date"]),
        authority_source_schema=authority_source_schema,
    )
    profile = get_market_profile(str(expected["market"]))
    if expected["market"] != profile.name:
        raise ValueError("compiled market-calendar market is not canonical")
    if expected["timezone"] != profile.session.timezone:
        raise ValueError(
            "compiled market-calendar timezone does not match its market profile"
        )
    return expected


def _report_parameters_from_manifest(
    parameters: Mapping[str, Any],
) -> dict[str, object]:
    if set(parameters) != {"expected_market"}:
        raise ValueError(
            "market-calendar report manifest parameters are invalid"
        )
    value = parameters.get("expected_market")
    if not isinstance(value, str):
        raise ValueError(
            "market-calendar report expected_market must be text"
        )
    return {"expected_market": value}


def _report_manifest_extra(
    report: MarketCalendarReport,
) -> dict[str, object]:
    row = report.summary.iloc[0]
    return {
        "ready": report.ready,
        "market": str(row["market"]),
        "calendar_id": str(row["market_calendar_id"]),
        "market_calendar_sha256": str(row["market_calendar_sha256"]),
        "non_authorizing": True,
    }


def _compiled_manifest_extra(
    report: MarketCalendarReport,
    document: _CompiledCalendarDocument,
) -> dict[str, object]:
    row = report.summary.iloc[0]
    extra: dict[str, object] = {
        "ready": report.ready,
        "market": document.market,
        "calendar_id": str(row["market_calendar_id"]),
        "market_calendar_sha256": str(row["market_calendar_sha256"]),
        "session_source_sha256": document.source_sha256,
        "compiled_from_sessions": True,
        "non_authorizing": True,
    }
    if document.authority_source_schema:
        extra.update(
            {
                "authority_source_bound": True,
                "authority_source_schema": (
                    document.authority_source_schema
                ),
                "authority_source_sha256": (
                    document.authority_source_sha256
                ),
            }
        )
    return extra


def _report_artifacts_consistent(
    root: Path,
    expected: MarketCalendarReport,
) -> bool:
    return bool(
        _csv_frame_matches(
            root / MARKET_CALENDAR_SESSIONS_FILE,
            expected.sessions,
        )
        and _csv_frame_matches(
            root / MARKET_CALENDAR_CHECKS_FILE,
            expected.checks,
        )
        and _csv_frame_matches(
            root / MARKET_CALENDAR_SUMMARY_FILE,
            expected.summary,
        )
        and (root / MARKET_CALENDAR_RUNBOOK_FILE).read_text(
            encoding="utf-8"
        )
        == _runbook(expected.summary.iloc[0], expected.sessions)
    )


def _csv_frame_matches(path: Path, expected: pd.DataFrame) -> bool:
    actual = _read_csv_frame(path, path.name)
    expected_roundtrip = pd.read_csv(
        StringIO(expected.to_csv(index=False)),
        keep_default_na=False,
    )
    return bool(
        list(actual.columns) == list(expected_roundtrip.columns)
        and actual.to_dict(orient="records")
        == expected_roundtrip.to_dict(orient="records")
    )


def _read_csv_frame(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, keep_default_na=False)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _manifest_file_input(
    inputs: Mapping[str, Any],
    name: str,
) -> Path:
    value = _mapping(inputs.get(name))
    if value.get("kind") != "file" or not value.get("path"):
        raise ValueError(
            f"market-calendar manifest lacks the {name} file input"
        )
    return Path(str(value["path"])).resolve()


def _manifest_file_input_current(
    inputs: Mapping[str, Any],
    name: str,
    source: Path,
) -> bool:
    value = _mapping(inputs.get(name))
    try:
        return bool(
            source.is_file()
            and value.get("kind") == "file"
            and Path(str(value.get("path", ""))).resolve() == source
            and int(value.get("size_bytes", -1)) == int(source.stat().st_size)
            and str(value.get("sha256", "")) == file_sha256(source)
        )
    except (OSError, TypeError, ValueError):
        return False


def _manifest_input_contract_current(
    inputs: Mapping[str, Any],
    expected: Mapping[str, Path],
) -> bool:
    return bool(
        set(inputs) == set(expected)
        and all(
            _manifest_file_input_current(inputs, name, source)
            for name, source in expected.items()
        )
    )


def _optional_authority_source(
    value: str | Path | None,
    *,
    authority_source_schema: str,
    output_dir: Path,
) -> Path | None:
    schema = authority_source_schema.strip()
    if value is None or (isinstance(value, str) and not value.strip()):
        if schema:
            raise ValueError(
                "market calendar authority source is required when its "
                "schema is supplied"
            )
        return None
    if not schema:
        raise ValueError(
            "market calendar authority source schema is required"
        )
    if schema != NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA:
        raise ValueError(
            "market calendar authority source schema is unsupported"
        )
    source = Path(value).resolve()
    if not source.is_file():
        raise FileNotFoundError(
            f"market calendar authority source not found: {source}"
        )
    try:
        source.relative_to(output_dir)
    except ValueError:
        return source
    raise ValueError(
        "market calendar output must not contain the authority source"
    )


def _authority_normalization(
    authority_source: Path | None,
    *,
    authority_source_schema: str,
    valid_from: str,
    valid_to: str,
) -> NseHolidayNormalization | None:
    if authority_source is None:
        if authority_source_schema:
            raise ValueError(
                "market calendar authority source is required"
            )
        return None
    if authority_source_schema != NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA:
        raise ValueError(
            "market calendar authority source schema is unsupported"
        )
    return normalize_nse_fo_holiday_snapshot(
        authority_source,
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _read_session_source(path: Path) -> list[dict[str, str]]:
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
    except (OSError, ValueError, pd.errors.EmptyDataError) as exc:
        raise ValueError(
            f"market calendar sessions CSV is invalid: {exc}"
        ) from exc
    actual_columns = tuple(str(column) for column in frame.columns)
    if actual_columns != MARKET_CALENDAR_SESSION_SOURCE_COLUMNS:
        raise ValueError(
            "market calendar sessions CSV columns must be exactly "
            + ",".join(MARKET_CALENDAR_SESSION_SOURCE_COLUMNS)
        )
    rows: list[dict[str, str]] = []
    for row_number, row in enumerate(
        frame.to_dict(orient="records"),
        start=2,
    ):
        normalized = {
            column: str(row.get(column, "")).strip()
            for column in MARKET_CALENDAR_SESSION_SOURCE_COLUMNS
        }
        if not normalized["date"]:
            raise ValueError(
                f"market calendar sessions CSV row {row_number} date is required"
            )
        if not normalized["status"]:
            raise ValueError(
                f"market calendar sessions CSV row {row_number} status is required"
            )
        normalized["status"] = normalized["status"].lower()
        rows.append({key: value for key, value in normalized.items() if value})
    return rows


def _write_report_artifacts(
    report: MarketCalendarReport,
    output_dir: Path,
) -> None:
    report.sessions.to_csv(
        output_dir / MARKET_CALENDAR_SESSIONS_FILE,
        index=False,
    )
    report.checks.to_csv(
        output_dir / MARKET_CALENDAR_CHECKS_FILE,
        index=False,
    )
    report.summary.to_csv(
        output_dir / MARKET_CALENDAR_SUMMARY_FILE,
        index=False,
    )
    (output_dir / MARKET_CALENDAR_RUNBOOK_FILE).write_text(
        _runbook(report.summary.iloc[0], report.sessions),
        encoding="utf-8",
    )


def _session_rows(calendar: MarketCalendar) -> pd.DataFrame:
    rows = [
        {
            "date": session.trade_date.isoformat(),
            "status": session.status,
            "open_time": _hhmmss(session.open_seconds),
            "close_time": _hhmmss(session.close_seconds),
            "weekday": session.trade_date.strftime("%a"),
            "weekend": session.trade_date.weekday() >= 5,
            "label": session.label,
        }
        for session in calendar.sessions
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "status",
            "open_time",
            "close_time",
            "weekday",
            "weekend",
            "label",
        ],
    )


def _checks(calendar: MarketCalendar) -> pd.DataFrame:
    rows = [
        _check(
            "calendar_coverage",
            calendar.valid_to.isoformat(),
            ">=",
            calendar.valid_from.isoformat(),
            calendar.valid_to >= calendar.valid_from,
            "calendar coverage must be nonempty",
        ),
        _check(
            "calendar_market",
            calendar.market,
            "is_not",
            "",
            bool(calendar.market),
            "calendar market is required",
        ),
        _check(
            "calendar_timezone",
            calendar.timezone,
            "is_not",
            "",
            bool(calendar.timezone),
            "calendar timezone is required",
        ),
        _check(
            "calendar_provenance",
            f"{calendar.publisher}|{calendar.source_url}",
            "has",
            "publisher_and_source_url",
            bool(calendar.publisher and calendar.source_url),
            "calendar publisher and source URL are required",
        ),
        _check(
            "calendar_source_sha256",
            calendar.source_sha256,
            "length",
            64,
            len(calendar.source_sha256) == 64,
            "calendar source must be fingerprinted",
        ),
    ]
    return pd.DataFrame(rows)


def _summary(calendar: MarketCalendar, checks: pd.DataFrame) -> pd.DataFrame:
    metadata = market_calendar_summary(calendar)
    closed = len(calendar.closed_dates)
    special = len(calendar.special_open_dates)
    weekend_specials = sum(day.weekday() >= 5 for day in calendar.special_open_dates)
    return pd.DataFrame(
        [
            {
                "ready": bool(checks["passed"].astype(bool).all()),
                "market": calendar.market,
                "timezone": calendar.timezone,
                "trading_day_policy": MARKET_CALENDAR_POLICY,
                "coverage_days": int(
                    (calendar.valid_to - calendar.valid_from).days + 1
                ),
                "calendar_overrides": len(calendar.sessions),
                "closed_dates": closed,
                "special_open_dates": special,
                "weekend_special_open_dates": weekend_specials,
                "failed_checks": int((~checks["passed"].astype(bool)).sum()),
                "non_authorizing": True,
                **metadata,
            }
        ]
    )


def _check(
    check: str,
    observed: object,
    operator: str,
    expected: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": check,
        "observed": observed,
        "operator": operator,
        "expected": expected,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _runbook(summary: pd.Series, sessions: pd.DataFrame) -> str:
    lines = [
        "# Market Calendar Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Market: `{summary['market']}`",
        f"- Calendar ID: `{summary['market_calendar_id']}`",
        f"- Coverage: `{summary['market_calendar_valid_from']}` to `{summary['market_calendar_valid_to']}`",
        f"- Publisher: `{summary['market_calendar_publisher']}`",
        f"- Source URL: `{summary['market_calendar_source_url']}`",
        f"- Source SHA-256: `{summary['market_calendar_sha256']}`",
        f"- Closed dates: {int(summary['closed_dates'])}",
        f"- Special open dates: {int(summary['special_open_dates'])}",
        *(
            [
                f"- Session source schema: `{summary['session_source_schema']}`",
                f"- Session source: `{summary['session_source_path']}`",
                f"- Session source SHA-256: `{summary['session_source_sha256']}`",
            ]
            if bool(summary.get("compiled_from_sessions", False))
            else []
        ),
        "- Authorizes trading: no",
        "",
        "## Overrides",
        "",
        "| Date | Status | Open | Close | Label |",
        "|---|---|---:|---:|---|",
    ]
    for row in sessions.to_dict(orient="records"):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("date", "")),
                    str(row.get("status", "")),
                    str(row.get("open_time", "")),
                    str(row.get("close_time", "")),
                    str(row.get("label", "")).replace("|", "\\|"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _hhmmss(seconds: int | None) -> str:
    if seconds is None:
        return ""
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"
