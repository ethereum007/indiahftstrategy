from __future__ import annotations

import json
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
    "resume_gate": "resume_summary.csv",
    "dispatch_roundtrip": "broker_dispatch_roundtrip_summary.csv",
}

SUMMARY_FALLBACK_DIRS = {
    "order_export": ("04_export", "03_export"),
    "upload_pack": ("05_upload_pack", "04_upload_pack"),
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
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
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
    resume_summary: pd.DataFrame | None = None,
    dispatch_roundtrip_summary: pd.DataFrame | None = None,
    dispatch_roundtrip_config: dict[str, Any] | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    dispatch_roundtrip = _dispatch_roundtrip_frame(
        dispatch_roundtrip_summary,
        dispatch_roundtrip_config or {},
    )
    summaries = {
        "schema_audit": _optional_frame(schema_audit_summary),
        "order_export": _optional_frame(order_export_summary),
        "mapping_draft": _optional_frame(mapping_draft_summary),
        "mapped_orders": _optional_frame(mapped_order_summary),
        "upload_pack": _optional_frame(upload_pack_summary),
        "halt_export": _optional_frame(halt_export_summary),
        "reconciliation": _optional_frame(reconciliation_summary),
        "runtime_session": _optional_frame(runtime_session_summary),
        "resume_gate": _optional_frame(resume_summary),
        "dispatch_roundtrip": dispatch_roundtrip,
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
    resume_dir: str | Path | None = None,
    dispatch_roundtrip_dir: str | Path | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    input_paths = {
        "schema_audit": _manifest_summary_input(schema_audit_dir, "schema_audit"),
        "order_export": _manifest_summary_input(order_export_dir, "order_export"),
        "mapping_draft": _manifest_summary_input(mapping_draft_dir, "mapping_draft"),
        "mapped_orders": _manifest_summary_input(mapped_orders_dir, "mapped_orders"),
        "upload_pack": _manifest_summary_input(upload_pack_dir, "upload_pack"),
        "halt_export": _manifest_summary_input(halt_export_dir, "halt_export"),
        "reconciliation": _manifest_summary_input(reconciliation_dir, "reconciliation"),
        "runtime_session": _manifest_summary_input(runtime_session_dir, "runtime_session"),
        "resume_gate": _manifest_summary_input(resume_dir, "resume_gate"),
        "dispatch_roundtrip": _manifest_summary_input(dispatch_roundtrip_dir, "dispatch_roundtrip"),
    }
    report = evaluate_broker_readiness(
        schema_audit_summary=_read_optional_summary(schema_audit_dir, "schema_audit"),
        order_export_summary=_read_optional_summary(order_export_dir, "order_export"),
        mapping_draft_summary=_read_optional_summary(mapping_draft_dir, "mapping_draft"),
        mapped_order_summary=_read_optional_summary(mapped_orders_dir, "mapped_orders"),
        upload_pack_summary=_read_optional_summary(upload_pack_dir, "upload_pack"),
        halt_export_summary=_read_optional_summary(halt_export_dir, "halt_export"),
        reconciliation_summary=_read_optional_summary(reconciliation_dir, "reconciliation"),
        runtime_session_summary=_read_optional_summary(runtime_session_dir, "runtime_session"),
        resume_summary=_read_optional_summary(resume_dir, "resume_gate"),
        dispatch_roundtrip_summary=_read_optional_summary(dispatch_roundtrip_dir, "dispatch_roundtrip"),
        dispatch_roundtrip_config=_read_optional_config(
            dispatch_roundtrip_dir,
            "broker_dispatch_roundtrip_config.json",
        ),
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
        inputs=input_paths,
    )
    return BrokerReadinessReport(report.items, report.checks, report.summary, out)


def _items(summaries: dict[str, pd.DataFrame], thresholds: BrokerReadinessThresholds) -> pd.DataFrame:
    return pd.DataFrame([_item(component, frame, thresholds) for component, frame in summaries.items()])


def _dispatch_roundtrip_frame(summary: pd.DataFrame | None, config: dict[str, Any]) -> pd.DataFrame:
    frame = _optional_frame(summary)
    if frame.empty:
        return frame
    route_enable = config.get("route_enable_dispatch_roundtrip", {}) or {}
    if "failed_checks" in route_enable:
        frame.loc[0, "route_enable_dispatch_roundtrip_failed_checks"] = int(
            _number_value(
                route_enable.get("failed_checks"),
                _number(frame.iloc[0], "route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
        )
    return frame


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
        "runtime_target_mode": _runtime_text(component, row, "target_mode"),
        "runtime_strategy": _runtime_text(component, row, "strategy"),
        "runtime_market": _runtime_text(component, row, "market"),
        "resume_strategy": _resume_text(component, row, "strategy"),
        "resume_market": _resume_text(component, row, "market"),
        "resume_incident_strategy": _resume_text(component, row, "incident_strategy"),
        "resume_incident_market": _resume_text(component, row, "incident_market"),
        "resume_proof_refresh_ready": _resume_bool(component, row, "proof_refresh_ready"),
        "resume_proof_refresh_strategy": _resume_text(component, row, "proof_refresh_strategy"),
        "resume_proof_refresh_market": _resume_text(component, row, "proof_refresh_market"),
        "resume_incident_proof_refresh_strategy": _resume_text(component, row, "incident_proof_refresh_strategy"),
        "resume_incident_proof_refresh_market": _resume_text(component, row, "incident_proof_refresh_market"),
        "dispatch_roundtrip_target_mode": _dispatch_text(component, row, "target_mode"),
        "dispatch_roundtrip_strategy": _dispatch_text(component, row, "strategy"),
        "dispatch_roundtrip_market": _dispatch_text(component, row, "market"),
        "dispatch_roundtrip_scenario_key": _dispatch_text(component, row, "scenario_key"),
        "dispatch_roundtrip_batch_id": _dispatch_text(component, row, "dispatch_batch_id"),
        "dispatch_roundtrip_requests": int(_number(row, "send_requests", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_acked_orders": int(_number(row, "acked_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_missing_request_acks": int(_number(row, "missing_request_acks", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_rejected_orders": int(_number(row, "rejected_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_unmatched_acks": int(_number(row, "unmatched_acks", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_failed_checks": int(failed_checks)
        if component == "dispatch_roundtrip" and provided and not pd.isna(failed_checks)
        else 0,
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_required": _dispatch_bool(component, row, "route_dispatch_roundtrip_required"),
        "route_dispatch_roundtrip_provided": _dispatch_bool(component, row, "route_dispatch_roundtrip_provided"),
        "route_dispatch_roundtrip_ready": _dispatch_bool(component, row, "route_dispatch_roundtrip_ready"),
        "route_dispatch_roundtrip_target_mode": _dispatch_text(component, row, "route_dispatch_roundtrip_target_mode"),
        "route_dispatch_roundtrip_strategy": _dispatch_text(component, row, "route_dispatch_roundtrip_strategy"),
        "route_dispatch_roundtrip_market": _dispatch_text(component, row, "route_dispatch_roundtrip_market"),
        "route_dispatch_roundtrip_scenario_key": _dispatch_text(
            component,
            row,
            "route_dispatch_roundtrip_scenario_key",
        ),
        "route_dispatch_roundtrip_batch_id": _dispatch_text(component, row, "route_dispatch_roundtrip_batch_id"),
        "route_dispatch_roundtrip_requests": int(_number(row, "route_dispatch_roundtrip_requests", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_acked_orders": int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_rejected_orders": int(
            _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
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
        if row.component == "dispatch_roundtrip" and bool(row.provided):
            checks.append(
                _check(
                    "route_enable_dispatch_roundtrip_failed_checks",
                    int(row.route_enable_dispatch_roundtrip_failed_checks),
                    "<=",
                    0,
                    int(row.route_enable_dispatch_roundtrip_failed_checks) <= 0,
                    "route-enable dispatch round-trip has failed component checks",
                )
            )
            route_required = _route_dispatch_roundtrip_required(row)
            if route_required:
                checks.append(
                    _check(
                        "route_dispatch_roundtrip_provided",
                        bool(row.route_dispatch_roundtrip_provided),
                        "is",
                        True,
                        bool(row.route_dispatch_roundtrip_provided),
                        "dispatch round-trip summary must carry route proof for live dry-run readiness",
                    )
                )
            if route_required or bool(row.route_dispatch_roundtrip_provided):
                checks.extend(_route_dispatch_roundtrip_checks(row))
    return pd.DataFrame(checks)


def _route_dispatch_roundtrip_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            bool(row.route_dispatch_roundtrip_ready),
            "is",
            True,
            bool(row.route_dispatch_roundtrip_ready),
            "dispatch route proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            _identity_key(row.route_dispatch_roundtrip_target_mode),
            "==",
            _identity_key(row.dispatch_roundtrip_target_mode),
            bool(
                _identity_key(row.route_dispatch_roundtrip_target_mode)
                and _identity_key(row.dispatch_roundtrip_target_mode)
                and _identity_key(row.route_dispatch_roundtrip_target_mode)
                == _identity_key(row.dispatch_roundtrip_target_mode)
            ),
            "dispatch route proof target mode does not match dispatch round-trip target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(row.route_dispatch_roundtrip_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.route_dispatch_roundtrip_strategy)
                and _identity_key(row.dispatch_roundtrip_strategy)
                and _identity_key(row.route_dispatch_roundtrip_strategy) == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "dispatch route proof strategy does not match dispatch round-trip strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            _identity_key(row.route_dispatch_roundtrip_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.route_dispatch_roundtrip_market)
                and _identity_key(row.dispatch_roundtrip_market)
                and _identity_key(row.route_dispatch_roundtrip_market) == _identity_key(row.dispatch_roundtrip_market)
            ),
            "dispatch route proof market does not match dispatch round-trip market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            str(row.route_dispatch_roundtrip_scenario_key),
            "==",
            str(row.dispatch_roundtrip_scenario_key),
            bool(
                str(row.route_dispatch_roundtrip_scenario_key)
                and str(row.dispatch_roundtrip_scenario_key)
                and str(row.route_dispatch_roundtrip_scenario_key) == str(row.dispatch_roundtrip_scenario_key)
            ),
            "dispatch route proof scenario does not match dispatch round-trip scenario",
        ),
        _check(
            "route_dispatch_roundtrip_request_count_matches",
            int(row.route_dispatch_roundtrip_requests),
            "==",
            int(row.dispatch_roundtrip_requests),
            int(row.route_dispatch_roundtrip_requests) == int(row.dispatch_roundtrip_requests)
            and int(row.route_dispatch_roundtrip_acked_orders) == int(row.dispatch_roundtrip_acked_orders),
            "dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            int(row.route_dispatch_roundtrip_missing_request_acks),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_missing_request_acks) <= 0,
            "dispatch route proof has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            int(row.route_dispatch_roundtrip_rejected_orders),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_rejected_orders) <= 0,
            "dispatch route proof has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            int(row.route_dispatch_roundtrip_unmatched_acks),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_unmatched_acks) <= 0,
            "dispatch route proof has unmatched acknowledgements",
        ),
    ]


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
    resume_item = _component_item(items, "resume_gate")
    dispatch_item = _component_item(items, "dispatch_roundtrip")
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
                "runtime_target_mode": _item_text(runtime_item, "runtime_target_mode"),
                "runtime_strategy": _item_text(runtime_item, "runtime_strategy"),
                "runtime_market": _item_text(runtime_item, "runtime_market"),
                "resume_gate_provided": _item_bool(resume_item, "provided"),
                "resume_gate_ready": _item_bool(resume_item, "ready"),
                "resume_strategy": _item_text(resume_item, "resume_strategy"),
                "resume_market": _item_text(resume_item, "resume_market"),
                "resume_incident_strategy": _item_text(resume_item, "resume_incident_strategy"),
                "resume_incident_market": _item_text(resume_item, "resume_incident_market"),
                "resume_proof_refresh_ready": _item_bool(resume_item, "resume_proof_refresh_ready"),
                "resume_proof_refresh_strategy": _item_text(resume_item, "resume_proof_refresh_strategy"),
                "resume_proof_refresh_market": _item_text(resume_item, "resume_proof_refresh_market"),
                "resume_incident_proof_refresh_strategy": _item_text(
                    resume_item,
                    "resume_incident_proof_refresh_strategy",
                ),
                "resume_incident_proof_refresh_market": _item_text(
                    resume_item,
                    "resume_incident_proof_refresh_market",
                ),
                "dispatch_roundtrip_provided": _item_bool(dispatch_item, "provided"),
                "dispatch_roundtrip_ready": _item_bool(dispatch_item, "ready"),
                "dispatch_roundtrip_target_mode": _item_text(dispatch_item, "dispatch_roundtrip_target_mode"),
                "dispatch_roundtrip_strategy": _item_text(dispatch_item, "dispatch_roundtrip_strategy"),
                "dispatch_roundtrip_market": _item_text(dispatch_item, "dispatch_roundtrip_market"),
                "dispatch_roundtrip_scenario_key": _item_text(dispatch_item, "dispatch_roundtrip_scenario_key"),
                "dispatch_roundtrip_batch_id": _item_text(dispatch_item, "dispatch_roundtrip_batch_id"),
                "dispatch_roundtrip_requests": int(_number(dispatch_item, "dispatch_roundtrip_requests", 0.0)),
                "dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_item, "dispatch_roundtrip_acked_orders", 0.0)
                ),
                "dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_item, "dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_item, "dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_item, "dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_item, "dispatch_roundtrip_failed_checks", 0.0)
                ),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_item, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                ),
                "route_dispatch_roundtrip_required": _item_bool(dispatch_item, "route_dispatch_roundtrip_required"),
                "route_dispatch_roundtrip_provided": _item_bool(dispatch_item, "route_dispatch_roundtrip_provided"),
                "route_dispatch_roundtrip_ready": _item_bool(dispatch_item, "route_dispatch_roundtrip_ready"),
                "route_dispatch_roundtrip_target_mode": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_target_mode",
                ),
                "route_dispatch_roundtrip_strategy": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_strategy",
                ),
                "route_dispatch_roundtrip_market": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_market",
                ),
                "route_dispatch_roundtrip_scenario_key": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_scenario_key",
                ),
                "route_dispatch_roundtrip_batch_id": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_batch_id",
                ),
                "route_dispatch_roundtrip_requests": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_requests", 0.0)
                ),
                "route_dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_acked_orders", 0.0)
                ),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "route_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "route_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
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
            "resume_gate": thresholds.require_resume_gate,
            "dispatch_roundtrip": thresholds.require_dispatch_roundtrip,
        }[component]
    )


