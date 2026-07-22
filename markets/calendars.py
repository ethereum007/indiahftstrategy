from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


MARKET_CALENDAR_SCHEMA_VERSION = 1
MARKET_CALENDAR_POLICY = "versioned_exchange_calendar_v1"
TIME_RE = re.compile(r"^([0-2][0-9]):([0-5][0-9]):([0-5][0-9])$")


@dataclass(frozen=True)
class CalendarSession:
    trade_date: date
    status: str
    open_seconds: int | None = None
    close_seconds: int | None = None
    label: str = ""


@dataclass(frozen=True)
class CalendarDayDecision:
    trade_date: date
    covered: bool
    trading_day: bool
    explicit_status: str
    open_seconds: int
    close_seconds: int
    label: str = ""


@dataclass(frozen=True)
class MarketCalendar:
    calendar_id: str
    market: str
    timezone: str
    valid_from: date
    valid_to: date
    publisher: str
    source_url: str
    published_date: date
    sessions: tuple[CalendarSession, ...]
    source_path: Path
    source_sha256: str

    def decision(
        self,
        trade_date: date,
        *,
        trading_weekdays: tuple[int, ...],
        default_open_seconds: int,
        default_close_seconds: int,
    ) -> CalendarDayDecision:
        if trade_date < self.valid_from or trade_date > self.valid_to:
            return CalendarDayDecision(
                trade_date=trade_date,
                covered=False,
                trading_day=False,
                explicit_status="out_of_range",
                open_seconds=default_open_seconds,
                close_seconds=default_close_seconds,
            )
        session = self.sessions_by_date.get(trade_date)
        if session is None:
            return CalendarDayDecision(
                trade_date=trade_date,
                covered=True,
                trading_day=trade_date.weekday() in trading_weekdays,
                explicit_status="default_weekday_policy",
                open_seconds=default_open_seconds,
                close_seconds=default_close_seconds,
            )
        if session.status == "closed":
            return CalendarDayDecision(
                trade_date=trade_date,
                covered=True,
                trading_day=False,
                explicit_status="closed",
                open_seconds=default_open_seconds,
                close_seconds=default_close_seconds,
                label=session.label,
            )
        return CalendarDayDecision(
            trade_date=trade_date,
            covered=True,
            trading_day=True,
            explicit_status="open",
            open_seconds=int(session.open_seconds or 0),
            close_seconds=int(session.close_seconds or 0),
            label=session.label,
        )

    @property
    def sessions_by_date(self) -> dict[date, CalendarSession]:
        return {session.trade_date: session for session in self.sessions}

    @property
    def closed_dates(self) -> tuple[date, ...]:
        return tuple(
            session.trade_date
            for session in self.sessions
            if session.status == "closed"
        )

    @property
    def special_open_dates(self) -> tuple[date, ...]:
        return tuple(
            session.trade_date
            for session in self.sessions
            if session.status == "open"
        )


def load_market_calendar(
    path: str | Path,
    *,
    expected_market: str | None = None,
    expected_timezone: str | None = None,
) -> MarketCalendar:
    source_path = Path(path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"market calendar not found: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"market calendar JSON is invalid: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("market calendar JSON must be an object")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != MARKET_CALENDAR_SCHEMA_VERSION
    ):
        raise ValueError(
            f"market calendar schema_version must be {MARKET_CALENDAR_SCHEMA_VERSION}"
        )

    calendar_id = _required_text(payload, "calendar_id")
    market = _required_text(payload, "market")
    timezone = _required_text(payload, "timezone")
    try:
        ZoneInfo(timezone)
    except Exception as exc:
        raise ValueError(f"market calendar timezone is invalid: {timezone!r}") from exc
    if expected_market and market != expected_market:
        raise ValueError(
            f"market calendar market {market!r} does not match {expected_market!r}"
        )
    if expected_timezone and timezone != expected_timezone:
        raise ValueError(
            f"market calendar timezone {timezone!r} does not match {expected_timezone!r}"
        )

    valid_from = _required_date(payload, "valid_from")
    valid_to = _required_date(payload, "valid_to")
    if valid_to < valid_from:
        raise ValueError("market calendar valid_to must be on or after valid_from")

    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("market calendar provenance must be an object")
    publisher = _required_text(provenance, "publisher")
    source_url = _required_text(provenance, "source_url")
    published_date = _required_date(provenance, "published_date")

    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        raise ValueError("market calendar sessions must be a list")
    sessions = tuple(
        _parse_session(item, valid_from=valid_from, valid_to=valid_to)
        for item in raw_sessions
    )
    dates = [session.trade_date for session in sessions]
    if len(dates) != len(set(dates)):
        raise ValueError("market calendar sessions must contain unique dates")
    sessions = tuple(sorted(sessions, key=lambda session: session.trade_date))

    return MarketCalendar(
        calendar_id=calendar_id,
        market=market,
        timezone=timezone,
        valid_from=valid_from,
        valid_to=valid_to,
        publisher=publisher,
        source_url=source_url,
        published_date=published_date,
        sessions=sessions,
        source_path=source_path,
        source_sha256=_file_sha256(source_path),
    )


