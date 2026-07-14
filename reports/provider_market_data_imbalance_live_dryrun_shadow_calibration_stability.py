from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.provider_market_data_imbalance_live_dryrun_shadow_calibration import (
    CONFIG_FILE as SOURCE_CONFIG_FILE,
    COST_SUMMARY_FILE as SOURCE_COST_SUMMARY_FILE,
    HORIZON_SUMMARY_FILE as SOURCE_HORIZON_SUMMARY_FILE,
    RECEIPT_FILE as SOURCE_RECEIPT_FILE,
    RUN_TYPE as SOURCE_RUN_TYPE,
    SUMMARY_FILE as SOURCE_SUMMARY_FILE,
    verify_provider_market_data_imbalance_live_dryrun_shadow_calibration,
)
from shadow_calibration_stability import (
    CHECK_COLUMNS,
    ShadowCalibrationStabilityConfig,
    ShadowCalibrationStabilityResult,
    evaluate_shadow_calibration_stability,
)
from shadow_markout_calibration import REFERENCE_STATUS


RUN_TYPE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability"
)
CONTRACT_VERSION = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability/v1"
)
EVIDENCE_CLASS = "deterministic_simulation"
CHECKS_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_checks.csv"
)
SESSIONS_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_sessions.csv"
)
HORIZON_STABILITY_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_horizon_stability.csv"
)
COST_STABILITY_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_cost_stability.csv"
)
SUMMARY_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_summary.csv"
)
RECEIPT_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_receipt.json"
)
CONFIG_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_config.json"
)
RUNBOOK_FILE = (
    "provider_market_data_imbalance_live_dryrun_"
    "shadow_calibration_stability_runbook.md"
)
STABILITY_ARTIFACTS = (
    CHECKS_FILE,
    SESSIONS_FILE,
    HORIZON_STABILITY_FILE,
    COST_STABILITY_FILE,
    SUMMARY_FILE,
    RECEIPT_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
)
SAFETY_FALSE_FIELDS = (
    "provider_network_called",
    "provider_backend_loaded",
    "credential_environment_read",
    "credential_values_stored",
    "execution_engine_loaded",
    "order_object_created",
    "live_position_created",
    "broker_order_api_imported",
    "broker_order_api_called",
    "broker_api_called",
    "routing_enabled",
    "submission_enabled",
    "authorizes_submission",
    "performance_gate_enabled",
    "authorizes_promotion",
    "strategy_promoted",
    "release_approved",
)
SAFETY_TRUE_FIELDS = (
    "stability_evidence_only",
    "calibration_sources_only",
    "deterministic_simulation_cohort",
    "deterministic_reconstruction",
    "cost_rates_require_external_validation",
    "requires_real_provider_observations",
    "requires_separate_promotion_review",
    "requires_distinct_session_identity",
)


@dataclass(frozen=True)
class ProviderShadowCalibrationStabilityConfig(
    ShadowCalibrationStabilityConfig
):
    max_dependency_count: int = 65_536


@dataclass(frozen=True)
class ProviderShadowCalibrationStabilityReport:
    checks: pd.DataFrame
    sessions: pd.DataFrame
    horizon_stability: pd.DataFrame
    cost_stability: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def stable(self) -> bool:
        return bool(
            not self.summary.empty
            and _explicit_true(self.summary.iloc[0], "stable")
        )


@dataclass(frozen=True)
class ProviderShadowCalibrationStabilityVerification:
    verified: bool
    stable: bool
    unstable: bool
    manifest_current: bool
    calibrations_current: bool
    artifacts_consistent: bool
    stability_evidence_only: bool
    non_authorizing: bool
    output_dir: Path
    calibration_dirs: tuple[Path, ...]
    error: str = ""


