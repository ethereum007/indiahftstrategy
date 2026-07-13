from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


DEFAULT_REQUIRED_RUN_TYPES = ("proof_report", "stress_report", "promotion_report")
LEADLAG_REQUIRED_RUN_TYPES = (
    "leadlag_edge_audit",
    "leadlag_replay_walkforward",
    "stress_report",
    "promotion_report",
    "leadlag_order_plan",
    "leadlag_launch_pipeline",
)
IMBALANCE_REQUIRED_RUN_TYPES = (
    "imbalance_edge_walkforward",
    "imbalance_replay_walkforward",
    "promotion_report",
    "imbalance_research_pipeline",
    "imbalance_order_plan",
    "imbalance_launch_pipeline",
)
PROVIDER_IMBALANCE_RESEARCH_REQUIRED_RUN_TYPES = (
    "provider_market_data_research_handoff",
    "imbalance_edge_walkforward",
    "imbalance_replay_walkforward",
    "promotion_report",
    "imbalance_research_pipeline",
    "provider_market_data_imbalance_research",
)
SETTLEMENT_REQUIRED_RUN_TYPES = (
    "settlement_convergence_walkforward",
    "promotion_report",
    "settlement_order_plan",
    "settlement_launch_pipeline",
)
PARITY_REQUIRED_RUN_TYPES = (
    "parity_edge_audit",
    "parity_sweep",
    "promotion_report",
    "parity_order_plan",
    "parity_launch_pipeline",
)
SURFACE_MM_REQUIRED_RUN_TYPES = (
    "surface_quality_report",
    "quote_risk_report",
    "surface_mm_research_pipeline",
    "surface_mm_launch_pipeline",
)
OPS_LAUNCH_REQUIRED_RUN_TYPES = (
    "scaleup_plan",
    "runtime_telemetry_snapshot",
    "runtime_guard",
    "runtime_session_monitor",
    "broker_vendor_data_readiness_pipeline",
    "broker_readiness",
    "cutover_gate",
    "route_enable_packet",
    "broker_dispatch_plan",
    "broker_dispatch_send_packet",
    "broker_dispatch_ack_reconciliation",
    "broker_dispatch_roundtrip",
)
PROVIDER_IMBALANCE_OPS_LAUNCH_REQUIRED_RUN_TYPES = (
    "provider_market_data_imbalance_scorecard",
    "provider_market_data_imbalance_route_readiness",
    "provider_market_data_imbalance_scaleup_plan",
    "provider_market_data_imbalance_runtime_telemetry_snapshot",
    "provider_market_data_imbalance_runtime_guard",
    "provider_market_data_imbalance_runtime_session",
    "provider_market_data_imbalance_broker_readiness",
    "provider_market_data_imbalance_cutover",
    "provider_market_data_imbalance_route_enable",
    "provider_market_data_imbalance_broker_dispatch",
    "provider_market_data_imbalance_broker_dispatch_send",
    "provider_market_data_imbalance_broker_dispatch_ack",
    "provider_market_data_imbalance_broker_dispatch_roundtrip",
    "provider_market_data_imbalance_broker_rehearsal_certificate",
)
PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE = (
    "provider_market_data_imbalance_broker_rehearsal_certificate"
)
PROVIDER_ACTIVE_LINEAGE_RUN_TYPES = (
    "provider_market_data_imbalance_broker_dispatch_ack",
    "provider_market_data_imbalance_broker_dispatch_roundtrip",
    PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE,
)
PLACEHOLDER_SCHEMA_STATUS = "placeholder_normalized_pending_vendor_schema"
EVIDENCE_PROFILE_RUN_TYPES = {
    "default": DEFAULT_REQUIRED_RUN_TYPES,
    "leadlag": LEADLAG_REQUIRED_RUN_TYPES,
    "imbalance": IMBALANCE_REQUIRED_RUN_TYPES,
    "provider_imbalance_research": PROVIDER_IMBALANCE_RESEARCH_REQUIRED_RUN_TYPES,
    "provider_imbalance_ops_launch": PROVIDER_IMBALANCE_OPS_LAUNCH_REQUIRED_RUN_TYPES,
    "settlement": SETTLEMENT_REQUIRED_RUN_TYPES,
    "parity": PARITY_REQUIRED_RUN_TYPES,
    "surface_mm": SURFACE_MM_REQUIRED_RUN_TYPES,
    "ops_launch": OPS_LAUNCH_REQUIRED_RUN_TYPES,
}
EVIDENCE_PROFILE_ALIASES = {
    "lead_lag": "leadlag",
    "lead_lag_taker": "leadlag",
    "leadlag_taker": "leadlag",
    "microprice_imbalance": "imbalance",
    "imbalance_research": "provider_imbalance_research",
    "microprice_imbalance_research": "provider_imbalance_research",
    "provider_market_data_imbalance": "provider_imbalance_research",
    "provider_market_data_imbalance_research": "provider_imbalance_research",
    "provider_imbalance_live_dryrun": "provider_imbalance_ops_launch",
    "provider_market_data_imbalance_live_dryrun": "provider_imbalance_ops_launch",
    "provider_market_data_imbalance_ops_launch": "provider_imbalance_ops_launch",
    "provider_microprice_imbalance_ops_launch": "provider_imbalance_ops_launch",
    "settlement_convergence": "settlement",
    "parity_box": "parity",
    "surface_market_making": "surface_mm",
    "broker_dryrun": "ops_launch",
    "broker_dry_run": "ops_launch",
    "launch_ops": "ops_launch",
    "live_dryrun": "ops_launch",
    "live_dry_run": "ops_launch",
    "ops_launch_readiness": "ops_launch",
}


def evidence_profile_run_types(profile: str | None = None) -> tuple[str, ...]:
    key = _normalize_identity(profile or "default")
    key = EVIDENCE_PROFILE_ALIASES.get(key, key)
    if key not in EVIDENCE_PROFILE_RUN_TYPES:
        profiles = ", ".join(sorted(EVIDENCE_PROFILE_RUN_TYPES))
        raise ValueError(f"unknown evidence profile {profile!r}; expected one of: {profiles}")
    return EVIDENCE_PROFILE_RUN_TYPES[key]


