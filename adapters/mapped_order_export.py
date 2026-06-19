from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from reports.manifest import write_experiment_manifest


MAPPING_COLUMNS = ["target_column", "source_column", "default_value", "required", "transform"]


@dataclass(frozen=True)
class MappedOrderExportConfig:
    adapter: str = "normalized"
    output_filename: str = "mapped_broker_orders.csv"
    require_all_mapped: bool = True


@dataclass(frozen=True)
class MappedOrderExportReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def map_broker_orders(
    broker_orders: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    config: MappedOrderExportConfig | None = None,
) -> MappedOrderExportReport:
    config = config or MappedOrderExportConfig()
    _validate_config(config)
    rows = _mapping_rows(mapping)
    mapped: dict[str, pd.Series] = {}
    checks = []
    for row in rows:
        series, check = _map_column(broker_orders, row, require_all_mapped=config.require_all_mapped)
        mapped[row["target_column"]] = series
        checks.append(check)

    orders = pd.DataFrame(mapped)
    checks_frame = pd.DataFrame(checks)
    summary = _summary(orders, checks_frame, config)
    action_queue = _action_queue(summary.iloc[0], checks_frame)
    summary = _summary_with_actions(summary, action_queue)
    schema = _schema_frame(orders, checks_frame, config)
    return MappedOrderExportReport(
        orders=orders,
        checks=checks_frame,
        summary=summary,
        schema=schema,
        action_queue=action_queue,
    )


def write_mapped_order_export(
    export_path: str | Path,
    mapping_path: str | Path,
    *,
    output_dir: str | Path,
    config: MappedOrderExportConfig | None = None,
) -> MappedOrderExportReport:
    config = config or MappedOrderExportConfig()
    _validate_config(config)
    orders_file = _broker_orders_path(export_path)
    mapping_file = Path(mapping_path)
    if not mapping_file.exists():
        raise FileNotFoundError(f"mapped order export mapping not found: {mapping_file}")
    broker_orders = pd.read_csv(orders_file)
    mapping = pd.read_csv(mapping_file)
    report = map_broker_orders(broker_orders, mapping, config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "mapped_order_checks.csv", index=False)
    report.summary.to_csv(out / "mapped_order_summary.csv", index=False)
    report.schema.to_csv(out / "mapped_order_schema.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.checks)
    )
    action_queue.to_csv(out / "mapped_order_action_queue.csv", index=False)
    (out / "mapped_order_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], action_queue, config, orders_file, mapping_file),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "mapped_order_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="mapped_order_export",
        parameters={"config": asdict(config)},
        inputs={"broker_orders": orders_file, "mapping": mapping_file},
    )
    return MappedOrderExportReport(
        report.orders,
        report.checks,
        report.summary,
        report.schema,
        out,
        action_queue,
    )


def _mapping_rows(mapping: pd.DataFrame) -> list[dict[str, Any]]:
    if mapping.empty:
        raise ValueError("mapped order export mapping is empty")
    if "target_column" not in mapping.columns:
        raise ValueError("mapped order export mapping missing required column: target_column")
    frame = mapping.copy()
    for column in MAPPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    rows: list[dict[str, Any]] = []
    targets = []
    for index, row in frame.iterrows():
        target = _cell(row, "target_column")
        if not target:
            raise ValueError(f"mapped order export mapping row {index} has blank target_column")
        targets.append(target)
        rows.append(
            {
                "target_column": target,
                "source_column": _cell(row, "source_column"),
                "default_value": _cell(row, "default_value"),
                "required": _to_bool(row.get("required", True), default=True),
                "transform": _cell(row, "transform").lower() or "identity",
            }
        )
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        raise ValueError(f"mapped order export mapping has duplicate target columns: {duplicates}")
    return rows


