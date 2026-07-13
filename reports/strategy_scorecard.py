from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.evidence import (
    EVIDENCE_PROFILE_RUN_TYPES,
    EvidenceThresholds,
    evaluate_strategy_evidence,
    evidence_profile_run_types,
    _market_identity,
    _normalize_identity,
    _normalize_strategy,
    _strategy_identity,
)
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


DEFAULT_SCORECARD_PROFILES = ("leadlag", "imbalance", "parity", "settlement", "surface_mm")
RESEARCH_FAMILY_REQUIRED_ARTIFACTS = (
    "research_family_studies.csv",
    "research_family_checks.csv",
    "research_family_summary.csv",
    "research_family_action_queue.csv",
    "research_family_launch_attempt_census.csv",
    "research_family_config.json",
    "research_family_runbook.md",
)
PROFILE_STRATEGY_HINTS = {
    "leadlag": "lead_lag_taker",
    "imbalance": "imbalance",
    "provider_imbalance_research": "imbalance",
    "provider_imbalance_ops_launch": "imbalance",
    "parity": "parity_box",
    "settlement": "settlement_convergence",
    "surface_mm": "surface_mm",
}
READY_NEXT_GATES = {
    "ops_launch": "review-route-readiness",
    "provider_imbalance_ops_launch": "review-route-readiness",
    "provider_imbalance_research": "pipeline-imbalance-launch",
}
PROMOTION_NEXT_GATES = {
    "leadlag": "promote-leadlag-candidate",
    "imbalance": "promote-imbalance-candidate",
    "provider_imbalance_research": "promote-imbalance-candidate",
    "parity": "promote-parity-candidate",
    "settlement": "promote-settlement-candidate",
}
RUN_TYPE_NEXT_GATES = {
    "provider_market_data_research_handoff": "handoff-provider-market-data-research",
    "provider_market_data_imbalance_research": "run-provider-market-data-imbalance-research",
    "provider_market_data_imbalance_launch_packet": "pipeline-provider-market-data-imbalance-launch",
    "provider_market_data_imbalance_launch_evidence_review": "review-provider-market-data-imbalance-launch-evidence",
    "provider_market_data_imbalance_scorecard": "score-provider-market-data-imbalance-readiness",
    "provider_market_data_imbalance_route_readiness": "review-provider-market-data-imbalance-route-readiness",
    "provider_market_data_imbalance_scaleup_plan": "plan-provider-market-data-imbalance-scaleup",
    "provider_market_data_imbalance_runtime_telemetry_snapshot": "build-provider-market-data-imbalance-runtime-telemetry",
    "provider_market_data_imbalance_runtime_guard": "monitor-provider-market-data-imbalance-runtime-guard",
    "provider_market_data_imbalance_runtime_session": "monitor-provider-market-data-imbalance-runtime-session",
    "provider_market_data_imbalance_broker_readiness": "review-provider-market-data-imbalance-broker-readiness",
    "provider_market_data_imbalance_cutover": "review-provider-market-data-imbalance-cutover",
    "provider_market_data_imbalance_route_enable": "review-provider-market-data-imbalance-route-enable",
    "provider_market_data_imbalance_broker_dispatch": "plan-provider-market-data-imbalance-broker-dispatch",
    "provider_market_data_imbalance_broker_dispatch_send": (
        "prepare-provider-market-data-imbalance-broker-dispatch-send"
    ),
    "provider_market_data_imbalance_broker_dispatch_ack": (
        "reconcile-provider-market-data-imbalance-broker-dispatch"
    ),
    "provider_market_data_imbalance_broker_dispatch_roundtrip": (
        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
    ),
    "provider_market_data_imbalance_broker_rehearsal_certificate": (
        "certify-provider-market-data-imbalance-broker-rehearsal"
    ),
    "proof_report": "proof-report",
    "backtest_overfit_audit": "audit-backtest-overfit",
    "backtest_significance_audit": "audit-backtest-significance",
    "backtest_holdout_audit": "audit-backtest-holdout",
    "research_family_audit": "audit-research-family",
    "research_family_registration": "register-research-family",
    "research_family_launch_matrix": "plan-research-family-launches",
    "robust_selection_pipeline": "pipeline-robust-selection",
    "proof_refresh_gate": "review-proof-refresh",
    "stress_report": "stress-replay",
    "promotion_report": "promote-scenario",
    "shadow_session_comparison": "compare-shadow-sessions",
    "leadlag_edge_audit": "audit-leadlag-edge",
    "leadlag_replay_walkforward": "walkforward-leadlag-replay",
    "leadlag_order_plan": "plan-leadlag-orders",
    "leadlag_launch_pipeline": "pipeline-leadlag-launch",
    "imbalance_edge_walkforward": "walkforward-imbalance-edge",
    "imbalance_replay_walkforward": "walkforward-imbalance-replay",
    "imbalance_research_pipeline": "pipeline-imbalance-research",
    "imbalance_order_plan": "plan-imbalance-orders",
    "imbalance_launch_pipeline": "pipeline-imbalance-launch",
    "parity_edge_audit": "audit-parity-edge",
    "parity_sweep": "sweep-parity",
    "parity_order_plan": "plan-parity-orders",
    "parity_launch_pipeline": "pipeline-parity-launch",
    "settlement_convergence_walkforward": "walkforward-settlement-convergence",
    "settlement_order_plan": "plan-settlement-orders",
    "settlement_launch_pipeline": "pipeline-settlement-launch",
    "surface_quality_report": "review-surface-quality",
    "quote_risk_report": "review-quotes",
    "surface_mm_research_pipeline": "pipeline-surface-mm-research",
    "surface_mm_launch_pipeline": "pipeline-surface-mm-launch",
    "scaleup_plan": "plan-scaleup",
    "runtime_telemetry_snapshot": "build-runtime-telemetry",
    "runtime_guard": "monitor-scaleup-guard",
    "runtime_session_monitor": "monitor-runtime-session",
    "broker_vendor_data_readiness_pipeline": "pipeline-broker-vendor-readiness",
    "broker_readiness": "review-broker-readiness",
    "cutover_gate": "review-cutover-gate",
    "route_enable_packet": "review-route-enable",
    "broker_dispatch_plan": "plan-broker-dispatch",
    "broker_dispatch_send_packet": "prepare-broker-dispatch-send",
    "broker_dispatch_ack_reconciliation": "reconcile-broker-dispatch",
    "broker_dispatch_roundtrip": "review-broker-dispatch-roundtrip",
}
NEXT_GATE_HELP_COMMANDS = {
    gate: f"python -m hft_cli {gate} --help"
    for gate in sorted({*READY_NEXT_GATES.values(), *PROMOTION_NEXT_GATES.values(), *RUN_TYPE_NEXT_GATES.values()})
}


@dataclass(frozen=True)
class StrategyScorecardThresholds:
    profiles: tuple[str, ...] = DEFAULT_SCORECARD_PROFILES
    expected_market: str | None = None
    expected_ops_strategy: str | None = None
    allow_dirty_git: bool = False
    require_file_inputs: bool = False
    require_research_family: bool = False


