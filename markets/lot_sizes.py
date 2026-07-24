from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES


NSE_INDEX_LOT_RULE_SCHEMA_VERSION = 1
NSE_INDEX_LOT_CYCLES = ("weekly", "monthly")
DEFAULT_NSE_INDEX_LOT_RULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "contracts"
    / "nse_fo_index_lot_sizes_v1.json"
)


@dataclass(frozen=True)
class NseIndexLotEntry:
    underlying: str
    cycle: str
    first_expiry: date
    lot_size: int
    last_existing_expiry: date | None = None


@dataclass(frozen=True)
class NseIndexLotRule:
    rule_id: str
    market: str
    publisher: str
    source_url: str
    circular_id: str
    circular_date: date
    entries: tuple[NseIndexLotEntry, ...]
    config_path: Path
    config_sha256: str
    authority_source_path: Path
    authority_source_sha256: str
    snapshot_source_url: str
    snapshot_as_of: date
    snapshot_path: Path
    snapshot_sha256: str
    snapshot_lot_sizes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class NseIndexLotDecision:
    underlying: str
    cycle: str
    contract_expiry: date
    lot_size: int
    first_expiry: date
    rule_id: str


@dataclass(frozen=True)
class NseIndexLotValidation:
    supplied_underlying: str
    supplied_expiry: str
    supplied_lot_size: str
    valid: bool
    covered: bool
    reason: str
    decision: NseIndexLotDecision | None = None

    @property
    def expected_lot_size(self) -> int | None:
        if self.decision is None:
            return None
        return self.decision.lot_size


def load_nse_index_lot_rule(
    path: str | Path = DEFAULT_NSE_INDEX_LOT_RULE_PATH,
) -> NseIndexLotRule:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"NSE index lot-size rule not found: {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"NSE index lot-size rule JSON is invalid: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("NSE index lot-size rule JSON must be an object")
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != NSE_INDEX_LOT_RULE_SCHEMA_VERSION
    ):
        raise ValueError(
            "NSE index lot-size rule schema_version must be "
            f"{NSE_INDEX_LOT_RULE_SCHEMA_VERSION}"
        )

    market = _required_text(payload, "market")
    if market != INDIA_NSE_INDEX_DERIVATIVES.name:
        raise ValueError(
            "NSE index lot-size rule market must be "
            f"{INDIA_NSE_INDEX_DERIVATIVES.name!r}"
        )
    sources = _required_mapping(payload, "authority_sources")
    circular = _verified_source(
        config_path,
        _required_mapping(sources, "circular"),
        label="circular",
    )
    snapshot_payload = _required_mapping(sources, "permitted_lot_snapshot")
    snapshot = _verified_source(
        config_path,
        snapshot_payload,
        label="permitted-lot snapshot",
    )

    raw_rule = _required_mapping(payload, "rule")
    raw_entries = raw_rule.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("NSE index lot-size rule entries must be a non-empty list")
    entries = tuple(_entry(value) for value in raw_entries)
    entry_keys = [(entry.underlying, entry.cycle) for entry in entries]
    if len(entry_keys) != len(set(entry_keys)):
        raise ValueError("NSE index lot-size rule entries must be unique")
    configured_lots = _configured_lot_sizes(entries)
    snapshot_lots = _snapshot_index_lot_sizes(snapshot[0])
    for underlying, lot_size in configured_lots.items():
        if snapshot_lots.get(underlying) != lot_size:
            raise ValueError(
                "NSE permitted-lot snapshot does not match the normalized "
                f"rule for {underlying}"
            )

    return NseIndexLotRule(
        rule_id=_required_text(raw_rule, "rule_id"),
        market=market,
        publisher=_required_text(payload, "publisher"),
        source_url=_required_text(payload, "source_url"),
        circular_id=_required_text(payload, "circular_id"),
        circular_date=_required_date(payload, "circular_date"),
        entries=entries,
        config_path=config_path,
        config_sha256=_file_sha256(config_path),
        authority_source_path=circular[0],
        authority_source_sha256=circular[1],
        snapshot_source_url=_required_text(snapshot_payload, "source_url"),
        snapshot_as_of=_required_date(snapshot_payload, "as_of"),
        snapshot_path=snapshot[0],
        snapshot_sha256=snapshot[1],
        snapshot_lot_sizes=tuple(sorted(snapshot_lots.items())),
    )


