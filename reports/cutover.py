from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class CutoverGateThresholds:
    target_mode: str = "live_dryrun"
    require_scaleup_ready: bool = True
    require_broker_readiness: bool = True
    require_runtime_session: bool = True
    require_runtime_guard_continue: bool = True
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    require_operator_approval: bool = True
    require_operator_identity_ack: bool = True
    require_operator_limits_ack: bool = True
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class CutoverGateReport:
    authorization: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_cutover_gate(
    *,
    scaleup_summary: pd.DataFrame,
    scaleup_config: dict[str, Any] | None = None,
    scaleup_checks: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    runtime_session_summary: pd.DataFrame | None = None,
    operator_review: pd.DataFrame | None = None,
    thresholds: CutoverGateThresholds | None = None,
) -> CutoverGateReport:
    thresholds = thresholds or CutoverGateThresholds()
    _validate_thresholds(thresholds)
    scaleup_summary = _require_nonempty(scaleup_summary, "scaleup_summary")
    scaleup_config = scaleup_config or {}
    scaleup_checks = pd.DataFrame() if scaleup_checks is None else scaleup_checks.copy().reset_index(drop=True)
    broker_readiness_summary = _optional_frame(broker_readiness_summary)
    runtime_session_summary = _optional_frame(runtime_session_summary)
    operator_review = _optional_frame(operator_review)

    scaleup = _scaleup_state(scaleup_summary.iloc[0], scaleup_config, scaleup_checks)
    broker = _broker_state(broker_readiness_summary)
    runtime = _runtime_state(runtime_session_summary, broker)
    operator = _operator_state(operator_review, scaleup)
    checks = _checks(scaleup, broker, runtime, operator, thresholds)
    authorization = _authorization(scaleup, broker, runtime, operator, thresholds, checks)
    summary = _summary(authorization.iloc[0], checks)
    config = _config(authorization.iloc[0], thresholds, checks)
    return CutoverGateReport(authorization=authorization, checks=checks, summary=summary, config=config)


