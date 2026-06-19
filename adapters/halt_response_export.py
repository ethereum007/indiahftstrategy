from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.mapped_order_export import MAPPING_COLUMNS, MappedOrderExportConfig, map_broker_orders
from reports.manifest import write_experiment_manifest


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "adapter",
    "check",
    "action_type",
    "output_file",
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


@dataclass(frozen=True)
class HaltResponseExportConfig:
    adapter: str = "normalized"
    cancel_output_filename: str = "broker_cancel_orders.csv"
    flatten_output_filename: str = "broker_flatten_orders.csv"
    require_response_ready: bool = True
    require_all_mapped: bool = True


@dataclass(frozen=True)
class HaltResponseExportReport:
    cancel_orders: pd.DataFrame
    flatten_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def export_halt_response_actions(
    halt_summary: pd.DataFrame,
    cancel_actions: pd.DataFrame,
    flatten_actions: pd.DataFrame,
    *,
    cancel_mapping: pd.DataFrame | None = None,
    flatten_mapping: pd.DataFrame | None = None,
    config: HaltResponseExportConfig | None = None,
) -> HaltResponseExportReport:
    config = config or HaltResponseExportConfig()
    _validate_config(config)
    _require_summary(halt_summary)
    cancel_actions = cancel_actions.copy().reset_index(drop=True)
    flatten_actions = flatten_actions.copy().reset_index(drop=True)
    cancel_orders, cancel_checks, cancel_schema = _export_action_frame(
        cancel_actions,
        cancel_mapping,
        action_type="cancel",
        output_filename=config.cancel_output_filename,
        config=config,
    )
    flatten_orders, flatten_checks, flatten_schema = _export_action_frame(
        flatten_actions,
        flatten_mapping,
        action_type="flatten",
        output_filename=config.flatten_output_filename,
        config=config,
    )
    checks = pd.concat(
        [
            _response_checks(halt_summary.iloc[0], config),
            cancel_checks,
            flatten_checks,
        ],
        ignore_index=True,
    )
    schema = pd.concat([cancel_schema, flatten_schema], ignore_index=True)
    action_queue = _action_queue(checks, config)
    summary = _summary_with_actions(
        _summary(halt_summary.iloc[0], cancel_orders, flatten_orders, checks, config),
        action_queue,
    )
    export_config = _config(summary.iloc[0], action_queue, config)
    return HaltResponseExportReport(
        cancel_orders=cancel_orders,
        flatten_orders=flatten_orders,
        checks=checks,
        summary=summary,
        schema=schema,
        config=export_config,
        action_queue=action_queue,
    )