@dataclass(frozen=True)
class StrategyScorecardReport:
    scorecard: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    action_queue: pd.DataFrame | None = None
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_scorecard(
    catalog: pd.DataFrame,
    *,
    thresholds: StrategyScorecardThresholds | None = None,
    research_family: dict[str, Any] | None = None,
) -> StrategyScorecardReport:
    thresholds = thresholds or StrategyScorecardThresholds()
    _validate_thresholds(thresholds)
    family = research_family or _empty_research_family_evidence()
    rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    for profile in thresholds.profiles:
        profile_key = _profile_key(profile)
        expected_strategy = _expected_strategy(profile_key, thresholds)
        expected_market = _normalize_identity(thresholds.expected_market)
        profile_catalog = _filter_catalog(catalog, strategy=expected_strategy, market=expected_market)
        required_run_types = evidence_profile_run_types(profile_key)
        evidence = evaluate_strategy_evidence(
            profile_catalog,
            thresholds=EvidenceThresholds(
                required_run_types=required_run_types,
                allow_dirty_git=thresholds.allow_dirty_git,
                require_same_strategy=bool(expected_strategy) or _is_ops_launch_profile(profile_key),
                require_same_market=bool(expected_market),
                expected_strategy=expected_strategy or None,
                expected_market=expected_market or None,
                require_file_inputs=thresholds.require_file_inputs,
                require_no_blocked_placeholder_schema=_is_ops_launch_profile(profile_key),
                require_broker_roundtrip_portfolio_safe=_is_ops_launch_profile(profile_key),
                fail_on_broker_roundtrip_portfolio_breach=_is_ops_launch_profile(profile_key),
                require_broker_roundtrip_portfolio_concentration_ok=_is_ops_launch_profile(profile_key),
                fail_on_broker_roundtrip_portfolio_concentration_breach=_is_ops_launch_profile(profile_key),
                require_broker_roundtrip_resume_route_ready=_is_ops_launch_profile(profile_key),
                fail_on_broker_roundtrip_resume_route_breach=_is_ops_launch_profile(profile_key),
                require_provider_broker_roundtrip_synthetic_sidecar_ready=(
                    _is_provider_imbalance_ops_launch_profile(profile_key)
                ),
                fail_on_provider_broker_roundtrip_synthetic_sidecar_breach=(
                    _is_provider_imbalance_ops_launch_profile(profile_key)
                ),
            ),
        )
        row = _scorecard_row(profile_key, expected_strategy, expected_market, evidence)
        family_gate = _research_family_profile_gate(
            profile_key,
            row,
            profile_catalog,
            required_run_types,
            family,
            required=thresholds.require_research_family,
        )
        rows.append(_apply_research_family_gate(row, family_gate))
        gap_rows.extend(_gap_rows(profile_key, expected_strategy, expected_market, evidence.evidence))
        family_gap = _research_family_gap_row(
            profile_key,
            expected_strategy,
            expected_market,
            family_gate,
        )
        if family_gap is not None:
            gap_rows.append(family_gap)

    scorecard = _rank_scorecard(pd.DataFrame(rows))
    gaps = pd.DataFrame(gap_rows)
    summary = _summary(scorecard)
    config = _config(scorecard, gaps, summary)
    action_queue = _action_queue(config)
    return StrategyScorecardReport(
        scorecard=scorecard,
        gaps=gaps,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_strategy_scorecard(
    catalog_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: StrategyScorecardThresholds | None = None,
    research_family_path: str | Path | None = None,
) -> StrategyScorecardReport:
    catalog_file = _catalog_path(catalog_path)
    catalog = pd.read_csv(catalog_file)
    thresholds = thresholds or StrategyScorecardThresholds()
    research_family = _load_research_family_evidence(research_family_path)
    report = evaluate_strategy_scorecard(
        catalog,
        thresholds=thresholds,
        research_family=research_family,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.scorecard.to_csv(out / "strategy_scorecard.csv", index=False)
    report.gaps.to_csv(out / "strategy_scorecard_gaps.csv", index=False)
    report.summary.to_csv(out / "strategy_scorecard_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.config)
    action_queue.to_csv(out / "strategy_scorecard_action_queue.csv", index=False)
    (out / "strategy_scorecard_next_actions.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "strategy_scorecard_runbook.md").write_text(
        _runbook_markdown(report.config),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"catalog": catalog_file}
    if research_family.get("provided", False):
        family_root = Path(str(research_family["path"]))
        inputs["research_family_audit"] = family_root
        family_manifest = family_root / "manifest.json"
        if family_manifest.is_file():
            inputs["research_family_manifest"] = family_manifest
    write_experiment_manifest(
        out,
        run_type="strategy_scorecard",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            "research_family_required": bool(
                thresholds.require_research_family
            ),
            "research_family_provided": bool(
                research_family.get("provided", False)
            ),
            "research_family_valid": bool(research_family.get("valid", False)),
            "research_family_id": str(research_family.get("family_id", "")),
            "research_family_manifest_sha256": str(
                research_family.get("manifest_sha256", "")
            ),
            "registered_research_profiles": int(
                report.summary.iloc[0].get("registered_research_profiles", 0)
            ),
            "research_family_gate_passed_profiles": int(
                report.summary.iloc[0].get(
                    "research_family_gate_passed_profiles",
                    0,
                )
            ),
            "research_family_gate_blocked_profiles": int(
                report.summary.iloc[0].get(
                    "research_family_gate_blocked_profiles",
                    0,
                )
            ),
            "authorizes_submission": False,
        },
    )
    return StrategyScorecardReport(
        scorecard=report.scorecard,
        gaps=report.gaps,
        summary=report.summary,
        config=report.config,
        action_queue=action_queue,
        output_dir=out,
    )


def _empty_research_family_evidence(path: str = "") -> dict[str, Any]:
    return {
        "provided": False,
        "valid": False,
        "path": path,
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_current": False,
        "manifest_error": "",
        "generated_at_utc": "",
        "family_id": "",
        "registration_id": "",
        "passed": False,
        "prospective_registration_passed": False,
        "registration_closed": False,
        "family_wise_error_control_claimed": False,
        "selection_consistent": False,
        "non_authorizing": False,
        "candidates": [],
        "reason": "research family audit was not provided",
    }


def _load_research_family_evidence(
    raw_path: str | Path | None,
) -> dict[str, Any]:
    if raw_path is None:
        return _empty_research_family_evidence()
    candidate = Path(raw_path).resolve()
    root = (
        candidate
        if candidate.is_dir() or not candidate.exists()
        else candidate.parent
    )
    evidence = _empty_research_family_evidence(str(root))
    evidence["provided"] = True
    manifest_path = root / "manifest.json"
    evidence["manifest_path"] = str(manifest_path)
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type="research_family_audit",
        required_artifacts=RESEARCH_FAMILY_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    evidence["manifest_current"] = bool(integrity.passed)
    evidence["manifest_error"] = str(integrity.error)
    evidence["manifest_sha256"] = (
        file_sha256(manifest_path) if manifest_path.is_file() else ""
    )
    manifest = _read_json_object(manifest_path)
    evidence["generated_at_utc"] = str(manifest.get("generated_at_utc", ""))
    summary = _read_first_row(root / "research_family_summary.csv")
    studies = _read_frame(root / "research_family_studies.csv")
    config = _read_json_object(root / "research_family_config.json")

    family_id = _value_text(summary.get("family_id", ""))
    registration_id = _value_text(summary.get("registration_id", ""))
    passed = _to_bool(summary.get("passed", False))
    prospective = _to_bool(
        summary.get("prospective_registration_passed", False)
    )
    registration_closed = _to_bool(summary.get("registration_closed", False))
    family_wise = _to_bool(
        summary.get("family_wise_error_control_claimed", False)
    )
    selected = config.get("selected_candidates", [])
    selected_records = selected if isinstance(selected, list) else []
    family_passed = (
        studies.get("family_passed", pd.Series(False, index=studies.index))
        .map(_to_bool)
        if not studies.empty
        else pd.Series(dtype=bool)
    )
    surviving = studies.loc[family_passed].copy() if not studies.empty else studies
    surviving_labels = sorted(
        surviving.get("study_label", pd.Series(dtype=str)).astype(str).tolist()
    )
    selected_labels = sorted(
        _value_text(item.get("study_label", ""))
        for item in selected_records
        if isinstance(item, dict)
    )
    selected_by_label = {
        _value_text(item.get("study_label", "")): item
        for item in selected_records
        if isinstance(item, dict) and _value_text(item.get("study_label", ""))
    }
    selected_rows_match = bool(
        surviving_labels
        and all(
            label in selected_by_label
            and _normalize_strategy(
                _value_text(selected_by_label[label].get("strategy", ""))
            )
            == _normalize_strategy(_value_text(row.get("strategy", "")))
            and _normalize_identity(
                _value_text(selected_by_label[label].get("market", ""))
            )
            == _normalize_identity(_value_text(row.get("market", "")))
            and _candidate_identity(
                selected_by_label[label].get("candidate_scenario", "")
            )
            == _candidate_identity(row.get("candidate_scenario", ""))
            and _to_bool(selected_by_label[label].get("family_passed", False))
            for label, (_, row) in zip(
                surviving_labels,
                surviving.sort_values("study_label").iterrows(),
            )
        )
    )
    selection_consistent = bool(
        passed
        and surviving_labels
        and surviving_labels == selected_labels
        and selected_rows_match
        and int(_numeric(summary.get("family_candidate_count", 0)))
        == len(surviving_labels)
        and _to_bool(config.get("passed", False))
    )
    candidates = [
        {
            "study_label": _value_text(row.get("study_label", "")),
            "strategy": _normalize_strategy(_value_text(row.get("strategy", ""))),
            "market": _normalize_identity(_value_text(row.get("market", ""))),
            "candidate_scenario": _value_text(
                row.get("candidate_scenario", "")
            ),
            "candidate_identity": _candidate_identity(
                row.get("candidate_scenario", "")
            ),
            "holm_adjusted_pvalue": float(
                _numeric(row.get("holm_adjusted_pvalue", 0.0))
            ),
        }
        for _, row in surviving.iterrows()
    ]
    manifest_extra = manifest.get("extra", {})
    extra = manifest_extra if isinstance(manifest_extra, dict) else {}
    non_authorizing = bool(
        not _to_bool(summary.get("authorizes_submission", False))
        and not _to_bool(config.get("authorizes_submission", False))
        and not _to_bool(extra.get("authorizes_submission", False))
        and not (
            studies.get(
                "source_authorizes_submission",
                pd.Series(False, index=studies.index),
            )
            .map(_to_bool)
            .any()
            if not studies.empty
            else False
        )
    )
    config_parameters = config.get("parameters", {})
    parameters = config_parameters if isinstance(config_parameters, dict) else {}
    config_summary_value = config.get("summary", {})
    config_summary = (
        config_summary_value if isinstance(config_summary_value, dict) else {}
    )
    family_identity_consistent = bool(
        family_id
        and family_id == _value_text(parameters.get("family_id", ""))
        and family_id == _value_text(config_summary.get("family_id", ""))
        and family_id == _value_text(extra.get("family_id", ""))
        and registration_id
        == _value_text(config_summary.get("registration_id", ""))
        and registration_id == _value_text(extra.get("registration_id", ""))
        and registration_closed
        == _to_bool(config_summary.get("registration_closed", False))
        and registration_closed
        == _to_bool(extra.get("registration_closed", False))
    )
    valid = bool(
        integrity.passed
        and passed
        and prospective
        and registration_closed
        and family_wise
        and registration_id
        and family_identity_consistent
        and selection_consistent
        and non_authorizing
        and candidates
    )
    if not integrity.passed:
        reason = f"research family manifest is not current: {integrity.error}"
    elif not passed:
        reason = "research family audit is blocked"
    elif not prospective or not registration_closed:
        reason = "research family prospective registration is not closed"
    elif not family_wise:
        reason = "research family does not claim complete family-wise error control"
    elif not family_identity_consistent or not registration_id:
        reason = "research family identity or registration binding is invalid"
    elif not selection_consistent:
        reason = "research family selected candidates differ from its study ledger"
    elif not non_authorizing:
        reason = "research family unexpectedly claims submission authority"
    elif not candidates:
        reason = "research family has no surviving candidates"
    else:
        reason = ""
    evidence.update(
        {
            "valid": valid,
            "family_id": family_id,
            "registration_id": registration_id,
            "passed": passed,
            "prospective_registration_passed": prospective,
            "registration_closed": registration_closed,
            "family_wise_error_control_claimed": family_wise,
            "selection_consistent": selection_consistent,
            "non_authorizing": non_authorizing,
            "candidates": candidates,
            "reason": reason,
        }
    )
    return evidence


def _research_family_profile_gate(
    profile: str,
    scorecard_row: dict[str, Any],
    catalog: pd.DataFrame,
    required_run_types: tuple[str, ...],
    family: dict[str, Any],
    *,
    required: bool,
) -> dict[str, Any]:
    applicable = not _is_ops_launch_profile(profile)
    provided = bool(family.get("provided", False))
    registered_research = _catalog_has_registered_research(catalog)
    enabled = bool(
        applicable and (required or provided or registered_research)
    )
    strategy = _normalize_strategy(_value_text(scorecard_row.get("strategy", "")))
    market = _normalize_identity(_value_text(scorecard_row.get("market", "")))
    candidate_identities = _catalog_candidate_identities(
        catalog,
        required_run_types,
    )
    candidate_consistent = len(candidate_identities) == 1
    candidate_identity = (
        next(iter(candidate_identities)) if candidate_consistent else ""
    )
    family_candidates = family.get("candidates", [])
    candidate_records = (
        family_candidates if isinstance(family_candidates, list) else []
    )
    strategy_market_matches = [
        item
        for item in candidate_records
        if isinstance(item, dict)
        and _normalize_strategy(_value_text(item.get("strategy", ""))) == strategy
        and _normalize_identity(_value_text(item.get("market", ""))) == market
    ]
    exact_matches = [
        item
        for item in strategy_market_matches
        if _value_text(item.get("candidate_identity", "")) == candidate_identity
    ]
    candidate_match = bool(
        candidate_consistent and candidate_identity and len(exact_matches) == 1
    )
    if not enabled:
        passed = True
        reason = ""
    elif not provided:
        passed = False
        reason = "a current registered research family audit is required"
    elif not family.get("valid", False):
        passed = False
        reason = _value_text(family.get("reason", ""))
    elif not candidate_consistent:
        passed = False
        reason = (
            "passed strategy evidence lacks one consistent candidate identity"
        )
    elif not strategy_market_matches:
        passed = False
        reason = (
            "research family has no surviving candidate for the scorecard "
            "strategy and market"
        )
    elif not candidate_match:
        passed = False
        reason = (
            "scorecard candidate is not an exact research-family survivor"
        )
    else:
        passed = True
        reason = ""
    matched = exact_matches[0] if len(exact_matches) == 1 else {}
    return {
        "applicable": applicable,
        "enabled": enabled,
        "required": bool((required or registered_research) and applicable),
        "registered_research_detected": registered_research,
        "provided": provided,
        "passed": passed,
        "reason": reason,
        "manifest_current": bool(family.get("manifest_current", False)),
        "family_valid": bool(family.get("valid", False)),
        "family_id": _value_text(family.get("family_id", "")),
        "registration_id": _value_text(family.get("registration_id", "")),
        "family_path": _value_text(family.get("path", "")),
        "manifest_sha256": _value_text(family.get("manifest_sha256", "")),
        "registration_closed": bool(family.get("registration_closed", False)),
        "family_wise_error_control_claimed": bool(
            family.get("family_wise_error_control_claimed", False)
        ),
        "candidate_identity": candidate_identity,
        "candidate_identity_count": len(candidate_identities),
        "candidate_consistent": candidate_consistent,
        "candidate_match": candidate_match,
        "matched_study_label": _value_text(matched.get("study_label", "")),
        "matched_holm_adjusted_pvalue": float(
            _numeric(matched.get("holm_adjusted_pvalue", 0.0))
        ),
        "generated_at_utc": _value_text(family.get("generated_at_utc", "")),
    }


def _apply_research_family_gate(
    row: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    result = dict(row)
    enabled = bool(gate.get("enabled", False))
    gate_passed = bool(gate.get("passed", False))
    if enabled:
        required_count = int(_numeric(result.get("required_run_type_count", 0))) + 1
        passed_count = int(_numeric(result.get("passed_required_run_types", 0)))
        if gate_passed:
            passed_count += 1
        result["required_run_type_count"] = required_count
        result["passed_required_run_types"] = passed_count
        result["readiness_score"] = (
            passed_count / required_count if required_count else 0.0
        )
        result["ready"] = bool(result.get("ready", False) and gate_passed)
        if not gate_passed:
            target = (
                "missing_required_run_types"
                if not gate.get("provided", False)
                else "blocked_required_run_types"
            )
            result[target] = _append_item(
                result.get(target, ""),
                "research_family_audit",
            )
            result["evidence_failed_checks"] = _append_item(
                result.get("evidence_failed_checks", ""),
                "research_family_gate",
            )
            if not _value_text(result.get("evidence_first_failed_reason", "")):
                result["evidence_first_failed_reason"] = _value_text(
                    gate.get("reason", "")
                )
            if not _value_text(result.get("next_required_run_type", "")):
                result["next_required_run_type"] = "research_family_audit"
                result["next_gate"] = _next_gate(
                    _value_text(result.get("profile", "")),
                    False,
                    "research_family_audit",
                )
                result["next_gate_help_command"] = _next_gate_help_command(
                    _value_text(result.get("next_gate", ""))
                )
            result["recommendation"] = "close_registered_research_family"
    result.update(
        {
            "research_family_applicable": bool(gate.get("applicable", False)),
            "research_family_enabled": enabled,
            "research_family_required": bool(gate.get("required", False)),
            "registered_research_detected": bool(
                gate.get("registered_research_detected", False)
            ),
            "research_family_provided": bool(gate.get("provided", False)),
            "research_family_gate_passed": gate_passed,
            "research_family_reason": _value_text(gate.get("reason", "")),
            "research_family_manifest_current": bool(
                gate.get("manifest_current", False)
            ),
            "research_family_valid": bool(gate.get("family_valid", False)),
            "research_family_id": _value_text(gate.get("family_id", "")),
            "research_family_registration_id": _value_text(
                gate.get("registration_id", "")
            ),
            "research_family_path": _value_text(gate.get("family_path", "")),
            "research_family_manifest_sha256": _value_text(
                gate.get("manifest_sha256", "")
            ),
            "research_family_registration_closed": bool(
                gate.get("registration_closed", False)
            ),
            "research_family_error_control_claimed": bool(
                gate.get("family_wise_error_control_claimed", False)
            ),
            "research_family_candidate_identity": _value_text(
                gate.get("candidate_identity", "")
            ),
            "research_family_candidate_identity_count": int(
                _numeric(gate.get("candidate_identity_count", 0))
            ),
            "research_family_candidate_consistent": bool(
                gate.get("candidate_consistent", False)
            ),
            "research_family_candidate_match": bool(
                gate.get("candidate_match", False)
            ),
            "research_family_matched_study_label": _value_text(
                gate.get("matched_study_label", "")
            ),
            "research_family_matched_holm_adjusted_pvalue": float(
                _numeric(gate.get("matched_holm_adjusted_pvalue", 0.0))
            ),
            "authorizes_submission": False,
        }
    )
    return result


def _research_family_gap_row(
    profile: str,
    expected_strategy: str,
    expected_market: str,
    gate: dict[str, Any],
) -> dict[str, Any] | None:
    if not gate.get("enabled", False):
        return None
    passed = bool(gate.get("passed", False))
    provided = bool(gate.get("provided", False))
    return {
        "profile": profile,
        "strategy": expected_strategy,
        "market": expected_market,
        "required_run_type": "research_family_audit",
        "passed": passed,
        "passed_runs": 1 if passed else 0,
        "failed_runs": 1 if provided and not passed else 0,
        "unknown_status_runs": 0,
        "total_runs": 1 if provided else 0,
        "latest_status": passed,
        "latest_generated_at_utc": _value_text(
            gate.get("generated_at_utc", "")
        ),
        "latest_run_dir": _value_text(gate.get("family_path", "")),
        "next_gate": "" if passed else "audit-research-family",
        "next_gate_help_command": (
            ""
            if passed
            else _next_gate_help_command("audit-research-family")
        ),
        "gap": (
            ""
            if passed
            else (
                "missing_required_run_type"
                if not provided
                else "required_run_type_not_passing"
            )
        ),
    }


def _scorecard_row(
    profile: str,
    expected_strategy: str,
    expected_market: str,
    evidence: Any,
) -> dict[str, Any]:
    summary = evidence.summary.iloc[0].to_dict() if not evidence.summary.empty else {}
    items = evidence.evidence.copy()
    required_count = int(summary.get("required_run_type_count", len(items)))
    passed_count = int(summary.get("passed_required_run_types", 0))
    missing = items.loc[items["total_runs"].astype(int) == 0, "required_run_type"].astype(str).tolist()
    blocked = items.loc[
        (items["total_runs"].astype(int) > 0) & (~items["passed"].astype(bool)),
        "required_run_type",
    ].astype(str).tolist()
    latest_generated = _latest_generated_at(items)
    score = passed_count / required_count if required_count else 0.0
    ready = bool(summary.get("ready", False))
    next_required_run_type = _next_required_run_type(items)
    evidence_failed_checks = _failed_evidence_checks(evidence.checks)
    return {
        "profile": profile,
        "strategy": expected_strategy or str(summary.get("strategy", "")),
        "market": expected_market or str(summary.get("market", "")),
        "ready": ready,
        "readiness_score": float(score),
        "passed_required_run_types": passed_count,
        "required_run_type_count": required_count,
        "missing_required_run_types": ";".join(missing),
        "blocked_required_run_types": ";".join(blocked),
        "next_required_run_type": next_required_run_type,
        "next_gate": _next_gate(profile, ready, next_required_run_type),
        "next_gate_help_command": _next_gate_help_command(_next_gate(profile, ready, next_required_run_type)),
        "failed_checks": int(_numeric(summary.get("failed_checks", 0))),
        "evidence_failed_checks": ";".join(evidence_failed_checks),
        "evidence_first_failed_reason": _first_evidence_failed_reason(evidence.checks),
        "broker_roundtrip_portfolio_safe_runs": int(
            _numeric(summary.get("broker_roundtrip_portfolio_safe_runs", 0))
        ),
        "broker_roundtrip_portfolio_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_portfolio_breach_runs", 0))
        ),
        "broker_roundtrip_portfolio_concentration_runs": int(
            _numeric(summary.get("broker_roundtrip_portfolio_concentration_runs", 0))
        ),
        "broker_roundtrip_portfolio_concentration_ok_runs": int(
            _numeric(summary.get("broker_roundtrip_portfolio_concentration_ok_runs", 0))
        ),
        "broker_roundtrip_portfolio_concentration_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_portfolio_concentration_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_ready_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_ready_runs", 0))
        ),
        "broker_roundtrip_resume_route_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_gap_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_gap_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_launch_control_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_launch_control_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_portfolio_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_portfolio_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_concentration_breach_runs": int(
            _numeric(summary.get("broker_roundtrip_resume_route_concentration_breach_runs", 0))
        ),
        "provider_broker_roundtrip_runs": int(
            _numeric(summary.get("provider_broker_roundtrip_runs", 0))
        ),
        "provider_broker_roundtrip_passed_runs": int(
            _numeric(summary.get("provider_broker_roundtrip_passed_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_dataset_count": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_dataset_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_count": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_sidecar_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_readable_count": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_sidecar_readable_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_sidecar_ready_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(
            _numeric(summary.get("provider_broker_roundtrip_synthetic_sidecar_breach_runs", 0))
        ),
        "require_provider_lineage_selection": bool(
            summary.get("require_provider_lineage_selection", False)
        ),
        "provider_lineage_selection_policy": str(
            summary.get("provider_lineage_selection_policy", "not_applicable")
        ),
        "provider_lineage_required_run_type_count": int(
            _numeric(summary.get("provider_lineage_required_run_type_count", 0))
        ),
        "provider_lineage_covered_run_type_count": int(
            _numeric(summary.get("provider_lineage_covered_run_type_count", 0))
        ),
        "provider_lineage_selectable_runs": int(
            _numeric(summary.get("provider_lineage_selectable_runs", 0))
        ),
        "provider_lineage_selection_blocked_runs": int(
            _numeric(summary.get("provider_lineage_selection_blocked_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_passed_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_passed_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_live_dryrun_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_live_dryrun_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_authorizing_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_authorizing_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_non_authorizing_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_non_authorizing_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_hashed_runs": int(
            _numeric(summary.get("provider_broker_rehearsal_certificate_hashed_runs", 0))
        ),
        "dirty_runs": int(_numeric(summary.get("dirty_runs", 0))),
        "git_commit_count": int(_numeric(summary.get("git_commit_count", 0))),
        "latest_generated_at_utc": latest_generated,
        "recommendation": _score_recommendation(profile, ready, score),
    }


def _gap_rows(
    profile: str,
    expected_strategy: str,
    expected_market: str,
    evidence: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in evidence.to_dict(orient="records"):
        total_runs = int(_numeric(row.get("total_runs", 0)))
        passed = bool(row.get("passed", False))
        required_run_type = row.get("required_run_type", "")
        rows.append(
            {
                "profile": profile,
                "strategy": expected_strategy,
                "market": expected_market,
                "required_run_type": required_run_type,
                "passed": passed,
                "passed_runs": int(_numeric(row.get("passed_runs", 0))),
                "failed_runs": int(_numeric(row.get("failed_runs", 0))),
                "unknown_status_runs": int(_numeric(row.get("unknown_status_runs", 0))),
                "total_runs": total_runs,
                "latest_status": bool(row.get("latest_status", False)),
                "latest_generated_at_utc": row.get("latest_generated_at_utc", ""),
                "latest_run_dir": row.get("latest_run_dir", ""),
                "next_gate": "" if passed else _next_gate(profile, False, str(required_run_type)),
                "next_gate_help_command": ""
                if passed
                else _next_gate_help_command(_next_gate(profile, False, str(required_run_type))),
                "gap": "" if passed else ("missing_required_run_type" if total_runs == 0 else "required_run_type_not_passing"),
            }
        )
    return rows


def _summary(scorecard: pd.DataFrame) -> pd.DataFrame:
    if scorecard.empty:
        return pd.DataFrame(
            [
                {
                    "ready": False,
                    "profile_count": 0,
                    "ready_profiles": 0,
                    "blocked_profiles": 0,
                    "best_profile": "",
                    "best_strategy": "",
                    "best_market": "",
                    "best_readiness_score": 0.0,
                    "best_next_required_run_type": "",
                    "best_next_gate": "",
                    "best_next_gate_help_command": "",
                    "ready_profile_names": "",
                    "blocked_profile_names": "",
                    "failed_check_count": 0,
                    "failed_check_names": "",
                    "first_failed_reason": "",
                    "primary_blocker_check": "",
                    "primary_blocker_value": "",
                    "primary_blocker_operator": "",
                    "primary_blocker_threshold": "",
                    "primary_blocker_reason": "",
                    "primary_blocker_profile": "",
                    "primary_blocker_strategy": "",
                    "primary_blocker_next_gate": "",
                    "primary_blocker_next_gate_help_command": "",
                    "research_family_enabled_profiles": 0,
                    "registered_research_profiles": 0,
                    "research_family_required_profiles": 0,
                    "research_family_provided_profiles": 0,
                    "research_family_gate_passed_profiles": 0,
                    "research_family_gate_blocked_profiles": 0,
                    "research_family_id": "",
                    "research_family_registration_id": "",
                    "research_family_path": "",
                    "research_family_manifest_sha256": "",
                    "authorizes_submission": False,
                    "recommendation": "no_profiles_to_score",
                }
            ]
        )
    ready = scorecard.loc[scorecard["ready"].astype(bool)]
    blocked = scorecard.loc[~scorecard["ready"].astype(bool)]
    best = scorecard.sort_values(
        ["ready", "readiness_score", "passed_required_run_types", "latest_generated_at_utc"],
        ascending=[False, False, False, False],
    ).iloc[0]
    has_ready = not ready.empty
    primary_blocker = _first_blocked_profile(blocked)
    family_enabled = scorecard["research_family_enabled"].map(_to_bool)
    registered_research = scorecard["registered_research_detected"].map(_to_bool)
    family_required = scorecard["research_family_required"].map(_to_bool)
    family_provided = scorecard["research_family_provided"].map(_to_bool)
    family_passed = scorecard["research_family_gate_passed"].map(_to_bool)
    family_rows = scorecard.loc[family_enabled]
    family_reference = (
        family_rows.iloc[0] if not family_rows.empty else pd.Series(dtype=object)
    )
    return pd.DataFrame(
        [
            {
                "ready": has_ready,
                "profile_count": int(len(scorecard)),
                "ready_profiles": int(len(ready)),
                "blocked_profiles": int(len(blocked)),
                "best_profile": best["profile"],
                "best_strategy": best["strategy"],
                "best_market": best["market"],
                "best_readiness_score": float(best["readiness_score"]),
                "best_next_required_run_type": best["next_required_run_type"],
                "best_next_gate": best["next_gate"],
                "best_next_gate_help_command": best["next_gate_help_command"],
                "ready_profile_names": ";".join(ready["profile"].astype(str).tolist()),
                "blocked_profile_names": ";".join(blocked["profile"].astype(str).tolist()),
                "failed_check_count": int(len(blocked)),
                "failed_check_names": _blocked_check_names(blocked),
                "first_failed_reason": _blocked_reason(primary_blocker),
                "primary_blocker_check": _blocked_check_name(primary_blocker),
                "primary_blocker_value": _blocked_check_value(primary_blocker),
                "primary_blocker_operator": _blocked_operator(primary_blocker),
                "primary_blocker_threshold": _blocked_threshold(primary_blocker),
                "primary_blocker_reason": _blocked_reason(primary_blocker),
                "primary_blocker_profile": _text(primary_blocker.get("profile", "")) if not primary_blocker.empty else "",
                "primary_blocker_strategy": _text(primary_blocker.get("strategy", "")) if not primary_blocker.empty else "",
                "primary_blocker_next_gate": _text(primary_blocker.get("next_gate", "")) if not primary_blocker.empty else "",
                "primary_blocker_next_gate_help_command": _text(primary_blocker.get("next_gate_help_command", ""))
                if not primary_blocker.empty
                else "",
                "research_family_enabled_profiles": int(family_enabled.sum()),
                "registered_research_profiles": int(registered_research.sum()),
                "research_family_required_profiles": int(family_required.sum()),
                "research_family_provided_profiles": int(
                    (family_enabled & family_provided).sum()
                ),
                "research_family_gate_passed_profiles": int(
                    (family_enabled & family_passed).sum()
                ),
                "research_family_gate_blocked_profiles": int(
                    (family_enabled & ~family_passed).sum()
                ),
                "research_family_id": _value_text(
                    family_reference.get("research_family_id", "")
                ),
                "research_family_registration_id": _value_text(
                    family_reference.get(
                        "research_family_registration_id",
                        "",
                    )
                ),
                "research_family_path": _value_text(
                    family_reference.get("research_family_path", "")
                ),
                "research_family_manifest_sha256": _value_text(
                    family_reference.get(
                        "research_family_manifest_sha256",
                        "",
                    )
                ),
                "authorizes_submission": False,
                "recommendation": _summary_recommendation(str(best["profile"]), has_ready),
            }
        ]
    )


def _config(scorecard: pd.DataFrame, gaps: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    summary_row = _jsonable_row(summary.iloc[0].to_dict()) if not summary.empty else {}
    next_actions = [_action(row) for row in _records(scorecard)]
    ready_actions = [action for action in next_actions if action["ready"]]
    blocked_actions = [action for action in next_actions if not action["ready"]]
    primary_action = next_actions[0] if next_actions else {}
    primary_blocker = _first_blocked_action(blocked_actions)
    failed_checks = [_blocked_action_check_name(action) for action in blocked_actions]
    gap_actions = [_gap_action(row) for row in _records(gaps) if str(row.get("gap", ""))]
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "best_profile": str(summary_row.get("best_profile", "")),
        "best_strategy": str(summary_row.get("best_strategy", "")),
        "best_market": str(summary_row.get("best_market", "")),
        "best_next_required_run_type": str(summary_row.get("best_next_required_run_type", "")),
        "best_next_gate": str(summary_row.get("best_next_gate", "")),
        "best_next_gate_help_command": str(summary_row.get("best_next_gate_help_command", "")),
        "next_gate": str(summary_row.get("best_next_gate", "")),
        "next_gate_help_command": str(summary_row.get("best_next_gate_help_command", "")),
        "recommendation": str(summary_row.get("recommendation", "")),
        "ready_action_count": len(ready_actions),
        "blocked_action_count": len(blocked_actions),
        "gap_count": len(gap_actions),
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "first_failed_reason": _blocked_action_reason(primary_blocker),
        "primary_blocker": _primary_blocker_record(primary_blocker),
        "primary_action_status": _primary_action_status(primary_action),
        "primary_action": primary_action,
        "research_family_enabled_profiles": int(
            _numeric(summary_row.get("research_family_enabled_profiles", 0))
        ),
        "registered_research_profiles": int(
            _numeric(summary_row.get("registered_research_profiles", 0))
        ),
        "research_family_required_profiles": int(
            _numeric(summary_row.get("research_family_required_profiles", 0))
        ),
        "research_family_provided_profiles": int(
            _numeric(summary_row.get("research_family_provided_profiles", 0))
        ),
        "research_family_gate_passed_profiles": int(
            _numeric(
                summary_row.get("research_family_gate_passed_profiles", 0)
            )
        ),
        "research_family_gate_blocked_profiles": int(
            _numeric(
                summary_row.get("research_family_gate_blocked_profiles", 0)
            )
        ),
        "research_family_id": str(summary_row.get("research_family_id", "")),
        "research_family_registration_id": str(
            summary_row.get("research_family_registration_id", "")
        ),
        "research_family_path": str(
            summary_row.get("research_family_path", "")
        ),
        "research_family_manifest_sha256": str(
            summary_row.get("research_family_manifest_sha256", "")
        ),
        "authorizes_submission": False,
        "next_actions": next_actions,
        "ready_actions": ready_actions,
        "blocked_actions": blocked_actions,
        "gaps": gap_actions,
    }


def _first_blocked_profile(blocked: pd.DataFrame) -> pd.Series:
    if blocked.empty:
        return pd.Series(dtype=object)
    return blocked.iloc[0]


def _blocked_check_names(blocked: pd.DataFrame) -> str:
    if blocked.empty:
        return ""
    return ";".join(_blocked_check_name(row) for _, row in blocked.iterrows())


def _blocked_check_name(row: pd.Series) -> str:
    if row.empty:
        return ""
    return f"profile_ready:{_text(row.get('profile', ''))}"


def _blocked_check_value(row: pd.Series) -> object:
    if row.empty:
        return ""
    return bool(row.get("ready", False))


def _blocked_operator(row: pd.Series) -> str:
    return "" if row.empty else "is"


def _blocked_threshold(row: pd.Series) -> object:
    return "" if row.empty else True


def _blocked_reason(row: pd.Series) -> str:
    if row.empty:
        return ""
    profile = _text(row.get("profile"))
    missing = _split_items(row.get("missing_required_run_types", ""))
    blocked = _split_items(row.get("blocked_required_run_types", ""))
    evidence_failed = _split_items(row.get("evidence_failed_checks", ""))
    if missing:
        if missing[0] == "research_family_audit":
            family_reason = _value_text(row.get("research_family_reason", ""))
            if family_reason:
                return family_reason
        return f"{profile} profile is missing required run type {missing[0]}"
    if blocked:
        if blocked[0] == "research_family_audit":
            family_reason = _value_text(row.get("research_family_reason", ""))
            if family_reason:
                return family_reason
        return f"{profile} profile has non-passing required run type {blocked[0]}"
    if evidence_failed:
        return f"{profile} profile failed evidence check {evidence_failed[0]}"
    next_required = _text(row.get("next_required_run_type"))
    if next_required:
        return f"{profile} profile is blocked at required run type {next_required}"
    return f"{profile} profile is not ready"


def _first_blocked_action(blocked_actions: list[dict[str, Any]]) -> dict[str, Any]:
    return blocked_actions[0] if blocked_actions else {}


def _blocked_action_check_name(action: dict[str, Any]) -> str:
    profile = str(action.get("profile", ""))
    return f"profile_ready:{profile}" if profile else "profile_ready"


def _blocked_action_reason(action: dict[str, Any]) -> str:
    if not action:
        return ""
    profile = str(action.get("profile", ""))
    missing = action.get("missing_required_run_types")
    blocked = action.get("blocked_required_run_types")
    evidence_failed = action.get("evidence_failed_checks")
    missing_items = missing if isinstance(missing, list) else _split_items(missing)
    blocked_items = blocked if isinstance(blocked, list) else _split_items(blocked)
    evidence_failed_items = evidence_failed if isinstance(evidence_failed, list) else _split_items(evidence_failed)
    if missing_items:
        if missing_items[0] == "research_family_audit":
            family_reason = str(action.get("research_family_reason", ""))
            if family_reason:
                return family_reason
        return f"{profile} profile is missing required run type {missing_items[0]}"
    if blocked_items:
        if blocked_items[0] == "research_family_audit":
            family_reason = str(action.get("research_family_reason", ""))
            if family_reason:
                return family_reason
        return f"{profile} profile has non-passing required run type {blocked_items[0]}"
    if evidence_failed_items:
        return f"{profile} profile failed evidence check {evidence_failed_items[0]}"
    next_required = str(action.get("next_required_run_type", ""))
    if next_required:
        return f"{profile} profile is blocked at required run type {next_required}"
    return f"{profile} profile is not ready"


def _primary_blocker_record(action: dict[str, Any]) -> dict[str, Any]:
    if not action:
        return {}
    return {
        "check": _blocked_action_check_name(action),
        "passed": False,
        "profile": str(action.get("profile", "")),
        "strategy": str(action.get("strategy", "")),
        "market": str(action.get("market", "")),
        "value": bool(action.get("ready", False)),
        "operator": "is",
        "threshold": True,
        "reason": _blocked_action_reason(action),
        "readiness_score": float(_numeric(action.get("readiness_score", 0.0))),
        "next_required_run_type": str(action.get("next_required_run_type", "")),
        "next_gate": str(action.get("next_gate", "")),
        "next_gate_help_command": str(action.get("next_gate_help_command", "")),
        "missing_required_run_types": action.get("missing_required_run_types", []),
        "blocked_required_run_types": action.get("blocked_required_run_types", []),
        "evidence_failed_checks": action.get("evidence_failed_checks", []),
        "evidence_first_failed_reason": str(action.get("evidence_first_failed_reason", "")),
        "research_family_gate_passed": bool(
            action.get("research_family_gate_passed", False)
        ),
        "research_family_reason": str(
            action.get("research_family_reason", "")
        ),
        "research_family_id": str(action.get("research_family_id", "")),
        "research_family_matched_study_label": str(
            action.get("research_family_matched_study_label", "")
        ),
    }


def _primary_action_status(action: dict[str, Any]) -> str:
    if not action:
        return ""
    return "ready" if action.get("ready") else "blocked"


def _action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(_numeric(row.get("rank", 0))),
        "profile": str(row.get("profile", "")),
        "strategy": str(row.get("strategy", "")),
        "market": str(row.get("market", "")),
        "ready": bool(row.get("ready", False)),
        "readiness_score": float(_numeric(row.get("readiness_score", 0.0))),
        "passed_required_run_types": int(_numeric(row.get("passed_required_run_types", 0))),
        "required_run_type_count": int(_numeric(row.get("required_run_type_count", 0))),
        "next_required_run_type": str(row.get("next_required_run_type", "")),
        "next_gate": str(row.get("next_gate", "")),
        "next_gate_help_command": str(row.get("next_gate_help_command", "")),
        "missing_required_run_types": _split_items(row.get("missing_required_run_types", "")),
        "blocked_required_run_types": _split_items(row.get("blocked_required_run_types", "")),
        "evidence_failed_checks": _split_items(row.get("evidence_failed_checks", "")),
        "evidence_first_failed_reason": str(row.get("evidence_first_failed_reason", "")),
        "research_family_enabled": bool(
            row.get("research_family_enabled", False)
        ),
        "research_family_required": bool(
            row.get("research_family_required", False)
        ),
        "registered_research_detected": bool(
            row.get("registered_research_detected", False)
        ),
        "research_family_provided": bool(
            row.get("research_family_provided", False)
        ),
        "research_family_gate_passed": bool(
            row.get("research_family_gate_passed", False)
        ),
        "research_family_reason": str(row.get("research_family_reason", "")),
        "research_family_manifest_current": bool(
            row.get("research_family_manifest_current", False)
        ),
        "research_family_valid": bool(row.get("research_family_valid", False)),
        "research_family_id": str(row.get("research_family_id", "")),
        "research_family_registration_id": str(
            row.get("research_family_registration_id", "")
        ),
        "research_family_path": str(row.get("research_family_path", "")),
        "research_family_manifest_sha256": str(
            row.get("research_family_manifest_sha256", "")
        ),
        "research_family_candidate_identity": str(
            row.get("research_family_candidate_identity", "")
        ),
        "research_family_candidate_match": bool(
            row.get("research_family_candidate_match", False)
        ),
        "research_family_matched_study_label": str(
            row.get("research_family_matched_study_label", "")
        ),
        "research_family_matched_holm_adjusted_pvalue": float(
            _numeric(
                row.get("research_family_matched_holm_adjusted_pvalue", 0.0)
            )
        ),
        "broker_roundtrip_portfolio_safe_runs": int(
            _numeric(row.get("broker_roundtrip_portfolio_safe_runs", 0))
        ),
        "broker_roundtrip_portfolio_breach_runs": int(
            _numeric(row.get("broker_roundtrip_portfolio_breach_runs", 0))
        ),
        "broker_roundtrip_portfolio_concentration_ok_runs": int(
            _numeric(row.get("broker_roundtrip_portfolio_concentration_ok_runs", 0))
        ),
        "broker_roundtrip_portfolio_concentration_breach_runs": int(
            _numeric(row.get("broker_roundtrip_portfolio_concentration_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_ready_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_ready_runs", 0))
        ),
        "broker_roundtrip_resume_route_breach_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_gap_breach_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_gap_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_launch_control_breach_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_launch_control_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_portfolio_breach_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_portfolio_breach_runs", 0))
        ),
        "broker_roundtrip_resume_route_concentration_breach_runs": int(
            _numeric(row.get("broker_roundtrip_resume_route_concentration_breach_runs", 0))
        ),
        "provider_broker_roundtrip_runs": int(
            _numeric(row.get("provider_broker_roundtrip_runs", 0))
        ),
        "provider_broker_roundtrip_passed_runs": int(
            _numeric(row.get("provider_broker_roundtrip_passed_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_dataset_count": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_dataset_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_count": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_sidecar_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_readable_count": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_sidecar_readable_count", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_sidecar_proof_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_sidecar_ready_runs", 0))
        ),
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(
            _numeric(row.get("provider_broker_roundtrip_synthetic_sidecar_breach_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_passed_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_passed_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_live_dryrun_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_live_dryrun_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_authorizing_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_authorizing_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_non_authorizing_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_non_authorizing_runs", 0))
        ),
        "provider_broker_rehearsal_certificate_hashed_runs": int(
            _numeric(row.get("provider_broker_rehearsal_certificate_hashed_runs", 0))
        ),
        "recommendation": str(row.get("recommendation", "")),
        "authorizes_submission": False,
    }


def _gap_action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": str(row.get("profile", "")),
        "strategy": str(row.get("strategy", "")),
        "market": str(row.get("market", "")),
        "required_run_type": str(row.get("required_run_type", "")),
        "gap": str(row.get("gap", "")),
        "next_gate": str(row.get("next_gate", "")),
        "next_gate_help_command": str(row.get("next_gate_help_command", "")),
        "passed_runs": int(_numeric(row.get("passed_runs", 0))),
        "failed_runs": int(_numeric(row.get("failed_runs", 0))),
        "unknown_status_runs": int(_numeric(row.get("unknown_status_runs", 0))),
        "latest_run_dir": str(row.get("latest_run_dir", "")),
    }


def _action_queue(config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for priority, action in enumerate(config.get("next_actions", []), start=1):
        if not isinstance(action, dict):
            continue
        rows.append(
            {
                "priority": priority,
                "queue_status": "ready" if bool(action.get("ready", False)) else "blocked",
                "profile": str(action.get("profile", "")),
                "strategy": str(action.get("strategy", "")),
                "market": str(action.get("market", "")),
                "readiness_score": float(_numeric(action.get("readiness_score", 0.0))),
                "passed_required_run_types": int(_numeric(action.get("passed_required_run_types", 0))),
                "required_run_type_count": int(_numeric(action.get("required_run_type_count", 0))),
                "next_required_run_type": str(action.get("next_required_run_type", "")),
                "next_gate": str(action.get("next_gate", "")),
                "next_gate_help_command": str(action.get("next_gate_help_command", "")),
                "missing_required_run_types": _list_text(action.get("missing_required_run_types")),
                "blocked_required_run_types": _list_text(action.get("blocked_required_run_types")),
                "evidence_failed_checks": _list_text(action.get("evidence_failed_checks")),
                "evidence_first_failed_reason": str(action.get("evidence_first_failed_reason", "")),
                "research_family_required": bool(
                    action.get("research_family_required", False)
                ),
                "registered_research_detected": bool(
                    action.get("registered_research_detected", False)
                ),
                "research_family_provided": bool(
                    action.get("research_family_provided", False)
                ),
                "research_family_gate_passed": bool(
                    action.get("research_family_gate_passed", False)
                ),
                "research_family_reason": str(
                    action.get("research_family_reason", "")
                ),
                "research_family_id": str(
                    action.get("research_family_id", "")
                ),
                "research_family_matched_study_label": str(
                    action.get("research_family_matched_study_label", "")
                ),
                "recommendation": str(action.get("recommendation", "")),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "profile",
            "strategy",
            "market",
            "readiness_score",
            "passed_required_run_types",
            "required_run_type_count",
            "next_required_run_type",
            "next_gate",
            "next_gate_help_command",
            "missing_required_run_types",
            "blocked_required_run_types",
            "evidence_failed_checks",
            "evidence_first_failed_reason",
            "research_family_required",
            "registered_research_detected",
            "research_family_provided",
            "research_family_gate_passed",
            "research_family_reason",
            "research_family_id",
            "research_family_matched_study_label",
            "recommendation",
        ],
    )


def _runbook_markdown(config: dict[str, Any]) -> str:
    ready_label = "yes" if bool(config.get("ready", False)) else "no"
    lines = [
        "# Strategy Scorecard Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Best profile: {_text(config.get('best_profile'))}",
        f"- Best strategy: {_text(config.get('best_strategy'))}",
        f"- Best market: {_text(config.get('best_market'))}",
        f"- Recommendation: {_text(config.get('recommendation'))}",
        f"- Best next gate: {_code(config.get('best_next_gate'))}",
        f"- Best next gate help: {_code(config.get('best_next_gate_help_command'))}",
        f"- Ready actions: {int(_numeric(config.get('ready_action_count', 0)))}",
        f"- Blocked actions: {int(_numeric(config.get('blocked_action_count', 0)))}",
        f"- Open gaps: {int(_numeric(config.get('gap_count', 0)))}",
        "- Research-family gated profiles: "
        f"{int(_numeric(config.get('research_family_enabled_profiles', 0)))}",
        "- Registered-research profiles: "
        f"{int(_numeric(config.get('registered_research_profiles', 0)))}",
        "- Research-family passed profiles: "
        f"{int(_numeric(config.get('research_family_gate_passed_profiles', 0)))}",
        f"- Research family: {_code(config.get('research_family_id'))}",
        "- Authorizes submission: false",
        "",
        "## Ready Actions",
        "",
        _actions_table(config.get("ready_actions", []), include_gaps=False),
        "",
        "## Blocked Actions",
        "",
        _actions_table(config.get("blocked_actions", []), include_gaps=True),
        "",
        "## Open Gaps",
        "",
        _gaps_table(config.get("gaps", [])),
        "",
    ]
    return "\n".join(lines)


def _actions_table(actions: Any, *, include_gaps: bool) -> str:
    rows = actions if isinstance(actions, list) else []
    if not rows:
        return "_None_"
    headers = [
        "Rank",
        "Profile",
        "Strategy",
        "Score",
        "Family gate",
        "Next gate",
        "Help",
    ]
    table_rows = [
        [
            str(int(_numeric(row.get("rank", 0)))),
            _text(row.get("profile")),
            _text(row.get("strategy")),
            _format_score(row.get("readiness_score")),
            (
                "passed"
                if row.get("research_family_enabled")
                and row.get("research_family_gate_passed")
                else (
                    "blocked"
                    if row.get("research_family_enabled")
                    else "not required"
                )
            ),
            _code(row.get("next_gate")),
            _code(row.get("next_gate_help_command")),
        ]
        for row in rows
        if isinstance(row, dict)
    ]
    if include_gaps:
        headers.extend(["Missing", "Blocked", "Failed checks"])
        for row, source in zip(table_rows, rows):
            if isinstance(source, dict):
                row.extend(
                    [
                        _list_text(source.get("missing_required_run_types")),
                        _list_text(source.get("blocked_required_run_types")),
                        _list_text(source.get("evidence_failed_checks")),
                    ]
                )
    return _markdown_table(headers, table_rows)


def _gaps_table(gaps: Any) -> str:
    rows = gaps if isinstance(gaps, list) else []
    if not rows:
        return "_None_"
    return _markdown_table(
        ["Profile", "Required run type", "Gap", "Next gate", "Latest run"],
        [
            [
                _text(row.get("profile")),
                _text(row.get("required_run_type")),
                _text(row.get("gap")),
                _code(row.get("next_gate")),
                _text(row.get("latest_run_dir")),
            ]
            for row in rows
            if isinstance(row, dict)
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _format_score(value: Any) -> str:
    return f"{_numeric(value):.3f}"


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item) for item in value if str(item)]
    else:
        items = _split_items(value)
    return ", ".join(items)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _rank_scorecard(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ranked = frame.sort_values(
        ["ready", "readiness_score", "passed_required_run_types", "latest_generated_at_utc", "profile"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1, dtype=int))
    return ranked


def _filter_catalog(catalog: pd.DataFrame, *, strategy: str, market: str) -> pd.DataFrame:
    if catalog.empty:
        return catalog.copy()
    frame = catalog.copy()
    keep = []
    for _, row in frame.iterrows():
        keep.append(_matches_identity(row, strategy=strategy, market=market))
    return frame.loc[keep].copy()


def _matches_identity(row: pd.Series, *, strategy: str, market: str) -> bool:
    if strategy and _strategy_identity(row) != strategy:
        return False
    if market and _market_identity(row) != market:
        return False
    return True


def _profile_key(profile: str) -> str:
    required_run_types = evidence_profile_run_types(profile)
    for key, value in EVIDENCE_PROFILE_RUN_TYPES.items():
        if tuple(value) == tuple(required_run_types):
            return key
    return _normalize_identity(profile)


def _expected_strategy(profile: str, thresholds: StrategyScorecardThresholds) -> str:
    if _is_ops_launch_profile(profile):
        return _normalize_strategy(thresholds.expected_ops_strategy) or _normalize_strategy(
            PROFILE_STRATEGY_HINTS.get(profile, "")
        )
    return _normalize_strategy(PROFILE_STRATEGY_HINTS.get(profile, ""))


def _is_ops_launch_profile(profile: str) -> bool:
    return profile in {"ops_launch", "provider_imbalance_ops_launch"}


def _is_provider_imbalance_ops_launch_profile(profile: str) -> bool:
    return profile == "provider_imbalance_ops_launch"


def _latest_generated_at(items: pd.DataFrame) -> str:
    if items.empty or "latest_generated_at_utc" not in items.columns:
        return ""
    values = [str(value) for value in items["latest_generated_at_utc"].dropna() if str(value)]
    return max(values) if values else ""


def _failed_evidence_checks(checks: pd.DataFrame) -> list[str]:
    if checks.empty or "passed" not in checks.columns or "check" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool), "check"]
    return [str(value) for value in failed.dropna().tolist() if str(value)]


def _first_evidence_failed_reason(checks: pd.DataFrame) -> str:
    if checks.empty or "passed" not in checks.columns or "reason" not in checks.columns:
        return ""
    failed = checks.loc[~checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    return str(failed.iloc[0].get("reason", ""))


def _next_required_run_type(items: pd.DataFrame) -> str:
    if items.empty or "passed" not in items.columns:
        return ""
    gaps = items.loc[~items["passed"].astype(bool)]
    if gaps.empty:
        return ""
    return str(gaps.iloc[0].get("required_run_type", ""))


def _next_gate(profile: str, ready: bool, required_run_type: str) -> str:
    if ready:
        return READY_NEXT_GATES.get(profile, "plan-scaleup")
    if required_run_type == "promotion_report":
        return PROMOTION_NEXT_GATES.get(profile, RUN_TYPE_NEXT_GATES[required_run_type])
    return RUN_TYPE_NEXT_GATES.get(required_run_type, "review-strategy-evidence")


def _next_gate_help_command(next_gate: str) -> str:
    if not next_gate:
        return ""
    return NEXT_GATE_HELP_COMMANDS.get(next_gate, f"python -m hft_cli {next_gate} --help")


def _score_recommendation(profile: str, ready: bool, score: float) -> str:
    if ready:
        if _is_ops_launch_profile(profile):
            return "ready_for_live_dryrun_route_review"
        return "ready_for_shadow_scaleup_review"
    if score <= 0:
        if _is_ops_launch_profile(profile):
            return "start_ops_launch_evidence"
        return "start_profile_research_evidence"
    if score < 1:
        if _is_ops_launch_profile(profile):
            return "complete_ops_launch_evidence_gaps"
        return "complete_profile_evidence_gaps"
    if _is_ops_launch_profile(profile):
        return "review_ops_launch_checks"
    return "review_profile_checks"


def _summary_recommendation(best_profile: str, has_ready: bool) -> str:
    if not has_ready:
        return "complete_missing_research_evidence"
    if _is_ops_launch_profile(best_profile):
        return "promote_ready_route_to_live_dryrun_review"
    return "promote_ready_strategy_to_shadow_scaleup_review"


def _catalog_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "experiment_catalog.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"experiment catalog not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: StrategyScorecardThresholds) -> None:
    if not thresholds.profiles:
        raise ValueError("profiles must not be empty")
    for profile in thresholds.profiles:
        evidence_profile_run_types(profile)


def _split_items(value: Any) -> list[str]:
    return [item for item in str(value).split(";") if item]


def _append_item(value: Any, item: str) -> str:
    items = _split_items(value)
    if item not in items:
        items.append(item)
    return ";".join(items)


def _catalog_candidate_identities(
    catalog: pd.DataFrame,
    required_run_types: tuple[str, ...],
) -> set[str]:
    if catalog.empty or "run_type" not in catalog.columns:
        return set()
    run_types = catalog["run_type"].astype(str)
    status = (
        catalog["summary_status"].map(_to_bool)
        if "summary_status" in catalog.columns
        else pd.Series(False, index=catalog.index)
    )
    passed = catalog.loc[run_types.isin(required_run_types) & status]
    candidate_columns = (
        "summary_candidate_scenario_key",
        "summary_candidate_scenario",
        "summary_selected_scenario_key",
        "summary_best_scenario_key",
        "summary_scenario_key",
        "scenario_key",
    )
    identities: set[str] = set()
    for _, row in passed.iterrows():
        value = ""
        for column in candidate_columns:
            if column in row.index:
                value = _value_text(row.get(column, ""))
                if value:
                    break
        identity = _candidate_identity(value)
        if identity:
            identities.add(identity)
    return identities


def _catalog_has_registered_research(catalog: pd.DataFrame) -> bool:
    if catalog.empty or "run_type" not in catalog.columns:
        return False
    robust = catalog.loc[
        catalog["run_type"].astype(str).eq("robust_selection_pipeline")
    ]
    if robust.empty:
        return False
    status = (
        robust["summary_status"].map(_to_bool)
        if "summary_status" in robust.columns
        else pd.Series(False, index=robust.index)
    )
    registration_passed = (
        robust["summary_research_registration_passed"].map(_to_bool)
        if "summary_research_registration_passed" in robust.columns
        else pd.Series(False, index=robust.index)
    )
    registration_ids = (
        robust["summary_research_registration_id"].map(_value_text)
        if "summary_research_registration_id" in robust.columns
        else pd.Series("", index=robust.index)
    )
    study_labels = (
        robust["summary_registered_study_label"].map(_value_text)
        if "summary_registered_study_label" in robust.columns
        else pd.Series("", index=robust.index)
    )
    return bool(
        (status & registration_passed & registration_ids.ne("") & study_labels.ne(""))
        .any()
    )


def _candidate_identity(value: Any) -> str:
    text = _value_text(value).strip()
    if not text:
        return ""
    parsed: dict[str, str] = {}
    for part in text.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        normalized_key = _normalize_identity(key)
        normalized_value = item.strip().casefold()
        if (
            normalized_key
            and normalized_value
            and normalized_key not in {"strategy", "market", "profile"}
        ):
            parsed[normalized_key] = normalized_value
    if parsed:
        return "|".join(
            f"{key}={parsed[key]}" for key in sorted(parsed)
        )
    return text.casefold()


def _read_frame(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _read_first_row(path: Path) -> pd.Series:
    frame = _read_frame(path)
    return frame.iloc[0] if not frame.empty else pd.Series(dtype=object)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "y", "passed", "ready"}:
            return True
        if normalized in {"0", "false", "no", "n", "blocked"}:
            return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number
