from __future__ import annotations

import calendar as month_calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from markets.calendars import MarketCalendar, resolve_market_calendar
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES, get_market_profile


NSE_FO_EXPIRY_RULE_SCHEMA_VERSION = 1
NSE_FO_EXPIRY_CYCLES = ("weekly", "monthly")
DEFAULT_NSE_FO_EXPIRY_RULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "contracts"
    / "nse_fo_expiry_rules_v1.json"
)


@dataclass(frozen=True)
class NseFoExpiryRule:
    rule_id: str
    market: str
    publisher: str
    source_url: str
    circular_id: str
    circular_date: date
    effective_from: date
    expiry_weekday: int
    cycles: tuple[str, ...]
    adjustment: str
    config_path: Path
    config_sha256: str
    authority_source_path: Path
    authority_source_sha256: str


@dataclass(frozen=True)
class NseFoExpiryDecision:
    cycle: str
    period_start: date
    period_end: date
    nominal_expiry: date
    actual_expiry: date
    adjusted: bool
    rollback_days: int
    rule_id: str
    calendar_id: str


@dataclass(frozen=True)
class NseFoExpiryValidation:
    supplied_value: str
    parsed_expiry: date | None
    valid: bool
    covered: bool
    reason: str
    decision: NseFoExpiryDecision | None = None

    @property
    def expected_expiry(self) -> date | None:
        if self.decision is None:
            return None
        return self.decision.actual_expiry

    @property
    def nominal_expiry(self) -> date | None:
        if self.decision is None:
            return None
        return self.decision.nominal_expiry


def load_nse_fo_expiry_rule(
    path: str | Path = DEFAULT_NSE_FO_EXPIRY_RULE_PATH,
) -> NseFoExpiryRule:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"NSE F&O expiry rule not found: {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"NSE F&O expiry rule JSON is invalid: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("NSE F&O expiry rule JSON must be an object")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != NSE_FO_EXPIRY_RULE_SCHEMA_VERSION
    ):
        raise ValueError(
            "NSE F&O expiry rule schema_version must be "
            f"{NSE_FO_EXPIRY_RULE_SCHEMA_VERSION}"
        )

    market = _required_text(payload, "market")
    if market != INDIA_NSE_INDEX_DERIVATIVES.name:
        raise ValueError(
            "NSE F&O expiry rule market must be "
            f"{INDIA_NSE_INDEX_DERIVATIVES.name!r}"
        )
    authority = _required_mapping(payload, "authority_source")
    authority_path = (
        config_path.parent / _required_text(authority, "path")
    ).resolve()
    if not authority_path.is_file():
        raise FileNotFoundError(
            f"NSE F&O expiry authority source not found: {authority_path}"
        )
    expected_authority_sha256 = _required_sha256(authority, "sha256")
    actual_authority_sha256 = _file_sha256(authority_path)
    if actual_authority_sha256 != expected_authority_sha256:
        raise ValueError(
            "NSE F&O expiry authority source fingerprint does not match "
            "the normalized rule"
        )

    raw_rule = _required_mapping(payload, "rule")
    expiry_weekday = raw_rule.get("expiry_weekday")
    if (
        isinstance(expiry_weekday, bool)
        or not isinstance(expiry_weekday, int)
        or expiry_weekday < 0
        or expiry_weekday > 6
    ):
        raise ValueError("NSE F&O expiry_weekday must be an integer from 0 to 6")
    cycles_value = raw_rule.get("cycles")
    if not isinstance(cycles_value, list):
        raise ValueError("NSE F&O expiry rule cycles must be a list")
    cycles = tuple(_expiry_cycle(item) for item in cycles_value)
    if not cycles or len(cycles) != len(set(cycles)):
        raise ValueError("NSE F&O expiry rule cycles must be unique and non-empty")
    adjustment = _required_text(raw_rule, "adjustment")
    if adjustment != "previous_trading_day":
        raise ValueError(
            "NSE F&O expiry rule adjustment must be 'previous_trading_day'"
        )

    return NseFoExpiryRule(
        rule_id=_required_text(raw_rule, "rule_id"),
        market=market,
        publisher=_required_text(payload, "publisher"),
        source_url=_required_text(payload, "source_url"),
        circular_id=_required_text(payload, "circular_id"),
        circular_date=_required_date(payload, "circular_date"),
        effective_from=_required_date(raw_rule, "effective_from"),
        expiry_weekday=expiry_weekday,
        cycles=cycles,
        adjustment=adjustment,
        config_path=config_path,
        config_sha256=_file_sha256(config_path),
        authority_source_path=authority_path,
        authority_source_sha256=actual_authority_sha256,
    )


def resolve_nse_fo_expiry(
    period: date | datetime | str,
    *,
    cycle: str,
    market_calendar: MarketCalendar | str | Path,
    rule: NseFoExpiryRule | None = None,
) -> NseFoExpiryDecision:
    resolved_rule = rule or load_nse_fo_expiry_rule()
    resolved_cycle = _expiry_cycle(cycle)
    if resolved_cycle not in resolved_rule.cycles:
        raise ValueError(
            f"NSE F&O expiry rule does not support cycle {resolved_cycle!r}"
        )
    calendar = resolve_market_calendar(
        market_calendar,
        market=resolved_rule.market,
    )
    if calendar is None:
        raise ValueError("market calendar is required for NSE F&O expiry resolution")

    reference = _date_value(period, field="expiry period")
    period_start, period_end, nominal = _period_bounds(
        reference,
        cycle=resolved_cycle,
        expiry_weekday=resolved_rule.expiry_weekday,
    )
    if nominal < resolved_rule.effective_from:
        raise ValueError(
            "NSE F&O Tuesday expiry rule does not cover nominal expiries "
            f"before {resolved_rule.effective_from.isoformat()}"
        )
    actual = _previous_trading_day(nominal, calendar)
    return NseFoExpiryDecision(
        cycle=resolved_cycle,
        period_start=period_start,
        period_end=period_end,
        nominal_expiry=nominal,
        actual_expiry=actual,
        adjusted=actual != nominal,
        rollback_days=(nominal - actual).days,
        rule_id=resolved_rule.rule_id,
        calendar_id=calendar.calendar_id,
    )