def write_cutover_gate_report(
    *,
    scaleup_dir: str | Path,
    broker_readiness_dir: str | Path,
    output_dir: str | Path,
    runtime_session_dir: str | Path | None = None,
    operator_review_path: str | Path | None = None,
    thresholds: CutoverGateThresholds | None = None,
) -> CutoverGateReport:
    scaleup = Path(scaleup_dir)
    broker = Path(broker_readiness_dir)
    thresholds = thresholds or CutoverGateThresholds()
    _validate_thresholds(thresholds)
    scaleup_config_path = scaleup / "scaleup_config.json" if scaleup.is_dir() else Path(scaleup_dir)
    broker_readiness_summary_path = _summary_path(
        broker,
        "broker_readiness_summary.csv",
        fallback_dirs=("06_broker_readiness", "05_broker_readiness"),
    )
    if not scaleup_config_path.exists():
        raise FileNotFoundError(f"scale-up config not found: {scaleup_config_path}")
    scaleup_summary_path = (
        scaleup / "scaleup_summary.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_summary.csv")
    )
    scaleup_checks_path = (
        scaleup / "scaleup_checks.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_checks.csv")
    )
    runtime_session_summary_path = (
        _summary_path(runtime_session_dir, "runtime_session_summary.csv")
        if runtime_session_dir is not None
        else None
    )
    report = evaluate_cutover_gate(
        scaleup_summary=_read_required(scaleup_summary_path, "scaleup_summary"),
        scaleup_config=json.loads(scaleup_config_path.read_text(encoding="utf-8")),
        scaleup_checks=_read_optional(scaleup_checks_path),
        broker_readiness_summary=_read_required(broker_readiness_summary_path, "broker_readiness"),
        runtime_session_summary=_read_optional(runtime_session_summary_path),
        operator_review=_read_optional(operator_review_path),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.authorization.to_csv(out / "cutover_authorization.csv", index=False)
    report.checks.to_csv(out / "cutover_checks.csv", index=False)
    report.summary.to_csv(out / "cutover_summary.csv", index=False)
    (out / "cutover_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs: dict[str, Any] = {
        "scaleup_summary": scaleup_summary_path,
        "scaleup_config": scaleup_config_path,
        "broker_readiness_summary": broker_readiness_summary_path,
    }
    if scaleup_checks_path.exists():
        inputs["scaleup_checks"] = scaleup_checks_path
    if runtime_session_summary_path is not None:
        inputs["runtime_session_summary"] = runtime_session_summary_path
    if operator_review_path is not None:
        inputs["operator_review"] = Path(operator_review_path)
    write_experiment_manifest(
        out,
        run_type="cutover_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return CutoverGateReport(report.authorization, report.checks, report.summary, report.config, out)


def _checks(
    scaleup: dict[str, Any],
    broker: dict[str, Any],
    runtime: dict[str, Any],
    operator: dict[str, Any],
    thresholds: CutoverGateThresholds,
) -> pd.DataFrame:
    target_mode = _identity_key(thresholds.target_mode)
    checks = [
        _check(
            "scaleup_ready",
            scaleup["ready"],
            "is",
            True,
            bool(scaleup["ready"]) or not thresholds.require_scaleup_ready,
            "scale-up plan is not ready",
        ),
        _check(
            "scaleup_target_mode",
            scaleup["target_mode"],
            "==",
            target_mode,
            bool(scaleup["target_mode"] and scaleup["target_mode"] == target_mode),
            "scale-up target mode does not match cutover target mode",
        ),
        _check(
            "scaleup_failed_checks",
            scaleup["failed_checks"],
            "<=",
            thresholds.max_failed_scaleup_checks,
            int(scaleup["failed_checks"]) <= thresholds.max_failed_scaleup_checks,
            "scale-up checks still have failures",
        ),
        _check(
            "broker_readiness_provided",
            broker["provided"],
            "is",
            True,
            bool(broker["provided"]) or not thresholds.require_broker_readiness,
            "broker readiness evidence is required but missing",
        ),
        _check(
            "broker_readiness_ready",
            broker["ready"],
            "is",
            True,
            bool(broker["ready"]) or not thresholds.require_broker_readiness,
            "broker readiness is not ready",
        ),
        _check(
            "broker_adapter_matches",
            broker["adapter"] or scaleup["adapter"],
            "==",
            scaleup["adapter"],
            bool((not broker["adapter"]) or broker["adapter"] == scaleup["adapter"]),
            "broker readiness adapter does not match scale-up adapter",
        ),
        _check(
            "runtime_session_provided",
            runtime["provided"],
            "is",
            True,
            bool(runtime["provided"]) or not thresholds.require_runtime_session,
            "runtime-session evidence is required but missing",
        ),
        _check(
            "runtime_session_ready",
            runtime["ready"],
            "is",
            True,
            bool(runtime["ready"]) or not thresholds.require_runtime_session,
            "runtime session is not ready",
        ),
        _check(
            "runtime_guard_continue",
            runtime["guard_action"] or ("halt" if runtime["halted"] else ""),
            "==",
            "continue",
            (runtime["guard_action"] == "continue" and not runtime["halted"])
            or not thresholds.require_runtime_guard_continue,
            "runtime guard is not continuing",
        ),
        _check(
            "runtime_target_mode_matches",
            runtime["target_mode"],
            "==",
            target_mode,
            bool(runtime["target_mode"] and runtime["target_mode"] == target_mode),
            "runtime-session target mode does not match cutover target mode",
        ),
        _check(
            "runtime_strategy_matches",
            runtime["strategy"],
            "==",
            scaleup["strategy"],
            bool(runtime["strategy"] and scaleup["strategy"] and runtime["strategy"] == scaleup["strategy"]),
            "runtime-session strategy does not match scale-up strategy",
        ),
        _check(
            "runtime_market_matches",
            runtime["market"],
            "==",
            scaleup["market"],
            bool(runtime["market"] and scaleup["market"] and runtime["market"] == scaleup["market"]),
            "runtime-session market does not match scale-up market",
        ),
        _check(
            "proof_refresh_ready",
            scaleup["proof_refresh_ready"] if scaleup["proof_refresh_active"] else "inactive",
            "is",
            True,
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_provided"] and scaleup["proof_refresh_ready"]),
            "scale-up proof freshness is missing or not ready",
        ),
        _check(
            "proof_refresh_identity_consistent",
            scaleup["proof_refresh_mixed_identity"] if scaleup["proof_refresh_active"] else "inactive",
            "is",
            False,
            (not scaleup["proof_refresh_active"]) or not bool(scaleup["proof_refresh_mixed_identity"]),
            "scale-up proof freshness has mixed strategy or market identity",
        ),
        _check(
            "proof_refresh_strategy_matches",
            scaleup["proof_refresh_strategy"] if scaleup["proof_refresh_active"] else "inactive",
            "==",
            scaleup["strategy"] if scaleup["proof_refresh_active"] else "inactive",
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_strategy"] and scaleup["proof_refresh_strategy"] == scaleup["strategy"]),
            "scale-up proof freshness strategy does not match cutover strategy",
        ),
        _check(
            "proof_refresh_market_matches",
            scaleup["proof_refresh_market"] if scaleup["proof_refresh_active"] else "inactive",
            "==",
            scaleup["market"] if scaleup["proof_refresh_active"] else "inactive",
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_market"] and scaleup["proof_refresh_market"] == scaleup["market"]),
            "scale-up proof freshness market does not match cutover market",
        ),
    ]
    dispatch_roundtrip_required = _dispatch_roundtrip_required(thresholds)
    scaleup_dispatch_active = bool(
        dispatch_roundtrip_required
        or scaleup["dispatch_roundtrip_required"]
        or scaleup["dispatch_roundtrip_provided"]
    )
    broker_dispatch_active = bool(dispatch_roundtrip_required or broker["dispatch_roundtrip_provided"])
    scaleup_route_active = _route_dispatch_roundtrip_active(dispatch_roundtrip_required, scaleup)
    broker_route_active = _route_dispatch_roundtrip_active(dispatch_roundtrip_required, broker)
    if dispatch_roundtrip_required:
        checks.extend(
            [
                _check(
                    "scaleup_dispatch_roundtrip_provided",
                    scaleup["dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(scaleup["dispatch_roundtrip_provided"]),
                    "cutover requires scale-up proof carrying dry-run dispatch round-trip evidence",
                ),
                _check(
                    "broker_dispatch_roundtrip_provided",
                    broker["dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(broker["dispatch_roundtrip_provided"]),
                    "cutover requires broker readiness with dry-run dispatch round-trip proof",
                ),
                _check(
                    "scaleup_route_dispatch_roundtrip_provided",
                    scaleup["route_dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(scaleup["route_dispatch_roundtrip_provided"]),
                    "cutover requires scale-up proof carrying dispatch route proof",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_provided",
                    broker["route_dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(broker["route_dispatch_roundtrip_provided"]),
                    "cutover requires broker readiness with dispatch route proof",
                ),
            ]
        )
    if scaleup_dispatch_active:
        checks.extend(_dispatch_roundtrip_checks("scaleup", scaleup, scaleup, target_mode))
    if broker_dispatch_active:
        checks.extend(_dispatch_roundtrip_checks("broker", broker, scaleup, target_mode))
    if scaleup_route_active:
        checks.extend(_route_dispatch_roundtrip_checks("scaleup", scaleup, scaleup, target_mode))
    if broker_route_active:
        checks.extend(_route_dispatch_roundtrip_checks("broker", broker, scaleup, target_mode))
    if scaleup_dispatch_active and broker_dispatch_active:
        checks.append(
            _check(
                "dispatch_roundtrip_batch_matches",
                broker["dispatch_roundtrip_batch_id"],
                "==",
                scaleup["dispatch_roundtrip_batch_id"],
                bool(
                    broker["dispatch_roundtrip_batch_id"]
                    and scaleup["dispatch_roundtrip_batch_id"]
                    and broker["dispatch_roundtrip_batch_id"] == scaleup["dispatch_roundtrip_batch_id"]
                ),
                "scale-up and broker readiness dispatch round-trip batches differ",
            )
        )
    if scaleup_route_active and broker_route_active:
        checks.append(
            _check(
                "route_dispatch_roundtrip_batch_matches",
                broker["route_dispatch_roundtrip_batch_id"],
                "==",
                scaleup["route_dispatch_roundtrip_batch_id"],
                bool(
                    broker["route_dispatch_roundtrip_batch_id"]
                    and scaleup["route_dispatch_roundtrip_batch_id"]
                    and broker["route_dispatch_roundtrip_batch_id"] == scaleup["route_dispatch_roundtrip_batch_id"]
                ),
                "scale-up and broker readiness route proof batches differ",
            )
        )
    resume_active = bool(thresholds.require_resume_gate or broker["resume_gate_provided"])
    if thresholds.require_resume_gate:
        checks.append(
            _check(
                "broker_resume_gate_provided",
                broker["resume_gate_provided"],
                "is",
                True,
                bool(broker["resume_gate_provided"]),
                "broker resume-gate authorization is required but missing",
            )
        )
    if resume_active:
        checks.extend(
            [
                _check(
                    "broker_resume_gate_ready",
                    broker["resume_gate_ready"],
                    "is",
                    True,
                    bool(broker["resume_gate_ready"]),
                    "broker resume-gate authorization is not ready",
                ),
                _check(
                    "broker_resume_strategy_matches",
                    broker["resume_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(broker["resume_strategy"] and broker["resume_strategy"] == scaleup["strategy"]),
                    "broker resume-gate strategy does not match cutover strategy",
                ),
                _check(
                    "broker_resume_market_matches",
                    broker["resume_market"],
                    "==",
                    scaleup["market"],
                    bool(broker["resume_market"] and broker["resume_market"] == scaleup["market"]),
                    "broker resume-gate market does not match cutover market",
                ),
                _check(
                    "broker_resume_proof_refresh_ready",
                    broker["resume_proof_refresh_ready"],
                    "is",
                    True,
                    bool(broker["resume_proof_refresh_ready"]),
                    "broker resume-gate proof freshness is not ready",
                ),
                _check(
                    "broker_resume_proof_refresh_strategy_matches",
                    broker["resume_proof_refresh_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(
                        broker["resume_proof_refresh_strategy"]
                        and broker["resume_proof_refresh_strategy"] == scaleup["strategy"]
                    ),
                    "broker resume-gate proof strategy does not match cutover strategy",
                ),
                _check(
                    "broker_resume_proof_refresh_market_matches",
                    broker["resume_proof_refresh_market"],
                    "==",
                    scaleup["market"],
                    bool(
                        broker["resume_proof_refresh_market"]
                        and broker["resume_proof_refresh_market"] == scaleup["market"]
                    ),
                    "broker resume-gate proof market does not match cutover market",
                ),
            ]
        )
    operator_approval_required = _operator_approval_required(thresholds)
    operator_identity_required = _operator_identity_ack_required(thresholds)
    operator_limits_required = _operator_limits_ack_required(thresholds)
    checks.extend(
        [
            _check(
                "operator_approved",
                operator["approved"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["approved"]) or not operator_approval_required,
                "operator cutover approval is missing or false",
            ),
            _check(
                "operator_identity_ack",
                operator["identity_ack"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["identity_ack"]) or not operator_identity_required,
                "operator review did not acknowledge cutover strategy and market",
            ),
            _check(
                "operator_limits_ack",
                operator["limits_ack"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["limits_ack"]) or not operator_limits_required,
                "operator review did not acknowledge scale-up order and notional limits",
            ),
        ]
    )
    return pd.DataFrame(checks)


def _dispatch_roundtrip_checks(
    prefix: str,
    source: dict[str, Any],
    scaleup: dict[str, Any],
    target_mode: str,
) -> list[dict[str, object]]:
    label = prefix.replace("_", " ")
    return [
        _check(
            f"{prefix}_dispatch_roundtrip_ready",
            source["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(source["dispatch_roundtrip_ready"]),
            f"{label} dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_target_mode_matches",
            source["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(source["dispatch_roundtrip_target_mode"] and source["dispatch_roundtrip_target_mode"] == target_mode),
            f"{label} dispatch round-trip target mode does not match cutover target",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_strategy_matches",
            source["dispatch_roundtrip_strategy"],
            "==",
            scaleup["strategy"],
            bool(
                source["dispatch_roundtrip_strategy"]
                and scaleup["strategy"]
                and source["dispatch_roundtrip_strategy"] == scaleup["strategy"]
            ),
            f"{label} dispatch round-trip strategy does not match cutover strategy",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_market_matches",
            source["dispatch_roundtrip_market"],
            "==",
            scaleup["market"],
            bool(
                source["dispatch_roundtrip_market"]
                and scaleup["market"]
                and source["dispatch_roundtrip_market"] == scaleup["market"]
            ),
            f"{label} dispatch round-trip market does not match cutover market",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_scenario_matches",
            source["dispatch_roundtrip_scenario_key"],
            "==",
            scaleup["scenario_key"],
            bool(
                source["dispatch_roundtrip_scenario_key"]
                and scaleup["scenario_key"]
                and source["dispatch_roundtrip_scenario_key"] == scaleup["scenario_key"]
            ),
            f"{label} dispatch round-trip scenario does not match cutover scenario",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_missing_request_acks",
            source["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_missing_request_acks"]) <= 0,
            f"{label} dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_rejected_orders",
            source["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(source["dispatch_roundtrip_rejected_orders"]) <= 0,
            f"{label} dispatch round-trip has rejected orders",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_unmatched_acks",
            source["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_unmatched_acks"]) <= 0,
            f"{label} dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_failed_checks",
            source["dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_failed_checks"]) <= 0,
            f"{label} dispatch round-trip has failed component checks",
        ),
        _check(
            f"{prefix}_route_enable_dispatch_roundtrip_failed_checks",
            source["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(source["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            f"{label} route-enable dispatch round-trip has failed component checks",
        ),
    ]


def _route_dispatch_roundtrip_checks(
    prefix: str,
    source: dict[str, Any],
    scaleup: dict[str, Any],
    target_mode: str,
) -> list[dict[str, object]]:
    label = prefix.replace("_", " ")
    return [
        _check(
            f"{prefix}_route_dispatch_roundtrip_ready",
            source["route_dispatch_roundtrip_ready"],
            "is",
            True,
            bool(source["route_dispatch_roundtrip_ready"]),
            f"{label} dispatch route proof is not ready",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_target_mode_matches",
            source["route_dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(
                source["route_dispatch_roundtrip_target_mode"]
                and source["route_dispatch_roundtrip_target_mode"] == target_mode
            ),
            f"{label} dispatch route proof target mode does not match cutover target",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_strategy_matches",
            source["route_dispatch_roundtrip_strategy"],
            "==",
            scaleup["strategy"],
            bool(
                source["route_dispatch_roundtrip_strategy"]
                and scaleup["strategy"]
                and source["route_dispatch_roundtrip_strategy"] == scaleup["strategy"]
            ),
            f"{label} dispatch route proof strategy does not match cutover strategy",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_market_matches",
            source["route_dispatch_roundtrip_market"],
            "==",
            scaleup["market"],
            bool(
                source["route_dispatch_roundtrip_market"]
                and scaleup["market"]
                and source["route_dispatch_roundtrip_market"] == scaleup["market"]
            ),
            f"{label} dispatch route proof market does not match cutover market",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_scenario_matches",
            source["route_dispatch_roundtrip_scenario_key"],
            "==",
            scaleup["scenario_key"],
            bool(
                source["route_dispatch_roundtrip_scenario_key"]
                and scaleup["scenario_key"]
                and source["route_dispatch_roundtrip_scenario_key"] == scaleup["scenario_key"]
            ),
            f"{label} dispatch route proof scenario does not match cutover scenario",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_batch_id_provided",
            source["route_dispatch_roundtrip_batch_id"],
            "is not",
            "",
            bool(source["route_dispatch_roundtrip_batch_id"]),
            f"{label} dispatch route proof batch id is missing",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_request_count_matches",
            f"{source['route_dispatch_roundtrip_requests']}/{source['route_dispatch_roundtrip_acked_orders']}",
            "==",
            f"{source['dispatch_roundtrip_requests']}/{source['dispatch_roundtrip_acked_orders']}",
            (
                int(source["route_dispatch_roundtrip_requests"]) == int(source["dispatch_roundtrip_requests"])
                and int(source["route_dispatch_roundtrip_acked_orders"])
                == int(source["dispatch_roundtrip_acked_orders"])
            ),
            f"{label} dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_missing_request_acks",
            source["route_dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_missing_request_acks"]) <= 0,
            f"{label} dispatch route proof has missing request acknowledgements",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_rejected_orders",
            source["route_dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_rejected_orders"]) <= 0,
            f"{label} dispatch route proof has rejected orders",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_unmatched_acks",
            source["route_dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_unmatched_acks"]) <= 0,
            f"{label} dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _authorization(
    scaleup: dict[str, Any],
    broker: dict[str, Any],
    runtime: dict[str, Any],
    operator: dict[str, Any],
    thresholds: CutoverGateThresholds,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    ready = bool(checks["passed"].astype(bool).all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": scaleup["target_mode"],
                "strategy": scaleup["strategy"],
                "market": scaleup["market"],
                "scenario_key": scaleup["scenario_key"],
                "adapter": scaleup["adapter"],
                "max_orders_per_session": scaleup["max_orders_per_session"],
                "max_notional_per_session": scaleup["max_notional_per_session"],
                "stop_loss": scaleup["stop_loss"],
                "proof_refresh_provided": scaleup["proof_refresh_provided"],
                "proof_refresh_ready": scaleup["proof_refresh_ready"],
                "proof_refresh_strategy": scaleup["proof_refresh_strategy"],
                "proof_refresh_market": scaleup["proof_refresh_market"],
                "proof_refresh_mixed_identity": scaleup["proof_refresh_mixed_identity"],
                "proof_source": scaleup["proof_source"],
                "scaleup_broker_schema_status": scaleup["broker_schema_status"],
                "scaleup_broker_schema_reviewed": scaleup["broker_schema_reviewed"],
                "scaleup_broker_schema_review_mode": scaleup["broker_schema_review_mode"],
                "broker_readiness_ready": broker["ready"],
                "broker_schema_status": broker["schema_status"],
                "broker_schema_reviewed": broker["schema_reviewed"],
                "broker_schema_review_mode": broker["schema_review_mode"],
                "broker_recommendation": broker["recommendation"],
                "runtime_session_provided": runtime["provided"],
                "runtime_session_ready": runtime["ready"],
                "runtime_guard_action": runtime["guard_action"],
                "runtime_guard_halted": runtime["halted"],
                "runtime_strategy": runtime["strategy"],
                "runtime_market": runtime["market"],
                "runtime_target_mode": runtime["target_mode"],
                "broker_resume_gate_provided": broker["resume_gate_provided"],
                "broker_resume_gate_ready": broker["resume_gate_ready"],
                "broker_resume_strategy": broker["resume_strategy"],
                "broker_resume_market": broker["resume_market"],
                "broker_resume_proof_refresh_ready": broker["resume_proof_refresh_ready"],
                "broker_resume_proof_refresh_strategy": broker["resume_proof_refresh_strategy"],
                "broker_resume_proof_refresh_market": broker["resume_proof_refresh_market"],
                "scaleup_dispatch_roundtrip_required": scaleup["dispatch_roundtrip_required"],
                "scaleup_dispatch_roundtrip_provided": scaleup["dispatch_roundtrip_provided"],
                "scaleup_dispatch_roundtrip_ready": scaleup["dispatch_roundtrip_ready"],
                "scaleup_dispatch_roundtrip_target_mode": scaleup["dispatch_roundtrip_target_mode"],
                "scaleup_dispatch_roundtrip_strategy": scaleup["dispatch_roundtrip_strategy"],
                "scaleup_dispatch_roundtrip_market": scaleup["dispatch_roundtrip_market"],
                "scaleup_dispatch_roundtrip_scenario_key": scaleup["dispatch_roundtrip_scenario_key"],
                "scaleup_dispatch_roundtrip_batch_id": scaleup["dispatch_roundtrip_batch_id"],
                "scaleup_dispatch_roundtrip_requests": scaleup["dispatch_roundtrip_requests"],
                "scaleup_dispatch_roundtrip_acked_orders": scaleup["dispatch_roundtrip_acked_orders"],
                "scaleup_dispatch_roundtrip_missing_request_acks": scaleup[
                    "dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_dispatch_roundtrip_rejected_orders": scaleup["dispatch_roundtrip_rejected_orders"],
                "scaleup_dispatch_roundtrip_unmatched_acks": scaleup["dispatch_roundtrip_unmatched_acks"],
                "scaleup_dispatch_roundtrip_failed_checks": scaleup["dispatch_roundtrip_failed_checks"],
                "scaleup_route_enable_dispatch_roundtrip_failed_checks": scaleup[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "scaleup_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_active(
                    _dispatch_roundtrip_required(thresholds),
                    scaleup,
                ),
                "scaleup_route_dispatch_roundtrip_provided": scaleup["route_dispatch_roundtrip_provided"],
                "scaleup_route_dispatch_roundtrip_ready": scaleup["route_dispatch_roundtrip_ready"],
                "scaleup_route_dispatch_roundtrip_target_mode": scaleup["route_dispatch_roundtrip_target_mode"],
                "scaleup_route_dispatch_roundtrip_strategy": scaleup["route_dispatch_roundtrip_strategy"],
                "scaleup_route_dispatch_roundtrip_market": scaleup["route_dispatch_roundtrip_market"],
                "scaleup_route_dispatch_roundtrip_scenario_key": scaleup["route_dispatch_roundtrip_scenario_key"],
                "scaleup_route_dispatch_roundtrip_batch_id": scaleup["route_dispatch_roundtrip_batch_id"],
                "scaleup_route_dispatch_roundtrip_requests": scaleup["route_dispatch_roundtrip_requests"],
                "scaleup_route_dispatch_roundtrip_acked_orders": scaleup["route_dispatch_roundtrip_acked_orders"],
                "scaleup_route_dispatch_roundtrip_missing_request_acks": scaleup[
                    "route_dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_route_dispatch_roundtrip_rejected_orders": scaleup["route_dispatch_roundtrip_rejected_orders"],
                "scaleup_route_dispatch_roundtrip_unmatched_acks": scaleup["route_dispatch_roundtrip_unmatched_acks"],
                "broker_dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "broker_dispatch_roundtrip_provided": broker["dispatch_roundtrip_provided"],
                "broker_dispatch_roundtrip_ready": broker["dispatch_roundtrip_ready"],
                "broker_dispatch_roundtrip_target_mode": broker["dispatch_roundtrip_target_mode"],
                "broker_dispatch_roundtrip_strategy": broker["dispatch_roundtrip_strategy"],
                "broker_dispatch_roundtrip_market": broker["dispatch_roundtrip_market"],
                "broker_dispatch_roundtrip_scenario_key": broker["dispatch_roundtrip_scenario_key"],
                "broker_dispatch_roundtrip_batch_id": broker["dispatch_roundtrip_batch_id"],
                "broker_dispatch_roundtrip_requests": broker["dispatch_roundtrip_requests"],
                "broker_dispatch_roundtrip_acked_orders": broker["dispatch_roundtrip_acked_orders"],
                "broker_dispatch_roundtrip_missing_request_acks": broker[
                    "dispatch_roundtrip_missing_request_acks"
                ],
                "broker_dispatch_roundtrip_rejected_orders": broker["dispatch_roundtrip_rejected_orders"],
                "broker_dispatch_roundtrip_unmatched_acks": broker["dispatch_roundtrip_unmatched_acks"],
                "broker_dispatch_roundtrip_failed_checks": broker["dispatch_roundtrip_failed_checks"],
                "broker_route_enable_dispatch_roundtrip_failed_checks": broker[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "broker_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_active(
                    _dispatch_roundtrip_required(thresholds),
                    broker,
                ),
                "broker_route_dispatch_roundtrip_provided": broker["route_dispatch_roundtrip_provided"],
                "broker_route_dispatch_roundtrip_ready": broker["route_dispatch_roundtrip_ready"],
                "broker_route_dispatch_roundtrip_target_mode": broker["route_dispatch_roundtrip_target_mode"],
                "broker_route_dispatch_roundtrip_strategy": broker["route_dispatch_roundtrip_strategy"],
                "broker_route_dispatch_roundtrip_market": broker["route_dispatch_roundtrip_market"],
                "broker_route_dispatch_roundtrip_scenario_key": broker["route_dispatch_roundtrip_scenario_key"],
                "broker_route_dispatch_roundtrip_batch_id": broker["route_dispatch_roundtrip_batch_id"],
                "broker_route_dispatch_roundtrip_requests": broker["route_dispatch_roundtrip_requests"],
                "broker_route_dispatch_roundtrip_acked_orders": broker["route_dispatch_roundtrip_acked_orders"],
                "broker_route_dispatch_roundtrip_missing_request_acks": broker[
                    "route_dispatch_roundtrip_missing_request_acks"
                ],
                "broker_route_dispatch_roundtrip_rejected_orders": broker["route_dispatch_roundtrip_rejected_orders"],
                "broker_route_dispatch_roundtrip_unmatched_acks": broker["route_dispatch_roundtrip_unmatched_acks"],
                "operator_review_provided": operator["provided"],
                "operator_approval_required": _operator_approval_required(thresholds),
                "operator_identity_ack_required": _operator_identity_ack_required(thresholds),
                "operator_limits_ack_required": _operator_limits_ack_required(thresholds),
                "operator_approved": operator["approved"],
                "operator_strategy": operator["strategy"],
                "operator_market": operator["market"],
                "operator_limits_ack": operator["limits_ack"],
            }
        ]
    )


def _summary(authorization: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(authorization["target_mode"]),
                "strategy": str(authorization["strategy"]),
                "market": str(authorization["market"]),
                "scenario_key": str(authorization["scenario_key"]),
                "adapter": str(authorization["adapter"]),
                "max_orders_per_session": int(authorization["max_orders_per_session"]),
                "max_notional_per_session": float(authorization["max_notional_per_session"]),
                "proof_refresh_ready": _to_bool(authorization["proof_refresh_ready"]),
                "proof_refresh_strategy": str(authorization["proof_refresh_strategy"]),
                "proof_refresh_market": str(authorization["proof_refresh_market"]),
                "scaleup_broker_schema_status": str(authorization["scaleup_broker_schema_status"]),
                "scaleup_broker_schema_reviewed": _to_bool(authorization["scaleup_broker_schema_reviewed"]),
                "scaleup_broker_schema_review_mode": str(authorization["scaleup_broker_schema_review_mode"]),
                "broker_readiness_ready": _to_bool(authorization["broker_readiness_ready"]),
                "broker_schema_status": str(authorization["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(authorization["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(authorization["broker_schema_review_mode"]),
                "runtime_session_ready": _to_bool(authorization["runtime_session_ready"]),
                "runtime_guard_action": str(authorization["runtime_guard_action"]),
                "runtime_guard_halted": _to_bool(authorization["runtime_guard_halted"]),
                "broker_resume_gate_provided": _to_bool(authorization["broker_resume_gate_provided"]),
                "broker_resume_gate_ready": _to_bool(authorization["broker_resume_gate_ready"]),
                "broker_resume_proof_refresh_ready": _to_bool(
                    authorization["broker_resume_proof_refresh_ready"]
                ),
                "scaleup_dispatch_roundtrip_required": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_required"]
                ),
                "scaleup_dispatch_roundtrip_provided": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_provided"]
                ),
                "scaleup_dispatch_roundtrip_ready": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_ready"]
                ),
                "broker_dispatch_roundtrip_required": _to_bool(
                    authorization["broker_dispatch_roundtrip_required"]
                ),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    authorization["broker_dispatch_roundtrip_provided"]
                ),
                "broker_dispatch_roundtrip_ready": _to_bool(
                    authorization["broker_dispatch_roundtrip_ready"]
                ),
                "broker_dispatch_roundtrip_batch_id": str(
                    authorization["broker_dispatch_roundtrip_batch_id"]
                ),
                "broker_dispatch_roundtrip_requests": int(
                    authorization["broker_dispatch_roundtrip_requests"]
                ),
                "broker_dispatch_roundtrip_acked_orders": int(
                    authorization["broker_dispatch_roundtrip_acked_orders"]
                ),
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    authorization["broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_dispatch_roundtrip_rejected_orders": int(
                    authorization["broker_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    authorization["broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "scaleup_dispatch_roundtrip_failed_checks": int(
                    authorization["scaleup_dispatch_roundtrip_failed_checks"]
                ),
                "broker_dispatch_roundtrip_failed_checks": int(
                    authorization["broker_dispatch_roundtrip_failed_checks"]
                ),
                "scaleup_route_enable_dispatch_roundtrip_failed_checks": int(
                    authorization["scaleup_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    authorization["broker_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "scaleup_route_dispatch_roundtrip_required": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_required"]
                ),
                "scaleup_route_dispatch_roundtrip_provided": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_provided"]
                ),
                "scaleup_route_dispatch_roundtrip_ready": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_ready"]
                ),
                "scaleup_route_dispatch_roundtrip_batch_id": str(
                    authorization["scaleup_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_required": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_required"]
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_provided"]
                ),
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_ready"]
                ),
                "broker_route_dispatch_roundtrip_batch_id": str(
                    authorization["broker_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_requests": int(
                    authorization["broker_route_dispatch_roundtrip_requests"]
                ),
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    authorization["broker_route_dispatch_roundtrip_acked_orders"]
                ),
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    authorization["broker_route_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    authorization["broker_route_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    authorization["broker_route_dispatch_roundtrip_unmatched_acks"]
                ),
                "operator_review_provided": _to_bool(authorization["operator_review_provided"]),
                "operator_approval_required": _to_bool(authorization["operator_approval_required"]),
                "operator_identity_ack_required": _to_bool(
                    authorization["operator_identity_ack_required"]
                ),
                "operator_limits_ack_required": _to_bool(authorization["operator_limits_ack_required"]),
                "failed_checks": failed,
                "recommendation": "allow_live_dryrun_cutover" if ready else "keep_cutover_disabled",
            }
        ]
    )


def _config(
    authorization: pd.Series,
    thresholds: CutoverGateThresholds,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(authorization["ready"]),
        "target_mode": str(authorization["target_mode"]),
        "strategy": str(authorization["strategy"]),
        "market": str(authorization["market"]),
        "scenario_key": str(authorization["scenario_key"]),
        "adapter": str(authorization["adapter"]),
        "limits": {
            "max_orders_per_session": int(authorization["max_orders_per_session"]),
            "max_notional_per_session": float(authorization["max_notional_per_session"]),
            "stop_loss": _jsonable(authorization["stop_loss"]),
        },
        "proof_freshness": {
            "provided": _to_bool(authorization["proof_refresh_provided"]),
            "ready": _to_bool(authorization["proof_refresh_ready"]),
            "strategy": str(authorization["proof_refresh_strategy"]),
            "market": str(authorization["proof_refresh_market"]),
            "mixed_identity": _to_bool(authorization["proof_refresh_mixed_identity"]),
            "proof_source": str(authorization["proof_source"]),
        },
        "scaleup_dispatch_roundtrip": {
            "required": _to_bool(authorization["scaleup_dispatch_roundtrip_required"]),
            "provided": _to_bool(authorization["scaleup_dispatch_roundtrip_provided"]),
            "ready": _to_bool(authorization["scaleup_dispatch_roundtrip_ready"]),
            "target_mode": str(authorization["scaleup_dispatch_roundtrip_target_mode"]),
            "strategy": str(authorization["scaleup_dispatch_roundtrip_strategy"]),
            "market": str(authorization["scaleup_dispatch_roundtrip_market"]),
            "scenario_key": str(authorization["scaleup_dispatch_roundtrip_scenario_key"]),
            "dispatch_batch_id": str(authorization["scaleup_dispatch_roundtrip_batch_id"]),
            "requests": int(authorization["scaleup_dispatch_roundtrip_requests"]),
            "acked_orders": int(authorization["scaleup_dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(authorization["scaleup_dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(authorization["scaleup_dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(authorization["scaleup_dispatch_roundtrip_unmatched_acks"]),
            "failed_checks": int(authorization["scaleup_dispatch_roundtrip_failed_checks"]),
            "route_enable_dispatch_roundtrip": {
                "failed_checks": int(authorization["scaleup_route_enable_dispatch_roundtrip_failed_checks"]),
            },
            "route_proof": {
                "required": _to_bool(authorization["scaleup_route_dispatch_roundtrip_required"]),
                "provided": _to_bool(authorization["scaleup_route_dispatch_roundtrip_provided"]),
                "ready": _to_bool(authorization["scaleup_route_dispatch_roundtrip_ready"]),
                "target_mode": str(authorization["scaleup_route_dispatch_roundtrip_target_mode"]),
                "strategy": str(authorization["scaleup_route_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_route_dispatch_roundtrip_market"]),
                "scenario_key": str(authorization["scaleup_route_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(authorization["scaleup_route_dispatch_roundtrip_batch_id"]),
                "requests": int(authorization["scaleup_route_dispatch_roundtrip_requests"]),
                "acked_orders": int(authorization["scaleup_route_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(authorization["scaleup_route_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(authorization["scaleup_route_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(authorization["scaleup_route_dispatch_roundtrip_unmatched_acks"]),
            },
        },
        "broker_readiness": {
            "ready": _to_bool(authorization["broker_readiness_ready"]),
            "adapter_schema_status": str(authorization["broker_schema_status"]),
            "schema_reviewed": _to_bool(authorization["broker_schema_reviewed"]),
            "schema_review_mode": str(authorization["broker_schema_review_mode"]),
            "recommendation": str(authorization["broker_recommendation"]),
            "resume_gate": {
                "provided": _to_bool(authorization["broker_resume_gate_provided"]),
                "ready": _to_bool(authorization["broker_resume_gate_ready"]),
                "strategy": str(authorization["broker_resume_strategy"]),
                "market": str(authorization["broker_resume_market"]),
                "proof_refresh_ready": _to_bool(
                    authorization["broker_resume_proof_refresh_ready"]
                ),
                "proof_refresh_strategy": str(authorization["broker_resume_proof_refresh_strategy"]),
                "proof_refresh_market": str(authorization["broker_resume_proof_refresh_market"]),
            },
            "dispatch_roundtrip": {
                "required": _to_bool(authorization["broker_dispatch_roundtrip_required"]),
                "provided": _to_bool(authorization["broker_dispatch_roundtrip_provided"]),
                "ready": _to_bool(authorization["broker_dispatch_roundtrip_ready"]),
                "target_mode": str(authorization["broker_dispatch_roundtrip_target_mode"]),
                "strategy": str(authorization["broker_dispatch_roundtrip_strategy"]),
                "market": str(authorization["broker_dispatch_roundtrip_market"]),
                "scenario_key": str(authorization["broker_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(authorization["broker_dispatch_roundtrip_batch_id"]),
                "requests": int(authorization["broker_dispatch_roundtrip_requests"]),
                "acked_orders": int(authorization["broker_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(authorization["broker_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(authorization["broker_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(authorization["broker_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": int(authorization["broker_dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip": {
                    "failed_checks": int(authorization["broker_route_enable_dispatch_roundtrip_failed_checks"]),
                },
                "route_proof": {
                    "required": _to_bool(authorization["broker_route_dispatch_roundtrip_required"]),
                    "provided": _to_bool(authorization["broker_route_dispatch_roundtrip_provided"]),
                    "ready": _to_bool(authorization["broker_route_dispatch_roundtrip_ready"]),
                    "target_mode": str(authorization["broker_route_dispatch_roundtrip_target_mode"]),
                    "strategy": str(authorization["broker_route_dispatch_roundtrip_strategy"]),
                    "market": str(authorization["broker_route_dispatch_roundtrip_market"]),
                    "scenario_key": str(authorization["broker_route_dispatch_roundtrip_scenario_key"]),
                    "dispatch_batch_id": str(authorization["broker_route_dispatch_roundtrip_batch_id"]),
                    "requests": int(authorization["broker_route_dispatch_roundtrip_requests"]),
                    "acked_orders": int(authorization["broker_route_dispatch_roundtrip_acked_orders"]),
                    "missing_request_acks": int(
                        authorization["broker_route_dispatch_roundtrip_missing_request_acks"]
                    ),
                    "rejected_orders": int(authorization["broker_route_dispatch_roundtrip_rejected_orders"]),
                    "unmatched_acks": int(authorization["broker_route_dispatch_roundtrip_unmatched_acks"]),
                },
            },
        },
        "runtime_session": {
            "provided": _to_bool(authorization["runtime_session_provided"]),
            "ready": _to_bool(authorization["runtime_session_ready"]),
            "guard_action": str(authorization["runtime_guard_action"]),
            "guard_halted": _to_bool(authorization["runtime_guard_halted"]),
            "target_mode": str(authorization["runtime_target_mode"]),
            "strategy": str(authorization["runtime_strategy"]),
            "market": str(authorization["runtime_market"]),
        },
        "operator_review": {
            "provided": _to_bool(authorization["operator_review_provided"]),
            "approval_required": _to_bool(authorization["operator_approval_required"]),
            "identity_ack_required": _to_bool(authorization["operator_identity_ack_required"]),
            "limits_ack_required": _to_bool(authorization["operator_limits_ack_required"]),
            "approved": _to_bool(authorization["operator_approved"]),
            "strategy": str(authorization["operator_strategy"]),
            "market": str(authorization["operator_market"]),
            "limits_ack": _to_bool(authorization["operator_limits_ack"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _scaleup_state(row: pd.Series, config: dict[str, Any], checks: pd.DataFrame) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    identity = config.get("identity", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route = dispatch.get("route_proof", {}) or {}
    strategy = _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""), identity.get("strategy", "")))
    market = _identity_key(_first_text(row.get("market", ""), config.get("market", ""), identity.get("market", "")))
    proof_strategy = _strategy_key(_first_text(proof.get("strategy", ""), row.get("proof_refresh_strategy", "")))
    proof_market = _identity_key(_first_text(proof.get("market", ""), row.get("proof_refresh_market", "")))
    proof_active = _proof_active(row, proof)
    return {
        "ready": _to_bool(row.get("ready", config.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": strategy,
        "market": market,
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "failed_checks": _failed_scaleup_checks(row, checks),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "proof_refresh_active": proof_active,
        "proof_refresh_provided": _to_bool(proof.get("provided", row.get("proof_refresh_provided", False))),
        "proof_refresh_ready": _to_bool(proof.get("ready", row.get("proof_refresh_ready", False))),
        "proof_refresh_strategy": proof_strategy or strategy,
        "proof_refresh_market": proof_market or market,
        "proof_refresh_mixed_identity": _to_bool(
            proof.get("mixed_identity", row.get("proof_refresh_mixed_identity", False))
        ),
        "proof_source": _first_text(proof.get("proof_source", ""), row.get("proof_source", "")),
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
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number_from(
                route_enable,
                "failed_checks",
                _number(row, "broker_route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
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


def _broker_state(summary: pd.DataFrame) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "provided": not summary.empty,
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "schema_status": _first_text(row.get("adapter_schema_status", "")),
        "schema_reviewed": _to_bool(row.get("schema_reviewed", False)),
        "schema_review_mode": _first_text(row.get("schema_review_mode", "")),
        "recommendation": _first_text(row.get("recommendation", "")),
        "runtime_session_provided": _to_bool(row.get("runtime_session_provided", False)),
        "runtime_session_ready": _to_bool(row.get("runtime_session_ready", False)),
        "runtime_guard_action": _identity_key(row.get("runtime_guard_action", "")),
        "runtime_guard_halted": _to_bool(row.get("runtime_guard_halted", False)),
        "runtime_target_mode": _identity_key(row.get("runtime_target_mode", "")),
        "runtime_strategy": _strategy_key(row.get("runtime_strategy", "")),
        "runtime_market": _identity_key(row.get("runtime_market", "")),
        "resume_gate_provided": _to_bool(row.get("resume_gate_provided", False)),
        "resume_gate_ready": _to_bool(row.get("resume_gate_ready", False)),
        "resume_strategy": _strategy_key(row.get("resume_strategy", "")),
        "resume_market": _identity_key(row.get("resume_market", "")),
        "resume_proof_refresh_ready": _to_bool(row.get("resume_proof_refresh_ready", False)),
        "resume_proof_refresh_strategy": _strategy_key(row.get("resume_proof_refresh_strategy", "")),
        "resume_proof_refresh_market": _identity_key(row.get("resume_proof_refresh_market", "")),
        "dispatch_roundtrip_provided": _to_bool(row.get("dispatch_roundtrip_provided", False)),
        "dispatch_roundtrip_ready": _to_bool(row.get("dispatch_roundtrip_ready", False)),
        "dispatch_roundtrip_target_mode": _identity_key(row.get("dispatch_roundtrip_target_mode", "")),
        "dispatch_roundtrip_strategy": _strategy_key(row.get("dispatch_roundtrip_strategy", "")),
        "dispatch_roundtrip_market": _identity_key(row.get("dispatch_roundtrip_market", "")),
        "dispatch_roundtrip_scenario_key": _first_text(row.get("dispatch_roundtrip_scenario_key", "")),
        "dispatch_roundtrip_batch_id": _first_text(row.get("dispatch_roundtrip_batch_id", "")),
        "dispatch_roundtrip_requests": int(_number(row, "dispatch_roundtrip_requests", 0.0)),
        "dispatch_roundtrip_acked_orders": int(_number(row, "dispatch_roundtrip_acked_orders", 0.0)),
        "dispatch_roundtrip_missing_request_acks": int(
            _number(row, "dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        "dispatch_roundtrip_rejected_orders": int(_number(row, "dispatch_roundtrip_rejected_orders", 0.0)),
        "dispatch_roundtrip_unmatched_acks": int(_number(row, "dispatch_roundtrip_unmatched_acks", 0.0)),
        "dispatch_roundtrip_failed_checks": int(_number(row, "dispatch_roundtrip_failed_checks", 0.0)),
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
        ),
        "route_dispatch_roundtrip_required": _to_bool(row.get("route_dispatch_roundtrip_required", False)),
        "route_dispatch_roundtrip_provided": _to_bool(row.get("route_dispatch_roundtrip_provided", False)),
        "route_dispatch_roundtrip_ready": _to_bool(row.get("route_dispatch_roundtrip_ready", False)),
        "route_dispatch_roundtrip_target_mode": _identity_key(row.get("route_dispatch_roundtrip_target_mode", "")),
        "route_dispatch_roundtrip_strategy": _strategy_key(row.get("route_dispatch_roundtrip_strategy", "")),
        "route_dispatch_roundtrip_market": _identity_key(row.get("route_dispatch_roundtrip_market", "")),
        "route_dispatch_roundtrip_scenario_key": _first_text(row.get("route_dispatch_roundtrip_scenario_key", "")),
        "route_dispatch_roundtrip_batch_id": _first_text(row.get("route_dispatch_roundtrip_batch_id", "")),
        "route_dispatch_roundtrip_requests": int(_number(row, "route_dispatch_roundtrip_requests", 0.0)),
        "route_dispatch_roundtrip_acked_orders": int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0)),
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        "route_dispatch_roundtrip_rejected_orders": int(
            _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0)
        ),
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0)
        ),
    }


def _runtime_state(summary: pd.DataFrame, broker: dict[str, Any]) -> dict[str, Any]:
    if not summary.empty:
        row = summary.iloc[0]
        return {
            "provided": True,
            "ready": _to_bool(row.get("ready", False)),
            "guard_action": _identity_key(row.get("guard_action", "")),
            "halted": _to_bool(row.get("halted", False)),
            "target_mode": _identity_key(row.get("target_mode", "")),
            "strategy": _strategy_key(row.get("strategy", "")),
            "market": _identity_key(row.get("market", "")),
        }
    return {
        "provided": bool(broker["runtime_session_provided"]),
        "ready": bool(broker["runtime_session_ready"]),
        "guard_action": broker["runtime_guard_action"],
        "halted": bool(broker["runtime_guard_halted"]),
        "target_mode": broker["runtime_target_mode"],
        "strategy": broker["runtime_strategy"],
        "market": broker["runtime_market"],
    }


def _operator_state(review: pd.DataFrame, scaleup: dict[str, Any]) -> dict[str, Any]:
    row = review.iloc[-1] if not review.empty else pd.Series(dtype=object)
    strategy = _strategy_key(_first_text(row.get("strategy", ""), row.get("approved_strategy", ""), row.get("ack_strategy", "")))
    market = _identity_key(_first_text(row.get("market", ""), row.get("approved_market", ""), row.get("ack_market", "")))
    limits_ack = _to_bool(row.get("limits_acknowledged", row.get("risk_limits_acknowledged", False)))
    if not limits_ack:
        acknowledged_orders = _number(row, "max_orders_per_session", fallback=None)
        acknowledged_notional = _number(row, "max_notional_per_session", fallback=None)
        limits_ack = (
            acknowledged_orders == float(scaleup["max_orders_per_session"])
            and acknowledged_notional == float(scaleup["max_notional_per_session"])
        )
    return {
        "provided": not review.empty,
        "approved": _operator_approved(row),
        "strategy": strategy,
        "market": market,
        "identity_ack": bool(strategy and market and strategy == scaleup["strategy"] and market == scaleup["market"]),
        "limits_ack": bool(limits_ack),
    }


def _operator_approved(row: pd.Series) -> bool:
    if row.empty:
        return False
    for column in ("approved", "cutover_approved", "allow_cutover"):
        if column in row.index:
            return _to_bool(row[column])
    return False


def _operator_approval_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_approval or thresholds.target_mode == "live_dryrun")


def _operator_identity_ack_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_identity_ack or thresholds.target_mode == "live_dryrun")


def _operator_limits_ack_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_limits_ack or thresholds.target_mode == "live_dryrun")


def _dispatch_roundtrip_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_dispatch_roundtrip_active(dispatch_roundtrip_required: bool, source: dict[str, Any]) -> bool:
    return bool(
        dispatch_roundtrip_required
        or source["route_dispatch_roundtrip_required"]
        or source["route_dispatch_roundtrip_provided"]
    )


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required cutover input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required cutover input is empty: {name}")
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


def _failed_scaleup_checks(row: pd.Series, checks: pd.DataFrame) -> int:
    if "failed_checks" in row.index and not _is_missing(row["failed_checks"]):
        return int(float(row["failed_checks"]))
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _proof_active(row: pd.Series, proof: dict[str, Any]) -> bool:
    return any(
        _to_bool(value)
        for value in (
            proof.get("required", False),
            proof.get("provided", False),
            proof.get("ready", False),
            proof.get("mixed_identity", False),
            row.get("proof_refresh_provided", False),
            row.get("proof_refresh_ready", False),
            row.get("proof_refresh_mixed_identity", False),
        )
    ) or any(
        _object_text(value)
        for value in (
            proof.get("strategy", ""),
            proof.get("market", ""),
            proof.get("proof_source", ""),
            row.get("proof_refresh_strategy", ""),
            row.get("proof_refresh_market", ""),
            row.get("proof_source", ""),
        )
    )


def _validate_thresholds(thresholds: CutoverGateThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_failed_scaleup_checks < 0:
        raise ValueError("max_failed_scaleup_checks must be non-negative")


def _number(row: pd.Series, column: str, fallback: float | None = 0.0) -> float | None:
    if row.empty or column not in row.index:
        return fallback
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return fallback
    return float(value)


def _number_from(mapping: dict[str, Any], key: str, fallback: float | None) -> float:
    value = mapping.get(key, fallback)
    if value is None or _is_missing(value):
        return float(fallback or 0.0)
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
    text = _object_text(value)
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _object_text(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed", "continue"}
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
