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
from reports.provider_market_data_imbalance_live_dryrun_shadow_evaluator import (
    RUN_TYPE as SHADOW_EVALUATOR_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation,
)
from shadow_markout_calibration import (
    REFERENCE_STATUS,
    ShadowCostScenario,
    ShadowMarkoutCalibrationConfig,
    ShadowMarkoutCalibrationResult,
    evaluate_shadow_markout_calibration,
)


RUN_TYPE = "provider_market_data_imbalance_live_dryrun_shadow_calibration"
CONTRACT_VERSION = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration/v1"
)
SHADOW_RECEIPT_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json"
)
SHADOW_CONFIG_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_config.json"
)
SHADOW_FEATURES_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_features.csv"
)
SHADOW_INTENTS_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_intents.csv"
)
CHECKS_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_checks.csv"
)
OBSERVATIONS_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_markouts.csv"
)
COST_SENSITIVITY_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_cost_sensitivity.csv"
)
HORIZON_SUMMARY_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_horizon_summary.csv"
)
COST_SUMMARY_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_cost_summary.csv"
)
SUMMARY_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_summary.csv"
)
RECEIPT_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_receipt.json"
)
CONFIG_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_config.json"
)
RUNBOOK_FILE = (
    "provider_market_data_imbalance_live_dryrun_shadow_calibration_runbook.md"
)
CALIBRATION_ARTIFACTS = (
    CHECKS_FILE,
    OBSERVATIONS_FILE,
    COST_SENSITIVITY_FILE,
    HORIZON_SUMMARY_FILE,
    COST_SUMMARY_FILE,
    SUMMARY_FILE,
    RECEIPT_FILE,
    CONFIG_FILE,
    RUNBOOK_FILE,
)
CHECK_COLUMNS = (
    "check",
    "component",
    "value",
    "operator",
    "threshold",
    "passed",
    "reason",
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
    "calibration_only",
    "shadow_source_only",
    "deterministic_reconstruction",
    "cost_rates_require_external_validation",
    "requires_real_provider_observations",
    "requires_separate_promotion_review",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig(
    ShadowMarkoutCalibrationConfig
):
    max_dependency_count: int = 32_768


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowCalibrationReport:
    checks: pd.DataFrame
    observations: pd.DataFrame
    cost_sensitivity: pd.DataFrame
    horizon_summary: pd.DataFrame
    cost_summary: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def completed(self) -> bool:
        return bool(
            not self.summary.empty
            and _explicit_true(self.summary.iloc[0], "completed")
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowCalibrationVerification:
    verified: bool
    completed: bool
    insufficient: bool
    manifest_current: bool
    shadow_current: bool
    artifacts_consistent: bool
    calibration_only: bool
    non_authorizing: bool
    output_dir: Path
    shadow_dir: Path | None
    error: str = ""


def write_provider_market_data_imbalance_live_dryrun_shadow_calibration(
    shadow_dir: str | Path,
    output_dir: str | Path,
    *,
    config: (
        ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig | None
    ) = None,
) -> ProviderMarketDataImbalanceLiveDryrunShadowCalibrationReport:
    config = config or (
        ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig()
    )
    _validate_report_config(config)
    shadow_candidate = Path(shadow_dir)
    shadow_root = (
        shadow_candidate.parent
        if shadow_candidate.is_file()
        else shadow_candidate
    ).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(
            f"shadow calibration output already exists: {out}"
        )
    _reject_output_collision(out, shadow_root)
    source_verification = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            shadow_root
        )
    )
    if not (
        source_verification.verified
        and source_verification.completed
        and source_verification.shadow_only
        and source_verification.non_authorizing
    ):
        raise ValueError(
            "shadow calibration requires a verified completed shadow-only "
            "non-authorizing source: "
            + (source_verification.error or "shadow_source_not_completed")
        )
    report = _assemble_report(
        shadow_root=shadow_root,
        config=config,
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        source_verification=source_verification,
    )
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / CHECKS_FILE, index=False)
    report.observations.to_csv(out / OBSERVATIONS_FILE, index=False)
    report.cost_sensitivity.to_csv(
        out / COST_SENSITIVITY_FILE,
        index=False,
    )
    report.horizon_summary.to_csv(out / HORIZON_SUMMARY_FILE, index=False)
    report.cost_summary.to_csv(out / COST_SUMMARY_FILE, index=False)
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

    shadow_manifest_path = shadow_root / MANIFEST_NAME
    final_source = (
        verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
            shadow_root
        )
    )
    if (
        not final_source.verified
        or not final_source.completed
        or file_sha256(shadow_manifest_path)
        != report.receipt["proof_contract"]["shadow_manifest_sha256"]
    ):
        raise RuntimeError("shadow source changed during calibration")
    recursive_dependencies = _recursive_dependencies(
        shadow_manifest_path,
        {shadow_root, shadow_manifest_path},
    )
    manifest_inputs: dict[str, Any] = {
        "shadow_evaluation": shadow_root,
        "shadow_evaluation_manifest": shadow_manifest_path,
    }
    if recursive_dependencies:
        manifest_inputs["shadow_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(report.receipt, report.summary.iloc[0]),
    )
    return ProviderMarketDataImbalanceLiveDryrunShadowCalibrationReport(
        checks=report.checks,
        observations=report.observations,
        cost_sensitivity=report.cost_sensitivity,
        horizon_summary=report.horizon_summary,
        cost_summary=report.cost_summary,
        summary=report.summary,
        receipt=report.receipt,
        config=report.config,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_live_dryrun_shadow_calibration(
    calibration_dir: str | Path,
) -> ProviderMarketDataImbalanceLiveDryrunShadowCalibrationVerification:
    candidate = Path(calibration_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=CALIBRATION_ARTIFACTS,
        require_input_fingerprints=True,
    )
    shadow_root: Path | None = None
    try:
        manifest = _read_json(manifest_path, "shadow calibration manifest")
        inputs = _mapping(manifest.get("inputs"))
        shadow_record = _mapping(inputs.get("shadow_evaluation"))
        if shadow_record.get("kind") != "directory":
            raise ValueError(
                "shadow calibration manifest lacks a directory source"
            )
        shadow_root = Path(str(shadow_record.get("path", ""))).resolve()
        source_verification = (
            verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
                shadow_root
            )
        )
        shadow_current = bool(
            source_verification.verified
            and source_verification.completed
            and source_verification.shadow_only
            and source_verification.non_authorizing
        )
        if not shadow_current:
            return _failed_verification(
                root=root,
                shadow_root=shadow_root,
                manifest_current=integrity.passed,
                shadow_current=False,
                error=(
                    source_verification.error
                    or "shadow source is stale, incomplete, or unsafe"
                ),
            )
        actual_receipt = _read_json(root / RECEIPT_FILE, "receipt")
        actual_config = _read_json(root / CONFIG_FILE, "config")
        config = _config_from_payload(actual_config)
        expected = _assemble_report(
            shadow_root=shadow_root,
            config=config,
            recorded_at_utc=_text(actual_receipt.get("recorded_at_utc")),
            source_verification=source_verification,
        )
        actual_checks = _read_csv(root / CHECKS_FILE, "checks")
        actual_observations = _read_csv(
            root / OBSERVATIONS_FILE,
            "markouts",
        )
        actual_cost_sensitivity = _read_csv(
            root / COST_SENSITIVITY_FILE,
            "cost sensitivity",
        )
        actual_horizon_summary = _read_csv(
            root / HORIZON_SUMMARY_FILE,
            "horizon summary",
        )
        actual_cost_summary = _read_csv(
            root / COST_SUMMARY_FILE,
            "cost summary",
        )
        actual_summary = _read_csv(root / SUMMARY_FILE, "summary")
        actual_summary_row = _single_row(actual_summary, "summary")
        actual_runbook = (root / RUNBOOK_FILE).read_text(encoding="utf-8")
        recursive_dependencies = _recursive_dependencies(
            shadow_root / MANIFEST_NAME,
            {shadow_root, shadow_root / MANIFEST_NAME},
        )
        manifest_inputs_current = _manifest_inputs_match(
            inputs,
            shadow_root=shadow_root,
            shadow_manifest_path=shadow_root / MANIFEST_NAME,
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
            and _dataframe_records_equal(
                actual_observations,
                expected.observations,
            )
            and _dataframe_records_equal(
                actual_cost_sensitivity,
                expected.cost_sensitivity,
            )
            and _dataframe_records_equal(
                actual_horizon_summary,
                expected.horizon_summary,
            )
            and _dataframe_records_equal(
                actual_cost_summary,
                expected.cost_summary,
            )
            and _dataframe_records_equal(actual_summary, expected.summary)
            and _jsonable(actual_receipt) == _jsonable(expected.receipt)
            and _jsonable(actual_config) == _jsonable(expected.config)
            and actual_runbook == _runbook_markdown(expected.summary.iloc[0])
            and _jsonable(manifest.get("extra"))
            == _jsonable(expected_extra)
            and parameters_current
            and manifest_inputs_current
        )
        calibration_only = _surfaces_calibration_only(
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
        completed = bool(expected.completed)
        verified = bool(
            integrity.passed
            and shadow_current
            and artifacts_consistent
            and calibration_only
            and non_authorizing
        )
        return ProviderMarketDataImbalanceLiveDryrunShadowCalibrationVerification(
            verified=verified,
            completed=completed,
            insufficient=not completed,
            manifest_current=integrity.passed,
            shadow_current=shadow_current,
            artifacts_consistent=artifacts_consistent,
            calibration_only=calibration_only,
            non_authorizing=non_authorizing,
            output_dir=root,
            shadow_dir=shadow_root,
            error="" if verified else "shadow calibration verification failed",
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _failed_verification(
            root=root,
            shadow_root=shadow_root,
            manifest_current=integrity.passed,
            shadow_current=False,
            error=str(exc),
        )


def _assemble_report(
    *,
    shadow_root: Path,
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    recorded_at_utc: str,
    source_verification: Any,
) -> ProviderMarketDataImbalanceLiveDryrunShadowCalibrationReport:
    shadow_manifest_path = shadow_root / MANIFEST_NAME
    shadow_manifest = _read_json(shadow_manifest_path, "shadow manifest")
    if _text(shadow_manifest.get("run_type")) != SHADOW_EVALUATOR_RUN_TYPE:
        raise ValueError("calibration source has the wrong run type")
    shadow_receipt = _read_json(
        shadow_root / SHADOW_RECEIPT_FILE,
        "shadow receipt",
    )
    shadow_config = _read_json(
        shadow_root / SHADOW_CONFIG_FILE,
        "shadow config",
    )
    features = _read_csv(shadow_root / SHADOW_FEATURES_FILE, "features")
    intents = _read_csv(shadow_root / SHADOW_INTENTS_FILE, "intents")
    settings = _mapping(shadow_config.get("settings"))
    tick_size = _positive_number(settings.get("tick_size"), "tick_size")
    source_lot_size = _positive_integer(
        settings.get("lot_size"),
        "source_lot_size",
    )
    evaluation = evaluate_shadow_markout_calibration(
        features,
        intents,
        tick_size=tick_size,
        source_lot_size=source_lot_size,
        config=_core_config(config),
    )
    recursive_dependencies = _recursive_dependencies(
        shadow_manifest_path,
        {shadow_root, shadow_manifest_path},
    )
    if len(recursive_dependencies) > config.max_dependency_count:
        raise ValueError(
            "shadow calibration dependency graph exceeds configured limit"
        )
    checks = _checks(
        source_verification=source_verification,
        evaluation=evaluation,
        config=config,
        recursive_dependency_count=len(recursive_dependencies),
    )
    receipt_core = _receipt_core(
        shadow_root=shadow_root,
        shadow_manifest_path=shadow_manifest_path,
        shadow_receipt=shadow_receipt,
        evaluation=evaluation,
        config=config,
        tick_size=tick_size,
        source_lot_size=source_lot_size,
        recorded_at_utc=recorded_at_utc,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "calibration_receipt_id": (
            f"provider-shadow-calibration-{receipt_sha256[:24]}"
        ),
        "calibration_receipt_sha256": receipt_sha256,
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
        shadow_root=shadow_root,
        tick_size=tick_size,
        source_lot_size=source_lot_size,
        evaluation=evaluation,
    )
    return ProviderMarketDataImbalanceLiveDryrunShadowCalibrationReport(
        checks=checks,
        observations=evaluation.observations,
        cost_sensitivity=evaluation.cost_sensitivity,
        horizon_summary=evaluation.horizon_summary,
        cost_summary=evaluation.cost_summary,
        summary=summary,
        receipt=receipt,
        config=config_payload,
    )


def _checks(
    *,
    source_verification: Any,
    evaluation: ShadowMarkoutCalibrationResult,
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    expected_observations = (
        evaluation.accepted_intent_count * len(config.horizons_ns)
    )
    expected_cost_rows = expected_observations * len(config.cost_scenarios)
    overall_horizons = evaluation.horizon_summary.loc[
        evaluation.horizon_summary["action_group"].eq("all")
    ]
    checks = [
        _check(
            "shadow_source_semantically_verified",
            "source",
            bool(source_verification.verified),
            "is",
            True,
            bool(source_verification.verified),
            "shadow source is not semantically verified",
        ),
        _check(
            "shadow_source_completed",
            "source",
            bool(source_verification.completed),
            "is",
            True,
            bool(source_verification.completed),
            "shadow source is not completed",
        ),
        _check(
            "shadow_source_non_authorizing",
            "source",
            bool(
                source_verification.shadow_only
                and source_verification.non_authorizing
            ),
            "is",
            True,
            bool(
                source_verification.shadow_only
                and source_verification.non_authorizing
            ),
            "shadow source is authorizing or not shadow-only",
        ),
        _check(
            "accepted_shadow_intents_present",
            "coverage",
            evaluation.accepted_intent_count,
            ">=",
            1,
            evaluation.accepted_intent_count >= 1,
            "no accepted shadow intents were available",
        ),
        _check(
            "observation_grid_complete",
            "artifacts",
            evaluation.observation_count,
            "==",
            expected_observations,
            evaluation.observation_count == expected_observations,
            "markout observation grid is incomplete",
        ),
        _check(
            "cost_sensitivity_grid_complete",
            "artifacts",
            len(evaluation.cost_sensitivity),
            "==",
            expected_cost_rows,
            len(evaluation.cost_sensitivity) == expected_cost_rows,
            "cost sensitivity grid is incomplete",
        ),
        _check(
            "cost_rates_explicitly_unvalidated",
            "costs",
            int(
                evaluation.cost_sensitivity["reference_status"]
                .astype(str)
                .eq(REFERENCE_STATUS)
                .sum()
            ),
            "==",
            expected_cost_rows,
            bool(
                expected_cost_rows > 0
                and evaluation.cost_sensitivity["reference_status"]
                .astype(str)
                .eq(REFERENCE_STATUS)
                .all()
            ),
            "a cost scenario is not labeled for external validation",
        ),
        _check(
            "dependency_graph_within_limit",
            "provenance",
            recursive_dependency_count,
            "<=",
            config.max_dependency_count,
            recursive_dependency_count <= config.max_dependency_count,
            "recursive source dependency limit exceeded",
        ),
    ]
    for row in overall_horizons.itertuples(index=False):
        horizon = int(row.requested_horizon_ns)
        checks.extend(
            [
                _check(
                    f"horizon_{horizon}_covered_observations",
                    "coverage",
                    int(row.covered_count),
                    ">=",
                    config.min_covered_observations_per_horizon,
                    int(row.covered_count)
                    >= config.min_covered_observations_per_horizon,
                    "horizon has too few covered observations",
                ),
                _check(
                    f"horizon_{horizon}_coverage_ratio",
                    "coverage",
                    float(row.coverage_ratio),
                    ">=",
                    config.min_coverage_ratio,
                    float(row.coverage_ratio)
                    >= config.min_coverage_ratio,
                    "horizon coverage ratio is below the configured floor",
                ),
            ]
        )
    checks.extend(
        [
            _check(
                "performance_gate_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "calibration enabled a performance gate",
            ),
            _check(
                "promotion_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "calibration enabled promotion",
            ),
            _check(
                "routing_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "calibration enabled routing",
            ),
            _check(
                "submission_disabled",
                "safety",
                False,
                "is",
                False,
                True,
                "calibration enabled submission",
            ),
        ]
    )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _receipt_core(
    *,
    shadow_root: Path,
    shadow_manifest_path: Path,
    shadow_receipt: Mapping[str, Any],
    evaluation: ShadowMarkoutCalibrationResult,
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    tick_size: float,
    source_lot_size: int,
    recorded_at_utc: str,
) -> dict[str, Any]:
    identity = _mapping(shadow_receipt.get("identity"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "non_authorizing_shadow_markout_calibration",
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "completed": evaluation.completed,
        "insufficient": not evaluation.completed,
        "incomplete_reason": evaluation.incomplete_reason,
        "source": {
            "shadow_receipt_id": _text(
                shadow_receipt.get("shadow_receipt_id")
            ),
            "shadow_receipt_sha256": _text(
                shadow_receipt.get("shadow_receipt_sha256")
            ).lower(),
        },
        "identity": {
            field: _text(identity.get(field))
            for field in (
                "strategy",
                "market",
                "target_mode",
                "provider",
                "transport",
                "exchange",
                "adapter",
                "session_id",
            )
        },
        "calibration": {
            "tick_size": tick_size,
            "source_lot_size": source_lot_size,
            "horizons_ns": list(config.horizons_ns),
            "max_horizon_overshoot_ns": (
                config.max_horizon_overshoot_ns
            ),
            "min_covered_observations_per_horizon": (
                config.min_covered_observations_per_horizon
            ),
            "min_coverage_ratio": config.min_coverage_ratio,
            "cost_scenarios": [
                asdict(scenario) for scenario in config.cost_scenarios
            ],
        },
        "outcome": {
            "accepted_intent_count": evaluation.accepted_intent_count,
            "observation_count": evaluation.observation_count,
            "covered_observation_count": (
                evaluation.covered_observation_count
            ),
            "cost_sensitivity_row_count": len(evaluation.cost_sensitivity),
            "horizon_summary_row_count": len(evaluation.horizon_summary),
            "cost_summary_row_count": len(evaluation.cost_summary),
        },
        "artifacts": {
            "observations_records_sha256": _records_sha256(
                evaluation.observations
            ),
            "cost_sensitivity_records_sha256": _records_sha256(
                evaluation.cost_sensitivity
            ),
            "horizon_summary_records_sha256": _records_sha256(
                evaluation.horizon_summary
            ),
            "cost_summary_records_sha256": _records_sha256(
                evaluation.cost_summary
            ),
        },
        "proof_contract": {
            "shadow_path": str(shadow_root),
            "shadow_manifest_path": str(shadow_manifest_path),
            "shadow_manifest_sha256": file_sha256(shadow_manifest_path),
        },
        "safety": _safety_payload(),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    evaluation: ShadowMarkoutCalibrationResult,
    checks: pd.DataFrame,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    identity = _mapping(receipt.get("identity"))
    overall = evaluation.horizon_summary.loc[
        evaluation.horizon_summary["action_group"].eq("all")
    ]
    max_horizon = int(max(evaluation.horizon_summary["requested_horizon_ns"]))
    terminal = overall.loc[
        overall["requested_horizon_ns"].eq(max_horizon)
    ].iloc[0]
    return pd.DataFrame(
        [
            {
                "passed": evaluation.completed and failed_checks == 0,
                "completed": evaluation.completed,
                "insufficient": not evaluation.completed,
                "status": (
                    "completed_non_authorizing_calibration"
                    if evaluation.completed
                    else "insufficient_shadow_observation_coverage"
                ),
                "incomplete_reason": evaluation.incomplete_reason,
                "failed_checks": failed_checks,
                "calibration_receipt_id": _text(
                    receipt.get("calibration_receipt_id")
                ),
                "calibration_receipt_sha256": _text(
                    receipt.get("calibration_receipt_sha256")
                ),
                "shadow_receipt_id": _text(
                    _mapping(receipt.get("source")).get("shadow_receipt_id")
                ),
                "provider": _text(identity.get("provider")),
                "market": _text(identity.get("market")),
                "session_id": _text(identity.get("session_id")),
                "accepted_intent_count": evaluation.accepted_intent_count,
                "observation_count": evaluation.observation_count,
                "covered_observation_count": (
                    evaluation.covered_observation_count
                ),
                "minimum_horizon_coverage_ratio": round(
                    float(overall["coverage_ratio"].min()),
                    10,
                ),
                "maximum_requested_horizon_ns": max_horizon,
                "terminal_mean_directional_mid_move_ticks": terminal[
                    "mean_directional_mid_move_ticks"
                ],
                "terminal_mean_touch_markout_ticks": terminal[
                    "mean_touch_markout_ticks"
                ],
                "terminal_adverse_selection_rate": terminal[
                    "adverse_selection_rate"
                ],
                "cost_scenario_count": len(
                    receipt["calibration"]["cost_scenarios"]
                ),
                "minimum_cost_break_even_rate": _numeric_min(
                    evaluation.cost_summary,
                    "cost_break_even_rate",
                ),
                "maximum_mean_round_trip_cost_ticks": _numeric_max(
                    evaluation.cost_summary,
                    "mean_round_trip_cost_ticks",
                ),
                "recursive_dependency_count": recursive_dependency_count,
                **_safety_payload(),
                "next_gate": "multi_session_shadow_calibration_stability",
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
    receipt: Mapping[str, Any],
    shadow_root: Path,
    tick_size: float,
    source_lot_size: int,
    evaluation: ShadowMarkoutCalibrationResult,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "shadow_dir": str(shadow_root),
        "tick_size": tick_size,
        "source_lot_size": source_lot_size,
        "calibration_receipt_id": _text(
            receipt.get("calibration_receipt_id")
        ),
        "calibration_receipt_sha256": _text(
            receipt.get("calibration_receipt_sha256")
        ),
        "completed": evaluation.completed,
        "insufficient": not evaluation.completed,
        "incomplete_reason": evaluation.incomplete_reason,
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
        "completed": _explicit_true(summary, "completed"),
        "insufficient": _explicit_true(summary, "insufficient"),
        "status": _text(summary.get("status")),
        "incomplete_reason": _text(summary.get("incomplete_reason")),
        "calibration_receipt_id": _text(
            receipt.get("calibration_receipt_id")
        ),
        "calibration_receipt_sha256": _text(
            receipt.get("calibration_receipt_sha256")
        ),
        "provider": _text(identity.get("provider")),
        "market": _text(identity.get("market")),
        "target_mode": "live_dryrun",
        "accepted_intent_count": int(summary["accepted_intent_count"]),
        "observation_count": int(summary["observation_count"]),
        **_safety_payload(),
    }


def _runbook_markdown(summary: pd.Series) -> str:
    return "\n".join(
        [
            "# Provider Shadow Markout Calibration",
            "",
            f"- Status: `{summary['status']}`",
            f"- Calibration receipt: `{summary['calibration_receipt_id']}`",
            f"- Provider identity: `{summary['provider']}` (proof label only)",
            f"- Session: `{summary['session_id']}`",
            f"- Accepted intents: `{summary['accepted_intent_count']}`",
            f"- Markout observations: `{summary['observation_count']}`",
            (
                "- Minimum horizon coverage: "
                f"`{summary['minimum_horizon_coverage_ratio']}`"
            ),
            "- Performance gate enabled: no",
            "- Strategy promoted: no",
            "- Routing or submission enabled: no",
            "- Cost rates require current external validation: yes",
            "",
            (
                "The cost scenarios are repository reference assumptions, not "
                "a current exchange circular or broker quote. This calibration "
                "cannot authorize promotion, routing, submission, or release."
            ),
            "",
        ]
    )


def _config_from_payload(
    payload: Mapping[str, Any],
) -> ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig:
    settings = _mapping(payload.get("settings"))
    expected_fields = {
        item.name
        for item in fields(
            ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig
        )
    }
    if set(settings) != expected_fields:
        raise ValueError("shadow calibration config settings are incomplete")
    raw_scenarios = settings.get("cost_scenarios")
    if not isinstance(raw_scenarios, list):
        raise ValueError("cost_scenarios must be a JSON list")
    scenario_fields = {item.name for item in fields(ShadowCostScenario)}
    scenarios = []
    for raw in raw_scenarios:
        selected = _mapping(raw)
        if set(selected) != scenario_fields:
            raise ValueError("cost scenario fields are incomplete")
        scenarios.append(ShadowCostScenario(**selected))
    config = ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig(
        horizons_ns=tuple(settings["horizons_ns"]),
        max_horizon_overshoot_ns=settings["max_horizon_overshoot_ns"],
        min_covered_observations_per_horizon=settings[
            "min_covered_observations_per_horizon"
        ],
        min_coverage_ratio=settings["min_coverage_ratio"],
        cost_scenarios=tuple(scenarios),
        max_dependency_count=settings["max_dependency_count"],
    )
    _validate_report_config(config)
    return config


def _core_config(
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
) -> ShadowMarkoutCalibrationConfig:
    return ShadowMarkoutCalibrationConfig(
        horizons_ns=tuple(config.horizons_ns),
        max_horizon_overshoot_ns=config.max_horizon_overshoot_ns,
        min_covered_observations_per_horizon=(
            config.min_covered_observations_per_horizon
        ),
        min_coverage_ratio=config.min_coverage_ratio,
        cost_scenarios=tuple(config.cost_scenarios),
    )


def _validate_report_config(
    config: ProviderMarketDataImbalanceLiveDryrunShadowCalibrationConfig,
) -> None:
    if (
        isinstance(config.max_dependency_count, bool)
        or not isinstance(config.max_dependency_count, int)
        or config.max_dependency_count <= 0
    ):
        raise ValueError("max_dependency_count must be a positive integer")
    if not config.horizons_ns or not config.cost_scenarios:
        raise ValueError("horizons and cost scenarios must not be empty")
    if any(
        scenario.reference_status != REFERENCE_STATUS
        for scenario in config.cost_scenarios
    ):
        raise ValueError(
            "all cost scenarios must require external validation"
        )


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    shadow_root: Path,
    shadow_manifest_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    expected_keys = {
        "shadow_evaluation",
        "shadow_evaluation_manifest",
    }
    if recursive_dependencies:
        expected_keys.add("shadow_recursive_dependencies")
    if set(inputs) != expected_keys:
        return False
    expected_paths = {
        shadow_root,
        shadow_manifest_path,
        *recursive_dependencies,
    }
    return set(_fingerprint_paths(inputs)) == {
        path.resolve() for path in expected_paths
    }


def _recursive_dependencies(
    manifest_path: Path,
    excluded: set[Path],
) -> list[Path]:
    excluded_resolved = {path.resolve() for path in excluded}
    return [
        path
        for path in manifest_dependency_paths(manifest_path)
        if path.resolve() not in excluded_resolved
    ]


def _reject_output_collision(output_dir: Path, shadow_root: Path) -> None:
    if output_dir == shadow_root or _is_relative_to(output_dir, shadow_root):
        raise ValueError("calibration output must not overlap its shadow source")
    if _is_relative_to(shadow_root, output_dir):
        raise ValueError("calibration output must not contain its shadow source")


def _surfaces_calibration_only(
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
    shadow_root: Path | None,
    manifest_current: bool,
    shadow_current: bool,
    error: str,
) -> ProviderMarketDataImbalanceLiveDryrunShadowCalibrationVerification:
    return ProviderMarketDataImbalanceLiveDryrunShadowCalibrationVerification(
        verified=False,
        completed=False,
        insufficient=False,
        manifest_current=manifest_current,
        shadow_current=shadow_current,
        artifacts_consistent=False,
        calibration_only=False,
        non_authorizing=False,
        output_dir=root,
        shadow_dir=shadow_root,
        error=error,
    )


def _safety_payload() -> dict[str, bool]:
    return {
        **{field: False for field in SAFETY_FALSE_FIELDS},
        **{field: True for field in SAFETY_TRUE_FIELDS},
    }


def _check(
    check: str,
    component: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": check,
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
        for item in value.values():
            paths.extend(_fingerprint_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_fingerprint_paths(item))
    return paths


def _numeric_min(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    if column == "cost_break_even_met":
        values = frame[column].dropna().map(_bool).astype(float)
    else:
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


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be positive and finite")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be positive and finite") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return parsed


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if not math.isfinite(parsed) or not parsed.is_integer() or parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(parsed)


def _utc_text(value: Any) -> str:
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("recorded_at_utc must be an ISO UTC timestamp") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        raise ValueError("recorded_at_utc must use UTC")
    return parsed.isoformat()


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
    return _text(value).lower() in {"true", "1", "yes", "ready", "passed"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if value is pd.NA:
        return None
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
