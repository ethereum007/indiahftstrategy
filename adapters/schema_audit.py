from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from reports.manifest import write_experiment_manifest


SCHEMA_KIND_ATTRS = {
    "tick": ("ticks", "tick_column_map"),
    "ticks": ("ticks", "tick_column_map"),
    "top_of_book": ("ticks", "tick_column_map"),
    "chain": ("chain", "chain_column_map"),
    "option_chain": ("chain", "chain_column_map"),
    "options": ("chain", "chain_column_map"),
    "order": ("orders", "simulated_order_column_map"),
    "orders": ("orders", "simulated_order_column_map"),
    "simulated_orders": ("orders", "simulated_order_column_map"),
    "fill": ("fills", "live_fill_column_map"),
    "fills": ("fills", "live_fill_column_map"),
    "live_fills": ("fills", "live_fill_column_map"),
}


@dataclass(frozen=True)
class AdapterSchemaAudit:
    adapter: str
    kind: str
    columns: pd.DataFrame
    summary: pd.DataFrame
    template: pd.DataFrame
    checklist: pd.DataFrame
    action_queue: pd.DataFrame | None = None
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["all_required_present"])


def audit_adapter_schema(
    sample: pd.DataFrame,
    *,
    adapter: str = "normalized",
    kind: str = "ticks",
) -> AdapterSchemaAudit:
    spec = get_adapter(adapter)
    canonical_kind, attr = _schema_kind(kind)
    column_map: dict[str, str] = getattr(spec, attr)
    sample_columns = [str(column) for column in sample.columns]
    rows = _column_rows(sample_columns, column_map)
    columns = pd.DataFrame(rows)
    template = _mapping_template(columns, spec.name, canonical_kind)
    summary = _summary(sample_columns, columns, spec.name, canonical_kind)
    checklist = _review_checklist(summary, template)
    action_queue = _action_queue(summary.iloc[0], columns)
    summary = _summary_with_actions(summary, action_queue)
    return AdapterSchemaAudit(
        adapter=spec.name,
        kind=canonical_kind,
        columns=columns,
        summary=summary,
        template=template,
        checklist=checklist,
        action_queue=action_queue,
    )


def write_adapter_schema_audit(
    sample_path: str | Path,
    output_dir: str | Path,
    *,
    adapter: str = "normalized",
    kind: str = "ticks",
) -> AdapterSchemaAudit:
    sample_file = Path(sample_path)
    if not sample_file.exists():
        raise FileNotFoundError(f"adapter schema sample not found: {sample_file}")
    sample = pd.read_csv(sample_file, nrows=0)
    report = audit_adapter_schema(sample, adapter=adapter, kind=kind)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.summary.to_csv(out / "adapter_schema_summary.csv", index=False)
    report.columns.to_csv(out / "adapter_schema_columns.csv", index=False)
    report.template.to_csv(out / "adapter_mapping_template.csv", index=False)
    report.checklist.to_csv(out / "adapter_schema_review_checklist.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.columns)
    )
    action_queue.to_csv(out / "adapter_schema_action_queue.csv", index=False)
    (out / "adapter_schema_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], report.columns, action_queue),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "adapter_schema_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="adapter_schema_audit",
        parameters={
            "adapter": report.adapter,
            "kind": report.kind,
            "adapter_schema_status": adapter_schema_status(report.adapter),
            "all_required_present": report.passed,
        },
        inputs={"sample": sample_file},
    )
    return AdapterSchemaAudit(
        adapter=report.adapter,
        kind=report.kind,
        columns=report.columns,
        summary=report.summary,
        template=report.template,
        checklist=report.checklist,
        action_queue=action_queue,
        output_dir=out,
    )


def _schema_kind(kind: str) -> tuple[str, str]:
    key = kind.strip().lower().replace("-", "_")
    try:
        return SCHEMA_KIND_ATTRS[key]
    except KeyError as exc:
        raise ValueError(f"unknown adapter schema kind {kind!r}; known kinds: {sorted(SCHEMA_KIND_ATTRS)}") from exc


def _column_rows(sample_columns: list[str], column_map: dict[str, str]) -> list[dict[str, object]]:
    folded = _casefold_lookup(sample_columns)
    rows = []
    for normalized_column, expected_source_column in column_map.items():
        source = str(expected_source_column)
        matched_source_column = ""
        match_type = "missing"
        if source in sample_columns:
            matched_source_column = source
            match_type = "exact"
        else:
            match = folded.get(source.casefold())
            if match is not None:
                matched_source_column = match
                match_type = "case_insensitive"
        rows.append(
            {
                "normalized_column": str(normalized_column),
                "expected_source_column": source,
                "present": bool(matched_source_column),
                "matched_source_column": matched_source_column,
                "match_type": match_type,
                "required": True,
            }
        )
    return rows


