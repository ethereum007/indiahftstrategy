from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import get_adapter
from adapters.schema_audit import SCHEMA_KIND_ATTRS
from data.chains import normalize_option_chain
from data.loaders import _to_ns, normalize_ticks
from markets.calendars import market_calendar_summary, resolve_market_calendar
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


MAPPED_DATA_TRANSFORMS = frozenset(
    {
        "identity",
        "none",
        "string",
        "uppercase",
        "lowercase",
        "int",
        "float",
        "side_text",
        "side_signed",
    }
)

QUARANTINE_SUMMARY_FIELDS = (
    "quarantine_total_rows",
    "quarantine_kept_rows",
    "quarantined_rows",
    "dropped_null_rows",
    "dropped_nonfinite_rows",
    "dropped_nonintegral_rows",
    "dropped_duplicate_rows",
    "dropped_integer_overflow_rows",
    "dropped_nonpositive_strike_rows",
    "dropped_nonpositive_quote_rows",
    "dropped_crossed_quote_rows",
    "dropped_nonmonotonic_rows",
    "dropped_negative_depth_rows",
    "dropped_invalid_trade_rows",
    "dropped_non_trading_day_rows",
    "dropped_calendar_closed_rows",
    "dropped_calendar_out_of_range_rows",
    "dropped_out_of_session_rows",
)


@dataclass(frozen=True)
class MappedDataConfig:
    adapter: str = "normalized"
    kind: str = "ticks"
    output_filename: str = "normalized_data.csv"
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None
    filter_session: bool = True
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name
    market_calendar_path: str | None = None
    require_all_mapped: bool = True


@dataclass(frozen=True)
class MappedDataReport:
    data: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame | None = None
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def normalize_mapped_data(
    raw: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    config: MappedDataConfig | None = None,
) -> MappedDataReport:
    config = config or MappedDataConfig()
    canonical_kind, expected_columns = _expected_columns(config)
    rows = _mapping_rows(mapping, expected_columns)
    mapped_columns: dict[str, pd.Series] = {}
    checks = []
    for row in rows:
        values, check = _map_column(raw, row, require_all_mapped=config.require_all_mapped)
        mapped_columns[row["normalized_column"]] = values
        checks.append(check)

    checks_frame = pd.DataFrame(checks)
    mapped = pd.DataFrame(mapped_columns)
    if checks_frame.empty or not bool(checks_frame["passed"].astype(bool).all()):
        data = mapped.iloc[0:0].copy()
        summary = _summary(
            raw,
            data,
            checks_frame,
            config,
            canonical_kind,
            _empty_quarantine(),
        )
        action_queue = _action_queue(summary.iloc[0], checks_frame)
        summary = _summary_with_actions(summary, action_queue)
        return MappedDataReport(data=data, checks=checks_frame, summary=summary, action_queue=action_queue)

    data, quarantine = _normalize_kind(mapped, canonical_kind, config)
    summary = _summary(
        raw,
        data,
        checks_frame,
        config,
        canonical_kind,
        quarantine,
    )
    action_queue = _action_queue(summary.iloc[0], checks_frame)
    summary = _summary_with_actions(summary, action_queue)
    return MappedDataReport(data=data, checks=checks_frame, summary=summary, action_queue=action_queue)


