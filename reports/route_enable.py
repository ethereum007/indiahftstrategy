from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class RouteEnableThresholds:
    target_mode: str = "live_dryrun"
    require_cutover_ready: bool = True
    require_upload_ready: bool = True
    require_order_export_ready: bool = False
    require_adapter_match: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1


@dataclass(frozen=True)
class RouteEnableReport:
    packet: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_route_enable_packet(
    *,
    cutover_summary: pd.DataFrame,
    cutover_config: dict[str, Any] | None = None,
    upload_summary: pd.DataFrame,
    order_export_summary: pd.DataFrame | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    thresholds = thresholds or RouteEnableThresholds()
    _validate_thresholds(thresholds)
    cutover_summary = _require_nonempty(cutover_summary, "cutover_summary")
    upload_summary = _require_nonempty(upload_summary, "upload_summary")
    order_export_summary = _optional_frame(order_export_summary)
    cutover_config = cutover_config or {}

    state = {
        "cutover": _cutover_state(cutover_summary.iloc[0], cutover_config),
        "upload": _upload_state(upload_summary.iloc[0]),
        "order_export": _order_export_state(order_export_summary),
    }
    checks = _checks(state, thresholds)
    packet = _packet(state, thresholds, checks)
    summary = _summary(packet.iloc[0], checks)
    config = _config(packet.iloc[0], thresholds, checks)
    return RouteEnableReport(packet=packet, checks=checks, summary=summary, config=config)


def write_route_enable_packet(
    *,
    cutover_dir: str | Path,
    upload_pack_dir: str | Path,
    output_dir: str | Path,
    order_export_dir: str | Path | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    cutover = Path(cutover_dir)
    upload = Path(upload_pack_dir)
    cutover_config_path = cutover / "cutover_config.json" if cutover.is_dir() else Path(cutover_dir)
    upload_summary_path = _summary_path(
        upload,
        "broker_upload_summary.csv",
        fallback_dirs=("05_upload_pack", "04_upload_pack"),
    )
    order_export_summary_path = (
        _summary_path(
            order_export_dir,
            "broker_order_summary.csv",
            fallback_dirs=("04_export", "03_export"),
        )
        if order_export_dir is not None
        else None
    )
    if not cutover_config_path.exists():
        raise FileNotFoundError(f"cutover config not found: {cutover_config_path}")
    cutover_summary_path = (
        cutover / "cutover_summary.csv" if cutover.is_dir() else cutover_config_path.with_name("cutover_summary.csv")
    )
    report = evaluate_route_enable_packet(
        cutover_summary=_read_required(cutover_summary_path, "cutover_summary"),
        cutover_config=json.loads(cutover_config_path.read_text(encoding="utf-8")),
        upload_summary=_read_required(upload_summary_path, "broker_upload_summary"),
        order_export_summary=(
            _read_optional(order_export_summary_path) if order_export_summary_path is not None else None
        ),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.packet.to_csv(out / "route_enable_packet.csv", index=False)
    report.checks.to_csv(out / "route_enable_checks.csv", index=False)
    report.summary.to_csv(out / "route_enable_summary.csv", index=False)
    (out / "route_enable_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "cutover_summary": cutover_summary_path,
        "cutover_config": cutover_config_path,
        "upload_pack": upload_summary_path,
    }
    if order_export_summary_path is not None:
        inputs["order_export"] = (
            order_export_summary_path if order_export_summary_path.exists() else Path(order_export_dir)
        )
    write_experiment_manifest(
        out,
        run_type="route_enable_packet",
        parameters={"thresholds": asdict(thresholds or RouteEnableThresholds())},
        inputs=inputs,
    )
    return RouteEnableReport(report.packet, report.checks, report.summary, report.config, out)


def _checks(state: dict[str, dict[str, Any]], thresholds: RouteEnableThresholds) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    target_mode = _identity_key(thresholds.target_mode)
    upload_orders = int(upload["orders"])
    max_orders = int(cutover["max_orders_per_session"])
    max_notional = float(cutover["max_notional_per_session"])
    export_notional = float(order_export["total_notional"])
    route_readiness_required = _route_readiness_required(thresholds, cutover)
    route_readiness_active = bool(route_readiness_required or cutover["route_readiness_provided"])
    checks = [
        _check(
            "cutover_ready",
            cutover["ready"],
            "is",
            True,
            bool(cutover["ready"]) or not thresholds.require_cutover_ready,
            "cutover gate is not ready",
        ),
        _check(
            "target_mode_matches",
            cutover["target_mode"],
            "==",
            target_mode,
            bool(cutover["target_mode"] and cutover["target_mode"] == target_mode),
            "cutover target mode does not match route-enable target mode",
        ),
        _check(
            "cutover_dispatch_roundtrip_provided",
            cutover["dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_provided"]) or not _dispatch_roundtrip_required(thresholds),
            "route enable requires cutover with dry-run dispatch round-trip proof",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_provided",
            cutover["route_dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_provided"]) or not _route_dispatch_roundtrip_required(
                thresholds,
                cutover,
            ),
            "route enable requires cutover with dispatch route proof",
        ),
    ]
    if route_readiness_required:
        checks.append(
            _check(
                "cutover_route_readiness_provided",
                cutover["route_readiness_provided"],
                "is",
                True,
                bool(cutover["route_readiness_provided"]),
                "route enable requires cutover with route-readiness proof",
            )
        )
    if route_readiness_active:
        checks.extend(_route_readiness_checks(cutover))
    checks.extend(
        [
            _check(
                "upload_ready",
                upload["ready"],
                "is",
                True,
                bool(upload["ready"]) or not thresholds.require_upload_ready,
                "broker upload pack is not ready",
            ),
            _check(
                "upload_orders_min",
                upload_orders,
                ">=",
                thresholds.min_orders,
                upload_orders >= thresholds.min_orders,
                "broker upload pack does not contain enough orders",
            ),
            _check(
                "upload_orders_within_cutover_limit",
                upload_orders,
                "<=",
                max_orders,
                upload_orders <= max_orders,
                "broker upload order count exceeds cutover limit",
            ),
            _check(
                "upload_adapter_matches",
                upload["adapter"],
                "==",
                cutover["adapter"],
                (not thresholds.require_adapter_match) or upload["adapter"] == cutover["adapter"],
                "broker upload adapter does not match cutover adapter",
            ),
        ]
    )
    if _dispatch_roundtrip_required(thresholds) or cutover["dispatch_roundtrip_provided"]:
        checks.extend(_dispatch_roundtrip_checks(cutover, target_mode))
    if _route_dispatch_roundtrip_required(thresholds, cutover):
        checks.extend(_route_dispatch_roundtrip_checks(cutover, target_mode))
    if thresholds.require_order_export_ready:
        checks.append(
            _check(
                "order_export_provided",
                order_export["provided"],
                "is",
                True,
                bool(order_export["provided"]),
                "order export summary is required but missing",
            )
        )
    if order_export["provided"]:
        checks.extend(
            [
                _check(
                    "order_export_ready",
                    order_export["ready"],
                    "is",
                    True,
                    bool(order_export["ready"]) or not thresholds.require_order_export_ready,
                    "order export is not ready",
                ),
                _check(
                    "order_export_adapter_matches",
                    order_export["adapter"],
                    "==",
                    cutover["adapter"],
                    (not thresholds.require_adapter_match) or order_export["adapter"] == cutover["adapter"],
                    "order export adapter does not match cutover adapter",
                ),
                _check(
                    "order_export_orders_match_upload",
                    order_export["orders"],
                    "==",
                    upload_orders,
                    int(order_export["orders"]) == upload_orders,
                    "order export and upload pack order counts differ",
                ),
                _check(
                    "order_export_notional_within_cutover_limit",
                    export_notional,
                    "<=",
                    max_notional,
                    export_notional <= max_notional,
                    "order export notional exceeds cutover limit",
                ),
            ]
        )
    return pd.DataFrame(checks)


def _route_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_route_readiness_ready",
            cutover["route_readiness_ready"],
            "is",
            True,
            bool(cutover["route_readiness_ready"]),
            "cutover route-readiness proof is not ready",
        ),
        _check(
            "cutover_route_readiness_strategy_matches",
            cutover["route_readiness_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_readiness_strategy"]
                and cutover["strategy"]
                and cutover["route_readiness_strategy"] == cutover["strategy"]
            ),
            "cutover route-readiness strategy does not match route strategy",
        ),
        _check(
            "cutover_route_readiness_market_matches",
            cutover["route_readiness_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_readiness_market"]
                and cutover["market"]
                and cutover["route_readiness_market"] == cutover["market"]
            ),
            "cutover route-readiness market does not match route market",
        ),
    ]