def _map_column(
    broker_orders: pd.DataFrame,
    row: dict[str, Any],
    *,
    require_all_mapped: bool,
) -> tuple[pd.Series, dict[str, Any]]:
    source_column = str(row["source_column"])
    default_value = str(row["default_value"])
    source_present = bool(source_column and source_column in broker_orders.columns)
    default_present = bool(default_value)
    if source_present:
        values = broker_orders[source_column].copy()
    else:
        values = pd.Series([pd.NA] * len(broker_orders), index=broker_orders.index)
    if default_present:
        values = values.mask(~_nonempty_mask(values), default_value)
    values = _apply_transform(values, str(row["transform"]))
    values_present = bool(_nonempty_mask(values).all()) if len(values) else False
    required = bool(row["required"])
    passed = (not required) or (not require_all_mapped) or ((source_present or default_present) and values_present)
    reason = ""
    if not passed:
        if not source_present and not default_present:
            reason = "required target has no available source column or default value"
        else:
            reason = "required target has blank mapped values"
    check = {
        "target_column": row["target_column"],
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


def _summary(orders: pd.DataFrame, checks: pd.DataFrame, config: MappedOrderExportConfig) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed_mappings = int(len(failed_rows)) if not checks.empty else 0
    ready = bool(len(orders) > 0 and failed_mappings == 0)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "orders": int(len(orders)),
                "target_columns": int(len(orders.columns)),
                "mapped_columns": int(checks["source_present"].astype(bool).sum()) if not checks.empty else 0,
                "defaulted_columns": int(checks["default_present"].astype(bool).sum()) if not checks.empty else 0,
                "failed_mappings": failed_mappings,
                "failed_check_count": failed_mappings,
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
                source="mapped_order_checks",
                component="mapping",
                adapter=_text(summary_row.get("adapter")),
                check=f"unmapped_required:{target}" if target else "",
                target_column=target,
                source_column=_check_value(row, "source_column"),
                actual=_failed_mapping_actual(row),
                operator=_check_value(row, "transform"),
                expected="required_source_or_default_with_values",
                reason=_check_reason(row),
                recommendation="fix_mapped_order_export_mapping_before_broker_upload",
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
    next_gate = "map-broker-orders"
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
    config: MappedOrderExportConfig,
    orders_file: Path,
    mapping_file: Path,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready"), default=False),
        "adapter": _text(summary_row.get("adapter")),
        "adapter_schema_status": _text(summary_row.get("adapter_schema_status")),
        "inputs": {
            "broker_orders": str(orders_file),
            "mapping": str(mapping_file),
        },
        "mapping": {
            "output_file": _text(summary_row.get("output_file")),
            "orders": _int(summary_row.get("orders")),
            "target_columns": _int(summary_row.get("target_columns")),
            "mapped_columns": _int(summary_row.get("mapped_columns")),
            "defaulted_columns": _int(summary_row.get("defaulted_columns")),
            "failed_mappings": _int(summary_row.get("failed_mappings")),
            "require_all_mapped": bool(config.require_all_mapped),
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
    ready_label = "yes" if _to_bool(summary_row.get("ready"), default=False) else "no"
    lines = [
        "# Mapped Broker Order Export Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Schema status: {_text(summary_row.get('adapter_schema_status'))}",
        f"- Orders: {_int(summary_row.get('orders'))}",
        f"- Target columns: {_int(summary_row.get('target_columns'))}",
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
        return "No mapped-order actions."
    rows = [
        "| priority | status | check | target column | source column | next gate | help | reason |",
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
                    _text(item.get("target_column")),
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
    return _check_value(row, "target_column")


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _cell(row, column)


def _schema_frame(orders: pd.DataFrame, checks: pd.DataFrame, config: MappedOrderExportConfig) -> pd.DataFrame:
    rows = []
    for check in checks.itertuples():
        rows.append(
            {
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "target_column": check.target_column,
                "source_column": check.source_column,
                "default_value": check.default_value,
                "required": bool(check.required),
                "transform": check.transform,
                "dtype": str(orders[check.target_column].dtype),
            }
        )
    return pd.DataFrame(rows)


def _apply_transform(values: pd.Series, transform: str) -> pd.Series:
    key = transform.strip().lower().replace("-", "_")
    if key in {"", "identity", "none"}:
        return values
    if key == "uppercase":
        return values.astype("string").str.upper()
    if key == "lowercase":
        return values.astype("string").str.lower()
    if key == "string":
        return values.astype("string")
    if key == "int":
        return pd.to_numeric(values, errors="coerce").astype("Int64")
    if key == "float":
        return pd.to_numeric(values, errors="coerce")
    if key == "side_text":
        return values.map(_side_text).astype("string")
    if key == "side_signed":
        return values.map(_side_signed).astype("Int64")
    raise ValueError(f"unknown mapped order export transform {transform!r}")


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


def _broker_orders_path(export_path: str | Path) -> Path:
    path = Path(export_path)
    if path.is_dir():
        path = path / "broker_orders.csv"
    if not path.exists():
        raise FileNotFoundError(f"broker order export not found: {path}")
    return path


def _validate_config(config: MappedOrderExportConfig) -> None:
    get_adapter(config.adapter)
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


def _nonempty_mask(values: pd.Series) -> pd.Series:
    return values.notna() & values.astype("string").str.strip().ne("").fillna(False)