@dataclass(frozen=True)
class EvidenceThresholds:
    required_run_types: tuple[str, ...] = DEFAULT_REQUIRED_RUN_TYPES
    min_passed_per_type: int = 1
    allow_dirty_git: bool = False
    require_same_git_commit: bool = False
    require_same_strategy: bool = False
    require_same_market: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None
    require_file_inputs: bool = False
    require_no_placeholder_schema: bool = False
    require_no_blocked_placeholder_schema: bool = False
    require_broker_roundtrip_portfolio_safe: bool = False
    fail_on_broker_roundtrip_portfolio_breach: bool = False
    require_broker_roundtrip_portfolio_concentration_ok: bool = False
    fail_on_broker_roundtrip_portfolio_concentration_breach: bool = False
    require_broker_roundtrip_resume_route_ready: bool = False
    fail_on_broker_roundtrip_resume_route_breach: bool = False
    require_provider_broker_roundtrip_synthetic_sidecar_ready: bool = False
    fail_on_provider_broker_roundtrip_synthetic_sidecar_breach: bool = False
    require_provider_lineage_selection: bool | None = None


@dataclass(frozen=True)
class StrategyEvidenceReview:
    evidence: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_evidence(
    catalog: pd.DataFrame,
    *,
    thresholds: EvidenceThresholds | None = None,
) -> StrategyEvidenceReview:
    thresholds = thresholds or EvidenceThresholds()
    _validate_thresholds(thresholds)
    frame = _normalize_catalog(catalog)
    evidence = pd.DataFrame([_evidence_row(frame, run_type, thresholds) for run_type in thresholds.required_run_types])
    checks = _checks(frame, evidence, thresholds)
    summary = _summary(frame, evidence, checks, thresholds)
    return StrategyEvidenceReview(evidence=evidence, checks=checks, summary=summary)