def write_mapped_data_normalization(
    input_path: str | Path,
    mapping_path: str | Path,
    *,
    output_dir: str | Path,
    config: MappedDataConfig | None = None,
) -> MappedDataReport:
    config = config or MappedDataConfig()
    _validate_config(config)
    input_file = Path(input_path)
    mapping_file = Path(mapping_path)
    if not input_file.exists():
        raise FileNotFoundError(f"mapped data input not found: {input_file}")
    if not mapping_file.exists():
        raise FileNotFoundError(f"mapped data mapping not found: {mapping_file}")
    raw = pd.read_csv(input_file)
    mapping = pd.read_csv(mapping_file)
    report = normalize_mapped_data(raw, mapping, config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.data.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "mapped_data_checks.csv", index=False)
    report.summary.to_csv(out / "mapped_data_summary.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.checks)
    )
    action_queue.to_csv(out / "mapped_data_action_queue.csv", index=False)
    (out / "mapped_data_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], action_queue, config, input_file, mapping_file),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "mapped_data_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    manifest_inputs: dict[str, Any] = {
        "input": input_file,
        "mapping": mapping_file,
    }
    if config.market_calendar_path:
        manifest_inputs["market_calendar"] = Path(config.market_calendar_path)
    write_experiment_manifest(
        out,
        run_type="mapped_data_normalization",
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
    )
    return MappedDataReport(report.data, report.checks, report.summary, action_queue, out)


def _expected_columns(config: MappedDataConfig) -> tuple[str, list[str]]:
    _validate_config(config)
    canonical_kind, attr = _schema_kind(config.kind)
    spec = get_adapter(config.adapter)
    return canonical_kind, [str(column) for column in getattr(spec, attr).keys()]


def _mapping_rows(mapping: pd.DataFrame, expected_columns: list[str]) -> list[dict[str, Any]]:
    if mapping.empty:
        raise ValueError("mapped data mapping is empty")
    target_field = _target_field(mapping)
    frame = mapping.copy()
    for column in ("source_column", "default_value", "required", "transform"):
        if column not in frame.columns:
            frame[column] = ""

    by_target: dict[str, dict[str, Any]] = {}
    for index, row in frame.iterrows():
        target = _cell(row, target_field)
        if not target:
            raise ValueError(f"mapped data mapping row {index} has blank normalized column")
        if target in by_target:
            raise ValueError(f"mapped data mapping has duplicate normalized column: {target}")
        by_target[target] = {
            "normalized_column": target,
            "source_column": _cell(row, "source_column"),
            "default_value": _cell(row, "default_value"),
            "required": _to_bool(row.get("required", True), default=True),
            "transform": _cell(row, "transform").lower() or "identity",
        }

    unknown = sorted(target for target in by_target if target not in expected_columns)
    if unknown:
        raise ValueError(f"mapped data mapping has unknown normalized columns: {unknown}")

    rows = []
    for column in expected_columns:
        rows.append(
            by_target.get(
                column,
                {
                    "normalized_column": column,
                    "source_column": "",
                    "default_value": "",
                    "required": True,
                    "transform": "identity",
                },
            )
        )
    return rows


def _target_field(mapping: pd.DataFrame) -> str:
    if "normalized_column" in mapping.columns:
        return "normalized_column"
    if "target_column" in mapping.columns:
        return "target_column"
    raise ValueError("mapped data mapping missing required column: normalized_column")


def _map_column(
    raw: pd.DataFrame,
    row: dict[str, Any],
    *,
    require_all_mapped: bool,
) -> tuple[pd.Series, dict[str, Any]]:
    source_column = str(row["source_column"])
    default_value = str(row["default_value"])
    source_present = bool(source_column and source_column in raw.columns)
    default_present = bool(default_value)
    if source_present:
        values = raw[source_column].copy()
    else:
        values = pd.Series([pd.NA] * len(raw), index=raw.index)
    if default_present:
        values = values.mask(~_nonempty_mask(values), default_value)
    values = _apply_transform(values, str(row["transform"]))
    values_present = bool(_nonempty_mask(values).all()) if len(values) else False
    required = bool(row["required"])
    passed = (not required) or (not require_all_mapped) or ((source_present or default_present) and values_present)
    reason = ""
    if not passed:
        if not source_present and not default_present:
            reason = "required normalized column has no available source column or default value"
        else:
            reason = "required normalized column has blank mapped values"
    check = {
        "normalized_column": row["normalized_column"],
        "source_column": source_column,
        "default_value": default_value,
        "required": required,
        "transform": row["transform"],
        "source_present": source_present,
        "default_present": default_present,
        "values_present": values_present,
        "passed": bool(passed),
        "reason": reason,
    }
    return values.reset_index(drop=True), check


def _normalize_kind(
    mapped: pd.DataFrame,
    canonical_kind: str,
    config: MappedDataConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if canonical_kind == "ticks":
        normalized = normalize_ticks(
            mapped,
            timestamp_unit=config.timestamp_unit,
            timestamp_tz=config.timestamp_tz,
            filter_session=config.filter_session,
            market=config.market,
            market_calendar=config.market_calendar_path,
        )
        return normalized.data, _quarantine_values(normalized.quarantine)
    if canonical_kind == "chain":
        normalized = normalize_option_chain(
            mapped,
            timestamp_unit=config.timestamp_unit,
            timestamp_tz=config.timestamp_tz,
            filter_session=config.filter_session,
            market=config.market,
            market_calendar=config.market_calendar_path,
        )
        return normalized.data, _quarantine_values(normalized.quarantine)
    if canonical_kind == "orders":
        data = _normalize_order_like(
            mapped,
            ts_column="ts_sent_ns",
            required_name="orders",
            config=config,
        )
        return data, _empty_quarantine(total_rows=len(mapped), kept_rows=len(data))
    if canonical_kind == "fills":
        data = _normalize_order_like(
            mapped,
            ts_column="ts_fill_ns",
            required_name="fills",
            config=config,
        )
        return data, _empty_quarantine(total_rows=len(mapped), kept_rows=len(data))
    raise ValueError(f"unsupported mapped data kind {canonical_kind!r}")


def _normalize_order_like(
    mapped: pd.DataFrame,
    *,
    ts_column: str,
    required_name: str,
    config: MappedDataConfig,
) -> pd.DataFrame:
    required = ["client_order_id", "instrument_id", ts_column, "side", "qty", "price"]
    missing = [column for column in required if column not in mapped.columns]
    if missing:
        raise ValueError(f"{required_name} missing required normalized columns: {missing}")
    out = mapped[required].copy()
    out[ts_column] = _to_ns(out[ts_column], unit=config.timestamp_unit, timestamp_tz=config.timestamp_tz)
    out["side"] = out["side"].map(_side_signed).astype("Int64")
    out["qty"] = pd.to_numeric(out["qty"], errors="coerce").astype("Int64")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    null_mask = out[required].isna().any(axis=1)
    out = out.loc[~null_mask].copy()
    out = out.sort_values(ts_column, kind="mergesort").reset_index(drop=True)
    return out


def _summary(
    raw: pd.DataFrame,
    data: pd.DataFrame,
    checks: pd.DataFrame,
    config: MappedDataConfig,
    canonical_kind: str,
    quarantine: dict[str, int],
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 0
    mapped_columns = int(checks["source_present"].astype(bool).sum()) if not checks.empty else 0
    defaulted_columns = int(checks["default_present"].astype(bool).sum()) if not checks.empty else 0
    calendar = resolve_market_calendar(
        config.market_calendar_path,
        market=config.market,
    )
    return pd.DataFrame(
        [
            {
                "ready": bool(failed == 0 and len(data) > 0),
                "adapter": config.adapter,
                "kind": canonical_kind,
                "market": config.market,
                "input_rows": int(len(raw)),
                "output_rows": int(len(data)),
                "required_columns": int(checks["required"].astype(bool).sum()) if not checks.empty else 0,
                "mapped_columns": mapped_columns,
                "defaulted_columns": defaulted_columns,
                "failed_mappings": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "source_column"),
                "primary_blocker_operator": _check_value(primary_blocker, "transform"),
                "primary_blocker_threshold": "required"
                if _to_bool(_check_value(primary_blocker, "required"), default=False)
                else "",
                "primary_blocker_reason": _check_reason(primary_blocker),
                "output_file": config.output_filename,
                **market_calendar_summary(calendar),
                **quarantine,
            }
        ]
    )


def _quarantine_values(report: object) -> dict[str, int]:
    values = asdict(report)
    quarantine = _empty_quarantine(
        total_rows=int(values.get("total_rows", 0)),
        kept_rows=int(values.get("kept_rows", 0)),
    )
    for field in QUARANTINE_SUMMARY_FIELDS:
        if field.startswith("dropped_"):
            quarantine[field] = int(values.get(field, 0))
    quarantine["quarantined_rows"] = (
        quarantine["quarantine_total_rows"] - quarantine["quarantine_kept_rows"]
    )
    return quarantine


def _empty_quarantine(
    *,
    total_rows: int = 0,
    kept_rows: int = 0,
) -> dict[str, int]:
    values = {field: 0 for field in QUARANTINE_SUMMARY_FIELDS}
    values["quarantine_total_rows"] = int(total_rows)
    values["quarantine_kept_rows"] = int(kept_rows)
    values["quarantined_rows"] = int(total_rows - kept_rows)
    return values


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "adapter",
    "kind",
    "market",
    "check",
    "normalized_column",
    "source_column",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    blocked = int((statuses == "blocked").sum()) if not statuses.empty else 0
    ready = int((statuses == "ready").sum()) if not statuses.empty else 0
    review = int((statuses == "review").sum()) if not statuses.empty else 0
    next_gate = _first_action_value(action_queue, "next_gate")
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = ready
    out["blocked_action_count"] = blocked
    out["review_action_count"] = review
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")

    if blocked and _int(out.iloc[0].get("failed_check_count")) == 0:
        blocked_actions = _actions_with_status(action_queue, "blocked")
        primary = blocked_actions.iloc[0] if not blocked_actions.empty else action_queue.iloc[0]
        index = out.index[0]
        out.at[index, "failed_check_count"] = blocked
        out.at[index, "failed_check_names"] = ";".join(
            _text(row.get("check"))
            for row in blocked_actions.to_dict(orient="records")
            if _text(row.get("check"))
        )
        out.at[index, "first_failed_reason"] = _text(primary.get("reason"))
        out.at[index, "primary_blocker_check"] = _text(primary.get("check"))
        out.at[index, "primary_blocker_value"] = _text(primary.get("actual"))
        out.at[index, "primary_blocker_operator"] = _text(primary.get("operator"))
        out.at[index, "primary_blocker_threshold"] = _text(primary.get("expected"))
        out.at[index, "primary_blocker_reason"] = _text(primary.get("reason"))
    return out


def _action_queue(summary_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed_rows = _failed_check_rows(checks)
    for _, row in failed_rows.iterrows():
        rows.append(
            _action_row(
                source="mapped_data_checks",
                component="mapping",
                adapter=_text(summary_row.get("adapter")),
                kind=_text(summary_row.get("kind")),
                market=_text(summary_row.get("market")),
                check=_check_name(row),
                normalized_column=_check_value(row, "normalized_column"),
                source_column=_check_value(row, "source_column"),
                actual=_failed_mapping_actual(row),
                operator=_check_value(row, "transform"),
                expected="required_source_or_default_with_values",
                reason=_check_reason(row),
                recommendation="fix_reviewed_mapping_before_normalizing_vendor_data",
            )
        )

    if not rows and not _to_bool(summary_row.get("ready", False), default=False):
        input_rows = _int(summary_row.get("input_rows"))
        output_rows = _int(summary_row.get("output_rows"))
        if output_rows == 0:
            rows.append(
                _action_row(
                    source="mapped_data_summary",
                    component="normalization",
                    adapter=_text(summary_row.get("adapter")),
                    kind=_text(summary_row.get("kind")),
                    market=_text(summary_row.get("market")),
                    check="normalized_output_empty",
                    normalized_column="",
                    source_column="",
                    actual=f"input_rows={input_rows};output_rows={output_rows}",
                    operator=">",
                    expected="output_rows=0",
                    reason=(
                        "mapped vendor data produced zero normalized rows; review timestamp, session, "
                        "price, quantity, and transform assumptions"
                    ),
                    recommendation="review_mapped_vendor_data_quality_before_research",
                )
            )

    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    source: str,
    component: str,
    adapter: str,
    kind: str,
    market: str,
    check: str,
    normalized_column: str,
    source_column: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "normalize-mapped-data"
    return {
        "queue_status": "blocked",
        "source": source,
        "component": component,
        "adapter": adapter,
        "kind": kind,
        "market": market,
        "check": check,
        "normalized_column": normalized_column,
        "source_column": source_column,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _failed_mapping_actual(row: pd.Series) -> str:
    source_present = _to_bool(row.get("source_present"), default=False)
    default_present = _to_bool(row.get("default_present"), default=False)
    values_present = _to_bool(row.get("values_present"), default=False)
    if not source_present and not default_present:
        return "source_missing_default_missing"
    if not values_present:
        return "blank_mapped_values"
    return "failed"


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    config: MappedDataConfig,
    input_file: Path,
    mapping_file: Path,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready", False), default=False),
        "adapter": _text(summary_row.get("adapter")),
        "kind": _text(summary_row.get("kind")),
        "market": config.market,
        "inputs": {
            "input": str(input_file),
            "mapping": str(mapping_file),
            "market_calendar": config.market_calendar_path or "",
        },
        "market_calendar": {
            "provided": _to_bool(
                summary_row.get("market_calendar_provided", False),
                default=False,
            ),
            "policy": _text(summary_row.get("market_calendar_policy")),
            "id": _text(summary_row.get("market_calendar_id")),
            "path": _text(summary_row.get("market_calendar_path")),
            "sha256": _text(summary_row.get("market_calendar_sha256")),
            "valid_from": _text(summary_row.get("market_calendar_valid_from")),
            "valid_to": _text(summary_row.get("market_calendar_valid_to")),
            "publisher": _text(summary_row.get("market_calendar_publisher")),
            "source_url": _text(summary_row.get("market_calendar_source_url")),
            "published_date": _text(
                summary_row.get("market_calendar_published_date")
            ),
            "closed_dates": _int(
                summary_row.get("market_calendar_closed_dates")
            ),
            "special_open_dates": _int(
                summary_row.get("market_calendar_special_open_dates")
            ),
        },
        "normalization": {
            "input_rows": _int(summary_row.get("input_rows")),
            "output_rows": _int(summary_row.get("output_rows")),
            "output_file": _text(summary_row.get("output_file")),
            "timestamp_unit": config.timestamp_unit,
            "timestamp_tz": config.timestamp_tz or "",
            "filter_session": bool(config.filter_session),
            "require_all_mapped": bool(config.require_all_mapped),
            "quarantine": {
                field: _int(summary_row.get(field))
                for field in QUARANTINE_SUMMARY_FIELDS
            },
        },
        "mapping": {
            "required_columns": _int(summary_row.get("required_columns")),
            "mapped_columns": _int(summary_row.get("mapped_columns")),
            "defaulted_columns": _int(summary_row.get("defaulted_columns")),
            "failed_mappings": _int(summary_row.get("failed_mappings")),
        },
        "failed_check_count": _int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _text(summary_row.get("primary_blocker_check")),
            "value": _text(summary_row.get("primary_blocker_value")),
            "operator": _text(summary_row.get("primary_blocker_operator")),
            "threshold": _text(summary_row.get("primary_blocker_threshold")),
            "reason": _text(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int(summary_row.get("action_queue_count")),
        "ready_action_count": _int(summary_row.get("ready_action_count")),
        "blocked_action_count": _int(summary_row.get("blocked_action_count")),
        "review_action_count": _int(summary_row.get("review_action_count")),
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(summary_row.get("primary_action_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False), default=False) else "no"
    lines = [
        "# Mapped Vendor Data Normalization Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Kind: {_text(summary_row.get('kind'))}",
        f"- Market calendar: {_text(summary_row.get('market_calendar_id')) or 'not provided'}",
        f"- Calendar policy: {_text(summary_row.get('market_calendar_policy'))}",
        f"- Calendar SHA-256: {_text(summary_row.get('market_calendar_sha256'))}",
        f"- Input rows: {_int(summary_row.get('input_rows'))}",
        f"- Output rows: {_int(summary_row.get('output_rows'))}",
        f"- Quarantined rows: {_int(summary_row.get('quarantined_rows'))}",
        f"- Nonpositive strike rows: {_int(summary_row.get('dropped_nonpositive_strike_rows'))}",
        f"- Non-trading-day rows: {_int(summary_row.get('dropped_non_trading_day_rows'))}",
        f"- Calendar-closed rows: {_int(summary_row.get('dropped_calendar_closed_rows'))}",
        f"- Calendar out-of-range rows: {_int(summary_row.get('dropped_calendar_out_of_range_rows'))}",
        f"- Intraday out-of-session rows: {_int(summary_row.get('dropped_out_of_session_rows'))}",
        f"- Failed mappings: {_int(summary_row.get('failed_mappings'))}",
        f"- Blocked actions: {_int(summary_row.get('blocked_action_count'))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No mapped-data actions."
    rows = [
        "| priority | status | check | normalized column | source column | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _text(item.get("priority")),
                    _text(item.get("queue_status")),
                    _text(item.get("check")),
                    _text(item.get("normalized_column")),
                    _text(item.get("source_column")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    failed_mask = ~checks["passed"].map(lambda value: _to_bool(value, default=False))
    return checks.loc[failed_mask].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    normalized = _check_value(row, "normalized_column")
    return f"unmapped_required:{normalized}" if normalized else ""


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _cell(row, column)


def _apply_transform(values: pd.Series, transform: str) -> pd.Series:
    key = transform.strip().lower().replace("-", "_")
    if key in {"", "identity", "none"}:
        return values
    if key == "string":
        return values.astype("string")
    if key == "uppercase":
        return values.astype("string").str.upper()
    if key == "lowercase":
        return values.astype("string").str.lower()
    if key == "int":
        return pd.to_numeric(values, errors="coerce")
    if key == "float":
        return pd.to_numeric(values, errors="coerce")
    if key == "side_text":
        return values.map(_side_text).astype("string")
    if key == "side_signed":
        return values.map(_side_signed).astype("Int64")
    raise ValueError(f"unknown mapped data transform {transform!r}")


def _side_text(value: object) -> object:
    side = _side_signed(value)
    if pd.isna(side):
        return pd.NA
    return "BUY" if int(side) > 0 else "SELL"


def _side_signed(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return pd.NA
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return pd.NA
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return pd.NA


def _schema_kind(kind: str) -> tuple[str, str]:
    key = kind.strip().lower().replace("-", "_")
    try:
        return SCHEMA_KIND_ATTRS[key]
    except KeyError as exc:
        raise ValueError(f"unknown mapped data kind {kind!r}; known kinds: {sorted(SCHEMA_KIND_ATTRS)}") from exc


def _validate_config(config: MappedDataConfig) -> None:
    get_adapter(config.adapter)
    _schema_kind(config.kind)
    resolve_market_calendar(config.market_calendar_path, market=config.market)
    output_name = Path(config.output_filename)
    if not config.output_filename or output_name.name != config.output_filename:
        raise ValueError("output_filename must be a file name without directories")


def _cell(row: pd.Series, column: str) -> str:
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _to_bool(value: object, *, default: bool) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"1", "true", "yes", "y"}
    return bool(value)


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    value = action_queue.iloc[0].get(column)
    return _text(value)


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split_items(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _nonempty_mask(values: pd.Series) -> pd.Series:
    return values.notna() & values.astype("string").str.strip().ne("").fillna(False)
