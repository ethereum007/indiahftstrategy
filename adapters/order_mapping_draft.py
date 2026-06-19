from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.mapped_order_export import MAPPING_COLUMNS
from reports.manifest import write_experiment_manifest


DRAFT_COLUMNS = [
    *MAPPING_COLUMNS,
    "confidence",
    "status",
    "notes",
]


@dataclass(frozen=True)
class OrderMappingDraftConfig:
    adapter: str = "normalized"
    output_filename: str = "order_mapping_draft.csv"
    required_columns: tuple[str, ...] = ()
    optional_columns: tuple[str, ...] = ()
    default_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderMappingDraftReport:
    mapping: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def draft_order_mapping(
    broker_orders: pd.DataFrame,
    sample_columns: list[str],
    *,
    config: OrderMappingDraftConfig | None = None,
) -> OrderMappingDraftReport:
    config = config or OrderMappingDraftConfig()
    _validate_config(config)
    targets = [str(column) for column in sample_columns]
    if not targets:
        raise ValueError("vendor order sample has no columns")
    _validate_requested_columns(targets, config)

    source_columns = [str(column) for column in broker_orders.columns]
    source_lookup = _key_lookup(source_columns)
    defaults = {_key(column): str(value) for column, value in config.default_values.items()}
    required_keys = {_key(column) for column in config.required_columns}
    optional_keys = {_key(column) for column in config.optional_columns}

    mapping_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    for target in targets:
        required = _is_required(target, required_keys, optional_keys)
        suggestion = _suggest_mapping(target, source_lookup, defaults)
        source_column = suggestion["source_column"]
        default_value = suggestion["default_value"]
        source_present = bool(source_column and source_column in source_columns)
        default_present = bool(default_value)
        mapped = source_present or default_present
        passed = mapped or not required
        status = _status(required, source_present, default_present)
        notes = _notes(required, passed, suggestion["confidence"], source_column, default_value)
        mapping_rows.append(
            {
                "target_column": target,
                "source_column": source_column,
                "default_value": default_value,
                "required": bool(required),
                "transform": suggestion["transform"],
                "confidence": suggestion["confidence"],
                "status": status,
                "notes": notes,
            }
        )
        check_rows.append(
            {
                "target_column": target,
                "required": bool(required),
                "source_column": source_column,
                "source_present": source_present,
                "default_present": default_present,
                "mapped": mapped,
                "passed": passed,
                "reason": "" if passed else "required vendor column is not mapped to a source or default",
            }
        )

    mapping = pd.DataFrame(mapping_rows, columns=DRAFT_COLUMNS)
    checks = pd.DataFrame(check_rows)
    summary = _summary(mapping, checks, config)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    return OrderMappingDraftReport(
        mapping=mapping,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
    )


def write_order_mapping_draft(
    export_path: str | Path,
    sample_path: str | Path,
    *,
    output_dir: str | Path,
    config: OrderMappingDraftConfig | None = None,
) -> OrderMappingDraftReport:
    config = config or OrderMappingDraftConfig()
    _validate_config(config)
    orders_file = _broker_orders_path(export_path)
    sample_file = Path(sample_path)
    if not sample_file.exists():
        raise FileNotFoundError(f"vendor order sample not found: {sample_file}")

    broker_orders = pd.read_csv(orders_file)
    sample = pd.read_csv(sample_file, nrows=0)
    report = draft_order_mapping(broker_orders, list(sample.columns), config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.mapping.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "order_mapping_draft_checks.csv", index=False)
    report.summary.to_csv(out / "order_mapping_draft_summary.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.checks)
    )
    action_queue.to_csv(out / "order_mapping_draft_action_queue.csv", index=False)
    (out / "order_mapping_draft_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], action_queue, config, orders_file, sample_file),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "order_mapping_draft_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="order_mapping_draft",
        parameters={"config": asdict(config)},
        inputs={"broker_orders": orders_file, "sample": sample_file},
    )
    return OrderMappingDraftReport(report.mapping, report.checks, report.summary, out, action_queue)


def _suggest_mapping(target: str, source_lookup: dict[str, str], defaults: dict[str, str]) -> dict[str, str]:
    target_key = _key(target)
    default_value = defaults.get(target_key, "")
    if default_value:
        return {
            "source_column": "",
            "default_value": default_value,
            "transform": "identity",
            "confidence": "manual_default",
        }

    alias = _alias_suggestion(target_key, source_lookup)
    if alias is not None:
        return alias

    source_column = source_lookup.get(target_key, "")
    if source_column:
        return {
            "source_column": source_column,
            "default_value": "",
            "transform": _transform_for_source(source_column, target_key),
            "confidence": "exact",
        }

    return {
        "source_column": "",
        "default_value": "",
        "transform": "identity",
        "confidence": "none",
    }


