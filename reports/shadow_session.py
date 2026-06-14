from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ShadowSessionThresholds:
    require_launch_ready: bool = True
    require_export_ready: bool = True
    require_reconciliation_passed: bool = True
    require_runtime_session: bool = False
    require_runtime_guard_continue: bool = True
    require_broker_readiness: bool = False
    max_failed_component_checks: int = 0
    min_order_fill_rate: float = 0.0
    max_unmatched_fills: int = 0
    max_mismatched_orders: int = 0
    max_overfilled_orders: int = 0
    max_unfilled_orders: int | None = None
    max_adverse_slippage: float | None = None


@dataclass(frozen=True)
class ShadowSessionReport:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def accepted(self) -> bool:
        return bool(self.summary.iloc[0]["accepted"]) if not self.summary.empty else False


def evaluate_shadow_session(
    *,
    launch_summary: pd.DataFrame,
    launch_checks: pd.DataFrame,
    export_summary: pd.DataFrame,
    export_checks: pd.DataFrame,
    reconciliation_summary: pd.DataFrame,
    reconciliation_checks: pd.DataFrame,
    runtime_session_summary: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    thresholds: ShadowSessionThresholds | None = None,
) -> ShadowSessionReport:
    thresholds = thresholds or ShadowSessionThresholds()
    _validate_thresholds(thresholds)
    _require(launch_summary, ["ready", "mode", "adapter", "scenario_key"], "launch_summary")
    _require(export_summary, ["ready", "adapter", "scenario_key"], "export_summary")
    _require(reconciliation_summary, ["passed", "order_fill_rate"], "reconciliation_summary")
    runtime_session_summary = pd.DataFrame() if runtime_session_summary is None else runtime_session_summary
    broker_readiness_summary = pd.DataFrame() if broker_readiness_summary is None else broker_readiness_summary

    metrics = _metrics(
        launch_summary,
        launch_checks,
        export_summary,
        export_checks,
        reconciliation_summary,
        reconciliation_checks,
        runtime_session_summary,
        broker_readiness_summary,
    )
    checks = _checks(metrics.iloc[0], thresholds)
    summary = _summary(metrics.iloc[0], checks)
    return ShadowSessionReport(metrics=metrics, checks=checks, summary=summary)


def write_shadow_session_report(
    *,
    launch_dir: str | Path,
    export_dir: str | Path,
    reconciliation_dir: str | Path,
    output_dir: str | Path,
    runtime_session_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    thresholds: ShadowSessionThresholds | None = None,
) -> ShadowSessionReport:
    launch = Path(launch_dir)
    export = Path(export_dir)
    reconciliation = Path(reconciliation_dir)
    thresholds = thresholds or ShadowSessionThresholds()
    report = evaluate_shadow_session(
        launch_summary=_read_required(launch / "launch_summary.csv"),
        launch_checks=_read_required(launch / "launch_checks.csv"),
        export_summary=_read_required(export / "broker_order_summary.csv"),
        export_checks=_read_required(export / "broker_order_checks.csv"),
        reconciliation_summary=_read_required(reconciliation / "reconciliation_summary.csv"),
        reconciliation_checks=_read_required(reconciliation / "reconciliation_checks.csv"),
        runtime_session_summary=_read_runtime_session_summary(runtime_session_dir),
        broker_readiness_summary=_read_broker_readiness_summary(broker_readiness_dir),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "shadow_session_metrics.csv", index=False)
    report.checks.to_csv(out / "shadow_session_checks.csv", index=False)
    report.summary.to_csv(out / "shadow_session_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="shadow_session_report",
        parameters={"thresholds": asdict(thresholds)},
        inputs={
            "launch": launch,
            "export": export,
            "reconciliation": reconciliation,
            "runtime_session": runtime_session_dir,
            "broker_readiness": broker_readiness_dir,
        },
    )
    return ShadowSessionReport(report.metrics, report.checks, report.summary, out)