def resolve_market_calendar(
    value: MarketCalendar | str | Path | None,
    *,
    market: str,
) -> MarketCalendar | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    from markets.profiles import get_market_profile

    profile = get_market_profile(market)
    if isinstance(value, MarketCalendar):
        calendar = value
        if calendar.market != profile.name:
            raise ValueError(
                f"market calendar market {calendar.market!r} does not match {profile.name!r}"
            )
        if calendar.timezone != profile.session.timezone:
            raise ValueError(
                "market calendar timezone does not match the market profile: "
                f"{calendar.timezone!r} != {profile.session.timezone!r}"
            )
        return calendar
    return load_market_calendar(
        value,
        expected_market=profile.name,
        expected_timezone=profile.session.timezone,
    )


def market_calendar_summary(calendar: MarketCalendar | None) -> dict[str, Any]:
    if calendar is None:
        return {
            "market_calendar_provided": False,
            "market_calendar_policy": "weekday_only_no_holiday_calendar",
            "market_calendar_id": "",
            "market_calendar_path": "",
            "market_calendar_sha256": "",
            "market_calendar_valid_from": "",
            "market_calendar_valid_to": "",
            "market_calendar_publisher": "",
            "market_calendar_source_url": "",
            "market_calendar_published_date": "",
            "market_calendar_closed_dates": 0,
            "market_calendar_special_open_dates": 0,
        }
    return {
        "market_calendar_provided": True,
        "market_calendar_policy": MARKET_CALENDAR_POLICY,
        "market_calendar_id": calendar.calendar_id,
        "market_calendar_path": str(calendar.source_path),
        "market_calendar_sha256": calendar.source_sha256,
        "market_calendar_valid_from": calendar.valid_from.isoformat(),
        "market_calendar_valid_to": calendar.valid_to.isoformat(),
        "market_calendar_publisher": calendar.publisher,
        "market_calendar_source_url": calendar.source_url,
        "market_calendar_published_date": calendar.published_date.isoformat(),
        "market_calendar_closed_dates": len(calendar.closed_dates),
        "market_calendar_special_open_dates": len(calendar.special_open_dates),
    }


def _parse_session(
    value: object,
    *,
    valid_from: date,
    valid_to: date,
) -> CalendarSession:
    if not isinstance(value, Mapping):
        raise ValueError("market calendar session entries must be objects")
    trade_date = _required_date(value, "date")
    if trade_date < valid_from or trade_date > valid_to:
        raise ValueError(
            f"market calendar session date {trade_date.isoformat()} is outside coverage"
        )
    status = _required_text(value, "status").lower()
    if status not in {"closed", "open"}:
        raise ValueError("market calendar session status must be 'closed' or 'open'")
    label = _optional_text(value.get("label"))
    open_value = _optional_text(value.get("open_time"))
    close_value = _optional_text(value.get("close_time"))
    if status == "closed":
        if open_value or close_value:
            raise ValueError("closed market calendar sessions cannot define open_time or close_time")
        return CalendarSession(trade_date=trade_date, status=status, label=label)
    if not open_value or not close_value:
        raise ValueError("open market calendar sessions require open_time and close_time")
    open_seconds = _parse_time(open_value)
    close_seconds = _parse_time(close_value)
    if close_seconds <= open_seconds:
        raise ValueError("market calendar open session close_time must be after open_time")
    return CalendarSession(
        trade_date=trade_date,
        status=status,
        open_seconds=open_seconds,
        close_seconds=close_seconds,
        label=label,
    )


def _required_text(value: Mapping[str, Any], field: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str):
        raise ValueError(f"market calendar {field} must be a string")
    text = raw.strip()
    if not text:
        raise ValueError(f"market calendar {field} is required")
    return text


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("market calendar optional text values must be strings")
    return value.strip()


def _required_date(value: Mapping[str, Any], field: str) -> date:
    text = _required_text(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"market calendar {field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise ValueError(f"market calendar {field} must be YYYY-MM-DD")
    return parsed


def _parse_time(value: str) -> int:
    match = TIME_RE.fullmatch(value)
    if match is None:
        raise ValueError("market calendar session times must be HH:MM:SS")
    hour, minute, second = (int(item) for item in match.groups())
    if hour > 23:
        raise ValueError("market calendar session hour must be between 00 and 23")
    return hour * 3600 + minute * 60 + second


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