def _casefold_lookup(columns: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        lookup.setdefault(column.casefold(), column)
    return lookup


def _mapping_template(columns: pd.DataFrame, adapter: str, kind: str) -> pd.DataFrame:
    status = adapter_schema_status(adapter)
    rows = []
    for row in columns.itertuples():
        mapped = bool(row.present)
        rows.append(
            {
                "adapter": adapter,
                "kind": kind,
                "adapter_schema_status": status,
                "normalized_column": row.normalized_column,
                "source_column": row.matched_source_column if mapped else row.expected_source_column,
                "status": "mapped" if mapped else "missing",
                "notes": _template_note(status, mapped),
            }
        )
    return pd.DataFrame(rows)


def _summary(sample_columns: list[str], columns: pd.DataFrame, adapter: str, kind: str) -> pd.DataFrame:
    present = columns["present"].astype(bool) if not columns.empty else pd.Series(dtype=bool)
    matched = {str(value) for value in columns.loc[present, "matched_source_column"]}
    missing_rows = columns.loc[~present].copy().reset_index(drop=True)
    missing = [str(value) for value in missing_rows["expected_source_column"]]
    primary_blocker = _first_missing_required(missing_rows)
    extra = [column for column in sample_columns if column not in matched]
    required_count = int(len(columns))
    present_count = int(present.sum()) if required_count else 0
    failed = int(len(missing_rows))
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": kind,
                "adapter_schema_status": adapter_schema_status(adapter),
                "source_columns": int(len(sample_columns)),
                "required_columns": required_count,
                "present_required_columns": present_count,
                "missing_required_columns": failed,
                "failed_check_count": failed,
                "failed_check_names": _missing_check_names(missing_rows),
                "first_failed_reason": _missing_reason(primary_blocker),
                "primary_blocker_check": _missing_check_name(primary_blocker),
                "primary_blocker_value": _missing_value(primary_blocker, "expected_source_column"),
                "primary_blocker_operator": "present",
                "primary_blocker_threshold": "required",
                "primary_blocker_reason": _missing_reason(primary_blocker),
                "extra_columns": int(len(extra)),
                "pass_rate": float(present_count / required_count) if required_count else 0.0,
                "all_required_present": bool(failed == 0),
                "missing_source_columns": ";".join(missing),
                "extra_source_columns": ";".join(extra),
            }
        ]
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
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
    review = int((statuses == "review").sum()) if not statuses.empty else 0
    next_gate = _first_action_value(action_queue, "next_gate")
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = 0
    out["blocked_action_count"] = blocked
    out["review_action_count"] = review
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(summary_row: pd.Series, columns: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not columns.empty:
        for item in columns.loc[~columns["present"].astype(bool)].to_dict(orient="records"):
            normalized = _text(item.get("normalized_column"))
            source = _text(item.get("expected_source_column"))
            rows.append(
                _action_row(
                    queue_status="blocked",
                    source="adapter_schema_columns",
                    component="schema_audit",
                    check=f"missing_required:{source}",
                    normalized_column=normalized,
                    source_column=source,
                    actual=False,
                    operator="present",
                    expected=True,
                    reason=f"{source} source column is missing for {normalized}",
                    recommendation="request_vendor_field_or_update_adapter_schema",
                )
            )

    schema_status = _text(summary_row.get("adapter_schema_status"))
    if schema_status == "placeholder_normalized_pending_vendor_schema":
        rows.append(
            _action_row(
                queue_status="blocked",
                source="adapter_schema_summary",
                component="schema_review",
                check="vendor_schema_reviewed",
                normalized_column="",
                source_column="",
                actual=schema_status,
                operator="reviewed_schema",
                expected="native_vendor_schema",
                reason="adapter is still using normalized placeholders; review real Arrow.money/iRage source columns",
                recommendation="replace_placeholder_adapter_schema",
            )
        )

    for source in _split_items(summary_row.get("extra_source_columns")):
        rows.append(
            _action_row(
                queue_status="review",
                source="adapter_schema_summary",
                component="extra_columns",
                check=f"extra_column:{source}",
                normalized_column="",
                source_column=source,
                actual=source,
                operator="classified",
                expected="approved_or_ignored",
                reason=f"{source} extra vendor column needs classification or ignore approval",
                recommendation="classify_extra_vendor_columns",
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
    queue_status: str,
    source: str,
    component: str,
    check: str,
    normalized_column: str,
    source_column: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "audit-adapter-schema"
    return {
        "queue_status": queue_status,
        "source": source,
        "component": component,
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


def _config(summary_row: pd.Series, columns: pd.DataFrame, action_queue: pd.DataFrame) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "passed": _to_bool(summary_row.get("all_required_present", False)),
        "adapter": _text(summary_row.get("adapter")),
        "kind": _text(summary_row.get("kind")),
        "adapter_schema_status": _text(summary_row.get("adapter_schema_status")),
        "columns": {
            "source_columns": _int(summary_row.get("source_columns")),
            "required_columns": _int(summary_row.get("required_columns")),
            "present_required_columns": _int(summary_row.get("present_required_columns")),
            "missing_required_columns": _int(summary_row.get("missing_required_columns")),
            "missing_source_columns": _split_items(summary_row.get("missing_source_columns")),
            "extra_columns": _int(summary_row.get("extra_columns")),
            "extra_source_columns": _split_items(summary_row.get("extra_source_columns")),
            "pass_rate": _float(summary_row.get("pass_rate")),
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
        "schema_columns": _schema_column_records(columns),
    }


def _schema_column_records(columns: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {
            "normalized_column": _text(item.get("normalized_column")),
            "expected_source_column": _text(item.get("expected_source_column")),
            "matched_source_column": _text(item.get("matched_source_column")),
            "present": _to_bool(item.get("present", False)),
            "match_type": _text(item.get("match_type")),
        }
        for item in columns.to_dict(orient="records")
    ]


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    passed_label = "yes" if _to_bool(summary_row.get("all_required_present", False)) else "no"
    lines = [
        "# Adapter Schema Audit Runbook",
        "",
        f"- Required columns present: {passed_label}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Kind: {_text(summary_row.get('kind'))}",
        f"- Schema status: {_text(summary_row.get('adapter_schema_status'))}",
        f"- Missing required columns: {_int(summary_row.get('missing_required_columns'))}",
        f"- Extra columns: {_int(summary_row.get('extra_columns'))}",
        f"- Blocked actions: {_int(summary_row.get('blocked_action_count'))}",
        f"- Review actions: {_int(summary_row.get('review_action_count'))}",
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
        return "No schema actions."
    rows = [
        "| priority | status | check | source column | next gate | help | reason |",
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
                    _text(item.get("source_column")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _first_missing_required(missing_rows: pd.DataFrame) -> pd.Series:
    if missing_rows.empty:
        return pd.Series(dtype=object)
    return missing_rows.iloc[0]


def _missing_check_names(missing_rows: pd.DataFrame) -> str:
    names = [_missing_check_name(row) for _, row in missing_rows.iterrows()]
    return ";".join(name for name in names if name)


def _missing_check_name(row: pd.Series) -> str:
    source = _missing_value(row, "expected_source_column")
    return f"missing_required:{source}" if source else ""


def _missing_reason(row: pd.Series) -> str:
    source = _missing_value(row, "expected_source_column")
    normalized = _missing_value(row, "normalized_column")
    if not source:
        return ""
    return f"{source} source column is missing for {normalized}" if normalized else f"{source} source column is missing"


def _missing_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _review_checklist(summary: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    row = summary.iloc[0]
    schema_status = str(row["adapter_schema_status"])
    missing_required = int(row["missing_required_columns"])
    extra_columns = int(row["extra_columns"])
    placeholder = schema_status == "placeholder_normalized_pending_vendor_schema"
    missing_mappings = int((template["status"].astype(str) == "missing").sum()) if not template.empty else 0
    checks = [
        _check(
            "required_columns_present",
            passed=missing_required == 0,
            status="pass" if missing_required == 0 else "blocked",
            detail="all required source columns are present"
            if missing_required == 0
            else f"{missing_required} required source columns are missing",
        ),
        _check(
            "vendor_schema_reviewed",
            passed=not placeholder,
            status="pass" if not placeholder else "blocked",
            detail="adapter uses a reviewed native schema"
            if not placeholder
            else "adapter is still using normalized placeholders; review real Arrow.money/iRage source columns",
        ),
        _check(
            "extra_columns_classified",
            passed=extra_columns == 0,
            status="pass" if extra_columns == 0 else "review",
            detail="no extra vendor columns found"
            if extra_columns == 0
            else f"{extra_columns} extra vendor columns need classification or ignore approval",
        ),
        _check(
            "mapping_template_complete",
            passed=missing_mappings == 0,
            status="pass" if missing_mappings == 0 else "blocked",
            detail="mapping template has a source column for every normalized field"
            if missing_mappings == 0
            else f"{missing_mappings} mapping rows are missing source columns",
        ),
    ]
    return pd.DataFrame(checks)


def _check(check_name: str, *, passed: bool, status: str, detail: str) -> dict[str, object]:
    return {
        "check_name": check_name,
        "passed": bool(passed),
        "status": status,
        "detail": detail,
    }


def _template_note(schema_status: str, mapped: bool) -> str:
    if not mapped:
        return "sample is missing expected source column; update adapter map or request vendor export field"
    if schema_status == "placeholder_normalized_pending_vendor_schema":
        return "placeholder normalized mapping; replace source_column after vendor schema review"
    return "source column found"


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
    record: dict[str, object] = {}
    for key, value in row.items():
        record[str(key)] = _jsonable_value(value)
    return record


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
    return [item for item in text.split(";") if item]


def _help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _text(value: object) -> str:
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


def _float(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "pass", "passed", "ready"}:
        return True
    if text in {"false", "0", "no", "n", "fail", "failed", "not_ready", "blocked"}:
        return False
    return default