def write_strategy_evidence_review(
    catalog_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: EvidenceThresholds | None = None,
) -> StrategyEvidenceReview:
    catalog_file = _catalog_path(catalog_path)
    catalog = pd.read_csv(catalog_file)
    thresholds = thresholds or EvidenceThresholds()
    review = evaluate_strategy_evidence(catalog, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    review.evidence.to_csv(out / "strategy_evidence_items.csv", index=False)
    review.checks.to_csv(out / "strategy_evidence_checks.csv", index=False)
    review.summary.to_csv(out / "strategy_evidence_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="strategy_evidence_review",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"catalog": catalog_file},
    )
    return StrategyEvidenceReview(review.evidence, review.checks, review.summary, out)


def _evidence_row(catalog: pd.DataFrame, run_type: str, thresholds: EvidenceThresholds) -> dict[str, Any]:
    matched = catalog.loc[catalog["run_type"].astype(str) == run_type].copy()
    if matched.empty:
        return {
            "required_run_type": run_type,
            "total_runs": 0,
            "passed_runs": 0,
            "failed_runs": 0,
            "unknown_status_runs": 0,
            "latest_run_dir": "",
            "latest_status": False,
            "latest_generated_at_utc": "",
            "latest_git_commit": "",
            "passed": False,
        }
    matched["summary_status_bool"] = matched["summary_status"].map(_to_optional_bool)
    latest = _latest_row(matched)
    passed = matched.loc[matched["summary_status_bool"] == True]  # noqa: E712
    identity = _latest_row(passed) if not passed.empty else latest
    passed_runs = int((matched["summary_status_bool"] == True).sum())  # noqa: E712 - pandas scalar comparison
    failed_runs = int((matched["summary_status_bool"] == False).sum())  # noqa: E712
    unknown_runs = int(matched["summary_status_bool"].isna().sum())
    return {
        "required_run_type": run_type,
        "total_runs": int(len(matched)),
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "unknown_status_runs": unknown_runs,
        "latest_run_dir": str(latest.get("run_dir", "")),
        "latest_status": bool(_to_bool(latest.get("summary_status", False))),
        "latest_generated_at_utc": str(latest.get("generated_at_utc", "")),
        "latest_git_commit": str(latest.get("git_commit", "")),
        "latest_strategy": _strategy_identity(identity),
        "latest_market": _market_identity(identity),
        "latest_input_count": int(_numeric(latest.get("input_count", 0))),
        "latest_input_file_count": int(_numeric(latest.get("input_file_count", 0))),
        "latest_input_directory_count": int(_numeric(latest.get("input_directory_count", 0))),
        "latest_input_other_count": int(_numeric(latest.get("input_other_count", 0))),
        "latest_input_unfingerprinted_count": int(_numeric(latest.get("input_unfingerprinted_count", 0))),
        "passed": bool(passed_runs >= thresholds.min_passed_per_type),
    }


def _checks(catalog: pd.DataFrame, evidence: pd.DataFrame, thresholds: EvidenceThresholds) -> pd.DataFrame:
    rows = [
        _check(
            f"required_run_type:{row.required_run_type}",
            int(row.passed_runs),
            ">=",
            thresholds.min_passed_per_type,
            bool(row.passed),
            f"{row.required_run_type} does not have enough passed runs",
        )
        for row in evidence.itertuples(index=False)
    ]
    dirty_runs = int(catalog["git_dirty"].map(_to_bool).sum()) if not catalog.empty else 0
    if not thresholds.allow_dirty_git:
        rows.append(
            _check(
                "clean_git_artifacts",
                dirty_runs,
                "==",
                0,
                dirty_runs == 0,
                "catalog contains runs generated from a dirty git tree",
            )
        )
    if thresholds.require_same_git_commit:
        commits = _passed_required_commits(catalog, evidence)
        rows.append(
            _check(
                "same_git_commit",
                len(commits),
                "==",
                1,
                len(commits) == 1,
                "passed required evidence spans multiple git commits or no commit",
            )
        )
    passed_required = _passed_required_rows(catalog, evidence)
    if thresholds.require_same_strategy:
        strategies = _identity_values(passed_required, _strategy_identity)
        rows.append(
            _check(
                "same_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "count==",
                1,
                len(strategies) == 1 and _missing_identities(passed_required, _strategy_identity) == 0,
                "passed required evidence has missing or multiple strategy identities",
            )
        )
    if thresholds.expected_strategy is not None:
        expected = _normalize_strategy(thresholds.expected_strategy)
        strategies = _identity_values(passed_required, _strategy_identity)
        rows.append(
            _check(
                "expected_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "==",
                expected,
                strategies == {expected} and _missing_identities(passed_required, _strategy_identity) == 0,
                "passed required evidence does not match the expected strategy",
            )
        )
    if thresholds.require_same_market:
        markets = _identity_values(passed_required, _market_identity)
        rows.append(
            _check(
                "same_market",
                ";".join(sorted(markets)) if markets else "",
                "count==",
                1,
                len(markets) == 1 and _missing_identities(passed_required, _market_identity) == 0,
                "passed required evidence has missing or multiple market identities",
            )
        )
    if thresholds.expected_market is not None:
        expected = _normalize_identity(thresholds.expected_market)
        markets = _identity_values(passed_required, _market_identity)
        rows.append(
            _check(
                "expected_market",
                ";".join(sorted(markets)) if markets else "",
                "==",
                expected,
                markets == {expected} and _missing_identities(passed_required, _market_identity) == 0,
                "passed required evidence does not match the expected market",
            )
        )
    if thresholds.require_file_inputs:
        broad_inputs = _input_provenance_count(passed_required, "input_directory_count")
        other_inputs = _input_provenance_count(passed_required, "input_other_count")
        unfingerprinted_inputs = _input_provenance_count(passed_required, "input_unfingerprinted_count")
        non_file_inputs = broad_inputs + other_inputs + unfingerprinted_inputs
        rows.append(
            _check(
                "file_fingerprinted_inputs",
                non_file_inputs,
                "==",
                0,
                non_file_inputs == 0,
                "passed required evidence has directory, other, or unfingerprinted inputs",
            )
        )
    if thresholds.require_no_placeholder_schema:
        active_placeholders = _placeholder_schema_active_count(catalog)
        rows.append(
            _check(
                "placeholder_schema_active",
                active_placeholders,
                "==",
                0,
                active_placeholders == 0,
                "catalog contains broker artifacts still using placeholder schemas",
            )
        )
    if thresholds.require_no_blocked_placeholder_schema:
        blocked_placeholders = _placeholder_schema_blocked_count(catalog)
        rows.append(
            _check(
                "placeholder_schema_blocked",
                blocked_placeholders,
                "==",
                0,
                blocked_placeholders == 0,
                "catalog contains unreviewed placeholder broker schemas that were not explicitly allowed",
            )
        )
    if thresholds.require_broker_roundtrip_portfolio_safe:
        safe_roundtrips = _broker_roundtrip_portfolio_safe_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_portfolio_safe",
                safe_roundtrips,
                ">=",
                1,
                safe_roundtrips >= 1,
                "catalog does not contain a portfolio-safe broker dispatch round-trip proof",
            )
        )
    if thresholds.fail_on_broker_roundtrip_portfolio_breach:
        breach_roundtrips = _broker_roundtrip_portfolio_breach_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_portfolio_breach",
                breach_roundtrips,
                "==",
                0,
                breach_roundtrips == 0,
                "catalog contains broker dispatch round-trip notional above selected portfolio allocation",
            )
        )
    if thresholds.require_broker_roundtrip_portfolio_concentration_ok:
        concentration_ok_roundtrips = _broker_roundtrip_portfolio_concentration_ok_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_portfolio_concentration_ok",
                concentration_ok_roundtrips,
                ">=",
                1,
                concentration_ok_roundtrips >= 1,
                "catalog does not contain a concentration-ok broker dispatch round-trip proof",
            )
        )
    if thresholds.fail_on_broker_roundtrip_portfolio_concentration_breach:
        concentration_breach_roundtrips = _broker_roundtrip_portfolio_concentration_breach_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_portfolio_concentration_breach",
                concentration_breach_roundtrips,
                "==",
                0,
                concentration_breach_roundtrips == 0,
                "catalog contains broker dispatch round-trip concentration above selected portfolio limits",
            )
        )
    if thresholds.require_broker_roundtrip_resume_route_ready:
        resume_ready_roundtrips = _broker_roundtrip_resume_route_ready_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_resume_route_ready",
                resume_ready_roundtrips,
                ">=",
                1,
                resume_ready_roundtrips >= 1,
                "catalog does not contain a broker dispatch round-trip with ready primary and incident resume-route proof",
            )
        )
    if thresholds.fail_on_broker_roundtrip_resume_route_breach:
        resume_breach_roundtrips = _broker_roundtrip_resume_route_breach_count(catalog)
        rows.append(
            _check(
                "broker_roundtrip_resume_route_breach",
                resume_breach_roundtrips,
                "==",
                0,
                resume_breach_roundtrips == 0,
                "catalog contains broker dispatch round-trip resume-route proof with gaps, failed controls, or unsafe portfolio evidence",
            )
        )
    if thresholds.require_provider_broker_roundtrip_synthetic_sidecar_ready:
        ready_sidecar_roundtrips = _provider_broker_roundtrip_synthetic_sidecar_ready_count(catalog)
        rows.append(
            _check(
                "provider_broker_roundtrip_synthetic_sidecar_ready",
                ready_sidecar_roundtrips,
                ">=",
                1,
                ready_sidecar_roundtrips >= 1,
                "catalog does not contain provider broker round-trip proof with ready synthetic sidecars",
            )
        )
    if thresholds.fail_on_provider_broker_roundtrip_synthetic_sidecar_breach:
        breached_sidecar_roundtrips = _provider_broker_roundtrip_synthetic_sidecar_breach_count(catalog)
        rows.append(
            _check(
                "provider_broker_roundtrip_synthetic_sidecar_breach",
                breached_sidecar_roundtrips,
                "==",
                0,
                breached_sidecar_roundtrips == 0,
                "catalog contains provider broker round-trip proof with missing or unreadable synthetic sidecars",
            )
        )
    lineage_policy = _provider_lineage_selection_policy(thresholds)
    if lineage_policy == "required":
        selectable_by_type = _provider_lineage_selectable_counts(catalog, thresholds)
        for run_type in _required_provider_lineage_run_types(thresholds):
            selectable_runs = selectable_by_type.get(run_type, 0)
            rows.append(
                _check(
                    f"provider_lineage_selectable:{run_type}",
                    selectable_runs,
                    ">=",
                    thresholds.min_passed_per_type,
                    selectable_runs >= thresholds.min_passed_per_type,
                    f"{run_type} does not have enough passed active-lineage selectable proofs",
                )
            )
    elif lineage_policy == "audit_only":
        rows.append(
            _check(
                "provider_lineage_selection_audit_only",
                True,
                "is",
                False,
                False,
                "audit-only provider lineage review cannot authorize launch candidate selection",
            )
        )
    if PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE in thresholds.required_run_types:
        certificate_counts = _provider_broker_rehearsal_certificate_counts(catalog)
        rows.extend(
            [
                _check(
                    "provider_broker_rehearsal_certificate_live_dryrun",
                    certificate_counts["provider_broker_rehearsal_certificate_live_dryrun_runs"],
                    ">=",
                    thresholds.min_passed_per_type,
                    certificate_counts["provider_broker_rehearsal_certificate_live_dryrun_runs"]
                    >= thresholds.min_passed_per_type,
                    "catalog does not contain enough passed live_dryrun provider broker rehearsal certificates",
                ),
                _check(
                    "provider_broker_rehearsal_certificate_authorizing",
                    certificate_counts["provider_broker_rehearsal_certificate_authorizing_runs"],
                    "==",
                    0,
                    certificate_counts["provider_broker_rehearsal_certificate_authorizing_runs"] == 0,
                    "catalog contains a provider broker rehearsal certificate that claims submission authority",
                ),
                _check(
                    "provider_broker_rehearsal_certificate_non_authorizing",
                    certificate_counts[
                        "provider_broker_rehearsal_certificate_non_authorizing_runs"
                    ],
                    ">=",
                    thresholds.min_passed_per_type,
                    certificate_counts[
                        "provider_broker_rehearsal_certificate_non_authorizing_runs"
                    ]
                    >= thresholds.min_passed_per_type,
                    "catalog does not contain enough explicit non-authorizing provider broker rehearsal certificates",
                ),
                _check(
                    "provider_broker_rehearsal_certificate_hashed",
                    certificate_counts["provider_broker_rehearsal_certificate_hashed_runs"],
                    ">=",
                    thresholds.min_passed_per_type,
                    certificate_counts["provider_broker_rehearsal_certificate_hashed_runs"]
                    >= thresholds.min_passed_per_type,
                    "catalog does not contain enough provider broker rehearsal certificates with SHA-256 identity",
                ),
            ]
        )
    return pd.DataFrame(rows)


