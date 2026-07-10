from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.halt_response import HaltResponseConfig
from reports.manifest import write_experiment_manifest
from reports.runtime_session import RuntimeSessionMonitorReport, write_runtime_session_monitor


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_runtime_session"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRuntimeSessionConfig:
    require_provider_runtime_guard_ready: bool = True
    require_runtime_session_continue: bool = False
    require_halt_response_ready: bool = True
    use_provider_runtime_telemetry_inputs: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRuntimeSessionReport:
    session: RuntimeSessionMonitorReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])

    @property
    def halted(self) -> bool:
        if self.summary.empty:
            return True
        return bool(self.summary.iloc[0]["halted"])


def write_provider_market_data_imbalance_runtime_session(
    provider_runtime_guard_dir: str | Path,
    output_dir: str | Path,
    *,
    export_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    pnl_path: str | Path | None = None,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    snapshot_ts_ns: int | float | None = None,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
    plan_halt_response: bool = True,
    halt_response_config: HaltResponseConfig | None = None,
    config: ProviderMarketDataImbalanceRuntimeSessionConfig | None = None,
) -> ProviderMarketDataImbalanceRuntimeSessionReport:
    config = config or ProviderMarketDataImbalanceRuntimeSessionConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    guard_root = Path(provider_runtime_guard_dir)
    guard_summary, guard_summary_error = _read_csv(
        guard_root / "provider_market_data_imbalance_runtime_guard_summary.csv"
    )
    guard_config, guard_config_error = _read_json(
        guard_root / "provider_market_data_imbalance_runtime_guard_config.json"
    )
    guard_manifest, guard_manifest_error = _read_json(
        guard_root / "manifest.json"
    )
    telemetry_root = _first_existing_path(
        _path_from_text(_first_text(guard_summary, "provider_runtime_telemetry_dir")),
        _path_from_text(
            (guard_config.get("summary", {}) or {}).get("provider_runtime_telemetry_dir")
            if isinstance(guard_config, dict)
            else ""
        ),
    )
    telemetry_config, telemetry_config_error = _read_json(
        _path_or_empty(telemetry_root) / "provider_market_data_imbalance_runtime_telemetry_config.json"
    )
    inferred_inputs = _runtime_inputs(telemetry_config)
    scaleup_dir = _first_existing_path(
        _path_from_text(_first_text(guard_summary, "scaleup_dir")),
        _path_from_text(
            (guard_config.get("summary", {}) or {}).get("scaleup_dir") if isinstance(guard_config, dict) else ""
        ),
    )
    resolved_export_dir = _explicit_or_inferred(export_dir, inferred_inputs, "export_dir", config)
    resolved_upload_pack_dir = _explicit_or_inferred(upload_pack_dir, inferred_inputs, "upload_pack_dir", config)
    resolved_reconciliation_dir = _explicit_or_inferred(reconciliation_dir, inferred_inputs, "reconciliation_dir", config)
    resolved_instrument_metadata_dir = _explicit_or_inferred(
        instrument_metadata_dir,
        inferred_inputs,
        "instrument_metadata_dir",
        config,
    )
    resolved_pnl_path = _explicit_or_inferred(pnl_path, inferred_inputs, "pnl_path", config)
    resolved_open_orders_path = _explicit_or_inferred(open_orders_path, inferred_inputs, "open_orders_path", config)
    resolved_positions_path = _explicit_or_inferred(positions_path, inferred_inputs, "positions_path", config)
    resolved_snapshot_ts_ns = _first_number(snapshot_ts_ns, inferred_inputs.get("snapshot_ts_ns"))

    prechecks = _prechecks(
        guard_root,
        guard_summary,
        guard_summary_error,
        guard_config,
        guard_config_error,
        guard_manifest,
        guard_manifest_error,
        telemetry_root,
        telemetry_config_error,
        scaleup_dir,
        config,
    )
    session: RuntimeSessionMonitorReport | None = None
    session_error = ""
    session_dir = out / "runtime_session"
    if bool(prechecks["passed"].all()):
        try:
            session = write_runtime_session_monitor(
                scaleup_dir=_path_or_empty(scaleup_dir),
                output_dir=session_dir,
                export_dir=resolved_export_dir,
                upload_pack_dir=resolved_upload_pack_dir,
                reconciliation_dir=resolved_reconciliation_dir,
                instrument_metadata_dir=resolved_instrument_metadata_dir,
                pnl_path=resolved_pnl_path,
                open_orders_path=resolved_open_orders_path,
                positions_path=resolved_positions_path,
                snapshot_ts_ns=resolved_snapshot_ts_ns,
                as_of_ts_ns=as_of_ts_ns,
                max_telemetry_age_ns=max_telemetry_age_ns,
                plan_halt_response=plan_halt_response,
                halt_response_config=halt_response_config,
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            session_error = str(exc)
    else:
        session_error = "provider imbalance runtime session prerequisites are not ready"

    checks = _checks(prechecks, session, session_error, guard_summary, config)
    summary = _summary(
        guard_root,
        telemetry_root,
        scaleup_dir,
        session,
        checks,
        out,
        guard_summary,
        guard_config,
        guard_manifest,
    )
    action_queue = _action_queue(summary.iloc[0], checks, session)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        guard_summary,
        guard_config,
        guard_manifest,
        telemetry_config,
        session,
        checks,
        action_queue,
        config,
        {
            "export_dir": resolved_export_dir,
            "upload_pack_dir": resolved_upload_pack_dir,
            "reconciliation_dir": resolved_reconciliation_dir,
            "instrument_metadata_dir": resolved_instrument_metadata_dir,
            "pnl_path": resolved_pnl_path,
            "open_orders_path": resolved_open_orders_path,
            "positions_path": resolved_positions_path,
            "snapshot_ts_ns": resolved_snapshot_ts_ns,
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
            "plan_halt_response": plan_halt_response,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_runtime_session_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_runtime_session_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_runtime_session_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_runtime_session_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_runtime_session_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_runtime_guard_dir": guard_root}
    if telemetry_root is not None:
        inputs["provider_runtime_telemetry_dir"] = telemetry_root
    if scaleup_dir is not None:
        inputs["scaleup"] = scaleup_dir
    if session is not None and session.output_dir is not None:
        inputs["runtime_session"] = session.output_dir
    for name, value in {
        "export": resolved_export_dir,
        "upload_pack": resolved_upload_pack_dir,
        "reconciliation": resolved_reconciliation_dir,
        "instrument_metadata": resolved_instrument_metadata_dir,
        "pnl": resolved_pnl_path,
        "open_orders": resolved_open_orders_path,
        "positions": resolved_positions_path,
    }.items():
        if value is not None:
            inputs[name] = Path(value)

    summary_row = summary.iloc[0]
    capture_bundle = _path_from_text(summary_row["capture_bundle_path"])
    if capture_bundle is not None and capture_bundle.exists():
        inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(summary_row["capture_env_template_path"])
    if capture_env_template is not None and capture_env_template.exists():
        inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(summary_row["adapter_handoff_path"])
    if adapter_handoff is not None and adapter_handoff.exists():
        inputs["adapter_handoff"] = adapter_handoff
    source_env_template = _path_from_text(summary_row["source_credential_env_template_path"])
    if source_env_template is not None and source_env_template.exists():
        inputs["source_credential_env_template"] = source_env_template
    receipt_paths, capture_paths = _adapter_receipt_proof_paths(
        _mapping(guard_config.get("adapter_receipt_proof"))
    )
    if receipt_paths:
        inputs["adapter_receipts"] = receipt_paths
    if capture_paths:
        inputs["provider_captures"] = capture_paths

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "runtime_inputs": _jsonable(payload["runtime_inputs"]),
        },
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "halted": bool(summary_row["halted"]),
            "guard_action": str(summary_row["guard_action"]),
            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                summary_row["route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"]
            ),
            "profile": PROFILE,
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "provider_profile": _mapping(payload.get("provider_profile")),
            "adapter_receipt_proof": _mapping(payload.get("adapter_receipt_proof")),
            "provider_profile_matches_session": bool(summary_row["provider_profile_matches_session"]),
            "provider_profile_matches_bundle": bool(summary_row["provider_profile_matches_bundle"]),
            "capture_bundle_provided": bool(summary_row["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary_row["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary_row["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary_row["capture_env_template_path"]),
                "exists": bool(summary_row["capture_env_template_exists"]),
                "sha256": str(summary_row["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary_row["adapter_handoff_path"]),
                "exists": bool(summary_row["adapter_handoff_exists"]),
                "sha256": str(summary_row["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(summary_row["provider_capture_command_count"]),
            "provider_capture_command_providers": str(summary_row["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(summary_row["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                summary_row["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary_row["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary_row["capture_bundle_provider_capture_commands_match_session"]
            ),
            "adapter_execution_contract": _mapping(payload.get("adapter_execution_contract")),
            "adapter_contract_provider_profile_sha256": str(summary_row["adapter_contract_provider_profile_sha256"]),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary_row["adapter_contract_provider_profile_matches_evidence"]
            ),
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
                "provider_profile": _mapping(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_profile")
                ),
                "provider_capture_commands": _list(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(
                    summary_row["capture_bundle_provider_capture_command_count"]
                ),
                "provider_capture_commands_match_session": bool(
                    summary_row["capture_bundle_provider_capture_commands_match_session"]
                ),
                "adapter_execution_contract": _mapping(
                    _mapping(payload.get("capture_bundle")).get("adapter_execution_contract")
                ),
                "adapter_receipt_proof": _mapping(
                    payload.get("adapter_receipt_proof")
                ),
                "metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary_row["source_credential_env_template_path"]),
                "exists": bool(summary_row["source_credential_env_template_exists"]),
                "sha256": str(summary_row["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary_row["source_live_fetch_contract_available"]),
                "next_gate": str(summary_row["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary_row["source_live_fetch_contract_command_template"]),
                "exchange": str(summary_row["source_live_fetch_contract_exchange"]),
                "market": str(summary_row["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary_row),
            },
            "provider_capture_commands": _list(payload.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                payload.get("capture_bundle_provider_capture_commands")
            ),
            "synthetic_sidecar_proof": _mapping(payload.get("synthetic_sidecar_proof")),
            "synthetic_dataset_count": int(summary_row["synthetic_dataset_count"]),
            "synthetic_sidecar_proof_ready": bool(summary_row["synthetic_sidecar_proof_ready"]),
            "synthetic_sidecar_count": int(summary_row["synthetic_sidecar_count"]),
            "synthetic_sidecar_readable_count": int(summary_row["synthetic_sidecar_readable_count"]),
        },
    )
    return ProviderMarketDataImbalanceRuntimeSessionReport(session, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{path.name} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not readable: {exc}"
    return value if isinstance(value, dict) else {}, ""


def _runtime_inputs(telemetry_config: tuple[dict[str, Any], str] | dict[str, Any]) -> dict[str, Any]:
    payload = telemetry_config[0] if isinstance(telemetry_config, tuple) else telemetry_config
    if not isinstance(payload, dict):
        return {}
    inputs = payload.get("runtime_inputs", {}) or {}
    return inputs if isinstance(inputs, dict) else {}


def _prechecks(
    guard_root: Path,
    guard_summary: pd.DataFrame,
    guard_summary_error: str,
    guard_config: dict[str, Any],
    guard_config_error: str,
    guard_manifest: dict[str, Any],
    guard_manifest_error: str,
    telemetry_root: Path | None,
    telemetry_config_error: str,
    scaleup_dir: Path | None,
    config: ProviderMarketDataImbalanceRuntimeSessionConfig,
) -> pd.DataFrame:
    telemetry_config_ok = (not config.use_provider_runtime_telemetry_inputs) or not telemetry_config_error
    bundle_provided = _first_bool(guard_summary, "capture_bundle_provided")
    config_receipt_proof = _mapping(guard_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(guard_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_proofs_match = bool(
        config_receipt_proof
        and manifest_receipt_proof
        and config_receipt_proof == manifest_receipt_proof
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    return pd.DataFrame(
        [
            _check(
                "provider_runtime_guard_dir_exists",
                str(guard_root),
                "exists",
                True,
                guard_root.exists(),
                "provider imbalance runtime guard directory is required",
            ),
            _check(
                "provider_runtime_guard_summary_readable",
                guard_summary_error or "ok",
                "is",
                "ok",
                not guard_summary_error,
                guard_summary_error or "provider imbalance runtime guard summary could not be read",
            ),
            _check(
                "provider_runtime_guard_config_readable",
                guard_config_error or "ok",
                "is",
                "ok",
                not guard_config_error,
                guard_config_error or "provider imbalance runtime guard config could not be read",
            ),
            _check(
                "provider_runtime_guard_manifest_readable",
                guard_manifest_error or "ok",
                "is",
                "ok",
                not guard_manifest_error,
                guard_manifest_error or "provider imbalance runtime guard manifest could not be read",
            ),
            _check(
                "provider_runtime_guard_manifest_type",
                _clean(guard_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_runtime_guard",
                _clean(guard_manifest.get("run_type"))
                == "provider_market_data_imbalance_runtime_guard",
                "provider imbalance runtime guard manifest run_type is not expected",
            ),
            _check(
                "provider_runtime_guard_ready",
                _first_bool(guard_summary, "ready"),
                "is",
                True,
                _first_bool(guard_summary, "ready") or not config.require_provider_runtime_guard_ready,
                "provider imbalance runtime guard is not ready",
            ),
            _check(
                "provider_runtime_guard_adapter_receipt_proof_carried",
                bool(config_receipt_proof),
                "is",
                True,
                bool(config_receipt_proof)
                and _truthy(config_receipt_proof.get("ready"))
                if bundle_provided
                else True,
                "provider imbalance runtime guard is missing ready adapter receipt proof",
            ),
            _check(
                "provider_runtime_guard_adapter_receipt_proof_matches_manifest",
                receipt_proofs_match,
                "is",
                True,
                receipt_proofs_match if bundle_provided else True,
                "adapter receipt proof differs between runtime guard config and manifest",
            ),
            _check(
                "provider_runtime_guard_adapter_receipts_valid",
                receipt_status["valid_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["valid_count"] == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider imbalance runtime guard did not preserve valid required adapter receipts",
            ),
            _check(
                "provider_runtime_guard_adapter_receipt_fingerprints_current",
                receipt_status["receipt_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["receipt_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "adapter receipt files changed after provider runtime guard evaluation",
            ),
            _check(
                "provider_runtime_guard_capture_fingerprints_current",
                receipt_status["capture_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["capture_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider capture files changed after provider runtime guard evaluation",
            ),
            _check(
                "provider_runtime_telemetry_config_readable",
                telemetry_config_error or "ok",
                "is",
                "ok",
                telemetry_config_ok,
                telemetry_config_error or "provider runtime telemetry config could not be read",
            ),
            _check(
                "provider_runtime_telemetry_dir_exists",
                _path_text(telemetry_root),
                "exists",
                True,
                bool(telemetry_root and telemetry_root.exists()),
                "provider runtime telemetry directory is required for inferred runtime inputs",
            ),
            _check(
                "nested_scaleup_config_exists",
                _path_text(scaleup_dir),
                "exists",
                True,
                bool(scaleup_dir and (scaleup_dir / "scaleup_config.json").exists()),
                "nested scaleup_config.json is required for runtime session",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    session: RuntimeSessionMonitorReport | None,
    session_error: str,
    guard_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeSessionConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    session_summary = session.summary if session is not None else pd.DataFrame()
    session_halted = _first_bool(session_summary, "halted")
    halt_response_ready = _first_bool(session_summary, "halt_response_ready")
    bundle_provided = _first_bool(guard_summary, "capture_bundle_provided")
    provider_capture_command_count = int(
        _first_number(_first_text(guard_summary, "provider_capture_command_count")) or 0
    )
    bundle_provider_capture_command_count = int(
        _first_number(_first_text(guard_summary, "capture_bundle_provider_capture_command_count")) or 0
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(_first_text(guard_summary, "capture_bundle_provider_capture_command_missing_count")) or 0
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(guard_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    adapter_contract_carried = _adapter_contract_carried(guard_summary)
    provider_profile_carried = _provider_profile_carried(guard_summary)
    synthetic_dataset_count = int(_first_number(_first_text(guard_summary, "synthetic_dataset_count")) or 0)
    synthetic_sidecar_count = int(_first_number(_first_text(guard_summary, "synthetic_sidecar_count")) or 0)
    synthetic_sidecar_proof_required = synthetic_dataset_count > 0
    synthetic_sidecar_proof_ready = _first_bool(guard_summary, "synthetic_sidecar_proof_ready")
    synthetic_sidecar_count_matches = synthetic_sidecar_count == synthetic_dataset_count
    route_sidecar_breach_pairs = int(
        _first_number(
            _first_text(
                guard_summary,
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
            )
        )
        or 0
    )
    route_sidecar_gate_active = (
        _first_bool(guard_summary, "route_readiness_provided")
        or _first_bool(guard_summary, "route_readiness_ops_launch_controls_present")
        or route_sidecar_breach_pairs > 0
    )
    rows.append(
        _check(
            "runtime_session_runnable",
            session_error or ("ran" if session is not None else "not_run"),
            "is",
            "ran",
            session is not None and not session_error,
            session_error or "generic runtime session monitor was not run",
        )
    )
    rows.append(
        _check(
            "runtime_session_evaluated",
            bool(session is not None and not session_summary.empty),
            "is",
            True,
            bool(session is not None and not session_summary.empty),
            "generic runtime session did not write a summary",
        )
    )
    rows.append(
        _check(
            "runtime_session_continue",
            not session_halted,
            "is",
            True,
            bool(session is not None and ((not session_halted) or not config.require_runtime_session_continue)),
            "runtime session guard halted routing",
        )
    )
    rows.append(
        _check(
            "runtime_session_halt_response_ready",
            halt_response_ready,
            "is",
            True,
            bool(
                session is not None
                and ((not session_halted) or halt_response_ready or not config.require_halt_response_ready)
            ),
            "runtime session halted but did not produce a ready halt response",
        )
    )
    strategy = _first_text(session_summary, "strategy") or _first_text(guard_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            _identity_key(strategy) == PROFILE,
            "runtime session did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(guard_summary, "market")
    session_market = _first_text(session_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            session_market or expected_market,
            "is",
            expected_market or "present",
            bool(session_market)
            and (not expected_market or _identity_key(session_market) == _identity_key(expected_market)),
            "runtime session market identity does not match provider guard",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_provider_capture_commands_carried",
            bundle_provider_capture_command_count,
            "==",
            provider_capture_command_count,
            bundle_provider_capture_commands_carried if bundle_provided else True,
            "provider imbalance runtime guard is missing capture-bundle provider command proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_provider_capture_commands_match_session",
            bundle_provider_capture_command_count,
            "matches",
            provider_capture_command_count,
            bundle_provider_capture_commands_match_session if bundle_provided else True,
            "provider imbalance runtime guard command proof no longer matches the session packet",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_adapter_execution_contract_carried",
            _adapter_contract_metadata_text(guard_summary),
            "is_not",
            "",
            adapter_contract_carried if bundle_provided else True,
            "provider imbalance runtime guard is missing credential-safe adapter execution contract proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_adapter_execution_contract_matches_evidence",
            _adapter_contract_metadata_text(guard_summary),
            "matches",
            "live evidence",
            _first_bool(guard_summary, "adapter_contract_metadata_matches_evidence") if bundle_provided else True,
            "provider imbalance runtime guard adapter execution contract no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_provider_profile_carried",
            _first_text(guard_summary, "provider_profile_sha256"),
            "has",
            "provider profile",
            provider_profile_carried,
            "provider imbalance runtime guard is missing provider-profile proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_provider_profile_matches_session",
            _first_text(guard_summary, "provider_profile_sha256"),
            "matches",
            "live session",
            _first_bool(guard_summary, "provider_profile_matches_session"),
            "provider imbalance runtime guard provider-profile proof no longer matches the live session packet",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_provider_profile_matches_bundle",
            _first_text(guard_summary, "capture_bundle_provider_profile_sha256"),
            "matches",
            _first_text(guard_summary, "provider_profile_sha256"),
            _first_bool(guard_summary, "provider_profile_matches_bundle") if bundle_provided else True,
            "provider imbalance runtime guard provider-profile proof no longer matches the capture bundle",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_adapter_provider_profile_matches_evidence",
            _first_text(guard_summary, "adapter_contract_provider_profile_sha256"),
            "==",
            _first_text(guard_summary, "provider_profile_sha256"),
            _first_bool(guard_summary, "adapter_contract_provider_profile_matches_evidence")
            if bundle_provided
            else True,
            "provider imbalance runtime guard adapter contract provider-profile SHA no longer matches live evidence",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_synthetic_sidecar_proof_carried",
            synthetic_sidecar_count,
            "==",
            synthetic_dataset_count,
            synthetic_sidecar_count_matches if synthetic_sidecar_proof_required else True,
            "provider imbalance runtime guard synthetic folds are missing rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_synthetic_sidecar_proof_ready",
            synthetic_sidecar_proof_ready,
            "is",
            True,
            synthetic_sidecar_proof_ready if synthetic_sidecar_proof_required else True,
            "provider imbalance runtime guard synthetic folds require ready rehearsal sidecar proof",
        )
    )
    rows.append(
        _check(
            "provider_runtime_guard_route_readiness_provider_sidecar_breach_pairs",
            route_sidecar_breach_pairs,
            "<=",
            0,
            route_sidecar_breach_pairs <= 0 if route_sidecar_gate_active else True,
            "provider runtime guard carries breached route-readiness broker round-trip synthetic sidecar proof",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    guard_root: Path,
    telemetry_root: Path | None,
    scaleup_dir: Path | None,
    session: RuntimeSessionMonitorReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    guard_summary: pd.DataFrame,
    guard_config: dict[str, Any],
    guard_manifest: dict[str, Any],
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    session_summary = session.summary if session is not None else pd.DataFrame()
    halted = True if session is None else _first_bool(session_summary, "halted")
    guard_action = _first_text(session_summary, "guard_action") or ("halt" if halted else "continue")
    config_receipt_proof = _mapping(guard_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(guard_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_runtime_guard_ready": _first_bool(guard_summary, "ready"),
                "runtime_session_ready": bool(session.ready) if session is not None else False,
                "runtime_session_evaluated": session is not None and not session_summary.empty,
                "runtime_session_continue": bool(session is not None and not halted),
                "halted": halted,
                "guard_action": guard_action,
                "halt_response_created": _first_bool(session_summary, "halt_response_created"),
                "halt_response_ready": _first_bool(session_summary, "halt_response_ready"),
                "provider_runtime_guard_dir": str(guard_root),
                "provider_runtime_telemetry_dir": _path_text(telemetry_root),
                "scaleup_dir": _path_text(scaleup_dir),
                "exchange": _first_text(guard_summary, "exchange"),
                "source_session_timezone": _first_text(guard_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(guard_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(guard_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(guard_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(guard_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(guard_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(guard_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(guard_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(guard_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(guard_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(guard_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    guard_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    guard_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    guard_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    guard_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    guard_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    guard_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    guard_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    guard_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(guard_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(guard_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(guard_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(guard_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(guard_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(guard_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(guard_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(guard_summary, "adapter_handoff_sha256"),
                "provider_runtime_guard_manifest_run_type": _clean(
                    guard_manifest.get("run_type")
                ),
                "adapter_receipt_proof_ready": bool(receipt_status["ready"]),
                "adapter_receipt_proof_matches_manifest": bool(
                    config_receipt_proof
                    and manifest_receipt_proof
                    and config_receipt_proof == manifest_receipt_proof
                ),
                "adapter_receipts_required": _truthy(
                    config_receipt_proof.get("required")
                ),
                "adapter_receipt_required_count": int(
                    receipt_status["required_count"]
                ),
                "adapter_receipt_valid_count": int(receipt_status["valid_count"]),
                "adapter_receipt_fingerprint_match_count": int(
                    receipt_status["receipt_fingerprint_match_count"]
                ),
                "capture_fingerprint_match_count": int(
                    receipt_status["capture_fingerprint_match_count"]
                ),
                "source_credential_env_template_path": _first_text(
                    guard_summary, "source_credential_env_template_path"
                ),
                "source_credential_env_template_exists": _first_bool(
                    guard_summary, "source_credential_env_template_exists"
                ),
                "source_credential_env_template_sha256": _first_text(
                    guard_summary, "source_credential_env_template_sha256"
                ),
                "source_live_fetch_contract_available": _first_bool(
                    guard_summary, "source_live_fetch_contract_available"
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    guard_summary, "source_live_fetch_contract_next_gate"
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    guard_summary, "source_live_fetch_contract_command_template"
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    guard_summary, "source_live_fetch_contract_exchange"
                ),
                "source_live_fetch_contract_market": _first_text(
                    guard_summary, "source_live_fetch_contract_market"
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    guard_summary, "source_live_fetch_contract_session_timezone"
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    guard_summary, "source_live_fetch_contract_session_open_local"
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    guard_summary, "source_live_fetch_contract_session_close_local"
                ),
                "adapter_contract_provider": _first_text(guard_summary, "adapter_contract_provider"),
                "adapter_contract_transport": _first_text(guard_summary, "adapter_contract_transport"),
                "adapter_contract_market": _first_text(guard_summary, "adapter_contract_market"),
                "adapter_contract_exchange": _first_text(guard_summary, "adapter_contract_exchange"),
                "adapter_contract_values_stored": _first_bool(guard_summary, "adapter_contract_values_stored"),
                "adapter_contract_metadata_matches_evidence": _first_bool(
                    guard_summary, "adapter_contract_metadata_matches_evidence"
                ),
                "provider_profile_sha256": _first_text(guard_summary, "provider_profile_sha256"),
                "provider_profile_adapter": _first_text(guard_summary, "provider_profile_adapter"),
                "provider_profile_auth_required": _first_bool(guard_summary, "provider_profile_auth_required"),
                "provider_profile_transports": _first_text(guard_summary, "provider_profile_transports"),
                "provider_profile_capabilities": _first_text(guard_summary, "provider_profile_capabilities"),
                "capture_bundle_provider_profile_sha256": _first_text(
                    guard_summary, "capture_bundle_provider_profile_sha256"
                ),
                "provider_profile_matches_session": _first_bool(guard_summary, "provider_profile_matches_session"),
                "provider_profile_matches_bundle": _first_bool(guard_summary, "provider_profile_matches_bundle")
                if _first_bool(guard_summary, "capture_bundle_provided")
                else True,
                "adapter_contract_provider_profile_sha256": _first_text(
                    guard_summary, "adapter_contract_provider_profile_sha256"
                ),
                "adapter_contract_provider_profile_matches_evidence": _first_bool(
                    guard_summary, "adapter_contract_provider_profile_matches_evidence"
                ),
                "provider_capture_command_count": int(
                    _first_number(_first_text(guard_summary, "provider_capture_command_count")) or 0
                ),
                "provider_capture_command_providers": _first_text(
                    guard_summary, "provider_capture_command_providers"
                ),
                "provider_capture_command_transports": _first_text(
                    guard_summary, "provider_capture_command_transports"
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(_first_text(guard_summary, "capture_bundle_provider_capture_command_count")) or 0
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(
                        _first_text(guard_summary, "capture_bundle_provider_capture_command_missing_count")
                    )
                    or 0
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    guard_summary, "capture_bundle_provider_capture_commands_match_session"
                )
                if _first_bool(guard_summary, "capture_bundle_provided")
                else True,
                "synthetic_dataset_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_dataset_count")) or 0
                ),
                "synthetic_sidecar_proof_ready": _first_bool(guard_summary, "synthetic_sidecar_proof_ready"),
                "synthetic_sidecar_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_count")) or 0
                ),
                "synthetic_sidecar_readable_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_readable_count")) or 0
                ),
                "synthetic_sidecar_source_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_source_count")) or 0
                ),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_adapter_command_hash_count")) or 0
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_capture_env_template_match_count")) or 0
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_adapter_handoff_match_count")) or 0
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_source_env_template_match_count")) or 0
                ),
                "synthetic_sidecar_live_fetch_contract_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_live_fetch_contract_count")) or 0
                ),
                "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_adapter_execution_contract_safe_count"))
                    or 0
                ),
                "synthetic_sidecar_invariant_count": int(
                    _first_number(_first_text(guard_summary, "synthetic_sidecar_invariant_count")) or 0
                ),
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _first_number(
                        _first_text(
                            guard_summary,
                            "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                        )
                    )
                    or 0
                ),
                "runtime_session_dir": "" if session is None else str(session.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(guard_summary, "provider"),
                "transport": _first_text(guard_summary, "transport"),
                "market": _first_text(session_summary, "market") or _first_text(guard_summary, "market"),
                "strategy": _first_text(session_summary, "strategy") or _first_text(guard_summary, "strategy") or PROFILE,
                "target_mode": _first_text(session_summary, "target_mode") or _first_text(guard_summary, "target_mode"),
                "adapter": _first_text(session_summary, "adapter") or _first_text(guard_summary, "adapter"),
                "scenario_key": _first_text(session_summary, "scenario_key")
                or _first_text(guard_summary, "scenario_key"),
                "orders_sent": _first_number(_first_text(session_summary, "orders_sent")),
                "session_notional": _first_number(_first_text(session_summary, "session_notional")),
                "runtime_session_failed_checks": _first_number(
                    _first_text(session_summary, "failed_check_count")
                ),
                "runtime_session_failed_check_names": _first_text(session_summary, "failed_check_names"),
                "runtime_session_primary_blocker": _first_text(session_summary, "primary_blocker_check"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": _recommendation(ready, halted, _first_bool(session_summary, "halt_response_ready")),
                "next_gate": _ready_next_gate(session) if ready else _blocked_next_gate(checks, session),
                "next_gate_help_command": _help_command_for_gate(
                    _ready_next_gate(session) if ready else _blocked_next_gate(checks, session)
                ),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    if not action_queue.empty:
        out["primary_action_status"] = str(action_queue.iloc[0].get("queue_status", ""))
        out["next_gate"] = str(action_queue.iloc[0].get("next_gate", out.iloc[0].get("next_gate", "")))
        out["next_gate_help_command"] = str(
            action_queue.iloc[0].get("next_gate_help_command", out.iloc[0].get("next_gate_help_command", ""))
        )
    return out


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    session: RuntimeSessionMonitorReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty and session is not None and not _first_bool(session.summary, "halted"):
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_runtime_session_summary",
                    "component": "runtime_session",
                    "check": "runtime_session_continue",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "review_provider_imbalance_broker_readiness",
                    "reason": "provider imbalance runtime session is clean for broker readiness review",
                    "recommendation": "feed_runtime_session_into_broker_readiness",
                    "next_gate": "review-provider-market-data-imbalance-broker-readiness",
                    "next_gate_help_command": _help_command_for_gate(
                        "review-provider-market-data-imbalance-broker-readiness"
                    ),
                }
            ]
        )
    if failed.empty and session is not None:
        return _session_halt_actions(session)
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, session)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_runtime_session_checks",
                "component": _component_for_check(name),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": _action_for_check(name),
                "reason": str(check.get("reason", "")) or name.replace("_", " "),
                "recommendation": _recommendation_for_check(name),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_runtime_session_checks",
                "component": "runtime_session",
                "check": "provider_runtime_session_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_runtime_session",
                "reason": "provider imbalance runtime session is not ready",
                "recommendation": "rerun_provider_imbalance_runtime_session",
                "next_gate": "monitor-provider-market-data-imbalance-runtime-session",
                "next_gate_help_command": _help_command_for_gate(
                    "monitor-provider-market-data-imbalance-runtime-session"
                ),
            }
        )
    return _action_frame(rows)


def _session_halt_actions(session: RuntimeSessionMonitorReport) -> pd.DataFrame:
    session_queue = session.action_queue if session.action_queue is not None else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    if session_queue.empty:
        rows.append(
            {
                "queue_status": "ready",
                "source": "runtime_session_summary",
                "component": "halt_response",
                "check": "guard_halted",
                "actual": "halt",
                "operator": "is",
                "expected": "continue",
                "action": "export_provider_imbalance_halt_response",
                "reason": "runtime session halted routing",
                "recommendation": "export_and_execute_halt_response_packet",
                "next_gate": "export-halt-response",
                "next_gate_help_command": _help_command_for_gate("export-halt-response"),
            }
        )
    for item in session_queue.to_dict(orient="records"):
        next_gate = str(item.get("next_gate") or "export-halt-response")
        rows.append(
            {
                "queue_status": str(item.get("queue_status") or "ready"),
                "source": "runtime_session_action_queue",
                "component": str(item.get("component") or "runtime_session"),
                "check": str(item.get("check") or "guard_halted"),
                "actual": item.get("actual"),
                "operator": item.get("operator"),
                "expected": item.get("expected"),
                "action": "export_provider_imbalance_halt_response"
                if next_gate == "export-halt-response"
                else "repair_provider_imbalance_runtime_session",
                "reason": str(item.get("reason") or "runtime session halted routing"),
                "recommendation": str(item.get("recommendation") or "export_and_execute_halt_response_packet"),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    guard_summary: pd.DataFrame,
    guard_config: dict[str, Any],
    guard_manifest: dict[str, Any],
    telemetry_config: dict[str, Any],
    session: RuntimeSessionMonitorReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceRuntimeSessionConfig,
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "halted": bool(summary["halted"]),
        "guard_action": str(summary["guard_action"]),
        "parameters": asdict(config),
        "runtime_inputs": _jsonable(runtime_inputs),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(guard_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(guard_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(guard_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(guard_config),
        "adapter_execution_contract": _mapping(guard_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            guard_config.get("adapter_receipt_proof")
        ),
        "synthetic_sidecar_proof": _mapping(guard_config.get("synthetic_sidecar_proof")),
        "capture_bundle": _provider_capture_bundle(summary, guard_config),
        "provider_runtime_guard": _first_record(guard_summary),
        "provider_runtime_guard_config": _jsonable(guard_config),
        "provider_runtime_guard_manifest_run_type": _clean(
            guard_manifest.get("run_type")
        ),
        "provider_runtime_telemetry_config": _jsonable(telemetry_config),
        "runtime_session": {
            "evaluated": session is not None,
            "ready": False if session is None else bool(session.ready),
            "halted": True if session is None else _first_bool(session.summary, "halted"),
            "output_dir": "" if session is None else str(session.output_dir or ""),
            "summary": _first_record(None if session is None else session.summary),
            "steps": _records(None if session is None else session.steps),
            "action_queue": _records(None if session is None else session.action_queue),
            "config": {} if session is None or session.config is None else session.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Runtime Session",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Halted: {'yes' if bool(summary['halted']) else 'no'}",
        f"- Guard action: {summary['guard_action']}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Target mode: {summary['target_mode']}",
        f"- Runtime session dir: {summary['runtime_session_dir']}",
        f"- Primary next gate: `{summary['next_gate']}`",
        f"- Primary next gate help: `{summary['next_gate_help_command']}`",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Adapter execution contract: {summary['adapter_contract_provider'] or 'missing'} / {summary['adapter_contract_transport'] or 'missing'} (evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Adapter receipt proof: {'ready' if bool(summary['adapter_receipt_proof_ready']) else 'blocked'} ({summary['adapter_receipt_fingerprint_match_count']}/{summary['adapter_receipt_required_count']} sealed; guard manifest match: {'yes' if bool(summary['adapter_receipt_proof_matches_manifest']) else 'no'})",
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
        f"- Route sidecar breach pairs: {summary['route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs']}",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _action_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _recommendation(ready: bool, halted: bool, halt_response_ready: bool) -> str:
    if halted and halt_response_ready:
        return "export_provider_imbalance_halt_response"
    if halted:
        return "repair_provider_imbalance_halt_response"
    if ready:
        return "review_provider_imbalance_broker_readiness"
    return "repair_provider_imbalance_runtime_session"


def _ready_next_gate(session: RuntimeSessionMonitorReport | None) -> str:
    if session is None:
        return "monitor-provider-market-data-imbalance-runtime-session"
    if _first_bool(session.summary, "halted"):
        return _first_action_value(session.action_queue, "next_gate") or "export-halt-response"
    return "review-provider-market-data-imbalance-broker-readiness"


def _blocked_next_gate(checks: pd.DataFrame, session: RuntimeSessionMonitorReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return _ready_next_gate(session)
    return _next_gate_for_check(failed[0], session)


def _next_gate_for_check(check: str, session: RuntimeSessionMonitorReport | None) -> str:
    if check.startswith("provider_runtime_guard_route_readiness_provider_sidecar"):
        return "review-provider-market-data-imbalance-route-readiness"
    if check.startswith("provider_runtime_guard"):
        return "monitor-provider-market-data-imbalance-runtime-guard"
    if check.startswith("provider_runtime_telemetry"):
        return "build-provider-market-data-imbalance-runtime-telemetry"
    if check == "nested_scaleup_config_exists":
        return "plan-provider-market-data-imbalance-scaleup"
    if check in {"runtime_session_runnable", "runtime_session_evaluated"}:
        return "monitor-runtime-session"
    if check == "runtime_session_halt_response_ready":
        return _first_action_value(None if session is None else session.action_queue, "next_gate") or "plan-halt-response"
    if check in {"runtime_session_continue", "strategy_identity_imbalance", "market_identity_consistent"}:
        return "monitor-provider-market-data-imbalance-runtime-session"
    return "monitor-provider-market-data-imbalance-runtime-session"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    if next_gate == "monitor-provider-market-data-imbalance-runtime-guard":
        return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-guard --help"
    if next_gate == "build-provider-market-data-imbalance-runtime-telemetry":
        return "python -m hft_cli build-provider-market-data-imbalance-runtime-telemetry --help"
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "monitor-runtime-session":
        return "python -m hft_cli monitor-runtime-session --help"
    if next_gate == "plan-halt-response":
        return "python -m hft_cli plan-halt-response --help"
    if next_gate == "export-halt-response":
        return "python -m hft_cli export-halt-response --help"
    if next_gate == "review-provider-market-data-imbalance-broker-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-readiness --help"
    return "python -m hft_cli monitor-provider-market-data-imbalance-runtime-session --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_runtime_guard_route_readiness_provider_sidecar"):
        return "provider_route_readiness"
    if check.startswith("provider_runtime_guard"):
        return "provider_runtime_guard"
    if check.startswith("provider_runtime_telemetry"):
        return "provider_runtime_telemetry"
    if check.startswith("nested_scaleup"):
        return "scaleup_plan"
    if check.startswith("runtime_session"):
        return "runtime_session"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_runtime_session"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_runtime_guard_route_readiness_provider_sidecar"):
        return "review_provider_imbalance_route_readiness"
    if check.startswith("provider_runtime_guard"):
        return "repair_provider_imbalance_runtime_guard"
    if check.startswith("provider_runtime_telemetry"):
        return "repair_provider_imbalance_runtime_telemetry"
    if check.startswith("nested_scaleup"):
        return "rebuild_provider_imbalance_scaleup"
    if check == "runtime_session_halt_response_ready":
        return "repair_provider_imbalance_halt_response"
    if check.startswith("runtime_session"):
        return "repair_provider_imbalance_runtime_session"
    return "repair_provider_imbalance_runtime_session"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_runtime_guard_route_readiness_provider_sidecar"):
        return "review_provider_route_readiness_sidecar_proof_before_session"
    if check.startswith("provider_runtime_guard"):
        return "rerun_provider_runtime_guard_before_session"
    if check.startswith("provider_runtime_telemetry"):
        return "rebuild_provider_runtime_telemetry_before_session"
    if check.startswith("nested_scaleup"):
        return "rebuild_provider_scaleup_before_session"
    if check == "runtime_session_halt_response_ready":
        return "repair_halt_response_inputs_before_export"
    if check.startswith("runtime_session"):
        return "rerun_runtime_session_with_valid_inputs"
    return "repair_provider_runtime_session_inputs"


def _first_action_value(action_queue: pd.DataFrame | None, column: str) -> str:
    if action_queue is None or action_queue.empty or column not in action_queue.columns:
        return ""
    for value in action_queue[column].tolist():
        text = _clean(value)
        if text:
            return text
    return ""


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred_inputs: dict[str, Any],
    key: str,
    config: ProviderMarketDataImbalanceRuntimeSessionConfig,
) -> str | Path | None:
    if explicit is not None:
        return explicit
    if not config.use_provider_runtime_telemetry_inputs:
        return None
    text = _clean(inferred_inputs.get(key))
    return text or None


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    return Path(text)


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _path_or_empty(path: Path | None) -> Path:
    return Path("") if path is None else path


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["market_session_timezone"]),
        "open_local": str(summary["market_session_open_local"]),
        "close_local": str(summary["market_session_close_local"]),
    }


def _capture_bundle_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_source_session_timezone"]),
        "open_local": str(summary["capture_bundle_source_session_open_local"]),
        "close_local": str(summary["capture_bundle_source_session_close_local"]),
    }


def _capture_bundle_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_market_session_timezone"]),
        "open_local": str(summary["capture_bundle_market_session_open_local"]),
        "close_local": str(summary["capture_bundle_market_session_close_local"]),
    }


def _source_live_fetch_contract_session_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["source_live_fetch_contract_session_close_local"]),
    }


def _adapter_contract_carried(guard_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(guard_summary, "adapter_contract_provider"))
        and bool(_first_text(guard_summary, "adapter_contract_transport"))
        and bool(_first_text(guard_summary, "adapter_contract_market"))
        and bool(_first_text(guard_summary, "adapter_contract_exchange"))
        and not _first_bool(guard_summary, "adapter_contract_values_stored")
    )


def _provider_profile_carried(guard_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(guard_summary, "provider_profile_sha256"))
        and bool(_first_text(guard_summary, "provider_profile_adapter"))
        and bool(_first_text(guard_summary, "provider_profile_transports"))
    )


def _adapter_contract_metadata_text(guard_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(guard_summary, 'adapter_contract_provider')}|"
        f"{_first_text(guard_summary, 'adapter_contract_transport')}|"
        f"{_first_text(guard_summary, 'adapter_contract_market')}|"
        f"{_first_text(guard_summary, 'adapter_contract_exchange')}"
    )


def _provider_capture_bundle(summary: pd.Series, guard_config: dict[str, Any]) -> dict[str, Any]:
    commands = _bundle_provider_capture_commands(guard_config)
    payload = _mapping(guard_config.get("capture_bundle"))
    if payload:
        carried = {str(key): _jsonable(value) for key, value in payload.items()}
        carried.setdefault("adapter_execution_contract", _mapping(guard_config.get("adapter_execution_contract")))
        carried.setdefault(
            "adapter_receipt_proof",
            _mapping(guard_config.get("adapter_receipt_proof")),
        )
        carried.setdefault("provider_profile", _mapping(guard_config.get("provider_profile")))
        carried.setdefault(
            "live_session_provider_profile",
            _mapping(guard_config.get("live_session_provider_profile")),
        )
        carried.setdefault("capture_bundle_provider_profile", _mapping(payload.get("capture_bundle_provider_profile")))
        carried.setdefault("adapter_contract_provider", str(summary["adapter_contract_provider"]))
        carried.setdefault("adapter_contract_transport", str(summary["adapter_contract_transport"]))
        carried.setdefault("adapter_contract_market", str(summary["adapter_contract_market"]))
        carried.setdefault("adapter_contract_exchange", str(summary["adapter_contract_exchange"]))
        carried.setdefault("adapter_contract_values_stored", bool(summary["adapter_contract_values_stored"]))
        carried.setdefault(
            "adapter_contract_metadata_matches_evidence",
            bool(summary["adapter_contract_metadata_matches_evidence"]),
        )
        carried.setdefault("provider_profile_sha256", str(summary["provider_profile_sha256"]))
        carried.setdefault("provider_profile_matches_session", bool(summary["provider_profile_matches_session"]))
        carried.setdefault("provider_profile_matches_bundle", bool(summary["provider_profile_matches_bundle"]))
        carried.setdefault(
            "adapter_contract_provider_profile_sha256",
            str(summary["adapter_contract_provider_profile_sha256"]),
        )
        carried.setdefault(
            "adapter_contract_provider_profile_matches_evidence",
            bool(summary["adapter_contract_provider_profile_matches_evidence"]),
        )
        carried.setdefault("provider_capture_command_count", int(summary["provider_capture_command_count"]))
        carried.setdefault(
            "provider_capture_command_providers",
            str(summary["provider_capture_command_providers"]),
        )
        carried.setdefault(
            "provider_capture_command_transports",
            str(summary["provider_capture_command_transports"]),
        )
        carried.setdefault(
            "capture_bundle_provider_capture_command_count",
            int(summary["capture_bundle_provider_capture_command_count"]),
        )
        carried.setdefault(
            "capture_bundle_provider_capture_command_missing_count",
            int(summary["capture_bundle_provider_capture_command_missing_count"]),
        )
        carried.setdefault(
            "capture_bundle_provider_capture_commands_match_session",
            bool(summary["capture_bundle_provider_capture_commands_match_session"]),
        )
        carried.setdefault("metadata_matches_session", bool(summary["capture_bundle_metadata_matches_session"]))
        carried.setdefault(
            "live_fetch_contract_metadata_matches_session",
            bool(summary["capture_bundle_live_fetch_contract_metadata_matches_session"]),
        )
        carried.setdefault("provider_capture_commands", commands)
        carried.setdefault("capture_bundle_provider_capture_commands", commands)
        return carried
    return {
        "capture_bundle_path": str(summary["capture_bundle_path"]),
        "capture_bundle_provided": bool(summary["capture_bundle_provided"]),
        "capture_bundle_exists": bool(summary["capture_bundle_exists"]),
        "capture_bundle_ready": bool(summary["capture_bundle_ready"]),
        "exchange": str(summary["capture_bundle_exchange"]),
        "source_session": _capture_bundle_source_session_contract_from_summary(summary),
        "market_session": _capture_bundle_market_session_contract_from_summary(summary),
        "capture_bundle_metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
        "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
            summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
        ),
        "metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
        "live_fetch_contract_metadata_matches_session": bool(
            summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
        ),
        "capture_env_template_path": str(summary["capture_env_template_path"]),
        "capture_env_template_provided": bool(summary["capture_env_template_provided"]),
        "capture_env_template_exists": bool(summary["capture_env_template_exists"]),
        "capture_env_template_sha256": str(summary["capture_env_template_sha256"]),
        "adapter_handoff_path": str(summary["adapter_handoff_path"]),
        "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
        "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
        "adapter_handoff_sha256": str(summary["adapter_handoff_sha256"]),
        "source_credential_env_template_path": str(summary["source_credential_env_template_path"]),
        "source_credential_env_template_exists": bool(summary["source_credential_env_template_exists"]),
        "source_credential_env_template_sha256": str(summary["source_credential_env_template_sha256"]),
        "source_live_fetch_contract_available": bool(summary["source_live_fetch_contract_available"]),
        "source_live_fetch_contract_next_gate": str(summary["source_live_fetch_contract_next_gate"]),
        "source_live_fetch_contract_command_template": str(summary["source_live_fetch_contract_command_template"]),
        "source_live_fetch_contract_exchange": str(summary["source_live_fetch_contract_exchange"]),
        "source_live_fetch_contract_market": str(summary["source_live_fetch_contract_market"]),
        "source_live_fetch_contract_session_timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "source_live_fetch_contract_session_open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "source_live_fetch_contract_session_close_local": str(
            summary["source_live_fetch_contract_session_close_local"]
        ),
        "adapter_execution_contract": _mapping(guard_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            guard_config.get("adapter_receipt_proof")
        ),
        "adapter_contract_provider": str(summary["adapter_contract_provider"]),
        "adapter_contract_transport": str(summary["adapter_contract_transport"]),
        "adapter_contract_market": str(summary["adapter_contract_market"]),
        "adapter_contract_exchange": str(summary["adapter_contract_exchange"]),
        "adapter_contract_values_stored": bool(summary["adapter_contract_values_stored"]),
        "adapter_contract_metadata_matches_evidence": bool(summary["adapter_contract_metadata_matches_evidence"]),
        "provider_profile": _mapping(guard_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(guard_config.get("live_session_provider_profile")),
        "capture_bundle_provider_profile": _mapping(
            _mapping(guard_config.get("capture_bundle")).get("capture_bundle_provider_profile")
        ),
        "provider_profile_sha256": str(summary["provider_profile_sha256"]),
        "provider_profile_matches_session": bool(summary["provider_profile_matches_session"]),
        "provider_profile_matches_bundle": bool(summary["provider_profile_matches_bundle"]),
        "adapter_contract_provider_profile_sha256": str(summary["adapter_contract_provider_profile_sha256"]),
        "adapter_contract_provider_profile_matches_evidence": bool(
            summary["adapter_contract_provider_profile_matches_evidence"]
        ),
        "provider_capture_command_count": int(summary["provider_capture_command_count"]),
        "provider_capture_command_providers": str(summary["provider_capture_command_providers"]),
        "provider_capture_command_transports": str(summary["provider_capture_command_transports"]),
        "capture_bundle_provider_capture_command_count": int(
            summary["capture_bundle_provider_capture_command_count"]
        ),
        "capture_bundle_provider_capture_command_missing_count": int(
            summary["capture_bundle_provider_capture_command_missing_count"]
        ),
        "capture_bundle_provider_capture_commands_match_session": bool(
            summary["capture_bundle_provider_capture_commands_match_session"]
        ),
        "provider_capture_commands": commands,
        "capture_bundle_provider_capture_commands": commands,
    }


def _adapter_receipt_proof_status(proof: dict[str, Any]) -> dict[str, Any]:
    records = [
        _mapping(item)
        for item in _list(proof.get("receipts"))
        if _truthy(_mapping(item).get("adapter_receipt_required"))
    ]
    required_count = int(_number(proof.get("required_count")))
    valid_count = int(_number(proof.get("valid_count")))
    receipt_fingerprint_match_count = sum(
        _proof_file_matches(
            _clean(record.get("adapter_receipt_path")),
            _clean(record.get("adapter_receipt_current_sha256"))
            or _clean(record.get("adapter_receipt_ingest_sha256")),
        )
        for record in records
    )
    capture_fingerprint_match_count = sum(
        _proof_file_matches(
            _clean(record.get("capture_path")),
            _clean(record.get("capture_sha256")),
        )
        for record in records
    )
    ready = bool(
        _truthy(proof.get("ready"))
        and required_count > 0
        and len(records) == required_count
        and valid_count == required_count
        and receipt_fingerprint_match_count == required_count
        and capture_fingerprint_match_count == required_count
    )
    return {
        "ready": ready,
        "required_count": required_count,
        "valid_count": valid_count,
        "receipt_fingerprint_match_count": int(receipt_fingerprint_match_count),
        "capture_fingerprint_match_count": int(capture_fingerprint_match_count),
    }


def _adapter_receipt_proof_paths(
    proof: dict[str, Any],
) -> tuple[list[Path], list[Path]]:
    receipt_paths: list[Path] = []
    capture_paths: list[Path] = []
    for item in _list(proof.get("receipts")):
        record = _mapping(item)
        if not _truthy(record.get("adapter_receipt_required")):
            continue
        receipt_path = _path_from_text(_clean(record.get("adapter_receipt_path")))
        if (
            receipt_path is not None
            and receipt_path.exists()
            and receipt_path.is_file()
            and receipt_path not in receipt_paths
        ):
            receipt_paths.append(receipt_path)
        capture_path = _path_from_text(_clean(record.get("capture_path")))
        if (
            capture_path is not None
            and capture_path.exists()
            and capture_path.is_file()
            and capture_path not in capture_paths
        ):
            capture_paths.append(capture_path)
    return receipt_paths, capture_paths


def _proof_file_matches(path_text: str, expected_sha256: str) -> bool:
    path = _path_from_text(path_text)
    return bool(
        path is not None
        and path.exists()
        and path.is_file()
        and expected_sha256
        and _file_sha256(path) == expected_sha256
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _provider_capture_commands(guard_config: dict[str, Any]) -> list[Any]:
    return _list(guard_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(guard_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(guard_config.get("capture_bundle"))
    return (
        _list(guard_config.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("provider_capture_commands"))
    )


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _clean(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(*values: object) -> float | None:
    for value in values:
        text = _clean(value)
        if not text:
            continue
        try:
            return float(text)
        except (TypeError, ValueError):
            continue
    return None


def _number(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _identity_key(value: object) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _truthy(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue"}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_jsonable(row) for row in frame.to_dict(orient="records")]


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _series_record(series: pd.Series) -> dict[str, Any]:
    return _jsonable(series.to_dict())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _records(value)
    if isinstance(value, pd.Series):
        return _series_record(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return str(value)
    return value