def _component_ready(component: str, row: pd.Series) -> bool:
    if component == "schema_audit":
        return _to_bool(row.get("all_required_present", False))
    if component == "reconciliation":
        return _to_bool(row.get("passed", False))
    if component == "runtime_session":
        return _to_bool(row.get("ready", False)) and not _guard_halted(row)
    if component == "resume_gate":
        return _to_bool(row.get("ready", False))
    if component == "dispatch_roundtrip":
        return _to_bool(row.get("passed", False)) and int(_number(row, "failed_checks", 0.0)) <= 0
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


def _runtime_text(component: str, row: pd.Series, column: str) -> str:
    if component != "runtime_session" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _resume_text(component: str, row: pd.Series, column: str) -> str:
    if component != "resume_gate" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _resume_bool(component: str, row: pd.Series, column: str) -> bool:
    if component != "resume_gate" or row.empty:
        return False
    return _to_bool(row.get(column, False))


def _dispatch_text(component: str, row: pd.Series, column: str) -> str:
    if component != "dispatch_roundtrip" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _dispatch_bool(component: str, row: pd.Series, column: str) -> bool:
    if component != "dispatch_roundtrip" or row.empty:
        return False
    return _to_bool(row.get(column, False))


def _route_dispatch_roundtrip_required(row: Any) -> bool:
    return bool(
        row.route_dispatch_roundtrip_required
        or _identity_key(row.dispatch_roundtrip_target_mode) == "live_dryrun"
    )


def _read_optional_summary(path: str | Path | None, component: str) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = _summary_path(path, component)
    if not candidate.exists():
        raise FileNotFoundError(f"{component} summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"{component} summary is empty: {candidate}")
    return frame


def _summary_path(path: str | Path, component: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / SUMMARY_FILES[component]
    if direct.exists():
        return direct
    return next(
        (
            nested
            for folder in SUMMARY_FALLBACK_DIRS.get(component, ())
            if (nested := candidate / folder / SUMMARY_FILES[component]).exists()
        ),
        direct,
    )


def _manifest_summary_input(path: str | Path | None, component: str) -> Path | None:
    if path is None:
        return None
    summary_path = _summary_path(path, component)
    return summary_path if summary_path.exists() else Path(path)


def _read_optional_config(path: str | Path | None, file_name: str) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / file_name
    if not candidate.exists():
        return {}
    return json.loads(candidate.read_text(encoding="utf-8"))


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _validate_thresholds(thresholds: BrokerReadinessThresholds) -> None:
    get_adapter(thresholds.adapter)


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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
