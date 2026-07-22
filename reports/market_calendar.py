from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from markets.calendars import (
    MARKET_CALENDAR_POLICY,
    MarketCalendar,
    load_market_calendar,
    market_calendar_summary,
    resolve_market_calendar,
)
from reports.manifest import write_experiment_manifest


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
    report.sessions.to_csv(out / "market_calendar_sessions.csv", index=False)
    report.checks.to_csv(out / "market_calendar_checks.csv", index=False)
    report.summary.to_csv(out / "market_calendar_summary.csv", index=False)
    (out / "market_calendar_runbook.md").write_text(
        _runbook(report.summary.iloc[0], report.sessions),
        encoding="utf-8",
    )
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
