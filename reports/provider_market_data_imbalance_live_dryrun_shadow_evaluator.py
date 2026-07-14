from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
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
from reports.provider_market_data_imbalance_live_dryrun_handoff import (
    verify_provider_market_data_imbalance_live_dryrun_handoff,
)
from reports.provider_market_data_imbalance_live_dryrun_runtime_launcher import (
    RUN_TYPE as RUNTIME_LAUNCHER_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_runtime_launcher,
)
from shadow_microprice_evaluator import (
    ShadowKillSwitch,
    ShadowMicropriceConfig,
    ShadowMicropriceEvaluationError,
    ShadowMicropriceEvaluationResult,
    ShadowRuntimeLimits,
    evaluate_shadow_microprice_session,
)


RUN_TYPE = "provider_market_data_imbalance_live_dryrun_shadow_evaluator"
CONTRACT_VERSION = (
    "provider_market_data_imbalance_live_dryrun_shadow_evaluator/v1"
)
LAUNCHER_RECEIPT_FILE = (
    "provider_market_data_imbalance_live_dryrun_terminal_receipt.json"
)
LAUNCHER_TELEMETRY_FILE = (
    "provider_market_data_imbalance_live_dryrun_market_data_telemetry.csv"
)
HANDOFF_PLAN_FILE = (
    "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
)
SHADOW_ARTIFACTS = (
    "provider_market_data_imbalance_live_dryrun_shadow_checks.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_features.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_intents.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_summary.csv",
    "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json",
    "provider_market_data_imbalance_live_dryrun_shadow_config.json",
    "provider_market_data_imbalance_live_dryrun_shadow_runbook.md",
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
    "release_approved",
)
SAFETY_TRUE_FIELDS = (
    "shadow_only",
    "market_data_read_only",
    "deterministic_evaluation",
    "broker_neutral_intents_only",
    "kill_switch_armed",
    "terminal_flatten_required",
    "requires_separate_order_runtime",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowConfig(
    ShadowMicropriceConfig
):
    max_dependency_count: int = 32_768


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowReport:
    checks: pd.DataFrame
    features: pd.DataFrame
    intents: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def completed(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("completed", False))
        )

    @property
    def halted(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("halted", False))
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunShadowVerification:
    verified: bool
    completed: bool
    halted: bool
    manifest_current: bool
    launcher_current: bool
    handoff_current: bool
    artifacts_consistent: bool
    shadow_only: bool
    non_authorizing: bool
    output_dir: Path
    launcher_dir: Path | None
    handoff_dir: Path | None
    error: str = ""


