from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ResumeGateThresholds:
    require_incident_passed: bool = True
    require_scaleup_ready: bool = True
    require_same_scenario: bool = True
    require_same_adapter: bool = True
    require_same_strategy: bool = True
    require_same_market: bool = True
    require_ready_proof_refresh: bool = True
    require_same_proof_refresh_strategy: bool = True
    require_same_proof_refresh_market: bool = True
    require_operator_approval: bool = False
    require_operator_guard_trigger_ack: bool = False
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class ResumeGateReport:
    authorization: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_resume_gate(
    *,
    incident_summary: pd.DataFrame,
    scaleup_summary: pd.DataFrame,
    scaleup_checks: pd.DataFrame | None = None,
    scaleup_config: dict[str, Any] | None = None,
    operator_review: pd.DataFrame | None = None,
    thresholds: ResumeGateThresholds | None = None,
) -> ResumeGateReport:
    thresholds = thresholds or ResumeGateThresholds()
    _validate_thresholds(thresholds)
    incident_summary = _require_nonempty(incident_summary, "incident_summary")
    scaleup_summary = _require_nonempty(scaleup_summary, "scaleup_summary")
    scaleup_checks = pd.DataFrame() if scaleup_checks is None else scaleup_checks.copy().reset_index(drop=True)
    scaleup_config = scaleup_config or {}
    operator_review = pd.DataFrame() if operator_review is None else operator_review.copy().reset_index(drop=True)

    checks = _checks(
        incident_summary.iloc[0],
        scaleup_summary.iloc[0],
        scaleup_checks,
        scaleup_config,
        operator_review,
        thresholds,
    )
    authorization = _authorization(incident_summary.iloc[0], scaleup_summary.iloc[0], scaleup_config, thresholds, checks)
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(_summary(authorization.iloc[0], checks), checks, action_queue)
    config = _config(authorization.iloc[0], scaleup_config, thresholds, checks, action_queue)
    return ResumeGateReport(
        authorization=authorization,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_resume_gate_report(
    *,
    incident_dir: str | Path,
    scaleup_dir: str | Path,
    output_dir: str | Path,
    operator_review_path: str | Path | None = None,
    thresholds: ResumeGateThresholds | None = None,
) -> ResumeGateReport:
    incident = Path(incident_dir)
    scaleup = Path(scaleup_dir)
    thresholds = thresholds or ResumeGateThresholds()
    incident_summary_path = incident / "halt_incident_summary.csv" if incident.is_dir() else incident
    scaleup_config_path = scaleup / "scaleup_config.json" if scaleup.is_dir() else Path(scaleup_dir)
    if not scaleup_config_path.exists():
        raise FileNotFoundError(f"scale-up config not found: {scaleup_config_path}")
    scaleup_summary_path = (
        scaleup / "scaleup_summary.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_summary.csv")
    )
    scaleup_checks_path = (
        scaleup / "scaleup_checks.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_checks.csv")
    )
    report = evaluate_resume_gate(
        incident_summary=_read_required(incident_summary_path),
        scaleup_summary=_read_required(scaleup_summary_path),
        scaleup_checks=_read_optional(scaleup_checks_path),
        scaleup_config=json.loads(scaleup_config_path.read_text(encoding="utf-8")),
        operator_review=_read_optional(operator_review_path),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.authorization.to_csv(out / "resume_authorization.csv", index=False)
    report.checks.to_csv(out / "resume_checks.csv", index=False)
    report.summary.to_csv(out / "resume_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "resume_action_queue.csv", index=False)
    (out / "resume_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "resume_runbook.md").write_text(_runbook_markdown(report.summary.iloc[0], action_queue), encoding="utf-8")
    inputs: dict[str, Any] = {
        "incident_summary": incident_summary_path,
        "scaleup_summary": scaleup_summary_path,
        "scaleup_config": scaleup_config_path,
    }
    if scaleup_checks_path.exists():
        inputs["scaleup_checks"] = scaleup_checks_path
    if operator_review_path is not None:
        inputs["operator_review"] = Path(operator_review_path)
    write_experiment_manifest(
        out,
        run_type="resume_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return ResumeGateReport(report.authorization, report.checks, report.summary, report.config, out, action_queue)


def _checks(
    incident: pd.Series,
    scaleup: pd.Series,
    scaleup_checks: pd.DataFrame,
    scaleup_config: dict[str, Any],
    operator_review: pd.DataFrame,
    thresholds: ResumeGateThresholds,
) -> pd.DataFrame:
    incident_passed = _to_bool(incident.get("passed", False))
    scaleup_ready = _to_bool(scaleup.get("ready", False))
    incident_scenario = str(incident.get("scenario_key", ""))
    scaleup_scenario = str(scaleup.get("scenario_key", ""))
    incident_adapter = str(incident.get("adapter", ""))
    scaleup_adapter = str(scaleup.get("adapter", ""))
    incident_strategy = _strategy_key(incident.get("strategy", ""))
    scaleup_strategy = _strategy_key(_scaleup_identity(scaleup, scaleup_config, "strategy"))
    incident_market = _identity_key(incident.get("market", ""))
    scaleup_market = _identity_key(_scaleup_identity(scaleup, scaleup_config, "market"))
    incident_proof = _incident_proof_refresh(incident)
    scaleup_proof = _scaleup_proof_refresh(scaleup, scaleup_config)
    proof_active = _proof_refresh_active(incident_proof) or _proof_refresh_active(scaleup_proof)
    scaleup_failed = _failed_scaleup_checks(scaleup, scaleup_checks)
    operator_approved = _operator_approved(operator_review)
    incident_guard_trigger = _text(incident, "guard_failed_check_names")
    operator_trigger_ack = _operator_guard_trigger_ack(operator_review, incident_guard_trigger)
    operator_approval_required = _operator_approval_required(scaleup, scaleup_config, thresholds)
    operator_trigger_ack_required = _operator_trigger_ack_required(scaleup, scaleup_config, thresholds)
    return pd.DataFrame(
        [
            _check(
                "incident_passed",
                incident_passed,
                "is",
                True,
                incident_passed or not thresholds.require_incident_passed,
                "halt incident is not closed",
            ),
            _check(
                "scaleup_ready",
                scaleup_ready,
                "is",
                True,
                scaleup_ready or not thresholds.require_scaleup_ready,
                "scale-up plan is not ready",
            ),
            _check(
                "scenario_match",
                scaleup_scenario,
                "==",
                incident_scenario,
                scaleup_scenario == incident_scenario or not thresholds.require_same_scenario,
                "incident and scale-up scenario keys differ",
            ),
            _check(
                "adapter_match",
                scaleup_adapter,
                "==",
                incident_adapter,
                scaleup_adapter == incident_adapter or not thresholds.require_same_adapter,
                "incident and scale-up adapters differ",
            ),
            _check(
                "strategy_match",
                scaleup_strategy,
                "==",
                incident_strategy,
                bool(scaleup_strategy and incident_strategy and scaleup_strategy == incident_strategy)
                or not thresholds.require_same_strategy,
                "incident and scale-up strategy identities differ",
            ),
            _check(
                "market_match",
                scaleup_market,
                "==",
                incident_market,
                bool(scaleup_market and incident_market and scaleup_market == incident_market)
                or not thresholds.require_same_market,
                "incident and scale-up market identities differ",
            ),
            _check(
                "proof_refresh_ready",
                scaleup_proof["ready"] if proof_active else "inactive",
                "is",
                True,
                (
                    not proof_active
                    or not thresholds.require_ready_proof_refresh
                    or bool(scaleup_proof["provided"] and scaleup_proof["ready"])
                ),
                "resume scale-up proof freshness is missing or not ready",
            ),
            _check(
                "proof_refresh_identity_consistent",
                scaleup_proof["mixed_identity"] if proof_active else "inactive",
                "is",
                False,
                not proof_active or not bool(scaleup_proof["mixed_identity"]),
                "resume scale-up proof freshness has mixed strategy or market identity",
            ),
            _check(
                "proof_refresh_strategy_match",
                scaleup_proof["strategy"] if proof_active else "inactive",
                "==",
                incident_proof["strategy"] if proof_active else "inactive",
                (
                    not proof_active
                    or not thresholds.require_same_proof_refresh_strategy
                    or bool(
                        scaleup_proof["strategy"]
                        and incident_proof["strategy"]
                        and scaleup_proof["strategy"] == incident_proof["strategy"]
                    )
                ),
                "incident and scale-up proof-refresh strategy identities differ",
            ),
            _check(
                "proof_refresh_market_match",
                scaleup_proof["market"] if proof_active else "inactive",
                "==",
                incident_proof["market"] if proof_active else "inactive",
                (
                    not proof_active
                    or not thresholds.require_same_proof_refresh_market
                    or bool(
                        scaleup_proof["market"]
                        and incident_proof["market"]
                        and scaleup_proof["market"] == incident_proof["market"]
                    )
                ),
                "incident and scale-up proof-refresh market identities differ",
            ),
            _check(
                "scaleup_failed_checks",
                scaleup_failed,
                "<=",
                thresholds.max_failed_scaleup_checks,
                scaleup_failed <= thresholds.max_failed_scaleup_checks,
                "scale-up checks still have failures",
            ),
            _check(
                "operator_approved",
                operator_approved if not operator_review.empty else "missing",
                "is",
                True,
                operator_approved or not operator_approval_required,
                "operator approval is missing or false",
            ),
            _check(
                "operator_guard_trigger_ack",
                operator_trigger_ack if operator_review.empty else _operator_guard_trigger_value(operator_review),
                "==",
                incident_guard_trigger,
                operator_trigger_ack or not operator_trigger_ack_required,
                "operator review did not acknowledge the incident guard trigger",
            ),
        ]
    )


def _authorization(
    incident: pd.Series,
    scaleup: pd.Series,
    scaleup_config: dict[str, Any],
    thresholds: ResumeGateThresholds,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    limits = scaleup_config.get("limits", {}) or {}
    kill_switches = scaleup_config.get("kill_switches", {}) or {}
    operator_approval_required = _operator_approval_required(scaleup, scaleup_config, thresholds)
    operator_trigger_ack_required = _operator_trigger_ack_required(scaleup, scaleup_config, thresholds)
    incident_proof = _incident_proof_refresh(incident)
    scaleup_proof = _scaleup_proof_refresh(scaleup, scaleup_config)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(scaleup.get("target_mode", scaleup_config.get("target_mode", ""))),
                "strategy": _strategy_key(_scaleup_identity(scaleup, scaleup_config, "strategy")),
                "market": _identity_key(_scaleup_identity(scaleup, scaleup_config, "market")),
                "incident_strategy": _strategy_key(incident.get("strategy", "")),
                "incident_market": _identity_key(incident.get("market", "")),
                "proof_refresh_required": bool(scaleup_proof["required"]),
                "proof_refresh_provided": bool(scaleup_proof["provided"]),
                "proof_refresh_ready": bool(scaleup_proof["ready"]),
                "proof_refresh_strategy": str(scaleup_proof["strategy"]),
                "proof_refresh_market": str(scaleup_proof["market"]),
                "proof_refresh_mixed_identity": bool(scaleup_proof["mixed_identity"]),
                "proof_source": str(scaleup_proof["proof_source"]),
                "incident_proof_refresh_required": bool(incident_proof["required"]),
                "incident_proof_refresh_provided": bool(incident_proof["provided"]),
                "incident_proof_refresh_ready": bool(incident_proof["ready"]),
                "incident_proof_refresh_strategy": str(incident_proof["strategy"]),
                "incident_proof_refresh_market": str(incident_proof["market"]),
                "incident_proof_refresh_mixed_identity": bool(incident_proof["mixed_identity"]),
                "incident_proof_source": str(incident_proof["proof_source"]),
                "scenario_key": str(scaleup.get("scenario_key", scaleup_config.get("scenario_key", ""))),
                "adapter": str(scaleup.get("adapter", scaleup_config.get("adapter", ""))),
                "incident_status": str(incident.get("incident_status", "")),
                "incident_guard_failed_check_names": _text(incident, "guard_failed_check_names"),
                "incident_guard_first_failed_reason": _text(incident, "guard_first_failed_reason"),
                "operator_approval_required": operator_approval_required,
                "operator_guard_trigger_ack_required": operator_trigger_ack_required,
                "max_orders_per_session": int(_number_from(limits, "max_orders_per_session", _number(scaleup, "max_orders_per_session", 0.0))),
                "max_notional_per_session": float(_number_from(limits, "max_notional_per_session", _number(scaleup, "max_notional_per_session", 0.0))),
                "stop_loss": _nullable_number(limits.get("stop_loss")),
                "max_total_failed_component_checks": _nullable_number(kill_switches.get("max_total_failed_component_checks")),
                "max_total_unmatched_fills": _nullable_number(kill_switches.get("max_total_unmatched_fills")),
                "max_total_mismatched_orders": _nullable_number(kill_switches.get("max_total_mismatched_orders")),
                "max_total_overfilled_orders": _nullable_number(kill_switches.get("max_total_overfilled_orders")),
                "max_lifecycle_orders": _nullable_number(kill_switches.get("max_lifecycle_orders")),
                "max_replace_orders": _nullable_number(kill_switches.get("max_replace_orders")),
                "max_open_order_notional": _nullable_number(kill_switches.get("max_open_order_notional")),
                "max_open_order_age_ns": _nullable_number(kill_switches.get("max_open_order_age_ns")),
                "max_gross_notional": _nullable_number(kill_switches.get("max_gross_notional")),
                "max_abs_net_delta": _nullable_number(kill_switches.get("max_abs_net_delta")),
                "max_abs_net_vega": _nullable_number(kill_switches.get("max_abs_net_vega")),
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
                "target_mode": str(authorization.get("target_mode", "")),
                "strategy": str(authorization.get("strategy", "")),
                "market": str(authorization.get("market", "")),
                "incident_strategy": str(authorization.get("incident_strategy", "")),
                "incident_market": str(authorization.get("incident_market", "")),
                "proof_refresh_required": _to_bool(authorization.get("proof_refresh_required", False)),
                "proof_refresh_provided": _to_bool(authorization.get("proof_refresh_provided", False)),
                "proof_refresh_ready": _to_bool(authorization.get("proof_refresh_ready", False)),
                "proof_refresh_strategy": str(authorization.get("proof_refresh_strategy", "")),
                "proof_refresh_market": str(authorization.get("proof_refresh_market", "")),
                "proof_refresh_mixed_identity": _to_bool(
                    authorization.get("proof_refresh_mixed_identity", False)
                ),
                "proof_source": str(authorization.get("proof_source", "")),
                "incident_proof_refresh_strategy": str(
                    authorization.get("incident_proof_refresh_strategy", "")
                ),
                "incident_proof_refresh_market": str(authorization.get("incident_proof_refresh_market", "")),
                "scenario_key": str(authorization.get("scenario_key", "")),
                "adapter": str(authorization.get("adapter", "")),
                "incident_guard_failed_check_names": _text(authorization, "incident_guard_failed_check_names"),
                "incident_guard_first_failed_reason": _text(authorization, "incident_guard_first_failed_reason"),
                "operator_approval_required": _to_bool(authorization.get("operator_approval_required", False)),
                "operator_guard_trigger_ack_required": _to_bool(
                    authorization.get("operator_guard_trigger_ack_required", False)
                ),
                "failed_checks": failed,
                "recommendation": "resume_with_scaleup_controls" if ready else "keep_trading_disabled",
            }
        ]
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
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


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


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "resume_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _object_text(row.get("operator")).strip(),
                "expected": row.get("threshold"),
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
    return checks.loc[~checks["passed"].map(_to_bool)].copy()


def _component(check: str) -> str:
    if check == "incident_passed":
        return "halt_incident"
    if check in {"scaleup_ready", "scaleup_failed_checks"}:
        return "scaleup_plan"
    if check in {"scenario_match", "adapter_match", "strategy_match", "market_match"}:
        return "resume_identity"
    if check.startswith("proof_refresh_"):
        return "proof_refresh"
    if check.startswith("operator_"):
        return "operator_review"
    return "resume_gate"


def _next_gate(check: str) -> str:
    if check == "incident_passed":
        return "review-halt-incident"
    if check.startswith("proof_refresh_"):
        return "review-proof-refresh"
    if check.startswith("operator_"):
        return "review-resume-gate"
    if check in {
        "scaleup_ready",
        "scaleup_failed_checks",
        "scenario_match",
        "adapter_match",
        "strategy_match",
        "market_match",
    }:
        return "plan-scaleup"
    return "review-resume-gate"


def _action_recommendation(check: str) -> str:
    if check == "incident_passed":
        return "close_halt_incident_before_resume"
    if check == "scaleup_ready":
        return "rerun_or_repair_scaleup_plan"
    if check == "scenario_match":
        return "regenerate_scaleup_for_incident_scenario_or_allow_scenario_change"
    if check == "adapter_match":
        return "regenerate_scaleup_for_incident_adapter_or_allow_adapter_change"
    if check == "strategy_match":
        return "align_scaleup_strategy_with_incident_strategy"
    if check == "market_match":
        return "align_scaleup_market_with_incident_market"
    if check == "proof_refresh_ready":
        return "rerun_proof_refresh_before_resume"
    if check == "proof_refresh_identity_consistent":
        return "rerun_proof_refresh_without_mixed_identity"
    if check == "proof_refresh_strategy_match":
        return "align_resume_proof_refresh_strategy"
    if check == "proof_refresh_market_match":
        return "align_resume_proof_refresh_market"
    if check == "scaleup_failed_checks":
        return "clear_scaleup_failed_checks_before_resume"
    if check == "operator_approved":
        return "capture_operator_resume_approval"
    if check == "operator_guard_trigger_ack":
        return "capture_operator_guard_trigger_ack"
    return "repair_resume_gate_inputs"


def _config(
    authorization: pd.Series,
    scaleup_config: dict[str, Any],
    thresholds: ResumeGateThresholds,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "ready": bool(authorization["ready"]),
        "failed_check_count": len(failed_check_records),
        "target_mode": str(authorization["target_mode"]),
        "strategy": str(authorization["strategy"]),
        "market": str(authorization["market"]),
        "scenario_key": str(authorization["scenario_key"]),
        "adapter": str(authorization["adapter"]),
        "identity": {
            "strategy": str(authorization["strategy"]),
            "market": str(authorization["market"]),
            "incident_strategy": str(authorization.get("incident_strategy", "")),
            "incident_market": str(authorization.get("incident_market", "")),
        },
        "proof_freshness": {
            "required": _to_bool(authorization.get("proof_refresh_required", False)),
            "provided": _to_bool(authorization.get("proof_refresh_provided", False)),
            "ready": _to_bool(authorization.get("proof_refresh_ready", False)),
            "strategy": str(authorization.get("proof_refresh_strategy", "")),
            "market": str(authorization.get("proof_refresh_market", "")),
            "mixed_identity": _to_bool(authorization.get("proof_refresh_mixed_identity", False)),
            "proof_source": str(authorization.get("proof_source", "")),
            "incident": {
                "required": _to_bool(authorization.get("incident_proof_refresh_required", False)),
                "provided": _to_bool(authorization.get("incident_proof_refresh_provided", False)),
                "ready": _to_bool(authorization.get("incident_proof_refresh_ready", False)),
                "strategy": str(authorization.get("incident_proof_refresh_strategy", "")),
                "market": str(authorization.get("incident_proof_refresh_market", "")),
                "mixed_identity": _to_bool(
                    authorization.get("incident_proof_refresh_mixed_identity", False)
                ),
                "proof_source": str(authorization.get("incident_proof_source", "")),
            },
        },
        "limits": scaleup_config.get("limits", {}),
        "kill_switches": scaleup_config.get("kill_switches", {}),
        "incident": {
            "status": str(authorization.get("incident_status", "")),
            "guard_failed_check_names": _text(authorization, "incident_guard_failed_check_names"),
            "guard_first_failed_reason": _text(authorization, "incident_guard_first_failed_reason"),
        },
        "operator_review": {
            "approval_required": _to_bool(authorization.get("operator_approval_required", False)),
            "guard_trigger_ack_required": _to_bool(
                authorization.get("operator_guard_trigger_ack_required", False)
            ),
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


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Resume Gate Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Incident strategy: {_object_text(summary_row.get('incident_strategy')).strip()}",
        f"- Incident market: {_object_text(summary_row.get('incident_market')).strip()}",
        f"- Proof refresh ready: {_object_text(summary_row.get('proof_refresh_ready')).strip()}",
        f"- Proof refresh strategy: {_object_text(summary_row.get('proof_refresh_strategy')).strip()}",
        f"- Proof refresh market: {_object_text(summary_row.get('proof_refresh_market')).strip()}",
        f"- Operator approval required: {_object_text(summary_row.get('operator_approval_required')).strip()}",
        f"- Operator trigger ack required: {_object_text(summary_row.get('operator_guard_trigger_ack_required')).strip()}",
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
        return "No resume-gate actions."
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


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [_jsonable_check_record(row) for row in failed.to_dict(orient="records")]


def _jsonable_check_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _read_required(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required resume gate input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required resume gate input is empty: {file_path}")
    return frame


def _read_optional(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _failed_scaleup_checks(scaleup: pd.Series, checks: pd.DataFrame) -> int:
    if "failed_checks" in scaleup.index and not pd.isna(scaleup["failed_checks"]):
        return int(float(scaleup["failed_checks"]))
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _operator_approved(operator_review: pd.DataFrame) -> bool:
    if operator_review.empty:
        return False
    row = operator_review.iloc[-1]
    for column in ("approved", "resume_approved", "allow_resume"):
        if column in row.index:
            return _to_bool(row[column])
    return False


def _operator_guard_trigger_ack(operator_review: pd.DataFrame, incident_guard_trigger: str) -> bool:
    if operator_review.empty or not incident_guard_trigger:
        return False
    return _operator_guard_trigger_value(operator_review) == incident_guard_trigger


def _operator_guard_trigger_value(operator_review: pd.DataFrame) -> str:
    if operator_review.empty:
        return "missing"
    row = operator_review.iloc[-1]
    for column in (
        "guard_failed_check_names",
        "incident_guard_failed_check_names",
        "ack_guard_failed_check_names",
        "acknowledged_guard_failed_check_names",
    ):
        if column in row.index:
            return _text(row, column)
    return "missing"


def _operator_approval_required(
    scaleup: pd.Series,
    scaleup_config: dict[str, Any],
    thresholds: ResumeGateThresholds,
) -> bool:
    return bool(thresholds.require_operator_approval or _target_mode(scaleup, scaleup_config) == "live_dryrun")


def _operator_trigger_ack_required(
    scaleup: pd.Series,
    scaleup_config: dict[str, Any],
    thresholds: ResumeGateThresholds,
) -> bool:
    return bool(thresholds.require_operator_guard_trigger_ack or _target_mode(scaleup, scaleup_config) == "live_dryrun")


def _target_mode(scaleup: pd.Series, scaleup_config: dict[str, Any]) -> str:
    summary_mode = str(scaleup.get("target_mode", "")).strip().lower()
    config_mode = str(scaleup_config.get("target_mode", "")).strip().lower()
    if "live_dryrun" in {summary_mode, config_mode}:
        return "live_dryrun"
    return summary_mode or config_mode


def _scaleup_identity(scaleup: pd.Series, scaleup_config: dict[str, Any], key: str) -> object:
    identity = scaleup_config.get("identity", {}) or {}
    if not isinstance(identity, dict):
        identity = {}
    return _first_text(scaleup.get(key, ""), scaleup_config.get(key, ""), identity.get(key, ""))


def _incident_proof_refresh(incident: pd.Series) -> dict[str, object]:
    raw_strategy = _text(incident, "proof_refresh_strategy")
    raw_market = _text(incident, "proof_refresh_market")
    return {
        "active": _proof_refresh_fields_active(incident),
        "required": _to_bool(incident.get("proof_refresh_required", False)),
        "provided": _to_bool(incident.get("proof_refresh_provided", False)),
        "ready": _to_bool(incident.get("proof_refresh_ready", False)),
        "strategy": _strategy_key(_first_text(raw_strategy, incident.get("strategy", ""))),
        "market": _identity_key(_first_text(raw_market, incident.get("market", ""))),
        "mixed_identity": _to_bool(incident.get("proof_refresh_mixed_identity", False)),
        "proof_source": _text(incident, "proof_source"),
    }


def _scaleup_proof_refresh(scaleup: pd.Series, scaleup_config: dict[str, Any]) -> dict[str, object]:
    proof = scaleup_config.get("proof_freshness", {}) or {}
    if not isinstance(proof, dict):
        proof = {}
    raw_strategy = _first_text(proof.get("strategy", ""), scaleup.get("proof_refresh_strategy", ""))
    raw_market = _first_text(proof.get("market", ""), scaleup.get("proof_refresh_market", ""))
    return {
        "active": _proof_refresh_mapping_active(proof) or _proof_refresh_fields_active(scaleup),
        "required": _to_bool(proof.get("required", scaleup.get("proof_refresh_required", False))),
        "provided": _to_bool(proof.get("provided", scaleup.get("proof_refresh_provided", False))),
        "ready": _to_bool(proof.get("ready", scaleup.get("proof_refresh_ready", False))),
        "strategy": _strategy_key(_first_text(raw_strategy, _scaleup_identity(scaleup, scaleup_config, "strategy"))),
        "market": _identity_key(_first_text(raw_market, _scaleup_identity(scaleup, scaleup_config, "market"))),
        "mixed_identity": _to_bool(
            proof.get("mixed_identity", scaleup.get("proof_refresh_mixed_identity", False))
        ),
        "proof_source": _first_text(proof.get("proof_source", ""), scaleup.get("proof_source", "")),
    }


def _proof_refresh_active(state: dict[str, object]) -> bool:
    return bool(state.get("active") or state.get("required") or state.get("provided") or state.get("ready"))


def _proof_refresh_mapping_active(proof: dict[str, Any]) -> bool:
    bool_columns = ("required", "provided", "ready", "mixed_identity")
    text_columns = ("strategy", "market", "proof_source")
    return any(_to_bool(proof.get(column, False)) for column in bool_columns) or any(
        _object_text(proof.get(column, "")).strip() for column in text_columns
    )


def _proof_refresh_fields_active(row: pd.Series) -> bool:
    return any(
        _to_bool(row.get(column, False))
        for column in (
            "proof_refresh_required",
            "proof_refresh_provided",
            "proof_refresh_ready",
            "proof_refresh_mixed_identity",
        )
    ) or any(
        _text(row, column).strip()
        for column in ("proof_refresh_strategy", "proof_refresh_market", "proof_source")
    )


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


def _first_text(*values: object) -> str:
    for value in values:
        text = _object_text(value)
        if text:
            return text
    return ""


def _validate_thresholds(thresholds: ResumeGateThresholds) -> None:
    if thresholds.max_failed_scaleup_checks < 0:
        raise ValueError("max_failed_scaleup_checks must be non-negative")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return fallback
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else fallback


def _number_from(mapping: dict[str, Any], key: str, fallback: float) -> float:
    value = mapping.get(key, fallback)
    return fallback if value is None or pd.isna(value) else float(value)


def _nullable_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _object_text(row[column])


def _object_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed"}
    return bool(value)


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
