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
    require_route_readiness: bool = False
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
    broker_readiness_config_path = _sidecar_path(
        broker,
        "broker_readiness_config.json",
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
    if broker_readiness_config_path is not None:
        inputs["broker_readiness_config"] = broker_readiness_config_path
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
    route_readiness_required = _route_readiness_required(thresholds)
    route_readiness_active = bool(route_readiness_required or scaleup["route_readiness_provided"])
    if route_readiness_required:
        checks.append(
            _check(
                "scaleup_route_readiness_provided",
                scaleup["route_readiness_provided"],
                "is",
                True,
                bool(scaleup["route_readiness_provided"]),
                "cutover requires scale-up proof carrying route-readiness evidence",
            )
        )
    if route_readiness_active:
        checks.extend(
            [
                _check(
                    "scaleup_route_readiness_ready",
                    scaleup["route_readiness_ready"],
                    "is",
                    True,
                    bool(scaleup["route_readiness_ready"]),
                    "scale-up route-readiness evidence is not ready",
                ),
                _check(
                    "scaleup_route_readiness_strategy_matches",
                    scaleup["route_readiness_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup["route_readiness_strategy"]
                        and scaleup["route_readiness_strategy"] == scaleup["strategy"]
                    ),
                    "scale-up route-readiness strategy does not match cutover strategy",
                ),
                _check(
                    "scaleup_route_readiness_market_matches",
                    scaleup["route_readiness_market"],
                    "==",
                    scaleup["market"],
                    bool(scaleup["route_readiness_market"] and scaleup["route_readiness_market"] == scaleup["market"]),
                    "scale-up route-readiness market does not match cutover market",
                ),
            ]
        )
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
    if _shadow_broker_readiness_active(scaleup):
        checks.extend(_shadow_broker_readiness_checks(scaleup))
    if _broker_shadow_broker_readiness_active(scaleup):
        checks.extend(_broker_shadow_broker_readiness_checks(scaleup))
    if _broker_vendor_market_data_batch_active(scaleup):
        checks.extend(_broker_vendor_market_data_batch_checks(scaleup))
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


def _shadow_broker_readiness_active(scaleup: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(scaleup, key_prefix="")


def _shadow_broker_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        scaleup,
        key_prefix="",
        check_prefix="scaleup_shadow_broker",
        label="scale-up shadow broker",
    )


def _broker_shadow_broker_readiness_active(scaleup: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(scaleup, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        scaleup,
        key_prefix="broker_",
        check_prefix="scaleup_broker_shadow_broker",
        label="scale-up broker-readiness shadow broker",
        check_provided=True,
    )


def _shadow_broker_readiness_active_for(scaleup: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(scaleup.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(scaleup[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    scaleup: dict[str, Any],
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
                _to_bool(scaleup[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(scaleup[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(scaleup[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    scaleup[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    scaleup["adapter"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "adapter")]
                        and scaleup[_shadow_broker_key(key_prefix, "adapter")] == scaleup["adapter"]
                    ),
                    f"{label} adapter does not match cutover adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    route_sessions = int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")])
                    == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == scaleup["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")] == scaleup["market"]
                    ),
                    f"{label} route-readiness market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        == scaleup["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == scaleup["market"]
                    ),
                    f"{label} dispatch round-trip market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")])
                    <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == scaleup["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == scaleup["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _broker_vendor_market_data_batch_active(scaleup: dict[str, Any]) -> bool:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_market_data_batch_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "scale-up broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "scale-up broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            scaleup["adapter"],
            bool(vendor["adapter"] and scaleup["adapter"] and vendor["adapter"] == scaleup["adapter"]),
            "scale-up broker-readiness vendor market-data adapter does not match cutover adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            scaleup["market"],
            bool(vendor["market"] and scaleup["market"] and vendor["market"] == scaleup["market"]),
            "scale-up broker-readiness vendor market-data market does not match cutover market",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "scale-up broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "scale-up broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "scale-up broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "scale-up broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "scale-up broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "scale-up broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "scale-up broker-readiness vendor market-data comparison has failed checks",
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
                "scaleup_route_readiness_required": _route_readiness_required(thresholds),
                "scaleup_route_readiness_provided": scaleup["route_readiness_provided"],
                "scaleup_route_readiness_ready": scaleup["route_readiness_ready"],
                "scaleup_route_readiness_strategy": scaleup["route_readiness_strategy"],
                "scaleup_route_readiness_market": scaleup["route_readiness_market"],
                "scaleup_route_readiness_route_ready_pairs": scaleup["route_readiness_route_ready_pairs"],
                "scaleup_route_readiness_gap_pairs": scaleup["route_readiness_gap_pairs"],
                "scaleup_route_readiness_recommendation": scaleup["route_readiness_recommendation"],
                "scaleup_shadow_broker_readiness_sessions": scaleup["shadow_broker_readiness_sessions"],
                "scaleup_shadow_broker_readiness_ready_sessions": scaleup[
                    "shadow_broker_readiness_ready_sessions"
                ],
                "scaleup_shadow_broker_adapter": scaleup["shadow_broker_adapter"],
                "scaleup_shadow_broker_adapter_count": scaleup["shadow_broker_adapter_count"],
                "scaleup_shadow_broker_route_readiness_sessions": scaleup[
                    "shadow_broker_route_readiness_sessions"
                ],
                "scaleup_shadow_broker_route_readiness_ready_sessions": scaleup[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "scaleup_shadow_broker_route_readiness_strategy": scaleup[
                    "shadow_broker_route_readiness_strategy"
                ],
                "scaleup_shadow_broker_route_readiness_market": scaleup[
                    "shadow_broker_route_readiness_market"
                ],
                "scaleup_shadow_broker_route_readiness_gap_pairs": scaleup[
                    "shadow_broker_route_readiness_gap_pairs"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_sessions": scaleup[
                    "shadow_broker_dispatch_roundtrip_sessions"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions": scaleup[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_strategy": scaleup[
                    "shadow_broker_dispatch_roundtrip_strategy"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_market": scaleup[
                    "shadow_broker_dispatch_roundtrip_market"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_scenario_count": scaleup[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks": scaleup[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders": scaleup[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks": scaleup[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_sessions": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_strategy": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_market": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_authorization_fields(scaleup),
                **_broker_vendor_market_data_batch_authorization_fields(scaleup),
                **_vendor_market_data_batch_authorization_fields(scaleup),
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


def _broker_shadow_broker_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    return {
        "scaleup_broker_shadow_broker_readiness_provided": scaleup[
            "broker_shadow_broker_readiness_provided"
        ],
        "scaleup_broker_shadow_broker_readiness_sessions": scaleup[
            "broker_shadow_broker_readiness_sessions"
        ],
        "scaleup_broker_shadow_broker_readiness_ready_sessions": scaleup[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_adapter": scaleup["broker_shadow_broker_adapter"],
        "scaleup_broker_shadow_broker_adapter_count": scaleup["broker_shadow_broker_adapter_count"],
        "scaleup_broker_shadow_broker_route_readiness_sessions": scaleup[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "scaleup_broker_shadow_broker_route_readiness_ready_sessions": scaleup[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_route_readiness_strategy": scaleup[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "scaleup_broker_shadow_broker_route_readiness_market": scaleup[
            "broker_shadow_broker_route_readiness_market"
        ],
        "scaleup_broker_shadow_broker_route_readiness_gap_pairs": scaleup[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_strategy": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_market": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_market": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    vendor = scaleup["vendor_market_data_batch"]
    return {
        "scaleup_vendor_market_data_batch_provided": vendor["provided"],
        "scaleup_vendor_market_data_batch_ready": vendor["ready"],
        "scaleup_vendor_market_data_batch_adapter": vendor["adapter"],
        "scaleup_vendor_market_data_batch_kind": vendor["kind"],
        "scaleup_vendor_market_data_batch_market": vendor["market"],
        "scaleup_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "scaleup_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "scaleup_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "scaleup_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "scaleup_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "scaleup_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "scaleup_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "scaleup_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "scaleup_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "scaleup_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": vendor["provided"],
        f"{field_prefix}_ready": vendor["ready"],
        f"{field_prefix}_adapter": vendor["adapter"],
        f"{field_prefix}_kind": vendor["kind"],
        f"{field_prefix}_market": vendor["market"],
        f"{field_prefix}_dataset_count": vendor["dataset_count"],
        f"{field_prefix}_ready_datasets": vendor["ready_datasets"],
        f"{field_prefix}_failed_datasets": vendor["failed_datasets"],
        f"{field_prefix}_ready_rate": vendor["ready_rate"],
        f"{field_prefix}_unique_source_files": vendor["unique_source_files"],
        f"{field_prefix}_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        f"{field_prefix}_mapping_sources": vendor["mapping_sources"],
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


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
                "scaleup_route_readiness_required": _to_bool(authorization["scaleup_route_readiness_required"]),
                "scaleup_route_readiness_provided": _to_bool(authorization["scaleup_route_readiness_provided"]),
                "scaleup_route_readiness_ready": _to_bool(authorization["scaleup_route_readiness_ready"]),
                "scaleup_route_readiness_strategy": str(authorization["scaleup_route_readiness_strategy"]),
                "scaleup_route_readiness_market": str(authorization["scaleup_route_readiness_market"]),
                "scaleup_route_readiness_route_ready_pairs": int(
                    authorization["scaleup_route_readiness_route_ready_pairs"]
                ),
                "scaleup_route_readiness_gap_pairs": int(authorization["scaleup_route_readiness_gap_pairs"]),
                "scaleup_shadow_broker_readiness_sessions": int(
                    authorization["scaleup_shadow_broker_readiness_sessions"]
                ),
                "scaleup_shadow_broker_readiness_ready_sessions": int(
                    authorization["scaleup_shadow_broker_readiness_ready_sessions"]
                ),
                "scaleup_shadow_broker_adapter": str(authorization["scaleup_shadow_broker_adapter"]),
                "scaleup_shadow_broker_adapter_count": int(
                    authorization["scaleup_shadow_broker_adapter_count"]
                ),
                "scaleup_shadow_broker_route_readiness_sessions": int(
                    authorization["scaleup_shadow_broker_route_readiness_sessions"]
                ),
                "scaleup_shadow_broker_route_readiness_ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_readiness_ready_sessions"]
                ),
                "scaleup_shadow_broker_route_readiness_strategy": str(
                    authorization["scaleup_shadow_broker_route_readiness_strategy"]
                ),
                "scaleup_shadow_broker_route_readiness_market": str(
                    authorization["scaleup_shadow_broker_route_readiness_market"]
                ),
                "scaleup_shadow_broker_route_readiness_gap_pairs": int(
                    authorization["scaleup_shadow_broker_route_readiness_gap_pairs"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_sessions": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_sessions"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_ready_sessions"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_strategy": str(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_strategy"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_market": str(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_market"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_scenario_count": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_sessions"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_strategy": str(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_strategy"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_market": str(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_market"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
                **_broker_shadow_broker_summary_fields(authorization),
                **_broker_vendor_market_data_batch_summary_fields(authorization),
                "scaleup_vendor_market_data_batch_provided": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_provided"]
                ),
                "scaleup_vendor_market_data_batch_ready": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_ready"]
                ),
                "scaleup_vendor_market_data_batch_adapter": str(
                    authorization["scaleup_vendor_market_data_batch_adapter"]
                ),
                "scaleup_vendor_market_data_batch_kind": str(
                    authorization["scaleup_vendor_market_data_batch_kind"]
                ),
                "scaleup_vendor_market_data_batch_market": str(
                    authorization["scaleup_vendor_market_data_batch_market"]
                ),
                "scaleup_vendor_market_data_batch_dataset_count": int(
                    authorization["scaleup_vendor_market_data_batch_dataset_count"]
                ),
                "scaleup_vendor_market_data_batch_ready_datasets": int(
                    authorization["scaleup_vendor_market_data_batch_ready_datasets"]
                ),
                "scaleup_vendor_market_data_batch_failed_datasets": int(
                    authorization["scaleup_vendor_market_data_batch_failed_datasets"]
                ),
                "scaleup_vendor_market_data_batch_ready_rate": _jsonable(
                    authorization["scaleup_vendor_market_data_batch_ready_rate"]
                ),
                "scaleup_vendor_market_data_batch_unique_source_files": int(
                    authorization["scaleup_vendor_market_data_batch_unique_source_files"]
                ),
                "scaleup_vendor_market_data_batch_unique_header_fingerprints": int(
                    authorization["scaleup_vendor_market_data_batch_unique_header_fingerprints"]
                ),
                "scaleup_vendor_market_data_batch_mapping_sources": str(
                    authorization["scaleup_vendor_market_data_batch_mapping_sources"]
                ),
                "scaleup_vendor_market_data_batch_comparison_accepted": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_comparison_accepted"]
                ),
                "scaleup_vendor_market_data_batch_comparison_failed_checks": int(
                    authorization["scaleup_vendor_market_data_batch_comparison_failed_checks"]
                ),
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


def _broker_shadow_broker_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    return {
        "scaleup_broker_shadow_broker_readiness_provided": _to_bool(
            authorization["scaleup_broker_shadow_broker_readiness_provided"]
        ),
        "scaleup_broker_shadow_broker_readiness_sessions": int(
            authorization["scaleup_broker_shadow_broker_readiness_sessions"]
        ),
        "scaleup_broker_shadow_broker_readiness_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_readiness_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_adapter": str(authorization["scaleup_broker_shadow_broker_adapter"]),
        "scaleup_broker_shadow_broker_adapter_count": int(
            authorization["scaleup_broker_shadow_broker_adapter_count"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_strategy": str(
            authorization["scaleup_broker_shadow_broker_route_readiness_strategy"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_market": str(
            authorization["scaleup_broker_shadow_broker_route_readiness_market"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_gap_pairs": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_gap_pairs"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_sessions"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_strategy": str(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_strategy"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_market": str(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_market"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy": str(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_market": str(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_market"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
        ),
    }


def _broker_vendor_market_data_batch_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": _to_bool(authorization[f"{field_prefix}_provided"]),
        f"{field_prefix}_ready": _to_bool(authorization[f"{field_prefix}_ready"]),
        f"{field_prefix}_adapter": str(authorization[f"{field_prefix}_adapter"]),
        f"{field_prefix}_kind": str(authorization[f"{field_prefix}_kind"]),
        f"{field_prefix}_market": str(authorization[f"{field_prefix}_market"]),
        f"{field_prefix}_dataset_count": int(authorization[f"{field_prefix}_dataset_count"]),
        f"{field_prefix}_ready_datasets": int(authorization[f"{field_prefix}_ready_datasets"]),
        f"{field_prefix}_failed_datasets": int(authorization[f"{field_prefix}_failed_datasets"]),
        f"{field_prefix}_ready_rate": _jsonable(authorization[f"{field_prefix}_ready_rate"]),
        f"{field_prefix}_unique_source_files": int(authorization[f"{field_prefix}_unique_source_files"]),
        f"{field_prefix}_unique_header_fingerprints": int(
            authorization[f"{field_prefix}_unique_header_fingerprints"]
        ),
        f"{field_prefix}_mapping_sources": str(authorization[f"{field_prefix}_mapping_sources"]),
        f"{field_prefix}_comparison_accepted": _to_bool(authorization[f"{field_prefix}_comparison_accepted"]),
        f"{field_prefix}_comparison_failed_checks": int(
            authorization[f"{field_prefix}_comparison_failed_checks"]
        ),
    }


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
        "scaleup_route_readiness": {
            "required": _to_bool(authorization["scaleup_route_readiness_required"]),
            "provided": _to_bool(authorization["scaleup_route_readiness_provided"]),
            "ready": _to_bool(authorization["scaleup_route_readiness_ready"]),
            "strategy": str(authorization["scaleup_route_readiness_strategy"]),
            "market": str(authorization["scaleup_route_readiness_market"]),
            "route_ready_pairs": int(authorization["scaleup_route_readiness_route_ready_pairs"]),
            "gap_pairs": int(authorization["scaleup_route_readiness_gap_pairs"]),
            "recommendation": str(authorization["scaleup_route_readiness_recommendation"]),
        },
        "scaleup_shadow_broker_readiness": {
            "provided": int(authorization["scaleup_shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(authorization["scaleup_shadow_broker_readiness_sessions"]),
            "ready_sessions": int(authorization["scaleup_shadow_broker_readiness_ready_sessions"]),
            "adapter": str(authorization["scaleup_shadow_broker_adapter"]),
            "adapter_count": int(authorization["scaleup_shadow_broker_adapter_count"]),
            "route_readiness": {
                "sessions": int(authorization["scaleup_shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(authorization["scaleup_shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(authorization["scaleup_shadow_broker_route_readiness_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(authorization["scaleup_shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(authorization["scaleup_shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "max_unmatched_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "strategy": str(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
            },
        },
        "scaleup_broker_shadow_broker_readiness": _broker_shadow_broker_config(authorization),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(authorization)
        ),
        "scaleup_vendor_market_data_batch": _vendor_market_data_batch_config(authorization),
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


def _broker_shadow_broker_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(authorization["scaleup_broker_shadow_broker_readiness_provided"]),
        "sessions": int(authorization["scaleup_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(authorization["scaleup_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(authorization["scaleup_broker_shadow_broker_adapter"]),
        "adapter_count": int(authorization["scaleup_broker_shadow_broker_adapter_count"]),
        "route_readiness": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_route_readiness_ready_sessions"]
            ),
            "strategy": str(authorization["scaleup_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(authorization["scaleup_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(authorization["scaleup_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
            ),
            "max_missing_request_acks": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
            ),
            "max_unmatched_acks": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
            ),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
            ),
            "market": str(authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
            ),
        },
    }


def _vendor_market_data_batch_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(authorization["scaleup_vendor_market_data_batch_provided"]),
        "ready": _to_bool(authorization["scaleup_vendor_market_data_batch_ready"]),
        "adapter": str(authorization["scaleup_vendor_market_data_batch_adapter"]),
        "kind": str(authorization["scaleup_vendor_market_data_batch_kind"]),
        "market": str(authorization["scaleup_vendor_market_data_batch_market"]),
        "dataset_count": int(authorization["scaleup_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(authorization["scaleup_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(authorization["scaleup_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(authorization["scaleup_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(authorization["scaleup_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            authorization["scaleup_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "mapping_sources": str(authorization["scaleup_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(authorization["scaleup_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(authorization["scaleup_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(authorization["scaleup_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(authorization: pd.Series) -> dict[str, Any]:
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(authorization[f"{field_prefix}_provided"]),
        "ready": _to_bool(authorization[f"{field_prefix}_ready"]),
        "adapter": str(authorization[f"{field_prefix}_adapter"]),
        "kind": str(authorization[f"{field_prefix}_kind"]),
        "market": str(authorization[f"{field_prefix}_market"]),
        "dataset_count": int(authorization[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(authorization[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(authorization[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(authorization[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(authorization[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(authorization[f"{field_prefix}_unique_header_fingerprints"]),
        "mapping_sources": str(authorization[f"{field_prefix}_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(authorization[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(authorization[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(authorization[f"{field_prefix}_datasets_json"]),
    }


def _vendor_market_data_batch_state(
    vendor: dict[str, Any],
    *,
    row: pd.Series | None = None,
    field_prefix: str = "",
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    comparison = vendor.get("comparison", {}) or {}
    datasets = vendor.get("datasets")
    if datasets is None and field_prefix:
        datasets = _json_list(row.get(f"{field_prefix}_datasets_json", "[]"))
    datasets = datasets or []
    row_value = (lambda suffix, default: row.get(f"{field_prefix}_{suffix}", default)) if field_prefix else (
        lambda _suffix, default: default
    )
    return {
        "provided": _to_bool(vendor.get("provided", row_value("provided", False))),
        "ready": _to_bool(vendor.get("ready", row_value("ready", False))),
        "adapter": _identity_key(_first_text(vendor.get("adapter", ""), row_value("adapter", ""))),
        "kind": _first_text(vendor.get("kind", ""), row_value("kind", "")),
        "market": _identity_key(_first_text(vendor.get("market", ""), row_value("market", ""))),
        "dataset_count": int(_number_from(vendor, "dataset_count", _number(row, f"{field_prefix}_dataset_count", 0.0))),
        "ready_datasets": int(
            _number_from(vendor, "ready_datasets", _number(row, f"{field_prefix}_ready_datasets", 0.0))
        ),
        "failed_datasets": int(
            _number_from(vendor, "failed_datasets", _number(row, f"{field_prefix}_failed_datasets", 0.0))
        ),
        "ready_rate": _number_from(vendor, "ready_rate", _number(row, f"{field_prefix}_ready_rate", 0.0)),
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
        "mapping_sources": _first_text(vendor.get("mapping_sources", ""), row_value("mapping_sources", "")),
        "comparison_accepted": _to_bool(comparison.get("accepted", row_value("comparison_accepted", False))),
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
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def _scaleup_state(row: pd.Series, config: dict[str, Any], checks: pd.DataFrame) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    identity = config.get("identity", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    data_readiness_comparison = config.get("data_readiness_comparison", {}) or {}
    vendor_market_data_batch = data_readiness_comparison.get("vendor_market_data_batch", {}) or {}
    route_readiness = config.get("route_readiness", {}) or {}
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_shadow_broker = broker_readiness.get("shadow_broker_readiness", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    broker_vendor_market_data_batch = dispatch.get("vendor_market_data_batch", {}) or {}
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
        "vendor_market_data_batch": _vendor_market_data_batch_state(vendor_market_data_batch),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_state(
            broker_vendor_market_data_batch,
            row=row,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(
            route_readiness.get("ready", row.get("route_readiness_ready", False))
        ),
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
        **_broker_shadow_broker_state_fields(row, broker_shadow_broker),
    }


def _broker_shadow_broker_state_fields(row: pd.Series, shadow_broker: dict[str, Any]) -> dict[str, Any]:
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            shadow_broker.get("provided", row.get("broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("broker_shadow_broker_adapter", ""))
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
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


def _route_readiness_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_route_readiness or thresholds.target_mode == "live_dryrun")


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


def _sidecar_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        direct = candidate / filename
        if direct.exists():
            return direct
        return next(
            (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
            None,
        )
    file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


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
