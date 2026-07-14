from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from provider_connectivity import (
    ProviderConnectivityBackend,
    ProviderConnectivityError,
    execute_provider_connectivity_probe,
    load_provider_connectivity_backend,
    provider_connectivity_backend_env_var,
    resolve_provider_connectivity_backend_entrypoint,
    validate_connectivity_endpoint,
)
from reports.manifest import (
    MANIFEST_NAME,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.market_data_source import PROVIDER_SPECS
from reports.provider_market_data_imbalance_live_dryrun_handoff import (
    RUN_TYPE as LIVE_DRYRUN_HANDOFF_RUN_TYPE,
    verify_provider_market_data_imbalance_live_dryrun_handoff,
)


RUN_TYPE = "provider_market_data_imbalance_live_dryrun_runtime_preflight"
CONTRACT_VERSION = (
    "provider_market_data_imbalance_live_dryrun_runtime_preflight/v1"
)
PROFILE_CONTRACT_VERSION = "provider_live_dryrun_runtime_preflight_profile/v1"
HANDOFF_PLAN_FILE = (
    "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
)
PREFLIGHT_ARTIFACTS = (
    "provider_market_data_imbalance_live_dryrun_runtime_preflight_checks.csv",
    "provider_market_data_imbalance_live_dryrun_runtime_preflight_summary.csv",
    "provider_market_data_imbalance_live_dryrun_launch_receipt.json",
    "provider_market_data_imbalance_live_dryrun_runtime_preflight_config.json",
    "provider_market_data_imbalance_live_dryrun_runtime_preflight_runbook.md",
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
PROFILE_KEYS = {
    "capability",
    "contract_version",
    "credential_env_vars",
    "endpoint",
    "handoff_id",
    "identity",
    "plan_sha256",
    "safety",
}
IDENTITY_KEYS = {
    "adapter",
    "exchange",
    "market",
    "provider",
    "session_id",
    "transport",
}
SAFETY_KEYS = {
    "authorizes_submission",
    "broker_order_api_enabled",
    "connectivity_only",
    "credential_values_stored",
    "dry_run_only",
    "submission_enabled",
}
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{0,64}$")


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig:
    max_dependency_count: int = 8192
    max_connectivity_latency_ms: float = 5000.0


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunRuntimePreflightReport:
    checks: pd.DataFrame
    summary: pd.DataFrame
    receipt: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("ready", False))
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunRuntimePreflightVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    handoff_current: bool
    runtime_profile_current: bool
    artifacts_consistent: bool
    credential_safe: bool
    non_authorizing: bool
    output_dir: Path
    handoff_dir: Path | None
    runtime_profile_path: Path | None
    error: str = ""


def write_provider_market_data_imbalance_live_dryrun_runtime_preflight(
    handoff_dir: str | Path,
    runtime_profile_path: str | Path,
    output_dir: str | Path,
    *,
    config: (
        ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig | None
    ) = None,
    backend: ProviderConnectivityBackend | None = None,
    backend_entrypoint: str = "",
    environ: Mapping[str, str] | None = None,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimePreflightReport:
    config = config or ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig()
    _validate_config(config)
    handoff_root = Path(handoff_dir).resolve()
    handoff_manifest_path = handoff_root / MANIFEST_NAME
    profile_path = Path(runtime_profile_path).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"runtime preflight output already exists: {out}")

    handoff_verification = (
        verify_provider_market_data_imbalance_live_dryrun_handoff(handoff_root)
    )
    if not (
        handoff_verification.verified
        and handoff_verification.ready
        and handoff_verification.non_authorizing
    ):
        raise ValueError(
            "runtime preflight requires a verified ready non-authorizing handoff: "
            + (handoff_verification.error or "handoff_not_ready")
        )
    handoff_manifest = _read_json(handoff_manifest_path, "handoff manifest")
    if _text(handoff_manifest.get("run_type")) != LIVE_DRYRUN_HANDOFF_RUN_TYPE:
        raise ValueError("runtime preflight source is not a live-dry-run handoff")
    handoff_plan = _read_json(handoff_root / HANDOFF_PLAN_FILE, "handoff plan")
    profile = _read_json(profile_path, "runtime profile")
    _reject_output_collision(out, handoff_root, profile_path)
    recursive_dependencies = _recursive_dependencies(
        handoff_manifest_path,
        {handoff_root, handoff_manifest_path, profile_path},
    )
    static_checks = _static_checks(
        handoff_verification=handoff_verification,
        handoff_plan=handoff_plan,
        profile=profile,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    failed_static = static_checks.loc[
        ~static_checks["passed"].map(_bool),
        "check",
    ].astype(str).tolist()
    if failed_static:
        raise ValueError(
            "runtime preflight profile contract failed: "
            + ", ".join(failed_static)
        )

    environment = dict(os.environ if environ is None else environ)
    identity = _mapping(profile.get("identity"))
    env_vars = tuple(_string_list(profile.get("credential_env_vars")))
    env_presence = {
        name: bool(str(environment.get(name, "")).strip())
        for name in env_vars
    }
    resolved_entrypoint = resolve_provider_connectivity_backend_entrypoint(
        _text(identity.get("provider")),
        backend_entrypoint,
        environ=environment,
    )
    loaded_backend = backend
    backend_error = ""
    if loaded_backend is not None and not resolved_entrypoint:
        resolved_entrypoint = "injected_backend:connectivity_probe"
    if (
        loaded_backend is None
        and resolved_entrypoint
        and all(env_presence.values())
    ):
        try:
            loaded_backend = load_provider_connectivity_backend(
                resolved_entrypoint
            )
        except ProviderConnectivityError:
            backend_error = "backend_load_error"

    observation = _blocked_observation(
        provider=_text(identity.get("provider")),
        backend_entrypoint=resolved_entrypoint,
        env_presence=env_presence,
        error_code=(
            backend_error
            or ("credentials_missing" if not all(env_presence.values()) else "")
            or ("backend_not_configured" if loaded_backend is None else "")
        ),
    )
    if loaded_backend is not None and all(env_presence.values()):
        try:
            probe = execute_provider_connectivity_probe(
                provider=_text(identity.get("provider")),
                adapter=_text(identity.get("adapter")),
                transport=_text(identity.get("transport")),
                endpoint=_text(profile.get("endpoint")),
                market=_text(identity.get("market")),
                exchange=_text(identity.get("exchange")),
                session_id=_text(identity.get("session_id")),
                handoff_id=_text(profile.get("handoff_id")),
                plan_sha256=_text(profile.get("plan_sha256")),
                credential_env_vars=env_vars,
                backend=loaded_backend,
                backend_entrypoint=resolved_entrypoint,
                environ=environment,
            )
            observation = _probe_observation(probe)
        except ProviderConnectivityError:
            observation = _blocked_observation(
                provider=_text(identity.get("provider")),
                backend_entrypoint=resolved_entrypoint,
                env_presence=env_presence,
                error_code="probe_contract_error",
            )

    runtime_checks = _runtime_checks(
        observation=observation,
        env_vars=env_vars,
        config=config,
    )
    checks = pd.concat([static_checks, runtime_checks], ignore_index=True)
    ready = bool(checks["passed"].map(_bool).all())
    observed_at_utc = datetime.now(timezone.utc).isoformat()
    receipt_core = _receipt_core(
        handoff_plan=handoff_plan,
        profile=profile,
        profile_path=profile_path,
        handoff_root=handoff_root,
        handoff_manifest_path=handoff_manifest_path,
        observation=observation,
        observed_at_utc=observed_at_utc,
        ready=ready,
    )
    receipt_sha256 = _canonical_sha256(receipt_core)
    receipt = {
        **receipt_core,
        "preflight_id": f"provider-runtime-preflight-{receipt_sha256[:24]}",
        "receipt_sha256": receipt_sha256,
    }
    summary = _summary(
        receipt=receipt,
        profile=profile,
        observation=observation,
        checks=checks,
        recursive_dependency_count=len(recursive_dependencies),
    )
    config_payload = _config_payload(
        config=config,
        receipt=receipt,
        profile=profile,
        profile_path=profile_path,
        handoff_root=handoff_root,
        observation=observation,
    )

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_preflight_checks.csv",
        index=False,
    )
    summary.to_csv(
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_preflight_summary.csv",
        index=False,
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_launch_receipt.json"
    ).write_text(
        json.dumps(_jsonable(receipt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_preflight_config.json"
    ).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out
        / "provider_market_data_imbalance_live_dryrun_runtime_preflight_runbook.md"
    ).write_text(
        _runbook_markdown(summary.iloc[0]),
        encoding="utf-8",
    )
    _assert_credential_values_absent(out, env_vars, environment)

    final_handoff = verify_provider_market_data_imbalance_live_dryrun_handoff(
        handoff_root
    )
    if (
        not final_handoff.verified
        or file_sha256(handoff_manifest_path)
        != receipt["proof_contract"]["handoff_manifest_sha256"]
        or file_sha256(profile_path)
        != receipt["proof_contract"]["runtime_profile_sha256"]
    ):
        raise RuntimeError("handoff or runtime profile changed during preflight")
    manifest_inputs: dict[str, Any] = {
        "live_dryrun_handoff": handoff_root,
        "live_dryrun_handoff_manifest": handoff_manifest_path,
        "runtime_profile": profile_path,
    }
    if recursive_dependencies:
        manifest_inputs["handoff_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(receipt, profile, observation),
    )
    return ProviderMarketDataImbalanceLiveDryrunRuntimePreflightReport(
        checks=checks,
        summary=summary,
        receipt=receipt,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_live_dryrun_runtime_preflight(
    preflight_dir: str | Path,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimePreflightVerification:
    candidate = Path(preflight_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=PREFLIGHT_ARTIFACTS,
        require_input_fingerprints=True,
    )
    handoff_root: Path | None = None
    profile_path: Path | None = None
    try:
        manifest = _read_json(manifest_path, "runtime-preflight manifest")
        checks_frame = _read_csv(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_preflight_checks.csv",
            "runtime-preflight checks",
        )
        summary_frame = _read_csv(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_preflight_summary.csv",
            "runtime-preflight summary",
        )
        summary = _single_row(summary_frame, "runtime-preflight summary")
        receipt = _read_json(
            root / "provider_market_data_imbalance_live_dryrun_launch_receipt.json",
            "launch receipt",
        )
        saved_config = _read_json(
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_preflight_config.json",
            "runtime-preflight config",
        )
        runbook = (
            root
            / "provider_market_data_imbalance_live_dryrun_runtime_preflight_runbook.md"
        ).read_text(encoding="utf-8")
        inputs = _mapping(manifest.get("inputs"))
        handoff_record = _mapping(inputs.get("live_dryrun_handoff"))
        profile_record = _mapping(inputs.get("runtime_profile"))
        if (
            handoff_record.get("kind") != "directory"
            or profile_record.get("kind") != "file"
            or not _text(handoff_record.get("path"))
            or not _text(profile_record.get("path"))
        ):
            raise ValueError("runtime-preflight input contract is invalid")
        handoff_root = Path(str(handoff_record["path"])).resolve()
        profile_path = Path(str(profile_record["path"])).resolve()
        handoff_manifest_path = handoff_root / MANIFEST_NAME
        handoff_verification = (
            verify_provider_market_data_imbalance_live_dryrun_handoff(
                handoff_root
            )
        )
        handoff_current = bool(
            handoff_verification.verified
            and handoff_verification.ready
            and handoff_verification.non_authorizing
        )
        profile_current = _input_file_current(profile_path, profile_record)
        credential_safe = _receipt_credential_safe(receipt)
        non_authorizing = _surfaces_non_authorizing(
            summary,
            receipt,
            saved_config,
            _mapping(manifest.get("extra")),
        )
        if not handoff_current or not profile_current:
            return _verification(
                root=root,
                handoff_root=handoff_root,
                profile_path=profile_path,
                manifest_current=bool(integrity.passed),
                handoff_current=handoff_current,
                profile_current=profile_current,
                credential_safe=credential_safe,
                non_authorizing=non_authorizing,
                error="runtime_preflight_source_not_current",
            )

        handoff_manifest = _read_json(
            handoff_manifest_path,
            "handoff manifest",
        )
        if _text(handoff_manifest.get("run_type")) != LIVE_DRYRUN_HANDOFF_RUN_TYPE:
            raise ValueError("runtime-preflight source has the wrong run type")
        handoff_plan = _read_json(
            handoff_root / HANDOFF_PLAN_FILE,
            "handoff plan",
        )
        profile = _read_json(profile_path, "runtime profile")
        settings = dict(
            _mapping(_mapping(manifest.get("parameters")).get("config"))
        )
        config = ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig(
            **settings
        )
        _validate_config(config)
        recursive_dependencies = _recursive_dependencies(
            handoff_manifest_path,
            {handoff_root, handoff_manifest_path, profile_path},
        )
        expected_static = _static_checks(
            handoff_verification=handoff_verification,
            handoff_plan=handoff_plan,
            profile=profile,
            recursive_dependency_count=len(recursive_dependencies),
            config=config,
        )
        observation = _receipt_observation(receipt)
        env_vars = tuple(_string_list(profile.get("credential_env_vars")))
        expected_runtime = _runtime_checks(
            observation=observation,
            env_vars=env_vars,
            config=config,
        )
        expected_checks = pd.concat(
            [expected_static, expected_runtime],
            ignore_index=True,
        )
        expected_ready = bool(expected_checks["passed"].map(_bool).all())
        expected_core = _receipt_core(
            handoff_plan=handoff_plan,
            profile=profile,
            profile_path=profile_path,
            handoff_root=handoff_root,
            handoff_manifest_path=handoff_manifest_path,
            observation=observation,
            observed_at_utc=_text(receipt.get("observed_at_utc")),
            ready=expected_ready,
        )
        receipt_sha256 = _canonical_sha256(expected_core)
        expected_receipt = {
            **expected_core,
            "preflight_id": f"provider-runtime-preflight-{receipt_sha256[:24]}",
            "receipt_sha256": receipt_sha256,
        }
        expected_summary = _summary(
            receipt=expected_receipt,
            profile=profile,
            observation=observation,
            checks=expected_checks,
            recursive_dependency_count=len(recursive_dependencies),
        )
        expected_config = _config_payload(
            config=config,
            receipt=expected_receipt,
            profile=profile,
            profile_path=profile_path,
            handoff_root=handoff_root,
            observation=observation,
        )
        expected_extra = _manifest_extra(
            expected_receipt,
            profile,
            observation,
        )
        artifacts_consistent = bool(
            receipt == expected_receipt
            and saved_config == expected_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and runbook == _runbook_markdown(expected_summary.iloc[0])
            and dict(_mapping(manifest.get("extra"))) == expected_extra
            and _manifest_inputs_match(
                inputs,
                handoff_root=handoff_root,
                handoff_manifest_path=handoff_manifest_path,
                profile_path=profile_path,
                recursive_dependencies=recursive_dependencies,
            )
        )
        ready_claim = bool(
            _bool(summary.get("ready", False))
            and _bool(receipt.get("ready_for_separate_runtime_launch", False))
            and _bool(saved_config.get("ready", False))
            and _bool(_mapping(manifest.get("extra")).get("ready", False))
        )
        verified = bool(
            integrity.passed
            and handoff_current
            and profile_current
            and artifacts_consistent
            and credential_safe
            and non_authorizing
        )
        ready = bool(verified and ready_claim)
        error = (
            integrity.error
            or (
                "runtime_preflight_artifacts_disagree_with_sources"
                if not artifacts_consistent
                else ""
            )
            or (
                "runtime_preflight_credential_contract_invalid"
                if not credential_safe
                else ""
            )
            or (
                "runtime_preflight_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
        )
        return ProviderMarketDataImbalanceLiveDryrunRuntimePreflightVerification(
            verified=verified,
            ready=ready,
            manifest_current=bool(integrity.passed),
            handoff_current=handoff_current,
            runtime_profile_current=profile_current,
            artifacts_consistent=artifacts_consistent,
            credential_safe=credential_safe,
            non_authorizing=non_authorizing,
            output_dir=root,
            handoff_dir=handoff_root,
            runtime_profile_path=profile_path,
            error=error,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _verification(
            root=root,
            handoff_root=handoff_root,
            profile_path=profile_path,
            manifest_current=bool(integrity.passed),
            handoff_current=False,
            profile_current=False,
            credential_safe=False,
            non_authorizing=False,
            error=f"runtime_preflight_unreadable:{exc}",
        )


def _static_checks(
    *,
    handoff_verification: Any,
    handoff_plan: Mapping[str, Any],
    profile: Mapping[str, Any],
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig,
) -> pd.DataFrame:
    profile_identity = _mapping(profile.get("identity"))
    handoff_identity = _mapping(handoff_plan.get("identity"))
    safety = _mapping(profile.get("safety"))
    env_vars = _string_list(profile.get("credential_env_vars"))
    provider = _identity(profile_identity.get("provider"))
    provider_spec = _mapping(PROVIDER_SPECS.get(provider))
    expected_env_vars = [
        str(value)
        for value in provider_spec.get("credential_env_vars", ())
    ]
    checks = [
        _check("handoff_verified", "handoff", handoff_verification.verified, "is", True, handoff_verification.verified, "handoff is not verified"),
        _check("handoff_ready", "handoff", handoff_verification.ready, "is", True, handoff_verification.ready, "handoff is not ready"),
        _check("handoff_non_authorizing", "handoff", handoff_verification.non_authorizing, "is", True, handoff_verification.non_authorizing, "handoff is authorizing"),
        _check("profile_contract_version", "profile", _text(profile.get("contract_version")), "==", PROFILE_CONTRACT_VERSION, _text(profile.get("contract_version")) == PROFILE_CONTRACT_VERSION, "runtime profile contract version is invalid"),
        _check("profile_root_schema_exact", "profile", sorted(profile), "==", sorted(PROFILE_KEYS), set(profile) == PROFILE_KEYS, "runtime profile root fields are invalid"),
        _check("profile_identity_schema_exact", "profile", sorted(profile_identity), "==", sorted(IDENTITY_KEYS), set(profile_identity) == IDENTITY_KEYS, "runtime profile identity fields are invalid"),
        _check("profile_safety_schema_exact", "profile", sorted(safety), "==", sorted(SAFETY_KEYS), set(safety) == SAFETY_KEYS, "runtime profile safety fields are invalid"),
        _check("profile_capability_market_data", "profile", _text(profile.get("capability")), "==", "market_data_connectivity", _text(profile.get("capability")) == "market_data_connectivity", "runtime profile must be market-data-connectivity only"),
        _check("profile_handoff_id_matches", "binding", _text(profile.get("handoff_id")), "==", _text(handoff_plan.get("handoff_id")), _text(profile.get("handoff_id")) == _text(handoff_plan.get("handoff_id")), "runtime profile handoff ID differs"),
        _check("profile_plan_sha256_matches", "binding", _text(profile.get("plan_sha256")).lower(), "==", _text(handoff_plan.get("plan_sha256")).lower(), _valid_sha256(profile.get("plan_sha256")) and _text(profile.get("plan_sha256")).lower() == _text(handoff_plan.get("plan_sha256")).lower(), "runtime profile plan SHA differs"),
        _check("provider_registered", "identity", provider, "in", sorted(PROVIDER_SPECS), bool(provider_spec), "runtime provider is not registered"),
        _check("provider_supports_live_ticks", "identity", provider_spec.get("capabilities", ()), "contains", "live_ticks", "live_ticks" in tuple(provider_spec.get("capabilities", ())), "runtime provider lacks live-tick capability"),
        _check("credential_env_vars_exact", "credentials", env_vars, "==", expected_env_vars, bool(expected_env_vars) and env_vars == expected_env_vars, "credential environment variable names differ from provider contract"),
        _check("credential_env_vars_are_names", "credentials", env_vars, "match", ENV_NAME_RE.pattern, bool(env_vars) and all(ENV_NAME_RE.fullmatch(value) for value in env_vars), "credential entries must be environment variable names"),
        _check("endpoint_secure_and_credential_free", "connectivity", _text(profile.get("endpoint")), "safe_for", _text(profile_identity.get("transport")), not validate_connectivity_endpoint(_text(profile.get("endpoint")), _text(profile_identity.get("transport"))), validate_connectivity_endpoint(_text(profile.get("endpoint")), _text(profile_identity.get("transport"))) or "runtime endpoint is unsafe"),
        _check("profile_connectivity_only", "safety", safety.get("connectivity_only", False), "is", True, _explicit_true(safety, "connectivity_only"), "profile must be connectivity-only"),
        _check("profile_dry_run_only", "safety", safety.get("dry_run_only", False), "is", True, _explicit_true(safety, "dry_run_only"), "profile must be dry-run only"),
        _check("profile_submission_disabled", "safety", safety.get("submission_enabled", True), "is", False, _explicit_false(safety, "submission_enabled"), "profile must disable submission"),
        _check("profile_order_api_disabled", "safety", safety.get("broker_order_api_enabled", True), "is", False, _explicit_false(safety, "broker_order_api_enabled"), "profile must disable broker order APIs"),
        _check("profile_non_authorizing", "safety", safety.get("authorizes_submission", True), "is", False, _explicit_false(safety, "authorizes_submission"), "profile must remain non-authorizing"),
        _check("profile_credential_values_not_stored", "safety", safety.get("credential_values_stored", True), "is", False, _explicit_false(safety, "credential_values_stored"), "profile must not store credential values"),
        _check("recursive_dependency_limit", "integrity", recursive_dependency_count, "<=", config.max_dependency_count, recursive_dependency_count <= config.max_dependency_count, "handoff dependency graph exceeds preflight limit"),
    ]
    for field in sorted(IDENTITY_KEYS):
        actual = _identity(profile_identity.get(field))
        expected = _identity(handoff_identity.get(field))
        checks.append(
            _check(
                f"profile_{field}_matches_handoff",
                "identity",
                actual,
                "==",
                expected,
                bool(actual) and actual == expected,
                f"runtime profile {field} differs from handoff",
            )
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _runtime_checks(
    *,
    observation: Mapping[str, Any],
    env_vars: tuple[str, ...],
    config: ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig,
) -> pd.DataFrame:
    presence = _mapping(observation.get("credential_env_presence"))
    latency = _number(observation.get("latency_ms"))
    checks = [
        _check("credential_env_vars_present_in_runtime", "credentials", sum(_explicit_true(presence, name) for name in env_vars), "==", len(env_vars), bool(env_vars) and all(_explicit_true(presence, name) for name in env_vars), "required credential environment variables are missing"),
        _check("connectivity_backend_configured", "connectivity", _text(observation.get("backend_entrypoint")), "nonempty", True, bool(_text(observation.get("backend_entrypoint"))), "connectivity backend is not configured"),
        _check("connectivity_probe_called", "connectivity", observation.get("probe_called", False), "is", True, _explicit_true(observation, "probe_called"), "connectivity probe was not called"),
        _check("provider_connected", "connectivity", observation.get("connected", False), "is", True, _explicit_true(observation, "connected"), "provider connectivity failed"),
        _check("provider_authenticated", "connectivity", observation.get("authenticated", False), "is", True, _explicit_true(observation, "authenticated"), "provider authentication failed"),
        _check("market_data_readable", "connectivity", observation.get("market_data_readable", False), "is", True, _explicit_true(observation, "market_data_readable"), "market-data read probe failed"),
        _check("connectivity_latency_bounded", "connectivity", latency, "<=", config.max_connectivity_latency_ms, _explicit_true(observation, "probe_called") and 0 <= latency <= config.max_connectivity_latency_ms, "connectivity latency exceeds limit"),
        _check("connectivity_error_clear", "connectivity", _text(observation.get("error_code")), "==", "", not _text(observation.get("error_code")), "connectivity probe returned an error code"),
    ]
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _probe_observation(probe: Any) -> dict[str, Any]:
    return {
        "backend_entrypoint": _text(probe.backend_entrypoint),
        "backend_env_var": provider_connectivity_backend_env_var(
            probe.request.provider
        ),
        "credential_env_presence": dict(probe.request.credential_env_presence),
        "probe_called": bool(probe.probe_called),
        "connected": bool(probe.outcome.connected),
        "authenticated": bool(probe.outcome.authenticated),
        "market_data_readable": bool(probe.outcome.market_data_readable),
        "protocol": _safe_code(probe.outcome.protocol),
        "latency_ms": float(probe.latency_ms),
        "error_code": _safe_code(probe.outcome.error_code),
    }


def _blocked_observation(
    *,
    provider: str,
    backend_entrypoint: str,
    env_presence: Mapping[str, bool],
    error_code: str,
) -> dict[str, Any]:
    return {
        "backend_entrypoint": _text(backend_entrypoint),
        "backend_env_var": provider_connectivity_backend_env_var(provider),
        "credential_env_presence": dict(env_presence),
        "probe_called": False,
        "connected": False,
        "authenticated": False,
        "market_data_readable": False,
        "protocol": "",
        "latency_ms": 0.0,
        "error_code": _safe_code(error_code),
    }


def _receipt_observation(receipt: Mapping[str, Any]) -> dict[str, Any]:
    connectivity = _mapping(receipt.get("connectivity"))
    presence = _mapping(receipt.get("credentials"))
    env_presence = _mapping(presence.get("env_presence"))
    return {
        "backend_entrypoint": _text(connectivity.get("backend_entrypoint")),
        "backend_env_var": _text(connectivity.get("backend_env_var")),
        "credential_env_presence": {
            _text(key): _bool(value)
            for key, value in env_presence.items()
        },
        "probe_called": _explicit_true(connectivity, "probe_called"),
        "connected": _explicit_true(connectivity, "connected"),
        "authenticated": _explicit_true(connectivity, "authenticated"),
        "market_data_readable": _explicit_true(connectivity, "market_data_readable"),
        "protocol": _safe_code(connectivity.get("protocol")),
        "latency_ms": _number(connectivity.get("latency_ms")),
        "error_code": _safe_code(connectivity.get("error_code")),
    }


def _receipt_core(
    *,
    handoff_plan: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_path: Path,
    handoff_root: Path,
    handoff_manifest_path: Path,
    observation: Mapping[str, Any],
    observed_at_utc: str,
    ready: bool,
) -> dict[str, Any]:
    identity = _mapping(profile.get("identity"))
    env_vars = _string_list(profile.get("credential_env_vars"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "receipt_type": "provider_market_data_connectivity_preflight",
        "observed_at_utc": _utc_text(observed_at_utc),
        "ready_for_separate_runtime_launch": bool(ready),
        "handoff_id": _text(profile.get("handoff_id")),
        "plan_sha256": _text(profile.get("plan_sha256")).lower(),
        "identity": {
            field: _text(identity.get(field))
            for field in sorted(IDENTITY_KEYS)
        },
        "capability": "market_data_connectivity",
        "endpoint": _text(profile.get("endpoint")),
        "credentials": {
            "env_vars": env_vars,
            "env_presence": {
                name: _explicit_true(
                    _mapping(observation.get("credential_env_presence")),
                    name,
                )
                for name in env_vars
            },
            "values_stored": False,
        },
        "connectivity": {
            "backend_entrypoint": _text(observation.get("backend_entrypoint")),
            "backend_env_var": provider_connectivity_backend_env_var(
                _text(identity.get("provider"))
            ),
            "probe_called": _explicit_true(observation, "probe_called"),
            "connected": _explicit_true(observation, "connected"),
            "authenticated": _explicit_true(observation, "authenticated"),
            "market_data_readable": _explicit_true(
                observation,
                "market_data_readable",
            ),
            "protocol": _safe_code(observation.get("protocol")),
            "latency_ms": _number(observation.get("latency_ms")),
            "error_code": _safe_code(observation.get("error_code")),
        },
        "proof_contract": {
            "handoff_path": str(handoff_root),
            "handoff_manifest_path": str(handoff_manifest_path),
            "handoff_manifest_sha256": file_sha256(handoff_manifest_path),
            "runtime_profile_path": str(profile_path),
            "runtime_profile_sha256": file_sha256(profile_path),
        },
        "safety": {
            "strategy_execution_enabled": False,
            "launch_executed": False,
            "requires_separate_runtime_launcher": True,
            "release_approved": False,
            "dry_run_only": True,
            "connectivity_only": True,
            "market_data_connectivity_probe_called": _explicit_true(
                observation,
                "probe_called",
            ),
            "broker_order_api_enabled": False,
            "broker_order_api_called": False,
            "broker_api_called": False,
            "submission_enabled": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
        "source_handoff_safety": _mapping(handoff_plan.get("safety")),
    }


def _summary(
    *,
    receipt: Mapping[str, Any],
    profile: Mapping[str, Any],
    observation: Mapping[str, Any],
    checks: pd.DataFrame,
    recursive_dependency_count: int,
) -> pd.DataFrame:
    failed = int((~checks["passed"].map(_bool)).sum())
    identity = _mapping(profile.get("identity"))
    presence = _mapping(observation.get("credential_env_presence"))
    return pd.DataFrame(
        [
            {
                "passed": failed == 0,
                "ready": failed == 0,
                "status": (
                    "ready_for_separate_runtime_launch"
                    if failed == 0
                    else "blocked_runtime_preflight"
                ),
                "failed_checks": failed,
                "preflight_id": _text(receipt.get("preflight_id")),
                "receipt_sha256": _text(receipt.get("receipt_sha256")),
                "handoff_id": _text(profile.get("handoff_id")),
                "plan_sha256": _text(profile.get("plan_sha256")),
                "provider": _text(identity.get("provider")),
                "adapter": _text(identity.get("adapter")),
                "transport": _text(identity.get("transport")),
                "market": _text(identity.get("market")),
                "exchange": _text(identity.get("exchange")),
                "session_id": _text(identity.get("session_id")),
                "credential_env_var_count": len(presence),
                "credential_env_vars_present": sum(
                    _bool(value) for value in presence.values()
                ),
                "connectivity_backend_entrypoint": _text(
                    observation.get("backend_entrypoint")
                ),
                "connectivity_probe_called": _explicit_true(
                    observation,
                    "probe_called",
                ),
                "provider_connected": _explicit_true(
                    observation,
                    "connected",
                ),
                "provider_authenticated": _explicit_true(
                    observation,
                    "authenticated",
                ),
                "market_data_readable": _explicit_true(
                    observation,
                    "market_data_readable",
                ),
                "connectivity_latency_ms": _number(
                    observation.get("latency_ms")
                ),
                "connectivity_error_code": _safe_code(
                    observation.get("error_code")
                ),
                "recursive_dependency_count": recursive_dependency_count,
                "strategy_execution_enabled": False,
                "launch_executed": False,
                "requires_separate_runtime_launcher": True,
                "release_approved": False,
                "dry_run_only": True,
                "connectivity_only": True,
                "broker_order_api_enabled": False,
                "broker_order_api_called": False,
                "broker_api_called": False,
                "submission_enabled": False,
                "authorizes_submission": False,
                "credential_values_stored": False,
                "next_gate": "separate_controlled_live_dryrun_runtime_launcher",
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig,
    receipt: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_path: Path,
    handoff_root: Path,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "preflight_id": _text(receipt.get("preflight_id")),
        "receipt_sha256": _text(receipt.get("receipt_sha256")),
        "handoff_dir": str(handoff_root),
        "runtime_profile_path": str(profile_path),
        "runtime_profile": _jsonable(profile),
        "connectivity": _jsonable(observation),
        "ready": _bool(receipt.get("ready_for_separate_runtime_launch")),
        "strategy_execution_enabled": False,
        "launch_executed": False,
        "requires_separate_runtime_launcher": True,
        "release_approved": False,
        "dry_run_only": True,
        "connectivity_only": True,
        "broker_order_api_enabled": False,
        "broker_order_api_called": False,
        "broker_api_called": False,
        "submission_enabled": False,
        "authorizes_submission": False,
        "credential_values_stored": False,
    }


def _manifest_extra(
    receipt: Mapping[str, Any],
    profile: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    identity = _mapping(profile.get("identity"))
    return {
        "passed": _bool(receipt.get("ready_for_separate_runtime_launch")),
        "ready": _bool(receipt.get("ready_for_separate_runtime_launch")),
        "preflight_id": _text(receipt.get("preflight_id")),
        "receipt_sha256": _text(receipt.get("receipt_sha256")),
        "handoff_id": _text(profile.get("handoff_id")),
        "plan_sha256": _text(profile.get("plan_sha256")),
        "provider": _text(identity.get("provider")),
        "market": _text(identity.get("market")),
        "target_mode": "live_dryrun",
        "connectivity_probe_called": _explicit_true(
            observation,
            "probe_called",
        ),
        "provider_connected": _explicit_true(observation, "connected"),
        "provider_authenticated": _explicit_true(
            observation,
            "authenticated",
        ),
        "market_data_readable": _explicit_true(
            observation,
            "market_data_readable",
        ),
        "strategy_execution_enabled": False,
        "launch_executed": False,
        "requires_separate_runtime_launcher": True,
        "release_approved": False,
        "dry_run_only": True,
        "connectivity_only": True,
        "broker_order_api_enabled": False,
        "broker_order_api_called": False,
        "broker_api_called": False,
        "submission_enabled": False,
        "authorizes_submission": False,
        "credential_values_stored": False,
    }


def _runbook_markdown(summary: pd.Series) -> str:
    return "\n".join(
        [
            "# Provider Live-Dry-Run Runtime Preflight",
            "",
            f"- Status: `{summary['status']}`",
            f"- Preflight ID: `{summary['preflight_id']}`",
            f"- Handoff ID: `{summary['handoff_id']}`",
            f"- Provider: `{summary['provider']}`",
            f"- Session: `{summary['session_id']}`",
            f"- Credential variables present: `{summary['credential_env_vars_present']}/{summary['credential_env_var_count']}`",
            f"- Connectivity probe called: `{summary['connectivity_probe_called']}`",
            f"- Provider connected: `{summary['provider_connected']}`",
            f"- Provider authenticated: `{summary['provider_authenticated']}`",
            f"- Market data readable: `{summary['market_data_readable']}`",
            f"- Connectivity latency (ms): `{summary['connectivity_latency_ms']}`",
            "- Backend trust model: reviewed in-process connectivity module",
            "- Strategy runtime launched: no",
            "- Broker order API called: no",
            "- Submission enabled: no",
            "- Credential values stored: no",
            "",
            "A separate controlled runtime launcher is required. This receipt does not authorize or submit orders.",
            "An unaudited backend retains ambient process authority; this receipt does not independently attest backend side effects or provider-side credential scope.",
            "",
        ]
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
    false_fields = (
        "strategy_execution_enabled",
        "launch_executed",
        "release_approved",
        "broker_order_api_enabled",
        "broker_order_api_called",
        "broker_api_called",
        "submission_enabled",
        "authorizes_submission",
        "credential_values_stored",
    )
    return bool(
        all(
            _explicit_false(surface, field)
            for surface in surfaces
            for field in false_fields
        )
        and all(_explicit_true(surface, "dry_run_only") for surface in surfaces)
        and all(
            _explicit_true(surface, "connectivity_only")
            for surface in surfaces
        )
        and all(
            _explicit_true(surface, "requires_separate_runtime_launcher")
            for surface in surfaces
        )
    )


def _receipt_credential_safe(receipt: Mapping[str, Any]) -> bool:
    credentials = _mapping(receipt.get("credentials"))
    env_vars = _string_list(credentials.get("env_vars"))
    presence = _mapping(credentials.get("env_presence"))
    return bool(
        set(credentials) == {"env_vars", "env_presence", "values_stored"}
        and env_vars
        and len(env_vars) == len(set(env_vars))
        and all(ENV_NAME_RE.fullmatch(name) for name in env_vars)
        and set(presence) == set(env_vars)
        and all(isinstance(value, (bool, np.bool_)) for value in presence.values())
        and _explicit_false(credentials, "values_stored")
    )


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    handoff_root: Path,
    handoff_manifest_path: Path,
    profile_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    names = {
        "live_dryrun_handoff",
        "live_dryrun_handoff_manifest",
        "runtime_profile",
    }
    if recursive_dependencies:
        names.add("handoff_recursive_dependencies")
    if set(inputs) != names:
        return False
    direct = {
        "live_dryrun_handoff": (handoff_root, "directory"),
        "live_dryrun_handoff_manifest": (handoff_manifest_path, "file"),
        "runtime_profile": (profile_path, "file"),
    }
    for name, (path, kind) in direct.items():
        record = _mapping(inputs.get(name))
        if record.get("kind") != kind or not _text(record.get("path")):
            return False
        if Path(str(record["path"])).resolve() != path:
            return False
    if recursive_dependencies:
        paths = _fingerprint_paths(inputs.get("handoff_recursive_dependencies"))
        if (
            {path.resolve() for path in paths}
            != {path.resolve() for path in recursive_dependencies}
            or len(paths) != len(recursive_dependencies)
        ):
            return False
    return True


def _recursive_dependencies(
    handoff_manifest_path: Path,
    direct_paths: set[Path],
) -> list[Path]:
    return _unique_paths(
        [
            path
            for path in manifest_dependency_paths(handoff_manifest_path)
            if path.resolve() not in direct_paths
        ]
    )


def _reject_output_collision(
    out: Path,
    handoff_root: Path,
    profile_path: Path,
) -> None:
    if out == handoff_root or _is_relative_to(out, handoff_root):
        raise ValueError("runtime preflight output must be outside the handoff")
    if profile_path == out or _is_relative_to(profile_path, out):
        raise ValueError("runtime profile must be outside preflight output")


def _assert_credential_values_absent(
    out: Path,
    env_vars: tuple[str, ...],
    environment: Mapping[str, str],
) -> None:
    values = {
        str(environment.get(name, ""))
        for name in env_vars
        if len(str(environment.get(name, ""))) >= 8
    }
    if not values:
        return
    for path in out.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if any(value in text for value in values):
            raise RuntimeError(
                "credential value appeared in runtime-preflight artifacts"
            )


def _verification(
    *,
    root: Path,
    handoff_root: Path | None,
    profile_path: Path | None,
    manifest_current: bool,
    handoff_current: bool,
    profile_current: bool,
    credential_safe: bool,
    non_authorizing: bool,
    error: str,
) -> ProviderMarketDataImbalanceLiveDryrunRuntimePreflightVerification:
    return ProviderMarketDataImbalanceLiveDryrunRuntimePreflightVerification(
        verified=False,
        ready=False,
        manifest_current=manifest_current,
        handoff_current=handoff_current,
        runtime_profile_current=profile_current,
        artifacts_consistent=False,
        credential_safe=credential_safe,
        non_authorizing=non_authorizing,
        output_dir=root,
        handoff_dir=handoff_root,
        runtime_profile_path=profile_path,
        error=error,
    )


def _input_file_current(path: Path, record: Mapping[str, Any]) -> bool:
    return bool(
        path.is_file()
        and _valid_sha256(record.get("sha256"))
        and file_sha256(path) == _text(record.get("sha256")).lower()
    )


def _fingerprint_paths(value: Any) -> list[Path]:
    if isinstance(value, Mapping):
        if value.get("kind") in {"file", "directory"} and _text(value.get("path")):
            return [Path(str(value["path"]))]
        paths: list[Path] = []
        for item in value.values():
            paths.extend(_fingerprint_paths(item))
        return paths
    if isinstance(value, list):
        paths = []
        for item in value:
            paths.extend(_fingerprint_paths(item))
        return paths
    return []


def _validate_config(
    config: ProviderMarketDataImbalanceLiveDryrunRuntimePreflightConfig,
) -> None:
    if config.max_dependency_count <= 0:
        raise ValueError("max_dependency_count must be positive")
    if (
        not np.isfinite(config.max_connectivity_latency_ms)
        or config.max_connectivity_latency_ms <= 0
    ):
        raise ValueError("max_connectivity_latency_ms must be finite and positive")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if frame.empty:
        raise ValueError(f"{label} is empty: {path}")
    return frame


def _single_row(frame: pd.DataFrame, label: str) -> pd.Series:
    if len(frame) != 1:
        raise ValueError(f"{label} must contain exactly one row")
    return frame.iloc[0]


def _check(
    name: str,
    component: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "component": component,
        "value": value,
        "operator": operator,
        "threshold": threshold,
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
            if isinstance(actual_value, (int, float, np.integer, np.floating)) and isinstance(expected_value, (int, float, np.integer, np.floating)):
                if float(actual_value) != float(expected_value):
                    return False
            elif str(actual_value) != str(expected_value):
                return False
    return True


def _artifact_value_missing(value: Any) -> bool:
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan"}):
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
        numeric = _number(raw)
        return numeric == 1.0
    return _text(raw).lower() in {"1", "true", "yes"}


def _explicit_false(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return not bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return _number(raw) == 0.0
    return _text(raw).lower() in {"0", "false", "no", "off"}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_text(value: Any) -> str:
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("preflight observation time is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("preflight observation time must be UTC")
    return parsed.isoformat()


def _safe_code(value: Any) -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", _text(value).lower()).strip("_")[:64]
    return text if SAFE_CODE_RE.fullmatch(text) else "invalid_code"


def _number(value: Any) -> float:
    if isinstance(value, (bool, np.bool_)):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if np.isfinite(number) else 0.0


def _valid_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return bool(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text)
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _unique_paths(paths: list[Path]) -> list[Path]:
    found = {str(path.resolve()): path.resolve() for path in paths}
    return [found[key] for key in sorted(found)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return _number(value) != 0.0
    return _text(value).lower() in {"1", "true", "yes", "y", "passed"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value
