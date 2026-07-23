from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import (
    MANIFEST_NAME,
    manifest_dependency_paths,
    write_experiment_manifest,
)
from reports.proof import ProofReportVerification, verify_proof_report


@dataclass(frozen=True)
class ProofRefreshThresholds:
    require_calibrated_replay_when_drift_fails: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None


@dataclass(frozen=True)
class ProofRefreshReport:
    decision: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    config: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_proof_refresh(
    *,
    drift_summary: pd.DataFrame,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None = None,
    calibrated_replay_summary: pd.DataFrame | None = None,
    thresholds: ProofRefreshThresholds | None = None,
    baseline_proof_verification: ProofReportVerification | None = None,
    latest_proof_verification: ProofReportVerification | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_passed = _frame_bool(drift_summary, "passed")
    baseline_reported_passed = _frame_bool(
        baseline_proof_summary,
        "all_passed",
    )
    baseline_verification_enforced = baseline_proof_verification is not None
    baseline_verified = bool(
        baseline_proof_verification is not None
        and baseline_proof_verification.verified
    )
    baseline_passed = bool(
        baseline_reported_passed
        and (
            baseline_verified
            if baseline_verification_enforced
            else True
        )
    )
    latest_available = latest_proof_summary is not None and not latest_proof_summary.empty
    latest_reported_passed = (
        _frame_bool(latest_proof_summary, "all_passed")
        if latest_available
        else False
    )
    latest_verification_enforced = bool(
        latest_available and latest_proof_verification is not None
    )
    latest_verified = bool(
        latest_proof_verification is not None
        and latest_proof_verification.verified
    )
    latest_passed = bool(
        latest_reported_passed
        and (
            latest_verified
            if latest_verification_enforced
            else True
        )
    )
    calibrated_available = calibrated_replay_summary is not None and not calibrated_replay_summary.empty
    calibrated_ready = _frame_bool(calibrated_replay_summary, "ready") if calibrated_available else False
    calibrated_strategy = _frame_str(calibrated_replay_summary, "strategy") if calibrated_available else ""
    identities = _input_identities(
        baseline_proof_summary=baseline_proof_summary,
        latest_proof_summary=latest_proof_summary if latest_available else None,
        calibrated_replay_summary=calibrated_replay_summary if calibrated_available else None,
    )
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    mixed_identity = bool((len(strategies) > 1) or (len(markets) > 1))

    checks = _checks(
        drift_passed=drift_passed,
        baseline_reported_passed=baseline_reported_passed,
        baseline_verification_enforced=baseline_verification_enforced,
        baseline_verified=baseline_verified,
        latest_available=latest_available,
        latest_reported_passed=latest_reported_passed,
        latest_verification_enforced=latest_verification_enforced,
        latest_verified=latest_verified,
        calibrated_available=calibrated_available,
        calibrated_ready=calibrated_ready,
        calibrated_strategy=calibrated_strategy,
        identities=identities,
        thresholds=thresholds,
    )
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed_checks == 0
    proof_source = _proof_source(drift_passed, baseline_passed, latest_passed, ready)
    recommendation = _recommendation(ready, drift_passed)
    decision = pd.DataFrame(
        [
            {
                "action": recommendation,
                "proof_source": proof_source,
                "strategy": _single_identity(strategies),
                "market": _single_identity(markets),
                "mixed_identity": mixed_identity,
                "fresh_proof_required": not drift_passed,
                "reason": _reason(ready, drift_passed, latest_available, latest_passed, calibrated_ready),
            }
        ]
    )
    summary = pd.DataFrame(
        [
            {
                "ready": ready,
                "drift_passed": drift_passed,
                "fresh_proof_required": not drift_passed,
                "proof_source": proof_source,
                "baseline_proof_reported_passed": baseline_reported_passed,
                "baseline_proof_passed": baseline_passed,
                "latest_proof_available": latest_available,
                "latest_proof_reported_passed": latest_reported_passed,
                "latest_proof_passed": latest_passed,
                "calibrated_replay_required": (not drift_passed)
                and thresholds.require_calibrated_replay_when_drift_fails,
                "calibrated_replay_available": calibrated_available,
                "calibrated_replay_ready": calibrated_ready,
                "strategy": _single_identity(strategies),
                "strategy_count": int(len(strategies)),
                "missing_strategy_sources": _missing_identity_count(identities, "strategy"),
                "expected_strategy": _strategy_key(thresholds.expected_strategy)
                if thresholds.expected_strategy is not None
                else "",
                "market": _single_identity(markets),
                "market_count": int(len(markets)),
                "missing_market_sources": _missing_identity_count(identities, "market"),
                "expected_market": _identity_key(thresholds.expected_market)
                if thresholds.expected_market is not None
                else "",
                "mixed_identity": mixed_identity,
                "failed_checks": failed_checks,
                "recommendation": recommendation,
                "non_authorizing": True,
                "authorizes_routing": False,
                "authorizes_submission": False,
                **_proof_verification_summary_fields(
                    "baseline_proof",
                    baseline_proof_verification,
                ),
                **_proof_verification_summary_fields(
                    "latest_proof",
                    latest_proof_verification,
                ),
            }
        ]
    )
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(decision.iloc[0], summary.iloc[0], thresholds, action_queue)
    return ProofRefreshReport(
        decision=decision,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config,
    )


def write_proof_refresh_report(
    *,
    drift_path: str | Path,
    baseline_proof_path: str | Path,
    output_dir: str | Path,
    latest_proof_path: str | Path | None = None,
    calibrated_replay_path: str | Path | None = None,
    thresholds: ProofRefreshThresholds | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_file = _summary_path(drift_path, "fill_model_drift_summary.csv")
    baseline_file = _summary_path(baseline_proof_path, "proof_summary.csv")
    latest_file = _optional_summary_path(latest_proof_path, "proof_summary.csv")
    calibrated_file = _optional_summary_path(calibrated_replay_path, "calibrated_replay_summary.csv")
    baseline_verification = verify_proof_report(baseline_file.parent)
    latest_verification = (
        verify_proof_report(latest_file.parent)
        if latest_file is not None
        else None
    )
    report = evaluate_proof_refresh(
        drift_summary=_read_summary(drift_file),
        baseline_proof_summary=_read_summary(baseline_file),
        latest_proof_summary=_read_summary(latest_file) if latest_file is not None else None,
        calibrated_replay_summary=_read_summary(calibrated_file) if calibrated_file is not None else None,
        thresholds=thresholds,
        baseline_proof_verification=baseline_verification,
        latest_proof_verification=latest_verification,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.decision.to_csv(out / "proof_refresh_decision.csv", index=False)
    report.checks.to_csv(out / "proof_refresh_checks.csv", index=False)
    report.summary.to_csv(out / "proof_refresh_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "proof_refresh_action_queue.csv", index=False)
    config_payload = report.config or _config(
        report.decision.iloc[0],
        report.summary.iloc[0],
        thresholds,
        action_queue,
    )
    (out / "proof_refresh_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "proof_refresh_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="proof_refresh_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs=_proof_refresh_manifest_inputs(
            drift_file=drift_file,
            baseline_proof_dir=baseline_file.parent,
            latest_proof_dir=(
                latest_file.parent
                if latest_file is not None
                else None
            ),
            calibrated_file=calibrated_file,
        ),
        extra=_proof_refresh_manifest_extra(report),
    )
    return ProofRefreshReport(
        report.decision,
        report.checks,
        report.summary,
        out,
        action_queue,
        config_payload,
    )


def _proof_verification_summary_fields(
    prefix: str,
    verification: ProofReportVerification | None,
) -> dict[str, object]:
    available = verification is not None
    return {
        f"{prefix}_verification_enforced": available,
        f"{prefix}_semantically_verified": bool(
            available and verification.verified
        ),
        f"{prefix}_verification_passed": bool(
            available and verification.passed
        ),
        f"{prefix}_manifest_current": bool(
            available and verification.manifest_current
        ),
        f"{prefix}_inputs_current": bool(
            available and verification.inputs_current
        ),
        f"{prefix}_replay_manifests_current": bool(
            available and verification.replay_manifests_current
        ),
        f"{prefix}_artifacts_consistent": bool(
            available and verification.artifacts_consistent
        ),
        f"{prefix}_non_authorizing": bool(
            available and verification.non_authorizing
        ),
        f"{prefix}_manifest_artifact_count": (
            verification.manifest_artifact_count
            if available
            else 0
        ),
        f"{prefix}_manifest_artifact_match_count": (
            verification.manifest_artifact_match_count
            if available
            else 0
        ),
        f"{prefix}_manifest_input_fingerprint_count": (
            verification.manifest_input_fingerprint_count
            if available
            else 0
        ),
        f"{prefix}_manifest_input_fingerprint_match_count": (
            verification.manifest_input_fingerprint_match_count
            if available
            else 0
        ),
        f"{prefix}_replay_manifest_count": (
            verification.replay_manifest_count
            if available
            else 0
        ),
        f"{prefix}_replay_manifest_current_count": (
            verification.replay_manifest_current_count
            if available
            else 0
        ),
        f"{prefix}_verification_error": (
            verification.error
            if available
            else ""
        ),
    }


def _proof_refresh_manifest_inputs(
    *,
    drift_file: Path,
    baseline_proof_dir: Path,
    latest_proof_dir: Path | None,
    calibrated_file: Path | None,
) -> dict[str, object]:
    inputs: dict[str, object] = {
        "fill_model_drift": drift_file.resolve(),
        **_proof_bundle_manifest_inputs(
            "baseline_proof",
            baseline_proof_dir,
        ),
    }
    if latest_proof_dir is not None:
        inputs.update(
            _proof_bundle_manifest_inputs(
                "latest_proof",
                latest_proof_dir,
            )
        )
    if calibrated_file is not None:
        inputs["calibrated_replay"] = calibrated_file.resolve()
    return inputs


def _proof_bundle_manifest_inputs(
    prefix: str,
    proof_dir: Path,
) -> dict[str, object]:
    root = proof_dir.resolve()
    manifest_path = root / MANIFEST_NAME
    inputs: dict[str, object] = {prefix: root}
    if not manifest_path.is_file():
        return inputs
    inputs[f"{prefix}_manifest"] = manifest_path
    dependencies = manifest_dependency_paths(manifest_path)
    if dependencies:
        inputs[f"{prefix}_dependencies"] = dependencies
    return inputs


def _proof_refresh_manifest_extra(
    report: ProofRefreshReport,
) -> dict[str, object]:
    row = (
        report.summary.iloc[0]
        if not report.summary.empty
        else pd.Series(dtype=object)
    )
    return {
        "ready": report.ready,
        "proof_source": _value_text(row.get("proof_source")),
        "baseline_proof_verified": _value_bool(
            row.get("baseline_proof_semantically_verified")
        ),
        "latest_proof_available": _value_bool(
            row.get("latest_proof_available")
        ),
        "latest_proof_verified": _value_bool(
            row.get("latest_proof_semantically_verified")
        ),
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _checks(
    *,
    drift_passed: bool,
    baseline_reported_passed: bool,
    baseline_verification_enforced: bool,
    baseline_verified: bool,
    latest_available: bool,
    latest_reported_passed: bool,
    latest_verification_enforced: bool,
    latest_verified: bool,
    calibrated_available: bool,
    calibrated_ready: bool,
    calibrated_strategy: str,
    identities: pd.DataFrame,
    thresholds: ProofRefreshThresholds,
) -> pd.DataFrame:
    checks = []
    if baseline_verification_enforced:
        checks.append(
            _check(
                "baseline_proof_verified",
                baseline_verified,
                "is",
                True,
                baseline_verified,
                "baseline proof bundle failed semantic verification",
            )
        )
    if latest_available and latest_verification_enforced:
        checks.append(
            _check(
                "latest_proof_verified",
                latest_verified,
                "is",
                True,
                latest_verified,
                "latest proof bundle failed semantic verification",
            )
        )
    if drift_passed:
        checks.append(
            _check(
                "reusable_proof_passed",
                baseline_reported_passed or latest_reported_passed,
                "is",
                True,
                baseline_reported_passed or latest_reported_passed,
                "neither baseline nor latest proof passed under reusable fill-model assumptions",
            )
        )
    else:
        checks.extend(
            [
                _check(
                    "latest_proof_available",
                    latest_available,
                    "is",
                    True,
                    latest_available,
                    "fill-model drift failed, so a fresh/latest proof report is required",
                ),
                _check(
                    "latest_proof_passed",
                    latest_reported_passed,
                    "is",
                    True,
                    latest_reported_passed,
                    "latest proof report did not pass",
                ),
            ]
        )
        if thresholds.require_calibrated_replay_when_drift_fails:
            checks.extend(
                [
                    _check(
                        "calibrated_replay_available",
                        calibrated_available,
                        "is",
                        True,
                        calibrated_available,
                        "fill-model drift failed, so a calibrated replay plan is required",
                    ),
                    _check(
                        "calibrated_replay_ready",
                        calibrated_ready,
                        "is",
                        True,
                        calibrated_ready,
                        "calibrated replay plan is not ready",
                    ),
                ]
            )
        if thresholds.expected_strategy is not None:
            expected = _strategy_key(thresholds.expected_strategy)
            actual = _strategy_key(calibrated_strategy) if calibrated_strategy else ""
            checks.append(
                _check(
                    "calibrated_replay_strategy_matches",
                    actual,
                    "==",
                    expected,
                    bool(actual) and actual == expected,
                    "calibrated replay plan strategy does not match expected strategy",
                )
            )

    checks.extend(_identity_checks(identities, thresholds))
    return pd.DataFrame(checks)


def _identity_checks(identities: pd.DataFrame, thresholds: ProofRefreshThresholds) -> list[dict[str, object]]:
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    rows = [
        _check(
            "same_strategy",
            ";".join(sorted(strategies)) if strategies else "",
            "count<=",
            1,
            len(strategies) <= 1,
            "proof refresh inputs mix strategy identities",
        ),
        _check(
            "same_market",
            ";".join(sorted(markets)) if markets else "",
            "count<=",
            1,
            len(markets) <= 1,
            "proof refresh inputs mix market identities",
        ),
    ]
    if thresholds.expected_strategy is not None:
        expected = _strategy_key(thresholds.expected_strategy)
        rows.append(
            _check(
                "expected_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "==",
                expected,
                not strategies or strategies == {expected},
                "available proof refresh strategies do not match expected strategy",
            )
        )
    if thresholds.expected_market is not None:
        expected = _identity_key(thresholds.expected_market)
        rows.append(
            _check(
                "expected_market",
                ";".join(sorted(markets)) if markets else "",
                "==",
                expected,
                not markets or markets == {expected},
                "available proof refresh markets do not match expected market",
            )
        )
    return rows


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
    out["first_failed_reason"] = _value_text(failed.iloc[0].get("reason")) if not failed.empty else ""
    out["primary_blocker_check"] = _value_text(failed.iloc[0].get("check")) if not failed.empty else ""
    out["primary_blocker_value"] = _value_text(failed.iloc[0].get("value")) if not failed.empty else ""
    out["primary_blocker_operator"] = _value_text(failed.iloc[0].get("operator")) if not failed.empty else ""
    out["primary_blocker_threshold"] = _value_text(failed.iloc[0].get("threshold")) if not failed.empty else ""
    out["primary_blocker_reason"] = _value_text(failed.iloc[0].get("reason")) if not failed.empty else ""
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
        check = _value_text(row.get("check"))
        rows.append(
            _action_row(
                component=_component(check),
                check=check,
                actual=row.get("value"),
                operator=_value_text(row.get("operator")),
                expected=row.get("threshold"),
                reason=_value_text(row.get("reason")),
                recommendation=_action_recommendation(check),
            )
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    component: str,
    check: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "review-proof-refresh"
    return {
        "queue_status": "blocked",
        "source": "proof_refresh_checks",
        "component": component,
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _proof_verification_config(
    summary_row: pd.Series,
    prefix: str,
) -> dict[str, object]:
    return {
        "enforced": _value_bool(
            summary_row.get(f"{prefix}_verification_enforced")
        ),
        "verified": _value_bool(
            summary_row.get(f"{prefix}_semantically_verified")
        ),
        "passed": _value_bool(
            summary_row.get(f"{prefix}_verification_passed")
        ),
        "manifest_current": _value_bool(
            summary_row.get(f"{prefix}_manifest_current")
        ),
        "inputs_current": _value_bool(
            summary_row.get(f"{prefix}_inputs_current")
        ),
        "replay_manifests_current": _value_bool(
            summary_row.get(f"{prefix}_replay_manifests_current")
        ),
        "artifacts_consistent": _value_bool(
            summary_row.get(f"{prefix}_artifacts_consistent")
        ),
        "non_authorizing": _value_bool(
            summary_row.get(f"{prefix}_non_authorizing")
        ),
        "manifest_artifact_count": _value_int(
            summary_row.get(f"{prefix}_manifest_artifact_count")
        ),
        "manifest_artifact_match_count": _value_int(
            summary_row.get(f"{prefix}_manifest_artifact_match_count")
        ),
        "manifest_input_fingerprint_count": _value_int(
            summary_row.get(
                f"{prefix}_manifest_input_fingerprint_count"
            )
        ),
        "manifest_input_fingerprint_match_count": _value_int(
            summary_row.get(
                f"{prefix}_manifest_input_fingerprint_match_count"
            )
        ),
        "replay_manifest_count": _value_int(
            summary_row.get(f"{prefix}_replay_manifest_count")
        ),
        "replay_manifest_current_count": _value_int(
            summary_row.get(
                f"{prefix}_replay_manifest_current_count"
            )
        ),
        "error": _value_text(
            summary_row.get(f"{prefix}_verification_error")
        ),
    }


def _config(
    decision_row: pd.Series,
    summary_row: pd.Series,
    thresholds: ProofRefreshThresholds,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "ready": _value_bool(summary_row.get("ready")),
        "authority": {
            "non_authorizing": _value_bool(
                summary_row.get("non_authorizing")
            ),
            "authorizes_routing": _value_bool(
                summary_row.get("authorizes_routing")
            ),
            "authorizes_submission": _value_bool(
                summary_row.get("authorizes_submission")
            ),
        },
        "decision": {
            "action": _value_text(decision_row.get("action")),
            "proof_source": _value_text(decision_row.get("proof_source")),
            "fresh_proof_required": _value_bool(decision_row.get("fresh_proof_required")),
            "reason": _value_text(decision_row.get("reason")),
        },
        "thresholds": asdict(thresholds),
        "identity": {
            "strategy": _value_text(summary_row.get("strategy")),
            "strategy_count": _value_int(summary_row.get("strategy_count")),
            "missing_strategy_sources": _value_int(summary_row.get("missing_strategy_sources")),
            "expected_strategy": _value_text(summary_row.get("expected_strategy")),
            "market": _value_text(summary_row.get("market")),
            "market_count": _value_int(summary_row.get("market_count")),
            "missing_market_sources": _value_int(summary_row.get("missing_market_sources")),
            "expected_market": _value_text(summary_row.get("expected_market")),
            "mixed_identity": _value_bool(summary_row.get("mixed_identity")),
        },
        "proof": {
            "drift_passed": _value_bool(summary_row.get("drift_passed")),
            "fresh_proof_required": _value_bool(summary_row.get("fresh_proof_required")),
            "proof_source": _value_text(summary_row.get("proof_source")),
            "baseline_proof_reported_passed": _value_bool(
                summary_row.get("baseline_proof_reported_passed")
            ),
            "baseline_proof_passed": _value_bool(summary_row.get("baseline_proof_passed")),
            "baseline_proof_verification": _proof_verification_config(
                summary_row,
                "baseline_proof",
            ),
            "latest_proof_available": _value_bool(summary_row.get("latest_proof_available")),
            "latest_proof_reported_passed": _value_bool(
                summary_row.get("latest_proof_reported_passed")
            ),
            "latest_proof_passed": _value_bool(summary_row.get("latest_proof_passed")),
            "latest_proof_verification": _proof_verification_config(
                summary_row,
                "latest_proof",
            ),
            "calibrated_replay_required": _value_bool(summary_row.get("calibrated_replay_required")),
            "calibrated_replay_available": _value_bool(summary_row.get("calibrated_replay_available")),
            "calibrated_replay_ready": _value_bool(summary_row.get("calibrated_replay_ready")),
        },
        "failed_check_count": _value_int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _value_text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _value_text(summary_row.get("primary_blocker_check")),
            "value": _value_text(summary_row.get("primary_blocker_value")),
            "operator": _value_text(summary_row.get("primary_blocker_operator")),
            "threshold": _value_text(summary_row.get("primary_blocker_threshold")),
            "reason": _value_text(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _value_int(summary_row.get("action_queue_count")),
        "ready_action_count": _value_int(summary_row.get("ready_action_count")),
        "blocked_action_count": _value_int(summary_row.get("blocked_action_count")),
        "review_action_count": _value_int(summary_row.get("review_action_count")),
        "next_gate": _value_text(summary_row.get("next_gate")),
        "next_gate_help_command": _value_text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _value_text(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "recommendation": _value_text(summary_row.get("recommendation")),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _value_bool(summary_row.get("ready")) else "no"
    lines = [
        "# Proof Refresh Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Drift passed: {_value_text(summary_row.get('drift_passed'))}",
        f"- Fresh proof required: {_value_text(summary_row.get('fresh_proof_required'))}",
        f"- Proof source: {_value_text(summary_row.get('proof_source'))}",
        f"- Baseline proof reported passed: {_value_text(summary_row.get('baseline_proof_reported_passed'))}",
        f"- Baseline proof semantically verified: {_value_text(summary_row.get('baseline_proof_semantically_verified'))}",
        f"- Baseline proof effective passed: {_value_text(summary_row.get('baseline_proof_passed'))}",
        f"- Latest proof available: {_value_text(summary_row.get('latest_proof_available'))}",
        f"- Latest proof reported passed: {_value_text(summary_row.get('latest_proof_reported_passed'))}",
        f"- Latest proof semantically verified: {_value_text(summary_row.get('latest_proof_semantically_verified'))}",
        f"- Latest proof effective passed: {_value_text(summary_row.get('latest_proof_passed'))}",
        f"- Calibrated replay required: {_value_text(summary_row.get('calibrated_replay_required'))}",
        f"- Calibrated replay ready: {_value_text(summary_row.get('calibrated_replay_ready'))}",
        f"- Strategy: {_value_text(summary_row.get('strategy'))}",
        f"- Market: {_value_text(summary_row.get('market'))}",
        f"- Mixed identity: {_value_text(summary_row.get('mixed_identity'))}",
        f"- Failed checks: {_value_int(summary_row.get('failed_check_count'))}",
        f"- Blocked actions: {_value_int(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_value_text(summary_row.get('recommendation'))}",
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
        return "No proof-refresh actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _value_text(item.get("priority")),
                    _value_text(item.get("queue_status")),
                    _value_text(item.get("component")),
                    _value_text(item.get("check")),
                    _value_text(item.get("actual")),
                    _value_text(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _value_text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].copy()


def _component(check: str) -> str:
    if check in {
        "baseline_proof_verified",
        "latest_proof_verified",
        "reusable_proof_passed",
        "latest_proof_available",
        "latest_proof_passed",
    }:
        return "proof_evidence"
    if check in {
        "calibrated_replay_available",
        "calibrated_replay_ready",
        "calibrated_replay_strategy_matches",
    }:
        return "calibrated_replay"
    if check in {"same_strategy", "expected_strategy"}:
        return "strategy_identity"
    if check in {"same_market", "expected_market"}:
        return "market_identity"
    return "proof_refresh"


def _action_recommendation(check: str) -> str:
    if check == "baseline_proof_verified":
        return "regenerate_and_verify_baseline_proof"
    if check == "latest_proof_verified":
        return "regenerate_and_verify_latest_proof"
    if check == "reusable_proof_passed":
        return "repair_or_rerun_reusable_proof_before_promotion"
    if check in {"latest_proof_available", "latest_proof_passed"}:
        return "rerun_latest_calibrated_proof"
    if check in {"calibrated_replay_available", "calibrated_replay_ready"}:
        return "run_calibrated_replay_plan_before_proof_refresh"
    if check == "calibrated_replay_strategy_matches":
        return "regenerate_calibrated_replay_for_expected_strategy"
    if check in {"same_strategy", "expected_strategy"}:
        return "align_proof_refresh_strategy_identity"
    if check in {"same_market", "expected_market"}:
        return "align_proof_refresh_market_identity"
    return "repair_proof_refresh_inputs"


def _proof_source(drift_passed: bool, baseline_passed: bool, latest_passed: bool, ready: bool) -> str:
    if not ready:
        return "none"
    if not drift_passed:
        return "latest"
    if baseline_passed:
        return "baseline"
    return "latest" if latest_passed else "none"


def _recommendation(ready: bool, drift_passed: bool) -> str:
    if ready and drift_passed:
        return "reuse_existing_proof"
    if ready:
        return "use_latest_calibrated_proof"
    if drift_passed:
        return "repair_proof_before_promotion"
    return "rerun_calibrated_proof_before_promotion"


def _reason(
    ready: bool,
    drift_passed: bool,
    latest_available: bool,
    latest_passed: bool,
    calibrated_ready: bool,
) -> str:
    if ready and drift_passed:
        return "fill-model drift passed, so reusable proof assumptions remain valid"
    if ready:
        return "fill-model drift failed, but latest calibrated proof evidence passed"
    if drift_passed:
        return "fill-model drift passed, but no passing proof report is available"
    if not latest_available:
        return "fill-model drift failed and no latest proof report was supplied"
    if not latest_passed:
        return "fill-model drift failed and latest proof report did not pass"
    if not calibrated_ready:
        return "fill-model drift failed and calibrated replay plan is not ready"
    return "proof refresh gate has unresolved failed checks"


def _summary_path(path: str | Path, filename: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / filename
    if not candidate.exists():
        raise FileNotFoundError(f"summary artifact not found: {candidate}")
    return candidate


def _optional_summary_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    return _summary_path(path, filename)


def _read_summary(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"summary artifact is empty: {path}")
    return frame


def _frame_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _frame_str(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _input_identities(
    *,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None,
    calibrated_replay_summary: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = [
        _identity_row("baseline_proof", baseline_proof_summary),
    ]
    if latest_proof_summary is not None and not latest_proof_summary.empty:
        rows.append(_identity_row("latest_proof", latest_proof_summary))
    if calibrated_replay_summary is not None and not calibrated_replay_summary.empty:
        rows.append(_identity_row("calibrated_replay", calibrated_replay_summary))
    return pd.DataFrame(rows)


def _identity_row(source: str, frame: pd.DataFrame) -> dict[str, str]:
    row = frame.iloc[0] if frame is not None and not frame.empty else pd.Series(dtype=object)
    return {
        "source": source,
        "strategy": _strategy_key(_first_identity(row, ("strategy", "strategy_name", "strategy_id"))),
        "market": _identity_key(_first_identity(row, ("market", "market_profile", "market_name", "market_id"))),
    }


def _identity_values(frame: pd.DataFrame, column: str, *, normalizer) -> set[str]:
    if frame.empty or column not in frame.columns:
        return set()
    return {value for value in frame[column].map(normalizer) if value}


def _missing_identity_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty:
        return 0
    if column not in frame.columns:
        return int(len(frame))
    return int((frame[column].map(_identity_key) == "").sum())


def _single_identity(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else ""


def _first_identity(row: pd.Series, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    return ""


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _strategy_key(strategy: object) -> str:
    key = _identity_key(strategy)
    aliases = {
        "lead_lag": "leadlag",
        "lead_lag_taker": "leadlag",
        "leadlag_taker": "leadlag",
        "leadlag_replay": "leadlag",
        "microprice": "imbalance",
        "microprice_imbalance": "imbalance",
        "order_book_imbalance": "imbalance",
        "obi": "imbalance",
        "surface": "surface_mm",
        "surface_market_making": "surface_mm",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _value_text(action_queue.iloc[0].get(column))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split_items(value: object) -> list[str]:
    text = _value_text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _value_text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _value_text(value)
    return f"`{text}`" if text else ""


def _value_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _value_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _value_int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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