def _metrics(
    launch_summary: pd.DataFrame,
    launch_checks: pd.DataFrame,
    export_summary: pd.DataFrame,
    export_checks: pd.DataFrame,
    reconciliation_summary: pd.DataFrame,
    reconciliation_checks: pd.DataFrame,
    runtime_session_summary: pd.DataFrame,
    broker_readiness_summary: pd.DataFrame,
) -> pd.DataFrame:
    launch = launch_summary.iloc[0]
    export = export_summary.iloc[0]
    recon = reconciliation_summary.iloc[0]
    runtime = runtime_session_summary.iloc[0] if not runtime_session_summary.empty else pd.Series(dtype=object)
    broker = broker_readiness_summary.iloc[0] if not broker_readiness_summary.empty else pd.Series(dtype=object)
    launch_failed = _failed_checks(launch_checks)
    export_failed = _failed_checks(export_checks)
    recon_failed = _failed_checks(reconciliation_checks)
    runtime_failed = int(_number(runtime, "failed_checks")) if not runtime.empty else 0
    broker_failed = int(_number(broker, "failed_checks")) if not broker.empty else 0
    launch_scenario = str(launch.get("scenario_key", ""))
    export_scenario = str(export.get("scenario_key", ""))
    scenario_match = launch_scenario == export_scenario
    return pd.DataFrame(
        [
            {
                "launch_ready": _to_bool(launch["ready"]),
                "export_ready": _to_bool(export["ready"]),
                "reconciliation_passed": _to_bool(recon["passed"]),
                "runtime_session_provided": not runtime_session_summary.empty,
                "runtime_session_ready": _to_bool(runtime.get("ready", False)) if not runtime.empty else False,
                "runtime_guard_action": str(runtime.get("guard_action", "")) if not runtime.empty else "",
                "runtime_guard_halted": _to_bool(runtime.get("halted", False)) if not runtime.empty else False,
                "runtime_target_mode": _text(runtime, "target_mode"),
                "runtime_strategy": _text(runtime, "strategy"),
                "runtime_market": _text(runtime, "market"),
                "runtime_proof_refresh_required": _to_bool(runtime.get("proof_refresh_required", False))
                if not runtime.empty
                else False,
                "runtime_proof_refresh_provided": _to_bool(runtime.get("proof_refresh_provided", False))
                if not runtime.empty
                else False,
                "runtime_proof_refresh_ready": _to_bool(runtime.get("proof_refresh_ready", False))
                if not runtime.empty
                else False,
                "runtime_proof_refresh_strategy": _text(runtime, "proof_refresh_strategy"),
                "runtime_proof_refresh_market": _text(runtime, "proof_refresh_market"),
                "runtime_proof_refresh_mixed_identity": _to_bool(
                    runtime.get("proof_refresh_mixed_identity", False)
                )
                if not runtime.empty
                else False,
                "runtime_proof_source": _text(runtime, "proof_source"),
                "runtime_broker_resume_gate_required": _to_bool(runtime.get("broker_resume_gate_required", False))
                if not runtime.empty
                else False,
                "runtime_broker_resume_gate_provided": _to_bool(runtime.get("broker_resume_gate_provided", False))
                if not runtime.empty
                else False,
                "runtime_broker_resume_gate_ready": _to_bool(runtime.get("broker_resume_gate_ready", False))
                if not runtime.empty
                else False,
                "runtime_broker_resume_strategy": _text(runtime, "broker_resume_strategy"),
                "runtime_broker_resume_market": _text(runtime, "broker_resume_market"),
                "runtime_broker_resume_proof_refresh_ready": _to_bool(
                    runtime.get("broker_resume_proof_refresh_ready", False)
                )
                if not runtime.empty
                else False,
                "runtime_broker_resume_proof_refresh_strategy": _text(
                    runtime,
                    "broker_resume_proof_refresh_strategy",
                ),
                "runtime_broker_resume_proof_refresh_market": _text(
                    runtime,
                    "broker_resume_proof_refresh_market",
                ),
                "runtime_failed_steps": _number(runtime, "failed_steps") if not runtime.empty else 0.0,
                "runtime_failed_checks": runtime_failed,
                "broker_readiness_provided": not broker_readiness_summary.empty,
                "broker_readiness_ready": _to_bool(broker.get("ready", False)) if not broker.empty else False,
                "broker_readiness_adapter": _text(broker, "adapter"),
                "broker_schema_status": _text(broker, "adapter_schema_status"),
                "broker_schema_reviewed": _to_bool(broker.get("schema_reviewed", False))
                if not broker.empty
                else False,
                "broker_schema_review_mode": _text(broker, "schema_review_mode"),
                "broker_route_readiness_required": _to_bool(broker.get("route_readiness_required", False))
                if not broker.empty
                else False,
                "broker_route_readiness_provided": _to_bool(broker.get("route_readiness_provided", False))
                if not broker.empty
                else False,
                "broker_route_readiness_ready": _to_bool(broker.get("route_readiness_ready", False))
                if not broker.empty
                else False,
                "broker_route_readiness_strategy": _text(broker, "route_readiness_strategy"),
                "broker_route_readiness_market": _text(broker, "route_readiness_market"),
                "broker_route_readiness_gap_pairs": _number_or_zero(broker, "route_readiness_gap_pairs")
                if not broker.empty
                else 0.0,
                "broker_dispatch_roundtrip_provided": _to_bool(broker.get("dispatch_roundtrip_provided", False))
                if not broker.empty
                else False,
                "broker_dispatch_roundtrip_ready": _to_bool(broker.get("dispatch_roundtrip_ready", False))
                if not broker.empty
                else False,
                "broker_dispatch_roundtrip_target_mode": _text(broker, "dispatch_roundtrip_target_mode"),
                "broker_dispatch_roundtrip_strategy": _text(broker, "dispatch_roundtrip_strategy"),
                "broker_dispatch_roundtrip_market": _text(broker, "dispatch_roundtrip_market"),
                "broker_dispatch_roundtrip_scenario_key": _text(broker, "dispatch_roundtrip_scenario_key"),
                "broker_dispatch_roundtrip_missing_request_acks": _number_or_zero(
                    broker,
                    "dispatch_roundtrip_missing_request_acks",
                )
                if not broker.empty
                else 0.0,
                "broker_dispatch_roundtrip_rejected_orders": _number_or_zero(
                    broker,
                    "dispatch_roundtrip_rejected_orders",
                )
                if not broker.empty
                else 0.0,
                "broker_dispatch_roundtrip_unmatched_acks": _number_or_zero(
                    broker,
                    "dispatch_roundtrip_unmatched_acks",
                )
                if not broker.empty
                else 0.0,
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    broker.get("route_dispatch_roundtrip_provided", False)
                )
                if not broker.empty
                else False,
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    broker.get("route_dispatch_roundtrip_ready", False)
                )
                if not broker.empty
                else False,
                "broker_route_dispatch_roundtrip_strategy": _text(broker, "route_dispatch_roundtrip_strategy"),
                "broker_route_dispatch_roundtrip_market": _text(broker, "route_dispatch_roundtrip_market"),
                "broker_route_dispatch_roundtrip_scenario_key": _text(
                    broker,
                    "route_dispatch_roundtrip_scenario_key",
                ),
                "broker_failed_checks": broker_failed,
                "scenario_key": launch_scenario,
                "export_scenario_key": export_scenario,
                "scenario_match": scenario_match,
                "mode": str(launch.get("mode", "")),
                "adapter": str(export.get("adapter", launch.get("adapter", ""))),
                "launch_failed_checks": launch_failed,
                "export_failed_checks": export_failed,
                "reconciliation_failed_checks": recon_failed,
                "total_failed_component_checks": (
                    launch_failed + export_failed + recon_failed + runtime_failed + broker_failed
                ),
                "orders": _number(recon, "orders"),
                "filled_orders": _number(recon, "filled_orders"),
                "unfilled_orders": _number(recon, "unfilled_orders"),
                "partial_orders": _number(recon, "partial_orders"),
                "overfilled_orders": _number(recon, "overfilled_orders"),
                "mismatched_orders": _number(recon, "mismatched_orders"),
                "unmatched_fills": _number(recon, "unmatched_fills"),
                "order_fill_rate": _number(recon, "order_fill_rate"),
                "requested_qty": _number(recon, "requested_qty"),
                "live_qty": _number(recon, "live_qty"),
                "max_adverse_slippage": _number(recon, "max_adverse_slippage"),
                "avg_adverse_slippage": _number(recon, "avg_adverse_slippage"),
                "avg_latency_ns": _number(recon, "avg_latency_ns"),
            }
        ]
    )