def _summary(
    catalog: pd.DataFrame,
    evidence: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: EvidenceThresholds,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    profile = _profile_identity(thresholds.required_run_types)
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    passed_required = int(evidence["passed"].astype(bool).sum()) if not evidence.empty else 0
    passed_required_rows = _passed_required_rows(catalog, evidence)
    strategies = _identity_values(passed_required_rows, _strategy_identity)
    markets = _identity_values(passed_required_rows, _market_identity)
    input_file_count = _input_provenance_count(passed_required_rows, "input_file_count")
    input_directory_count = _input_provenance_count(passed_required_rows, "input_directory_count")
    input_other_count = _input_provenance_count(passed_required_rows, "input_other_count")
    input_unfingerprinted_count = _input_provenance_count(passed_required_rows, "input_unfingerprinted_count")
    input_hashed_count = _input_provenance_count(passed_required_rows, "input_hashed_count")
    placeholder_active = _placeholder_schema_active_count(catalog)
    placeholder_blocked = _placeholder_schema_blocked_count(catalog)
    roundtrip_safe = _broker_roundtrip_portfolio_safe_count(catalog)
    roundtrip_breach = _broker_roundtrip_portfolio_breach_count(catalog)
    concentration_runs, concentration_ok, concentration_breach = _broker_roundtrip_portfolio_concentration_counts(
        catalog
    )
    resume_route_counts = _broker_roundtrip_resume_route_counts(catalog)
    provider_sidecar_counts = _provider_broker_roundtrip_synthetic_sidecar_counts(catalog)
    provider_certificate_counts = _provider_broker_rehearsal_certificate_counts(catalog)
    provider_lineage_counts = _provider_lineage_selection_counts(catalog, thresholds)
    provider_lineage_policy = _provider_lineage_selection_policy(thresholds)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_checks": failed,
                "recommendation": _recommendation(
                    profile,
                    ready,
                    provider_lineage_policy=provider_lineage_policy,
                ),
                "evidence_profile": profile,
                "run_count": int(len(catalog)),
                "required_run_types": ";".join(thresholds.required_run_types),
                "passed_required_run_types": passed_required,
                "required_run_type_count": int(len(thresholds.required_run_types)),
                "min_passed_per_type": int(thresholds.min_passed_per_type),
                "dirty_runs": int(catalog["git_dirty"].map(_to_bool).sum()) if not catalog.empty else 0,
                "git_commit_count": int(catalog["git_commit"].dropna().nunique()) if not catalog.empty else 0,
                "strategy": next(iter(strategies)) if len(strategies) == 1 else "",
                "strategy_count": int(len(strategies)),
                "missing_strategy_runs": _missing_identities(passed_required_rows, _strategy_identity),
                "expected_strategy": _normalize_strategy(thresholds.expected_strategy)
                if thresholds.expected_strategy is not None
                else "",
                "market": next(iter(markets)) if len(markets) == 1 else "",
                "market_count": int(len(markets)),
                "missing_market_runs": _missing_identities(passed_required_rows, _market_identity),
                "expected_market": _normalize_identity(thresholds.expected_market)
                if thresholds.expected_market is not None
                else "",
                "require_file_inputs": bool(thresholds.require_file_inputs),
                "require_no_placeholder_schema": bool(thresholds.require_no_placeholder_schema),
                "require_no_blocked_placeholder_schema": bool(thresholds.require_no_blocked_placeholder_schema),
                "require_broker_roundtrip_portfolio_safe": bool(
                    thresholds.require_broker_roundtrip_portfolio_safe
                ),
                "fail_on_broker_roundtrip_portfolio_breach": bool(
                    thresholds.fail_on_broker_roundtrip_portfolio_breach
                ),
                "require_broker_roundtrip_portfolio_concentration_ok": bool(
                    thresholds.require_broker_roundtrip_portfolio_concentration_ok
                ),
                "fail_on_broker_roundtrip_portfolio_concentration_breach": bool(
                    thresholds.fail_on_broker_roundtrip_portfolio_concentration_breach
                ),
                "require_broker_roundtrip_resume_route_ready": bool(
                    thresholds.require_broker_roundtrip_resume_route_ready
                ),
                "fail_on_broker_roundtrip_resume_route_breach": bool(
                    thresholds.fail_on_broker_roundtrip_resume_route_breach
                ),
                "require_provider_broker_roundtrip_synthetic_sidecar_ready": bool(
                    thresholds.require_provider_broker_roundtrip_synthetic_sidecar_ready
                ),
                "fail_on_provider_broker_roundtrip_synthetic_sidecar_breach": bool(
                    thresholds.fail_on_provider_broker_roundtrip_synthetic_sidecar_breach
                ),
                "require_provider_lineage_selection": provider_lineage_policy == "required",
                "provider_lineage_selection_policy": provider_lineage_policy,
                "provider_lineage_selection_audit_only": provider_lineage_policy == "audit_only",
                "placeholder_schema_active_runs": placeholder_active,
                "placeholder_schema_blocked_runs": placeholder_blocked,
                "broker_roundtrip_portfolio_safe_runs": roundtrip_safe,
                "broker_roundtrip_portfolio_breach_runs": roundtrip_breach,
                "broker_roundtrip_portfolio_concentration_runs": concentration_runs,
                "broker_roundtrip_portfolio_concentration_ok_runs": concentration_ok,
                "broker_roundtrip_portfolio_concentration_breach_runs": concentration_breach,
                **resume_route_counts,
                **provider_sidecar_counts,
                **provider_certificate_counts,
                **provider_lineage_counts,
                "input_file_count": input_file_count,
                "input_directory_count": input_directory_count,
                "input_other_count": input_other_count,
                "input_unfingerprinted_count": input_unfingerprinted_count,
                "input_hashed_count": input_hashed_count,
            }
        ]
    )


