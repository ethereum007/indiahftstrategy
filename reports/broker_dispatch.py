from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    empty_route_enable_lineage,
    load_route_enable_lineage,
    route_enable_lineage_fields,
    route_enable_lineage_manifest_inputs,
)
from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
)


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "target_mode",
    "strategy",
    "market",
    "scenario_key",
    "adapter",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]
ROUTE_ENABLE_LINEAGE_OUTPUT_COLUMNS = tuple(
    route_enable_lineage_fields(empty_route_enable_lineage()).keys()
)
TARGET_APPLICATION_BATCH_MODE = "per_dataset_verified_target_application"
TARGET_APPLICATION_DATASET_LINEAGE_FIELDS: tuple[str, ...] = (
    "mapping_application_path",
    "mapping_application_id",
    "mapping_application_sha256",
    "mapping_scope_review_id",
    "mapping_scope_review_sha256",
    "target_intake_receipt_id",
    "applied_mapping_sha256",
)
TARGET_APPLICATION_LINEAGE_IDENTITY_FIELDS: tuple[str, ...] = (
    "source_file_sha256",
    "source_header_sha256",
    "mapping_draft_sha256",
    "mapping_source",
    "mapping_application_id",
    "mapping_application_sha256",
    "mapping_scope_review_id",
    "mapping_scope_review_sha256",
    "target_intake_receipt_id",
    "applied_mapping_sha256",
)
ROUTE_FINAL_LINEAGE_COMPARISON_KEY = (
    "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
ROUTE_FINAL_LINEAGE_FIELD_PREFIX = (
    "route_broker_dispatch_roundtrip_vendor_market_data_batch"
)
ROUTE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
)
ROUTE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    "current_application_lineage_sha256",
    "broker_application_lineage_sha256",
    "scaleup_carried_application_lineage_sha256",
    "cutover_carried_application_lineage_sha256",
    "route_carried_application_lineage_sha256",
    "dispatch_carried_application_lineage_sha256",
    "send_carried_application_lineage_sha256",
    "ack_carried_application_lineage_sha256",
    "roundtrip_carried_application_lineage_sha256",
    "readiness_carried_application_lineage_sha256",
    "scaleup_review_carried_application_lineage_sha256",
    "cutover_review_carried_application_lineage_sha256",
)
ROUTE_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
ROUTE_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "route_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
ROUTE_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
ROUTE_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    "current_application_lineage_sha256",
    "broker_application_lineage_sha256",
    "scaleup_carried_application_lineage_sha256",
    "cutover_carried_application_lineage_sha256",
    "route_carried_application_lineage_sha256",
    "dispatch_carried_application_lineage_sha256",
    "send_carried_application_lineage_sha256",
    "ack_carried_application_lineage_sha256",
    "roundtrip_carried_application_lineage_sha256",
    "readiness_carried_application_lineage_sha256",
    "scaleup_review_carried_application_lineage_sha256",
    "cutover_review_carried_application_lineage_sha256",
    "route_enable_review_carried_application_lineage_sha256",
    "dispatch_plan_review_carried_application_lineage_sha256",
    "send_packet_review_carried_application_lineage_sha256",
    "ack_reconciliation_review_carried_application_lineage_sha256",
    "roundtrip_final_review_carried_application_lineage_sha256",
    "broker_readiness_review_carried_application_lineage_sha256",
    "scaleup_final_review_carried_application_lineage_sha256",
    "cutover_final_review_carried_application_lineage_sha256",
)
DISPATCH_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)


@dataclass(frozen=True)
class BrokerDispatchThresholds:
    target_mode: str = "live_dryrun"
    require_route_enabled: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1
    max_orders: int | None = None


@dataclass(frozen=True)
class BrokerDispatchReport:
    dispatch_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_dispatch_plan(
    *,
    route_enable_summary: pd.DataFrame,
    route_enable_config: dict[str, Any] | None = None,
    upload_orders: pd.DataFrame,
    upload_file_hash: str = "",
    route_enable_lineage: dict[str, Any] | None = None,
    thresholds: BrokerDispatchThresholds | None = None,
) -> BrokerDispatchReport:
    thresholds = thresholds or BrokerDispatchThresholds()
    _validate_thresholds(thresholds)
    route_enable_summary = _require_nonempty(route_enable_summary, "route_enable_summary")
    upload_orders = _require_nonempty(upload_orders, "upload_orders")
    route_enable_config = route_enable_config or {}

    route = _route_state(
        route_enable_summary.iloc[0],
        route_enable_config,
        route_enable_lineage or empty_route_enable_lineage(),
    )
    dispatch_orders = _dispatch_orders(upload_orders, route, upload_file_hash)
    checks = _checks(route, dispatch_orders, thresholds)
    summary = _summary(route, dispatch_orders, checks, upload_file_hash, thresholds)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(route, dispatch_orders, summary.iloc[0], thresholds, checks, upload_file_hash, action_queue)
    return BrokerDispatchReport(
        dispatch_orders=dispatch_orders,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_broker_dispatch_plan(
    *,
    route_enable_dir: str | Path,
    upload_pack_dir: str | Path,
    output_dir: str | Path,
    upload_orders_path: str | Path | None = None,
    thresholds: BrokerDispatchThresholds | None = None,
) -> BrokerDispatchReport:
    thresholds = thresholds or BrokerDispatchThresholds()
    _validate_thresholds(thresholds)
    route_dir = Path(route_enable_dir)
    upload_dir = Path(upload_pack_dir)
    route_config_path = route_dir / "route_enable_config.json" if route_dir.is_dir() else Path(route_enable_dir)
    if not route_config_path.exists():
        raise FileNotFoundError(f"route-enable config not found: {route_config_path}")
    route_summary_path = (
        route_dir / "route_enable_summary.csv"
        if route_dir.is_dir()
        else route_config_path.with_name("route_enable_summary.csv")
    )
    route_manifest_path = _sidecar_path(route_enable_dir, "manifest.json")
    route_lineage = load_route_enable_lineage(route_config_path)
    route_config = json.loads(route_config_path.read_text(encoding="utf-8"))
    cutover_manifest_path = _manifest_input_path(route_manifest_path, "cutover_manifest")
    broker_readiness_config_path = _manifest_input_path(cutover_manifest_path, "broker_readiness_config")
    if broker_readiness_config_path is not None:
        route_config = _with_broker_readiness_config_vendor_market_data_batch(
            route_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    upload_file = _upload_orders_path(upload_dir, route_config, upload_orders_path)
    upload_bytes = upload_file.read_bytes()
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=_read_required(route_summary_path, "route_enable_summary"),
        route_enable_config=route_config,
        upload_orders=pd.read_csv(upload_file),
        upload_file_hash=hashlib.sha256(upload_bytes).hexdigest(),
        route_enable_lineage=route_lineage,
        thresholds=thresholds,
    )
    out = Path(output_dir).resolve()
    _reject_input_output_collision(
        out,
        {
            "route enable": route_config_path,
            "upload pack": upload_file,
        },
    )
    out.mkdir(parents=True, exist_ok=True)
    report.dispatch_orders.to_csv(out / "broker_dispatch_orders.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(
        report.summary.iloc[0], report.checks
    )
    action_queue.to_csv(out / "broker_dispatch_action_queue.csv", index=False)
    (out / "broker_dispatch_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "broker_dispatch_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "route_enable_summary": route_summary_path,
        "route_enable_config": route_config_path,
        "upload_orders": upload_file,
    }
    if route_manifest_path is not None:
        inputs["route_enable_manifest"] = route_manifest_path
    inputs.update(route_enable_lineage_manifest_inputs(route_lineage))
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_plan",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            **route_enable_lineage_fields(route_lineage),
            "authorizes_submission": False,
        },
    )
    return BrokerDispatchReport(
        dispatch_orders=report.dispatch_orders,
        checks=report.checks,
        summary=report.summary,
        config=report.config,
        output_dir=out,
        action_queue=action_queue,
    )