def _checks(row: pd.Series, thresholds: ShadowSessionThresholds) -> pd.DataFrame:
    checks = [
        _check(
            "launch_ready",
            row["launch_ready"],
            "is",
            True,
            (not thresholds.require_launch_ready) or bool(row["launch_ready"]),
            "launch bundle is not ready",
        ),
        _check(
            "export_ready",
            row["export_ready"],
            "is",
            True,
            (not thresholds.require_export_ready) or bool(row["export_ready"]),
            "order export is not ready",
        ),
        _check(
            "reconciliation_passed",
            row["reconciliation_passed"],
            "is",
            True,
            (not thresholds.require_reconciliation_passed) or bool(row["reconciliation_passed"]),
            "broker fill reconciliation did not pass",
        ),
        _check(
            "scenario_match",
            row["scenario_match"],
            "is",
            True,
            bool(row["scenario_match"]),
            "launch and export scenario keys differ",
        ),
        _threshold_check(
            "total_failed_component_checks",
            row["total_failed_component_checks"],
            "<=",
            thresholds.max_failed_component_checks,
        ),
        _threshold_check("order_fill_rate", row["order_fill_rate"], ">=", thresholds.min_order_fill_rate),
        _threshold_check("unmatched_fills", row["unmatched_fills"], "<=", thresholds.max_unmatched_fills),
        _threshold_check("mismatched_orders", row["mismatched_orders"], "<=", thresholds.max_mismatched_orders),
        _threshold_check("overfilled_orders", row["overfilled_orders"], "<=", thresholds.max_overfilled_orders),
    ]
    if thresholds.max_unfilled_orders is not None:
        checks.append(_threshold_check("unfilled_orders", row["unfilled_orders"], "<=", thresholds.max_unfilled_orders))
    if thresholds.max_adverse_slippage is not None:
        checks.append(
            _threshold_check("max_adverse_slippage", row["max_adverse_slippage"], "<=", thresholds.max_adverse_slippage)
        )
    if thresholds.require_runtime_session or bool(row["runtime_session_provided"]):
        checks.append(
            _check(
                "runtime_session_provided",
                row["runtime_session_provided"],
                "is",
                True,
                bool(row["runtime_session_provided"]),
                "runtime session monitor evidence is required but missing",
            )
        )
    if bool(row["runtime_session_provided"]) and thresholds.require_runtime_guard_continue:
        checks.extend(
            [
                _check(
                    "runtime_session_ready",
                    row["runtime_session_ready"],
                    "is",
                    True,
                    bool(row["runtime_session_ready"]),
                    "runtime session monitor did not finish ready",
                ),
                _check(
                    "runtime_guard_continue",
                    row["runtime_guard_action"],
                    "==",
                    "continue",
                    str(row["runtime_guard_action"]) == "continue" and not bool(row["runtime_guard_halted"]),
                    "runtime guard halted during the paper/shadow session",
                ),
            ]
        )
        if bool(row["runtime_proof_refresh_required"]) or bool(row["runtime_proof_refresh_provided"]):
            checks.extend(
                [
                    _check(
                        "runtime_proof_refresh_ready",
                        row["runtime_proof_refresh_ready"],
                        "is",
                        True,
                        bool(row["runtime_proof_refresh_ready"]),
                        "runtime proof-refresh evidence is not ready",
                    ),
                    _check(
                        "runtime_proof_refresh_identity_consistent",
                        row["runtime_proof_refresh_mixed_identity"],
                        "is",
                        False,
                        not bool(row["runtime_proof_refresh_mixed_identity"]),
                        "runtime proof-refresh evidence reports mixed identity",
                    ),
                    _check(
                        "runtime_proof_refresh_strategy_matches",
                        row["runtime_proof_refresh_strategy"],
                        "==",
                        row["runtime_strategy"],
                        bool(row["runtime_proof_refresh_strategy"])
                        and row["runtime_proof_refresh_strategy"] == row["runtime_strategy"],
                        "runtime proof-refresh strategy does not match runtime strategy",
                    ),
                    _check(
                        "runtime_proof_refresh_market_matches",
                        row["runtime_proof_refresh_market"],
                        "==",
                        row["runtime_market"],
                        bool(row["runtime_proof_refresh_market"])
                        and row["runtime_proof_refresh_market"] == row["runtime_market"],
                        "runtime proof-refresh market does not match runtime market",
                    ),
                ]
            )
        if bool(row["runtime_broker_resume_gate_required"]) or bool(row["runtime_broker_resume_gate_provided"]):
            checks.extend(
                [
                    _check(
                        "runtime_broker_resume_gate_provided",
                        row["runtime_broker_resume_gate_provided"],
                        "is",
                        True,
                        bool(row["runtime_broker_resume_gate_provided"]),
                        "runtime broker resume-gate evidence is required but missing",
                    ),
                    _check(
                        "runtime_broker_resume_gate_ready",
                        row["runtime_broker_resume_gate_ready"],
                        "is",
                        True,
                        bool(row["runtime_broker_resume_gate_ready"]),
                        "runtime broker resume-gate evidence is not ready",
                    ),
                    _check(
                        "runtime_broker_resume_strategy_matches",
                        row["runtime_broker_resume_strategy"],
                        "==",
                        row["runtime_strategy"],
                        bool(row["runtime_broker_resume_strategy"])
                        and row["runtime_broker_resume_strategy"] == row["runtime_strategy"],
                        "runtime broker resume-gate strategy does not match runtime strategy",
                    ),
                    _check(
                        "runtime_broker_resume_market_matches",
                        row["runtime_broker_resume_market"],
                        "==",
                        row["runtime_market"],
                        bool(row["runtime_broker_resume_market"])
                        and row["runtime_broker_resume_market"] == row["runtime_market"],
                        "runtime broker resume-gate market does not match runtime market",
                    ),
                    _check(
                        "runtime_broker_resume_proof_refresh_ready",
                        row["runtime_broker_resume_proof_refresh_ready"],
                        "is",
                        True,
                        bool(row["runtime_broker_resume_proof_refresh_ready"]),
                        "runtime broker resume-gate proof freshness is not ready",
                    ),
                    _check(
                        "runtime_broker_resume_proof_refresh_strategy_matches",
                        row["runtime_broker_resume_proof_refresh_strategy"],
                        "==",
                        row["runtime_strategy"],
                        bool(row["runtime_broker_resume_proof_refresh_strategy"])
                        and row["runtime_broker_resume_proof_refresh_strategy"] == row["runtime_strategy"],
                        "runtime broker resume-gate proof strategy does not match runtime strategy",
                    ),
                    _check(
                        "runtime_broker_resume_proof_refresh_market_matches",
                        row["runtime_broker_resume_proof_refresh_market"],
                        "==",
                        row["runtime_market"],
                        bool(row["runtime_broker_resume_proof_refresh_market"])
                        and row["runtime_broker_resume_proof_refresh_market"] == row["runtime_market"],
                        "runtime broker resume-gate proof market does not match runtime market",
                    ),
                ]
            )
    if thresholds.require_broker_readiness or bool(row["broker_readiness_provided"]):
        checks.append(
            _check(
                "broker_readiness_provided",
                row["broker_readiness_provided"],
                "is",
                True,
                bool(row["broker_readiness_provided"]),
                "broker readiness evidence is required but missing",
            )
        )
    if bool(row["broker_readiness_provided"]):
        checks.extend(_broker_readiness_checks(row))
    return pd.DataFrame(checks)


