from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from markets.calendars import (
    MARKET_CALENDAR_POLICY,
    MarketCalendar,
    load_market_calendar,
    market_calendar_summary,
    resolve_market_calendar,
)
from markets.profiles import get_market_profile
from reports.manifest import file_sha256, write_experiment_manifest


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
        run_type="market_calendar_report",
        parameters={"expected_market": expected_market or ""},
        inputs={"market_calendar": Path(calendar_path)},
        extra={
            "ready": report.ready,
            "market": str(report.summary.iloc[0]["market"]),
            "calendar_id": str(report.summary.iloc[0]["market_calendar_id"]),
            "market_calendar_sha256": str(
                report.summary.iloc[0]["market_calendar_sha256"]
            ),
            "non_authorizing": True,
        },
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

    source_rows = _read_session_source(source)
    source_sha256 = file_sha256(source)
    profile = get_market_profile(market)
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
        },
        "sessions": sorted(source_rows, key=lambda row: row["date"]),
    }
    calendar_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with TemporaryDirectory(prefix="market-calendar-") as temp_dir:
        validation_path = Path(temp_dir) / "market_calendar.json"
        validation_path.write_text(calendar_text, encoding="utf-8")
        load_market_calendar(
            validation_path,
            expected_market=profile.name,
            expected_timezone=profile.session.timezone,
        )
    out.mkdir(parents=True, exist_ok=True)
    calendar_path = out / "market_calendar.json"
    calendar_path.write_text(calendar_text, encoding="utf-8")
    calendar = load_market_calendar(
        calendar_path,
        expected_market=profile.name,
        expected_timezone=profile.session.timezone,
    )
    base_report = _build_report(calendar)
    summary = base_report.summary.assign(
        compiled_from_sessions=True,
        session_source_schema=MARKET_CALENDAR_SESSION_SOURCE_SCHEMA,
        session_source_path=str(source),
        session_source_sha256=source_sha256,
        session_source_rows=len(source_rows),
    )
    report = MarketCalendarReport(
        sessions=base_report.sessions,
        checks=base_report.checks,
        summary=summary,
    )
    _write_report_artifacts(report, out)
    write_experiment_manifest(
        out,
        run_type="market_calendar_report",
        parameters={
            "compiled_from_sessions": True,
            "session_source_schema": MARKET_CALENDAR_SESSION_SOURCE_SCHEMA,
            "calendar_id": calendar_id,
            "market": profile.name,
            "timezone": profile.session.timezone,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "publisher": publisher,
            "source_url": source_url,
            "published_date": published_date,
        },
        inputs={"market_calendar_sessions_source": source},
        extra={
            "ready": report.ready,
            "market": profile.name,
            "calendar_id": calendar.calendar_id,
            "market_calendar_sha256": calendar.source_sha256,
            "session_source_sha256": source_sha256,
            "compiled_from_sessions": True,
            "non_authorizing": True,
        },
    )
    return MarketCalendarReport(
        sessions=report.sessions,
        checks=report.checks,
        summary=report.summary,
        output_dir=out,
    )


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
        output_dir / "market_calendar_sessions.csv",
        index=False,
    )
    report.checks.to_csv(
        output_dir / "market_calendar_checks.csv",
        index=False,
    )
    report.summary.to_csv(
        output_dir / "market_calendar_summary.csv",
        index=False,
    )
    (output_dir / "market_calendar_runbook.md").write_text(
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