def write_provider_shadow_calibration_stability(
    calibration_dirs: list[str | Path],
    output_dir: str | Path,
    *,
    config: ProviderShadowCalibrationStabilityConfig | None = None,
) -> ProviderShadowCalibrationStabilityReport:
    config = config or ProviderShadowCalibrationStabilityConfig()
    _validate_report_config(config)
    roots = _calibration_roots(calibration_dirs)
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(
            f"shadow calibration stability output already exists: {out}"
        )
    _reject_output_collision(out, roots)
    verifications = _verified_calibrations(roots)
    report = _assemble_report(
        calibration_roots=roots,
        config=config,
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        source_verifications=verifications,
    )
    ordered_roots = tuple(
        Path(path).resolve()
        for path in report.config["calibration_dirs"]
    )
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / CHECKS_FILE, index=False)
    report.sessions.to_csv(out / SESSIONS_FILE, index=False)
    report.horizon_stability.to_csv(
        out / HORIZON_STABILITY_FILE,
        index=False,
    )
    report.cost_stability.to_csv(out / COST_STABILITY_FILE, index=False)
    report.summary.to_csv(out / SUMMARY_FILE, index=False)
    (out / RECEIPT_FILE).write_text(
        json.dumps(_jsonable(report.receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / CONFIG_FILE).write_text(
        json.dumps(_jsonable(report.config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / RUNBOOK_FILE).write_text(
        _runbook_markdown(report.summary.iloc[0]),
        encoding="utf-8",
    )

    final_verifications = _verified_calibrations(ordered_roots)
    expected_source_hashes = {
        item["calibration_path"]: item["calibration_manifest_sha256"]
        for item in report.receipt["sources"]
    }
    for root, verification in zip(ordered_roots, final_verifications):
        if not verification.verified or not verification.completed:
            raise RuntimeError("calibration source changed during stability run")
        if file_sha256(root / MANIFEST_NAME) != expected_source_hashes[
            str(root)
        ]:
            raise RuntimeError("calibration source changed during stability run")
    manifests = [root / MANIFEST_NAME for root in ordered_roots]
    recursive_dependencies = _recursive_dependencies(ordered_roots)
    manifest_inputs: dict[str, Any] = {
        "shadow_calibrations": list(ordered_roots),
        "shadow_calibration_manifests": manifests,
    }
    if recursive_dependencies:
        manifest_inputs["shadow_calibration_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(report.receipt, report.summary.iloc[0]),
    )
    return ProviderShadowCalibrationStabilityReport(
        checks=report.checks,
        sessions=report.sessions,
        horizon_stability=report.horizon_stability,
        cost_stability=report.cost_stability,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_provider_shadow_calibration_stability(
    stability_dir: str | Path,
) -> ProviderShadowCalibrationStabilityVerification:
    candidate = Path(stability_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=STABILITY_ARTIFACTS,
        require_input_fingerprints=True,
    )
    calibration_roots: tuple[Path, ...] = ()
    try:
        manifest = _read_json(manifest_path, "stability manifest")
        inputs = _mapping(manifest.get("inputs"))
        calibration_roots = tuple(
            _input_directory_paths(inputs.get("shadow_calibrations"))
        )
        if not calibration_roots:
            raise ValueError("stability manifest lacks calibration sources")
        source_verifications = _verified_calibrations(calibration_roots)
        calibrations_current = all(
            verification.verified
            and verification.completed
            and verification.calibration_only
            and verification.non_authorizing
            for verification in source_verifications
        )
        if not calibrations_current:
            return _failed_verification(
                root=root,
                calibration_roots=calibration_roots,
                manifest_current=integrity.passed,
                calibrations_current=False,
                error="a calibration source is stale, incomplete, or unsafe",
            )
        actual_receipt = _read_json(root / RECEIPT_FILE, "receipt")
        actual_config = _read_json(root / CONFIG_FILE, "config")
        config = _config_from_payload(actual_config)
        expected = _assemble_report(
            calibration_roots=calibration_roots,
            config=config,
            recorded_at_utc=_text(actual_receipt.get("recorded_at_utc")),
            source_verifications=source_verifications,
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "checks")
        actual_sessions = _read_csv(root / SESSIONS_FILE, "sessions")
        actual_horizons = _read_csv(
            root / HORIZON_STABILITY_FILE,
            "horizon stability",
        )
        actual_costs = _read_csv(
            root / COST_STABILITY_FILE,
            "cost stability",
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "summary")
        actual_summary_row = _single_row(actual_summary, "summary")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        ordered_roots = tuple(
            Path(path).resolve()
            for path in expected.config["calibration_dirs"]
        )
        recursive_dependencies = _recursive_dependencies(ordered_roots)
        inputs_current = _manifest_inputs_match(
            inputs,
            calibration_roots=ordered_roots,
            recursive_dependencies=recursive_dependencies,
        )
        parameters_current = _jsonable(manifest.get("parameters")) == {
            "config": _jsonable(asdict(config))
        }
        expected_extra = _manifest_extra(
            expected.receipt,
            expected.summary.iloc[0],
        )
        artifacts_consistent = bool(
            _dataframe_records_equal(actual_checks, expected.checks)
            and _dataframe_records_equal(actual_sessions, expected.sessions)
            and _dataframe_records_equal(
                actual_horizons,
                expected.horizon_stability,
            )
            and _dataframe_records_equal(
                actual_costs,
                expected.cost_stability,
            )
            and _dataframe_records_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook == _runbook_markdown(expected.summary.iloc[0])
            and _jsonable(manifest.get("extra"))
            == _jsonable(expected_extra)
            and parameters_current
            and inputs_current
        )
        evidence_only = _surfaces_stability_evidence_only(
            actual_summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        non_authorizing = _surfaces_non_authorizing(
            actual_summary_row,
            actual_receipt,
            actual_config,
            _mapping(manifest.get("extra")),
        )
        stable = bool(expected.stable)
        verified = bool(
            integrity.passed
            and calibrations_current
            and artifacts_consistent
            and evidence_only
            and non_authorizing
        )
        return ProviderShadowCalibrationStabilityVerification(
            verified=verified,
            stable=stable,
            unstable=not stable,
            manifest_current=integrity.passed,
            calibrations_current=calibrations_current,
            artifacts_consistent=artifacts_consistent,
            stability_evidence_only=evidence_only,
            non_authorizing=non_authorizing,
            output_dir=root,
            calibration_dirs=ordered_roots,
            error="" if verified else "stability verification failed",
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _failed_verification(
            root=root,
            calibration_roots=calibration_roots,
            manifest_current=integrity.passed,
            calibrations_current=False,
            error=str(exc),
        )


def _assemble_report(
    *,
    calibration_roots: tuple[Path, ...],
    config: ProviderShadowCalibrationStabilityConfig,
    recorded_at_utc: str,
    source_verifications: tuple[Any, ...],
) -> ProviderShadowCalibrationStabilityReport:
    records = []
    for root, verification in zip(calibration_roots, source_verifications):
        receipt = _read_json(root / SOURCE_RECEIPT_FILE, "source receipt")
        source_config = _read_json(
            root / SOURCE_CONFIG_FILE,
            "source config",
        )
        source_summary = _single_row(
            _read_csv(root / SOURCE_SUMMARY_FILE, "source summary"),
            "source summary",
        )
        horizon_summary = _read_csv(
            root / SOURCE_HORIZON_SUMMARY_FILE,
            "source horizon summary",
        )
        cost_summary = _read_csv(
            root / SOURCE_COST_SUMMARY_FILE,
            "source cost summary",
        )
        identity = _mapping(receipt.get("identity"))
        outcome = _mapping(receipt.get("outcome"))
        session_id = _text(identity.get("session_id"))
        calibration_id = _text(receipt.get("calibration_receipt_id"))
        if not session_id or not calibration_id:
            raise ValueError("calibration source identity is incomplete")
        contract_sha256 = _canonical_sha256(
            {
                "contract_version": receipt.get("contract_version"),
                "calibration": receipt.get("calibration"),
                "source_settings": source_config.get("settings"),
            }
        )
        records.append(
            {
                "root": root,
                "verification": verification,
                "receipt": receipt,
                "session_id": session_id,
                "calibration_id": calibration_id,
                "contract_sha256": contract_sha256,
                "identity": identity,
                "outcome": outcome,
                "source_summary": source_summary,
                "horizon_summary": horizon_summary,
                "cost_summary": cost_summary,
            }
        )
    records.sort(key=lambda item: (item["session_id"], item["calibration_id"]))
    sessions = pd.DataFrame(
        [
            {
                "calibration_receipt_id": item["calibration_id"],
                "session_id": item["session_id"],
                **{
                    field: _text(item["identity"].get(field))
                    for field in (
                        "strategy",
                        "market",
                        "target_mode",
                        "provider",
                        "transport",
                        "exchange",
                        "adapter",
                    )
                },
                "evidence_class": EVIDENCE_CLASS,
                "calibration_contract_sha256": item["contract_sha256"],
                "accepted_intent_count": int(
                    item["outcome"]["accepted_intent_count"]
                ),
                "observation_count": int(
                    item["outcome"]["observation_count"]
                ),
            }
            for item in records
        ]
    )
    horizon_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    for item in records:
        selected_horizons = item["horizon_summary"].loc[
            item["horizon_summary"]["action_group"].astype(str).eq("all")
        ]
        selected_costs = item["cost_summary"].loc[
            item["cost_summary"]["action_group"].astype(str).eq("all")
        ]
        for row in selected_horizons.to_dict(orient="records"):
            horizon_rows.append(
                {
                    "calibration_receipt_id": item["calibration_id"],
                    "session_id": item["session_id"],
                    "requested_horizon_ns": row["requested_horizon_ns"],
                    "action_group": row["action_group"],
                    "coverage_ratio": row["coverage_ratio"],
                    "mean_directional_mid_move_ticks": row[
                        "mean_directional_mid_move_ticks"
                    ],
                    "mean_directional_microprice_move_ticks": row[
                        "mean_directional_microprice_move_ticks"
                    ],
                    "mean_touch_markout_ticks": row[
                        "mean_touch_markout_ticks"
                    ],
                    "adverse_selection_rate": row[
                        "adverse_selection_rate"
                    ],
                }
            )
        for row in selected_costs.to_dict(orient="records"):
            cost_rows.append(
                {
                    "calibration_receipt_id": item["calibration_id"],
                    "session_id": item["session_id"],
                    "requested_horizon_ns": row["requested_horizon_ns"],
                    "action_group": row["action_group"],
                    "cost_scenario": row["cost_scenario"],
                    "cost_model_version": row["cost_model_version"],
                    "reference_status": row["reference_status"],
                    "cost_break_even_rate": row["cost_break_even_rate"],
                    "mean_round_trip_cost_ticks": row[
                        "mean_round_trip_cost_ticks"
                    ],
                    "mean_break_even_surplus_ticks": row[
                        "mean_break_even_surplus_ticks"
                    ],
                }
            )
    evaluation = evaluate_shadow_calibration_stability(
        sessions,
        pd.DataFrame(horizon_rows),
        pd.DataFrame(cost_rows),
        config=_core_config(config),
    )
    recursive_dependencies = _recursive_dependencies(
        tuple(item["root"] for item in records)
    )
    if len(recursive_dependencies) > config.max_dependency_count:
        raise ValueError(
            "stability dependency graph exceeds configured limit"
        )
    checks = _report_checks(
        evaluation=evaluation,
        records=records,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    stable = bool(checks["passed"].map(_bool).all())
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    instability_reason = (
        ""
        if stable
        else ";".join(
            checks.loc[~checks["passed"].map(_bool), "check"]
            .astype(str)
            .tolist()
        )
    )
    receipt_core = _receipt_core(
        records=records,
        evaluation=evaluation,
        config=config,
        stable=stable,
        failed_checks=failed_checks,
        instability_reason=instability_reason,
        recorded_at_utc=recorded_at_utc,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "stability_receipt_id": (
            f"provider-shadow-stability-{receipt_sha256[:24]}"
        ),
        "stability_receipt_sha256": receipt_sha256,
    }
    summary = _summary(
        receipt=receipt,
        evaluation=evaluation,
        checks=checks,
        recursive_dependency_count=len(recursive_dependencies),
    )
    config_payload = _config_payload(
        config=config,
        receipt=receipt,
        calibration_roots=tuple(item["root"] for item in records),
    )
    return ProviderShadowCalibrationStabilityReport(
        checks=checks,
        sessions=evaluation.sessions,
        horizon_stability=evaluation.horizon_stability,
        cost_stability=evaluation.cost_stability,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _report_checks(
    *,
    evaluation: ShadowCalibrationStabilityResult,
    records: list[dict[str, Any]],
    recursive_dependency_count: int,
    config: ProviderShadowCalibrationStabilityConfig,
) -> pd.DataFrame:
    checks = evaluation.checks.to_dict(orient="records")
    checks.extend(
        [
            _check(
                "all_calibrations_semantically_verified",
                "source",
                sum(bool(item["verification"].verified) for item in records),
                "==",
                len(records),
                all(item["verification"].verified for item in records),
                "a calibration source is not semantically verified",
            ),
            _check(
                "all_calibrations_completed",
                "source",
                sum(bool(item["verification"].completed) for item in records),
                "==",
                len(records),
                all(item["verification"].completed for item in records),
                "a calibration source is incomplete",
            ),
            _check(
                "all_calibrations_non_authorizing",
                "source",
                sum(
                    bool(
                        item["verification"].calibration_only
                        and item["verification"].non_authorizing
                    )
                    for item in records
                ),
                "==",
                len(records),
                all(
                    item["verification"].calibration_only
                    and item["verification"].non_authorizing
                    for item in records
                ),
                "a calibration source is authorizing or not calibration-only",
            ),
            _check(
                "deterministic_simulation_evidence_only",
                "evidence",
                int(evaluation.sessions["evidence_class"].eq(EVIDENCE_CLASS).sum()),
                "==",
                len(evaluation.sessions),
                bool(
                    evaluation.sessions["evidence_class"]
                    .eq(EVIDENCE_CLASS)
                    .all()
                ),
                "the cohort mixes simulation and real-provider evidence",
            ),
            _check(
                "cost_rates_explicitly_unvalidated",
                "cost",
                int(
                    evaluation.cost_stability["reference_status"]
                    .astype(str)
                    .eq(REFERENCE_STATUS)
                    .sum()
                ),
                "==",
                len(evaluation.cost_stability),
                bool(
                    not evaluation.cost_stability.empty
                    and evaluation.cost_stability["reference_status"]
                    .astype(str)
                    .eq(REFERENCE_STATUS)
                    .all()
                ),
                "a reference cost is not labeled for external validation",
            ),
            _check(
                "dependency_graph_within_limit",
                "provenance",
                recursive_dependency_count,
                "<=",
                config.max_dependency_count,
                recursive_dependency_count <= config.max_dependency_count,
                "recursive calibration dependency limit exceeded",
            ),
            _check(
                "performance_gate_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "stability evidence enabled a performance gate",
            ),
            _check(
                "promotion_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "stability evidence enabled promotion",
            ),
            _check(
                "routing_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "stability evidence enabled routing",
            ),
            _check(
                "submission_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "stability evidence enabled submission",
            ),
        ]
    )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _receipt_core(
    *,
    records: list[dict[str, Any]],
    evaluation: ShadowCalibrationStabilityResult,
    config: ProviderShadowCalibrationStabilityConfig,
    stable: bool,
    failed_checks: int,
    instability_reason: str,
    recorded_at_utc: str,
) -> dict[str, Any]:
    identity_fields = (
        "strategy",
        "market",
        "target_mode",
        "provider",
        "transport",
        "exchange",
        "adapter",
    )
    identity = {
        field: _single_or_mixed(evaluation.sessions[field])
        for field in identity_fields
    }
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "non_authorizing_shadow_calibration_stability",
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "stable": stable,
        "unstable": not stable,
        "failed_check_count": failed_checks,
        "instability_reason": instability_reason,
        "evidence_class": EVIDENCE_CLASS,
        "identity": identity,
        "sources": [
            {
                "calibration_path": str(item["root"]),
                "calibration_manifest_path": str(
                    item["root"] / MANIFEST_NAME
                ),
                "calibration_manifest_sha256": file_sha256(
                    item["root"] / MANIFEST_NAME
                ),
                "calibration_receipt_id": item["calibration_id"],
                "session_id": item["session_id"],
            }
            for item in records
        ],
        "stability": _jsonable(asdict(_core_config(config))),
        "outcome": {
            "session_count": len(evaluation.sessions),
            "horizon_stability_row_count": len(
                evaluation.horizon_stability
            ),
            "cost_stability_row_count": len(evaluation.cost_stability),
            "minimum_horizon_coverage_ratio": _numeric_min(
                evaluation.horizon_stability,
                "minimum_coverage_ratio",
            ),
            "maximum_horizon_coverage_range": _numeric_max(
                evaluation.horizon_stability,
                "coverage_ratio_range",
            ),
            "maximum_directional_mid_range_ticks": _numeric_max(
                evaluation.horizon_stability,
                "directional_mid_move_range_ticks",
            ),
            "maximum_adverse_selection_rate_range": _numeric_max(
                evaluation.horizon_stability,
                "adverse_selection_rate_range",
            ),
            "maximum_cost_break_even_rate_range": _numeric_max(
                evaluation.cost_stability,
                "cost_break_even_rate_range",
            ),
            "maximum_round_trip_cost_range_ticks": _numeric_max(
                evaluation.cost_stability,
                "round_trip_cost_range_ticks",
            ),
        },
        "artifacts": {
            "sessions_records_sha256": _records_sha256(
                evaluation.sessions
            ),
            "horizon_stability_records_sha256": _records_sha256(
                evaluation.horizon_stability
            ),
            "cost_stability_records_sha256": _records_sha256(
                evaluation.cost_stability
            ),
        },
        "safety": _safety_payload(),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    evaluation: ShadowCalibrationStabilityResult,
    checks: pd.DataFrame,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    stable = bool(checks["passed"].map(_bool).all())
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    outcome = _mapping(receipt.get("outcome"))
    identity = _mapping(receipt.get("identity"))
    return pd.DataFrame(
        [
            {
                "passed": stable,
                "stable": stable,
                "unstable": not stable,
                "status": (
                    "stable_non_authorizing_simulation_cohort"
                    if stable
                    else "unstable_non_authorizing_simulation_cohort"
                ),
                "failed_checks": failed_checks,
                "instability_reason": _text(
                    receipt.get("instability_reason")
                ),
                "stability_receipt_id": _text(
                    receipt.get("stability_receipt_id")
                ),
                "stability_receipt_sha256": _text(
                    receipt.get("stability_receipt_sha256")
                ),
                "evidence_class": EVIDENCE_CLASS,
                "strategy": _text(identity.get("strategy")),
                "market": _text(identity.get("market")),
                "provider": _text(identity.get("provider")),
                "session_count": len(evaluation.sessions),
                "minimum_horizon_coverage_ratio": outcome.get(
                    "minimum_horizon_coverage_ratio"
                ),
                "maximum_horizon_coverage_range": outcome.get(
                    "maximum_horizon_coverage_range"
                ),
                "maximum_directional_mid_range_ticks": outcome.get(
                    "maximum_directional_mid_range_ticks"
                ),
                "maximum_adverse_selection_rate_range": outcome.get(
                    "maximum_adverse_selection_rate_range"
                ),
                "maximum_cost_break_even_rate_range": outcome.get(
                    "maximum_cost_break_even_rate_range"
                ),
                "maximum_round_trip_cost_range_ticks": outcome.get(
                    "maximum_round_trip_cost_range_ticks"
                ),
                "recursive_dependency_count": recursive_dependency_count,
                **_safety_payload(),
                "next_gate": (
                    "real_provider_shadow_observation_collection"
                    if stable
                    else "expand_simulation_cohort_and_review_instability"
                ),
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderShadowCalibrationStabilityConfig,
    receipt: Mapping[str, Any],
    calibration_roots: tuple[Path, ...],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "calibration_dirs": [str(root) for root in calibration_roots],
        "stability_receipt_id": _text(receipt.get("stability_receipt_id")),
        "stability_receipt_sha256": _text(
            receipt.get("stability_receipt_sha256")
        ),
        "stable": bool(receipt.get("stable")),
        "unstable": bool(receipt.get("unstable")),
        "performance_thresholds": {},
        **_safety_payload(),
    }


def _manifest_extra(
    receipt: Mapping[str, Any],
    summary: pd.Series,
) -> dict[str, Any]:
    identity = _mapping(receipt.get("identity"))
    return {
        "passed": _explicit_true(summary, "passed"),
        "stable": _explicit_true(summary, "stable"),
        "unstable": _explicit_true(summary, "unstable"),
        "status": _text(summary.get("status")),
        "stability_receipt_id": _text(
            receipt.get("stability_receipt_id")
        ),
        "stability_receipt_sha256": _text(
            receipt.get("stability_receipt_sha256")
        ),
        "evidence_class": EVIDENCE_CLASS,
        "provider": _text(identity.get("provider")),
        "market": _text(identity.get("market")),
        "target_mode": "live_dryrun",
        "session_count": int(summary["session_count"]),
        **_safety_payload(),
    }


def _runbook_markdown(summary: pd.Series) -> str:
    return "\n".join(
        [
            "# Provider Shadow Calibration Stability",
            "",
            f"- Status: `{summary['status']}`",
            f"- Stability receipt: `{summary['stability_receipt_id']}`",
            f"- Evidence class: `{summary['evidence_class']}`",
            f"- Provider identity: `{summary['provider']}` (proof label only)",
            f"- Distinct sessions: `{summary['session_count']}`",
            (
                "- Minimum horizon coverage: "
                f"`{summary['minimum_horizon_coverage_ratio']}`"
            ),
            "- Performance gate enabled: no",
            "- Strategy promoted: no",
            "- Routing or submission enabled: no",
            "- Cost rates require current external validation: yes",
            "- Real provider observations supplied: no",
            "",
            (
                "Stable means only that this deterministic simulation cohort "
                "met its configured dispersion and coverage checks. It does "
                "not establish live edge and cannot authorize promotion, "
                "routing, submission, or release."
            ),
            "",
        ]
    )


def _config_from_payload(
    payload: Mapping[str, Any],
) -> ProviderShadowCalibrationStabilityConfig:
    settings = _mapping(payload.get("settings"))
    expected_fields = {
        item.name for item in fields(ProviderShadowCalibrationStabilityConfig)
    }
    if set(settings) != expected_fields:
        raise ValueError("stability config settings are incomplete")
    config = ProviderShadowCalibrationStabilityConfig(**settings)
    _validate_report_config(config)
    return config


def _core_config(
    config: ProviderShadowCalibrationStabilityConfig,
) -> ShadowCalibrationStabilityConfig:
    return ShadowCalibrationStabilityConfig(
        min_sessions=config.min_sessions,
        min_session_coverage_ratio=config.min_session_coverage_ratio,
        max_horizon_coverage_range=config.max_horizon_coverage_range,
        max_directional_mid_range_ticks=(
            config.max_directional_mid_range_ticks
        ),
        require_directional_sign_consistency=(
            config.require_directional_sign_consistency
        ),
        max_adverse_selection_rate_range=(
            config.max_adverse_selection_rate_range
        ),
        max_cost_break_even_rate_range=(
            config.max_cost_break_even_rate_range
        ),
        max_round_trip_cost_range_ticks=(
            config.max_round_trip_cost_range_ticks
        ),
    )


def _validate_report_config(
    config: ProviderShadowCalibrationStabilityConfig,
) -> None:
    if (
        isinstance(config.max_dependency_count, bool)
        or not isinstance(config.max_dependency_count, int)
        or config.max_dependency_count <= 0
    ):
        raise ValueError("max_dependency_count must be a positive integer")


def _calibration_roots(
    calibration_dirs: list[str | Path] | tuple[Path, ...],
) -> tuple[Path, ...]:
    if not calibration_dirs:
        raise ValueError("at least one calibration directory is required")
    roots = tuple(
        (
            Path(path).parent
            if Path(path).is_file()
            else Path(path)
        ).resolve()
        for path in calibration_dirs
    )
    if len(set(roots)) != len(roots):
        raise ValueError("calibration directories must be distinct")
    return roots


def _verified_calibrations(roots: tuple[Path, ...]) -> tuple[Any, ...]:
    verifications = tuple(
        verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
            root
        )
        for root in roots
    )
    for verification in verifications:
        if not (
            verification.verified
            and verification.completed
            and verification.calibration_only
            and verification.non_authorizing
        ):
            raise ValueError(
                "stability requires verified completed calibration-only "
                "non-authorizing sources: "
                + (verification.error or "calibration_source_not_completed")
            )
    return verifications


def _recursive_dependencies(
    calibration_roots: tuple[Path, ...],
) -> list[Path]:
    excluded = {
        *(root.resolve() for root in calibration_roots),
        *((root / MANIFEST_NAME).resolve() for root in calibration_roots),
    }
    dependencies: set[Path] = set()
    for root in calibration_roots:
        dependencies.update(
            path.resolve()
            for path in manifest_dependency_paths(root / MANIFEST_NAME)
            if path.resolve() not in excluded
        )
    return sorted(dependencies, key=lambda path: str(path).lower())


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    calibration_roots: tuple[Path, ...],
    recursive_dependencies: list[Path],
) -> bool:
    expected_keys = {
        "shadow_calibrations",
        "shadow_calibration_manifests",
    }
    if recursive_dependencies:
        expected_keys.add("shadow_calibration_recursive_dependencies")
    if set(inputs) != expected_keys:
        return False
    expected_paths = {
        *(root.resolve() for root in calibration_roots),
        *((root / MANIFEST_NAME).resolve() for root in calibration_roots),
        *(path.resolve() for path in recursive_dependencies),
    }
    return set(_fingerprint_paths(inputs)) == expected_paths


def _reject_output_collision(
    output_dir: Path,
    calibration_roots: tuple[Path, ...],
) -> None:
    for root in calibration_roots:
        if output_dir == root or _is_relative_to(output_dir, root):
            raise ValueError(
                "stability output must not overlap a calibration source"
            )
        if _is_relative_to(root, output_dir):
            raise ValueError(
                "stability output must not contain a calibration source"
            )


def _surfaces_stability_evidence_only(
    summary: pd.Series,
    receipt: Mapping[str, Any],
    config: Mapping[str, Any],
    manifest_extra: Mapping[str, Any],
) -> bool:
    safety = _mapping(receipt.get("safety"))
    surfaces: tuple[Mapping[str, Any] | pd.Series, ...] = (
        summary,
        safety,
        config,
        manifest_extra,
    )
    return bool(
        all(
            _explicit_true(surface, field)
            for surface in surfaces
            for field in SAFETY_TRUE_FIELDS
        )
    )


def _surfaces_non_authorizing(
    summary: pd.Series,
    receipt: Mapping[str, Any],
    config: Mapping[str, Any],
    manifest_extra: Mapping[str, Any],
) -> bool:
    safety = _mapping(receipt.get("safety"))
    surfaces: tuple[Mapping[str, Any] | pd.Series, ...] = (
        summary,
        safety,
        config,
        manifest_extra,
    )
    return bool(
        all(
            _explicit_false(surface, field)
            for surface in surfaces
            for field in SAFETY_FALSE_FIELDS
        )
    )


def _failed_verification(
    *,
    root: Path,
    calibration_roots: tuple[Path, ...],
    manifest_current: bool,
    calibrations_current: bool,
    error: str,
) -> ProviderShadowCalibrationStabilityVerification:
    return ProviderShadowCalibrationStabilityVerification(
        verified=False,
        stable=False,
        unstable=False,
        manifest_current=manifest_current,
        calibrations_current=calibrations_current,
        artifacts_consistent=False,
        stability_evidence_only=False,
        non_authorizing=False,
        output_dir=root,
        calibration_dirs=calibration_roots,
        error=error,
    )


def _safety_payload() -> dict[str, bool]:
    return {
        **{field: False for field in SAFETY_FALSE_FIELDS},
        **{field: True for field in SAFETY_TRUE_FIELDS},
    }


def _check(
    name: str,
    component: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "component": component,
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _records_sha256(frame: pd.DataFrame) -> str:
    return _canonical_sha256(frame.to_dict(orient="records"))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dataframe_records_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(
        expected
    ):
        return False
    for actual_row, expected_row in zip(
        actual.itertuples(index=False, name=None),
        expected.itertuples(index=False, name=None),
    ):
        for actual_value, expected_value in zip(actual_row, expected_row):
            actual_missing = _artifact_value_missing(actual_value)
            expected_missing = _artifact_value_missing(expected_value)
            if actual_missing or expected_missing:
                if actual_missing != expected_missing:
                    return False
                continue
            if isinstance(
                actual_value,
                (int, float, np.integer, np.floating),
            ) and isinstance(
                expected_value,
                (int, float, np.integer, np.floating),
            ):
                if float(actual_value) != float(expected_value):
                    return False
            elif str(actual_value) != str(expected_value):
                return False
    return True


def _artifact_value_missing(value: Any) -> bool:
    if value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "nan"}
    ):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _fingerprint_paths(value: Any) -> list[Path]:
    paths: list[Path] = []
    if isinstance(value, Mapping):
        if value.get("kind") in {"file", "directory"} and value.get("path"):
            paths.append(Path(str(value["path"])).resolve())
        else:
            for nested in value.values():
                paths.extend(_fingerprint_paths(nested))
    elif isinstance(value, list):
        for nested in value:
            paths.extend(_fingerprint_paths(nested))
    return paths


def _input_directory_paths(value: Any) -> list[Path]:
    if not isinstance(value, list):
        raise ValueError("shadow_calibrations input must be a list")
    paths = []
    for item in value:
        record = _mapping(item)
        if record.get("kind") != "directory" or not record.get("path"):
            raise ValueError("shadow_calibrations input is malformed")
        paths.append(Path(str(record["path"])).resolve())
    if len(set(paths)) != len(paths):
        raise ValueError("shadow_calibrations inputs must be distinct")
    return paths


def _numeric_min(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else round(float(values.min()), 10)


def _numeric_max(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else round(float(values.max()), 10)


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _single_or_mixed(values: pd.Series) -> str:
    unique = values.astype(str).drop_duplicates().tolist()
    return unique[0] if len(unique) == 1 else "MIXED"


def _utc_text(value: Any) -> str:
    text = _text(value)
    if not text:
        raise ValueError("recorded_at_utc must not be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("recorded_at_utc must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _explicit_true(
    value: Mapping[str, Any] | pd.Series,
    key: str,
) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return bool(math.isfinite(float(raw)) and float(raw) == 1.0)
    return _text(raw).lower() in {"1", "true", "yes"}


def _explicit_false(
    value: Mapping[str, Any] | pd.Series,
    key: str,
) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return not bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return bool(math.isfinite(float(raw)) and float(raw) == 0.0)
    return _text(raw).lower() in {"0", "false", "no", "off"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None:
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"unable to read {label}: {path}") from exc
    if frame.empty:
        raise ValueError(f"{label} must not be empty")
    return frame


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
