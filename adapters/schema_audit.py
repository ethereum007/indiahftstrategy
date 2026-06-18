from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    return AdapterSchemaAudit(
        adapter=spec.name,
        kind=canonical_kind,
        columns=columns,
        summary=summary,
        template=template,
        checklist=checklist,
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