def _profile_identity(required_run_types: tuple[str, ...]) -> str:
    for profile, run_types in EVIDENCE_PROFILE_RUN_TYPES.items():
        if tuple(required_run_types) == tuple(run_types):
            return profile
    return "custom"


def _recommendation(
    profile: str,
    ready: bool,
    *,
    provider_lineage_policy: str = "not_applicable",
) -> str:
    if provider_lineage_policy == "audit_only":
        return "provider_lineage_audit_only"
    if profile in {"ops_launch", "provider_imbalance_ops_launch"}:
        return "eligible_for_live_dryrun_route_review" if ready else "ops_launch_evidence_incomplete"
    return "eligible_for_shadow_scaleup_review" if ready else "evidence_incomplete"


def _normalize_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    frame = catalog.copy()
    for column in [
        "run_dir",
        "run_type",
        "generated_at_utc",
        "git_commit",
        "git_dirty",
        "summary_status",
        "input_count",
        "input_file_count",
        "input_directory_count",
        "input_other_count",
        "input_unfingerprinted_count",
        "input_hashed_count",
        "provider_lineage_selection_status",
        "provider_lineage_selection_eligible",
    ]:
        if column not in frame.columns:
            frame[column] = False if column == "provider_lineage_selection_eligible" else np.nan
    for column in (
        "input_count",
        "input_file_count",
        "input_directory_count",
        "input_other_count",
        "input_unfingerprinted_count",
        "input_hashed_count",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def _required_provider_lineage_run_types(
    thresholds: EvidenceThresholds,
) -> tuple[str, ...]:
    supported = set(PROVIDER_ACTIVE_LINEAGE_RUN_TYPES)
    return tuple(
        run_type
        for run_type in thresholds.required_run_types
        if run_type in supported
    )


def _provider_lineage_selection_policy(thresholds: EvidenceThresholds) -> str:
    if not _required_provider_lineage_run_types(thresholds):
        return "not_applicable"
    if thresholds.require_provider_lineage_selection is False:
        return "audit_only"
    return "required"


def _provider_lineage_candidate_rows(
    catalog: pd.DataFrame,
    thresholds: EvidenceThresholds,
) -> pd.DataFrame:
    required = set(_required_provider_lineage_run_types(thresholds))
    if catalog.empty or not required:
        return catalog.iloc[0:0].copy()
    passed = _bool_column(catalog, "summary_status")
    return catalog.loc[
        catalog["run_type"].astype(str).isin(required) & passed
    ].copy()


def _provider_lineage_selectable_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    statuses = (
        frame["provider_lineage_selection_status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    return statuses.eq("selectable") & _bool_column(
        frame,
        "provider_lineage_selection_eligible",
    )


def _provider_lineage_selectable_counts(
    catalog: pd.DataFrame,
    thresholds: EvidenceThresholds,
) -> dict[str, int]:
    frame = _provider_lineage_candidate_rows(catalog, thresholds)
    selectable = _provider_lineage_selectable_mask(frame)
    return {
        run_type: int(
            (
                frame["run_type"].astype(str).eq(run_type)
                & selectable
            ).sum()
        )
        for run_type in _required_provider_lineage_run_types(thresholds)
    }


def _provider_lineage_selection_counts(
    catalog: pd.DataFrame,
    thresholds: EvidenceThresholds,
) -> dict[str, int]:
    required = _required_provider_lineage_run_types(thresholds)
    frame = _provider_lineage_candidate_rows(catalog, thresholds)
    selectable = _provider_lineage_selectable_mask(frame)
    statuses = (
        frame["provider_lineage_selection_status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    selectable_by_type = _provider_lineage_selectable_counts(catalog, thresholds)
    covered = sum(
        count >= thresholds.min_passed_per_type
        for count in selectable_by_type.values()
    )
    return {
        "provider_lineage_required_run_type_count": int(len(required)),
        "provider_lineage_covered_run_type_count": int(covered),
        "provider_lineage_missing_run_type_count": int(len(required) - covered),
        "provider_lineage_candidate_passed_runs": int(len(frame)),
        "provider_lineage_selectable_runs": int(selectable.sum()),
        "provider_lineage_retained_only_runs": int(statuses.eq("retained_only").sum()),
        "provider_lineage_unindexed_runs": int(
            statuses.isin(["unindexed", "index_not_provided"]).sum()
        ),
        "provider_lineage_selection_blocked_runs": int((~selectable).sum()),
    }


def _latest_row(frame: pd.DataFrame) -> pd.Series:
    work = frame.copy()
    work["_generated_sort"] = work["generated_at_utc"].astype(str)
    return work.sort_values("_generated_sort").iloc[-1]


def _passed_required_commits(catalog: pd.DataFrame, evidence: pd.DataFrame) -> set[str]:
    passed = _passed_required_rows(catalog, evidence)
    return {str(value) for value in passed["git_commit"].dropna() if str(value)}


def _passed_required_rows(catalog: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    required = set(evidence.loc[evidence["passed"].astype(bool), "required_run_type"].astype(str))
    if not required:
        return catalog.iloc[0:0].copy()
    work = catalog.copy()
    work["summary_status_bool"] = work["summary_status"].map(_to_optional_bool)
    return work.loc[work["run_type"].astype(str).isin(required) & (work["summary_status_bool"] == True)].copy()  # noqa: E712


def _identity_values(frame: pd.DataFrame, extractor: Any) -> set[str]:
    values: set[str] = set()
    for _, row in frame.iterrows():
        value = extractor(row)
        if value:
            values.add(value)
    return values


def _missing_identities(frame: pd.DataFrame, extractor: Any) -> int:
    if frame.empty:
        return 0
    return int(sum(1 for _, row in frame.iterrows() if not extractor(row)))


def _input_provenance_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    return int(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _placeholder_schema_active_count(catalog: pd.DataFrame) -> int:
    return int(_placeholder_schema_active(catalog).sum())


def _placeholder_schema_blocked_count(catalog: pd.DataFrame) -> int:
    active = _placeholder_schema_active(catalog)
    reviewed = _bool_column(catalog, "summary_schema_reviewed")
    allowed = _bool_column(catalog, "summary_placeholder_schema_allowed")
    return int((active & ~reviewed & ~allowed).sum())


def _placeholder_schema_active(catalog: pd.DataFrame) -> pd.Series:
    if catalog.empty:
        return pd.Series(dtype=bool)
    explicit_active = _bool_column(catalog, "summary_placeholder_schema_active")
    if "summary_adapter_schema_status" in catalog.columns:
        status_active = catalog["summary_adapter_schema_status"].map(_is_placeholder_schema)
    else:
        status_active = pd.Series(False, index=catalog.index)
    return explicit_active | status_active


def _is_placeholder_schema(value: Any) -> bool:
    return str(value).strip() == PLACEHOLDER_SCHEMA_STATUS


def _broker_roundtrip_portfolio_safe_count(catalog: pd.DataFrame) -> int:
    frame = _broker_roundtrip_rows(catalog)
    if frame.empty:
        return 0
    provided = _bool_column(frame, "summary_strategy_portfolio_provided")
    ready = _bool_column(frame, "summary_strategy_portfolio_ready")
    passed = _bool_column(frame, "summary_status")
    dispatch_notional = _numeric_column(frame, "summary_dispatch_total_notional")
    selected_allocation = _numeric_column(
        frame, "summary_strategy_portfolio_selected_allocation_notional"
    )
    safe_roundtrip = (
        provided
        & ready
        & passed
        & (selected_allocation > 0.0)
        & (dispatch_notional <= selected_allocation)
    )
    return int(safe_roundtrip.sum())


def _broker_roundtrip_portfolio_breach_count(catalog: pd.DataFrame) -> int:
    frame = _broker_roundtrip_rows(catalog)
    if frame.empty:
        return 0
    provided = _bool_column(frame, "summary_strategy_portfolio_provided")
    dispatch_notional = _numeric_column(frame, "summary_dispatch_total_notional")
    selected_allocation = _numeric_column(
        frame, "summary_strategy_portfolio_selected_allocation_notional"
    )
    breached_roundtrip = (
        provided & (selected_allocation > 0.0) & (dispatch_notional > selected_allocation)
    )
    return int(breached_roundtrip.sum())


def _broker_roundtrip_portfolio_concentration_ok_count(catalog: pd.DataFrame) -> int:
    return _broker_roundtrip_portfolio_concentration_counts(catalog)[1]


def _broker_roundtrip_portfolio_concentration_breach_count(catalog: pd.DataFrame) -> int:
    return _broker_roundtrip_portfolio_concentration_counts(catalog)[2]


def _broker_roundtrip_portfolio_concentration_counts(catalog: pd.DataFrame) -> tuple[int, int, int]:
    frame = _broker_roundtrip_rows(catalog)
    if frame.empty:
        return (0, 0, 0)
    provided = _bool_column(frame, "summary_strategy_portfolio_provided")
    ready = _bool_column(frame, "summary_strategy_portfolio_ready")
    selected_allocation = _numeric_column(
        frame, "summary_strategy_portfolio_selected_allocation_notional"
    )
    min_strategy_count = _numeric_column(frame, "summary_strategy_portfolio_min_strategy_count")
    min_market_count = _numeric_column(frame, "summary_strategy_portfolio_min_market_count")
    max_strategy_weight = _numeric_column(frame, "summary_strategy_portfolio_max_strategy_weight")
    max_market_weight = _numeric_column(frame, "summary_strategy_portfolio_max_market_weight")
    allocated_strategy_count = _numeric_column(frame, "summary_strategy_portfolio_allocated_strategy_count")
    allocated_market_count = _numeric_column(frame, "summary_strategy_portfolio_allocated_market_count")
    max_strategy_allocation_weight = _numeric_column(
        frame, "summary_strategy_portfolio_max_strategy_allocation_weight"
    )
    max_market_allocation_weight = _numeric_column(
        frame, "summary_strategy_portfolio_max_market_allocation_weight"
    )
    concentration_provided = (
        (min_strategy_count > 0.0)
        | (min_market_count > 0.0)
        | (max_strategy_weight > 0.0)
        | (max_market_weight > 0.0)
        | (allocated_strategy_count > 0.0)
        | (allocated_market_count > 0.0)
        | (max_strategy_allocation_weight > 0.0)
        | (max_market_allocation_weight > 0.0)
    )
    concentration = provided & ready & (selected_allocation > 0.0) & concentration_provided
    strategy_count_ok = (min_strategy_count <= 0.0) | (allocated_strategy_count >= min_strategy_count)
    market_count_ok = (min_market_count <= 0.0) | (allocated_market_count >= min_market_count)
    strategy_weight_ok = (max_strategy_weight <= 0.0) | (
        max_strategy_allocation_weight <= max_strategy_weight + 1e-9
    )
    market_weight_ok = (max_market_weight <= 0.0) | (
        max_market_allocation_weight <= max_market_weight + 1e-9
    )
    concentration_ok = (
        concentration
        & strategy_count_ok
        & market_count_ok
        & strategy_weight_ok
        & market_weight_ok
    )
    concentration_breach = concentration & ~concentration_ok
    return (int(concentration.sum()), int(concentration_ok.sum()), int(concentration_breach.sum()))


def _broker_roundtrip_resume_route_ready_count(catalog: pd.DataFrame) -> int:
    return _broker_roundtrip_resume_route_counts(catalog)["broker_roundtrip_resume_route_ready_runs"]


def _broker_roundtrip_resume_route_breach_count(catalog: pd.DataFrame) -> int:
    return _broker_roundtrip_resume_route_counts(catalog)["broker_roundtrip_resume_route_breach_runs"]


def _provider_broker_roundtrip_synthetic_sidecar_ready_count(catalog: pd.DataFrame) -> int:
    return _provider_broker_roundtrip_synthetic_sidecar_counts(catalog)[
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs"
    ]


def _provider_broker_roundtrip_synthetic_sidecar_breach_count(catalog: pd.DataFrame) -> int:
    return _provider_broker_roundtrip_synthetic_sidecar_counts(catalog)[
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs"
    ]


def _broker_roundtrip_resume_route_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "broker_roundtrip_resume_route_provided_runs": 0,
        "broker_roundtrip_resume_route_ready_runs": 0,
        "broker_roundtrip_resume_route_primary_ready_runs": 0,
        "broker_roundtrip_resume_route_incident_ready_runs": 0,
        "broker_roundtrip_resume_route_breach_runs": 0,
        "broker_roundtrip_resume_route_gap_breach_runs": 0,
        "broker_roundtrip_resume_route_launch_control_breach_runs": 0,
        "broker_roundtrip_resume_route_portfolio_breach_runs": 0,
        "broker_roundtrip_resume_route_concentration_breach_runs": 0,
    }
    frame = _broker_roundtrip_rows(catalog)
    if frame.empty:
        return keys
    primary = _resume_route_branch_state(frame, "summary_route_broker_resume_broker_route_readiness")
    incident = _resume_route_branch_state(frame, "summary_route_broker_resume_incident_broker_route_readiness")
    any_active = primary["active"] | incident["active"]
    provided = primary["provided"] & incident["provided"]
    ready = primary["ready"] & incident["ready"]
    gap_breach = primary["gap_breach"] | incident["gap_breach"]
    launch_control_breach = primary["launch_control_breach"] | incident["launch_control_breach"]
    portfolio_breach = primary["portfolio_breach"] | incident["portfolio_breach"]
    concentration_breach = primary["concentration_breach"] | incident["concentration_breach"]
    any_breach = any_active & (
        ~provided
        | ~ready
        | gap_breach
        | launch_control_breach
        | portfolio_breach
        | concentration_breach
    )
    keys.update(
        {
            "broker_roundtrip_resume_route_provided_runs": int(provided.sum()),
            "broker_roundtrip_resume_route_ready_runs": int(ready.sum()),
            "broker_roundtrip_resume_route_primary_ready_runs": int(primary["ready"].sum()),
            "broker_roundtrip_resume_route_incident_ready_runs": int(incident["ready"].sum()),
            "broker_roundtrip_resume_route_breach_runs": int(any_breach.sum()),
            "broker_roundtrip_resume_route_gap_breach_runs": int((any_active & gap_breach).sum()),
            "broker_roundtrip_resume_route_launch_control_breach_runs": int(
                (any_active & launch_control_breach).sum()
            ),
            "broker_roundtrip_resume_route_portfolio_breach_runs": int((any_active & portfolio_breach).sum()),
            "broker_roundtrip_resume_route_concentration_breach_runs": int(
                (any_active & concentration_breach).sum()
            ),
        }
    )
    return keys


def _resume_route_branch_state(frame: pd.DataFrame, prefix: str) -> dict[str, pd.Series]:
    required = _bool_column(frame, f"{prefix}_required")
    provided = _bool_column(frame, f"{prefix}_provided")
    ready_flag = _bool_column(frame, f"{prefix}_ready")
    route_ready_pairs = _numeric_column(frame, f"{prefix}_route_ready_pairs")
    gap_pairs = _numeric_column(frame, f"{prefix}_gap_pairs")
    launch_ready = _bool_column(frame, f"{prefix}_ops_launch_controls_ready")
    safe_runs = _numeric_column(frame, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs")
    breach_runs = _numeric_column(frame, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs")
    concentration_ok_runs = _numeric_column(
        frame,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    )
    concentration_breach_runs = _numeric_column(
        frame,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    )
    active = (
        required
        | provided
        | ready_flag
        | (route_ready_pairs > 0.0)
        | (gap_pairs > 0.0)
        | launch_ready
        | (safe_runs > 0.0)
        | (breach_runs > 0.0)
        | (concentration_ok_runs > 0.0)
        | (concentration_breach_runs > 0.0)
    )
    gap_breach = (route_ready_pairs <= 0.0) | (gap_pairs > 0.0)
    launch_control_breach = ~launch_ready
    portfolio_breach = (safe_runs <= 0.0) | (breach_runs > 0.0)
    concentration_breach = (concentration_ok_runs <= 0.0) | (concentration_breach_runs > 0.0)
    ready = (
        provided
        & ready_flag
        & ~gap_breach
        & ~launch_control_breach
        & ~portfolio_breach
        & ~concentration_breach
    )
    return {
        "active": active,
        "provided": provided,
        "ready": ready,
        "gap_breach": gap_breach,
        "launch_control_breach": launch_control_breach,
        "portfolio_breach": portfolio_breach,
        "concentration_breach": concentration_breach,
    }


def _provider_broker_roundtrip_synthetic_sidecar_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "provider_broker_roundtrip_runs": 0,
        "provider_broker_roundtrip_passed_runs": 0,
        "provider_broker_roundtrip_synthetic_dataset_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_readable_count": 0,
        "provider_broker_roundtrip_synthetic_sidecar_proof_runs": 0,
        "provider_broker_roundtrip_synthetic_sidecar_ready_runs": 0,
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs": 0,
    }
    frame = _provider_broker_roundtrip_rows(catalog)
    if frame.empty:
        return keys
    passed = _bool_column(frame, "summary_status")
    dataset_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_dataset_count")
    sidecar_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_count")
    readable_count = _numeric_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_readable_count")
    ready_flag = _bool_column(frame, "summary_dispatch_roundtrip_synthetic_sidecar_proof_ready")
    proof_runs = dataset_count > 0.0
    ready_runs = proof_runs & ready_flag & (sidecar_count >= dataset_count) & (readable_count >= dataset_count)
    breach_runs = proof_runs & ~ready_runs
    keys.update(
        {
            "provider_broker_roundtrip_runs": int(len(frame)),
            "provider_broker_roundtrip_passed_runs": int(passed.sum()),
            "provider_broker_roundtrip_synthetic_dataset_count": int(dataset_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_count": int(sidecar_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_readable_count": int(readable_count.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_proof_runs": int(proof_runs.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_ready_runs": int(ready_runs.sum()),
            "provider_broker_roundtrip_synthetic_sidecar_breach_runs": int(breach_runs.sum()),
        }
    )
    return keys


def _provider_broker_rehearsal_certificate_counts(catalog: pd.DataFrame) -> dict[str, int]:
    keys = {
        "provider_broker_rehearsal_certificate_runs": 0,
        "provider_broker_rehearsal_certificate_passed_runs": 0,
        "provider_broker_rehearsal_certificate_live_dryrun_runs": 0,
        "provider_broker_rehearsal_certificate_authorizing_runs": 0,
        "provider_broker_rehearsal_certificate_non_authorizing_runs": 0,
        "provider_broker_rehearsal_certificate_hashed_runs": 0,
    }
    if catalog.empty or "run_type" not in catalog.columns:
        return keys
    frame = catalog.loc[
        catalog["run_type"].astype(str)
        == PROVIDER_BROKER_REHEARSAL_CERTIFICATE_RUN_TYPE
    ].copy()
    if frame.empty:
        return keys
    passed = _bool_column(frame, "summary_status")
    target_modes = (
        frame["summary_target_mode"].map(_normalize_identity)
        if "summary_target_mode" in frame.columns
        else pd.Series("", index=frame.index)
    )
    authorization_values = (
        frame["summary_authorizes_submission"]
        if "summary_authorizes_submission" in frame.columns
        else pd.Series(None, index=frame.index, dtype=object)
    )
    authorization_present = authorization_values.notna() & authorization_values.astype(str).str.strip().ne("")
    authorizes_submission = authorization_values.map(_to_bool)
    certificate_hashes = (
        frame["summary_certificate_sha256"].fillna("").astype(str).str.strip()
        if "summary_certificate_sha256" in frame.columns
        else pd.Series("", index=frame.index)
    )
    keys.update(
        {
            "provider_broker_rehearsal_certificate_runs": int(len(frame)),
            "provider_broker_rehearsal_certificate_passed_runs": int(passed.sum()),
            "provider_broker_rehearsal_certificate_live_dryrun_runs": int(
                (passed & target_modes.eq("live_dryrun")).sum()
            ),
            "provider_broker_rehearsal_certificate_authorizing_runs": int(
                (passed & authorizes_submission).sum()
            ),
            "provider_broker_rehearsal_certificate_non_authorizing_runs": int(
                (passed & authorization_present & ~authorizes_submission).sum()
            ),
            "provider_broker_rehearsal_certificate_hashed_runs": int(
                (passed & certificate_hashes.str.fullmatch(r"[0-9a-fA-F]{64}")).sum()
            ),
        }
    )
    return keys


def _broker_roundtrip_rows(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty or "run_type" not in catalog.columns:
        return catalog.iloc[0:0].copy()
    run_types = catalog["run_type"].astype(str)
    generic = run_types == "broker_dispatch_roundtrip"
    if generic.any():
        return catalog.loc[generic].copy()
    provider = run_types == "provider_market_data_imbalance_broker_dispatch_roundtrip"
    return catalog.loc[provider].copy()


def _provider_broker_roundtrip_rows(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog.empty or "run_type" not in catalog.columns:
        return catalog.iloc[0:0].copy()
    run_types = catalog["run_type"].astype(str)
    return catalog.loc[run_types == "provider_market_data_imbalance_broker_dispatch_roundtrip"].copy()


def _bool_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    if column not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[column].map(_to_bool)


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number


def _strategy_identity(row: pd.Series) -> str:
    return _normalize_strategy(_first_identity(row, ("strategy", "strategy_name", "strategy_id")))


def _market_identity(row: pd.Series) -> str:
    return _normalize_identity(_first_identity(row, ("market", "market_profile", "market_name", "market_id")))


def _first_identity(row: pd.Series, keys: tuple[str, ...]) -> str:
    for column in _summary_columns(keys):
        value = _row_text(row, column)
        if value:
            return value
    for scenario_column in (
        "summary_candidate_scenario_key",
        "summary_best_scenario_key",
        "summary_selected_scenario_key",
        "summary_scenario_key",
        "scenario_key",
    ):
        parsed = _parse_scenario_key(_row_text(row, scenario_column))
        for key in keys:
            if key in parsed:
                return parsed[key]
    for json_column in ("parameters_json", "inputs_json"):
        parsed_json = _parse_json(_row_text(row, json_column))
        value = _find_json_key(parsed_json, keys)
        if value:
            return value
    return ""


def _summary_columns(keys: tuple[str, ...]) -> tuple[str, ...]:
    columns: list[str] = []
    for key in keys:
        columns.append(f"summary_{key}")
        columns.append(f"summary_runtime_{key}")
        columns.append(f"summary_broker_runtime_{key}")
    if "market" in keys:
        columns.extend(["summary_market_key", "summary_market_profile_name"])
    return tuple(dict.fromkeys(columns))


def _parse_scenario_key(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in value.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        key = key.strip()
        item = item.strip()
        if key and item:
            parsed[key] = item
    return parsed


def _parse_json(value: str) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _find_json_key(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, (str, int, float)) and str(item).strip():
                return str(item)
        for item in value.values():
            found = _find_json_key(item, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_json_key(item, keys)
            if found:
                return found
    return ""


def _row_text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value)


def _normalize_strategy(value: str | None) -> str:
    normalized = _normalize_identity(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(normalized, normalized)


def _normalize_identity(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _catalog_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "experiment_catalog.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"experiment catalog not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: EvidenceThresholds) -> None:
    if not thresholds.required_run_types:
        raise ValueError("required_run_types must not be empty")
    if thresholds.min_passed_per_type <= 0:
        raise ValueError("min_passed_per_type must be positive")
    blanks = [run_type for run_type in thresholds.required_run_types if not str(run_type).strip()]
    if blanks:
        raise ValueError("required_run_types must not contain blanks")


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
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


def _to_optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None
    return bool(value)


def _to_bool(value: Any) -> bool:
    result = _to_optional_bool(value)
    return bool(result) if result is not None else False