def _broker_readiness_checks(row: pd.Series) -> list[dict[str, object]]:
    checks = [
        _check(
            "broker_readiness_ready",
            row["broker_readiness_ready"],
            "is",
            True,
            bool(row["broker_readiness_ready"]),
            "broker readiness gate is not ready",
        ),
        _check(
            "broker_readiness_adapter_matches",
            _identity_key(row["broker_readiness_adapter"]),
            "==",
            _identity_key(row["adapter"]),
            bool(_identity_key(row["broker_readiness_adapter"]) == _identity_key(row["adapter"])),
            "broker readiness adapter does not match session adapter",
        ),
    ]
    if bool(row["broker_route_readiness_required"]) or bool(row["broker_route_readiness_provided"]):
        checks.extend(
            [
                _check(
                    "broker_route_readiness_provided",
                    row["broker_route_readiness_provided"],
                    "is",
                    True,
                    bool(row["broker_route_readiness_provided"]),
                    "broker readiness must carry route-readiness proof",
                ),
                _check(
                    "broker_route_readiness_ready",
                    row["broker_route_readiness_ready"],
                    "is",
                    True,
                    bool(row["broker_route_readiness_ready"]),
                    "broker route-readiness proof is not ready",
                ),
                _identity_match_check(
                    "broker_route_readiness_strategy_matches",
                    row["broker_route_readiness_strategy"],
                    row["runtime_strategy"],
                    "broker route-readiness strategy does not match runtime strategy",
                ),
                _identity_match_check(
                    "broker_route_readiness_market_matches",
                    row["broker_route_readiness_market"],
                    row["runtime_market"],
                    "broker route-readiness market does not match runtime market",
                ),
                _threshold_check(
                    "broker_route_readiness_gap_pairs",
                    row["broker_route_readiness_gap_pairs"],
                    "<=",
                    0,
                ),
            ]
        )
    if bool(row["broker_dispatch_roundtrip_provided"]):
        checks.extend(
            [
                _check(
                    "broker_dispatch_roundtrip_ready",
                    row["broker_dispatch_roundtrip_ready"],
                    "is",
                    True,
                    bool(row["broker_dispatch_roundtrip_ready"]),
                    "broker dispatch round-trip proof is not ready",
                ),
                _identity_match_check(
                    "broker_dispatch_roundtrip_strategy_matches",
                    row["broker_dispatch_roundtrip_strategy"],
                    row["runtime_strategy"],
                    "broker dispatch round-trip strategy does not match runtime strategy",
                ),
                _identity_match_check(
                    "broker_dispatch_roundtrip_market_matches",
                    row["broker_dispatch_roundtrip_market"],
                    row["runtime_market"],
                    "broker dispatch round-trip market does not match runtime market",
                ),
                _check(
                    "broker_dispatch_roundtrip_scenario_matches",
                    row["broker_dispatch_roundtrip_scenario_key"],
                    "==",
                    row["scenario_key"],
                    bool(
                        str(row["broker_dispatch_roundtrip_scenario_key"])
                        and str(row["broker_dispatch_roundtrip_scenario_key"]) == str(row["scenario_key"])
                    ),
                    "broker dispatch round-trip scenario does not match session scenario",
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_missing_request_acks",
                    row["broker_dispatch_roundtrip_missing_request_acks"],
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_rejected_orders",
                    row["broker_dispatch_roundtrip_rejected_orders"],
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_unmatched_acks",
                    row["broker_dispatch_roundtrip_unmatched_acks"],
                    "<=",
                    0,
                ),
            ]
        )
    if bool(row["broker_route_dispatch_roundtrip_provided"]):
        checks.extend(
            [
                _check(
                    "broker_route_dispatch_roundtrip_ready",
                    row["broker_route_dispatch_roundtrip_ready"],
                    "is",
                    True,
                    bool(row["broker_route_dispatch_roundtrip_ready"]),
                    "broker route dispatch round-trip proof is not ready",
                ),
                _identity_match_check(
                    "broker_route_dispatch_roundtrip_strategy_matches",
                    row["broker_route_dispatch_roundtrip_strategy"],
                    row["runtime_strategy"],
                    "broker route dispatch round-trip strategy does not match runtime strategy",
                ),
                _identity_match_check(
                    "broker_route_dispatch_roundtrip_market_matches",
                    row["broker_route_dispatch_roundtrip_market"],
                    row["runtime_market"],
                    "broker route dispatch round-trip market does not match runtime market",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_scenario_matches",
                    row["broker_route_dispatch_roundtrip_scenario_key"],
                    "==",
                    row["scenario_key"],
                    bool(
                        str(row["broker_route_dispatch_roundtrip_scenario_key"])
                        and str(row["broker_route_dispatch_roundtrip_scenario_key"]) == str(row["scenario_key"])
                    ),
                    "broker route dispatch round-trip scenario does not match session scenario",
                ),
            ]
        )
    return checks


