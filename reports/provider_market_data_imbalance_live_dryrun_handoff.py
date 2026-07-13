from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
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
from reports.provider_market_data_imbalance_release_decision import (
    RUN_TYPE as RELEASE_DECISION_RUN_TYPE,
    verify_provider_market_data_imbalance_release_decision,
)


RUN_TYPE = "provider_market_data_imbalance_live_dryrun_handoff"
CONTRACT_VERSION = "provider_market_data_imbalance_live_dryrun_handoff/v1"
CONTROLS_CONTRACT_VERSION = "provider_live_dryrun_runtime_controls/v1"
CERTIFICATE_FILE = (
    "provider_market_data_imbalance_broker_rehearsal_certificate.json"
)
HANDOFF_ARTIFACTS = (
    "provider_market_data_imbalance_live_dryrun_handoff_checks.csv",
    "provider_market_data_imbalance_live_dryrun_handoff_proofs.csv",
    "provider_market_data_imbalance_live_dryrun_handoff_summary.csv",
    "provider_market_data_imbalance_live_dryrun_handoff_plan.json",
    "provider_market_data_imbalance_live_dryrun_handoff_config.json",
    "provider_market_data_imbalance_live_dryrun_handoff_runbook.md",
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
PROOF_COLUMNS = (
    "component",
    "path",
    "kind",
    "sha256",
    "digest_sha256",
    "current",
)
FORBIDDEN_CONTROL_KEY_PARTS = (
    "access_key",
    "api_key",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunHandoffConfig:
    max_dependency_count: int = 4096


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunHandoffReport:
    checks: pd.DataFrame
    proofs: pd.DataFrame
    summary: pd.DataFrame
    plan: dict[str, Any]
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(
            not self.summary.empty
            and _bool(self.summary.iloc[0].get("ready", False))
        )


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLiveDryrunHandoffVerification:
    verified: bool
    ready: bool
    manifest_current: bool
    release_decision_current: bool
    runtime_controls_current: bool
    rollback_runbook_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    release_decision_dir: Path | None
    runtime_controls_path: Path | None
    rollback_runbook_path: Path | None
    error: str = ""


def write_provider_market_data_imbalance_live_dryrun_handoff(
    release_decision_dir: str | Path,
    runtime_controls_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceLiveDryrunHandoffConfig | None = None,
) -> ProviderMarketDataImbalanceLiveDryrunHandoffReport:
    config = config or ProviderMarketDataImbalanceLiveDryrunHandoffConfig()
    _validate_config(config)
    decision_root = Path(release_decision_dir).resolve()
    decision_manifest_path = decision_root / MANIFEST_NAME
    controls_path = Path(runtime_controls_path).resolve()
    out = Path(output_dir).resolve()
    if out.exists():
        raise FileExistsError(f"live-dry-run handoff output already exists: {out}")

    decision_verification = (
        verify_provider_market_data_imbalance_release_decision(decision_root)
    )
    if not (
        decision_verification.verified
        and decision_verification.sealed
        and decision_verification.approved
        and decision_verification.ready
    ):
        raise ValueError(
            "live-dry-run handoff requires a verified approved release "
            f"decision: {decision_verification.error or 'decision_not_ready'}"
        )
    source = _source_state(decision_root)
    controls = _read_json(controls_path, "runtime controls")
    rollback_path = _rollback_path(controls, controls_path)
    _reject_output_collision(
        out,
        decision_root=decision_root,
        controls_path=controls_path,
        rollback_path=rollback_path,
    )
    direct_paths = {
        decision_root,
        decision_manifest_path,
        controls_path,
        rollback_path,
    }
    recursive_dependencies = _recursive_dependencies(
        decision_manifest_path,
        direct_paths,
    )
    checks = _handoff_checks(
        decision_verification=decision_verification,
        source=source,
        controls=controls,
        controls_path=controls_path,
        rollback_path=rollback_path,
        recursive_dependency_count=len(recursive_dependencies),
        config=config,
    )
    failed_checks = checks.loc[
        ~checks["passed"].map(_bool),
        "check",
    ].astype(str).tolist()
    if failed_checks:
        raise ValueError(
            "live-dry-run handoff contract failed: "
            + ", ".join(failed_checks)
        )

    proof_contract = _proof_contract(
        source=source,
        controls_path=controls_path,
        rollback_path=rollback_path,
    )
    plan_core = _plan_core(source=source, controls=controls, proof_contract=proof_contract)
    plan_sha256 = _canonical_sha256(plan_core)
    handoff_id = f"provider-live-dryrun-handoff-{plan_sha256[:24]}"
    plan = {
        **plan_core,
        "handoff_id": handoff_id,
        "plan_sha256": plan_sha256,
    }
    proofs = _proof_rows(proof_contract)
    summary = _summary(
        handoff_id=handoff_id,
        plan_sha256=plan_sha256,
        source=source,
        controls=controls,
        proof_contract=proof_contract,
        recursive_dependency_count=len(recursive_dependencies),
        checks=checks,
    )
    config_payload = _config_payload(
        config=config,
        handoff_id=handoff_id,
        plan_sha256=plan_sha256,
        decision_root=decision_root,
        controls_path=controls_path,
        rollback_path=rollback_path,
        proof_contract=proof_contract,
    )

    out.mkdir(parents=True, exist_ok=True)
    checks.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_handoff_checks.csv",
        index=False,
    )
    proofs.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_handoff_proofs.csv",
        index=False,
    )
    summary.to_csv(
        out / "provider_market_data_imbalance_live_dryrun_handoff_summary.csv",
        index=False,
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_handoff_plan.json"
    ).write_text(
        json.dumps(_jsonable(plan), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_handoff_config.json"
    ).write_text(
        json.dumps(_jsonable(config_payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (
        out / "provider_market_data_imbalance_live_dryrun_handoff_runbook.md"
    ).write_text(
        _runbook_markdown(summary.iloc[0], controls, proof_contract),
        encoding="utf-8",
    )

    final_decision_verification = (
        verify_provider_market_data_imbalance_release_decision(decision_root)
    )
    if (
        not final_decision_verification.ready
        or file_sha256(decision_manifest_path)
        != proof_contract["release_decision"]["manifest_sha256"]
        or file_sha256(controls_path)
        != proof_contract["runtime_controls"]["sha256"]
        or file_sha256(rollback_path)
        != proof_contract["rollback_runbook"]["sha256"]
    ):
        raise RuntimeError(
            "release decision or runtime controls changed during handoff preparation"
        )

    manifest_inputs: dict[str, Any] = {
        "release_decision": decision_root,
        "release_decision_manifest": decision_manifest_path,
        "runtime_controls": controls_path,
        "rollback_runbook": rollback_path,
    }
    if recursive_dependencies:
        manifest_inputs["release_decision_recursive_dependencies"] = (
            recursive_dependencies
        )
    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=manifest_inputs,
        extra=_manifest_extra(
            handoff_id=handoff_id,
            plan_sha256=plan_sha256,
            source=source,
            proof_contract=proof_contract,
        ),
    )
    return ProviderMarketDataImbalanceLiveDryrunHandoffReport(
        checks=checks,
        proofs=proofs,
        summary=summary,
        plan=plan,
        config=config_payload,
        output_dir=out,
    )


def verify_provider_market_data_imbalance_live_dryrun_handoff(
    handoff_dir: str | Path,
) -> ProviderMarketDataImbalanceLiveDryrunHandoffVerification:
    candidate = Path(handoff_dir)
    root = candidate.parent if candidate.is_file() else candidate
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=RUN_TYPE,
        required_artifacts=HANDOFF_ARTIFACTS,
        require_input_fingerprints=True,
    )
    decision_root: Path | None = None
    controls_path: Path | None = None
    rollback_path: Path | None = None
    try:
        manifest = _read_json(manifest_path, "handoff manifest")
        checks_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_handoff_checks.csv",
            "handoff checks",
        )
        proofs_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_handoff_proofs.csv",
            "handoff proofs",
        )
        summary_frame = _read_csv(
            root / "provider_market_data_imbalance_live_dryrun_handoff_summary.csv",
            "handoff summary",
        )
        summary = _single_row(summary_frame, "handoff summary")
        saved_plan = _read_json(
            root / "provider_market_data_imbalance_live_dryrun_handoff_plan.json",
            "handoff plan",
        )
        saved_config = _read_json(
            root / "provider_market_data_imbalance_live_dryrun_handoff_config.json",
            "handoff config",
        )
        runbook = (
            root / "provider_market_data_imbalance_live_dryrun_handoff_runbook.md"
        ).read_text(encoding="utf-8")
        inputs = _mapping(manifest.get("inputs"))
        decision_record = _mapping(inputs.get("release_decision"))
        controls_record = _mapping(inputs.get("runtime_controls"))
        rollback_record = _mapping(inputs.get("rollback_runbook"))
        if (
            decision_record.get("kind") != "directory"
            or controls_record.get("kind") != "file"
            or rollback_record.get("kind") != "file"
            or not _text(decision_record.get("path"))
            or not _text(controls_record.get("path"))
            or not _text(rollback_record.get("path"))
        ):
            raise ValueError("handoff input contract is invalid")
        decision_root = Path(str(decision_record["path"])).resolve()
        controls_path = Path(str(controls_record["path"])).resolve()
        rollback_path = Path(str(rollback_record["path"])).resolve()
        decision_manifest_path = decision_root / MANIFEST_NAME
        decision_verification = (
            verify_provider_market_data_imbalance_release_decision(decision_root)
        )
        decision_current = bool(
            decision_verification.verified
            and decision_verification.approved
            and decision_verification.ready
        )
        controls_current = _input_file_current(controls_path, controls_record)
        rollback_current = _input_file_current(rollback_path, rollback_record)
        if not decision_current or not controls_current or not rollback_current:
            return ProviderMarketDataImbalanceLiveDryrunHandoffVerification(
                verified=False,
                ready=False,
                manifest_current=bool(integrity.passed),
                release_decision_current=decision_current,
                runtime_controls_current=controls_current,
                rollback_runbook_current=rollback_current,
                artifacts_consistent=False,
                non_authorizing=_surfaces_non_authorizing(
                    summary,
                    saved_plan,
                    saved_config,
                    _mapping(manifest.get("extra")),
                ),
                output_dir=root,
                release_decision_dir=decision_root,
                runtime_controls_path=controls_path,
                rollback_runbook_path=rollback_path,
                error="handoff_source_not_current",
            )

        source = _source_state(decision_root)
        controls = _read_json(controls_path, "runtime controls")
        resolved_rollback_path = _rollback_path(controls, controls_path)
        manifest_settings = dict(
            _mapping(_mapping(manifest.get("parameters")).get("config"))
        )
        config = ProviderMarketDataImbalanceLiveDryrunHandoffConfig(
            **manifest_settings
        )
        _validate_config(config)
        direct_paths = {
            decision_root,
            decision_manifest_path,
            controls_path,
            rollback_path,
        }
        recursive_dependencies = _recursive_dependencies(
            decision_manifest_path,
            direct_paths,
        )
        expected_checks = _handoff_checks(
            decision_verification=decision_verification,
            source=source,
            controls=controls,
            controls_path=controls_path,
            rollback_path=rollback_path,
            recursive_dependency_count=len(recursive_dependencies),
            config=config,
        )
        failed_checks = expected_checks.loc[
            ~expected_checks["passed"].map(_bool),
            "check",
        ].astype(str).tolist()
        if failed_checks or resolved_rollback_path != rollback_path:
            return ProviderMarketDataImbalanceLiveDryrunHandoffVerification(
                verified=False,
                ready=False,
                manifest_current=bool(integrity.passed),
                release_decision_current=True,
                runtime_controls_current=True,
                rollback_runbook_current=True,
                artifacts_consistent=False,
                non_authorizing=_surfaces_non_authorizing(
                    summary,
                    saved_plan,
                    saved_config,
                    _mapping(manifest.get("extra")),
                ),
                output_dir=root,
                release_decision_dir=decision_root,
                runtime_controls_path=controls_path,
                rollback_runbook_path=rollback_path,
                error="handoff_controls_contract_failed:" + ",".join(failed_checks),
            )
        proof_contract = _proof_contract(
            source=source,
            controls_path=controls_path,
            rollback_path=rollback_path,
        )
        expected_core = _plan_core(
            source=source,
            controls=controls,
            proof_contract=proof_contract,
        )
        plan_sha256 = _canonical_sha256(expected_core)
        handoff_id = f"provider-live-dryrun-handoff-{plan_sha256[:24]}"
        expected_plan = {
            **expected_core,
            "handoff_id": handoff_id,
            "plan_sha256": plan_sha256,
        }
        expected_proofs = _proof_rows(proof_contract)
        expected_summary = _summary(
            handoff_id=handoff_id,
            plan_sha256=plan_sha256,
            source=source,
            controls=controls,
            proof_contract=proof_contract,
            recursive_dependency_count=len(recursive_dependencies),
            checks=expected_checks,
        )
        expected_config = _config_payload(
            config=config,
            handoff_id=handoff_id,
            plan_sha256=plan_sha256,
            decision_root=decision_root,
            controls_path=controls_path,
            rollback_path=rollback_path,
            proof_contract=proof_contract,
        )
        expected_extra = _manifest_extra(
            handoff_id=handoff_id,
            plan_sha256=plan_sha256,
            source=source,
            proof_contract=proof_contract,
        )
        expected_runbook = _runbook_markdown(
            expected_summary.iloc[0],
            controls,
            proof_contract,
        )
        artifacts_consistent = bool(
            saved_plan == expected_plan
            and saved_config == expected_config
            and _dataframe_records_equal(checks_frame, expected_checks)
            and _dataframe_records_equal(proofs_frame, expected_proofs)
            and _dataframe_records_equal(summary_frame, expected_summary)
            and runbook == expected_runbook
            and dict(_mapping(manifest.get("extra"))) == expected_extra
            and _manifest_inputs_match(
                inputs,
                decision_root=decision_root,
                decision_manifest_path=decision_manifest_path,
                controls_path=controls_path,
                rollback_path=rollback_path,
                recursive_dependencies=recursive_dependencies,
            )
        )
        non_authorizing = _surfaces_non_authorizing(
            summary,
            saved_plan,
            saved_config,
            _mapping(manifest.get("extra")),
        )
        ready_claim = bool(
            _bool(summary.get("ready", False))
            and _bool(saved_plan.get("ready", False))
            and _bool(saved_config.get("ready", False))
            and _bool(_mapping(manifest.get("extra")).get("ready", False))
        )
        verified = bool(
            integrity.passed
            and decision_current
            and controls_current
            and rollback_current
            and artifacts_consistent
            and non_authorizing
            and ready_claim
        )
        error = (
            integrity.error
            or (
                "handoff_artifacts_disagree_with_sources"
                if not artifacts_consistent
                else ""
            )
            or (
                "handoff_authorization_claim_invalid"
                if not non_authorizing
                else ""
            )
            or ("handoff_not_ready" if not ready_claim else "")
        )
        return ProviderMarketDataImbalanceLiveDryrunHandoffVerification(
            verified=verified,
            ready=verified,
            manifest_current=bool(integrity.passed),
            release_decision_current=decision_current,
            runtime_controls_current=controls_current,
            rollback_runbook_current=rollback_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            release_decision_dir=decision_root,
            runtime_controls_path=controls_path,
            rollback_runbook_path=rollback_path,
            error=error,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ProviderMarketDataImbalanceLiveDryrunHandoffVerification(
            verified=False,
            ready=False,
            manifest_current=bool(integrity.passed),
            release_decision_current=False,
            runtime_controls_current=False,
            rollback_runbook_current=False,
            artifacts_consistent=False,
            non_authorizing=False,
            output_dir=root,
            release_decision_dir=decision_root,
            runtime_controls_path=controls_path,
            rollback_runbook_path=rollback_path,
            error=f"handoff_unreadable:{exc}",
        )


def _source_state(decision_root: Path) -> dict[str, Any]:
    decision_manifest_path = decision_root / MANIFEST_NAME
    decision_manifest = _read_json(decision_manifest_path, "release-decision manifest")
    if _text(decision_manifest.get("run_type")) != RELEASE_DECISION_RUN_TYPE:
        raise ValueError("handoff source is not a release-decision run")
    decision_summary = _single_row(
        _read_csv(
            decision_root / "provider_market_data_imbalance_release_decision_summary.csv",
            "release-decision summary",
        ),
        "release-decision summary",
    )
    decision = _read_json(
        decision_root / "provider_market_data_imbalance_release_decision.json",
        "sealed release decision",
    )
    release_review_path_text = _text(
        _mapping(_mapping(decision.get("proof_contract")).get("release_review")).get(
            "path"
        )
    )
    if not release_review_path_text:
        raise ValueError("sealed decision does not bind a release-review directory")
    release_review_path = Path(release_review_path_text).resolve()
    if not release_review_path.is_dir():
        raise ValueError("sealed decision does not bind a release-review directory")
    release_summary = _single_row(
        _read_csv(
            release_review_path / "provider_market_data_imbalance_release_review_summary.csv",
            "release-review summary",
        ),
        "release-review summary",
    )
    release_packet = _read_json(
        release_review_path / "provider_market_data_imbalance_release_review_packet.json",
        "release-review packet",
    )
    certificate_binding = _mapping(
        _mapping(release_packet.get("proof_contract")).get(
            "broker_rehearsal_certificate"
        )
    )
    certificate_path_text = _text(certificate_binding.get("path"))
    if not certificate_path_text:
        raise ValueError("release review does not bind a rehearsal certificate")
    certificate_dir = Path(certificate_path_text).resolve()
    if not certificate_dir.is_dir():
        raise ValueError("release review does not bind a rehearsal certificate")
    certificate = _read_json(certificate_dir / CERTIFICATE_FILE, "rehearsal certificate")
    certificate_payload = _mapping(certificate.get("payload"))
    certificate_identity = _mapping(certificate_payload.get("identity"))
    return {
        "decision_root": decision_root,
        "decision_manifest_path": decision_manifest_path,
        "decision_manifest_sha256": file_sha256(decision_manifest_path),
        "decision_summary": decision_summary,
        "decision": decision,
        "release_review_path": release_review_path,
        "release_summary": release_summary,
        "release_packet": release_packet,
        "certificate_dir": certificate_dir,
        "certificate": certificate,
        "certificate_identity": certificate_identity,
        "certificate_sha256": _text(certificate.get("certificate_sha256")).lower(),
    }


def _handoff_checks(
    *,
    decision_verification: Any,
    source: Mapping[str, Any],
    controls: Mapping[str, Any],
    controls_path: Path,
    rollback_path: Path,
    recursive_dependency_count: int,
    config: ProviderMarketDataImbalanceLiveDryrunHandoffConfig,
) -> pd.DataFrame:
    decision_summary = source["decision_summary"]
    certificate_identity = _mapping(source.get("certificate_identity"))
    provider_session = _mapping(controls.get("provider_session"))
    limits = _mapping(controls.get("limits"))
    kill_switch = _mapping(controls.get("kill_switch"))
    rollback = _mapping(controls.get("rollback"))
    safety = _mapping(controls.get("safety"))
    session_open = _minutes(provider_session.get("open_local"))
    session_close = _minutes(provider_session.get("close_local"))
    max_orders = _integer(limits.get("max_orders_per_session"))
    max_notional = _number(limits.get("max_notional_per_session"))
    max_open_orders = _integer(limits.get("max_open_orders"))
    max_position_lots = _integer(limits.get("max_position_lots"))
    expected_certificate_sha = _text(
        source["release_summary"].get("broker_rehearsal_certificate_sha256")
    ).lower()
    checks = [
        _check("release_decision_verified", "decision", decision_verification.verified, "is", True, decision_verification.verified, "release decision is not verified"),
        _check("release_decision_approved", "decision", decision_verification.approved, "is", True, decision_verification.approved, "release decision is not approved"),
        _check("release_decision_ready", "decision", decision_verification.ready, "is", True, decision_verification.ready, "release decision is not ready"),
        _check("controls_contract_version", "controls", _text(controls.get("contract_version")), "==", CONTROLS_CONTRACT_VERSION, _text(controls.get("contract_version")) == CONTROLS_CONTRACT_VERSION, "runtime controls contract version is invalid"),
        _check("controls_decision_id", "binding", _text(controls.get("decision_id")), "==", _text(decision_summary.get("decision_id")), _text(controls.get("decision_id")) == _text(decision_summary.get("decision_id")), "runtime controls do not bind the approved decision ID"),
        _check("controls_decision_sha256", "binding", _text(controls.get("decision_sha256")).lower(), "==", _text(decision_summary.get("decision_sha256")).lower(), _text(controls.get("decision_sha256")).lower() == _text(decision_summary.get("decision_sha256")).lower(), "runtime controls do not bind the approved decision SHA"),
        _check("certificate_payload_sha256", "binding", source.get("certificate_sha256", ""), "==", expected_certificate_sha, _valid_sha256(expected_certificate_sha) and source.get("certificate_sha256", "") == expected_certificate_sha, "retained certificate payload SHA differs from release review"),
        _check("target_mode_live_dryrun", "identity", _identity(decision_summary.get("target_mode")), "==", "live_dryrun", _identity(decision_summary.get("target_mode")) == "live_dryrun", "approved decision target mode is not live_dryrun"),
        _check("provider_present", "identity", _text(provider_session.get("provider")), "nonempty", True, bool(_text(provider_session.get("provider"))), "provider session identity is missing provider"),
        _check("transport_present", "identity", _text(provider_session.get("transport")), "nonempty", True, bool(_text(provider_session.get("transport"))), "provider session identity is missing transport"),
        _check("exchange_present", "identity", _text(provider_session.get("exchange")), "nonempty", True, bool(_text(provider_session.get("exchange"))), "provider session identity is missing exchange"),
        _check("adapter_present", "identity", _text(provider_session.get("adapter")), "nonempty", True, bool(_text(provider_session.get("adapter"))), "provider session identity is missing adapter"),
        _check("session_id_present", "identity", _text(provider_session.get("session_id")), "nonempty", True, bool(_text(provider_session.get("session_id"))), "provider session ID is required"),
        _check("trading_date_valid", "identity", _text(provider_session.get("trading_date")), "iso_date", True, _date_valid(provider_session.get("trading_date")), "provider trading date must be ISO-8601"),
        _check("session_timezone_india", "identity", _text(provider_session.get("timezone")), "==", "Asia/Kolkata", _text(provider_session.get("timezone")) == "Asia/Kolkata", "India live-dry-run session timezone must be Asia/Kolkata"),
        _check("session_window_valid", "identity", f"{provider_session.get('open_local', '')}-{provider_session.get('close_local', '')}", "open<close", True, session_open >= 0 and session_close > session_open, "provider session window is invalid"),
        _check("max_orders_positive", "limits", max_orders, ">", 0, max_orders > 0, "max orders per session must be positive"),
        _check("max_notional_positive", "limits", max_notional, ">", 0, max_notional > 0, "max notional per session must be positive"),
        _check("max_open_orders_bounded", "limits", max_open_orders, "between", f"1..{max_orders}", 0 < max_open_orders <= max_orders, "max open orders must be positive and no greater than max session orders"),
        _check("max_position_lots_positive", "limits", max_position_lots, ">", 0, max_position_lots > 0, "max position lots must be positive"),
        _check("kill_switch_enabled", "kill_switch", kill_switch.get("enabled", False), "is", True, _explicit_true(kill_switch, "enabled"), "kill switch must be enabled"),
        _check("kill_switch_limit_trigger", "kill_switch", kill_switch.get("trigger_on_limit_breach", False), "is", True, _explicit_true(kill_switch, "trigger_on_limit_breach"), "kill switch must trigger on a limit breach"),
        _check("kill_switch_stops_orders", "kill_switch", kill_switch.get("stop_new_orders", False), "is", True, _explicit_true(kill_switch, "stop_new_orders"), "kill switch must stop new orders"),
        _check("kill_switch_cancels_orders", "kill_switch", kill_switch.get("cancel_open_orders", False), "is", True, _explicit_true(kill_switch, "cancel_open_orders"), "kill switch must cancel open dry-run orders"),
        _check("kill_switch_owner_present", "kill_switch", _text(kill_switch.get("owner")), "nonempty", True, bool(_text(kill_switch.get("owner"))), "kill switch owner is required"),
        _check("rollback_procedure_present", "rollback", _text(rollback.get("procedure_id")), "nonempty", True, bool(_text(rollback.get("procedure_id"))), "rollback procedure ID is required"),
        _check("rollback_owner_present", "rollback", _text(rollback.get("owner")), "nonempty", True, bool(_text(rollback.get("owner"))), "rollback owner is required"),
        _check("rollback_runbook_exists", "rollback", str(rollback_path), "is_file", True, rollback_path.is_file(), "rollback runbook is missing"),
        _check("rollback_runbook_sha256", "rollback", _text(rollback.get("runbook_sha256")).lower(), "==", file_sha256(rollback_path) if rollback_path.is_file() else "", rollback_path.is_file() and _text(rollback.get("runbook_sha256")).lower() == file_sha256(rollback_path), "rollback runbook SHA is invalid"),
        _check("controls_dry_run_only", "safety", safety.get("dry_run_only", False), "is", True, _explicit_true(safety, "dry_run_only"), "runtime controls must be dry-run only"),
        _check("controls_submission_disabled", "safety", safety.get("submission_enabled", "missing"), "is", False, _explicit_false(safety, "submission_enabled"), "runtime controls must disable submission"),
        _check("controls_broker_api_not_called", "safety", safety.get("broker_api_called", "missing"), "is", False, _explicit_false(safety, "broker_api_called"), "runtime controls must state that no broker API is called"),
        _check("controls_non_authorizing", "safety", safety.get("authorizes_submission", "missing"), "is", False, _explicit_false(safety, "authorizes_submission"), "runtime controls must remain non-authorizing"),
        _check("controls_credential_free", "safety", ",".join(_forbidden_control_keys(controls)), "==", "", not _forbidden_control_keys(controls), "runtime controls contain credential-bearing key names"),
        _check("recursive_dependency_limit", "integrity", recursive_dependency_count, "<=", config.max_dependency_count, recursive_dependency_count <= config.max_dependency_count, "release-decision dependency graph exceeds the handoff limit"),
    ]
    for field in ("provider", "transport", "exchange", "adapter"):
        actual = _identity(provider_session.get(field))
        expected = _identity(certificate_identity.get(field))
        checks.append(
            _check(
                f"provider_session_{field}_matches_certificate",
                "identity",
                actual,
                "==",
                expected,
                bool(actual) and actual == expected,
                f"runtime provider session {field} differs from retained certificate",
            )
        )
    for field in ("strategy", "market", "target_mode"):
        actual = _normalize_strategy(certificate_identity.get(field)) if field == "strategy" else _identity(certificate_identity.get(field))
        expected = _normalize_strategy(decision_summary.get(field)) if field == "strategy" else _identity(decision_summary.get(field))
        checks.append(
            _check(
                f"certificate_{field}_matches_decision",
                "identity",
                actual,
                "==",
                expected,
                bool(actual) and actual == expected,
                f"retained certificate {field} differs from approved decision",
            )
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _proof_contract(
    *,
    source: Mapping[str, Any],
    controls_path: Path,
    rollback_path: Path,
) -> dict[str, Any]:
    decision_summary = source["decision_summary"]
    return {
        "release_decision": {
            "path": str(source["decision_root"]),
            "manifest_path": str(source["decision_manifest_path"]),
            "manifest_sha256": source["decision_manifest_sha256"],
            "decision_id": _text(decision_summary.get("decision_id")),
            "decision_sha256": _text(decision_summary.get("decision_sha256")).lower(),
        },
        "runtime_controls": {
            "path": str(controls_path),
            "sha256": file_sha256(controls_path),
        },
        "rollback_runbook": {
            "path": str(rollback_path),
            "sha256": file_sha256(rollback_path),
        },
        "broker_rehearsal_certificate": {
            "path": str(source["certificate_dir"]),
            "certificate_sha256": source["certificate_sha256"],
            "manifest_sha256": _text(
                source["release_summary"].get(
                    "broker_rehearsal_certificate_manifest_sha256"
                )
            ).lower(),
        },
    }


def _plan_core(
    *,
    source: Mapping[str, Any],
    controls: Mapping[str, Any],
    proof_contract: Mapping[str, Any],
) -> dict[str, Any]:
    decision_summary = source["decision_summary"]
    provider_session = _mapping(controls.get("provider_session"))
    limits = _mapping(controls.get("limits"))
    kill_switch = _mapping(controls.get("kill_switch"))
    rollback = _mapping(controls.get("rollback"))
    return {
        "schema_version": 1,
        "contract_version": CONTRACT_VERSION,
        "plan_type": "provider_market_data_imbalance_controlled_live_dryrun_handoff",
        "status": "ready_for_controlled_live_dryrun_handoff",
        "ready": True,
        "identity": {
            "strategy": _text(decision_summary.get("strategy")),
            "market": _text(decision_summary.get("market")),
            "target_mode": "live_dryrun",
            "provider": _text(provider_session.get("provider")),
            "transport": _text(provider_session.get("transport")),
            "exchange": _text(provider_session.get("exchange")),
            "adapter": _text(provider_session.get("adapter")),
            "session_id": _text(provider_session.get("session_id")),
            "trading_date": _text(provider_session.get("trading_date")),
            "timezone": _text(provider_session.get("timezone")),
            "open_local": _text(provider_session.get("open_local")),
            "close_local": _text(provider_session.get("close_local")),
        },
        "limits": {
            "max_orders_per_session": _integer(limits.get("max_orders_per_session")),
            "max_notional_per_session": _number(limits.get("max_notional_per_session")),
            "max_open_orders": _integer(limits.get("max_open_orders")),
            "max_position_lots": _integer(limits.get("max_position_lots")),
        },
        "kill_switch": {
            "enabled": True,
            "trigger_on_limit_breach": True,
            "stop_new_orders": True,
            "cancel_open_orders": True,
            "owner": _text(kill_switch.get("owner")),
        },
        "rollback": {
            "procedure_id": _text(rollback.get("procedure_id")),
            "owner": _text(rollback.get("owner")),
            "runbook_path": proof_contract["rollback_runbook"]["path"],
            "runbook_sha256": proof_contract["rollback_runbook"]["sha256"],
        },
        "steps": [
            {"sequence": 1, "action": "verify_release_decision_and_controls"},
            {"sequence": 2, "action": "confirm_provider_session_identity"},
            {"sequence": 3, "action": "arm_kill_switch_before_runtime_start"},
            {"sequence": 4, "action": "start_separately_controlled_dryrun_runtime"},
            {"sequence": 5, "action": "monitor_limits_and_record_telemetry"},
            {"sequence": 6, "action": "stop_runtime_and_reconcile_dryrun_outputs"},
        ],
        "proof_contract": proof_contract,
        "safety": {
            "execution_enabled": False,
            "requires_separate_runtime_launcher": True,
            "dry_run_only": True,
            "submission_enabled": False,
            "broker_api_called": False,
            "authorizes_submission": False,
            "credential_values_stored": False,
        },
    }


def _proof_rows(proof_contract: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for component in (
        "release_decision",
        "runtime_controls",
        "rollback_runbook",
        "broker_rehearsal_certificate",
    ):
        proof = _mapping(proof_contract.get(component))
        digest = _text(
            proof.get("sha256")
            or proof.get("manifest_sha256")
            or proof.get("certificate_sha256")
        ).lower()
        rows.append(
            {
                "component": component,
                "path": _text(proof.get("path")),
                "kind": "file" if component in {"runtime_controls", "rollback_runbook"} else "sha256_binding",
                "sha256": digest,
                "digest_sha256": digest,
                "current": True,
            }
        )
    return pd.DataFrame(rows, columns=PROOF_COLUMNS)


def _summary(
    *,
    handoff_id: str,
    plan_sha256: str,
    source: Mapping[str, Any],
    controls: Mapping[str, Any],
    proof_contract: Mapping[str, Any],
    recursive_dependency_count: int,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed_checks = int((~checks["passed"].map(_bool)).sum())
    identity = _mapping(controls.get("provider_session"))
    limits = _mapping(controls.get("limits"))
    decision_summary = source["decision_summary"]
    return pd.DataFrame(
        [
            {
                "passed": failed_checks == 0,
                "ready": failed_checks == 0,
                "status": "ready_for_controlled_live_dryrun_handoff",
                "failed_checks": failed_checks,
                "handoff_id": handoff_id,
                "plan_sha256": plan_sha256,
                "decision_id": _text(decision_summary.get("decision_id")),
                "decision_sha256": _text(decision_summary.get("decision_sha256")),
                "release_decision_manifest_sha256": proof_contract["release_decision"]["manifest_sha256"],
                "runtime_controls_sha256": proof_contract["runtime_controls"]["sha256"],
                "rollback_runbook_sha256": proof_contract["rollback_runbook"]["sha256"],
                "broker_rehearsal_certificate_sha256": proof_contract["broker_rehearsal_certificate"]["certificate_sha256"],
                "strategy": _text(decision_summary.get("strategy")),
                "market": _text(decision_summary.get("market")),
                "target_mode": "live_dryrun",
                "provider": _text(identity.get("provider")),
                "transport": _text(identity.get("transport")),
                "exchange": _text(identity.get("exchange")),
                "adapter": _text(identity.get("adapter")),
                "session_id": _text(identity.get("session_id")),
                "trading_date": _text(identity.get("trading_date")),
                "session_timezone": _text(identity.get("timezone")),
                "session_open_local": _text(identity.get("open_local")),
                "session_close_local": _text(identity.get("close_local")),
                "max_orders_per_session": _integer(limits.get("max_orders_per_session")),
                "max_notional_per_session": _number(limits.get("max_notional_per_session")),
                "max_open_orders": _integer(limits.get("max_open_orders")),
                "max_position_lots": _integer(limits.get("max_position_lots")),
                "recursive_dependency_count": recursive_dependency_count,
                "execution_enabled": False,
                "requires_separate_runtime_launcher": True,
                "release_approved": False,
                "dry_run_only": True,
                "submission_enabled": False,
                "broker_api_called": False,
                "authorizes_submission": False,
                "credential_values_stored": False,
                "recommendation": "review_handoff_before_separate_runtime_launch",
                "next_gate": "controlled_live_dryrun_runtime_preflight",
            }
        ]
    )


def _config_payload(
    *,
    config: ProviderMarketDataImbalanceLiveDryrunHandoffConfig,
    handoff_id: str,
    plan_sha256: str,
    decision_root: Path,
    controls_path: Path,
    rollback_path: Path,
    proof_contract: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "settings": asdict(config),
        "handoff_id": handoff_id,
        "plan_sha256": plan_sha256,
        "release_decision_dir": str(decision_root),
        "runtime_controls_path": str(controls_path),
        "rollback_runbook_path": str(rollback_path),
        "proof_contract": proof_contract,
        "ready": True,
        "execution_enabled": False,
        "requires_separate_runtime_launcher": True,
        "release_approved": False,
        "dry_run_only": True,
        "submission_enabled": False,
        "broker_api_called": False,
        "authorizes_submission": False,
        "credential_values_stored": False,
    }


def _manifest_extra(
    *,
    handoff_id: str,
    plan_sha256: str,
    source: Mapping[str, Any],
    proof_contract: Mapping[str, Any],
) -> dict[str, Any]:
    decision_summary = source["decision_summary"]
    return {
        "passed": True,
        "ready": True,
        "handoff_id": handoff_id,
        "plan_sha256": plan_sha256,
        "decision_id": _text(decision_summary.get("decision_id")),
        "decision_sha256": _text(decision_summary.get("decision_sha256")),
        "release_decision_manifest_sha256": proof_contract["release_decision"]["manifest_sha256"],
        "runtime_controls_sha256": proof_contract["runtime_controls"]["sha256"],
        "rollback_runbook_sha256": proof_contract["rollback_runbook"]["sha256"],
        "strategy": _text(decision_summary.get("strategy")),
        "market": _text(decision_summary.get("market")),
        "target_mode": "live_dryrun",
        "execution_enabled": False,
        "requires_separate_runtime_launcher": True,
        "release_approved": False,
        "dry_run_only": True,
        "submission_enabled": False,
        "broker_api_called": False,
        "authorizes_submission": False,
        "credential_values_stored": False,
    }


def _runbook_markdown(
    summary: pd.Series,
    controls: Mapping[str, Any],
    proof_contract: Mapping[str, Any],
) -> str:
    kill_switch = _mapping(controls.get("kill_switch"))
    rollback = _mapping(controls.get("rollback"))
    return "\n".join(
        [
            "# Controlled Live-Dry-Run Handoff",
            "",
            "## Handoff State",
            "",
            f"- Handoff ID: `{summary['handoff_id']}`",
            f"- Strategy: `{summary['strategy']}`",
            f"- Market: `{summary['market']}`",
            f"- Provider: `{summary['provider']}`",
            f"- Session ID: `{summary['session_id']}`",
            f"- Trading date: `{summary['trading_date']}`",
            "- Execution enabled by this artifact: no",
            "- Broker submission enabled: no",
            "- Credential values stored: no",
            "",
            "## Limits",
            "",
            f"- Maximum orders: `{summary['max_orders_per_session']}`",
            f"- Maximum notional: `{summary['max_notional_per_session']}`",
            f"- Maximum open orders: `{summary['max_open_orders']}`",
            f"- Maximum position lots: `{summary['max_position_lots']}`",
            "",
            "## Safety Owners",
            "",
            f"- Kill-switch owner: `{_text(kill_switch.get('owner'))}`",
            f"- Rollback owner: `{_text(rollback.get('owner'))}`",
            f"- Rollback procedure: `{_text(rollback.get('procedure_id'))}`",
            "",
            "## Proofs",
            "",
            f"- Release decision: `{proof_contract['release_decision']['manifest_sha256']}`",
            f"- Runtime controls: `{proof_contract['runtime_controls']['sha256']}`",
            f"- Rollback runbook: `{proof_contract['rollback_runbook']['sha256']}`",
            f"- Rehearsal certificate: `{proof_contract['broker_rehearsal_certificate']['certificate_sha256']}`",
            "",
            "A separate runtime preflight and launcher are required. This handoff does not execute commands or call a broker API.",
            "",
        ]
    )


def _surfaces_non_authorizing(
    summary: pd.Series,
    plan: Mapping[str, Any],
    config: Mapping[str, Any],
    manifest_extra: Mapping[str, Any],
) -> bool:
    safety = _mapping(plan.get("safety"))
    surfaces: tuple[Mapping[str, Any] | pd.Series, ...] = (
        summary,
        safety,
        config,
        manifest_extra,
    )
    return bool(
        all(_explicit_false(surface, "submission_enabled") for surface in surfaces)
        and all(_explicit_false(surface, "broker_api_called") for surface in surfaces)
        and all(_explicit_false(surface, "authorizes_submission") for surface in surfaces)
        and all(_explicit_false(surface, "release_approved") for surface in (summary, config, manifest_extra))
        and all(_explicit_false(surface, "execution_enabled") for surface in (summary, safety, config, manifest_extra))
        and all(_explicit_false(surface, "credential_values_stored") for surface in surfaces)
        and all(_bool(surface.get("dry_run_only", False)) for surface in surfaces)
        and all(_bool(surface.get("requires_separate_runtime_launcher", False)) for surface in (summary, safety, config, manifest_extra))
    )


def _manifest_inputs_match(
    inputs: Mapping[str, Any],
    *,
    decision_root: Path,
    decision_manifest_path: Path,
    controls_path: Path,
    rollback_path: Path,
    recursive_dependencies: list[Path],
) -> bool:
    expected_names = {
        "release_decision",
        "release_decision_manifest",
        "runtime_controls",
        "rollback_runbook",
    }
    if recursive_dependencies:
        expected_names.add("release_decision_recursive_dependencies")
    if set(inputs) != expected_names:
        return False
    direct = {
        "release_decision": (decision_root, "directory"),
        "release_decision_manifest": (decision_manifest_path, "file"),
        "runtime_controls": (controls_path, "file"),
        "rollback_runbook": (rollback_path, "file"),
    }
    for name, (expected_path, expected_kind) in direct.items():
        record = _mapping(inputs.get(name))
        if record.get("kind") != expected_kind or not _text(record.get("path")):
            return False
        if Path(str(record["path"])).resolve() != expected_path:
            return False
    if recursive_dependencies:
        paths = _fingerprint_paths(inputs.get("release_decision_recursive_dependencies"))
        if (
            {path.resolve() for path in paths}
            != {path.resolve() for path in recursive_dependencies}
            or len(paths) != len(recursive_dependencies)
        ):
            return False
    return True


def _rollback_path(controls: Mapping[str, Any], controls_path: Path) -> Path:
    rollback = _mapping(controls.get("rollback"))
    raw = _text(rollback.get("runbook_path"))
    if not raw:
        return (controls_path.parent / "__missing_rollback_runbook__").resolve()
    path = Path(raw)
    if not path.is_absolute():
        path = controls_path.parent / path
    return path.resolve()


def _reject_output_collision(
    out: Path,
    *,
    decision_root: Path,
    controls_path: Path,
    rollback_path: Path,
) -> None:
    if out == decision_root or _is_relative_to(out, decision_root):
        raise ValueError("handoff output must be outside the release decision")
    for source in (controls_path, rollback_path):
        if source == out or _is_relative_to(source, out):
            raise ValueError("handoff source files must be outside output")


def _recursive_dependencies(
    decision_manifest_path: Path,
    direct_paths: set[Path],
) -> list[Path]:
    return _unique_paths(
        [
            path
            for path in manifest_dependency_paths(decision_manifest_path)
            if path.resolve() not in direct_paths
        ]
    )


def _input_file_current(path: Path, record: Mapping[str, Any]) -> bool:
    return bool(
        path.is_file()
        and _valid_sha256(record.get("sha256"))
        and file_sha256(path) == _text(record.get("sha256")).lower()
    )


def _forbidden_control_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            text = str(key).strip().lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if any(part in text for part in FORBIDDEN_CONTROL_KEY_PARTS):
                found.append(path)
            found.extend(_forbidden_control_keys(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_control_keys(item, f"{prefix}[{index}]"))
    return found


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


def _minutes(value: Any) -> int:
    text = _text(value)
    parts = text.split(":")
    if len(parts) != 2:
        return -1
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError:
        return -1
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return -1
    return hour * 60 + minute


def _date_valid(value: Any) -> bool:
    try:
        date.fromisoformat(_text(value))
    except ValueError:
        return False
    return True


def _validate_config(config: ProviderMarketDataImbalanceLiveDryrunHandoffConfig) -> None:
    if config.max_dependency_count <= 0:
        raise ValueError("max_dependency_count must be positive")


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
        try:
            numeric = float(raw)
            return not bool(np.isnan(numeric)) and numeric == 1.0
        except (TypeError, ValueError):
            return False
    return _text(raw).lower() in {"1", "true", "yes"}


def _explicit_false(value: Mapping[str, Any] | pd.Series, key: str) -> bool:
    if key not in value:
        return False
    raw = value.get(key)
    if isinstance(raw, (bool, np.bool_)):
        return not bool(raw)
    if isinstance(raw, (int, float, np.integer, np.floating)):
        try:
            numeric = float(raw)
            return not bool(np.isnan(numeric)) and numeric == 0.0
        except (TypeError, ValueError):
            return False
    return _text(raw).lower() in {"0", "false", "fail", "failed", "n", "no", "off"}


def _valid_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return bool(len(text) == 64 and all(character in "0123456789abcdef" for character in text))


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _unique_paths(paths: list[Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for path in paths:
        resolved = path.resolve()
        found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)]


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


def _normalize_strategy(value: Any) -> str:
    identity = _identity(value)
    return {
        "microprice_imbalance": "imbalance",
        "provider_market_data_imbalance": "imbalance",
    }.get(identity, identity)


def _integer(value: Any) -> int:
    if isinstance(value, (bool, np.bool_)):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if not np.isfinite(number) or not number.is_integer():
        return 0
    return int(number)


def _number(value: Any) -> float:
    if isinstance(value, (bool, np.bool_)):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if np.isfinite(number) else 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            return bool(float(value)) and not bool(np.isnan(float(value)))
        except (TypeError, ValueError):
            return False
    return _text(value).lower() in {"1", "true", "yes", "y", "pass", "passed"}


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