def write_halt_response_export(
    *,
    halt_response_dir: str | Path,
    output_dir: str | Path,
    cancel_mapping_path: str | Path | None = None,
    flatten_mapping_path: str | Path | None = None,
    config: HaltResponseExportConfig | None = None,
) -> HaltResponseExportReport:
    config = config or HaltResponseExportConfig()
    _validate_config(config)
    halt_dir = Path(halt_response_dir)
    halt_summary_path = halt_dir / "halt_response_summary.csv"
    cancel_path = halt_dir / "halt_cancel_orders.csv"
    flatten_path = halt_dir / "halt_flatten_orders.csv"
    if not halt_summary_path.exists():
        raise FileNotFoundError(f"halt response summary not found: {halt_summary_path}")
    if not cancel_path.exists():
        raise FileNotFoundError(f"halt cancel orders not found: {cancel_path}")
    if not flatten_path.exists():
        raise FileNotFoundError(f"halt flatten orders not found: {flatten_path}")

    cancel_mapping = _read_mapping(cancel_mapping_path)
    flatten_mapping = _read_mapping(flatten_mapping_path)
    report = export_halt_response_actions(
        pd.read_csv(halt_summary_path),
        pd.read_csv(cancel_path),
        pd.read_csv(flatten_path),
        cancel_mapping=cancel_mapping,
        flatten_mapping=flatten_mapping,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.cancel_orders.to_csv(out / config.cancel_output_filename, index=False)
    report.flatten_orders.to_csv(out / config.flatten_output_filename, index=False)
    report.checks.to_csv(out / "halt_response_export_checks.csv", index=False)
    report.summary.to_csv(out / "halt_response_export_summary.csv", index=False)
    report.schema.to_csv(out / "halt_response_export_schema.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks, config)
    action_queue.to_csv(out / "halt_response_export_action_queue.csv", index=False)
    (out / "halt_response_export_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    export_config = report.config if report.config is not None else _config(report.summary.iloc[0], action_queue, config)
    (out / "halt_response_export_config.json").write_text(
        json.dumps(export_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "halt_response_summary": halt_summary_path,
        "halt_cancel_orders": cancel_path,
        "halt_flatten_orders": flatten_path,
    }
    if cancel_mapping_path is not None:
        inputs["cancel_mapping"] = Path(cancel_mapping_path)
    if flatten_mapping_path is not None:
        inputs["flatten_mapping"] = Path(flatten_mapping_path)
    write_experiment_manifest(
        out,
        run_type="halt_response_export",
        parameters={"config": asdict(config)},
        inputs=inputs,
    )
    return HaltResponseExportReport(
        report.cancel_orders,
        report.flatten_orders,
        report.checks,
        report.summary,
        report.schema,
        out,
        export_config,
        action_queue,
    )


def _export_action_frame(
    actions: pd.DataFrame,
    mapping: pd.DataFrame | None,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if mapping is None:
        return _passthrough_action_frame(actions, action_type=action_type, output_filename=output_filename, config=config)
    targets = _mapping_target_columns(mapping)
    if actions.empty:
        mapped = pd.DataFrame(columns=targets)
        checks = _empty_mapping_checks(mapping, action_type=action_type, output_filename=output_filename)
        schema = _schema_frame(mapped, mapping, action_type=action_type, output_filename=output_filename, config=config)
        return mapped, checks, schema

    mapped = map_broker_orders(
        actions,
        mapping,
        config=MappedOrderExportConfig(
            adapter=config.adapter,
            output_filename=output_filename,
            require_all_mapped=config.require_all_mapped,
        ),
    )
    checks = mapped.checks.copy()
    checks.insert(0, "action_type", action_type)
    checks.insert(1, "output_file", output_filename)
    schema = mapped.schema.copy()
    schema.insert(0, "action_type", action_type)
    schema.insert(1, "output_file", output_filename)
    return mapped.orders, checks, schema


def _passthrough_action_frame(
    actions: pd.DataFrame,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = actions.copy().reset_index(drop=True)
    checks = pd.DataFrame(
        [
            {
                "action_type": action_type,
                "output_file": output_filename,
                "target_column": "*",
                "source_column": "*",
                "default_value": "",
                "required": True,
                "transform": "passthrough",
                "source_present": True,
                "default_present": False,
                "values_present": True,
                "passed": True,
                "reason": "",
            }
        ]
    )
    schema = pd.DataFrame(
        [
            {
                "action_type": action_type,
                "output_file": output_filename,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "target_column": column,
                "source_column": column,
                "default_value": "",
                "required": True,
                "transform": "passthrough",
                "dtype": str(out[column].dtype),
            }
            for column in out.columns
        ]
    )
    return out, checks, schema


def _response_checks(row: pd.Series, config: HaltResponseExportConfig) -> pd.DataFrame:
    response_ready = _to_bool(row.get("ready", False))
    halt_adapter = str(row.get("adapter", "")).strip()
    adapter_consistent = not halt_adapter or config.adapter in {"normalized", halt_adapter}
    return pd.DataFrame(
        [
            _check(
                "response_ready",
                response_ready,
                "is",
                True,
                response_ready or not config.require_response_ready,
                "halt response plan is not ready",
            ),
            _check(
                "adapter_consistent",
                config.adapter,
                "matches",
                halt_adapter or config.adapter,
                adapter_consistent,
                "export adapter does not match halt response adapter",
            ),
        ]
    )


def _summary(
    halt_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    checks: pd.DataFrame,
    config: HaltResponseExportConfig,
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "scenario_key": str(halt_row.get("scenario_key", "")),
                "cancel_orders": int(len(cancel_orders)),
                "flatten_orders": int(len(flatten_orders)),
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator")
                or _check_value(primary_blocker, "transform"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "cancel_output_file": config.cancel_output_filename,
                "flatten_output_file": config.flatten_output_filename,
                "recommendation": "send_halt_actions_to_broker" if ready else "fix_halt_action_export",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(checks: pd.DataFrame, config: HaltResponseExportConfig) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _check_name(row)
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "halt_response_export_checks",
                "component": _component(row),
                "adapter": config.adapter,
                "check": check,
                "action_type": _check_value(row, "action_type"),
                "output_file": _check_value(row, "output_file"),
                "target_column": _check_value(row, "target_column"),
                "source_column": _check_value(row, "source_column"),
                "actual": _failed_action_actual(row),
                "operator": _check_value(row, "transform"),
                "expected": _expected_value(row),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "reason": _check_reason(row),
                "recommendation": _action_recommendation(row),
            }
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _component(row: pd.Series) -> str:
    target = _check_value(row, "target_column")
    action_type = _check_value(row, "action_type")
    if action_type == "response" and target == "response_ready":
        return "halt_response"
    if action_type == "response" and target == "adapter_consistent":
        return "adapter_selection"
    if action_type == "cancel":
        return "cancel_mapping"
    if action_type == "flatten":
        return "flatten_mapping"
    return "halt_response_export"


def _next_gate(check: str) -> str:
    if check == "response:response_ready":
        return "plan-halt-response"
    return "export-halt-response"


def _action_recommendation(row: pd.Series) -> str:
    target = _check_value(row, "target_column")
    action_type = _check_value(row, "action_type")
    if action_type == "response" and target == "response_ready":
        return "repair_or_rerun_halt_response_plan"
    if action_type == "response" and target == "adapter_consistent":
        return "align_export_adapter_with_halt_response_or_use_normalized"
    if action_type == "cancel":
        return "repair_cancel_action_mapping_before_emergency_export"
    if action_type == "flatten":
        return "repair_flatten_action_mapping_before_emergency_export"
    return "repair_halt_response_export_inputs"


def _failed_action_actual(row: pd.Series) -> str:
    if "value" in row.index:
        value = _check_value(row, "value")
        if value:
            return value
    source_present = _to_bool(row.get("source_present"), default=False)
    default_present = _to_bool(row.get("default_present"), default=False)
    values_present = _to_bool(row.get("values_present"), default=False)
    if not source_present and not default_present:
        return "source_missing_default_missing"
    if not values_present:
        return "blank_mapped_values"
    return "failed"


def _expected_value(row: pd.Series) -> str:
    if "threshold" in row.index:
        threshold = _check_value(row, "threshold")
        if threshold:
            return threshold
    return "required_source_or_default_with_values"


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    config: HaltResponseExportConfig,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready"), default=False),
        "adapter": _clean(summary_row.get("adapter")),
        "adapter_schema_status": _clean(summary_row.get("adapter_schema_status")),
        "cancel_output_file": _clean(summary_row.get("cancel_output_file")),
        "flatten_output_file": _clean(summary_row.get("flatten_output_file")),
        "require_response_ready": bool(config.require_response_ready),
        "require_all_mapped": bool(config.require_all_mapped),
        "failed_check_count": _int_value(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _clean(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _clean(summary_row.get("primary_blocker_check")),
            "value": _clean(summary_row.get("primary_blocker_value")),
            "operator": _clean(summary_row.get("primary_blocker_operator")),
            "threshold": _clean(summary_row.get("primary_blocker_threshold")),
            "reason": _clean(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int_value(summary_row.get("action_queue_count")),
        "ready_action_count": _int_value(summary_row.get("ready_action_count")),
        "blocked_action_count": _int_value(summary_row.get("blocked_action_count")),
        "review_action_count": _int_value(summary_row.get("review_action_count")),
        "next_gate": _clean(summary_row.get("next_gate")),
        "next_gate_help_command": _clean(summary_row.get("next_gate_help_command")),
        "primary_action_status": _clean(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary.get("ready"), default=False) else "no"
    lines = [
        "# Halt Response Export Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_clean(summary.get('adapter'))}",
        f"- Schema status: {_clean(summary.get('adapter_schema_status'))}",
        f"- Scenario: {_clean(summary.get('scenario_key'))}",
        f"- Cancel orders: {_int_value(summary.get('cancel_orders'))}",
        f"- Flatten orders: {_int_value(summary.get('flatten_orders'))}",
        f"- Cancel output file: {_code(summary.get('cancel_output_file'))}",
        f"- Flatten output file: {_code(summary.get('flatten_output_file'))}",
        f"- Failed checks: {_int_value(summary.get('failed_check_count'))}",
        f"- Blocked actions: {_int_value(summary.get('blocked_action_count'))}",
        f"- Recommendation: {_clean(summary.get('recommendation'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No halt-response-export actions."
    rows = [
        "| priority | status | component | check | target column | source column | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _clean(item.get("priority")),
                    _clean(item.get("queue_status")),
                    _clean(item.get("component")),
                    _clean(item.get("check")),
                    _clean(item.get("target_column")),
                    _clean(item.get("source_column")),
                    _clean(item.get("actual")),
                    _clean(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _clean(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    return checks.loc[~checks["passed"].map(_to_bool)].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    if row.empty:
        return ""
    explicit = _check_value(row, "check")
    target = explicit or _check_value(row, "target_column")
    action_type = _check_value(row, "action_type")
    output_file = _check_value(row, "output_file")
    pieces = [piece for piece in (action_type, output_file, target) if piece and piece != "*"]
    return ":".join(pieces)


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _clean(action_queue.iloc[0].get(column))


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
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _split_items(value: object) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _clean(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _clean(value)
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _schema_frame(
    mapped: pd.DataFrame,
    mapping: pd.DataFrame,
    *,
    action_type: str,
    output_filename: str,
    config: HaltResponseExportConfig,
) -> pd.DataFrame:
    rows = []
    frame = mapping.copy()
    for column in MAPPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    for row in frame.itertuples(index=False):
        target = _clean(getattr(row, "target_column"))
        if not target:
            continue
        rows.append(
            {
                "action_type": action_type,
                "output_file": output_filename,
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "target_column": target,
                "source_column": _clean(getattr(row, "source_column")),
                "default_value": _clean(getattr(row, "default_value")),
                "required": _to_bool(getattr(row, "required"), default=True),
                "transform": _clean(getattr(row, "transform")) or "identity",
                "dtype": str(mapped[target].dtype) if target in mapped.columns else "object",
            }
        )
    return pd.DataFrame(rows)


def _empty_mapping_checks(mapping: pd.DataFrame, *, action_type: str, output_filename: str) -> pd.DataFrame:
    rows = []
    frame = mapping.copy()
    for column in MAPPING_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    for row in frame.itertuples(index=False):
        rows.append(
            {
                "action_type": action_type,
                "output_file": output_filename,
                "target_column": _clean(getattr(row, "target_column")),
                "source_column": _clean(getattr(row, "source_column")),
                "default_value": _clean(getattr(row, "default_value")),
                "required": _to_bool(getattr(row, "required"), default=True),
                "transform": _clean(getattr(row, "transform")) or "identity",
                "source_present": True,
                "default_present": False,
                "values_present": True,
                "passed": True,
                "reason": "",
            }
        )
    return pd.DataFrame(rows)


def _mapping_target_columns(mapping: pd.DataFrame) -> list[str]:
    if mapping.empty:
        raise ValueError("halt action mapping is empty")
    if "target_column" not in mapping.columns:
        raise ValueError("halt action mapping missing required column: target_column")
    targets = [_clean(value) for value in mapping["target_column"] if _clean(value)]
    if len(targets) != len(set(targets)):
        duplicates = sorted({target for target in targets if targets.count(target) > 1})
        raise ValueError(f"halt action mapping has duplicate target columns: {duplicates}")
    return targets


def _read_mapping(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    mapping_path = Path(path)
    if not mapping_path.exists():
        raise FileNotFoundError(f"halt action mapping not found: {mapping_path}")
    return pd.read_csv(mapping_path)


def _require_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        raise ValueError("halt response summary is empty")
    missing = [column for column in ("ready",) if column not in summary.columns]
    if missing:
        raise ValueError(f"halt response summary missing columns: {missing}")


def _validate_config(config: HaltResponseExportConfig) -> None:
    get_adapter(config.adapter)
    for name in (config.cancel_output_filename, config.flatten_output_filename):
        output_name = Path(name)
        if not name or output_name.name != name:
            raise ValueError("halt action output filenames must be file names without directories")


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "action_type": "response",
        "output_file": "",
        "target_column": name,
        "source_column": "",
        "default_value": "",
        "required": True,
        "transform": operator,
        "source_present": True,
        "default_present": False,
        "values_present": True,
        "passed": bool(passed),
        "reason": "" if passed else reason,
        "value": value,
        "threshold": threshold,
    }


def _to_bool(value: object, *, default: bool = False) -> bool:
    if pd.isna(value):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized in {"1", "true", "yes", "y"}
    return bool(value)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()