def resolve_nse_index_lot_size(
    underlying: object,
    expiry: date | datetime | str,
    *,
    cycle: str,
    rule: NseIndexLotRule | None = None,
) -> NseIndexLotDecision:
    resolved_rule = rule or load_nse_index_lot_rule()
    symbol = _underlying(underlying)
    resolved_cycle = _cycle(cycle)
    contract_expiry = _date_value(expiry, field="contract expiry")
    entry = next(
        (
            item
            for item in resolved_rule.entries
            if item.underlying == symbol and item.cycle == resolved_cycle
        ),
        None,
    )
    if entry is None:
        raise ValueError(
            "NSE index lot-size rule does not cover "
            f"{symbol or '<blank>'} {resolved_cycle} contracts"
        )
    if contract_expiry < entry.first_expiry:
        raise ValueError(
            "NSE index lot-size rule does not cover "
            f"{symbol} {resolved_cycle} expiries before "
            f"{entry.first_expiry.isoformat()}"
        )
    return NseIndexLotDecision(
        underlying=symbol,
        cycle=resolved_cycle,
        contract_expiry=contract_expiry,
        lot_size=entry.lot_size,
        first_expiry=entry.first_expiry,
        rule_id=resolved_rule.rule_id,
    )


def validate_nse_index_lot_size(
    underlying: object,
    expiry: object,
    lot_size: object,
    *,
    cycle: str,
    rule: NseIndexLotRule | None = None,
) -> NseIndexLotValidation:
    supplied_underlying = str(underlying or "").strip().upper()
    supplied_expiry = _supplied_text(expiry)
    supplied_lot_size = _supplied_text(lot_size)
    try:
        decision = resolve_nse_index_lot_size(
            underlying,
            expiry,
            cycle=cycle,
            rule=rule,
        )
    except (FileNotFoundError, ValueError) as exc:
        return NseIndexLotValidation(
            supplied_underlying=supplied_underlying,
            supplied_expiry=supplied_expiry,
            supplied_lot_size=supplied_lot_size,
            valid=False,
            covered=False,
            reason=str(exc),
        )
    parsed_lot_size = _lot_size(lot_size)
    if parsed_lot_size is None:
        return NseIndexLotValidation(
            supplied_underlying=supplied_underlying,
            supplied_expiry=supplied_expiry,
            supplied_lot_size=supplied_lot_size,
            valid=False,
            covered=True,
            reason="invalid_contract_lot_size",
            decision=decision,
        )
    if parsed_lot_size != decision.lot_size:
        return NseIndexLotValidation(
            supplied_underlying=supplied_underlying,
            supplied_expiry=supplied_expiry,
            supplied_lot_size=supplied_lot_size,
            valid=False,
            covered=True,
            reason="contract_lot_size_mismatch",
            decision=decision,
        )
    return NseIndexLotValidation(
        supplied_underlying=supplied_underlying,
        supplied_expiry=supplied_expiry,
        supplied_lot_size=supplied_lot_size,
        valid=True,
        covered=True,
        reason="valid_contract_lot_size",
        decision=decision,
    )


def index_lot_rule_summary(rule: NseIndexLotRule) -> dict[str, Any]:
    return {
        "contract_lot_rule_id": rule.rule_id,
        "contract_lot_rule_publisher": rule.publisher,
        "contract_lot_rule_source_url": rule.source_url,
        "contract_lot_rule_circular_id": rule.circular_id,
        "contract_lot_rule_circular_date": rule.circular_date.isoformat(),
        "contract_lot_rule_path": str(rule.config_path),
        "contract_lot_rule_sha256": rule.config_sha256,
        "contract_lot_authority_source_path": str(
            rule.authority_source_path
        ),
        "contract_lot_authority_source_sha256": (
            rule.authority_source_sha256
        ),
        "contract_lot_snapshot_source_url": rule.snapshot_source_url,
        "contract_lot_snapshot_as_of": rule.snapshot_as_of.isoformat(),
        "contract_lot_snapshot_path": str(rule.snapshot_path),
        "contract_lot_snapshot_sha256": rule.snapshot_sha256,
    }