def _summary(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    accepted = bool(checks["passed"].all()) if not checks.empty else False
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "accepted": accepted,
                "scenario_key": row["scenario_key"],
                "mode": row["mode"],
                "adapter": row["adapter"],
                "strategy": row["runtime_strategy"],
                "market": row["runtime_market"],
                "order_fill_rate": float(row["order_fill_rate"]),
                "runtime_session_provided": bool(row["runtime_session_provided"]),
                "runtime_guard_action": row["runtime_guard_action"],
                "runtime_target_mode": row["runtime_target_mode"],
                "runtime_strategy": row["runtime_strategy"],
                "runtime_market": row["runtime_market"],
                "runtime_proof_refresh_required": bool(row["runtime_proof_refresh_required"]),
                "runtime_proof_refresh_provided": bool(row["runtime_proof_refresh_provided"]),
                "runtime_proof_refresh_ready": bool(row["runtime_proof_refresh_ready"]),
                "runtime_proof_refresh_strategy": row["runtime_proof_refresh_strategy"],
                "runtime_proof_refresh_market": row["runtime_proof_refresh_market"],
                "runtime_proof_refresh_mixed_identity": bool(row["runtime_proof_refresh_mixed_identity"]),
                "runtime_proof_source": row["runtime_proof_source"],
                "runtime_broker_resume_gate_required": bool(row["runtime_broker_resume_gate_required"]),
                "runtime_broker_resume_gate_provided": bool(row["runtime_broker_resume_gate_provided"]),
                "runtime_broker_resume_gate_ready": bool(row["runtime_broker_resume_gate_ready"]),
                "runtime_broker_resume_strategy": row["runtime_broker_resume_strategy"],
                "runtime_broker_resume_market": row["runtime_broker_resume_market"],
                "runtime_broker_resume_proof_refresh_ready": bool(
                    row["runtime_broker_resume_proof_refresh_ready"]
                ),
                "runtime_broker_resume_proof_refresh_strategy": row[
                    "runtime_broker_resume_proof_refresh_strategy"
                ],
                "runtime_broker_resume_proof_refresh_market": row[
                    "runtime_broker_resume_proof_refresh_market"
                ],
                "runtime_failed_checks": int(row["runtime_failed_checks"]),
                "broker_readiness_provided": bool(row["broker_readiness_provided"]),
                "broker_readiness_ready": bool(row["broker_readiness_ready"]),
                "broker_readiness_adapter": row["broker_readiness_adapter"],
                "broker_schema_status": row["broker_schema_status"],
                "broker_schema_reviewed": bool(row["broker_schema_reviewed"]),
                "broker_schema_review_mode": row["broker_schema_review_mode"],
                "broker_route_readiness_required": bool(row["broker_route_readiness_required"]),
                "broker_route_readiness_provided": bool(row["broker_route_readiness_provided"]),
                "broker_route_readiness_ready": bool(row["broker_route_readiness_ready"]),
                "broker_route_readiness_strategy": row["broker_route_readiness_strategy"],
                "broker_route_readiness_market": row["broker_route_readiness_market"],
                "broker_route_readiness_gap_pairs": int(row["broker_route_readiness_gap_pairs"]),
                "broker_dispatch_roundtrip_provided": bool(row["broker_dispatch_roundtrip_provided"]),
                "broker_dispatch_roundtrip_ready": bool(row["broker_dispatch_roundtrip_ready"]),
                "broker_dispatch_roundtrip_target_mode": row["broker_dispatch_roundtrip_target_mode"],
                "broker_dispatch_roundtrip_strategy": row["broker_dispatch_roundtrip_strategy"],
                "broker_dispatch_roundtrip_market": row["broker_dispatch_roundtrip_market"],
                "broker_dispatch_roundtrip_scenario_key": row["broker_dispatch_roundtrip_scenario_key"],
                "broker_route_dispatch_roundtrip_provided": bool(
                    row["broker_route_dispatch_roundtrip_provided"]
                ),
                "broker_route_dispatch_roundtrip_ready": bool(row["broker_route_dispatch_roundtrip_ready"]),
                "broker_route_dispatch_roundtrip_strategy": row["broker_route_dispatch_roundtrip_strategy"],
                "broker_route_dispatch_roundtrip_market": row["broker_route_dispatch_roundtrip_market"],
                "broker_failed_checks": int(row["broker_failed_checks"]),
                "total_failed_component_checks": int(row["total_failed_component_checks"]),
                "failed_checks": failed_checks,
                "recommendation": "continue_shadow_or_promote" if accepted else "hold_in_research",
            }
        ]
    )


