from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from reports.manifest import write_experiment_manifest


SUMMARY_FILES = {
    "schema_audit": "adapter_schema_summary.csv",
    "order_export": "broker_order_summary.csv",
    "mapping_draft": "order_mapping_draft_summary.csv",
    "mapped_orders": "mapped_order_summary.csv",
    "upload_pack": "broker_upload_summary.csv",
    "halt_export": "halt_response_export_summary.csv",
    "reconciliation": "reconciliation_summary.csv",
    "runtime_session": "runtime_session_summary.csv",
}


@dataclass(frozen=True)
class BrokerReadinessThresholds:
    adapter: str = "arrow_money"
    require_reviewed_schema: bool = True
    require_schema_audit: bool = True
    require_order_export: bool = True
    require_mapping_draft: bool = False
    require_mapped_orders: bool = False
    require_upload_pack: bool = True
    require_halt_export: bool = False
    require_reconciliation: bool = False
    require_runtime_session: bool = False
    require_adapter_match: bool = True


@dataclass(frozen=True)
class BrokerReadinessReport:
    items: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_readiness(
    *,
    schema_audit_summary: pd.DataFrame | None = None,
    order_export_summary: pd.DataFrame | None = None,
    mapping_draft_summary: pd.DataFrame | None = None,
    mapped_order_summary: pd.DataFrame | None = None,
    upload_pack_summary: pd.DataFrame | None = None,
    halt_export_summary: pd.DataFrame | None = None,
    reconciliation_summary: pd.DataFrame | None = None,
    runtime_session_summary: pd.DataFrame | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    summaries = {
        "schema_audit": _optional_frame(schema_audit_summary),
        "order_export": _optional_frame(order_export_summary),
        "mapping_draft": _optional_frame(mapping_draft_summary),
        "mapped_orders": _optional_frame(mapped_order_summary),
        "upload_pack": _optional_frame(upload_pack_summary),
        "halt_export": _optional_frame(halt_export_summary),
        "reconciliation": _optional_frame(reconciliation_summary),
        "runtime_session": _optional_frame(runtime_session_summary),
    }
    items = _items(summaries, thresholds)
    checks = _checks(items, thresholds)
    summary = _summary(items, checks, thresholds)
    return BrokerReadinessReport(items=items, checks=checks, summary=summary)


def write_broker_readiness_report(
    *,
    output_dir: str | Path,
    schema_audit_dir: str | Path | None = None,
    order_export_dir: str | Path | None = None,
    mapping_draft_dir: str | Path | None = None,
    mapped_orders_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    halt_export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    runtime_session_dir: str | Path | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    report = evaluate_broker_readiness(
        schema_audit_summary=_read_optional_summary(schema_audit_dir, "schema_audit"),
        order_export_summary=_read_optional_summary(order_export_dir, "order_export"),
        mapping_draft_summary=_read_optional_summary(mapping_draft_dir, "mapping_draft"),
        mapped_order_summary=_read_optional_summary(mapped_orders_dir, "mapped_orders"),
        upload_pack_summary=_read_optional_summary(upload_pack_dir, "upload_pack"),
        halt_export_summary=_read_optional_summary(halt_export_dir, "halt_export"),
        reconciliation_summary=_read_optional_summary(reconciliation_dir, "reconciliation"),
        runtime_session_summary=_read_optional_summary(runtime_session_dir, "runtime_session"),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.items.to_csv(out / "broker_readiness_items.csv", index=False)
    report.checks.to_csv(out / "broker_readiness_checks.csv", index=False)
    report.summary.to_csv(out / "broker_readiness_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="broker_readiness",
        parameters={"thresholds": asdict(thresholds)},
        inputs={
            "schema_audit": schema_audit_dir,
            "order_export": order_export_dir,
            "mapping_draft": mapping_draft_dir,
            "mapped_orders": mapped_orders_dir,
            "upload_pack": upload_pack_dir,
            "halt_export": halt_export_dir,
            "reconciliation": reconciliation_dir,
            "runtime_session": runtime_session_dir,
        },
    )
    return BrokerReadinessReport(report.items, report.checks, report.summary, out)


def _items(summaries: dict[str, pd.DataFrame], thresholds: BrokerReadinessThresholds) -> pd.DataFrame:
    return pd.DataFrame([_item(component, frame, thresholds) for component, frame in summaries.items()])


def _item(component: str, summary: pd.DataFrame, thresholds: BrokerReadinessThresholds) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    provided = not summary.empty
    ready = _component_ready(component, row) if provided else False
    adapter = str(row.get("adapter", "")).strip()
    schema_status = str(row.get("adapter_schema_status", "")).strip()
    failed_checks = _number(row, "failed_checks", fallback=_number(row, "unmapped_required_columns", fallback=0.0))
    required = _component_required(component, thresholds)
    adapter_match = (not adapter) or adapter == thresholds.adapter or not thresholds.require_adapter_match
    return {
        "component": component,
        "required": required,
        "provided": provided,
        "ready": ready,
        "adapter": adapter,
        "expected_adapter": thresholds.adapter,
        "adapter_match": adapter_match,
        "adapter_schema_status": schema_status,
        "failed_checks": int(failed_checks) if not pd.isna(failed_checks) else 0,
        "runtime_guard_action": str(row.get("guard_action", "")).strip() if component == "runtime_session" else "",
        "runtime_guard_halted": _guard_halted(row) if component == "runtime_session" and provided else False,
        "source_file": SUMMARY_FILES[component],
        "recommendation": _component_recommendation(component, provided, ready, required),
    }


def _checks(items: pd.DataFrame, thresholds: BrokerReadinessThresholds) -> pd.DataFrame:
    checks: list[dict[str, Any]] = [
        _check(
            "schema_reviewed",
            adapter_schema_status(thresholds.adapter),
            "!=",
            "placeholder_normalized_pending_vendor_schema",
            (not thresholds.require_reviewed_schema)
            or adapter_schema_status(thresholds.adapter) != "placeholder_normalized_pending_vendor_schema",
            "adapter schema is still placeholder; review a real vendor sample before broker integration",
        )
    ]
    for row in items.itertuples(index=False):
        if bool(row.required):
            checks.append(
                _check(
                    f"{row.component}_provided",
                    bool(row.provided),
                    "is",
                    True,
                    bool(row.provided),
                    f"{row.component} summary is required but missing",
                )
            )
        if bool(row.required) or bool(row.provided):
            checks.append(
                _check(
                    f"{row.component}_ready",
                    bool(row.ready),
                    "is",
                    True,
                    bool(row.ready),
                    f"{row.component} is not ready",
                )
            )
        if bool(row.provided) and thresholds.require_adapter_match:
            checks.append(
                _check(
                    f"{row.component}_adapter_match",
                    row.adapter or thresholds.adapter,
                    "==",
                    thresholds.adapter,
                    bool(row.adapter_match),
                    f"{row.component} adapter does not match expected broker adapter",
                )
            )
    return pd.DataFrame(checks)


def _summary(
    items: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerReadinessThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    required_items = items.loc[items["required"].astype(bool)] if not items.empty else pd.DataFrame()
    missing_required = int((~required_items["provided"].astype(bool)).sum()) if not required_items.empty else 0
    ready_items = int(items["ready"].astype(bool).sum()) if not items.empty else 0
    schema_status = adapter_schema_status(thresholds.adapter)
    ready = failed == 0
    runtime_item = _component_item(items, "runtime_session")
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": thresholds.adapter,
                "adapter_schema_status": schema_status,
                "required_components": int(len(required_items)),
                "provided_components": int(items["provided"].astype(bool).sum()) if not items.empty else 0,
                "ready_components": ready_items,
                "missing_required_components": missing_required,
                "failed_checks": failed,
                "runtime_session_provided": _item_bool(runtime_item, "provided"),
                "runtime_session_ready": _item_bool(runtime_item, "ready"),
                "runtime_guard_action": _item_text(runtime_item, "runtime_guard_action"),
                "runtime_guard_halted": _item_bool(runtime_item, "runtime_guard_halted"),
                "recommendation": _summary_recommendation(ready, schema_status, thresholds),
            }
        ]
    )


def _component_required(component: str, thresholds: BrokerReadinessThresholds) -> bool:
    return bool(
        {
            "schema_audit": thresholds.require_schema_audit,
            "order_export": thresholds.require_order_export,
            "mapping_draft": thresholds.require_mapping_draft,
            "mapped_orders": thresholds.require_mapped_orders,
            "upload_pack": thresholds.require_upload_pack,
            "halt_export": thresholds.require_halt_export,
            "reconciliation": thresholds.require_reconciliation,
            "runtime_session": thresholds.require_runtime_session,
        }[component]
    )


def _component_ready(component: str, row: pd.Series) -> bool:
    if component == "schema_audit":
        return _to_bool(row.get("all_required_present", False))
    if component == "reconciliation":
        return _to_bool(row.get("passed", False))
    if component == "runtime_session":
        return _to_bool(row.get("ready", False)) and not _guard_halted(row)
    return _to_bool(row.get("ready", False))


def _component_recommendation(component: str, provided: bool, ready: bool, required: bool) -> str:
    if not provided and required:
        return f"run_{component}"
    if not provided:
        return "optional_not_supplied"
    if not ready:
        return f"fix_{component}"
    return "accepted"


def _summary_recommendation(
    ready: bool,
    schema_status: str,
    thresholds: BrokerReadinessThresholds,
) -> str:
    if ready and schema_status == "placeholder_normalized_pending_vendor_schema":
        return "dry_run_only_until_vendor_schema_review"
    if ready:
        return "broker_integration_ready"
    if thresholds.require_reviewed_schema and schema_status == "placeholder_normalized_pending_vendor_schema":
        return "obtain_vendor_schema_samples"
    return "fix_broker_readiness_gaps"


def _component_item(items: pd.DataFrame, component: str) -> pd.Series:
    if items.empty or "component" not in items.columns:
        return pd.Series(dtype=object)
    matches = items.loc[items["component"] == component]
    return matches.iloc[0] if not matches.empty else pd.Series(dtype=object)


def _item_bool(item: pd.Series, column: str) -> bool:
    if item.empty or column not in item.index:
        return False
    return _to_bool(item[column])


def _item_text(item: pd.Series, column: str) -> str:
    if item.empty or column not in item.index or pd.isna(item[column]):
        return ""
    return str(item[column])


def _read_optional_summary(path: str | Path | None, component: str) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / SUMMARY_FILES[component]
    if not candidate.exists():
        raise FileNotFoundError(f"{component} summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"{component} summary is empty: {candidate}")
    return frame


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _validate_thresholds(thresholds: BrokerReadinessThresholds) -> None:
    get_adapter(thresholds.adapter)


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _guard_halted(row: pd.Series) -> bool:
    return _to_bool(row.get("halted", False)) or str(row.get("guard_action", "")).strip().lower() == "halt"


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