def _alias_suggestion(target_key: str, source_lookup: dict[str, str]) -> dict[str, str] | None:
    aliases = {
        "symbol": [("instrument_id", "string")],
        "tradingsymbol": [("instrument_id", "string")],
        "tradingsymbolname": [("instrument_id", "string")],
        "instrument": [("instrument_id", "string")],
        "instrumentid": [("instrument_id", "string")],
        "security": [("instrument_id", "string")],
        "securityid": [("instrument_id", "string")],
        "contract": [("instrument_id", "string")],
        "transactiontype": [("side", "side_text")],
        "orderside": [("side", "side_text")],
        "buysell": [("side", "side_text")],
        "buysellindicator": [("side", "side_text")],
        "action": [("side", "side_text")],
        "side": [("side", "side_text")],
        "quantity": [("qty", "int")],
        "orderquantity": [("qty", "int")],
        "orderqty": [("qty", "int")],
        "qty": [("qty", "int")],
        "limitprice": [("price", "float")],
        "orderprice": [("price", "float")],
        "price": [("price", "float")],
        "validity": [("time_in_force", "uppercase")],
        "timeinforce": [("time_in_force", "uppercase")],
        "tif": [("time_in_force", "uppercase")],
        "ordertype": [("order_type", "uppercase")],
        "type": [("order_type", "uppercase")],
        "clientorderid": [("client_order_id", "string")],
        "clientid": [("client_order_id", "string")],
        "clordid": [("client_order_id", "string")],
        "tag": [("client_order_id", "string")],
        "remarks": [("client_order_id", "string")],
    }
    for source_name, transform in aliases.get(target_key, []):
        source_column = source_lookup.get(_key(source_name), "")
        if source_column:
            return {
                "source_column": source_column,
                "default_value": "",
                "transform": transform,
                "confidence": "alias",
            }
    return None


def _transform_for_source(source_column: str, target_key: str) -> str:
    source_key = _key(source_column)
    if source_key in {"qty", "quantity", "orderqty", "orderquantity"}:
        return "int"
    if source_key in {"price", "limitprice", "orderprice"}:
        return "float"
    if source_key == "side":
        return "side_text" if target_key != "sidesigned" else "side_signed"
    if source_key == "sidetext":
        return "uppercase"
    if source_key in {"ordertype", "timeinforce", "validity", "tif"}:
        return "uppercase"
    if source_key in {"instrumentid", "clientorderid", "brokerorderid", "launchorderid"}:
        return "string"
    return "identity"


