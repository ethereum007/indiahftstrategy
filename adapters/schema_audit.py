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
    return AdapterSchemaAudit(
        adapter=spec.name,
        kind=canonical_kind,
        columns=columns,
        summary=summary,
        template=template,
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
    missing = [str(value) for value in columns.loc[~present, "expected_source_column"]]
    extra = [column for column in sample_columns if column not in matched]
    required_count = int(len(columns))
    present_count = int(present.sum()) if required_count else 0
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": kind,
                "adapter_schema_status": adapter_schema_status(adapter),
                "source_columns": int(len(sample_columns)),
                "required_columns": required_count,
                "present_required_columns": present_count,
                "missing_required_columns": int(len(missing)),
                "extra_columns": int(len(extra)),
                "pass_rate": float(present_count / required_count) if required_count else 0.0,
                "all_required_present": bool(len(missing) == 0),
                "missing_source_columns": ";".join(missing),
                "extra_source_columns": ";".join(extra),
            }
        ]
    )


def _template_note(schema_status: str, mapped: bool) -> str:
    if not mapped:
        return "sample is missing expected source column; update adapter map or request vendor export field"
    if schema_status == "placeholder_normalized_pending_vendor_schema":
        return "placeholder normalized mapping; replace source_column after vendor schema review"
    return "source column found"