def write_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
    launcher_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig | None = None,
) -> ProviderMarketDataImbalanceLiveDryrunShadowReport:
    config = config or ProviderMarketDataImbalanceLiveDryrunShadowConfig()
    _validate_config(config)
    launcher_candidate = Path(launcher_dir)
    launcher_root = (
        launcher_candidate.parent
        if launcher_candidate.is_file()
        else launcher_candidate
    ).resolve()
    launcher_manifest_path = launcher_root / MANIFEST_NAME
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"shadow evaluator output already exists: {out}")

    launcher_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            launcher_root
        )
    )
    if not (
        launcher_verification.verified
        and launcher_verification.completed
        and launcher_verification.simulation_only
        and launcher_verification.non_authorizing
    ):
        raise ValueError(
            "shadow evaluator requires a verified completed simulation-only "
            "non-authorizing launcher: "
            + (launcher_verification.error or "launcher_not_completed")
        )
    handoff_root = launcher_verification.handoff_dir
    if handoff_root is None:
        raise ValueError("shadow evaluator launcher has no handoff source")
    handoff_root = handoff_root.resolve()
    handoff_manifest_path = handoff_root / MANIFEST_NAME
    handoff_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_root)
    )
    if not (
        handoff_verification.verified
        and handoff_verification.ready
        and handoff_verification.non_authorizing
    ):
        raise ValueError("shadow evaluator handoff is not current and ready")

    launcher_manifest = _read_json(
        launcher_manifest_path,
        "runtime-launcher manifest",
    )
    if _text(launcher_manifest.get("run_type")) != RUNTIME_LAUNCHER_RUN_TYPE:
        raise ValueError("shadow evaluator source has the wrong run type")
    launcher_receipt = _read_json(
        launcher_root / LAUNCHER_RECEIPT_FILE,
        "runtime-launcher terminal receipt",
    )
    launcher_telemetry = _read_csv(
        launcher_root / LAUNCHER_TELEMETRY_FILE,
        "runtime-launcher telemetry",
    )
    handoff_plan = _read_json(
        handoff_root / HANDOFF_PLAN_FILE,
        "live-dry-run handoff plan",
    )
    _reject_output_collision(out, launcher_root, handoff_root)
    recursive_dependencies = _recursive_dependencies(
        launcher_manifest_path,
        {
            launcher_root,
            launcher_manifest_path,
            handoff_root,
            handoff_manifest_path,
        },
    )
    if len(recursive_dependencies) > config.max_dependency_count:
        raise ValueError("shadow evaluator dependency graph exceeds configured limit")

    _validate_source_identity(launcher_receipt, handoff_plan)
    limits = _limits_from_handoff(handoff_plan)
    kill_switch = _kill_switch_from_handoff(handoff_plan)
    evaluation = evaluate_shadow_microprice_session(
        launcher_telemetry,
        config=_shadow_config(config),
        limits=limits,
        kill_switch=kill_switch,
    )
    checks = _checks(
        launcher_verification=launcher_verification,
        handoff_verification=handoff_verification,
        evaluation=evaluation,
        limits=limits,
        kill_switch=kill_switch,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    recorded_at_utc = datetime.now(timezone.utc).isoformat()
    receipt_core = _receipt_core(
        launcher_root=launcher_root,
        launcher_manifest_path=launcher_manifest_path,
        launcher_receipt=launcher_receipt,
        handoff_root=handoff_root,
        handoff_manifest_path=handoff_manifest_path,
        handoff_plan=handoff_plan,
        evaluation=evaluation,
        config=config,
        limits=limits,
        recorded_at_utc=recorded_at_utc,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "shadow_receipt_id": f"provider-shadow-{receipt_sha256[:24]}",
        "shadow_receipt_sha256": receipt_sha256,
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
        launcher_root=launcher_root,
        handoff_root=handoff_root,
        handoff_plan=handoff_plan,
        limits=limits,
        evaluation=evaluation,
    )

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_shadow_checks.csv",
        index=False,
    )
    evaluation.features.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_shadow_features.csv",
        index=False,
    )
    evaluation.intents.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_shadow_intents.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_shadow_summary.csv",
        index=False,
    )
    (
        out
        / "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json"
    ).write_text(
        json.dumps(_jsonable(receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_shadow_config.json"
    ).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_shadow_runbook.md"
    ).write_text(
        _runbook_markdown(summary.iloc[0]),
        encoding="utf-8",
    )

    final_launcher = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
            launcher_root
        )
    )
    if (
        not final_launcher.verified
        or not final_launcher.completed
        or file_sha256(launcher_manifest_path)
        != receipt["proof_contract"]["launcher_manifest_sha256"]
        or file_sha256(handoff_manifest_path)
        != receipt["proof_contract"]["handoff_manifest_sha256"]
    ):
        raise RuntimeError("launcher or handoff changed during shadow evaluation")
    manifest_inputs: dict[str, Any] = {
        "runtime_launcher": launcher_root,
        "runtime_launcher_manifest": launcher_manifest_path,
        "live_dryrun_handoff": handoff_root,
        "live_dryrun_handoff_manifest": handoff_manifest_path,
    }
    if recursive_dependencies:
        manifest_inputs["launcher_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(receipt, evaluation),
    )
    return ProviderMarketDataImbalanceLiveDryrunShadowReport(
        checks=checks,
        features=evaluation.features,
        intents=evaluation.intents,
        summary=summary,
        receipt=receipt,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_live_dryrun_shadow_evaluation(
    shadow_dir: str | Path,
) -> ProviderMarketDataImbalanceLiveDryrunShadowVerification:
    candidate = Path(shadow_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=SHADOW_ARTIFACTS,
        require_input_fingerprints=True,
    )
    launcher_root: Path | None = None
    handoff_root: Path | None = None
    try:
        manifest = _read_json(manifest_path, "shadow-evaluator manifest")
        inputs = _mapping(manifest.get("inputs"))
        launcher_record = _mapping(inputs.get("runtime_launcher"))
        handoff_record = _mapping(inputs.get("live_dryrun_handoff"))
        if (
            launcher_record.get("kind") != "directory"
            or handoff_record.get("kind") != "directory"
            or not _text(launcher_record.get("path"))
            or not _text(handoff_record.get("path"))
        ):
            raise ValueError("shadow-evaluator input contract is invalid")
        launcher_root = Path(str(launcher_record["path"])).resolve()
        handoff_root = Path(str(handoff_record["path"])).resolve()
        launcher_manifest_path = launcher_root / MANIFEST_NAME
        handoff_manifest_path = handoff_root / MANIFEST_NAME
        launcher_verification = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
                launcher_root
            )
        )
        handoff_verification = (
            verify_provider_market_data_imbalance_live_dryrun_handoff(
                handoff_root
            )
        )
        launcher_current = bool(
            launcher_verification.verified
            and launcher_verification.completed
            and launcher_verification.simulation_only
            and launcher_verification.non_authorizing
        )
        handoff_current = bool(
            handoff_verification.verified
            and handoff_verification.ready
            and handoff_verification.non_authorizing
            and launcher_verification.handoff_dir == handoff_root
        )
        receipt = _read_json(
            root
            / "provider_market_data_imbalance_live_dryrun_shadow_terminal_receipt.json",
            "shadow terminal receipt",
        )
        summary_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_shadow_summary.csv",
            "shadow summary",
        )
        summary = _single_row(summary_frame, "shadow summary")
        saved_config = _read_json(
            root / "provider_market_data_imbalance_live_dryrun_shadow_config.json",
            "shadow config",
        )
        shadow_only = _surfaces_shadow_only(
            summary,
            receipt,
            saved_config,
            _mapping(manifest.get("extra")),
        )
        non_authorizing = _surfaces_non_authorizing(
            summary,
            receipt,
            saved_config,
            _mapping(manifest.get("extra")),
        )
        if not launcher_current or not handoff_current:
            return _verification(
                root=root,
                launcher_root=launcher_root,
                handoff_root=handoff_root,
                manifest_current=bool(integrity.passed),
                launcher_current=launcher_current,
                handoff_current=handoff_current,
                shadow_only=shadow_only,
                non_authorizing=non_authorizing,
                error="shadow_evaluator_source_not_current",
            )

        checks_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_shadow_checks.csv",
            "shadow checks",
        )
        features_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_shadow_features.csv",
            "shadow features",
        )
        intents_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_shadow_intents.csv",
            "shadow intents",
        )
        runbook = (
            root / "provider_market_data_imbalance_live_dryrun_shadow_runbook.md"
        ).read_text(encoding="utf-8")
        launcher_manifest = _read_json(
            launcher_manifest_path,
            "runtime-launcher manifest",
        )
        if _text(launcher_manifest.get("run_type")) != RUNTIME_LAUNCHER_RUN_TYPE:
            raise ValueError("shadow evaluator source has the wrong run type")
        launcher_receipt = _read_json(
            launcher_root / LAUNCHER_RECEIPT_FILE,
            "runtime-launcher terminal receipt",
        )
        launcher_telemetry = _read_csv(
            launcher_root / LAUNCHER_TELEMETRY_FILE,
            "runtime-launcher telemetry",
        )
        handoff_plan = _read_json(
            handoff_root / HANDOFF_PLAN_FILE,
            "live-dry-run handoff plan",
        )
        settings = dict(
            _mapping(_mapping(manifest.get("parameters")).get("config"))
        )
        config = ProviderMarketDataImbalanceLiveDryrunShadowConfig(**settings)
        _validate_config(config)
        recursive_dependencies = _recursive_dependencies(
            launcher_manifest_path,
            {
                launcher_root,
                launcher_manifest_path,
                handoff_root,
                handoff_manifest_path,
            },
        )
        _validate_source_identity(launcher_receipt, handoff_plan)
        limits = _limits_from_handoff(handoff_plan)
        kill_switch = _kill_switch_from_handoff(handoff_plan)
        evaluation = evaluate_shadow_microprice_session(
            launcher_telemetry,
            config=_shadow_config(config),
            limits=limits,
            kill_switch=kill_switch,
        )
        expected_checks = _checks(
            launcher_verification=launcher_verification,
            handoff_verification=handoff_verification,
            evaluation=evaluation,
            limits=limits,
            kill_switch=kill_switch,
            recursive_dependency_count=len(recursive_dependencies),
            config=config,
        )
        expected_core = _receipt_core(
            launcher_root=launcher_root,
            launcher_manifest_path=launcher_manifest_path,
            launcher_receipt=launcher_receipt,
            handoff_root=handoff_root,
            handoff_manifest_path=handoff_manifest_path,
            handoff_plan=handoff_plan,
            evaluation=evaluation,
            config=config,
            limits=limits,
            recorded_at_utc=_text(receipt.get("recorded_at_utc")),
        )
        receipt_sha256 = _canonical_sha256(expected_core)
        expected_receipt = {
            **expected_core,
            "shadow_receipt_id": f"provider-shadow-{receipt_sha256[:24]}",
            "shadow_receipt_sha256": receipt_sha256,
        }
        expected_summary = _summary(
            receipt=expected_receipt,
            evaluation=evaluation,
            checks=expected_checks,
            recursive_dependency_count=len(recursive_dependencies),
        )
        expected_config = _config_payload(
            config=config,
            receipt=expected_receipt,
            launcher_root=launcher_root,
            handoff_root=handoff_root,
            handoff_plan=handoff_plan,
            limits=limits,
            evaluation=evaluation,
        )
        expected_extra = _manifest_extra(expected_receipt, evaluation)
        artifacts_consistent = bool(
            receipt == expected_receipt
            and saved_config == expected_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(features_frame, evaluation.features)
            and _dataframe_records_equal(intents_frame, evaluation.intents)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and runbook == _runbook_markdown(expected_summary.iloc[0])
            and dict(_mapping(manifest.get("extra"))) == expected_extra
            and _manifest_inputs_match(
                inputs,
                launcher_root=launcher_root,
                launcher_manifest_path=launcher_manifest_path,
                handoff_root=handoff_root,
                handoff_manifest_path=handoff_manifest_path,
                recursive_dependencies=recursive_dependencies,
            )
        )
        verified = bool(
            integrity.passed
            and launcher_current
            and handoff_current
            and artifacts_consistent
            and shadow_only
            and non_authorizing
        )
        checks_passed = bool(expected_checks["passed"].map(_bool).all())
        completed = bool(
            verified
            and checks_passed
            and evaluation.completed
            and _explicit_true(summary, "passed")
            and _explicit_true(summary, "ready")
            and _explicit_true(summary, "completed")
            and _explicit_true(receipt, "completed")
            and _explicit_true(saved_config, "completed")
            and _explicit_true(_mapping(manifest.get("extra")), "passed")
            and _explicit_true(_mapping(manifest.get("extra")), "ready")
            and _explicit_true(_mapping(manifest.get("extra")), "completed")
        )
        halted = bool(
            verified
            and evaluation.halted
            and _explicit_true(summary, "halted")
            and _explicit_true(receipt, "halted")
            and _explicit_true(saved_config, "halted")
            and _explicit_true(_mapping(manifest.get("extra")), "halted")
        )
        error = (
            integrity.error
            or (
                "shadow_evaluator_artifacts_disagree_with_sources"
                if not artifacts_consistent
                else ""
            )
            or (
                "shadow_evaluator_capability_contract_invalid"
                if not shadow_only
                else ""
            )
            or (
                "shadow_evaluator_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
        )
        return ProviderMarketDataImbalanceLiveDryrunShadowVerification(
            verified=verified,
            completed=completed,
            halted=halted,
            manifest_current=bool(integrity.passed),
            launcher_current=launcher_current,
            handoff_current=handoff_current,
            artifacts_consistent=artifacts_consistent,
            shadow_only=shadow_only,
            non_authorizing=non_authorizing,
            output_dir=root,
            launcher_dir=launcher_root,
            handoff_dir=handoff_root,
            error=error,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ShadowMicropriceEvaluationError,
    ) as exc:
        return _verification(
            root=root,
            launcher_root=launcher_root,
            handoff_root=handoff_root,
            manifest_current=bool(integrity.passed),
            launcher_current=False,
            handoff_current=False,
            shadow_only=False,
            non_authorizing=False,
            error=f"shadow_evaluator_unreadable:{exc}",
        )


def _checks(
    *,
    launcher_verification: Any,
    handoff_verification: Any,
    evaluation: ShadowMicropriceEvaluationResult,
    limits: ShadowRuntimeLimits,
    kill_switch: ShadowKillSwitch,
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig,
) -> pd.DataFrame:
    checks = [
        _check(
            "launcher_verified",
            "source",
            launcher_verification.verified,
            "is",
            True,
            launcher_verification.verified,
            "runtime launcher is not verified",
        ),
        _check(
            "launcher_completed",
            "source",
            launcher_verification.completed,
            "is",
            True,
            launcher_verification.completed,
            "runtime launcher is not completed",
        ),
        _check(
            "launcher_simulation_only",
            "source",
            launcher_verification.simulation_only,
            "is",
            True,
            launcher_verification.simulation_only,
            "runtime launcher is not simulation-only",
        ),
        _check(
            "launcher_non_authorizing",
            "source",
            launcher_verification.non_authorizing,
            "is",
            True,
            launcher_verification.non_authorizing,
            "runtime launcher is authorizing",
        ),
        _check(
            "handoff_verified",
            "source",
            handoff_verification.verified,
            "is",
            True,
            handoff_verification.verified,
            "live-dry-run handoff is not verified",
        ),
        _check(
            "handoff_ready",
            "source",
            handoff_verification.ready,
            "is",
            True,
            handoff_verification.ready,
            "live-dry-run handoff is not ready",
        ),
        _check(
            "kill_switch_armed",
            "safety",
            kill_switch.enabled,
            "is",
            True,
            all(asdict(kill_switch).values()),
            "retained kill-switch contract is incomplete",
        ),
        _check(
            "dependency_limit",
            "integrity",
            recursive_dependency_count,
            "<=",
            config.max_dependency_count,
            recursive_dependency_count <= config.max_dependency_count,
            "launcher dependency graph exceeds shadow limit",
        ),
        _check(
            "source_events_processed",
            "evaluation",
            evaluation.processed_event_count,
            "==",
            evaluation.source_event_count,
            evaluation.completed
            and evaluation.processed_event_count
            == evaluation.source_event_count,
            evaluation.halt_reason or "not all source events were processed",
        ),
        _check(
            "terminal_state_exclusive",
            "evaluation",
            int(evaluation.completed) + int(evaluation.halted),
            "==",
            1,
            evaluation.completed != evaluation.halted,
            "shadow terminal state is ambiguous",
        ),
        _check(
            "ending_shadow_position_flat",
            "limits",
            evaluation.ending_shadow_position_lots,
            "==",
            0,
            evaluation.ending_shadow_position_lots == 0,
            evaluation.halt_reason or "hypothetical position was not flattened",
        ),
        _check(
            "observed_intents_within_order_limit",
            "limits",
            evaluation.observed_intent_count,
            "<=",
            limits.max_orders_per_session,
            evaluation.observed_intent_count <= limits.max_orders_per_session,
            "observed intent count exceeds retained order limit",
        ),
        _check(
            "shadow_notional_within_limit",
            "limits",
            evaluation.cumulative_shadow_notional,
            "<=",
            limits.max_notional_per_session,
            evaluation.cumulative_shadow_notional
            <= limits.max_notional_per_session,
            "shadow notional exceeds retained limit",
        ),
        _check(
            "shadow_open_orders_zero",
            "limits",
            evaluation.max_shadow_open_orders,
            "<=",
            limits.max_open_orders,
            evaluation.max_shadow_open_orders == 0,
            "shadow evaluator created an open order",
        ),
        _check(
            "intents_not_routable",
            "safety",
            _intent_status_count(evaluation.intents, "routing_status", "not_routable"),
            "==",
            len(evaluation.intents),
            _intent_column_all(
                evaluation.intents,
                "routing_status",
                "not_routable",
            ),
            "a shadow intent is routable",
        ),
        _check(
            "intents_not_submitted",
            "safety",
            _intent_status_count(
                evaluation.intents,
                "submission_status",
                "not_submitted",
            ),
            "==",
            len(evaluation.intents),
            _intent_column_all(
                evaluation.intents,
                "submission_status",
                "not_submitted",
            ),
            "a shadow intent claims submission",
        ),
        _check(
            "execution_engine_not_loaded",
            "safety",
            False,
            "is",
            False,
            True,
            "shadow evaluator loaded an execution engine",
        ),
        _check(
            "broker_order_api_not_imported",
            "safety",
            False,
            "is",
            False,
            True,
            "shadow evaluator imported a broker order API",
        ),
        _check(
            "routing_disabled",
            "safety",
            False,
            "is",
            False,
            True,
            "shadow evaluator enabled routing",
        ),
        _check(
            "submission_disabled",
            "safety",
            False,
            "is",
            False,
            True,
            "shadow evaluator enabled submission",
        ),
    ]
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _receipt_core(
    *,
    launcher_root: Path,
    launcher_manifest_path: Path,
    launcher_receipt: Mapping[str, Any],
    handoff_root: Path,
    handoff_manifest_path: Path,
    handoff_plan: Mapping[str, Any],
    evaluation: ShadowMicropriceEvaluationResult,
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig,
    limits: ShadowRuntimeLimits,
    recorded_at_utc: str,
) -> dict[str, Any]:
    identity = _mapping(handoff_plan.get("identity"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "bounded_non_submitting_shadow_evaluation",
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "evaluation_mode": "deterministic_microprice_shadow",
        "completed": evaluation.completed,
        "halted": evaluation.halted,
        "halt_reason": evaluation.halt_reason,
        "source": {
            "launcher_receipt_id": _text(
                launcher_receipt.get("terminal_receipt_id")
            ),
            "launcher_receipt_sha256": _text(
                launcher_receipt.get("terminal_receipt_sha256")
            ).lower(),
            "handoff_id": _text(handoff_plan.get("handoff_id")),
            "handoff_plan_sha256": _text(
                handoff_plan.get("plan_sha256")
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
        "strategy": _jsonable(asdict(_shadow_config(config))),
        "retained_limits": _jsonable(asdict(limits)),
        "outcome": {
            "source_event_count": evaluation.source_event_count,
            "processed_event_count": evaluation.processed_event_count,
            "observed_intent_count": evaluation.observed_intent_count,
            "rejected_intent_count": evaluation.rejected_intent_count,
            "ending_shadow_position_lots": (
                evaluation.ending_shadow_position_lots
            ),
            "cumulative_shadow_notional": (
                evaluation.cumulative_shadow_notional
            ),
            "max_shadow_open_orders": evaluation.max_shadow_open_orders,
        },
        "artifacts": {
            "features_row_count": len(evaluation.features),
            "features_records_sha256": _canonical_sha256(
                evaluation.features.to_dict(orient="records")
            ),
            "intents_row_count": len(evaluation.intents),
            "intents_records_sha256": _canonical_sha256(
                evaluation.intents.to_dict(orient="records")
            ),
        },
        "proof_contract": {
            "launcher_path": str(launcher_root),
            "launcher_manifest_path": str(launcher_manifest_path),
            "launcher_manifest_sha256": file_sha256(launcher_manifest_path),
            "handoff_path": str(handoff_root),
            "handoff_manifest_path": str(handoff_manifest_path),
            "handoff_manifest_sha256": file_sha256(handoff_manifest_path),
        },
        "safety": _safety_payload(),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    evaluation: ShadowMicropriceEvaluationResult,
    checks: pd.DataFrame,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    identity = _mapping(receipt.get("identity"))
    return pd.DataFrame(
        [
            {
                "passed": evaluation.completed and failed_checks == 0,
                "ready": evaluation.completed and failed_checks == 0,
                "completed": evaluation.completed,
                "halted": evaluation.halted,
                "status": (
                    "completed_shadow_evaluation"
                    if evaluation.completed
                    else "halted_shadow_evaluation"
                ),
                "halt_reason": evaluation.halt_reason,
                "failed_checks": failed_checks,
                "shadow_receipt_id": _text(receipt.get("shadow_receipt_id")),
                "shadow_receipt_sha256": _text(
                    receipt.get("shadow_receipt_sha256")
                ),
                "launcher_receipt_id": _text(
                    _mapping(receipt.get("source")).get("launcher_receipt_id")
                ),
                "provider": _text(identity.get("provider")),
                "market": _text(identity.get("market")),
                "session_id": _text(identity.get("session_id")),
                "source_event_count": evaluation.source_event_count,
                "processed_event_count": evaluation.processed_event_count,
                "observed_intent_count": evaluation.observed_intent_count,
                "rejected_intent_count": evaluation.rejected_intent_count,
                "ending_shadow_position_lots": (
                    evaluation.ending_shadow_position_lots
                ),
                "cumulative_shadow_notional": (
                    evaluation.cumulative_shadow_notional
                ),
                "max_shadow_open_orders": evaluation.max_shadow_open_orders,
                "recursive_dependency_count": recursive_dependency_count,
                **_safety_payload(),
                "next_gate": "provider_market_data_shadow_calibration",
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig,
    receipt: Mapping[str, Any],
    launcher_root: Path,
    handoff_root: Path,
    handoff_plan: Mapping[str, Any],
    limits: ShadowRuntimeLimits,
    evaluation: ShadowMicropriceEvaluationResult,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "evaluation_mode": "deterministic_microprice_shadow",
        "launcher_dir": str(launcher_root),
        "handoff_dir": str(handoff_root),
        "handoff_identity": _jsonable(_mapping(handoff_plan.get("identity"))),
        "retained_limits": _jsonable(asdict(limits)),
        "shadow_receipt_id": _text(receipt.get("shadow_receipt_id")),
        "shadow_receipt_sha256": _text(receipt.get("shadow_receipt_sha256")),
        "completed": evaluation.completed,
        "halted": evaluation.halted,
        "halt_reason": evaluation.halt_reason,
        "outcome": _jsonable(_mapping(receipt.get("outcome"))),
        **_safety_payload(),
    }


def _manifest_extra(
    receipt: Mapping[str, Any],
    evaluation: ShadowMicropriceEvaluationResult,
) -> dict[str, Any]:
    identity = _mapping(receipt.get("identity"))
    return {
        "passed": evaluation.completed,
        "ready": evaluation.completed,
        "completed": evaluation.completed,
        "halted": evaluation.halted,
        "halt_reason": evaluation.halt_reason,
        "shadow_receipt_id": _text(receipt.get("shadow_receipt_id")),
        "shadow_receipt_sha256": _text(
            receipt.get("shadow_receipt_sha256")
        ),
        "provider": _text(identity.get("provider")),
        "market": _text(identity.get("market")),
        "target_mode": "live_dryrun",
        "source_event_count": evaluation.source_event_count,
        "observed_intent_count": evaluation.observed_intent_count,
        "rejected_intent_count": evaluation.rejected_intent_count,
        "ending_shadow_position_lots": evaluation.ending_shadow_position_lots,
        **_safety_payload(),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        **{field: False for field in SAFETY_FALSE_FIELDS},
        **{field: True for field in SAFETY_TRUE_FIELDS},
    }


def _runbook_markdown(summary: pd.Series) -> str:
    return "\n".join(
        [
            "# Provider Live-Dry-Run Microprice Shadow Evaluation",
            "",
            f"- Status: `{summary['status']}`",
            f"- Shadow receipt: `{summary['shadow_receipt_id']}`",
            f"- Provider identity: `{summary['provider']}` (source proof only)",
            f"- Session: `{summary['session_id']}`",
            f"- Source events: `{summary['source_event_count']}`",
            f"- Observed intents: `{summary['observed_intent_count']}`",
            f"- Rejected intents: `{summary['rejected_intent_count']}`",
            f"- Ending shadow position: `{summary['ending_shadow_position_lots']}`",
            f"- Halt reason: `{summary['halt_reason']}`",
            "- Execution engine loaded: no",
            "- Order object created: no",
            "- Broker order API imported or called: no",
            "- Routing enabled: no",
            "- Submission enabled: no",
            "",
            (
                "Intents are deterministic observations under an immediate-touch "
                "shadow assumption. They are not orders and cannot be routed or "
                "submitted. A separate controlled order runtime is required."
            ),
            "",
        ]
    )


def _surfaces_shadow_only(
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
        and _text(receipt.get("evaluation_mode"))
        == "deterministic_microprice_shadow"
        and _text(config.get("evaluation_mode"))
        == "deterministic_microprice_shadow"
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


def _limits_from_handoff(
    handoff_plan: Mapping[str, Any],
) -> ShadowRuntimeLimits:
    limits = _mapping(handoff_plan.get("limits"))
    return ShadowRuntimeLimits(
        max_orders_per_session=_exact_integer(
            limits.get("max_orders_per_session"),
            "max_orders_per_session",
        ),
        max_notional_per_session=_positive_number(
            limits.get("max_notional_per_session"),
            "max_notional_per_session",
        ),
        max_open_orders=_exact_integer(
            limits.get("max_open_orders"),
            "max_open_orders",
        ),
        max_position_lots=_exact_integer(
            limits.get("max_position_lots"),
            "max_position_lots",
        ),
    )


def _kill_switch_from_handoff(
    handoff_plan: Mapping[str, Any],
) -> ShadowKillSwitch:
    kill_switch = _mapping(handoff_plan.get("kill_switch"))
    return ShadowKillSwitch(
        enabled=_explicit_true(kill_switch, "enabled"),
        trigger_on_limit_breach=_explicit_true(
            kill_switch,
            "trigger_on_limit_breach",
        ),
        stop_new_orders=_explicit_true(kill_switch, "stop_new_orders"),
        cancel_open_orders=_explicit_true(kill_switch, "cancel_open_orders"),
    )


def _shadow_config(
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig,
) -> ShadowMicropriceConfig:
    return ShadowMicropriceConfig(
        lot_size=config.lot_size,
        intent_quantity_lots=config.intent_quantity_lots,
        tick_size=config.tick_size,
        entry_imbalance=config.entry_imbalance,
        exit_imbalance=config.exit_imbalance,
        min_microprice_edge_ticks=config.min_microprice_edge_ticks,
        max_spread_ticks=config.max_spread_ticks,
        min_depth=config.min_depth,
        hold_ns=config.hold_ns,
        cooloff_ns=config.cooloff_ns,
        terminal_flatten=config.terminal_flatten,
    )


def _validate_config(
    config: ProviderMarketDataImbalanceLiveDryrunShadowConfig,
) -> None:
    if (
        isinstance(config.max_dependency_count, bool)
        or not isinstance(config.max_dependency_count, int)
        or config.max_dependency_count <= 0
    ):
        raise ValueError("max_dependency_count must be a positive integer")
    _shadow_config(config)


def _validate_source_identity(
    launcher_receipt: Mapping[str, Any],
    handoff_plan: Mapping[str, Any],
) -> None:
    launcher_identity = _mapping(launcher_receipt.get("identity"))
    handoff_identity = _mapping(handoff_plan.get("identity"))
    fields = (
        "strategy",
        "market",
        "target_mode",
        "provider",
        "transport",
        "exchange",
        "adapter",
        "session_id",
    )
    mismatched = [
        field
        for field in fields
        if _identity(launcher_identity.get(field))
        != _identity(handoff_identity.get(field))
    ]
    if mismatched:
        raise ValueError(
            "shadow evaluator source identity differs: "
            + ", ".join(mismatched)
        )


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    launcher_root: Path,
    launcher_manifest_path: Path,
    handoff_root: Path,
    handoff_manifest_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    expected_keys = {
        "runtime_launcher",
        "runtime_launcher_manifest",
        "live_dryrun_handoff",
        "live_dryrun_handoff_manifest",
    }
    if recursive_dependencies:
        expected_keys.add("launcher_recursive_dependencies")
    if set(inputs) != expected_keys:
        return False
    expected_paths = {
        launcher_root,
        launcher_manifest_path,
        handoff_root,
        handoff_manifest_path,
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


def _reject_output_collision(
    output_dir: Path,
    launcher_root: Path,
    handoff_root: Path,
) -> None:
    for source in (launcher_root, handoff_root):
        if output_dir == source or _is_relative_to(output_dir, source):
            raise ValueError("shadow evaluator output must not overlap a source")
        if _is_relative_to(source, output_dir):
            raise ValueError("shadow evaluator output must not contain a source")


def _verification(
    *,
    root: Path,
    launcher_root: Path | None,
    handoff_root: Path | None,
    manifest_current: bool,
    launcher_current: bool,
    handoff_current: bool,
    shadow_only: bool,
    non_authorizing: bool,
    error: str,
) -> ProviderMarketDataImbalanceLiveDryrunShadowVerification:
    return ProviderMarketDataImbalanceLiveDryrunShadowVerification(
        verified=False,
        completed=False,
        halted=False,
        manifest_current=manifest_current,
        launcher_current=launcher_current,
        handoff_current=handoff_current,
        artifacts_consistent=False,
        shadow_only=shadow_only,
        non_authorizing=non_authorizing,
        output_dir=root,
        launcher_dir=launcher_root,
        handoff_dir=handoff_root,
        error=error,
    )


def _intent_status_count(
    intents: pd.DataFrame,
    column: str,
    expected: str,
) -> int:
    if column not in intents.columns:
        return 0
    return int((intents[column].astype(str) == expected).sum())


def _intent_column_all(
    intents: pd.DataFrame,
    column: str,
    expected: str,
) -> bool:
    return bool(
        column in intents.columns
        and (intents.empty or (intents[column].astype(str) == expected).all())
    )


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


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _dataframe_records_equal(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
) -> bool:
    if list(actual.columns) != list(expected.columns) or len(actual) != len(expected):
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


def _exact_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if not math.isfinite(parsed) or not parsed.is_integer() or parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(parsed)


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


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_text(value: Any) -> str:
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("recorded_at_utc must be an ISO UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("recorded_at_utc must use UTC")
    return parsed.isoformat()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _identity(value: Any) -> str:
    return _text(value).lower()


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