def _dispatch_orders(upload_orders: pd.DataFrame, route: dict[str, Any], upload_file_hash: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    batch_id = _batch_id(route, upload_orders, upload_file_hash)
    for idx, row in upload_orders.reset_index(drop=True).iterrows():
        source_order_id = _source_order_id(row, idx)
        payload = _jsonable_row(row.to_dict())
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        rows.append(
            {
                "dispatch_batch_id": batch_id,
                "dispatch_sequence": idx + 1,
                "dispatch_order_id": f"DSP-{idx + 1:06d}-{payload_hash[:12]}",
                "dispatch_action": "dry_run_submit",
                "dry_run_only": True,
                "target_mode": route["target_mode"],
                "strategy": route["strategy"],
                "market": route["market"],
                "scenario_key": route["scenario_key"],
                "adapter": route["adapter"],
                "source_order_id": source_order_id,
                "source_payload_hash": payload_hash,
                "source_order_notional": _source_order_notional(row),
                "upload_file_hash": upload_file_hash,
                "route_enable_hash": route["route_enable_hash"],
                "route_dispatch_roundtrip_batch_id": route["dispatch_roundtrip_batch_id"],
                **_route_lineage_output_fields(route),
                "authorizes_submission": False,
                "order_payload_json": json.dumps(payload, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _checks(route: dict[str, Any], dispatch_orders: pd.DataFrame, thresholds: BrokerDispatchThresholds) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    max_orders = thresholds.max_orders or int(route["max_orders_per_session"])
    target_mode = _identity_key(thresholds.target_mode)
    route_readiness_required = _route_readiness_required(thresholds, route)
    route_readiness_active = bool(route_readiness_required or route["route_readiness_provided"])
    dispatch_total_notional = _dispatch_total_notional(dispatch_orders)
    checks = [
        _check(
            "route_enabled",
            route["route_enabled"],
            "is",
            True,
            bool(route["route_enabled"]) or not thresholds.require_route_enabled,
            "route-enable packet is not enabled",
        ),
        _check(
            "target_mode_matches",
            route["target_mode"],
            "==",
            target_mode,
            bool(route["target_mode"] and route["target_mode"] == target_mode),
            "dispatch target mode does not match route-enable target mode",
        ),
        _check(
            "route_dispatch_roundtrip_provided",
            route["dispatch_roundtrip_provided"],
            "is",
            True,
            bool(route["dispatch_roundtrip_provided"]) or not _dispatch_roundtrip_required(thresholds),
            "dispatch requires route-enable dry-run dispatch round-trip proof",
        ),
    ]
    if route["route_enable_lineage_required"]:
        checks.extend(
            [
                _check(
                    "route_enable_lineage_provided",
                    route["route_enable_lineage_provided"],
                    "is",
                    True,
                    bool(route["route_enable_lineage_provided"]),
                    "route-enable lineage evidence is required but missing",
                ),
                _check(
                    "route_enable_manifest_current",
                    route["route_enable_manifest_current"],
                    "is",
                    True,
                    bool(route["route_enable_manifest_current"]),
                    "route-enable manifest is missing, stale, or incomplete",
                ),
                _check(
                    "route_enable_lineage_contract_consistent",
                    route["route_enable_lineage_contract_consistent"],
                    "is",
                    True,
                    bool(route["route_enable_lineage_contract_consistent"]),
                    "route-enable packet, summary, config, and manifest lineage disagree",
                ),
                _check(
                    "route_enable_non_authorizing",
                    route["route_enable_non_authorizing"],
                    "is",
                    True,
                    bool(route["route_enable_non_authorizing"]),
                    "route-enable lineage contains an authorizing claim",
                ),
                _check(
                    "route_enable_cutover_lineage_gate_passed",
                    route["route_enable_cutover_lineage_gate_passed"],
                    "is",
                    True,
                    bool(route["route_enable_cutover_lineage_gate_passed"]),
                    "route-enable did not retain a valid cutover lineage gate",
                ),
                _check(
                    "route_enable_cutover_matches_current",
                    route["route_enable_cutover_matches_current"],
                    "is",
                    True,
                    bool(route["route_enable_cutover_matches_current"]),
                    "route-enable cutover lineage does not match the current cutover source",
                ),
                _check(
                    "route_enable_lineage_gate_passed",
                    route["route_enable_lineage_gate_passed"],
                    "is",
                    True,
                    bool(route["route_enable_lineage_gate_passed"]),
                    "route-enable operational lineage gate did not pass",
                ),
            ]
        )
    if route_readiness_required:
        checks.append(
            _check(
                "route_readiness_provided",
                route["route_readiness_provided"],
                "is",
                True,
                bool(route["route_readiness_provided"]),
                "dispatch requires route-enable route-readiness proof",
            )
        )
    if route_readiness_active:
        checks.extend(_route_readiness_checks(route))
    if _resume_route_readiness_active(route, "broker_resume_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                route,
                source_prefix="broker_resume_broker_route_readiness",
                check_prefix="route_broker_resume_broker_route_readiness",
                label="route-enable broker resume-gate broker route-readiness",
            )
        )
    if _resume_route_readiness_active(route, "broker_resume_incident_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                route,
                source_prefix="broker_resume_incident_broker_route_readiness",
                check_prefix="route_broker_resume_incident_broker_route_readiness",
                label="route-enable broker resume-gate incident broker route-readiness",
            )
        )
    checks.extend(
        [
            _check(
                "dispatch_orders_min",
                orders,
                ">=",
                thresholds.min_orders,
                orders >= thresholds.min_orders,
                "dispatch batch does not contain enough orders",
            ),
            _check(
                "dispatch_orders_within_limit",
                orders,
                "<=",
                max_orders,
                orders <= max_orders,
                "dispatch order count exceeds route limit",
            ),
            _check(
                "dispatch_orders_match_route_enable",
                orders,
                "==",
                int(route["upload_orders"]),
                orders == int(route["upload_orders"]),
                "dispatch order count does not match route-enable upload order count",
            ),
            _check(
                "unique_dispatch_order_id",
                int(dispatch_orders["dispatch_order_id"].nunique()),
                "==",
                orders,
                int(dispatch_orders["dispatch_order_id"].nunique()) == orders,
                "dispatch order ids are not unique",
            ),
            _check(
                "unique_source_order_id",
                int(dispatch_orders["source_order_id"].nunique()),
                "==",
                orders,
                int(dispatch_orders["source_order_id"].nunique()) == orders,
                "source order ids are not unique",
            ),
            _check(
                "dry_run_only",
                bool(dispatch_orders["dry_run_only"].astype(bool).all()),
                "is",
                True,
                bool(dispatch_orders["dry_run_only"].astype(bool).all()) or not thresholds.require_dry_run,
                "dispatch plan contains non-dry-run rows",
            ),
        ]
    )
    if _dispatch_roundtrip_required(thresholds) or route["dispatch_roundtrip_provided"]:
        checks.extend(_dispatch_roundtrip_checks(route, target_mode))
    if _strategy_portfolio_active(route):
        checks.extend(
            [
                _check(
                    "strategy_portfolio_ready",
                    route["strategy_portfolio_ready"],
                    "is",
                    True,
                    bool(route["strategy_portfolio_ready"]),
                    "route-enable strategy portfolio allocation is not ready",
                ),
                _check(
                    "strategy_portfolio_allocation_eligible",
                    route["strategy_portfolio_selected_eligible"],
                    "is",
                    True,
                    bool(route["strategy_portfolio_selected_eligible"]),
                    "route-enable strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "strategy_portfolio_strategy_matches",
                    route["strategy_portfolio_selected_strategy"],
                    "==",
                    route["strategy"],
                    bool(
                        route["strategy_portfolio_selected_strategy"]
                        and route["strategy"]
                        and route["strategy_portfolio_selected_strategy"] == route["strategy"]
                    ),
                    "route-enable strategy portfolio strategy does not match dispatch strategy",
                ),
                _check(
                    "strategy_portfolio_market_matches",
                    route["strategy_portfolio_selected_market"],
                    "==",
                    route["market"],
                    bool(
                        route["strategy_portfolio_selected_market"]
                        and route["market"]
                        and route["strategy_portfolio_selected_market"] == route["market"]
                    ),
                    "route-enable strategy portfolio market does not match dispatch market",
                ),
                _check(
                    "strategy_portfolio_allocation_notional",
                    route["strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    float(route["strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "route-enable strategy portfolio allocation notional must be positive",
                ),
                _check(
                    "dispatch_notional_within_strategy_portfolio_allocation",
                    dispatch_total_notional,
                    "<=",
                    route["strategy_portfolio_selected_allocation_notional"],
                    dispatch_total_notional <= float(route["strategy_portfolio_selected_allocation_notional"]),
                    "dispatch upload notional exceeds selected strategy portfolio allocation",
                ),
            ]
        )
    if _shadow_broker_readiness_active(route):
        checks.extend(_shadow_broker_readiness_checks(route))
    if _broker_shadow_broker_readiness_active(route):
        checks.extend(_broker_shadow_broker_readiness_checks(route))
    if _broker_vendor_data_readiness_active(route):
        checks.extend(_broker_vendor_data_readiness_checks(route))
    if _broker_vendor_market_data_batch_active(route):
        checks.extend(_broker_vendor_market_data_batch_checks(route))
    return pd.DataFrame(checks)


def _route_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    checks = [
        _check(
            "route_readiness_ready",
            route["route_readiness_ready"],
            "is",
            True,
            bool(route["route_readiness_ready"]),
            "route-enable route-readiness proof is not ready",
        ),
        _check(
            "route_readiness_strategy_matches",
            route["route_readiness_strategy"],
            "==",
            route["strategy"],
            bool(
                route["route_readiness_strategy"]
                and route["strategy"]
                and route["route_readiness_strategy"] == route["strategy"]
            ),
            "route-enable route-readiness strategy does not match dispatch strategy",
        ),
        _check(
            "route_readiness_market_matches",
            route["route_readiness_market"],
            "==",
            route["market"],
            bool(
                route["route_readiness_market"]
                and route["market"]
                and route["route_readiness_market"] == route["market"]
            ),
            "route-enable route-readiness market does not match dispatch market",
        ),
        _check(
            "route_readiness_ops_launch_controls_present",
            route["route_readiness_ops_launch_controls_present"],
            "is",
            True,
            bool(route["route_readiness_ops_launch_controls_present"]),
            "route-enable route-readiness proof is missing launch-grade ops broker controls",
        ),
        _check(
            "route_readiness_ops_launch_controls_blocked_pairs",
            route["route_readiness_ops_launch_controls_blocked_pairs"],
            "<=",
            0,
            int(route["route_readiness_ops_launch_controls_blocked_pairs"]) <= 0,
            "route-enable route-readiness proof has blocked launch-control pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
            route["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"],
            "<=",
            0,
            int(route["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) <= 0,
            "route-enable route-readiness proof has broker round-trip allocation breach pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            route["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"],
            "<=",
            0,
            int(route["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]) <= 0,
            "route-enable route-readiness proof has broker round-trip concentration breach pairs",
        ),
    ]
    if _broker_route_readiness_active(route):
        checks.extend(_broker_route_readiness_checks(route))
    return checks


def _broker_route_readiness_active(route: dict[str, Any]) -> bool:
    return bool(
        _to_bool(route["broker_route_readiness_required"])
        or _to_bool(route["broker_route_readiness_provided"])
        or _to_bool(route["broker_route_readiness_ready"])
        or int(route["broker_route_readiness_route_ready_pairs"]) > 0
        or int(route["broker_route_readiness_gap_pairs"]) > 0
        or bool(_object_text(route["broker_route_readiness_strategy"]))
        or bool(_object_text(route["broker_route_readiness_market"]))
        or bool(_object_text(route["broker_route_readiness_recommendation"]))
        or _to_bool(route["broker_route_readiness_ops_launch_controls_ready"])
        or bool(_object_text(route["broker_route_readiness_ops_launch_control_failures"]))
        or int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _broker_route_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "route_broker_route_readiness_provided",
            route["broker_route_readiness_provided"],
            "is",
            True,
            bool(route["broker_route_readiness_provided"] or not route["broker_route_readiness_required"]),
            "route-enable broker-carried route proof is required but not provided",
        ),
        _check(
            "route_broker_route_readiness_ready",
            route["broker_route_readiness_ready"],
            "is",
            True,
            bool(route["broker_route_readiness_ready"]),
            "route-enable broker-carried route proof is not ready",
        ),
        _check(
            "route_broker_route_readiness_strategy_matches",
            route["broker_route_readiness_strategy"],
            "==",
            route["strategy"],
            bool(
                route["broker_route_readiness_strategy"]
                and route["broker_route_readiness_strategy"] == route["strategy"]
            ),
            "route-enable broker-carried route strategy does not match dispatch strategy",
        ),
        _check(
            "route_broker_route_readiness_market_matches",
            route["broker_route_readiness_market"],
            "==",
            route["market"],
            bool(
                route["broker_route_readiness_market"]
                and route["broker_route_readiness_market"] == route["market"]
            ),
            "route-enable broker-carried route market does not match dispatch market",
        ),
        _check(
            "route_broker_route_readiness_gap_pairs",
            route["broker_route_readiness_gap_pairs"],
            "<=",
            0,
            int(route["broker_route_readiness_gap_pairs"]) <= 0,
            "route-enable broker-carried route proof has route gaps",
        ),
        _check(
            "route_broker_route_readiness_ops_launch_controls_ready",
            route["broker_route_readiness_ops_launch_controls_ready"],
            "is",
            True,
            bool(route["broker_route_readiness_ops_launch_controls_ready"]),
            "route-enable broker-carried route proof is missing launch-grade ops broker controls",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            route["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            "route-enable broker-carried route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            route["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            "route-enable broker-carried route proof has allocation breach broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            "route-enable broker-carried route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(route["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            "route-enable broker-carried route proof has concentration breach broker round-trip runs",
        ),
    ]


def _resume_route_readiness_active(route: dict[str, Any], prefix: str) -> bool:
    return bool(
        _to_bool(route[f"{prefix}_required"])
        or _to_bool(route[f"{prefix}_provided"])
        or _to_bool(route[f"{prefix}_ready"])
        or int(route[f"{prefix}_route_ready_pairs"]) > 0
        or int(route[f"{prefix}_gap_pairs"]) > 0
        or bool(_object_text(route[f"{prefix}_strategy"]))
        or bool(_object_text(route[f"{prefix}_market"]))
        or bool(_object_text(route[f"{prefix}_recommendation"]))
        or _to_bool(route[f"{prefix}_ops_launch_controls_ready"])
        or bool(_object_text(route[f"{prefix}_ops_launch_control_failures"]))
        or int(route[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(route[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(route[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(route[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _resume_route_readiness_checks(
    route: dict[str, Any],
    *,
    source_prefix: str,
    check_prefix: str,
    label: str,
) -> list[dict[str, object]]:
    return [
        _check(
            f"{check_prefix}_provided",
            route[f"{source_prefix}_provided"],
            "is",
            True,
            bool(route[f"{source_prefix}_provided"] or not route[f"{source_prefix}_required"]),
            f"{label} proof is required but not provided",
        ),
        _check(
            f"{check_prefix}_ready",
            route[f"{source_prefix}_ready"],
            "is",
            True,
            bool(route[f"{source_prefix}_ready"]),
            f"{label} proof is not ready",
        ),
        _check(
            f"{check_prefix}_strategy_matches",
            route[f"{source_prefix}_strategy"],
            "==",
            route["strategy"],
            bool(
                route[f"{source_prefix}_strategy"]
                and route["strategy"]
                and route[f"{source_prefix}_strategy"] == route["strategy"]
            ),
            f"{label} strategy does not match dispatch strategy",
        ),
        _check(
            f"{check_prefix}_market_matches",
            route[f"{source_prefix}_market"],
            "==",
            route["market"],
            bool(
                route[f"{source_prefix}_market"]
                and route["market"]
                and route[f"{source_prefix}_market"] == route["market"]
            ),
            f"{label} market does not match dispatch market",
        ),
        _check(
            f"{check_prefix}_route_ready_pairs",
            route[f"{source_prefix}_route_ready_pairs"],
            ">",
            0,
            int(route[f"{source_prefix}_route_ready_pairs"]) > 0,
            f"{label} has no route-ready pairs",
        ),
        _check(
            f"{check_prefix}_gap_pairs",
            route[f"{source_prefix}_gap_pairs"],
            "<=",
            0,
            int(route[f"{source_prefix}_gap_pairs"]) <= 0,
            f"{label} has route gaps",
        ),
        _check(
            f"{check_prefix}_ops_launch_controls_ready",
            route[f"{source_prefix}_ops_launch_controls_ready"],
            "is",
            True,
            bool(route[f"{source_prefix}_ops_launch_controls_ready"]),
            f"{label} is missing launch-grade ops broker controls",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            route[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(route[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            f"{label} has no allocation-safe broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            route[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(route[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            f"{label} has allocation breach broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            route[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(route[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            f"{label} has no concentration-OK broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            route[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(route[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            f"{label} has concentration breach broker round-trip runs",
        ),
    ]


def _dispatch_roundtrip_checks(route: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            route["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(route["dispatch_roundtrip_ready"]),
            "route-enable dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            route["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(route["dispatch_roundtrip_target_mode"] and route["dispatch_roundtrip_target_mode"] == target_mode),
            "route-enable dispatch round-trip target mode does not match dispatch target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            route["dispatch_roundtrip_strategy"],
            "==",
            route["strategy"],
            bool(
                route["dispatch_roundtrip_strategy"]
                and route["strategy"]
                and route["dispatch_roundtrip_strategy"] == route["strategy"]
            ),
            "route-enable dispatch round-trip strategy does not match dispatch strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            route["dispatch_roundtrip_market"],
            "==",
            route["market"],
            bool(
                route["dispatch_roundtrip_market"]
                and route["market"]
                and route["dispatch_roundtrip_market"] == route["market"]
            ),
            "route-enable dispatch round-trip market does not match dispatch market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            route["dispatch_roundtrip_scenario_key"],
            "==",
            route["scenario_key"],
            bool(
                route["dispatch_roundtrip_scenario_key"]
                and route["scenario_key"]
                and route["dispatch_roundtrip_scenario_key"] == route["scenario_key"]
            ),
            "route-enable dispatch round-trip scenario does not match dispatch scenario",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            route["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(route["dispatch_roundtrip_missing_request_acks"]) <= 0,
            "route-enable dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            route["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(route["dispatch_roundtrip_rejected_orders"]) <= 0,
            "route-enable dispatch round-trip has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            route["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(route["dispatch_roundtrip_unmatched_acks"]) <= 0,
            "route-enable dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "route_enable_dispatch_roundtrip_failed_checks",
            route["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(route["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            "route-enable dispatch round-trip has failed component checks",
        ),
    ]


def _shadow_broker_readiness_active(route: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(route, key_prefix="")


def _shadow_broker_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        route,
        key_prefix="",
        check_prefix="route_shadow_broker",
        label="route-enable shadow broker",
    )


def _broker_shadow_broker_readiness_active(route: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(route, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        route,
        key_prefix="broker_",
        check_prefix="route_broker_shadow_broker",
        label="route-enable broker-readiness shadow broker",
        check_provided=True,
    )


def _broker_vendor_market_data_batch_active(route: dict[str, Any]) -> bool:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_data_readiness_active(route: dict[str, Any]) -> bool:
    readiness = route["broker_vendor_data_readiness"]
    return bool(
        _to_bool(readiness["provided"])
        or _to_bool(readiness["ready"])
        or int(readiness["failed_checks"]) > 0
    )


def _broker_vendor_data_readiness_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    readiness = route["broker_vendor_data_readiness"]
    prefix = "route_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(readiness["provided"]),
            "is",
            True,
            _to_bool(readiness["provided"]),
            "route-enable broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(readiness["ready"]),
            "is",
            True,
            _to_bool(readiness["ready"]),
            "route-enable broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(readiness["failed_checks"]),
            "<=",
            0,
            int(readiness["failed_checks"]) <= 0,
            "route-enable broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_checks(route: dict[str, Any]) -> list[dict[str, object]]:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    checks = [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "route-enable broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "route-enable broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            route["adapter"],
            bool(vendor["adapter"] and route["adapter"] and vendor["adapter"] == route["adapter"]),
            "route-enable broker-readiness vendor market-data adapter does not match dispatch adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            route["market"],
            bool(vendor["market"] and route["market"] and vendor["market"] == route["market"]),
            "route-enable broker-readiness vendor market-data market does not match dispatch market",
        ),
        _check(
            f"{prefix}_manifest_run_type",
            vendor["manifest_run_type"],
            "==",
            "vendor_market_data_batch_pipeline",
            vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline",
            "route-enable broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "route-enable broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "route-enable broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "route-enable broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "route-enable broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            float(vendor["source_file_fingerprint_coverage"]),
            ">=",
            1.0,
            float(vendor["source_file_fingerprint_coverage"]) >= 1.0,
            "route-enable broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            float(vendor["min_mapping_coverage"]),
            ">=",
            1.0,
            float(vendor["min_mapping_coverage"]) >= 1.0,
            "route-enable broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(vendor["unique_mapping_drafts"]),
            ">",
            0,
            int(vendor["unique_mapping_drafts"]) > 0,
            "route-enable broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "route-enable broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "route-enable broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "route-enable broker-readiness vendor market-data comparison has failed checks",
        ),
    ]
    if _target_application_batch_active(vendor):
        dataset_count = int(vendor["dataset_count"])
        mapping_application_count = int(vendor["mapping_application_count"])
        unique_mapping_applications = int(vendor["unique_mapping_applications"])
        target_application_coverage = float(vendor["target_application_coverage"])
        lineage_datasets = _target_application_lineage_dataset_count(vendor)
        lineage_consistency_required = _to_bool(
            vendor["application_lineage_consistency_required"]
        )
        lineage_consistent = _to_bool(vendor["application_lineage_consistent"])
        lineage_match_required = _to_bool(
            route["broker_vendor_market_data_batch_lineage_match_required"]
        )
        lineage_matches = _to_bool(
            route["broker_vendor_market_data_batch_lineage_matches"]
        )
        current_lineage_sha256 = _sha256_text(
            route["vendor_market_data_batch_application_lineage_sha256"]
        )
        broker_lineage_sha256 = _sha256_text(
            route["broker_vendor_market_data_batch_application_lineage_sha256"]
        )
        scaleup_carried_lineage_sha256 = _sha256_text(
            route[
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        cutover_carried_lineage_sha256 = _sha256_text(
            route[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        route_carried_lineage_sha256 = _sha256_text(
            route[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        dispatch_carried_lineage_sha256 = _target_application_lineage_sha256(vendor)
        mapping_source_mode = _identity_key(vendor["mapping_source_mode"])
        checks.extend(
            [
                _check(
                    f"{prefix}_mapping_source_mode",
                    mapping_source_mode,
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    mapping_source_mode == TARGET_APPLICATION_BATCH_MODE,
                    "route-enable broker-readiness vendor target applications are missing strict source mode",
                ),
                _check(
                    f"{prefix}_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "route-enable broker-readiness vendor target applications are not aligned one for one",
                ),
                _check(
                    f"{prefix}_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "route-enable broker-readiness vendor target applications are not distinct per dataset",
                ),
                _check(
                    f"{prefix}_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "route-enable broker-readiness vendor target-application coverage is incomplete",
                ),
                _check(
                    f"{prefix}_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "route-enable broker-readiness vendor datasets are missing target-application lineage",
                ),
                _check(
                    f"{prefix}_lineage_match_required",
                    lineage_match_required,
                    "is",
                    True,
                    lineage_match_required,
                    "target-application dispatch planning requires the route current/final lineage comparison",
                ),
                _check(
                    f"{prefix}_lineage_matches",
                    lineage_matches,
                    "is",
                    True,
                    lineage_match_required and lineage_matches,
                    "route current and final target-application lineages do not match",
                ),
                _check(
                    f"{prefix}_source_lineage_sha256_matches",
                    current_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and current_lineage_sha256
                        and broker_lineage_sha256
                        and current_lineage_sha256 == broker_lineage_sha256
                    ),
                    "route current/final target-lineage digests are missing or disagree",
                ),
                _check(
                    f"{prefix}_scaleup_carried_lineage_sha256_matches",
                    scaleup_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and scaleup_carried_lineage_sha256
                        and broker_lineage_sha256
                        and scaleup_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "route scale-up-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_cutover_carried_lineage_sha256_matches",
                    cutover_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and cutover_carried_lineage_sha256
                        and broker_lineage_sha256
                        and cutover_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "route cutover-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_route_carried_lineage_sha256_matches",
                    route_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and route_carried_lineage_sha256
                        and broker_lineage_sha256
                        and route_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "route-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_dispatch_carried_lineage_sha256_matches",
                    dispatch_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and dispatch_carried_lineage_sha256
                        and broker_lineage_sha256
                        and dispatch_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan carried target lineage does not match route-enable proof",
                ),
            ]
        )
        if lineage_consistency_required:
            checks.extend(
                [
                    _check(
                        f"{prefix}_application_lineage_consistent",
                        lineage_consistent,
                        "is",
                        True,
                        lineage_consistent,
                        "route final dispatch/send/ack target lineage was not consistent",
                    ),
                    *_broker_vendor_final_lineage_checks(
                        route,
                        dispatch_lineage_sha256=dispatch_carried_lineage_sha256,
                    ),
                    *_broker_vendor_route_complete_final_lineage_checks(
                        route,
                        dispatch_lineage_sha256=dispatch_carried_lineage_sha256,
                    ),
                ]
            )
    return checks


def _broker_vendor_final_lineage_checks(
    route: dict[str, Any],
    *,
    dispatch_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = ROUTE_FINAL_LINEAGE_FIELD_PREFIX
    prefix = source_prefix
    lineage_match_required = _to_bool(
        route[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(route[f"{source_prefix}_lineage_matches"])
    final_broker_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    final_current_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_current_application_lineage_sha256"]
    )
    route_broker_lineage_sha256 = _sha256_text(
        route["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    route_lineage_sha256 = _sha256_text(
        route[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    checks = [
        _check(
            f"{prefix}_final_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target dispatch planning requires route enable's final lineage comparison",
        ),
        _check(
            f"{prefix}_final_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "route enable did not reconcile every final target-lineage view",
        ),
        _check(
            f"{prefix}_final_source_lineage_sha256_matches",
            final_current_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and final_current_lineage_sha256
                and final_broker_lineage_sha256
                and final_current_lineage_sha256 == final_broker_lineage_sha256
            ),
            "route enable's final source lineage does not match final broker proof",
        ),
        _check(
            f"{prefix}_final_broker_lineage_sha256_matches",
            route_broker_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and route_broker_lineage_sha256
                and final_broker_lineage_sha256
                and route_broker_lineage_sha256 == final_broker_lineage_sha256
            ),
            "route enable's current/final broker digest does not match its final comparison",
        ),
        _check(
            f"{prefix}_final_application_lineage_sha256_matches",
            route_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and route_lineage_sha256
                and final_broker_lineage_sha256
                and route_lineage_sha256 == final_broker_lineage_sha256
            ),
            "route enable's independently recomputed batch digest does not match final comparison",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(route[f"{source_prefix}_{field}"])
        checks.append(
            _check(
                f"{prefix}_final_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and final_broker_lineage_sha256
                    and carried_sha256 == final_broker_lineage_sha256
                ),
                (
                    f"route enable's {stage.replace('_', '-')} target lineage does not "
                    "match final broker proof"
                ),
            )
        )
    route_review_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    checks.extend(
        [
            _check(
                f"{prefix}_final_route_enable_review_carried_lineage_sha256_matches",
                route_review_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_review_lineage_sha256
                    and final_broker_lineage_sha256
                    and route_review_lineage_sha256 == final_broker_lineage_sha256
                ),
                "route enable's carried review lineage does not match final broker proof",
            ),
            _check(
                f"{prefix}_dispatch_plan_review_carried_lineage_sha256_matches",
                dispatch_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_lineage_sha256
                    and final_broker_lineage_sha256
                    and dispatch_lineage_sha256 == final_broker_lineage_sha256
                ),
                "dispatch planning's independently recomputed target lineage does not match final broker proof",
            ),
        ]
    )
    return checks


def _broker_vendor_route_complete_final_lineage_checks(
    route: dict[str, Any],
    *,
    dispatch_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = ROUTE_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = f"{ROUTE_FINAL_LINEAGE_FIELD_PREFIX}_route_final"
    lineage_match_required = _to_bool(
        route[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(route[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        route[
            f"{ROUTE_FINAL_LINEAGE_FIELD_PREFIX}_broker_application_lineage_sha256"
        ]
    )
    compatibility_route_lineage_sha256 = _sha256_text(
        route[
            f"{ROUTE_FINAL_LINEAGE_FIELD_PREFIX}_carried_application_lineage_sha256"
        ]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target dispatch planning requires route enable's complete final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "route enable did not match every complete final target-lineage view",
        ),
        _check(
            f"{check_prefix}_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "route final source lineage does not match final broker proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
            compatibility_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_broker_lineage_sha256
                and broker_lineage_sha256
                and compatibility_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "dispatch compatibility broker digest does not match route's final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_route_carried_lineage_sha256_matches",
            compatibility_route_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_route_lineage_sha256
                and broker_lineage_sha256
                and compatibility_route_lineage_sha256 == broker_lineage_sha256
            ),
            "dispatch compatibility route digest does not match route's final proof",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
        (
            "route_enable_review",
            "route_enable_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_plan_review",
            "dispatch_plan_review_carried_application_lineage_sha256",
        ),
        (
            "send_packet_review",
            "send_packet_review_carried_application_lineage_sha256",
        ),
        (
            "ack_reconciliation_review",
            "ack_reconciliation_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_final_review",
            "roundtrip_final_review_carried_application_lineage_sha256",
        ),
        (
            "broker_readiness_review",
            "broker_readiness_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_final_review",
            "scaleup_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_final_review",
            "cutover_final_review_carried_application_lineage_sha256",
        ),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(route[f"{source_prefix}_{field}"])
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"route enable's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    route_final_review_lineage_sha256 = _sha256_text(
        route[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    dispatch_final_review_lineage_sha256 = _sha256_text(
        dispatch_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_route_final_review_carried_lineage_sha256_matches",
                route_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and route_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "route enable's carried final-review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_dispatch_final_review_carried_lineage_sha256_matches",
                dispatch_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and dispatch_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "dispatch planning's independently recomputed target lineage does not match route's final proof",
            ),
        ]
    )
    return checks


def _target_application_batch_active(vendor: dict[str, Any]) -> bool:
    mapping_sources = {
        value.strip().lower()
        for value in str(vendor["mapping_sources"]).split(";")
        if value.strip()
    }
    return bool(
        _identity_key(vendor["mapping_source_mode"]) == TARGET_APPLICATION_BATCH_MODE
        or "verified_target_application" in mapping_sources
        or int(vendor["mapping_application_count"]) > 0
        or float(vendor["target_application_coverage"]) > 0.0
    )


def _target_application_lineage_dataset_count(vendor: dict[str, Any]) -> int:
    return sum(
        isinstance(dataset, dict)
        and all(
            _first_text(dataset.get(field, ""))
            for field in TARGET_APPLICATION_DATASET_LINEAGE_FIELDS
        )
        for dataset in vendor["datasets"]
    )


def _target_application_lineage_sha256(vendor: dict[str, Any]) -> str:
    identities: list[dict[str, str]] = []
    for dataset in vendor["datasets"]:
        if not isinstance(dataset, dict):
            return ""
        identity = {
            field: _object_text(dataset.get(field))
            for field in TARGET_APPLICATION_LINEAGE_IDENTITY_FIELDS
        }
        if not all(identity.values()):
            return ""
        identities.append(identity)
    if not identities:
        return ""
    canonical = json.dumps(
        sorted(
            identities,
            key=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_text(value: object) -> str:
    normalized = _object_text(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return ""
    return normalized


def _shadow_broker_readiness_active_for(route: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "vendor_data_readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(route.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(route[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    route: dict[str, Any],
    *,
    key_prefix: str,
    check_prefix: str,
    label: str,
    check_provided: bool = False,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    if check_provided:
        checks.append(
            _check(
                f"{check_prefix}_readiness_provided",
                _to_bool(route[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(route[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(route[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(route[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(route[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    route[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    route["adapter"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "adapter")]
                        and route[_shadow_broker_key(key_prefix, "adapter")] == route["adapter"]
                    ),
                    f"{label} adapter does not match dispatch adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(route[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_sessions")])
    if vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_vendor_data_readiness_present_for_broker_sessions",
                    vendor_sessions,
                    "==",
                    sessions,
                    vendor_sessions == sessions,
                    f"{label} vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_provided",
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")]),
                    "==",
                    sessions,
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_ready",
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_failed_checks",
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]) <= 0,
                    f"{label} vendor-data wrapper proof has failed checks",
                ),
            ]
        )
    route_sessions = int(route[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]) == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and route[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == route["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    route[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and route[_shadow_broker_key(key_prefix, "route_readiness_market")] == route["market"]
                    ),
                    f"{label} route-readiness market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")] == route["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == route["market"]
                    ),
                    f"{label} dispatch round-trip market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]) <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(route[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    route["strategy"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == route["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match dispatch strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    route["market"],
                    bool(
                        route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == route["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match dispatch market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(route[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _summary(
    route: dict[str, Any],
    dispatch_orders: pd.DataFrame,
    checks: pd.DataFrame,
    upload_file_hash: str,
    thresholds: BrokerDispatchThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "dispatch_state": "armed_dry_run" if ready else "disabled",
                "target_mode": route["target_mode"],
                "strategy": route["strategy"],
                "market": route["market"],
                "scenario_key": route["scenario_key"],
                "adapter": route["adapter"],
                "broker_schema_status": route["broker_schema_status"],
                "broker_schema_reviewed": route["broker_schema_reviewed"],
                "broker_schema_review_mode": route["broker_schema_review_mode"],
                "dispatch_orders": int(len(dispatch_orders)),
                "route_upload_orders": int(route["upload_orders"]),
                "max_orders_per_session": int(route["max_orders_per_session"]),
                "max_notional_per_session": float(route["max_notional_per_session"]),
                "dispatch_total_notional": _dispatch_total_notional(dispatch_orders),
                "strategy_portfolio_required": route["strategy_portfolio_required"],
                "strategy_portfolio_provided": route["strategy_portfolio_provided"],
                "strategy_portfolio_ready": route["strategy_portfolio_ready"],
                "strategy_portfolio_deployment_mode": route["strategy_portfolio_deployment_mode"],
                "strategy_portfolio_allocation_mode": route["strategy_portfolio_allocation_mode"],
                "strategy_portfolio_capital_currency": route["strategy_portfolio_capital_currency"],
                "strategy_portfolio_selected_profile": route["strategy_portfolio_selected_profile"],
                "strategy_portfolio_selected_strategy": route["strategy_portfolio_selected_strategy"],
                "strategy_portfolio_selected_market": route["strategy_portfolio_selected_market"],
                "strategy_portfolio_selected_eligible": route["strategy_portfolio_selected_eligible"],
                "strategy_portfolio_selected_allocation_weight": route[
                    "strategy_portfolio_selected_allocation_weight"
                ],
                "strategy_portfolio_selected_allocation_notional": route[
                    "strategy_portfolio_selected_allocation_notional"
                ],
                "strategy_portfolio_notional_cap_applied": route["strategy_portfolio_notional_cap_applied"],
                "strategy_portfolio_min_strategy_count": route["strategy_portfolio_min_strategy_count"],
                "strategy_portfolio_min_market_count": route["strategy_portfolio_min_market_count"],
                "strategy_portfolio_max_strategy_weight": route["strategy_portfolio_max_strategy_weight"],
                "strategy_portfolio_max_market_weight": route["strategy_portfolio_max_market_weight"],
                "strategy_portfolio_allocated_strategy_count": route[
                    "strategy_portfolio_allocated_strategy_count"
                ],
                "strategy_portfolio_allocated_market_count": route["strategy_portfolio_allocated_market_count"],
                "strategy_portfolio_top_strategy_by_weight": route["strategy_portfolio_top_strategy_by_weight"],
                "strategy_portfolio_top_market_by_weight": route["strategy_portfolio_top_market_by_weight"],
                "strategy_portfolio_max_strategy_allocation_weight": route[
                    "strategy_portfolio_max_strategy_allocation_weight"
                ],
                "strategy_portfolio_max_market_allocation_weight": route[
                    "strategy_portfolio_max_market_allocation_weight"
                ],
                "pre_portfolio_max_notional_per_session": route["pre_portfolio_max_notional_per_session"],
                **_route_lineage_output_fields(route),
                "authorizes_submission": False,
                "upload_file_hash": upload_file_hash,
                "dispatch_batch_id": str(dispatch_orders.iloc[0]["dispatch_batch_id"]) if not dispatch_orders.empty else "",
                "route_readiness_required": _route_readiness_required(thresholds, route),
                "route_readiness_provided": route["route_readiness_provided"],
                "route_readiness_ready": route["route_readiness_ready"],
                "route_readiness_strategy": route["route_readiness_strategy"],
                "route_readiness_market": route["route_readiness_market"],
                "route_readiness_route_ready_pairs": route["route_readiness_route_ready_pairs"],
                "route_readiness_gap_pairs": route["route_readiness_gap_pairs"],
                "route_readiness_ops_launch_controls_present": route[
                    "route_readiness_ops_launch_controls_present"
                ],
                "route_readiness_ops_launch_controls_blocked_pairs": route[
                    "route_readiness_ops_launch_controls_blocked_pairs"
                ],
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": route[
                    "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"
                ],
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": route[
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"
                ],
                **_broker_route_readiness_summary_fields(route),
                **_resume_route_readiness_summary_fields(
                    route,
                    source_prefix="broker_resume_broker_route_readiness",
                    output_prefix="route_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_summary_fields(
                    route,
                    source_prefix="broker_resume_incident_broker_route_readiness",
                    output_prefix="route_broker_resume_incident_broker_route_readiness",
                ),
                "shadow_broker_readiness_sessions": route["shadow_broker_readiness_sessions"],
                "shadow_broker_readiness_ready_sessions": route["shadow_broker_readiness_ready_sessions"],
                "shadow_broker_vendor_data_readiness_sessions": route[
                    "shadow_broker_vendor_data_readiness_sessions"
                ],
                "shadow_broker_vendor_data_readiness_provided_sessions": route[
                    "shadow_broker_vendor_data_readiness_provided_sessions"
                ],
                "shadow_broker_vendor_data_readiness_ready_sessions": route[
                    "shadow_broker_vendor_data_readiness_ready_sessions"
                ],
                "shadow_broker_vendor_data_readiness_failed_checks": route[
                    "shadow_broker_vendor_data_readiness_failed_checks"
                ],
                "shadow_broker_adapter": route["shadow_broker_adapter"],
                "shadow_broker_adapter_count": route["shadow_broker_adapter_count"],
                "shadow_broker_route_readiness_sessions": route["shadow_broker_route_readiness_sessions"],
                "shadow_broker_route_readiness_ready_sessions": route[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "shadow_broker_route_readiness_strategy": route["shadow_broker_route_readiness_strategy"],
                "shadow_broker_route_readiness_market": route["shadow_broker_route_readiness_market"],
                "shadow_broker_route_readiness_gap_pairs": route["shadow_broker_route_readiness_gap_pairs"],
                "shadow_broker_dispatch_roundtrip_sessions": route["shadow_broker_dispatch_roundtrip_sessions"],
                "shadow_broker_dispatch_roundtrip_ready_sessions": route[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_dispatch_roundtrip_strategy": route["shadow_broker_dispatch_roundtrip_strategy"],
                "shadow_broker_dispatch_roundtrip_market": route["shadow_broker_dispatch_roundtrip_market"],
                "shadow_broker_dispatch_roundtrip_scenario_count": route[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "shadow_broker_dispatch_roundtrip_missing_request_acks": route[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "shadow_broker_dispatch_roundtrip_rejected_orders": route[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "shadow_broker_dispatch_roundtrip_unmatched_acks": route[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "shadow_broker_route_dispatch_roundtrip_sessions": route[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": route[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_strategy": route[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "shadow_broker_route_dispatch_roundtrip_market": route[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "shadow_broker_route_dispatch_roundtrip_scenario_count": route[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_summary_fields(route),
                **_broker_vendor_data_readiness_summary_fields(route),
                **_broker_vendor_market_data_batch_summary_fields(route),
                **_vendor_market_data_batch_summary_fields(route),
                "route_dispatch_roundtrip_required": route["dispatch_roundtrip_required"],
                "route_dispatch_roundtrip_provided": route["dispatch_roundtrip_provided"],
                "route_dispatch_roundtrip_ready": route["dispatch_roundtrip_ready"],
                "route_dispatch_roundtrip_target_mode": route["dispatch_roundtrip_target_mode"],
                "route_dispatch_roundtrip_strategy": route["dispatch_roundtrip_strategy"],
                "route_dispatch_roundtrip_market": route["dispatch_roundtrip_market"],
                "route_dispatch_roundtrip_scenario_key": route["dispatch_roundtrip_scenario_key"],
                "route_dispatch_roundtrip_batch_id": route["dispatch_roundtrip_batch_id"],
                "route_dispatch_roundtrip_requests": route["dispatch_roundtrip_requests"],
                "route_dispatch_roundtrip_acked_orders": route["dispatch_roundtrip_acked_orders"],
                "route_dispatch_roundtrip_missing_request_acks": route["dispatch_roundtrip_missing_request_acks"],
                "route_dispatch_roundtrip_rejected_orders": route["dispatch_roundtrip_rejected_orders"],
                "route_dispatch_roundtrip_unmatched_acks": route["dispatch_roundtrip_unmatched_acks"],
                "route_enable_dispatch_roundtrip_failed_checks": route[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "dry_run_only": True,
                "failed_checks": failed,
                "recommendation": "ready_for_broker_dryrun_dispatch" if ready else "keep_dispatch_disabled",
            }
        ]
    )


def _summary_with_actions(
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    out = summary.copy()
    failed = _failed_check_rows(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    out["failed_check_count"] = int(len(failed))
    out["failed_check_names"] = ";".join(failed["check"].astype(str).tolist()) if not failed.empty else ""
    out["first_failed_reason"] = _object_text(failed.iloc[0].get("reason")).strip() if not failed.empty else ""
    out["primary_blocker_check"] = _object_text(failed.iloc[0].get("check")).strip() if not failed.empty else ""
    out["primary_blocker_value"] = _object_text(failed.iloc[0].get("value")).strip() if not failed.empty else ""
    out["primary_blocker_operator"] = _object_text(failed.iloc[0].get("operator")).strip() if not failed.empty else ""
    out["primary_blocker_threshold"] = _object_text(failed.iloc[0].get("threshold")).strip() if not failed.empty else ""
    out["primary_blocker_reason"] = _object_text(failed.iloc[0].get("reason")).strip() if not failed.empty else ""
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(summary: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "broker_dispatch_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _object_text(row.get("operator")).strip(),
                "expected": row.get("threshold"),
                "target_mode": _object_text(summary.get("target_mode")).strip(),
                "strategy": _object_text(summary.get("strategy")).strip(),
                "market": _object_text(summary.get("market")).strip(),
                "scenario_key": _object_text(summary.get("scenario_key")).strip(),
                "adapter": _object_text(summary.get("adapter")).strip(),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "reason": _object_text(row.get("reason")).strip(),
                "recommendation": _action_recommendation(check),
            }
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].copy()


def _component(check: str) -> str:
    if check in {"route_enabled", "target_mode_matches", "adapter_matches"} or check.startswith(
        ("route_enable_lineage_", "route_enable_manifest_", "route_enable_non_authorizing")
    ):
        return "route_enable"
    if check.startswith("strategy_portfolio_") or "strategy_portfolio" in check:
        return "strategy_portfolio"
    if check.startswith("route_broker_resume_") or check.startswith("broker_resume_"):
        return "resume_gate"
    if "route_readiness" in check:
        return "route_readiness"
    if "vendor_market_data_batch" in check:
        return "vendor_market_data"
    if "broker_vendor_data_readiness" in check or "vendor_data_readiness" in check:
        return "broker_vendor_data_readiness"
    if "dispatch_roundtrip" in check:
        return "broker_dispatch_roundtrip"
    if check.startswith("dispatch_orders_") or check in {
        "unique_dispatch_order_id",
        "unique_source_order_id",
        "dry_run_only",
    }:
        return "broker_dispatch_plan"
    if check.startswith("dispatch_notional_"):
        return "broker_dispatch_plan"
    return "broker_dispatch_plan"


def _next_gate(check: str) -> str:
    component = _component(check)
    if component == "route_enable":
        return "review-route-enable"
    if component == "strategy_portfolio":
        return "review-cutover-gate"
    if component == "route_readiness":
        return "review-route-readiness"
    if component == "broker_dispatch_roundtrip":
        return "review-broker-dispatch-roundtrip"
    if component == "vendor_market_data":
        return "pipeline-vendor-market-data-batch"
    if component == "broker_vendor_data_readiness":
        return "pipeline-broker-vendor-readiness"
    if component == "resume_gate":
        return "review-resume-gate"
    return "plan-broker-dispatch"


def _action_recommendation(check: str) -> str:
    component = _component(check)
    if component == "route_enable":
        return "repair_or_rebuild_route_enable_packet"
    if component == "strategy_portfolio":
        return "repair_strategy_portfolio_cutover_allocation"
    if component == "route_readiness":
        return "rerun_route_readiness_before_dispatch"
    if component == "broker_dispatch_roundtrip":
        return "rerun_broker_dispatch_roundtrip_before_dispatch"
    if component == "vendor_market_data":
        return "refresh_vendor_market_data_batch_proof"
    if component == "broker_vendor_data_readiness":
        return "refresh_broker_vendor_data_readiness_wrapper"
    if component == "resume_gate":
        return "repair_resume_gate_proof_before_dispatch"
    if check in {"unique_source_order_id", "unique_dispatch_order_id"}:
        return "deduplicate_dispatch_order_id_inputs"
    if check.startswith("dispatch_notional_"):
        return "reduce_dispatch_notional_or_refresh_allocation"
    if check.startswith("dispatch_orders_"):
        return "repair_dispatch_order_count_or_route_limits"
    if check == "dry_run_only":
        return "keep_dispatch_plan_dry_run_only"
    return "repair_broker_dispatch_inputs"


def _broker_route_readiness_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_broker_route_readiness_required": route["broker_route_readiness_required"],
        "route_broker_route_readiness_provided": route["broker_route_readiness_provided"],
        "route_broker_route_readiness_ready": route["broker_route_readiness_ready"],
        "route_broker_route_readiness_strategy": route["broker_route_readiness_strategy"],
        "route_broker_route_readiness_market": route["broker_route_readiness_market"],
        "route_broker_route_readiness_route_ready_pairs": route["broker_route_readiness_route_ready_pairs"],
        "route_broker_route_readiness_gap_pairs": route["broker_route_readiness_gap_pairs"],
        "route_broker_route_readiness_recommendation": route["broker_route_readiness_recommendation"],
        "route_broker_route_readiness_ops_launch_controls_ready": route[
            "broker_route_readiness_ops_launch_controls_ready"
        ],
        "route_broker_route_readiness_ops_launch_control_failures": route[
            "broker_route_readiness_ops_launch_control_failures"
        ],
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": route[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": route[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": route[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": route[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _resume_route_readiness_summary_fields(
    route: dict[str, Any],
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, Any]:
    return {
        f"{output_prefix}_required": route[f"{source_prefix}_required"],
        f"{output_prefix}_provided": route[f"{source_prefix}_provided"],
        f"{output_prefix}_ready": route[f"{source_prefix}_ready"],
        f"{output_prefix}_strategy": route[f"{source_prefix}_strategy"],
        f"{output_prefix}_market": route[f"{source_prefix}_market"],
        f"{output_prefix}_route_ready_pairs": route[f"{source_prefix}_route_ready_pairs"],
        f"{output_prefix}_gap_pairs": route[f"{source_prefix}_gap_pairs"],
        f"{output_prefix}_recommendation": route[f"{source_prefix}_recommendation"],
        f"{output_prefix}_ops_launch_controls_ready": route[f"{source_prefix}_ops_launch_controls_ready"],
        f"{output_prefix}_ops_launch_control_failures": route[f"{source_prefix}_ops_launch_control_failures"],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": route[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": route[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": route[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": route[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _broker_shadow_broker_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_broker_shadow_broker_readiness_provided": route["broker_shadow_broker_readiness_provided"],
        "route_broker_shadow_broker_readiness_sessions": route["broker_shadow_broker_readiness_sessions"],
        "route_broker_shadow_broker_readiness_ready_sessions": route[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "route_broker_shadow_broker_vendor_data_readiness_sessions": route[
            "broker_shadow_broker_vendor_data_readiness_sessions"
        ],
        "route_broker_shadow_broker_vendor_data_readiness_provided_sessions": route[
            "broker_shadow_broker_vendor_data_readiness_provided_sessions"
        ],
        "route_broker_shadow_broker_vendor_data_readiness_ready_sessions": route[
            "broker_shadow_broker_vendor_data_readiness_ready_sessions"
        ],
        "route_broker_shadow_broker_vendor_data_readiness_failed_checks": route[
            "broker_shadow_broker_vendor_data_readiness_failed_checks"
        ],
        "route_broker_shadow_broker_adapter": route["broker_shadow_broker_adapter"],
        "route_broker_shadow_broker_adapter_count": route["broker_shadow_broker_adapter_count"],
        "route_broker_shadow_broker_route_readiness_sessions": route[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "route_broker_shadow_broker_route_readiness_ready_sessions": route[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "route_broker_shadow_broker_route_readiness_strategy": route[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "route_broker_shadow_broker_route_readiness_market": route["broker_shadow_broker_route_readiness_market"],
        "route_broker_shadow_broker_route_readiness_gap_pairs": route[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_sessions": route[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_ready_sessions": route[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_strategy": route[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_market": route[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_scenario_count": route[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": route[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_rejected_orders": route[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "route_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": route[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_sessions": route[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": route[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_strategy": route[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_market": route[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "route_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": route[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    vendor = route["vendor_market_data_batch"]
    return {
        "route_vendor_market_data_batch_provided": vendor["provided"],
        "route_vendor_market_data_batch_ready": vendor["ready"],
        "route_vendor_market_data_batch_adapter": vendor["adapter"],
        "route_vendor_market_data_batch_kind": vendor["kind"],
        "route_vendor_market_data_batch_manifest_run_type": vendor["manifest_run_type"],
        "route_vendor_market_data_batch_market": vendor["market"],
        "route_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "route_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "route_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "route_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "route_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "route_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "route_vendor_market_data_batch_source_file_fingerprint_coverage": vendor[
            "source_file_fingerprint_coverage"
        ],
        "route_vendor_market_data_batch_min_mapping_coverage": vendor["min_mapping_coverage"],
        "route_vendor_market_data_batch_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        "route_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "route_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "route_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "route_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    vendor = route["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    dispatch_lineage_sha256 = _target_application_lineage_sha256(vendor)
    return {
        f"{field_prefix}_provided": vendor["provided"],
        f"{field_prefix}_ready": vendor["ready"],
        f"{field_prefix}_adapter": vendor["adapter"],
        f"{field_prefix}_kind": vendor["kind"],
        f"{field_prefix}_manifest_run_type": vendor["manifest_run_type"],
        f"{field_prefix}_market": vendor["market"],
        f"{field_prefix}_dataset_count": vendor["dataset_count"],
        f"{field_prefix}_ready_datasets": vendor["ready_datasets"],
        f"{field_prefix}_failed_datasets": vendor["failed_datasets"],
        f"{field_prefix}_ready_rate": vendor["ready_rate"],
        f"{field_prefix}_unique_source_files": vendor["unique_source_files"],
        f"{field_prefix}_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        f"{field_prefix}_source_file_fingerprint_coverage": vendor["source_file_fingerprint_coverage"],
        f"{field_prefix}_min_mapping_coverage": vendor["min_mapping_coverage"],
        f"{field_prefix}_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        f"{field_prefix}_mapping_sources": vendor["mapping_sources"],
        f"{field_prefix}_mapping_source_mode": vendor["mapping_source_mode"],
        f"{field_prefix}_mapping_application_count": vendor["mapping_application_count"],
        f"{field_prefix}_unique_mapping_applications": vendor["unique_mapping_applications"],
        f"{field_prefix}_target_application_coverage": vendor["target_application_coverage"],
        f"{field_prefix}_application_lineage_consistency_required": vendor[
            "application_lineage_consistency_required"
        ],
        f"{field_prefix}_application_lineage_consistent": vendor[
            "application_lineage_consistent"
        ],
        **_broker_vendor_final_lineage_summary_fields(route),
        **_broker_vendor_route_complete_final_lineage_summary_fields(route),
        "route_broker_vendor_market_data_batch_lineage_match_required": route[
            "broker_vendor_market_data_batch_lineage_match_required"
        ],
        "route_broker_vendor_market_data_batch_lineage_matches": route[
            "broker_vendor_market_data_batch_lineage_matches"
        ],
        "route_vendor_market_data_batch_application_lineage_sha256": route[
            "vendor_market_data_batch_application_lineage_sha256"
        ],
        "route_broker_vendor_market_data_batch_application_lineage_sha256": route[
            "broker_vendor_market_data_batch_application_lineage_sha256"
        ],
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": route[
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": route[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        f"{field_prefix}_application_lineage_sha256": route[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            dispatch_lineage_sha256
        ),
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_final_lineage_summary_fields(
    route: dict[str, Any],
) -> dict[str, Any]:
    source_prefix = ROUTE_FINAL_LINEAGE_FIELD_PREFIX
    field_prefix = ROUTE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{field_prefix}_lineage_match_required": route[
            f"{source_prefix}_lineage_match_required"
        ],
        f"{field_prefix}_lineage_matches": route[
            f"{source_prefix}_lineage_matches"
        ],
        f"{field_prefix}_route_enable_review_carried_application_lineage_sha256": route[
            f"{source_prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in ROUTE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = route[f"{source_prefix}_{field}"]
    return fields


def _broker_vendor_route_complete_final_lineage_summary_fields(
    route: dict[str, Any],
) -> dict[str, Any]:
    prefix = ROUTE_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": route[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": route[f"{prefix}_lineage_matches"],
        f"{prefix}_route_final_review_carried_application_lineage_sha256": route[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in ROUTE_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = route[f"{prefix}_{field}"]
    return fields


def _broker_vendor_data_readiness_summary_fields(route: dict[str, Any]) -> dict[str, Any]:
    readiness = route["broker_vendor_data_readiness"]
    return {
        "route_broker_vendor_data_readiness_provided": readiness["provided"],
        "route_broker_vendor_data_readiness_ready": readiness["ready"],
        "route_broker_vendor_data_readiness_failed_checks": readiness["failed_checks"],
    }


def _broker_shadow_broker_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(summary["route_broker_shadow_broker_readiness_provided"]),
        "sessions": int(summary["route_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(summary["route_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(summary["route_broker_shadow_broker_adapter"]),
        "adapter_count": int(summary["route_broker_shadow_broker_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(summary["route_broker_shadow_broker_vendor_data_readiness_sessions"]),
            "provided_sessions": int(
                summary["route_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
            ),
            "ready_sessions": int(summary["route_broker_shadow_broker_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(summary["route_broker_shadow_broker_vendor_data_readiness_failed_checks"]),
        },
        "route_readiness": {
            "sessions": int(summary["route_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_route_readiness_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(summary["route_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(summary["route_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(summary["route_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(summary["route_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(summary["route_broker_shadow_broker_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(
                summary["route_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(summary["route_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]),
            "max_unmatched_acks": int(summary["route_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(summary["route_broker_shadow_broker_route_dispatch_roundtrip_strategy"]),
            "market": str(summary["route_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(summary["route_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(summary["route_vendor_market_data_batch_provided"]),
        "ready": _to_bool(summary["route_vendor_market_data_batch_ready"]),
        "adapter": str(summary["route_vendor_market_data_batch_adapter"]),
        "kind": str(summary["route_vendor_market_data_batch_kind"]),
        "manifest_run_type": str(summary["route_vendor_market_data_batch_manifest_run_type"]),
        "market": str(summary["route_vendor_market_data_batch_market"]),
        "dataset_count": int(summary["route_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(summary["route_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(summary["route_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(summary["route_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(summary["route_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            summary["route_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            summary["route_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(summary["route_vendor_market_data_batch_min_mapping_coverage"]),
        "unique_mapping_drafts": int(summary["route_vendor_market_data_batch_unique_mapping_drafts"]),
        "mapping_sources": str(summary["route_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(summary["route_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(summary["route_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary["route_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(summary: pd.Series) -> dict[str, Any]:
    field_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "adapter": str(summary[f"{field_prefix}_adapter"]),
        "kind": str(summary[f"{field_prefix}_kind"]),
        "manifest_run_type": str(summary[f"{field_prefix}_manifest_run_type"]),
        "market": str(summary[f"{field_prefix}_market"]),
        "dataset_count": int(summary[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(summary[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(summary[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(summary[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(summary[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(summary[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            summary[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(summary[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(summary[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": str(summary[f"{field_prefix}_mapping_sources"]),
        "mapping_source_mode": str(summary[f"{field_prefix}_mapping_source_mode"]),
        "mapping_application_count": int(summary[f"{field_prefix}_mapping_application_count"]),
        "unique_mapping_applications": int(
            summary[f"{field_prefix}_unique_mapping_applications"]
        ),
        "target_application_coverage": _jsonable(
            summary[f"{field_prefix}_target_application_coverage"]
        ),
        "application_lineage_consistency_required": _to_bool(
            summary[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        "application_lineage_consistent": _to_bool(
            summary[f"{field_prefix}_application_lineage_consistent"]
        ),
        "application_lineage_sha256": str(
            summary[f"{field_prefix}_application_lineage_sha256"]
        ),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_dispatch_final_lineage_config(
    summary: pd.Series,
) -> dict[str, Any]:
    field_prefix = ROUTE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(summary[f"{field_prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{field_prefix}_lineage_matches"]),
        "route_enable_review_carried_application_lineage_sha256": str(
            summary[
                f"{field_prefix}_route_enable_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            summary[
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in ROUTE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(summary[f"{field_prefix}_{field}"])
    return config


def _broker_vendor_dispatch_complete_final_lineage_config(
    summary: pd.Series,
) -> dict[str, Any]:
    prefix = ROUTE_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(summary[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{prefix}_lineage_matches"]),
        "route_final_review_carried_application_lineage_sha256": str(
            summary[
                f"{prefix}_route_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            summary[
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in ROUTE_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(summary[f"{prefix}_{field}"])
    return config


def _broker_vendor_data_readiness_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(summary["route_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(summary["route_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(summary["route_broker_vendor_data_readiness_failed_checks"]),
    }


def _broker_route_readiness_config(summary: pd.Series) -> dict[str, Any]:
    return {
        "required": _to_bool(summary["route_broker_route_readiness_required"]),
        "provided": _to_bool(summary["route_broker_route_readiness_provided"]),
        "ready": _to_bool(summary["route_broker_route_readiness_ready"]),
        "strategy": str(summary["route_broker_route_readiness_strategy"]),
        "market": str(summary["route_broker_route_readiness_market"]),
        "route_ready_pairs": int(summary["route_broker_route_readiness_route_ready_pairs"]),
        "gap_pairs": int(summary["route_broker_route_readiness_gap_pairs"]),
        "recommendation": str(summary["route_broker_route_readiness_recommendation"]),
        "ops_launch_controls_ready": _to_bool(summary["route_broker_route_readiness_ops_launch_controls_ready"]),
        "ops_launch_control_failures": str(summary["route_broker_route_readiness_ops_launch_control_failures"]),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _resume_route_readiness_config(summary: pd.Series, prefix: str) -> dict[str, Any]:
    return {
        "required": _to_bool(summary[f"{prefix}_required"]),
        "provided": _to_bool(summary[f"{prefix}_provided"]),
        "ready": _to_bool(summary[f"{prefix}_ready"]),
        "strategy": str(summary[f"{prefix}_strategy"]),
        "market": str(summary[f"{prefix}_market"]),
        "route_ready_pairs": int(summary[f"{prefix}_route_ready_pairs"]),
        "gap_pairs": int(summary[f"{prefix}_gap_pairs"]),
        "recommendation": str(summary[f"{prefix}_recommendation"]),
        "ops_launch_controls_ready": _to_bool(summary[f"{prefix}_ops_launch_controls_ready"]),
        "ops_launch_control_failures": str(summary[f"{prefix}_ops_launch_control_failures"]),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _config(
    route: dict[str, Any],
    dispatch_orders: pd.DataFrame,
    summary: pd.Series,
    thresholds: BrokerDispatchThresholds,
    checks: pd.DataFrame,
    upload_file_hash: str,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "ready": _to_bool(summary["ready"]),
        "failed_check_count": len(failed_check_records),
        "dispatch_state": str(summary["dispatch_state"]),
        "dry_run_only": True,
        "dispatch_batch_id": str(summary["dispatch_batch_id"]),
        "target_mode": route["target_mode"],
        "strategy": route["strategy"],
        "market": route["market"],
        "scenario_key": route["scenario_key"],
        "adapter": route["adapter"],
        "broker_readiness": {
            "adapter_schema_status": route["broker_schema_status"],
            "schema_reviewed": _to_bool(route["broker_schema_reviewed"]),
            "schema_review_mode": route["broker_schema_review_mode"],
        },
        "limits": {
            "max_orders_per_session": int(route["max_orders_per_session"]),
            "max_notional_per_session": float(route["max_notional_per_session"]),
            "stop_loss": _jsonable(route["stop_loss"]),
        },
        "strategy_portfolio": {
            "required": _to_bool(summary["strategy_portfolio_required"]),
            "provided": _to_bool(summary["strategy_portfolio_provided"]),
            "ready": _to_bool(summary["strategy_portfolio_ready"]),
            "deployment_mode": str(summary["strategy_portfolio_deployment_mode"]),
            "allocation_mode": str(summary["strategy_portfolio_allocation_mode"]),
            "capital_currency": str(summary["strategy_portfolio_capital_currency"]),
            "selected_profile": str(summary["strategy_portfolio_selected_profile"]),
            "selected_strategy": str(summary["strategy_portfolio_selected_strategy"]),
            "selected_market": str(summary["strategy_portfolio_selected_market"]),
            "selected_eligible": _to_bool(summary["strategy_portfolio_selected_eligible"]),
            "selected_allocation_weight": float(summary["strategy_portfolio_selected_allocation_weight"]),
            "selected_allocation_notional": float(summary["strategy_portfolio_selected_allocation_notional"]),
            "notional_cap_applied": _to_bool(summary["strategy_portfolio_notional_cap_applied"]),
            "min_strategy_count": int(summary["strategy_portfolio_min_strategy_count"]),
            "min_market_count": int(summary["strategy_portfolio_min_market_count"]),
            "max_strategy_weight": float(summary["strategy_portfolio_max_strategy_weight"]),
            "max_market_weight": float(summary["strategy_portfolio_max_market_weight"]),
            "allocated_strategy_count": int(summary["strategy_portfolio_allocated_strategy_count"]),
            "allocated_market_count": int(summary["strategy_portfolio_allocated_market_count"]),
            "top_strategy_by_weight": str(summary["strategy_portfolio_top_strategy_by_weight"]),
            "top_market_by_weight": str(summary["strategy_portfolio_top_market_by_weight"]),
            "max_strategy_allocation_weight": float(
                summary["strategy_portfolio_max_strategy_allocation_weight"]
            ),
            "max_market_allocation_weight": float(summary["strategy_portfolio_max_market_allocation_weight"]),
            "pre_portfolio_max_notional_per_session": float(summary["pre_portfolio_max_notional_per_session"]),
        },
        "route_enable_lineage": _route_lineage_config(summary),
        "upload": {
            "orders": int(route["upload_orders"]),
            "total_notional": float(summary["dispatch_total_notional"]),
            "file_hash": upload_file_hash,
            "output_file": route["upload_output_file"],
        },
        "route_readiness": {
            "required": _to_bool(summary["route_readiness_required"]),
            "provided": _to_bool(summary["route_readiness_provided"]),
            "ready": _to_bool(summary["route_readiness_ready"]),
            "strategy": str(summary["route_readiness_strategy"]),
            "market": str(summary["route_readiness_market"]),
            "route_ready_pairs": int(summary["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(summary["route_readiness_gap_pairs"]),
            "ops_launch_controls_present": _to_bool(summary["route_readiness_ops_launch_controls_present"]),
            "ops_launch_controls_blocked_pairs": int(
                summary["route_readiness_ops_launch_controls_blocked_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                summary["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                summary["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
            ),
            "recommendation": route["route_readiness_recommendation"],
        },
        "shadow_broker_readiness": {
            "provided": int(summary["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(summary["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(summary["shadow_broker_readiness_ready_sessions"]),
            "adapter": str(summary["shadow_broker_adapter"]),
            "adapter_count": int(summary["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(summary["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(summary["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(summary["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(summary["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(summary["shadow_broker_route_readiness_strategy"]),
                "market": str(summary["shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(summary["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(summary["shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(summary["shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(summary["shadow_broker_dispatch_roundtrip_missing_request_acks"]),
                "max_rejected_orders": int(summary["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(summary["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(summary["shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(summary["shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(summary["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "route_broker_route_readiness": _broker_route_readiness_config(summary),
        "route_broker_resume_gate": {
            "broker_route_readiness": _resume_route_readiness_config(
                summary,
                "route_broker_resume_broker_route_readiness",
            ),
            "incident_broker_route_readiness": _resume_route_readiness_config(
                summary,
                "route_broker_resume_incident_broker_route_readiness",
            ),
        },
        "route_broker_shadow_broker_readiness": _broker_shadow_broker_config(summary),
        "route_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(summary),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(summary)
        ),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": {
            "required": _to_bool(
                summary[
                    "route_broker_vendor_market_data_batch_lineage_match_required"
                ]
            ),
            "matches": _to_bool(
                summary["route_broker_vendor_market_data_batch_lineage_matches"]
            ),
            "current_application_lineage_sha256": str(
                summary["route_vendor_market_data_batch_application_lineage_sha256"]
            ),
            "broker_application_lineage_sha256": str(
                summary[
                    "route_broker_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "scaleup_carried_application_lineage_sha256": str(
                summary[
                    "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "cutover_carried_application_lineage_sha256": str(
                summary[
                    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "route_carried_application_lineage_sha256": str(
                summary[
                    "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "dispatch_carried_application_lineage_sha256": str(
                summary[
                    "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
        },
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
            _broker_vendor_dispatch_final_lineage_config(summary)
        ),
        DISPATCH_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_dispatch_complete_final_lineage_config(summary)
        ),
        "route_vendor_market_data_batch": _vendor_market_data_batch_config(summary),
        "dispatch": {
            "orders": int(len(dispatch_orders)),
            "first_dispatch_order_id": str(dispatch_orders.iloc[0]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
            "last_dispatch_order_id": str(dispatch_orders.iloc[-1]["dispatch_order_id"])
            if not dispatch_orders.empty
            else "",
        },
        "route_dispatch_roundtrip": {
            "required": _to_bool(route["dispatch_roundtrip_required"]),
            "provided": _to_bool(route["dispatch_roundtrip_provided"]),
            "ready": _to_bool(route["dispatch_roundtrip_ready"]),
            "target_mode": route["dispatch_roundtrip_target_mode"],
            "strategy": route["dispatch_roundtrip_strategy"],
            "market": route["dispatch_roundtrip_market"],
            "scenario_key": route["dispatch_roundtrip_scenario_key"],
            "dispatch_batch_id": route["dispatch_roundtrip_batch_id"],
            "requests": int(route["dispatch_roundtrip_requests"]),
            "acked_orders": int(route["dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(route["dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(route["dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(route["dispatch_roundtrip_unmatched_acks"]),
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(route["route_enable_dispatch_roundtrip_failed_checks"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
        "action_queue_count": int(len(action_queue)),
        "ready_action_count": int((statuses == "ready").sum()) if not statuses.empty else 0,
        "blocked_action_count": int((statuses == "blocked").sum()) if not statuses.empty else 0,
        "review_action_count": int((statuses == "review").sum()) if not statuses.empty else 0,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "primary_action_status": _first_action_value(action_queue, "queue_status"),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
    }


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [_jsonable_row(row) for row in failed.to_dict(orient="records")]


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Broker Dispatch Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Dispatch state: {_object_text(summary_row.get('dispatch_state')).strip()}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Scenario: {_object_text(summary_row.get('scenario_key')).strip()}",
        f"- Adapter: {_object_text(summary_row.get('adapter')).strip()}",
        f"- Dispatch orders: {_int_value(summary_row.get('dispatch_orders'))}",
        f"- Dispatch total notional: {_object_text(summary_row.get('dispatch_total_notional')).strip()}",
        f"- Route readiness ready: {_object_text(summary_row.get('route_readiness_ready')).strip()}",
        f"- Route dispatch round-trip ready: {_object_text(summary_row.get('route_dispatch_roundtrip_ready')).strip()}",
        f"- Route-enable lineage current: {'yes' if _to_bool(summary_row.get('route_enable_lineage_gate_passed')) else 'no'}",
        f"- Research family: {_object_text(summary_row.get('route_enable_cutover_runtime_scaleup_research_family_id')).strip()}",
        "- Submission authorization: no",
        f"- Failed checks: {_int_value(summary_row.get('failed_check_count'))}",
        f"- Blocked actions: {_int_value(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_object_text(summary_row.get('recommendation')).strip()}",
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
        return "No broker dispatch actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _object_text(item.get("priority")).strip(),
                    _object_text(item.get("queue_status")).strip(),
                    _object_text(item.get("component")).strip(),
                    _object_text(item.get("check")).strip(),
                    _object_text(item.get("actual")).strip(),
                    _object_text(item.get("expected")).strip(),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _object_text(item.get("reason")).strip(),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _object_text(action_queue.iloc[0].get(column)).strip()


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_check_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_check_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_check_record(record: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_check_value(value) for key, value in record.items()}


def _jsonable_check_value(value: object) -> object:
    value = _jsonable(value)
    if hasattr(value, "item"):
        try:
            return value.item()  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def _help_command(next_gate: str) -> str:
    gate = _object_text(next_gate).strip()
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _object_text(value).strip()
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _resume_route_readiness_state_fields(
    row: pd.Series,
    route_readiness: object,
    *,
    source_prefix: str,
    row_prefix: str,
) -> dict[str, Any]:
    readiness = route_readiness if isinstance(route_readiness, dict) else {}
    return {
        f"{source_prefix}_required": _to_bool(
            readiness.get("required", row.get(f"{row_prefix}_required", False))
        ),
        f"{source_prefix}_provided": _to_bool(
            readiness.get("provided", row.get(f"{row_prefix}_provided", False))
        ),
        f"{source_prefix}_ready": _to_bool(readiness.get("ready", row.get(f"{row_prefix}_ready", False))),
        f"{source_prefix}_strategy": _strategy_key(
            _first_text(readiness.get("strategy", ""), row.get(f"{row_prefix}_strategy", ""))
        ),
        f"{source_prefix}_market": _identity_key(
            _first_text(readiness.get("market", ""), row.get(f"{row_prefix}_market", ""))
        ),
        f"{source_prefix}_route_ready_pairs": int(
            _number_from(readiness, "route_ready_pairs", _number(row, f"{row_prefix}_route_ready_pairs", 0.0))
        ),
        f"{source_prefix}_gap_pairs": int(
            _number_from(readiness, "gap_pairs", _number(row, f"{row_prefix}_gap_pairs", 0.0))
        ),
        f"{source_prefix}_recommendation": _first_text(
            readiness.get("recommendation", ""),
            row.get(f"{row_prefix}_recommendation", ""),
        ),
        f"{source_prefix}_ops_launch_controls_ready": _to_bool(
            readiness.get("ops_launch_controls_ready", row.get(f"{row_prefix}_ops_launch_controls_ready", False))
        ),
        f"{source_prefix}_ops_launch_control_failures": _first_text(
            readiness.get("ops_launch_control_failures", ""),
            row.get(f"{row_prefix}_ops_launch_control_failures", ""),
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0),
            )
        ),
    }


def _route_lineage_output_fields(route: dict[str, Any]) -> dict[str, Any]:
    return {column: route[column] for column in ROUTE_ENABLE_LINEAGE_OUTPUT_COLUMNS}


def _route_lineage_config(summary: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(summary[column])
        for column in ROUTE_ENABLE_LINEAGE_OUTPUT_COLUMNS
    }


def _route_state(
    row: pd.Series,
    config: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    strategy_portfolio = config.get("strategy_portfolio", {}) or {}
    upload = config.get("upload", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    route_readiness = config.get("route_readiness", {}) or {}
    broker_route_readiness = config.get("cutover_broker_route_readiness", {}) or {}
    cutover_broker_resume_gate = (
        config.get("cutover_broker_resume_gate", {})
        or config.get("route_broker_resume_gate", {})
        or {}
    )
    if not isinstance(cutover_broker_resume_gate, dict):
        cutover_broker_resume_gate = {}
    resume_broker_route_readiness = cutover_broker_resume_gate.get("broker_route_readiness", {}) or {}
    resume_incident_broker_route_readiness = (
        cutover_broker_resume_gate.get("incident_broker_route_readiness", {}) or {}
    )
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_shadow_broker = config.get("cutover_broker_shadow_broker_readiness", {}) or {}
    broker_shadow_broker_vendor_readiness = broker_shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    broker_shadow_broker_route = broker_shadow_broker.get("route_readiness", {}) or {}
    broker_shadow_broker_dispatch = broker_shadow_broker.get("dispatch_roundtrip", {}) or {}
    broker_shadow_broker_route_dispatch = broker_shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    (
        broker_vendor_market_data_batch,
        broker_vendor_market_data_batch_prefix,
    ) = _broker_vendor_market_data_batch_source(config)
    lineage_comparison = _broker_vendor_market_data_batch_lineage_comparison_source(
        config
    )
    final_lineage_comparison = _broker_vendor_final_lineage_comparison_source(config)
    route_complete_final_lineage_comparison = (
        _broker_vendor_route_complete_final_lineage_comparison_source(config)
    )
    broker_vendor_market_data_batch_state = _vendor_market_data_batch_state(
        row,
        broker_vendor_market_data_batch,
        field_prefix=broker_vendor_market_data_batch_prefix,
    )
    (
        broker_vendor_data_readiness,
        broker_vendor_data_readiness_prefix,
    ) = _broker_vendor_data_readiness_source(config)
    vendor_market_data_batch = config.get("cutover_vendor_market_data_batch", {}) or {}
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route_proof = dispatch.get("route_proof", {}) or {}
    payload = _jsonable_row({"summary": row.to_dict(), "config": config})
    route_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "route_enabled": _to_bool(config.get("route_enabled", row.get("ready", False))),
        **route_enable_lineage_fields(lineage),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""))),
        "market": _identity_key(_first_text(row.get("market", ""), config.get("market", ""))),
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "broker_schema_status": _first_text(
            broker_readiness.get("adapter_schema_status", ""),
            row.get("broker_schema_status", ""),
        ),
        "broker_schema_reviewed": _to_bool(
            broker_readiness.get("schema_reviewed", row.get("broker_schema_reviewed", False))
        ),
        "broker_schema_review_mode": _first_text(
            broker_readiness.get("schema_review_mode", ""),
            row.get("broker_schema_review_mode", ""),
        ),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "strategy_portfolio_required": _to_bool(
            strategy_portfolio.get("required", row.get("strategy_portfolio_required", False))
        ),
        "strategy_portfolio_provided": _to_bool(
            strategy_portfolio.get("provided", row.get("strategy_portfolio_provided", False))
        ),
        "strategy_portfolio_ready": _to_bool(
            strategy_portfolio.get("ready", row.get("strategy_portfolio_ready", False))
        ),
        "strategy_portfolio_deployment_mode": _first_text(
            strategy_portfolio.get("deployment_mode", ""),
            row.get("strategy_portfolio_deployment_mode", ""),
        ),
        "strategy_portfolio_allocation_mode": _first_text(
            strategy_portfolio.get("allocation_mode", ""),
            row.get("strategy_portfolio_allocation_mode", ""),
        ),
        "strategy_portfolio_capital_currency": _first_text(
            strategy_portfolio.get("capital_currency", ""),
            row.get("strategy_portfolio_capital_currency", ""),
        ),
        "strategy_portfolio_selected_profile": _first_text(
            strategy_portfolio.get("selected_profile", ""),
            row.get("strategy_portfolio_selected_profile", ""),
        ),
        "strategy_portfolio_selected_strategy": _strategy_key(
            _first_text(
                strategy_portfolio.get("selected_strategy", ""),
                row.get("strategy_portfolio_selected_strategy", ""),
            )
        ),
        "strategy_portfolio_selected_market": _identity_key(
            _first_text(
                strategy_portfolio.get("selected_market", ""),
                row.get("strategy_portfolio_selected_market", ""),
            )
        ),
        "strategy_portfolio_selected_eligible": _to_bool(
            strategy_portfolio.get("selected_eligible", row.get("strategy_portfolio_selected_eligible", False))
        ),
        "strategy_portfolio_selected_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_weight",
                _number(row, "strategy_portfolio_selected_allocation_weight", 0.0),
            )
        ),
        "strategy_portfolio_selected_allocation_notional": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_notional",
                _number(row, "strategy_portfolio_selected_allocation_notional", 0.0),
            )
        ),
        "strategy_portfolio_notional_cap_applied": _to_bool(
            strategy_portfolio.get(
                "notional_cap_applied",
                row.get("strategy_portfolio_notional_cap_applied", False),
            )
        ),
        "strategy_portfolio_min_strategy_count": int(
            _number_from(
                strategy_portfolio,
                "min_strategy_count",
                _number(row, "strategy_portfolio_min_strategy_count", 0.0),
            )
        ),
        "strategy_portfolio_min_market_count": int(
            _number_from(
                strategy_portfolio,
                "min_market_count",
                _number(row, "strategy_portfolio_min_market_count", 0.0),
            )
        ),
        "strategy_portfolio_max_strategy_weight": float(
            _number_from(
                strategy_portfolio,
                "max_strategy_weight",
                _number(row, "strategy_portfolio_max_strategy_weight", 0.0),
            )
        ),
        "strategy_portfolio_max_market_weight": float(
            _number_from(
                strategy_portfolio,
                "max_market_weight",
                _number(row, "strategy_portfolio_max_market_weight", 0.0),
            )
        ),
        "strategy_portfolio_allocated_strategy_count": int(
            _number_from(
                strategy_portfolio,
                "allocated_strategy_count",
                _number(row, "strategy_portfolio_allocated_strategy_count", 0.0),
            )
        ),
        "strategy_portfolio_allocated_market_count": int(
            _number_from(
                strategy_portfolio,
                "allocated_market_count",
                _number(row, "strategy_portfolio_allocated_market_count", 0.0),
            )
        ),
        "strategy_portfolio_top_strategy_by_weight": _strategy_key(
            _first_text(
                strategy_portfolio.get("top_strategy_by_weight", ""),
                row.get("strategy_portfolio_top_strategy_by_weight", ""),
            )
        ),
        "strategy_portfolio_top_market_by_weight": _identity_key(
            _first_text(
                strategy_portfolio.get("top_market_by_weight", ""),
                row.get("strategy_portfolio_top_market_by_weight", ""),
            )
        ),
        "strategy_portfolio_max_strategy_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "max_strategy_allocation_weight",
                _number(row, "strategy_portfolio_max_strategy_allocation_weight", 0.0),
            )
        ),
        "strategy_portfolio_max_market_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "max_market_allocation_weight",
                _number(row, "strategy_portfolio_max_market_allocation_weight", 0.0),
            )
        ),
        "pre_portfolio_max_notional_per_session": float(
            _number_from(
                strategy_portfolio,
                "pre_portfolio_max_notional_per_session",
                _number(row, "pre_portfolio_max_notional_per_session", 0.0),
            )
        ),
        "upload_orders": int(_number_from(upload, "orders", _number(row, "upload_orders", 0.0))),
        "upload_output_file": _first_text(upload.get("output_file", "")),
        "route_enable_hash": route_hash,
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(route_readiness.get("ready", row.get("route_readiness_ready", False))),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("route_readiness_recommendation", ""),
        ),
        "route_readiness_ops_launch_controls_present": _to_bool(
            route_readiness.get(
                "ops_launch_controls_present",
                row.get("route_readiness_ops_launch_controls_present", False),
            )
        ),
        "route_readiness_ops_launch_controls_blocked_pairs": int(
            _number_from(
                route_readiness,
                "ops_launch_controls_blocked_pairs",
                _number(row, "route_readiness_ops_launch_controls_blocked_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_breach_pairs",
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0.0),
            )
        ),
        "broker_route_readiness_required": _to_bool(
            broker_route_readiness.get("required", row.get("cutover_broker_route_readiness_required", False))
        ),
        "broker_route_readiness_provided": _to_bool(
            broker_route_readiness.get("provided", row.get("cutover_broker_route_readiness_provided", False))
        ),
        "broker_route_readiness_ready": _to_bool(
            broker_route_readiness.get("ready", row.get("cutover_broker_route_readiness_ready", False))
        ),
        "broker_route_readiness_strategy": _strategy_key(
            _first_text(
                broker_route_readiness.get("strategy", ""),
                row.get("cutover_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_route_readiness_market": _identity_key(
            _first_text(
                broker_route_readiness.get("market", ""),
                row.get("cutover_broker_route_readiness_market", ""),
            )
        ),
        "broker_route_readiness_route_ready_pairs": int(
            _number_from(
                broker_route_readiness,
                "route_ready_pairs",
                _number(row, "cutover_broker_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "broker_route_readiness_gap_pairs": int(
            _number_from(
                broker_route_readiness,
                "gap_pairs",
                _number(row, "cutover_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_route_readiness_recommendation": _first_text(
            broker_route_readiness.get("recommendation", ""),
            row.get("cutover_broker_route_readiness_recommendation", ""),
        ),
        "broker_route_readiness_ops_launch_controls_ready": _to_bool(
            broker_route_readiness.get(
                "ops_launch_controls_ready",
                row.get("cutover_broker_route_readiness_ops_launch_controls_ready", False),
            )
        ),
        "broker_route_readiness_ops_launch_control_failures": _first_text(
            broker_route_readiness.get("ops_launch_control_failures", ""),
            row.get("cutover_broker_route_readiness_ops_launch_control_failures", ""),
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(
                    row,
                    "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                ),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                _number(
                    row,
                    "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                ),
            )
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_broker_route_readiness,
            source_prefix="broker_resume_broker_route_readiness",
            row_prefix="cutover_broker_resume_broker_route_readiness",
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_incident_broker_route_readiness,
            source_prefix="broker_resume_incident_broker_route_readiness",
            row_prefix="cutover_broker_resume_incident_broker_route_readiness",
        ),
        "shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("shadow_broker_adapter", ""))
        ),
        "shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "shadow_broker_adapter_count", 0.0),
            )
        ),
        "shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("shadow_broker_route_readiness_market", ""),
            )
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_provided": _to_bool(
            broker_shadow_broker.get("provided", row.get("cutover_broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                broker_shadow_broker,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                broker_shadow_broker,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                broker_shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                broker_shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                broker_shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                broker_shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(
                broker_shadow_broker.get("adapter", ""),
                row.get("cutover_broker_shadow_broker_adapter", ""),
            )
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                broker_shadow_broker,
                "adapter_count",
                _number(row, "cutover_broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                broker_shadow_broker_route,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                broker_shadow_broker_route,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_route.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                broker_shadow_broker_route.get("market", ""),
                row.get("cutover_broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                broker_shadow_broker_route,
                "max_gap_pairs",
                _number(row, "cutover_broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_dispatch.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                broker_shadow_broker_dispatch.get("market", ""),
                row.get("cutover_broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "scenario_count",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                broker_shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "sessions",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                broker_shadow_broker_route_dispatch.get("strategy", ""),
                row.get("cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                broker_shadow_broker_route_dispatch.get("market", ""),
                row.get("cutover_broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                broker_shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": broker_vendor_market_data_batch_state,
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            lineage_comparison.get(
                "required",
                row.get(
                    "route_broker_vendor_market_data_batch_lineage_match_required",
                    row.get(
                        "cutover_broker_vendor_market_data_batch_lineage_match_required",
                        False,
                    ),
                ),
            )
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            lineage_comparison.get(
                "matches",
                row.get(
                    "route_broker_vendor_market_data_batch_lineage_matches",
                    row.get(
                        "cutover_broker_vendor_market_data_batch_lineage_matches",
                        False,
                    ),
                ),
            )
        ),
        "vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("current_application_lineage_sha256", ""),
                row.get("route_vendor_market_data_batch_application_lineage_sha256", ""),
                row.get("cutover_vendor_market_data_batch_application_lineage_sha256", ""),
            )
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("broker_application_lineage_sha256", ""),
                row.get(
                    "route_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
                row.get(
                    "cutover_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
            )
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    lineage_comparison.get(
                        "scaleup_carried_application_lineage_sha256",
                        "",
                    ),
                    row.get(
                        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    lineage_comparison.get(
                        "cutover_carried_application_lineage_sha256",
                        "",
                    ),
                    row.get(
                        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    lineage_comparison.get(
                        "route_carried_application_lineage_sha256",
                        "",
                    ),
                    row.get(
                        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        **_broker_vendor_final_lineage_state_fields(
            final_lineage_comparison,
            row,
        ),
        **_broker_vendor_route_complete_final_lineage_state_fields(
            route_complete_final_lineage_comparison,
            row,
        ),
        "broker_vendor_data_readiness": _broker_vendor_data_readiness_state(
            row,
            broker_vendor_data_readiness,
            field_prefix=broker_vendor_data_readiness_prefix,
        ),
        "vendor_market_data_batch": _vendor_market_data_batch_state(row, vendor_market_data_batch),
        "dispatch_roundtrip_required": _to_bool(
            route_proof.get("required", row.get("route_dispatch_roundtrip_required", False))
        ),
        "dispatch_roundtrip_provided": _to_bool(
            route_proof.get("provided", row.get("route_dispatch_roundtrip_provided", False))
        ),
        "dispatch_roundtrip_ready": _to_bool(
            route_proof.get("ready", row.get("route_dispatch_roundtrip_ready", False))
        ),
        "dispatch_roundtrip_target_mode": _identity_key(
            _first_text(route_proof.get("target_mode", ""), row.get("route_dispatch_roundtrip_target_mode", ""))
        ),
        "dispatch_roundtrip_strategy": _strategy_key(
            _first_text(route_proof.get("strategy", ""), row.get("route_dispatch_roundtrip_strategy", ""))
        ),
        "dispatch_roundtrip_market": _identity_key(
            _first_text(route_proof.get("market", ""), row.get("route_dispatch_roundtrip_market", ""))
        ),
        "dispatch_roundtrip_scenario_key": _first_text(
            route_proof.get("scenario_key", ""),
            row.get("route_dispatch_roundtrip_scenario_key", ""),
        ),
        "dispatch_roundtrip_batch_id": _first_text(
            route_proof.get("dispatch_batch_id", ""),
            row.get("route_dispatch_roundtrip_batch_id", ""),
        ),
        "dispatch_roundtrip_requests": int(
            _number_from(route_proof, "requests", _number(row, "route_dispatch_roundtrip_requests", 0.0))
        ),
        "dispatch_roundtrip_acked_orders": int(
            _number_from(route_proof, "acked_orders", _number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        ),
        "dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                route_proof,
                "missing_request_acks",
                _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_rejected_orders": int(
            _number_from(route_proof, "rejected_orders", _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0))
        ),
        "dispatch_roundtrip_unmatched_acks": int(
            _number_from(route_proof, "unmatched_acks", _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0))
        ),
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number_from(
                route_enable,
                "failed_checks",
                _number(
                    row,
                    "route_enable_dispatch_roundtrip_failed_checks",
                    _number(row, "dispatch_roundtrip_failed_checks", 0.0),
                ),
            )
        ),
    }


def _broker_vendor_market_data_batch_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _broker_vendor_market_data_batch_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
    ):
        comparison = config.get(key)
        if isinstance(comparison, dict) and comparison:
            return comparison
    return {}


def _broker_vendor_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(ROUTE_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_route_complete_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(ROUTE_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = ROUTE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = ROUTE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(f"{prefix}_application_lineage_sha256", ""),
            )
        ),
    }
    for field in ROUTE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_route_complete_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = ROUTE_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = ROUTE_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{ROUTE_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in ROUTE_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
        (config.get("route_broker_vendor_data_readiness"), "route_broker_vendor_data_readiness"),
        (config.get("cutover_broker_vendor_data_readiness"), "cutover_broker_vendor_data_readiness"),
        (config.get("scaleup_broker_vendor_data_readiness"), "scaleup_broker_vendor_data_readiness"),
        (config.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness"),
    ]
    broker_readiness = config.get("broker_readiness", {}) or {}
    if isinstance(broker_readiness, dict):
        candidates.append(
            (broker_readiness.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
        broker_dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
        if isinstance(broker_dispatch, dict):
            candidates.append(
                (broker_dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
            )
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(
            (dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
    for candidate, source in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_source_active(candidate):
            return candidate, source
    return {}, "cutover_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    route_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = _broker_vendor_market_data_batch_source(route_config)
    sidecar_broker = broker_readiness_config.get(
        "broker_readiness",
        broker_readiness_config,
    ) or {}
    if not isinstance(sidecar_broker, dict):
        return route_config
    dispatch = sidecar_broker.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        sidecar_vendor, _source = select_vendor_market_data_batch_source(
            dispatch,
            (
                "broker_dispatch_roundtrip_vendor_market_data_batch",
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "vendor_market_data_batch",
                "roundtrip_vendor_market_data_batch",
            ),
            default_source="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        sidecar_vendor = {}
    should_hydrate_vendor = (
        not vendor_market_data_batch_source_active(vendor)
        and vendor_market_data_batch_source_active(sidecar_vendor)
    )
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(route_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(
        sidecar_broker
    )
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    existing_lineage = _broker_vendor_market_data_batch_lineage_comparison_source(
        route_config
    )
    sidecar_lineage = (
        dispatch.get("vendor_market_data_batch_lineage_comparison", {}) or {}
        if isinstance(dispatch, dict)
        else {}
    )
    should_hydrate_lineage = (
        not existing_lineage
        and isinstance(sidecar_lineage, dict)
        and bool(sidecar_lineage)
    )
    if (
        not should_hydrate_vendor
        and not should_hydrate_readiness
        and not should_hydrate_lineage
    ):
        return route_config

    out = dict(route_config)
    if should_hydrate_vendor:
        out["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out["cutover_broker_vendor_data_readiness"] = dict(sidecar_readiness)
    if should_hydrate_lineage:
        out[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
        ] = dict(sidecar_lineage)
    return out


def _manifest_input_path(manifest_path: Path | None, input_name: str) -> Path | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path if path.exists() else None


def _batch_id(route: dict[str, Any], upload_orders: pd.DataFrame, upload_file_hash: str) -> str:
    seed = {
        "route_enable_hash": route["route_enable_hash"],
        "upload_file_hash": upload_file_hash,
        "orders": len(upload_orders),
    }
    return f"BDP-{hashlib.sha256(json.dumps(seed, sort_keys=True).encode('utf-8')).hexdigest()[:16]}"


def _strategy_portfolio_active(route: dict[str, Any]) -> bool:
    return bool(route["strategy_portfolio_required"] or route["strategy_portfolio_provided"])


def _dispatch_total_notional(dispatch_orders: pd.DataFrame) -> float:
    if dispatch_orders.empty or "source_order_notional" not in dispatch_orders.columns:
        return 0.0
    return float(pd.to_numeric(dispatch_orders["source_order_notional"], errors="coerce").fillna(0.0).sum())


def _source_order_notional(row: pd.Series) -> float:
    for column in ("notional", "order_notional", "total_notional", "value", "amount"):
        if column in row.index:
            value = pd.to_numeric(row[column], errors="coerce")
            if not pd.isna(value):
                return abs(float(value))
    qty = _first_numeric(row, "quantity", "qty", "order_qty", "lots")
    price = _first_numeric(row, "price", "limit_price", "order_price")
    return abs(qty * price)


def _first_numeric(row: pd.Series, *columns: str) -> float:
    for column in columns:
        if column in row.index:
            value = pd.to_numeric(row[column], errors="coerce")
            if not pd.isna(value):
                return float(value)
    return 0.0


def _vendor_market_data_batch_state(
    row: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str = "cutover_vendor_market_data_batch",
) -> dict[str, Any]:
    comparison = vendor.get("comparison", {}) or {}
    datasets = vendor.get("datasets")
    if datasets is None:
        datasets = _json_list(row.get(f"{field_prefix}_datasets_json", "[]"))
    datasets = datasets or []
    return {
        "provided": _to_bool(vendor.get("provided", row.get(f"{field_prefix}_provided", False))),
        "ready": _to_bool(vendor.get("ready", row.get(f"{field_prefix}_ready", False))),
        "adapter": _first_text(vendor.get("adapter", ""), row.get(f"{field_prefix}_adapter", "")),
        "kind": _first_text(vendor.get("kind", ""), row.get(f"{field_prefix}_kind", "")),
        "manifest_run_type": _identity_key(
            _first_text(vendor.get("manifest_run_type", ""), row.get(f"{field_prefix}_manifest_run_type", ""))
        ),
        "market": _identity_key(
            _first_text(vendor.get("market", ""), row.get(f"{field_prefix}_market", ""))
        ),
        "dataset_count": int(
            _number_from(
                vendor,
                "dataset_count",
                _number(row, f"{field_prefix}_dataset_count", 0.0),
            )
        ),
        "ready_datasets": int(
            _number_from(
                vendor,
                "ready_datasets",
                _number(row, f"{field_prefix}_ready_datasets", 0.0),
            )
        ),
        "failed_datasets": int(
            _number_from(
                vendor,
                "failed_datasets",
                _number(row, f"{field_prefix}_failed_datasets", 0.0),
            )
        ),
        "ready_rate": _number_from(
            vendor,
            "ready_rate",
            _number(row, f"{field_prefix}_ready_rate", 0.0),
        ),
        "unique_source_files": int(
            _number_from(
                vendor,
                "unique_source_files",
                _number(row, f"{field_prefix}_unique_source_files", 0.0),
            )
        ),
        "unique_header_fingerprints": int(
            _number_from(
                vendor,
                "unique_header_fingerprints",
                _number(row, f"{field_prefix}_unique_header_fingerprints", 0.0),
            )
        ),
        "source_file_fingerprint_coverage": _number_from(
            vendor,
            "source_file_fingerprint_coverage",
            _number(row, f"{field_prefix}_source_file_fingerprint_coverage", 0.0),
        ),
        "min_mapping_coverage": _number_from(
            vendor,
            "min_mapping_coverage",
            _number(row, f"{field_prefix}_min_mapping_coverage", 0.0),
        ),
        "unique_mapping_drafts": int(
            _number_from(
                vendor,
                "unique_mapping_drafts",
                _number(row, f"{field_prefix}_unique_mapping_drafts", 0.0),
            )
        ),
        "mapping_sources": _first_text(
            vendor.get("mapping_sources", ""),
            row.get(f"{field_prefix}_mapping_sources", ""),
        ),
        "mapping_source_mode": _identity_key(
            _first_text(
                vendor.get("mapping_source_mode", ""),
                row.get(f"{field_prefix}_mapping_source_mode", ""),
            )
        ),
        "mapping_application_count": int(
            _number_from(
                vendor,
                "mapping_application_count",
                _number(row, f"{field_prefix}_mapping_application_count", 0.0),
            )
        ),
        "unique_mapping_applications": int(
            _number_from(
                vendor,
                "unique_mapping_applications",
                _number(row, f"{field_prefix}_unique_mapping_applications", 0.0),
            )
        ),
        "target_application_coverage": _number_from(
            vendor,
            "target_application_coverage",
            _number(row, f"{field_prefix}_target_application_coverage", 0.0),
        ),
        "application_lineage_consistency_required": _to_bool(
            vendor.get(
                "application_lineage_consistency_required",
                row.get(
                    f"{field_prefix}_application_lineage_consistency_required",
                    False,
                ),
            )
        ),
        "application_lineage_consistent": _to_bool(
            vendor.get(
                "application_lineage_consistent",
                row.get(f"{field_prefix}_application_lineage_consistent", False),
            )
        ),
        "application_lineage_sha256": _sha256_text(
            _first_text(
                vendor.get("application_lineage_sha256", ""),
                row.get(f"{field_prefix}_application_lineage_sha256", ""),
            )
        ),
        "comparison_accepted": _to_bool(
            comparison.get("accepted", row.get(f"{field_prefix}_comparison_accepted", False))
        ),
        "comparison_failed_checks": int(
            _number_from(
                comparison,
                "failed_checks",
                _number(row, f"{field_prefix}_comparison_failed_checks", 0.0),
            )
        ),
        "datasets": [
            {
                "dataset": _first_text(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": _first_text(item.get("source_file_sha256", "")),
                "source_header_sha256": _first_text(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": _first_text(item.get("mapping_draft_sha256", "")),
                "mapping_source": _first_text(item.get("mapping_source", "")),
                "mapping_application_path": _first_text(item.get("mapping_application_path", "")),
                "mapping_application_id": _first_text(item.get("mapping_application_id", "")),
                "mapping_application_sha256": _first_text(
                    item.get("mapping_application_sha256", "")
                ),
                "mapping_scope_review_id": _first_text(item.get("mapping_scope_review_id", "")),
                "mapping_scope_review_sha256": _first_text(
                    item.get("mapping_scope_review_sha256", "")
                ),
                "target_intake_receipt_id": _first_text(item.get("target_intake_receipt_id", "")),
                "applied_mapping_sha256": _first_text(item.get("applied_mapping_sha256", "")),
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def _broker_vendor_data_readiness_state(
    row: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str = "cutover_broker_vendor_data_readiness",
) -> dict[str, Any]:
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    return {
        "provided": _to_bool(readiness.get("provided", row.get(f"{field_prefix}_provided", active_config))),
        "ready": _to_bool(readiness.get("ready", row.get(f"{field_prefix}_ready", False))),
        "failed_checks": _broker_vendor_data_readiness_failed_checks(
            readiness,
            fallback=_number(row, f"{field_prefix}_failed_checks", 0.0),
        ),
    }


def _broker_vendor_data_readiness_failed_checks(
    readiness: dict[str, Any],
    *,
    fallback: float = 0.0,
) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_from(readiness, "failed_checks", fallback))
    return int(_number_from(readiness, "failed_check_count", fallback))


def _source_order_id(row: pd.Series, idx: int) -> str:
    for column in ("client_order_id", "client_tag", "broker_order_id", "tag", "strategy_tag"):
        value = _object_text(row.get(column, ""))
        if value:
            return value
    return f"row-{idx + 1:06d}"


def _upload_orders_path(upload_dir: Path, route_config: dict[str, Any], override: str | Path | None) -> Path:
    if override is not None:
        candidate = Path(override)
    else:
        upload_file = str((route_config.get("upload", {}) or {}).get("output_file", "")).strip()
        filename = upload_file or "broker_upload_orders.csv"
        if upload_dir.is_dir():
            direct = upload_dir / filename
            candidate = next(
                (
                    nested
                    for folder in ("05_upload_pack", "04_upload_pack")
                    if (nested := upload_dir / folder / filename).exists()
                ),
                direct,
            )
        else:
            candidate = upload_dir
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"broker upload orders not found: {candidate}")
    return candidate


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch input is empty: {name}")
    return frame


def _sidecar_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        file_path = candidate / filename
    else:
        file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _reject_input_output_collision(
    output_dir: Path,
    inputs: dict[str, Path],
) -> None:
    for label, value in inputs.items():
        path = Path(value).resolve()
        root = path if path.is_dir() else path.parent
        if output_dir == root or root in output_dir.parents or output_dir in root.parents:
            raise ValueError(f"broker-dispatch output_dir must not overwrite the {label} source directory")


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: BrokerDispatchThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: BrokerDispatchThresholds, route: dict[str, Any] | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (route is not None and route["route_readiness_required"])
    )


def _validate_thresholds(thresholds: BrokerDispatchThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")
    if thresholds.max_orders is not None and thresholds.max_orders <= 0:
        raise ValueError("max_orders must be positive")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_from(mapping: dict[str, Any], key: str, fallback: float) -> float:
    value = mapping.get(key, fallback)
    if value is None or _is_missing(value):
        return float(fallback)
    return float(value)


def _nullable_number(value: object) -> float | None:
    if value is None or _is_missing(value):
        return None
    return float(value)


def _first_text(*values: object) -> str:
    for value in values:
        text = _object_text(value)
        if text:
            return text
    return ""


def _strategy_key(value: object) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    return _object_text(value).lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _object_text(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed", "enabled"}
    return bool(value)


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value: object) -> object:
    if _is_missing(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