def _summary(
    mapping: pd.DataFrame,
    checks: pd.DataFrame,
    config: OrderMappingDraftConfig,
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 0
    required = int(checks["required"].astype(bool).sum()) if not checks.empty else 0
    mapped_required = int((checks["required"].astype(bool) & checks["mapped"].astype(bool)).sum())
    defaulted = int((checks["default_present"].astype(bool)).sum()) if not checks.empty else 0
    mapped = int((checks["mapped"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": bool(len(mapping) > 0 and failed == 0),
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "vendor_columns": int(len(mapping)),
                "required_columns": required,
                "mapped_columns": mapped,
                "mapped_required_columns": mapped_required,
                "defaulted_columns": defaulted,
                "unmapped_required_columns": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "target_column"),
                "primary_blocker_operator": "mapped",
                "primary_blocker_threshold": "source_or_default",
                "primary_blocker_reason": _check_reason(primary_blocker),
                "output_file": config.output_filename,
            }
        ]
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "adapter",
    "check",
    "target_column",
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
    return out


def _action_queue(summary_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed_rows = _failed_check_rows(checks)
    for _, row in failed_rows.iterrows():
        target = _check_value(row, "target_column")
        rows.append(
            _action_row(
                source="order_mapping_draft_checks",
                component="mapping",
                adapter=_text(summary_row.get("adapter")),
                check=_check_name(row),
                target_column=target,
                source_column=_check_value(row, "source_column"),
                actual="source_missing_default_missing",
                operator="mapped",
                expected="source_or_default",
                reason=_check_reason(row),
                recommendation="complete_vendor_order_mapping_before_upload_export",
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
    check: str,
    target_column: str,
    source_column: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "draft-order-mapping"
    return {
        "queue_status": "blocked",
        "source": source,
        "component": component,
        "adapter": adapter,
        "check": check,
        "target_column": target_column,
        "source_column": source_column,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    config: OrderMappingDraftConfig,
    orders_file: Path,
    sample_file: Path,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready")),
        "adapter": _text(summary_row.get("adapter")),
        "adapter_schema_status": _text(summary_row.get("adapter_schema_status")),
        "inputs": {
            "broker_orders": str(orders_file),
            "sample": str(sample_file),
        },
        "mapping": {
            "output_file": _text(summary_row.get("output_file")),
            "vendor_columns": _int(summary_row.get("vendor_columns")),
            "required_columns": _int(summary_row.get("required_columns")),
            "mapped_columns": _int(summary_row.get("mapped_columns")),
            "mapped_required_columns": _int(summary_row.get("mapped_required_columns")),
            "defaulted_columns": _int(summary_row.get("defaulted_columns")),
            "unmapped_required_columns": _int(summary_row.get("unmapped_required_columns")),
            "requested_required_columns": list(config.required_columns),
            "requested_optional_columns": list(config.optional_columns),
            "default_values": dict(config.default_values),
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
    ready_label = "yes" if _to_bool(summary_row.get("ready")) else "no"
    lines = [
        "# Order Mapping Draft Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Schema status: {_text(summary_row.get('adapter_schema_status'))}",
        f"- Vendor columns: {_int(summary_row.get('vendor_columns'))}",
        f"- Required columns: {_int(summary_row.get('required_columns'))}",
        f"- Mapped required columns: {_int(summary_row.get('mapped_required_columns'))}",
        f"- Unmapped required columns: {_int(summary_row.get('unmapped_required_columns'))}",
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
        return "No order-mapping actions."
    rows = [
        "| priority | status | check | target column | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _text(item.get("priority")),
                    _text(item.get("queue_status")),
                    _text(item.get("check")),
                    _text(item.get("target_column")),
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
    failed_mask = ~checks["passed"].map(_to_bool)
    return checks.loc[failed_mask].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    target = _check_value(row, "target_column")
    return f"unmapped_required:{target}" if target else ""


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _is_required(target: str, required_keys: set[str], optional_keys: set[str]) -> bool:
    target_key = _key(target)
    if target_key in optional_keys:
        return False
    if required_keys:
        return target_key in required_keys
    return True


def _status(required: bool, source_present: bool, default_present: bool) -> str:
    if source_present:
        return "mapped"
    if default_present:
        return "defaulted"
    return "unmapped_required" if required else "unmapped_optional"


def _notes(
    required: bool,
    passed: bool,
    confidence: str,
    source_column: str,
    default_value: str,
) -> str:
    if not passed:
        return "review vendor schema and supply source_column or default_value before mapping export"
    if default_value:
        return "manual default supplied; verify against vendor order-entry semantics"
    if source_column and confidence in {"alias", "exact"}:
        return "suggested mapping; review before submitting to a broker or paper adapter"
    if not required:
        return "optional vendor column left blank"
    return ""


def _validate_config(config: OrderMappingDraftConfig) -> None:
    get_adapter(config.adapter)
    output_name = Path(config.output_filename)
    if not config.output_filename or output_name.name != config.output_filename:
        raise ValueError("output_filename must be a file name without directories")
    overlap = {_key(column) for column in config.required_columns} & {
        _key(column) for column in config.optional_columns
    }
    if overlap:
        raise ValueError(f"columns cannot be both required and optional: {sorted(overlap)}")
    for target in config.default_values:
        if not str(target).strip():
            raise ValueError("default_values contains a blank target column")


def _validate_requested_columns(targets: list[str], config: OrderMappingDraftConfig) -> None:
    target_keys = {_key(column) for column in targets}
    requested = {
        *_requested_column_rows(config.required_columns, "required"),
        *_requested_column_rows(config.optional_columns, "optional"),
        *_requested_column_rows(config.default_values.keys(), "default"),
    }
    missing = [f"{kind}:{column}" for kind, column in requested if _key(column) not in target_keys]
    if missing:
        raise ValueError(f"requested mapping columns are not in vendor sample: {missing}")


def _requested_column_rows(columns: Any, kind: str) -> list[tuple[str, str]]:
    return [(kind, str(column)) for column in columns]


def _broker_orders_path(export_path: str | Path) -> Path:
    path = Path(export_path)
    if path.is_dir():
        path = path / "broker_orders.csv"
    if not path.exists():
        raise FileNotFoundError(f"broker order export not found: {path}")
    return path


def _key_lookup(columns: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        lookup.setdefault(_key(column), column)
    return lookup


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _text(action_queue.iloc[0].get(column))


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


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())