def _entry(value: object) -> NseIndexLotEntry:
    if not isinstance(value, Mapping):
        raise ValueError("NSE index lot-size rule entry must be an object")
    first_expiry = _required_date(value, "first_expiry")
    raw_last_expiry = value.get("last_existing_expiry")
    last_expiry = (
        _date_value(raw_last_expiry, field="last_existing_expiry")
        if raw_last_expiry is not None
        else None
    )
    if last_expiry is not None and last_expiry >= first_expiry:
        raise ValueError(
            "NSE index lot-size last_existing_expiry must precede first_expiry"
        )
    lot_size = _positive_integer(value.get("lot_size"), field="lot_size")
    return NseIndexLotEntry(
        underlying=_underlying(_required_text(value, "underlying")),
        cycle=_cycle(_required_text(value, "cycle")),
        first_expiry=first_expiry,
        lot_size=lot_size,
        last_existing_expiry=last_expiry,
    )


def _configured_lot_sizes(
    entries: tuple[NseIndexLotEntry, ...],
) -> dict[str, int]:
    values: dict[str, int] = {}
    for entry in entries:
        existing = values.get(entry.underlying)
        if existing is not None and existing != entry.lot_size:
            raise ValueError(
                "NSE index lot-size entries disagree across cycles for "
                f"{entry.underlying}"
            )
        values[entry.underlying] = entry.lot_size
    return values


def _snapshot_index_lot_sizes(path: Path) -> dict[str, int]:
    rows: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None or len(header) < 3:
            raise ValueError("NSE permitted-lot snapshot is empty")
        for raw_row in reader:
            row = [cell.strip() for cell in raw_row]
            if not row or not row[0]:
                continue
            if row[0] == "Derivatives on Individual Securities":
                break
            if len(row) < 3:
                raise ValueError("NSE permitted-lot snapshot row is incomplete")
            symbol = _underlying(row[1])
            lots = {
                _positive_integer(value, field=f"{symbol} snapshot lot size")
                for value in row[2:]
                if value
            }
            if len(lots) != 1:
                raise ValueError(
                    "NSE permitted-lot snapshot has inconsistent lots for "
                    f"{symbol}"
                )
            rows[symbol] = lots.pop()
    if not rows:
        raise ValueError("NSE permitted-lot snapshot has no index contracts")
    return rows


def _verified_source(
    config_path: Path,
    value: Mapping[str, Any],
    *,
    label: str,
) -> tuple[Path, str]:
    source_path = (config_path.parent / _required_text(value, "path")).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(
            f"NSE index lot-size {label} not found: {source_path}"
        )
    expected_sha256 = _required_sha256(value, "sha256")
    actual_sha256 = _file_sha256(source_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"NSE index lot-size {label} fingerprint does not match "
            "the normalized rule"
        )
    return source_path, actual_sha256


def _underlying(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise ValueError("NSE index underlying must not be blank")
    return symbol


def _cycle(value: object) -> str:
    cycle = str(value or "").strip().lower()
    if cycle not in NSE_INDEX_LOT_CYCLES:
        raise ValueError(
            "NSE index lot-size cycle must be one of "
            f"{list(NSE_INDEX_LOT_CYCLES)}"
        )
    return cycle


def _lot_size(value: object) -> int | None:
    try:
        if isinstance(value, bool):
            return None
        numeric = float(value)
        integer = int(numeric)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or numeric != integer or integer <= 0:
        return None
    return integer


def _positive_integer(value: object, *, field: str) -> int:
    parsed = _lot_size(value)
    if parsed is None:
        raise ValueError(f"NSE index lot-size {field} must be a positive integer")
    return parsed


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


def _required_mapping(
    value: Mapping[str, Any],
    field: str,
) -> Mapping[str, Any]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        raise ValueError(f"NSE index lot-size rule {field} must be an object")
    return result


def _required_text(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"NSE index lot-size rule {field} must not be blank")
    return result.strip()


def _required_date(value: Mapping[str, Any], field: str) -> date:
    return _date_value(value.get(field), field=field)


def _required_sha256(value: Mapping[str, Any], field: str) -> str:
    result = _required_text(value, field).lower()
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError(
            f"NSE index lot-size rule {field} must be a SHA-256 fingerprint"
        )
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
