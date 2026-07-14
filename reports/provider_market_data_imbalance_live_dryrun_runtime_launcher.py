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

from market_data_observation_simulator import (
    BoundedMarketDataSimulationConfig,
    BoundedMarketDataSimulationResult,
    MarketDataObservationSimulationError,
    simulate_bounded_market_data_session,
)
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
from reports.provider_market_data_imbalance_live_dryrun_runtime_preflight import (
    RUN_TYPE as RUNTIME_PREFLIGHT_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_runtime_preflight,
)


RUN_TYPE = "provider_market_data_imbalance_live_dryrun_runtime_launcher"
CONTRACT_VERSION = (
    "provider_market_data_imbalance_live_dryrun_runtime_launcher/v1"
)
HANDOFF_PLAN_FILE = (
    "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
)
PREFLIGHT_RECEIPT_FILE = (
    "provider_market_data_imbalance_live_dryrun_launch_receipt.json"
)
LAUNCHER_ARTIFACTS = (
    "provider_market_data_imbalance_live_dryrun_runtime_launcher_checks.csv",
    "provider_market_data_imbalance_live_dryrun_market_data_telemetry.csv",
    "provider_market_data_imbalance_live_dryrun_runtime_launcher_summary.csv",
    "provider_market_data_imbalance_live_dryrun_terminal_receipt.json",
    "provider_market_data_imbalance_live_dryrun_runtime_launcher_config.json",
    "provider_market_data_imbalance_live_dryrun_runtime_launcher_runbook.md",
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
PREFLIGHT_IDENTITY_FIELDS = (
    "provider",
    "adapter",
    "transport",
    "market",
    "exchange",
    "session_id",
)
SAFETY_FALSE_FIELDS = (
    "provider_network_called",
    "provider_backend_loaded",
    "credential_environment_read",
    "credential_values_stored",
    "strategy_execution_enabled",
    "order_generation_enabled",
    "broker_order_api_imported",
    "broker_order_api_called",
    "broker_api_called",
    "submission_enabled",
    "authorizes_submission",
    "release_approved",
)
SAFETY_TRUE_FIELDS = (
    "simulation_only",
    "market_data_only",
    "dry_run_only",
    "kill_switch_armed",
    "requires_separate_shadow_strategy_runtime",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
    BoundedMarketDataSimulationConfig
):
    max_dependency_count: int = 16_384


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherReport:
    checks: pd.DataFrame
    telemetry: pd.DataFrame
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
class ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherVerification:
    verified: bool
    completed: bool
    halted: bool
    manifest_current: bool
    preflight_current: bool
    handoff_current: bool
    artifacts_consistent: bool
    simulation_only: bool
    non_authorizing: bool
    output_dir: Path
    preflight_dir: Path | None
    handoff_dir: Path | None
    error: str = ""


def write_provider_market_data_imbalance_live_dryrun_runtime_launcher(
    preflight_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig | None = None,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherReport:
    config = config or ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig()
    _validate_launcher_config(config)
    preflight_root = Path(preflight_dir).resolve()
    preflight_manifest_path = preflight_root / MANIFEST_NAME
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"runtime launcher output already exists: {out}")

    preflight_verification = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            preflight_root
        )
    )
    if not (
        preflight_verification.verified
        and preflight_verification.ready
        and preflight_verification.credential_safe
        and preflight_verification.non_authorizing
    ):
        raise ValueError(
            "runtime launcher requires a verified ready credential-safe "
            "non-authorizing preflight: "
            + (preflight_verification.error or "preflight_not_ready")
        )
    handoff_root = preflight_verification.handoff_dir
    if handoff_root is None:
        raise ValueError("runtime launcher preflight has no handoff source")
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
        raise ValueError("runtime launcher handoff is not current and ready")

    preflight_manifest = _read_json(
        preflight_manifest_path,
        "runtime-preflight manifest",
    )
    if _text(preflight_manifest.get("run_type")) != RUNTIME_PREFLIGHT_RUN_TYPE:
        raise ValueError("runtime launcher source has the wrong run type")
    preflight_receipt = _read_json(
        preflight_root / PREFLIGHT_RECEIPT_FILE,
        "runtime-preflight receipt",
    )
    handoff_plan = _read_json(
        handoff_root / HANDOFF_PLAN_FILE,
        "live-dry-run handoff plan",
    )
    _reject_output_collision(out, preflight_root, handoff_root)
    recursive_dependencies = _recursive_dependencies(
        preflight_manifest_path,
        {
            preflight_root,
            preflight_manifest_path,
            handoff_root,
            handoff_manifest_path,
        },
    )
    if len(recursive_dependencies) > config.max_dependency_count:
        raise ValueError("runtime launcher dependency graph exceeds configured limit")

    identity = _mapping(handoff_plan.get("identity"))
    preflight_identity = _mapping(preflight_receipt.get("identity"))
    _validate_source_identity(identity, preflight_identity)
    simulation = simulate_bounded_market_data_session(
        config=_simulation_config(config),
        provider=_text(identity.get("provider")),
        adapter=_text(identity.get("adapter")),
        transport=_text(identity.get("transport")),
        market=_text(identity.get("market")),
        exchange=_text(identity.get("exchange")),
        session_id=_text(identity.get("session_id")),
        trading_date=_text(identity.get("trading_date")),
        timezone_name=_text(identity.get("timezone")),
        open_local=_text(identity.get("open_local")),
        close_local=_text(identity.get("close_local")),
        kill_switch_enabled=_explicit_true(
            _mapping(handoff_plan.get("kill_switch")),
            "enabled",
        ),
    )
    checks = _checks(
        preflight_verification=preflight_verification,
        handoff_verification=handoff_verification,
        preflight_receipt=preflight_receipt,
        handoff_plan=handoff_plan,
        simulation=simulation,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    recorded_at_utc = datetime.now(timezone.utc).isoformat()
    receipt_core = _receipt_core(
        preflight_root=preflight_root,
        preflight_manifest_path=preflight_manifest_path,
        preflight_receipt=preflight_receipt,
        handoff_root=handoff_root,
        handoff_manifest_path=handoff_manifest_path,
        handoff_plan=handoff_plan,
        simulation=simulation,
        config=config,
        recorded_at_utc=recorded_at_utc,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "terminal_receipt_id": f"provider-runtime-terminal-{receipt_sha256[:24]}",
        "terminal_receipt_sha256": receipt_sha256,
    }
    summary = _summary(
        receipt=receipt,
        simulation=simulation,
        checks=checks,
        recursive_dependency_count=len(recursive_dependencies),
    )
    config_payload = _config_payload(
        config=config,
        receipt=receipt,
        preflight_root=preflight_root,
        handoff_root=handoff_root,
        handoff_plan=handoff_plan,
        simulation=simulation,
    )

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_launcher_checks.csv",
        index=False,
    )
    simulation.telemetry.to_csv(
        out
        / "provider_market_data_imbalance_live_dryrun_market_data_telemetry.csv",
        index=False,
    )
    summary.to_csv(
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_launcher_summary.csv",
        index=False,
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_terminal_receipt.json"
    ).write_text(
        json.dumps(_jsonable(receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_runtime_launcher_config.json"
    ).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_runtime_launcher_runbook.md"
    ).write_text(
        _runbook_markdown(summary.iloc[0]),
        encoding="utf-8",
    )

    final_preflight = (
        verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
            preflight_root
        )
    )
    if (
        not final_preflight.verified
        or not final_preflight.ready
        or file_sha256(preflight_manifest_path)
        != receipt["proof_contract"]["preflight_manifest_sha256"]
        or file_sha256(handoff_manifest_path)
        != receipt["proof_contract"]["handoff_manifest_sha256"]
    ):
        raise RuntimeError("preflight or handoff changed during runtime launch")
    manifest_inputs: dict[str, Any] = {
        "runtime_preflight": preflight_root,
        "runtime_preflight_manifest": preflight_manifest_path,
        "live_dryrun_handoff": handoff_root,
        "live_dryrun_handoff_manifest": handoff_manifest_path,
    }
    if recursive_dependencies:
        manifest_inputs["preflight_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(receipt, simulation),
    )
    return ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherReport(
        checks=checks,
        telemetry=simulation.telemetry,
        summary=summary,
        receipt=receipt,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_live_dryrun_runtime_launcher(
    launcher_dir: str | Path,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherVerification:
    candidate = Path(launcher_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=LAUNCHER_ARTIFACTS,
        require_input_fingerprints=True,
    )
    preflight_root: Path | None = None
    handoff_root: Path | None = None
    try:
        manifest = _read_json(manifest_path, "runtime-launcher manifest")
        inputs = _mapping(manifest.get("inputs"))
        preflight_record = _mapping(inputs.get("runtime_preflight"))
        handoff_record = _mapping(inputs.get("live_dryrun_handoff"))
        if (
            preflight_record.get("kind") != "directory"
            or handoff_record.get("kind") != "directory"
            or not _text(preflight_record.get("path"))
            or not _text(handoff_record.get("path"))
        ):
            raise ValueError("runtime-launcher input contract is invalid")
        preflight_root = Path(str(preflight_record["path"])).resolve()
        handoff_root = Path(str(handoff_record["path"])).resolve()
        preflight_manifest_path = preflight_root / MANIFEST_NAME
        handoff_manifest_path = handoff_root / MANIFEST_NAME
        preflight_verification = (
            verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
                preflight_root
            )
        )
        handoff_verification = (
            verify_provider_market_data_imbalance_live_dryrun_handoff(
                handoff_root
            )
        )
        preflight_current = bool(
            preflight_verification.verified
            and preflight_verification.ready
            and preflight_verification.credential_safe
            and preflight_verification.non_authorizing
        )
        handoff_current = bool(
            handoff_verification.verified
            and handoff_verification.ready
            and handoff_verification.non_authorizing
            and preflight_verification.handoff_dir == handoff_root
        )
        receipt = _read_json(
            root
            / "provider_market_data_imbalance_live_dryrun_terminal_receipt.json",
            "runtime terminal receipt",
        )
        summary_frame = _read_csv(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_launcher_summary.csv",
            "runtime-launcher summary",
        )
        summary = _single_row(summary_frame, "runtime-launcher summary")
        saved_config = _read_json(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_launcher_config.json",
            "runtime-launcher config",
        )
        simulation_only = _surfaces_simulation_only(
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
        if not preflight_current or not handoff_current:
            return _verification(
                root=root,
                preflight_root=preflight_root,
                handoff_root=handoff_root,
                manifest_current=bool(integrity.passed),
                preflight_current=preflight_current,
                handoff_current=handoff_current,
                simulation_only=simulation_only,
                non_authorizing=non_authorizing,
                error="runtime_launcher_source_not_current",
            )

        checks_frame = _read_csv(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_launcher_checks.csv",
            "runtime-launcher checks",
        )
        telemetry_frame = _read_csv(
            root
            / "provider_market_data_imbalance_live_dryrun_market_data_telemetry.csv",
            "runtime-launcher telemetry",
        )
        runbook = (
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_launcher_runbook.md"
        ).read_text(encoding="utf-8")
        preflight_manifest = _read_json(
            preflight_manifest_path,
            "runtime-preflight manifest",
        )
        if _text(preflight_manifest.get("run_type")) != RUNTIME_PREFLIGHT_RUN_TYPE:
            raise ValueError("runtime-launcher source has the wrong run type")
        preflight_receipt = _read_json(
            preflight_root / PREFLIGHT_RECEIPT_FILE,
            "runtime-preflight receipt",
        )
        handoff_plan = _read_json(
            handoff_root / HANDOFF_PLAN_FILE,
            "live-dry-run handoff plan",
        )
        settings = dict(
            _mapping(_mapping(manifest.get("parameters")).get("config"))
        )
        config = ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig(
            **settings
        )
        _validate_launcher_config(config)
        recursive_dependencies = _recursive_dependencies(
            preflight_manifest_path,
            {
                preflight_root,
                preflight_manifest_path,
                handoff_root,
                handoff_manifest_path,
            },
        )
        identity = _mapping(handoff_plan.get("identity"))
        _validate_source_identity(
            identity,
            _mapping(preflight_receipt.get("identity")),
        )
        simulation = simulate_bounded_market_data_session(
            config=_simulation_config(config),
            provider=_text(identity.get("provider")),
            adapter=_text(identity.get("adapter")),
            transport=_text(identity.get("transport")),
            market=_text(identity.get("market")),
            exchange=_text(identity.get("exchange")),
            session_id=_text(identity.get("session_id")),
            trading_date=_text(identity.get("trading_date")),
            timezone_name=_text(identity.get("timezone")),
            open_local=_text(identity.get("open_local")),
            close_local=_text(identity.get("close_local")),
            kill_switch_enabled=_explicit_true(
                _mapping(handoff_plan.get("kill_switch")),
                "enabled",
            ),
        )
        expected_checks = _checks(
            preflight_verification=preflight_verification,
            handoff_verification=handoff_verification,
            preflight_receipt=preflight_receipt,
            handoff_plan=handoff_plan,
            simulation=simulation,
            recursive_dependency_count=len(recursive_dependencies),
            config=config,
        )
        expected_core = _receipt_core(
            preflight_root=preflight_root,
            preflight_manifest_path=preflight_manifest_path,
            preflight_receipt=preflight_receipt,
            handoff_root=handoff_root,
            handoff_manifest_path=handoff_manifest_path,
            handoff_plan=handoff_plan,
            simulation=simulation,
            config=config,
            recorded_at_utc=_text(receipt.get("recorded_at_utc")),
        )
        receipt_sha256 = _canonical_sha256(expected_core)
        expected_receipt = {
            **expected_core,
            "terminal_receipt_id": f"provider-runtime-terminal-{receipt_sha256[:24]}",
            "terminal_receipt_sha256": receipt_sha256,
        }
        expected_summary = _summary(
            receipt=expected_receipt,
            simulation=simulation,
            checks=expected_checks,
            recursive_dependency_count=len(recursive_dependencies),
        )
        expected_config = _config_payload(
            config=config,
            receipt=expected_receipt,
            preflight_root=preflight_root,
            handoff_root=handoff_root,
            handoff_plan=handoff_plan,
            simulation=simulation,
        )
        expected_extra = _manifest_extra(expected_receipt, simulation)
        artifacts_consistent = bool(
            receipt == expected_receipt
            and saved_config == expected_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(telemetry_frame, simulation.telemetry)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and runbook == _runbook_markdown(expected_summary.iloc[0])
            and dict(_mapping(manifest.get("extra"))) == expected_extra
            and _manifest_inputs_match(
                inputs,
                preflight_root=preflight_root,
                preflight_manifest_path=preflight_manifest_path,
                handoff_root=handoff_root,
                handoff_manifest_path=handoff_manifest_path,
                recursive_dependencies=recursive_dependencies,
            )
        )
        verified = bool(
            integrity.passed
            and preflight_current
            and handoff_current
            and artifacts_consistent
            and simulation_only
            and non_authorizing
        )
        checks_passed = bool(expected_checks["passed"].map(_bool).all())
        completed = bool(
            verified
            and checks_passed
            and simulation.completed
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
            and simulation.halted
            and _explicit_true(summary, "halted")
            and _explicit_true(receipt, "halted")
            and _explicit_true(saved_config, "halted")
            and _explicit_true(_mapping(manifest.get("extra")), "halted")
        )
        error = (
            integrity.error
            or (
                "runtime_launcher_artifacts_disagree_with_sources"
                if not artifacts_consistent
                else ""
            )
            or (
                "runtime_launcher_simulation_contract_invalid"
                if not simulation_only
                else ""
            )
            or (
                "runtime_launcher_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
        )
        return ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherVerification(
            verified=verified,
            completed=completed,
            halted=halted,
            manifest_current=bool(integrity.passed),
            preflight_current=preflight_current,
            handoff_current=handoff_current,
            artifacts_consistent=artifacts_consistent,
            simulation_only=simulation_only,
            non_authorizing=non_authorizing,
            output_dir=root,
            preflight_dir=preflight_root,
            handoff_dir=handoff_root,
            error=error,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        MarketDataObservationSimulationError,
    ) as exc:
        return _verification(
            root=root,
            preflight_root=preflight_root,
            handoff_root=handoff_root,
            manifest_current=bool(integrity.passed),
            preflight_current=False,
            handoff_current=False,
            simulation_only=False,
            non_authorizing=False,
            error=f"runtime_launcher_unreadable:{exc}",
        )


def _checks(
    *,
    preflight_verification: Any,
    handoff_verification: Any,
    preflight_receipt: Mapping[str, Any],
    handoff_plan: Mapping[str, Any],
    simulation: BoundedMarketDataSimulationResult,
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
) -> pd.DataFrame:
    source_safety = _mapping(preflight_receipt.get("safety"))
    handoff_kill_switch = _mapping(handoff_plan.get("kill_switch"))
    checks = [
        _check(
            "preflight_verified",
            "source",
            preflight_verification.verified,
            "is",
            True,
            preflight_verification.verified,
            "runtime preflight is not verified",
        ),
        _check(
            "preflight_ready",
            "source",
            preflight_verification.ready,
            "is",
            True,
            preflight_verification.ready,
            "runtime preflight is not ready",
        ),
        _check(
            "preflight_credential_safe",
            "source",
            preflight_verification.credential_safe,
            "is",
            True,
            preflight_verification.credential_safe,
            "runtime preflight credential contract is unsafe",
        ),
        _check(
            "preflight_non_authorizing",
            "source",
            preflight_verification.non_authorizing,
            "is",
            True,
            preflight_verification.non_authorizing,
            "runtime preflight is authorizing",
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
            "handoff_non_authorizing",
            "source",
            handoff_verification.non_authorizing,
            "is",
            True,
            handoff_verification.non_authorizing,
            "live-dry-run handoff is authorizing",
        ),
        _check(
            "source_preflight_did_not_launch_strategy",
            "source",
            source_safety.get("strategy_execution_enabled", True),
            "is",
            False,
            _explicit_false(source_safety, "strategy_execution_enabled"),
            "source preflight already launched a strategy",
        ),
        _check(
            "kill_switch_armed",
            "safety",
            handoff_kill_switch.get("enabled", False),
            "is",
            True,
            _explicit_true(handoff_kill_switch, "enabled"),
            "handoff kill switch is not armed",
        ),
        _check(
            "simulation_mode_only",
            "safety",
            "deterministic_simulation",
            "==",
            "deterministic_simulation",
            True,
            "launcher mode is not deterministic simulation",
        ),
        _check(
            "dependency_limit",
            "integrity",
            recursive_dependency_count,
            "<=",
            config.max_dependency_count,
            recursive_dependency_count <= config.max_dependency_count,
            "preflight dependency graph exceeds launcher limit",
        ),
        _check(
            "telemetry_attempted",
            "telemetry",
            simulation.attempted_event_count,
            ">",
            0,
            simulation.attempted_event_count > 0,
            "runtime emitted no telemetry",
        ),
        _check(
            "terminal_state_exclusive",
            "runtime",
            int(simulation.completed) + int(simulation.halted),
            "==",
            1,
            simulation.completed != simulation.halted,
            "runtime terminal state is ambiguous",
        ),
        _check(
            "requested_events_completed",
            "runtime",
            simulation.accepted_event_count,
            "==",
            simulation.requested_event_count,
            simulation.completed
            and simulation.accepted_event_count
            == simulation.requested_event_count,
            simulation.halt_reason
            or "runtime did not complete the requested event bound",
        ),
        _check(
            "runtime_not_halted",
            "runtime",
            simulation.halted,
            "is",
            False,
            not simulation.halted,
            simulation.halt_reason or "runtime halted",
        ),
        _check(
            "provider_network_not_called",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher called a provider network",
        ),
        _check(
            "provider_backend_not_loaded",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher loaded a provider backend",
        ),
        _check(
            "credential_environment_not_read",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher read credential environment variables",
        ),
        _check(
            "strategy_execution_disabled",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher enabled strategy execution",
        ),
        _check(
            "order_generation_disabled",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher enabled order generation",
        ),
        _check(
            "broker_order_api_not_imported",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher imported a broker order API",
        ),
        _check(
            "broker_order_api_not_called",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher called a broker order API",
        ),
        _check(
            "submission_disabled",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher enabled submission",
        ),
        _check(
            "non_authorizing",
            "safety",
            False,
            "is",
            False,
            True,
            "launcher authorized submission",
        ),
    ]
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _receipt_core(
    *,
    preflight_root: Path,
    preflight_manifest_path: Path,
    preflight_receipt: Mapping[str, Any],
    handoff_root: Path,
    handoff_manifest_path: Path,
    handoff_plan: Mapping[str, Any],
    simulation: BoundedMarketDataSimulationResult,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
    recorded_at_utc: str,
) -> dict[str, Any]:
    identity = _mapping(handoff_plan.get("identity"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "bounded_simulated_market_data_observation",
        "recorded_at_utc": _utc_text(recorded_at_utc),
        "launcher_mode": "deterministic_simulation",
        "completed": simulation.completed,
        "halted": simulation.halted,
        "halt_reason": simulation.halt_reason,
        "source": {
            "preflight_id": _text(preflight_receipt.get("preflight_id")),
            "preflight_receipt_sha256": _text(
                preflight_receipt.get("receipt_sha256")
            ).lower(),
            "handoff_id": _text(handoff_plan.get("handoff_id")),
            "handoff_plan_sha256": _text(handoff_plan.get("plan_sha256")).lower(),
            "source_connectivity_observed": _explicit_true(
                _mapping(preflight_receipt.get("connectivity")),
                "probe_called",
            ),
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
        "session": {
            field: _text(identity.get(field))
            for field in (
                "trading_date",
                "timezone",
                "open_local",
                "close_local",
            )
        },
        "simulation": _jsonable(asdict(_simulation_config(config))),
        "outcome": {
            "requested_event_count": simulation.requested_event_count,
            "attempted_event_count": simulation.attempted_event_count,
            "accepted_event_count": simulation.accepted_event_count,
            "session_open_ts_ns": simulation.session_open_ts_ns,
            "session_close_ts_ns": simulation.session_close_ts_ns,
            "first_attempt_ts_ns": simulation.first_attempt_ts_ns,
            "last_attempt_ts_ns": simulation.last_attempt_ts_ns,
        },
        "telemetry": {
            "row_count": len(simulation.telemetry),
            "records_sha256": _canonical_sha256(
                simulation.telemetry.to_dict(orient="records")
            ),
        },
        "proof_contract": {
            "preflight_path": str(preflight_root),
            "preflight_manifest_path": str(preflight_manifest_path),
            "preflight_manifest_sha256": file_sha256(preflight_manifest_path),
            "handoff_path": str(handoff_root),
            "handoff_manifest_path": str(handoff_manifest_path),
            "handoff_manifest_sha256": file_sha256(handoff_manifest_path),
        },
        "safety": _safety_payload(),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    simulation: BoundedMarketDataSimulationResult,
    checks: pd.DataFrame,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    identity = _mapping(receipt.get("identity"))
    return pd.DataFrame(
        [
            {
                "passed": simulation.completed and failed_checks == 0,
                "ready": simulation.completed and failed_checks == 0,
                "completed": simulation.completed,
                "halted": simulation.halted,
                "status": (
                    "completed_market_data_observation"
                    if simulation.completed
                    else "halted_market_data_observation"
                ),
                "halt_reason": simulation.halt_reason,
                "failed_checks": failed_checks,
                "terminal_receipt_id": _text(receipt.get("terminal_receipt_id")),
                "terminal_receipt_sha256": _text(
                    receipt.get("terminal_receipt_sha256")
                ),
                "preflight_id": _text(_mapping(receipt.get("source")).get("preflight_id")),
                "handoff_id": _text(_mapping(receipt.get("source")).get("handoff_id")),
                "provider": _text(identity.get("provider")),
                "adapter": _text(identity.get("adapter")),
                "transport": _text(identity.get("transport")),
                "market": _text(identity.get("market")),
                "exchange": _text(identity.get("exchange")),
                "session_id": _text(identity.get("session_id")),
                "requested_event_count": simulation.requested_event_count,
                "attempted_event_count": simulation.attempted_event_count,
                "accepted_event_count": simulation.accepted_event_count,
                "telemetry_records_sha256": _text(
                    _mapping(receipt.get("telemetry")).get("records_sha256")
                ),
                "recursive_dependency_count": recursive_dependency_count,
                **_safety_payload(),
                "next_gate": "bounded_shadow_strategy_runtime",
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
    receipt: Mapping[str, Any],
    preflight_root: Path,
    handoff_root: Path,
    handoff_plan: Mapping[str, Any],
    simulation: BoundedMarketDataSimulationResult,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "launcher_mode": "deterministic_simulation",
        "preflight_dir": str(preflight_root),
        "handoff_dir": str(handoff_root),
        "handoff_identity": _jsonable(_mapping(handoff_plan.get("identity"))),
        "terminal_receipt_id": _text(receipt.get("terminal_receipt_id")),
        "terminal_receipt_sha256": _text(
            receipt.get("terminal_receipt_sha256")
        ),
        "completed": simulation.completed,
        "halted": simulation.halted,
        "halt_reason": simulation.halt_reason,
        "outcome": _jsonable(_mapping(receipt.get("outcome"))),
        **_safety_payload(),
    }


def _manifest_extra(
    receipt: Mapping[str, Any],
    simulation: BoundedMarketDataSimulationResult,
) -> dict[str, Any]:
    identity = _mapping(receipt.get("identity"))
    return {
        "passed": simulation.completed,
        "ready": simulation.completed,
        "completed": simulation.completed,
        "halted": simulation.halted,
        "halt_reason": simulation.halt_reason,
        "terminal_receipt_id": _text(receipt.get("terminal_receipt_id")),
        "terminal_receipt_sha256": _text(
            receipt.get("terminal_receipt_sha256")
        ),
        "provider": _text(identity.get("provider")),
        "market": _text(identity.get("market")),
        "target_mode": "live_dryrun",
        "requested_event_count": simulation.requested_event_count,
        "accepted_event_count": simulation.accepted_event_count,
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
            "# Provider Live-Dry-Run Simulated Market-Data Runtime",
            "",
            f"- Status: `{summary['status']}`",
            f"- Terminal receipt: `{summary['terminal_receipt_id']}`",
            f"- Provider identity: `{summary['provider']}` (source proof only)",
            f"- Session: `{summary['session_id']}`",
            f"- Requested events: `{summary['requested_event_count']}`",
            f"- Accepted events: `{summary['accepted_event_count']}`",
            f"- Halt reason: `{summary['halt_reason']}`",
            "- Runtime mode: deterministic simulation",
            "- Provider network called: no",
            "- Provider backend loaded: no",
            "- Credential environment read: no",
            "- Strategy execution enabled: no",
            "- Order generation enabled: no",
            "- Broker order API imported or called: no",
            "- Submission enabled: no",
            "",
            (
                "A separate bounded shadow-strategy runtime is required. "
                "This terminal receipt does not authorize or submit orders."
            ),
            "",
        ]
    )


def _surfaces_simulation_only(
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
        and _text(receipt.get("launcher_mode")) == "deterministic_simulation"
        and _text(config.get("launcher_mode")) == "deterministic_simulation"
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


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    preflight_root: Path,
    preflight_manifest_path: Path,
    handoff_root: Path,
    handoff_manifest_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    expected_keys = {
        "runtime_preflight",
        "runtime_preflight_manifest",
        "live_dryrun_handoff",
        "live_dryrun_handoff_manifest",
    }
    if recursive_dependencies:
        expected_keys.add("preflight_recursive_dependencies")
    if set(inputs) != expected_keys:
        return False
    expected_paths = {
        preflight_root,
        preflight_manifest_path,
        handoff_root,
        handoff_manifest_path,
        *recursive_dependencies,
    }
    return set(_fingerprint_paths(inputs)) == {path.resolve() for path in expected_paths}


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
    preflight_root: Path,
    handoff_root: Path,
) -> None:
    for source in (preflight_root, handoff_root):
        if output_dir == source or _is_relative_to(output_dir, source):
            raise ValueError("runtime launcher output must not overlap a source")
        if _is_relative_to(source, output_dir):
            raise ValueError("runtime launcher output must not contain a source")


def _validate_launcher_config(
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
) -> None:
    if (
        isinstance(config.max_dependency_count, bool)
        or not isinstance(config.max_dependency_count, int)
        or config.max_dependency_count <= 0
    ):
        raise ValueError("max_dependency_count must be a positive integer")
    # The simulator owns validation of the remaining fields before output exists.
    _simulation_config(config)


def _simulation_config(
    config: ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherConfig,
) -> BoundedMarketDataSimulationConfig:
    return BoundedMarketDataSimulationConfig(
        event_count=config.event_count,
        interval_ms=config.interval_ms,
        start_offset_seconds=config.start_offset_seconds,
        symbol=config.symbol,
        base_mid_price=config.base_mid_price,
        spread=config.spread,
        quantity=config.quantity,
        price_step=config.price_step,
        fault_mode=config.fault_mode,
        fault_at_event=config.fault_at_event,
    )


def _validate_source_identity(
    handoff_identity: Mapping[str, Any],
    preflight_identity: Mapping[str, Any],
) -> None:
    mismatched = [
        field
        for field in PREFLIGHT_IDENTITY_FIELDS
        if _identity(handoff_identity.get(field))
        != _identity(preflight_identity.get(field))
    ]
    if mismatched:
        raise ValueError(
            "runtime launcher source identity differs: " + ", ".join(mismatched)
        )


def _verification(
    *,
    root: Path,
    preflight_root: Path | None,
    handoff_root: Path | None,
    manifest_current: bool,
    preflight_current: bool,
    handoff_current: bool,
    simulation_only: bool,
    non_authorizing: bool,
    error: str,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherVerification:
    return ProviderMarketDataImbalanceLiveDryrunRuntimeLauncherVerification(
        verified=False,
        completed=False,
        halted=False,
        manifest_current=manifest_current,
        preflight_current=preflight_current,
        handoff_current=handoff_current,
        artifacts_consistent=False,
        simulation_only=simulation_only,
        non_authorizing=non_authorizing,
        output_dir=root,
        preflight_dir=preflight_root,
        handoff_dir=handoff_root,
        error=error,
    )


def _fingerprint_paths(value: Any) -> list[Path]:
    paths: list[Path] = []
    if isinstance(value, Mapping):
        if value.get("kind") in {"file", "directory"} and value.get("path"):
            paths.append(Path(str(value["path"])).resolve())
        else:
            for item in value.values():
                paths.extend(_fingerprint_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_fingerprint_paths(item))
    return paths


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


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


def _dataframe_records_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> bool:
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


def _explicit_true(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return bool(math.isfinite(float(raw)) and float(raw) == 1.0)
    return _text(raw).lower() in {"1", "true", "yes"}


def _explicit_false(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return not bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return bool(math.isfinite(float(raw)) and float(raw) == 0.0)
    return _text(raw).lower() in {"0", "false", "no", "off"}


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _identity(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