def validate_nse_fo_expiry(
    value: object,
    *,
    cycle: str,
    market_calendar: MarketCalendar | str | Path,
    rule: NseFoExpiryRule | None = None,
) -> NseFoExpiryValidation:
    resolved_rule = rule or load_nse_fo_expiry_rule()
    resolved_cycle = _expiry_cycle(cycle)
    supplied = _supplied_text(value)
    try:
        parsed = _date_value(value, field="contract expiry")
    except ValueError:
        return NseFoExpiryValidation(
            supplied_value=supplied,
            parsed_expiry=None,
            valid=False,
            covered=False,
            reason="invalid_expiry_date",
        )

    references = [parsed]
    if resolved_cycle == "weekly":
        references.append(parsed + timedelta(days=7))
    decisions: list[NseFoExpiryDecision] = []
    errors: list[str] = []
    seen_periods: set[tuple[date, date]] = set()
    for reference in references:
        try:
            decision = resolve_nse_fo_expiry(
                reference,
                cycle=resolved_cycle,
                market_calendar=market_calendar,
                rule=resolved_rule,
            )
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            continue
        period_key = (decision.period_start, decision.period_end)
        if period_key in seen_periods:
            continue
        seen_periods.add(period_key)
        decisions.append(decision)
        if decision.actual_expiry == parsed:
            return NseFoExpiryValidation(
                supplied_value=supplied,
                parsed_expiry=parsed,
                valid=True,
                covered=True,
                reason="valid_adjusted_expiry"
                if decision.adjusted
                else "valid_expiry",
                decision=decision,
            )

    if decisions:
        return NseFoExpiryValidation(
            supplied_value=supplied,
            parsed_expiry=parsed,
            valid=False,
            covered=True,
            reason=f"not_{resolved_cycle}_expiry",
            decision=decisions[0],
        )
    return NseFoExpiryValidation(
        supplied_value=supplied,
        parsed_expiry=parsed,
        valid=False,
        covered=False,
        reason=errors[0] if errors else "expiry_not_covered",
    )


def expiry_rule_summary(rule: NseFoExpiryRule) -> dict[str, Any]:
    return {
        "contract_expiry_rule_id": rule.rule_id,
        "contract_expiry_rule_effective_from": rule.effective_from.isoformat(),
        "contract_expiry_rule_publisher": rule.publisher,
        "contract_expiry_rule_source_url": rule.source_url,
        "contract_expiry_rule_circular_id": rule.circular_id,
        "contract_expiry_rule_circular_date": rule.circular_date.isoformat(),
        "contract_expiry_rule_path": str(rule.config_path),
        "contract_expiry_rule_sha256": rule.config_sha256,
        "contract_expiry_authority_source_path": str(
            rule.authority_source_path
        ),
        "contract_expiry_authority_source_sha256": (
            rule.authority_source_sha256
        ),
    }


def _period_bounds(
    reference: date,
    *,
    cycle: str,
    expiry_weekday: int,
) -> tuple[date, date, date]:
    if cycle == "weekly":
        start = reference - timedelta(days=reference.weekday())
        end = start + timedelta(days=6)
        return start, end, start + timedelta(days=expiry_weekday)
    start = reference.replace(day=1)
    end = reference.replace(
        day=month_calendar.monthrange(reference.year, reference.month)[1]
    )
    rollback = (end.weekday() - expiry_weekday) % 7
    return start, end, end - timedelta(days=rollback)


def _previous_trading_day(
    nominal: date,
    market_calendar: MarketCalendar,
) -> date:
    profile = get_market_profile(market_calendar.market)
    candidate = nominal
    while True:
        decision = market_calendar.decision(
            candidate,
            trading_weekdays=profile.session.trading_weekdays,
            default_open_seconds=profile.session.open_seconds,
            default_close_seconds=profile.session.close_seconds,
        )
        if not decision.covered:
            raise ValueError(
                "market calendar does not cover expiry resolution date "
                f"{candidate.isoformat()}"
            )
        if decision.trading_day:
            return candidate
        candidate -= timedelta(days=1)


def _expiry_cycle(value: object) -> str:
    cycle = str(value or "").strip().lower()
    if cycle not in NSE_FO_EXPIRY_CYCLES:
        raise ValueError(
            "NSE F&O expiry cycle must be one of "
            f"{list(NSE_FO_EXPIRY_CYCLES)}"
        )
    return cycle


def _date_value(value: object, *, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    text = value.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise ValueError(f"{field} must be YYYY-MM-DD")
    return parsed


def _supplied_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _required_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        raise ValueError(f"NSE F&O expiry rule {field} must be an object")
    return result


def _required_text(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"NSE F&O expiry rule {field} is required")
    return result.strip()


def _required_date(value: Mapping[str, Any], field: str) -> date:
    return _date_value(_required_text(value, field), field=field)


def _required_sha256(value: Mapping[str, Any], field: str) -> str:
    result = _required_text(value, field).lower()
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(f"NSE F&O expiry rule {field} must be a SHA-256")
    return result


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