def _dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_dispatch_roundtrip_ready",
            cutover["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_ready"]),
            "cutover dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            "cutover_dispatch_roundtrip_target_mode_matches",
            cutover["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(cutover["dispatch_roundtrip_target_mode"] and cutover["dispatch_roundtrip_target_mode"] == target_mode),
            "cutover dispatch round-trip target mode does not match route target",
        ),
        _check(
            "cutover_dispatch_roundtrip_strategy_matches",
            cutover["dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch round-trip strategy does not match route strategy",
        ),
        _check(
            "cutover_dispatch_roundtrip_market_matches",
            cutover["dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch round-trip market does not match route market",
        ),
        _check(
            "cutover_dispatch_roundtrip_scenario_matches",
            cutover["dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch round-trip scenario does not match route scenario",
        ),
        _check(
            "cutover_dispatch_roundtrip_missing_request_acks",
            cutover["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_rejected_orders",
            cutover["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch round-trip has rejected orders",
        ),
        _check(
            "cutover_dispatch_roundtrip_unmatched_acks",
            cutover["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_failed_checks",
            cutover["dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover dispatch round-trip has failed component checks",
        ),
        _check(
            "cutover_route_enable_dispatch_roundtrip_failed_checks",
            cutover["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover carries failed route-enable dispatch round-trip checks",
        ),
    ]


def _route_dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_route_dispatch_roundtrip_ready",
            cutover["route_dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_ready"]),
            "cutover dispatch route proof is not ready",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_target_mode_matches",
            cutover["route_dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(
                cutover["route_dispatch_roundtrip_target_mode"]
                and cutover["route_dispatch_roundtrip_target_mode"] == target_mode
            ),
            "cutover dispatch route proof target mode does not match route target",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_strategy_matches",
            cutover["route_dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["route_dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch route proof strategy does not match route strategy",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_market_matches",
            cutover["route_dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["route_dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch route proof market does not match route market",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_scenario_matches",
            cutover["route_dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["route_dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["route_dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch route proof scenario does not match route scenario",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_batch_id_provided",
            cutover["route_dispatch_roundtrip_batch_id"],
            "is not",
            "",
            bool(cutover["route_dispatch_roundtrip_batch_id"]),
            "cutover dispatch route proof batch id is missing",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_request_count_matches",
            f"{cutover['route_dispatch_roundtrip_requests']}/{cutover['route_dispatch_roundtrip_acked_orders']}",
            "==",
            f"{cutover['dispatch_roundtrip_requests']}/{cutover['dispatch_roundtrip_acked_orders']}",
            (
                int(cutover["route_dispatch_roundtrip_requests"]) == int(cutover["dispatch_roundtrip_requests"])
                and int(cutover["route_dispatch_roundtrip_acked_orders"])
                == int(cutover["dispatch_roundtrip_acked_orders"])
            ),
            "cutover dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_missing_request_acks",
            cutover["route_dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch route proof has missing request acknowledgements",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_rejected_orders",
            cutover["route_dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch route proof has rejected orders",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_unmatched_acks",
            cutover["route_dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _packet(
    state: dict[str, dict[str, Any]],
    thresholds: RouteEnableThresholds,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    ready = bool(checks["passed"].astype(bool).all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "route_enabled": ready,
                "route_state": "enabled" if ready else "disabled",
                "target_mode": cutover["target_mode"],
                "strategy": cutover["strategy"],
                "market": cutover["market"],
                "scenario_key": cutover["scenario_key"],
                "adapter": cutover["adapter"],
                "max_orders_per_session": int(cutover["max_orders_per_session"]),
                "max_notional_per_session": float(cutover["max_notional_per_session"]),
                "stop_loss": cutover["stop_loss"],
                "upload_ready": upload["ready"],
                "upload_orders": int(upload["orders"]),
                "upload_output_file": upload["output_file"],
                "upload_recommendation": upload["recommendation"],
                "adapter_schema_status": upload["schema_status"],
                "broker_schema_status": cutover["broker_schema_status"],
                "broker_schema_reviewed": cutover["broker_schema_reviewed"],
                "broker_schema_review_mode": cutover["broker_schema_review_mode"],
                "order_export_provided": order_export["provided"],
                "order_export_ready": order_export["ready"],
                "order_export_orders": int(order_export["orders"]),
                "order_export_total_notional": float(order_export["total_notional"]),
                "order_export_max_order_notional": float(order_export["max_order_notional"]),
                "proof_refresh_ready": cutover["proof_refresh_ready"],
                "proof_refresh_strategy": cutover["proof_refresh_strategy"],
                "proof_refresh_market": cutover["proof_refresh_market"],
                "route_readiness_required": _route_readiness_required(thresholds, cutover),
                "route_readiness_provided": cutover["route_readiness_provided"],
                "route_readiness_ready": cutover["route_readiness_ready"],
                "route_readiness_strategy": cutover["route_readiness_strategy"],
                "route_readiness_market": cutover["route_readiness_market"],
                "route_readiness_route_ready_pairs": cutover["route_readiness_route_ready_pairs"],
                "route_readiness_gap_pairs": cutover["route_readiness_gap_pairs"],
                "route_readiness_recommendation": cutover["route_readiness_recommendation"],
                "broker_resume_gate_ready": cutover["broker_resume_gate_ready"],
                "broker_resume_proof_refresh_ready": cutover["broker_resume_proof_refresh_ready"],
                "dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "dispatch_roundtrip_provided": cutover["dispatch_roundtrip_provided"],
                "dispatch_roundtrip_ready": cutover["dispatch_roundtrip_ready"],
                "dispatch_roundtrip_target_mode": cutover["dispatch_roundtrip_target_mode"],
                "dispatch_roundtrip_strategy": cutover["dispatch_roundtrip_strategy"],
                "dispatch_roundtrip_market": cutover["dispatch_roundtrip_market"],
                "dispatch_roundtrip_scenario_key": cutover["dispatch_roundtrip_scenario_key"],
                "dispatch_roundtrip_batch_id": cutover["dispatch_roundtrip_batch_id"],
                "dispatch_roundtrip_requests": cutover["dispatch_roundtrip_requests"],
                "dispatch_roundtrip_acked_orders": cutover["dispatch_roundtrip_acked_orders"],
                "dispatch_roundtrip_missing_request_acks": cutover["dispatch_roundtrip_missing_request_acks"],
                "dispatch_roundtrip_rejected_orders": cutover["dispatch_roundtrip_rejected_orders"],
                "dispatch_roundtrip_unmatched_acks": cutover["dispatch_roundtrip_unmatched_acks"],
                "dispatch_roundtrip_failed_checks": cutover["dispatch_roundtrip_failed_checks"],
                "route_enable_dispatch_roundtrip_failed_checks": cutover[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "route_dispatch_roundtrip_required": _route_dispatch_roundtrip_required(thresholds, cutover),
                "route_dispatch_roundtrip_provided": cutover["route_dispatch_roundtrip_provided"],
                "route_dispatch_roundtrip_ready": cutover["route_dispatch_roundtrip_ready"],
                "route_dispatch_roundtrip_target_mode": cutover["route_dispatch_roundtrip_target_mode"],
                "route_dispatch_roundtrip_strategy": cutover["route_dispatch_roundtrip_strategy"],
                "route_dispatch_roundtrip_market": cutover["route_dispatch_roundtrip_market"],
                "route_dispatch_roundtrip_scenario_key": cutover["route_dispatch_roundtrip_scenario_key"],
                "route_dispatch_roundtrip_batch_id": cutover["route_dispatch_roundtrip_batch_id"],
                "route_dispatch_roundtrip_requests": cutover["route_dispatch_roundtrip_requests"],
                "route_dispatch_roundtrip_acked_orders": cutover["route_dispatch_roundtrip_acked_orders"],
                "route_dispatch_roundtrip_missing_request_acks": cutover["route_dispatch_roundtrip_missing_request_acks"],
                "route_dispatch_roundtrip_rejected_orders": cutover["route_dispatch_roundtrip_rejected_orders"],
                "route_dispatch_roundtrip_unmatched_acks": cutover["route_dispatch_roundtrip_unmatched_acks"],
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1,
                "threshold_target_mode": thresholds.target_mode,
            }
        ]
    )


def _summary(packet: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(packet["target_mode"]),
                "strategy": str(packet["strategy"]),
                "market": str(packet["market"]),
                "scenario_key": str(packet["scenario_key"]),
                "adapter": str(packet["adapter"]),
                "route_state": "enabled" if ready else "disabled",
                "upload_orders": int(packet["upload_orders"]),
                "max_orders_per_session": int(packet["max_orders_per_session"]),
                "max_notional_per_session": float(packet["max_notional_per_session"]),
                "order_export_total_notional": float(packet["order_export_total_notional"]),
                "adapter_schema_status": str(packet["adapter_schema_status"]),
                "broker_schema_status": str(packet["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(packet["broker_schema_review_mode"]),
                "proof_refresh_ready": _to_bool(packet["proof_refresh_ready"]),
                "route_readiness_required": _to_bool(packet["route_readiness_required"]),
                "route_readiness_provided": _to_bool(packet["route_readiness_provided"]),
                "route_readiness_ready": _to_bool(packet["route_readiness_ready"]),
                "route_readiness_strategy": str(packet["route_readiness_strategy"]),
                "route_readiness_market": str(packet["route_readiness_market"]),
                "route_readiness_route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
                "route_readiness_gap_pairs": int(packet["route_readiness_gap_pairs"]),
                "broker_resume_gate_ready": _to_bool(packet["broker_resume_gate_ready"]),
                "broker_resume_proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
                "dispatch_roundtrip_required": _to_bool(packet["dispatch_roundtrip_required"]),
                "dispatch_roundtrip_provided": _to_bool(packet["dispatch_roundtrip_provided"]),
                "dispatch_roundtrip_ready": _to_bool(packet["dispatch_roundtrip_ready"]),
                "dispatch_roundtrip_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
                "dispatch_roundtrip_requests": int(packet["dispatch_roundtrip_requests"]),
                "dispatch_roundtrip_acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
                "dispatch_roundtrip_missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
                "dispatch_roundtrip_rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
                "dispatch_roundtrip_unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
                "dispatch_roundtrip_failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    packet["route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "route_dispatch_roundtrip_required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "route_dispatch_roundtrip_provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "route_dispatch_roundtrip_ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "route_dispatch_roundtrip_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "route_dispatch_roundtrip_requests": int(packet["route_dispatch_roundtrip_requests"]),
                "route_dispatch_roundtrip_acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    packet["route_dispatch_roundtrip_missing_request_acks"]
                ),
                "route_dispatch_roundtrip_rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "route_dispatch_roundtrip_unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": failed,
                "recommendation": "enable_broker_route" if ready else "keep_broker_route_disabled",
            }
        ]
    )


def _config(packet: pd.Series, thresholds: RouteEnableThresholds, checks: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "route_enabled": _to_bool(packet["route_enabled"]),
        "route_state": str(packet["route_state"]),
        "target_mode": str(packet["target_mode"]),
        "strategy": str(packet["strategy"]),
        "market": str(packet["market"]),
        "scenario_key": str(packet["scenario_key"]),
        "adapter": str(packet["adapter"]),
        "limits": {
            "max_orders_per_session": int(packet["max_orders_per_session"]),
            "max_notional_per_session": float(packet["max_notional_per_session"]),
            "stop_loss": _jsonable(packet["stop_loss"]),
        },
        "upload": {
            "ready": _to_bool(packet["upload_ready"]),
            "orders": int(packet["upload_orders"]),
            "output_file": str(packet["upload_output_file"]),
            "adapter_schema_status": str(packet["adapter_schema_status"]),
            "recommendation": str(packet["upload_recommendation"]),
        },
        "broker_readiness": {
            "adapter_schema_status": str(packet["broker_schema_status"]),
            "schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
            "schema_review_mode": str(packet["broker_schema_review_mode"]),
        },
        "order_export": {
            "provided": _to_bool(packet["order_export_provided"]),
            "ready": _to_bool(packet["order_export_ready"]),
            "orders": int(packet["order_export_orders"]),
            "total_notional": float(packet["order_export_total_notional"]),
            "max_order_notional": float(packet["order_export_max_order_notional"]),
        },
        "proof_freshness": {
            "ready": _to_bool(packet["proof_refresh_ready"]),
            "strategy": str(packet["proof_refresh_strategy"]),
            "market": str(packet["proof_refresh_market"]),
        },
        "route_readiness": {
            "required": _to_bool(packet["route_readiness_required"]),
            "provided": _to_bool(packet["route_readiness_provided"]),
            "ready": _to_bool(packet["route_readiness_ready"]),
            "strategy": str(packet["route_readiness_strategy"]),
            "market": str(packet["route_readiness_market"]),
            "route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(packet["route_readiness_gap_pairs"]),
            "recommendation": str(packet["route_readiness_recommendation"]),
        },
        "broker_resume_gate": {
            "ready": _to_bool(packet["broker_resume_gate_ready"]),
            "proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
        },
        "dispatch_roundtrip": {
            "required": _to_bool(packet["dispatch_roundtrip_required"]),
            "provided": _to_bool(packet["dispatch_roundtrip_provided"]),
            "ready": _to_bool(packet["dispatch_roundtrip_ready"]),
            "target_mode": str(packet["dispatch_roundtrip_target_mode"]),
            "strategy": str(packet["dispatch_roundtrip_strategy"]),
            "market": str(packet["dispatch_roundtrip_market"]),
            "scenario_key": str(packet["dispatch_roundtrip_scenario_key"]),
            "dispatch_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
            "requests": int(packet["dispatch_roundtrip_requests"]),
            "acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
            "failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
            "route_enable_dispatch_roundtrip": {
                "failed_checks": int(packet["route_enable_dispatch_roundtrip_failed_checks"]),
            },
            "route_proof": {
                "required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "target_mode": str(packet["route_dispatch_roundtrip_target_mode"]),
                "strategy": str(packet["route_dispatch_roundtrip_strategy"]),
                "market": str(packet["route_dispatch_roundtrip_market"]),
                "scenario_key": str(packet["route_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "requests": int(packet["route_dispatch_roundtrip_requests"]),
                "acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(packet["route_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
            },
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _cutover_state(row: pd.Series, config: dict[str, Any]) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    resume = broker_readiness.get("resume_gate", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    broker_route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route_readiness = config.get("scaleup_route_readiness", {}) or {}
    scaleup_dispatch = config.get("scaleup_dispatch_roundtrip", {}) or {}
    scaleup_route_enable = scaleup_dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route = dispatch.get("route_proof", {}) or {}
    return {
        "ready": _to_bool(row.get("ready", config.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""))),
        "market": _identity_key(_first_text(row.get("market", ""), config.get("market", ""))),
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "proof_refresh_ready": _to_bool(proof.get("ready", row.get("proof_refresh_ready", False))),
        "proof_refresh_strategy": _strategy_key(
            _first_text(proof.get("strategy", ""), row.get("proof_refresh_strategy", ""))
        ),
        "proof_refresh_market": _identity_key(_first_text(proof.get("market", ""), row.get("proof_refresh_market", ""))),
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("scaleup_route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("scaleup_route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(
            route_readiness.get("ready", row.get("scaleup_route_readiness_ready", False))
        ),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("scaleup_route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("scaleup_route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "scaleup_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "scaleup_route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("scaleup_route_readiness_recommendation", ""),
        ),
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
        "broker_resume_gate_ready": _to_bool(resume.get("ready", row.get("broker_resume_gate_ready", False))),
        "broker_resume_proof_refresh_ready": _to_bool(
            resume.get("proof_refresh_ready", row.get("broker_resume_proof_refresh_ready", False))
        ),
        "dispatch_roundtrip_required": _to_bool(
            dispatch.get("required", row.get("broker_dispatch_roundtrip_required", False))
        ),
        "dispatch_roundtrip_provided": _to_bool(
            dispatch.get("provided", row.get("broker_dispatch_roundtrip_provided", False))
        ),
        "dispatch_roundtrip_ready": _to_bool(
            dispatch.get("ready", row.get("broker_dispatch_roundtrip_ready", False))
        ),
        "dispatch_roundtrip_target_mode": _identity_key(
            _first_text(dispatch.get("target_mode", ""), row.get("broker_dispatch_roundtrip_target_mode", ""))
        ),
        "dispatch_roundtrip_strategy": _strategy_key(
            _first_text(dispatch.get("strategy", ""), row.get("broker_dispatch_roundtrip_strategy", ""))
        ),
        "dispatch_roundtrip_market": _identity_key(
            _first_text(dispatch.get("market", ""), row.get("broker_dispatch_roundtrip_market", ""))
        ),
        "dispatch_roundtrip_scenario_key": _first_text(
            dispatch.get("scenario_key", ""),
            row.get("broker_dispatch_roundtrip_scenario_key", ""),
        ),
        "dispatch_roundtrip_batch_id": _first_text(
            dispatch.get("dispatch_batch_id", ""),
            row.get("broker_dispatch_roundtrip_batch_id", ""),
        ),
        "dispatch_roundtrip_requests": int(
            _number_from(
                dispatch,
                "requests",
                _number(row, "broker_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "dispatch_roundtrip_acked_orders": int(
            _number_from(
                dispatch,
                "acked_orders",
                _number(row, "broker_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                dispatch,
                "missing_request_acks",
                _number(row, "broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_rejected_orders": int(
            _number_from(
                dispatch,
                "rejected_orders",
                _number(row, "broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                dispatch,
                "unmatched_acks",
                _number(row, "broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_failed_checks": int(
            _number_from(
                dispatch,
                "failed_checks",
                _number(row, "broker_dispatch_roundtrip_failed_checks", 0.0),
            )
        ),
        "route_enable_dispatch_roundtrip_failed_checks": max(
            int(
                _number_from(
                    broker_route_enable,
                    "failed_checks",
                    _number(row, "broker_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
            int(
                _number_from(
                    scaleup_route_enable,
                    "failed_checks",
                    _number(row, "scaleup_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
        ),
        "route_dispatch_roundtrip_required": _to_bool(
            route.get("required", row.get("broker_route_dispatch_roundtrip_required", False))
        ),
        "route_dispatch_roundtrip_provided": _to_bool(
            route.get("provided", row.get("broker_route_dispatch_roundtrip_provided", False))
        ),
        "route_dispatch_roundtrip_ready": _to_bool(
            route.get("ready", row.get("broker_route_dispatch_roundtrip_ready", False))
        ),
        "route_dispatch_roundtrip_target_mode": _identity_key(
            _first_text(route.get("target_mode", ""), row.get("broker_route_dispatch_roundtrip_target_mode", ""))
        ),
        "route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(route.get("strategy", ""), row.get("broker_route_dispatch_roundtrip_strategy", ""))
        ),
        "route_dispatch_roundtrip_market": _identity_key(
            _first_text(route.get("market", ""), row.get("broker_route_dispatch_roundtrip_market", ""))
        ),
        "route_dispatch_roundtrip_scenario_key": _first_text(
            route.get("scenario_key", ""),
            row.get("broker_route_dispatch_roundtrip_scenario_key", ""),
        ),
        "route_dispatch_roundtrip_batch_id": _first_text(
            route.get("dispatch_batch_id", ""),
            row.get("broker_route_dispatch_roundtrip_batch_id", ""),
        ),
        "route_dispatch_roundtrip_requests": int(
            _number_from(
                route,
                "requests",
                _number(row, "broker_route_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "route_dispatch_roundtrip_acked_orders": int(
            _number_from(
                route,
                "acked_orders",
                _number(row, "broker_route_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                route,
                "missing_request_acks",
                _number(row, "broker_route_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "route_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                route,
                "rejected_orders",
                _number(row, "broker_route_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                route,
                "unmatched_acks",
                _number(row, "broker_route_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
    }


def _upload_state(row: pd.Series) -> dict[str, Any]:
    return {
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "schema_status": _first_text(row.get("adapter_schema_status", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "output_file": _first_text(row.get("output_file", "")),
        "recommendation": _first_text(row.get("recommendation", "")),
    }


def _order_export_state(summary: pd.DataFrame) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "provided": not summary.empty,
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "total_notional": float(_number(row, "total_notional", 0.0)),
        "max_order_notional": float(_number(row, "max_order_notional", 0.0)),
    }


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required route-enable input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required route-enable input is empty: {name}")
    return frame


def _read_optional(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def _summary_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path:
    if path is None:
        return Path(filename)
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    return next(
        (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
        direct,
    )


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: RouteEnableThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any] | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (cutover is not None and cutover["route_readiness_required"])
    )


def _route_dispatch_roundtrip_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any]) -> bool:
    return bool(
        _dispatch_roundtrip_required(thresholds)
        or cutover["route_dispatch_roundtrip_required"]
        or cutover["route_dispatch_roundtrip_provided"]
    )


def _validate_thresholds(thresholds: RouteEnableThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")


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
    return value


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