def _failed_checks(frame: pd.DataFrame) -> int:
    if frame.empty or "passed" not in frame.columns:
        return 0
    return int((~frame["passed"].map(_to_bool)).sum())


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _identity_match_check(name: str, value: object, expected: object, reason: str) -> dict[str, object]:
    value_key = _identity_key(value)
    expected_key = _identity_key(expected)
    passed = bool((not expected_key) or (value_key and value_key == expected_key))
    return _check(name, value_key, "==", expected_key, passed, reason)


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


def _validate_thresholds(thresholds: ShadowSessionThresholds) -> None:
    if thresholds.max_failed_component_checks < 0:
        raise ValueError("max_failed_component_checks must be non-negative")
    if not 0 <= thresholds.min_order_fill_rate <= 1:
        raise ValueError("min_order_fill_rate must be between 0 and 1")
    for name in ("max_unmatched_fills", "max_mismatched_orders", "max_overfilled_orders", "max_unfilled_orders"):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    if thresholds.max_adverse_slippage is not None and thresholds.max_adverse_slippage < 0:
        raise ValueError("max_adverse_slippage must be non-negative")


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required shadow-session input missing: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required shadow-session input is empty: {path}")
    return frame


def _read_runtime_session_summary(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "runtime_session_summary.csv"
    return _read_required(candidate)


def _read_broker_readiness_summary(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "broker_readiness_summary.csv"
    return _read_required(candidate)


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _number(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _number_or_zero(row: pd.Series, column: str) -> float:
    value = _number(row, column)
    return 0.0 if pd.isna(value) else value


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
