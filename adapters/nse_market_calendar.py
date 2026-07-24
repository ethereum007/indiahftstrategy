from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping


NSE_FO_HOLIDAY_SNAPSHOT_SCHEMA = "nse_holiday_master_fo_json_v1"
NSE_HOLIDAY_API_URL = (
    "https://www.nseindia.com/api/holiday-master?type=trading"
)
NSE_FO_SEGMENT = "FO"
NSE_SESSION_SOURCE_COLUMNS = (
    "date",
    "status",
    "open_time",
    "close_time",
    "label",
)


@dataclass(frozen=True)
class NseHolidayNormalization:
    sessions: tuple[dict[str, str], ...]
    source_rows: int
    selected_rows: int
    skipped_weekend_rows: int


def normalize_nse_fo_holiday_snapshot(
    snapshot_path: str | Path,
    *,
    valid_from: str,
    valid_to: str,
) -> NseHolidayNormalization:
    start = _iso_date(valid_from, "valid_from")
    end = _iso_date(valid_to, "valid_to")
    if end < start:
        raise ValueError("NSE holiday coverage must be nonempty")

    payload = _read_json_object(
        Path(snapshot_path),
        "NSE holiday-master snapshot",
    )
    raw_rows = payload.get(NSE_FO_SEGMENT)
    if not isinstance(raw_rows, list):
        raise ValueError(
            "NSE holiday-master snapshot lacks the FO segment"
        )

    parsed_rows: list[tuple[date, str]] = []
    seen_dates: set[date] = set()
    for row_number, raw_row in enumerate(raw_rows, start=1):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                f"NSE FO holiday row {row_number} must be an object"
            )
        trade_date = _nse_date(
            raw_row.get("tradingDate"),
            row_number=row_number,
        )
        if trade_date in seen_dates:
            raise ValueError(
                "NSE FO holiday snapshot contains duplicate trading dates"
            )
        seen_dates.add(trade_date)

        weekday = _required_text(
            raw_row,
            "weekDay",
            row_number=row_number,
        )
        expected_weekday = trade_date.strftime("%A")
        if weekday != expected_weekday:
            raise ValueError(
                f"NSE FO holiday row {row_number} weekday "
                f"{weekday!r} does not match {expected_weekday!r}"
            )
        description = _required_text(
            raw_row,
            "description",
            row_number=row_number,
        )
        for field in ("morning_session", "evening_session"):
            if field not in raw_row:
                raise ValueError(
                    f"NSE FO holiday row {row_number} lacks {field}"
                )
            if raw_row.get(field) is not None:
                raise ValueError(
                    "NSE FO holiday snapshot contains unsupported "
                    f"session-level status in row {row_number}"
                )
        sequence = raw_row.get("Sr_no")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError(
                f"NSE FO holiday row {row_number} Sr_no must be positive"
            )
        parsed_rows.append((trade_date, description))

    sessions: list[dict[str, str]] = []
    selected_rows = 0
    skipped_weekend_rows = 0
    for trade_date, description in sorted(parsed_rows):
        if trade_date < start or trade_date > end:
            continue
        selected_rows += 1
        if trade_date.weekday() >= 5:
            skipped_weekend_rows += 1
            if "*" in description:
                raise ValueError(
                    "NSE FO holiday snapshot marks "
                    f"{trade_date.isoformat()} as a special session but "
                    "does not provide its open and close times"
                )
            continue
        sessions.append(
            {
                "date": trade_date.isoformat(),
                "status": "closed",
                "label": description,
            }
        )

    return NseHolidayNormalization(
        sessions=tuple(sessions),
        source_rows=len(parsed_rows),
        selected_rows=selected_rows,
        skipped_weekend_rows=skipped_weekend_rows,
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _required_text(
    row: Mapping[str, Any],
    field: str,
    *,
    row_number: int,
) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"NSE FO holiday row {row_number} {field} is required"
        )
    return value.strip()


def _nse_date(value: object, *, row_number: int) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"NSE FO holiday row {row_number} tradingDate is required"
        )
    text = value.strip()
    try:
        parsed = datetime.strptime(text, "%d-%b-%Y").date()
    except ValueError as exc:
        raise ValueError(
            f"NSE FO holiday row {row_number} tradingDate is invalid"
        ) from exc
    if parsed.strftime("%d-%b-%Y") != text:
        raise ValueError(
            f"NSE FO holiday row {row_number} tradingDate is not canonical"
        )
    return parsed


def _iso_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"NSE holiday {field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"NSE holiday {field} must be YYYY-MM-DD")
    return parsed
