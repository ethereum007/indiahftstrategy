from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


SUPPORTED_STRATEGIES = {"imbalance"}
DEFAULT_STRATEGIES = ("imbalance",)


@dataclass(frozen=True)
class ProviderMarketDataResearchHandoffConfig:
    strategies: tuple[str, ...] = field(default_factory=lambda: DEFAULT_STRATEGIES)
    require_research_ready: bool = True
    allow_synthetic_smoke: bool = False
    min_tick_folds: int = 2
    tick_size: float = 0.05
    market: str = ""
    instrument_id: str = "PROVIDER_BOOK"
    output_root: str = "runs/provider_market_data_research"


@dataclass(frozen=True)
class ProviderMarketDataResearchHandoffReport:
    datasets: pd.DataFrame
    commands: pd.DataFrame
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


def write_provider_market_data_research_handoff(
    live_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataResearchHandoffConfig | None = None,
) -> ProviderMarketDataResearchHandoffReport:
    report = evaluate_provider_market_data_research_handoff(live_evidence_dir, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.datasets.to_csv(out / "provider_market_data_research_handoff_datasets.csv", index=False)
    report.commands.to_csv(out / "provider_market_data_research_handoff_commands.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_research_handoff_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_research_handoff_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_research_handoff_action_queue.csv", index=False)
    (out / "provider_market_data_research_handoff_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_research_handoff_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.datasets, report.commands, report.action_queue),
        encoding="utf-8",
    )
    evidence_dir = Path(live_evidence_dir)
    inputs: dict[str, Any] = {"live_evidence_dir": evidence_dir} if evidence_dir.exists() else {}
    summary_row = report.summary.iloc[0]
    capture_bundle = _path_from_text(str(summary_row["capture_bundle_path"]))
    if capture_bundle is not None and capture_bundle.exists():
        inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(str(summary_row["capture_env_template_path"]))
    if capture_env_template is not None and capture_env_template.exists():
        inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(str(summary_row["adapter_handoff_path"]))
    if adapter_handoff is not None and adapter_handoff.exists():
        inputs["adapter_handoff"] = adapter_handoff
    source_env_template = _path_from_text(str(summary_row["source_credential_env_template_path"]))
    if source_env_template is not None and source_env_template.exists():
        inputs["source_credential_env_template"] = source_env_template
    capture_paths = [Path(str(path)) for path in report.datasets["capture_path"].astype(str).tolist()] if not report.datasets.empty else []
    if capture_paths:
        inputs["captures"] = [path for path in capture_paths if path.exists()]
    write_experiment_manifest(
        out,
        run_type="provider_market_data_research_handoff",
        parameters={"config": asdict(config or ProviderMarketDataResearchHandoffConfig())},
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "research_ready": bool(summary_row["research_ready"]),
            "ready_command_count": int(summary_row["ready_command_count"]),
            "blocked_action_count": int(summary_row["blocked_action_count"]),
            "synthetic_sidecar_proof": _mapping(report.config.get("synthetic_sidecar_proof")),
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "provider_profile": _mapping(report.config.get("provider_profile")),
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
            "adapter_execution_contract": _mapping(report.config.get("adapter_execution_contract")),
            "adapter_contract_provider_profile_sha256": str(summary_row["adapter_contract_provider_profile_sha256"]),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary_row["adapter_contract_provider_profile_matches_evidence"]
            ),
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
                "provider_profile": _mapping(
                    _mapping(report.config.get("capture_bundle")).get("capture_bundle_provider_profile")
                ),
                "provider_capture_commands": _list(
                    _mapping(report.config.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(summary_row["capture_bundle_provider_capture_command_count"]),
                "provider_capture_commands_match_session": bool(
                    summary_row["capture_bundle_provider_capture_commands_match_session"]
                ),
                "adapter_execution_contract": _mapping(
                    _mapping(report.config.get("capture_bundle")).get("adapter_execution_contract")
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
            "provider_capture_commands": _list(report.config.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                _mapping(report.config.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
            ),
        },
    )
    return ProviderMarketDataResearchHandoffReport(
        report.datasets,
        report.commands,
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_research_handoff(
    live_evidence_dir: str | Path,
    *,
    config: ProviderMarketDataResearchHandoffConfig | None = None,
) -> ProviderMarketDataResearchHandoffReport:
    config = _normalize_config(config or ProviderMarketDataResearchHandoffConfig())
    evidence_dir = Path(live_evidence_dir)
    evidence_summary, summary_error = _read_csv(evidence_dir / "provider_market_data_live_evidence_summary.csv")
    evidence_captures, captures_error = _read_csv(evidence_dir / "provider_market_data_live_evidence_captures.csv")
    evidence_config, config_error = _read_json(evidence_dir / "provider_market_data_live_evidence_config.json")
    manifest, manifest_error = _read_json(evidence_dir / "manifest.json")
    datasets = _datasets(evidence_captures)
    commands = _commands(evidence_summary, datasets, config)
    capture_provenance = _capture_provenance(evidence_config, manifest)
    checks = pd.DataFrame(
        _checks(
            evidence_dir,
            evidence_summary,
            summary_error,
            evidence_captures,
            captures_error,
            evidence_config,
            config_error,
            manifest,
            manifest_error,
            datasets,
            commands,
            capture_provenance,
            config,
        )
    )
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    action_queue = _action_queue(checks, commands, ready)
    summary = _summary(evidence_dir, evidence_summary, datasets, commands, checks, action_queue, capture_provenance, config, ready)
    handoff_config = _config(
        summary.iloc[0],
        evidence_dir,
        evidence_summary,
        evidence_config,
        manifest,
        datasets,
        commands,
        capture_provenance,
        checks,
        action_queue,
        config,
    )
    return ProviderMarketDataResearchHandoffReport(datasets, commands, checks, summary, action_queue, handoff_config)


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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"{path.name} is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"{path.name} JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{path.name} JSON must be an object"
    return payload, ""


def _datasets(captures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(captures.to_dict(orient="records") if not captures.empty else [], start=1):
        capture_path = Path(_text(row.get("capture_path")))
        rows.append(
            {
                "priority": index,
                "fold_label": _text(row.get("pipeline_label"), _text(row.get("label"), f"fold_{index}")),
                "capture_path": str(capture_path),
                "capture_exists": bool(capture_path.exists() and capture_path.is_file()),
                "capture_rows": int(_number(row.get("capture_rows"))),
                "synthetic_rehearsal": _truthy(row.get("synthetic_rehearsal")),
                "role": "tick_fold",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "fold_label",
            "capture_path",
            "capture_exists",
            "capture_rows",
            "synthetic_rehearsal",
            "role",
        ],
    )


def _capture_provenance(evidence_config: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    bundle = _mapping(evidence_config.get("capture_bundle"))
    manifest_inputs = _mapping(manifest.get("inputs"))
    manifest_bundle = _mapping(manifest_inputs.get("capture_bundle"))
    manifest_env = _mapping(manifest_inputs.get("capture_env_template"))
    manifest_handoff = _mapping(manifest_inputs.get("adapter_handoff"))
    manifest_source_env = _mapping(manifest_inputs.get("source_credential_env_template"))
    manifest_extra = _mapping(manifest.get("extra"))
    manifest_extra_bundle = _mapping(manifest_extra.get("capture_bundle"))
    manifest_extra_env = _mapping(manifest_extra.get("capture_env_template"))
    manifest_extra_handoff = _mapping(manifest_extra.get("adapter_handoff"))
    manifest_extra_source_env = _mapping(manifest_extra.get("source_credential_env_template"))
    synthetic_sidecar_proof = _mapping(evidence_config.get("synthetic_sidecar_proof")) or _mapping(
        manifest_extra.get("synthetic_sidecar_proof")
    )
    bundle_source_env = _mapping(bundle.get("source_credential_env_template"))
    live_fetch_contract = _mapping(bundle.get("live_fetch_contract")) or _mapping(manifest_extra.get("live_fetch_contract"))
    evidence_adapter_execution_contract = _mapping(evidence_config.get("adapter_execution_contract")) or _mapping(
        manifest_extra.get("adapter_execution_contract")
    )
    session_adapter_execution_contract = _mapping(
        _mapping(evidence_config.get("live_session_packet")).get("adapter_execution_contract")
    )
    bundle_adapter_execution_contract = (
        _mapping(bundle.get("adapter_execution_contract"))
        or _mapping(manifest_extra_bundle.get("adapter_execution_contract"))
    )
    adapter_execution_contract = (
        bundle_adapter_execution_contract
        or evidence_adapter_execution_contract
    )
    adapter_contract_matches_evidence = _adapter_contract_matches_evidence(
        adapter_execution_contract,
        evidence_adapter_execution_contract,
        session_adapter_execution_contract,
    )
    evidence_provider_profile = _mapping(evidence_config.get("provider_profile")) or _mapping(
        manifest_extra.get("provider_profile")
    )
    session_provider_profile = _mapping(_mapping(evidence_config.get("live_session_packet")).get("provider_profile"))
    bundle_provider_profile = (
        _mapping(bundle.get("capture_bundle_provider_profile"))
        or _mapping(bundle.get("provider_profile"))
        or _mapping(manifest_extra_bundle.get("provider_profile"))
        or _mapping(manifest_extra.get("capture_bundle_provider_profile"))
    )
    adapter_contract_provider_profile_sha256 = _text(adapter_execution_contract.get("provider_profile_sha256"))
    provider_profile_matches_session = _provider_profiles_match(
        evidence_provider_profile,
        session_provider_profile,
    )
    provider_profile_matches_bundle = _provider_profiles_match(
        evidence_provider_profile,
        bundle_provider_profile,
    )
    adapter_contract_provider_profile_matches_evidence = bool(
        adapter_contract_provider_profile_sha256
        and adapter_contract_provider_profile_sha256 == _text(evidence_provider_profile.get("sha256"))
    )
    live_fetch_session = _mapping(live_fetch_contract.get("session"))
    evidence_source_session = _mapping(evidence_config.get("source_session")) or _mapping(manifest_extra.get("source_session"))
    evidence_market_session = _mapping(evidence_config.get("market_session")) or _mapping(manifest_extra.get("market_session"))
    capture_bundle_source_session = _mapping(bundle.get("capture_bundle_source_session")) or _mapping(
        manifest_extra_bundle.get("source_session")
    )
    capture_bundle_market_session = _mapping(bundle.get("capture_bundle_market_session")) or _mapping(
        manifest_extra_bundle.get("market_session")
    )
    provider_capture_commands = _provider_capture_command_records(
        evidence_config.get("provider_capture_commands")
    ) or _provider_capture_command_records(manifest_extra.get("provider_capture_commands"))
    bundle_provider_capture_commands = (
        _provider_capture_command_records(bundle.get("capture_bundle_provider_capture_commands"))
        or _provider_capture_command_records(bundle.get("provider_capture_commands"))
        or _provider_capture_command_records(evidence_config.get("capture_bundle_provider_capture_commands"))
        or _provider_capture_command_records(manifest_extra.get("capture_bundle_provider_capture_commands"))
    )
    reported_commands_match = _optional_bool(bundle.get("capture_bundle_provider_capture_commands_match_session"))
    if reported_commands_match is None:
        reported_commands_match = _optional_bool(bundle.get("provider_capture_commands_match_session"))
    if reported_commands_match is None:
        reported_commands_match = _optional_bool(manifest_extra.get("capture_bundle_provider_capture_commands_match_session"))
    computed_commands_match = _provider_capture_commands_match(provider_capture_commands, bundle_provider_capture_commands)
    provider_commands_match = (
        computed_commands_match if reported_commands_match is None else bool(reported_commands_match and computed_commands_match)
    )
    bundle_path = _path_from_text(
        _text(bundle.get("capture_bundle_path"))
        or _text(bundle.get("path"))
        or _text(manifest_bundle.get("path"))
    )
    env_template_path = _path_from_text(
        _text(bundle.get("capture_env_template_path"))
        or _text(bundle.get("env_template_path"))
        or _text(manifest_env.get("path"))
    )
    adapter_handoff_path = _path_from_text(
        _text(bundle.get("adapter_handoff_path"))
        or _text(manifest_handoff.get("path"))
    )
    source_env_template_path = _path_from_text(
        _text(bundle.get("source_credential_env_template_path"))
        or _text(bundle_source_env.get("path"))
        or _text(manifest_source_env.get("path"))
        or _text(manifest_extra_source_env.get("path"))
    )
    source_env_template_exists = bool(
        _truthy(bundle.get("source_credential_env_template_exists"))
        or _truthy(bundle_source_env.get("exists"))
        or _truthy(manifest_extra_source_env.get("exists"))
        or (source_env_template_path is not None and source_env_template_path.exists())
    )
    source_env_template_sha256 = (
        _text(bundle.get("source_credential_env_template_sha256"))
        or _text(bundle_source_env.get("sha256"))
        or _text(manifest_source_env.get("sha256"))
        or _text(manifest_extra_source_env.get("sha256"))
    )
    capture_env_template_sha256 = (
        _text(bundle.get("capture_env_template_sha256"))
        or _text(bundle.get("env_template_sha256"))
        or _text(manifest_env.get("sha256"))
        or _text(manifest_extra_env.get("sha256"))
    )
    adapter_handoff_sha256 = (
        _text(bundle.get("adapter_handoff_sha256"))
        or _text(manifest_handoff.get("sha256"))
        or _text(manifest_extra_handoff.get("sha256"))
    )
    live_fetch_available = bool(
        _truthy(bundle.get("source_live_fetch_contract_available"))
        or _truthy(live_fetch_contract.get("available"))
    )
    live_fetch_next_gate = (
        _text(bundle.get("source_live_fetch_contract_next_gate"))
        or _text(live_fetch_contract.get("next_gate"))
    )
    live_fetch_command_template = (
        _text(bundle.get("source_live_fetch_contract_command_template"))
        or _text(live_fetch_contract.get("command_template"))
    )
    return {
        "capture_bundle_path": _path_text(bundle_path),
        "capture_bundle_provided": bool(bundle_path),
        "capture_bundle_exists": bool(bundle_path is not None and bundle_path.exists()),
        "capture_bundle_ready": _truthy(bundle.get("capture_bundle_ready")) or _truthy(bundle.get("ready")),
        "capture_env_template_path": _path_text(env_template_path),
        "capture_env_template_provided": bool(env_template_path),
        "capture_env_template_exists": bool(env_template_path is not None and env_template_path.exists()),
        "capture_env_template_sha256": capture_env_template_sha256,
        "adapter_handoff_path": _path_text(adapter_handoff_path),
        "adapter_handoff_provided": bool(adapter_handoff_path),
        "adapter_handoff_exists": bool(adapter_handoff_path is not None and adapter_handoff_path.exists()),
        "adapter_handoff_sha256": adapter_handoff_sha256,
        "source_credential_env_template_path": _path_text(source_env_template_path),
        "source_credential_env_template_provided": bool(source_env_template_path),
        "source_credential_env_template_exists": source_env_template_exists,
        "source_credential_env_template_sha256": source_env_template_sha256,
        "source_live_fetch_contract_available": live_fetch_available,
        "source_live_fetch_contract_next_gate": live_fetch_next_gate,
        "source_live_fetch_contract_command_template": live_fetch_command_template,
        "source_live_fetch_contract_exchange": _text(bundle.get("source_live_fetch_contract_exchange"))
        or _text(live_fetch_contract.get("exchange")),
        "source_live_fetch_contract_market": _text(bundle.get("source_live_fetch_contract_market"))
        or _text(live_fetch_contract.get("market")),
        "source_live_fetch_contract_session_timezone": _text(bundle.get("source_live_fetch_contract_session_timezone"))
        or _text(live_fetch_session.get("timezone")),
        "source_live_fetch_contract_session_open_local": _text(bundle.get("source_live_fetch_contract_session_open_local"))
        or _text(live_fetch_session.get("open_local")),
        "source_live_fetch_contract_session_close_local": _text(bundle.get("source_live_fetch_contract_session_close_local"))
        or _text(live_fetch_session.get("close_local")),
        "adapter_execution_contract": adapter_execution_contract,
        "adapter_contract_provider": _text(adapter_execution_contract.get("provider")),
        "adapter_contract_transport": _text(adapter_execution_contract.get("transport")),
        "adapter_contract_market": _text(adapter_execution_contract.get("market")),
        "adapter_contract_exchange": _text(adapter_execution_contract.get("exchange")),
        "adapter_contract_values_stored": bool(adapter_execution_contract.get("values_stored", True)),
        "adapter_contract_metadata_matches_evidence": adapter_contract_matches_evidence,
        "provider_profile": evidence_provider_profile,
        "live_session_provider_profile": session_provider_profile,
        "capture_bundle_provider_profile": bundle_provider_profile,
        "provider_profile_sha256": _text(evidence_provider_profile.get("sha256")),
        "provider_profile_adapter": _text(evidence_provider_profile.get("adapter")),
        "provider_profile_auth_required": bool(evidence_provider_profile.get("auth_required", False)),
        "provider_profile_transports": ";".join(_string_list(evidence_provider_profile.get("transports"))),
        "provider_profile_capabilities": ";".join(_string_list(evidence_provider_profile.get("capabilities"))),
        "capture_bundle_provider_profile_sha256": _text(bundle_provider_profile.get("sha256")),
        "provider_profile_matches_session": provider_profile_matches_session,
        "provider_profile_matches_bundle": provider_profile_matches_bundle,
        "adapter_contract_provider_profile_sha256": adapter_contract_provider_profile_sha256,
        "adapter_contract_provider_profile_matches_evidence": adapter_contract_provider_profile_matches_evidence,
        "provider_capture_commands": provider_capture_commands,
        "provider_capture_command_count": int(len(provider_capture_commands)),
        "provider_capture_command_providers": _unique_command_values(provider_capture_commands, "provider"),
        "provider_capture_command_transports": _unique_command_values(provider_capture_commands, "transport"),
        "capture_bundle_provider_capture_commands": bundle_provider_capture_commands,
        "capture_bundle_provider_capture_command_count": int(len(bundle_provider_capture_commands)),
        "capture_bundle_provider_capture_commands_match_session": provider_commands_match,
        "exchange": _text(evidence_config.get("exchange")) or _text(manifest_extra.get("exchange")),
        "source_session": evidence_source_session,
        "market_session": evidence_market_session,
        "capture_bundle_exchange": _text(bundle.get("capture_bundle_exchange"))
        or _text(manifest_extra_bundle.get("exchange")),
        "capture_bundle_source_session": capture_bundle_source_session,
        "capture_bundle_market_session": capture_bundle_market_session,
        "capture_bundle_metadata_matches_session": _coalesced_bool(
            bundle.get("capture_bundle_metadata_matches_session"),
            manifest_extra_bundle.get("metadata_matches_session"),
            manifest_extra.get("capture_bundle_metadata_matches_session"),
        ),
        "capture_bundle_live_fetch_contract_metadata_matches_session": _coalesced_bool(
            bundle.get("capture_bundle_live_fetch_contract_metadata_matches_session"),
            manifest_extra_bundle.get("live_fetch_contract_metadata_matches_session"),
            manifest_extra.get("capture_bundle_live_fetch_contract_metadata_matches_session"),
        ),
        "synthetic_sidecar_proof": synthetic_sidecar_proof,
        "synthetic_sidecar_proof_ready": _truthy(synthetic_sidecar_proof.get("ready")),
        "synthetic_sidecar_count": int(_number(synthetic_sidecar_proof.get("synthetic_sidecar_count"))),
        "synthetic_sidecar_readable_count": int(_number(synthetic_sidecar_proof.get("sidecar_readable_count"))),
        "synthetic_sidecar_source_count": int(_number(synthetic_sidecar_proof.get("sidecar_source_count"))),
        "synthetic_sidecar_adapter_command_hash_count": int(
            _number(synthetic_sidecar_proof.get("adapter_command_hash_count"))
        ),
        "synthetic_sidecar_capture_env_template_match_count": int(
            _number(synthetic_sidecar_proof.get("capture_env_template_match_count"))
        ),
        "synthetic_sidecar_adapter_handoff_match_count": int(
            _number(synthetic_sidecar_proof.get("adapter_handoff_match_count"))
        ),
        "synthetic_sidecar_source_env_template_match_count": int(
            _number(synthetic_sidecar_proof.get("source_credential_env_template_match_count"))
        ),
        "synthetic_sidecar_live_fetch_contract_count": int(
            _number(synthetic_sidecar_proof.get("live_fetch_contract_count"))
        ),
        "synthetic_sidecar_adapter_execution_contract_safe_count": int(
            _number(synthetic_sidecar_proof.get("adapter_execution_contract_safe_count"))
        ),
        "synthetic_sidecar_invariant_count": int(_number(synthetic_sidecar_proof.get("invariant_count"))),
    }


def _commands(
    evidence_summary: pd.DataFrame,
    datasets: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    market = _effective_market(evidence_summary, config)
    output_root = Path(config.output_root)
    ticks = datasets["capture_path"].astype(str).tolist() if not datasets.empty else []
    labels = datasets["fold_label"].astype(str).tolist() if not datasets.empty else []
    requested = tuple(config.strategies)
    if "imbalance" in requested:
        edge_out = output_root / "imbalance_edge"
        replay_out = output_root / "imbalance_replay"
        rows.append(
            _command(
                "ready",
                "imbalance",
                "imbalance_edge_walkforward",
                "walkforward-imbalance-edge",
                _imbalance_edge_command(ticks, labels, edge_out, market, config),
                str(edge_out),
                "provider tick folds are ready for imbalance edge discovery",
            )
        )
        rows.append(
            _command(
                "ready",
                "imbalance",
                "imbalance_replay_walkforward",
                "walkforward-imbalance-replay",
                _imbalance_replay_command(ticks, labels, edge_out, replay_out, market, config),
                str(replay_out),
                "replay the selected imbalance candidate after edge discovery writes candidate_config.json",
            )
        )
    for strategy in requested:
        if strategy not in SUPPORTED_STRATEGIES:
            rows.append(
                _command(
                    "blocked",
                    strategy,
                    "unsupported_provider_research_handoff",
                    _unsupported_gate(strategy),
                    "",
                    "",
                    _unsupported_reason(strategy),
                )
            )
    for priority, row in enumerate(rows, start=1):
        row["priority"] = priority
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "strategy",
            "run_type",
            "next_gate",
            "command",
            "output_dir",
            "reason",
        ],
    )


def _command(status: str, strategy: str, run_type: str, next_gate: str, command: str, output_dir: str, reason: str) -> dict[str, Any]:
    return {
        "priority": 0,
        "queue_status": status,
        "strategy": strategy,
        "run_type": run_type,
        "next_gate": next_gate,
        "command": command,
        "output_dir": output_dir,
        "reason": reason,
    }


def _imbalance_edge_command(
    ticks: list[str],
    labels: list[str],
    output_dir: Path,
    market: str,
    config: ProviderMarketDataResearchHandoffConfig,
) -> str:
    parts = [
        "python",
        "-m",
        "hft_cli",
        "walkforward-imbalance-edge",
        "--ticks",
        *ticks,
        "--out",
        str(output_dir),
    ]
    for label in labels:
        parts.extend(["--label", label])
    parts.extend(
        [
            "--market",
            market,
            "--tick-size",
            str(config.tick_size),
            "--entry-imbalance",
            "0.55",
            "0.65",
            "0.75",
            "--min-microprice-edge-ticks",
            "0.25",
            "0.50",
            "1.00",
            "--forward-horizon-ns",
            "100000000",
            "500000000",
            "1000000000",
            "--min-signals",
            "1",
            "--min-passed-configs",
            "1",
            "--fail-on-breach",
        ]
    )
    return " ".join(_shell_quote(part) for part in parts)


def _imbalance_replay_command(
    ticks: list[str],
    labels: list[str],
    edge_out: Path,
    output_dir: Path,
    market: str,
    config: ProviderMarketDataResearchHandoffConfig,
) -> str:
    parts = [
        "python",
        "-m",
        "hft_cli",
        "walkforward-imbalance-replay",
        "--ticks",
        *ticks,
        "--out",
        str(output_dir),
        "--candidate-config",
        str(edge_out / "candidate_config.json"),
    ]
    for label in labels:
        parts.extend(["--label", label])
    parts.extend(
        [
            "--market",
            market,
            "--instrument-id",
            config.instrument_id,
            "--tick-size",
            str(config.tick_size),
            "--qty",
            "75",
            "--min-fills",
            "1",
            "--min-folds",
            str(config.min_tick_folds),
            "--fail-on-breach",
        ]
    )
    return " ".join(_shell_quote(part) for part in parts)


def _checks(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    summary_error: str,
    evidence_captures: pd.DataFrame,
    captures_error: str,
    evidence_config: dict[str, Any],
    config_error: str,
    manifest: dict[str, Any],
    manifest_error: str,
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    capture_provenance: dict[str, Any],
    config: ProviderMarketDataResearchHandoffConfig,
) -> list[dict[str, Any]]:
    dataset_count = int(len(datasets))
    synthetic_count = int(datasets["synthetic_rehearsal"].astype(bool).sum()) if not datasets.empty else 0
    ready_commands = int((commands["queue_status"].astype(str) == "ready").sum()) if not commands.empty else 0
    blocked_commands = int((commands["queue_status"].astype(str) == "blocked").sum()) if not commands.empty else 0
    unsupported = [strategy for strategy in config.strategies if strategy not in SUPPORTED_STRATEGIES]
    bundle_provided = bool(capture_provenance["capture_bundle_provided"])
    env_template_required = bool(bundle_provided or capture_provenance["capture_env_template_provided"])
    handoff_required = bool(bundle_provided or capture_provenance["adapter_handoff_provided"])
    source_session = _mapping(capture_provenance.get("source_session"))
    market_session = _mapping(capture_provenance.get("market_session"))
    bundle_source_session = _mapping(capture_provenance.get("capture_bundle_source_session"))
    bundle_market_session = _mapping(capture_provenance.get("capture_bundle_market_session"))
    provider_capture_command_count = int(capture_provenance["provider_capture_command_count"])
    bundle_provider_capture_command_count = int(capture_provenance["capture_bundle_provider_capture_command_count"])
    bundle_provider_capture_command_missing_count = max(
        provider_capture_command_count - bundle_provider_capture_command_count,
        0,
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and bool(capture_provenance["capture_bundle_provider_capture_commands_match_session"])
    )
    adapter_execution_contract = _mapping(capture_provenance.get("adapter_execution_contract"))
    adapter_execution_contract_carried = (
        bool(capture_provenance["adapter_contract_provider"])
        and bool(capture_provenance["adapter_contract_transport"])
        and bool(capture_provenance["adapter_contract_market"])
        and bool(capture_provenance["adapter_contract_exchange"])
        and bool(capture_provenance["adapter_contract_values_stored"]) is False
    )
    evidence_provider_profile = _mapping(capture_provenance.get("provider_profile"))
    bundle_provider_profile = _mapping(capture_provenance.get("capture_bundle_provider_profile"))
    evidence_provider_profile_carried = _provider_profile_carried(evidence_provider_profile)
    bundle_provider_profile_carried = _provider_profile_carried(bundle_provider_profile)
    sidecar_proof_required = synthetic_count > 0
    sidecar_proof_count = int(capture_provenance["synthetic_sidecar_count"])
    sidecar_proof_count_matches = sidecar_proof_count == synthetic_count
    sidecar_proof_ready = bool(capture_provenance["synthetic_sidecar_proof_ready"])
    return [
        _check("live_evidence_dir_exists", str(evidence_dir), "exists", True, evidence_dir.exists(), "live evidence directory is required"),
        _check("live_evidence_summary_readable", summary_error or "ok", "is", "ok", not summary_error, summary_error or "live evidence summary could not be read"),
        _check("live_evidence_captures_readable", captures_error or "ok", "is", "ok", not captures_error, captures_error or "live evidence captures could not be read"),
        _check("live_evidence_config_readable", config_error or "ok", "is", "ok", not config_error, config_error or "live evidence config could not be read"),
        _check("live_evidence_manifest_readable", manifest_error or "ok", "is", "ok", not manifest_error, manifest_error or "live evidence manifest could not be read"),
        _check("live_evidence_manifest_type", _text(manifest.get("run_type")), "is", "provider_market_data_live_evidence_review", _text(manifest.get("run_type")) == "provider_market_data_live_evidence_review", "live evidence manifest run_type is not expected"),
        _check("capture_bundle_exists", capture_provenance["capture_bundle_path"], "exists", True, bool(capture_provenance["capture_bundle_exists"]) if bundle_provided else True, "capture bundle referenced by live evidence is missing"),
        _check("capture_env_template_exists", capture_provenance["capture_env_template_path"], "exists", True, bool(capture_provenance["capture_env_template_exists"]) if env_template_required else True, "credential env-template referenced by live evidence is missing"),
        _check("adapter_handoff_exists", capture_provenance["adapter_handoff_path"], "exists", True, bool(capture_provenance["adapter_handoff_exists"]) if handoff_required else True, "adapter handoff referenced by live evidence is missing"),
        _check("capture_bundle_source_credential_env_template_carried", capture_provenance["source_credential_env_template_path"], "exists", True, bool(capture_provenance["source_credential_env_template_exists"]) and bool(capture_provenance["source_credential_env_template_sha256"]) if bundle_provided else True, "source credential env-template referenced by live evidence is missing"),
        _check("capture_bundle_live_fetch_contract_carried", bool(capture_provenance["source_live_fetch_contract_available"]), "is", True, bool(capture_provenance["source_live_fetch_contract_available"]) and str(capture_provenance["source_live_fetch_contract_next_gate"]) == "provider_fetcher" if bundle_provided else True, "live fetch-contract referenced by live evidence is missing"),
        _check("capture_bundle_provider_capture_commands_carried", bundle_provider_capture_command_count, "==", provider_capture_command_count, bundle_provider_capture_commands_carried if bundle_provided else True, "live evidence provider capture command handoffs are missing"),
        _check("capture_bundle_provider_capture_commands_match_session", bundle_provider_capture_command_count, "matches", provider_capture_command_count, bundle_provider_capture_commands_match_session if bundle_provided else True, "live evidence provider capture command handoffs must match the live session packet"),
        _check("capture_bundle_adapter_execution_contract_carried", _adapter_contract_metadata_text(adapter_execution_contract), "is_not", "", adapter_execution_contract_carried if bundle_provided else True, "adapter execution contract referenced by live evidence is missing or stores credential values"),
        _check("capture_bundle_adapter_execution_contract_matches_evidence", _adapter_contract_metadata_text(adapter_execution_contract), "==", "live evidence adapter contract", bool(capture_provenance["adapter_contract_metadata_matches_evidence"]) if bundle_provided else True, "adapter execution contract must match the live evidence session contract"),
        _check("live_evidence_provider_profile_carried", _text(evidence_provider_profile.get("sha256")), "has", "provider profile", evidence_provider_profile_carried, "live evidence provider-profile contract is missing or unsafe"),
        _check("live_evidence_provider_profile_matches_session", _text(evidence_provider_profile.get("sha256")), "==", "live session provider profile", bool(capture_provenance["provider_profile_matches_session"]), "live evidence provider-profile contract must match the live session packet"),
        _check("capture_bundle_provider_profile_carried", _text(bundle_provider_profile.get("sha256")), "has", "provider profile", bundle_provider_profile_carried if bundle_provided else True, "capture-bundle provider-profile proof is missing from live evidence"),
        _check("capture_bundle_provider_profile_matches_evidence", _text(bundle_provider_profile.get("sha256")), "==", _text(evidence_provider_profile.get("sha256")), bool(capture_provenance["provider_profile_matches_bundle"]) if bundle_provided else True, "capture-bundle provider-profile contract must match live evidence"),
        _check("adapter_execution_contract_provider_profile_matches_evidence", capture_provenance["adapter_contract_provider_profile_sha256"], "==", _text(evidence_provider_profile.get("sha256")), bool(capture_provenance["adapter_contract_provider_profile_matches_evidence"]) if bundle_provided else True, "adapter execution contract provider-profile SHA must match live evidence"),
        _check("live_evidence_exchange_carried", capture_provenance["exchange"], "is_not", "", bool(capture_provenance["exchange"]) if bundle_provided else True, "live evidence exchange metadata is missing"),
        _check("live_evidence_source_session_carried", _session_contract_text(source_session), "has", "timezone/open/close", _session_contract_carried(source_session) if bundle_provided else True, "live evidence source-session metadata is missing"),
        _check("live_evidence_market_session_carried", _session_contract_text(market_session), "has", "timezone/open/close", _session_contract_carried(market_session) if bundle_provided else True, "live evidence market-session metadata is missing"),
        _check("capture_bundle_exchange_matches_evidence", capture_provenance["capture_bundle_exchange"], "==", capture_provenance["exchange"], capture_provenance["capture_bundle_exchange"] == capture_provenance["exchange"] if bundle_provided else True, "capture bundle exchange metadata must match live evidence"),
        _check("capture_bundle_source_session_matches_evidence", _session_contract_text(bundle_source_session), "==", _session_contract_text(source_session), _session_contracts_match(bundle_source_session, source_session) if bundle_provided else True, "capture bundle source-session metadata must match live evidence"),
        _check("capture_bundle_market_session_matches_evidence", _session_contract_text(bundle_market_session), "==", _session_contract_text(market_session), _session_contracts_match(bundle_market_session, market_session) if bundle_provided else True, "capture bundle market-session metadata must match live evidence"),
        _check("capture_bundle_metadata_matches_session", bool(capture_provenance["capture_bundle_metadata_matches_session"]), "is", True, bool(capture_provenance["capture_bundle_metadata_matches_session"]) if bundle_provided else True, "live evidence must mark capture-bundle exchange/session metadata as matching"),
        _check("capture_bundle_live_fetch_contract_metadata_matches_session", bool(capture_provenance["capture_bundle_live_fetch_contract_metadata_matches_session"]), "is", True, bool(capture_provenance["capture_bundle_live_fetch_contract_metadata_matches_session"]) if bundle_provided else True, "live evidence must mark live fetch-contract exchange/session metadata as matching"),
        _check("live_evidence_ready", _first_bool(evidence_summary, "ready"), "is", True, _first_bool(evidence_summary, "ready"), "live evidence review is not ready"),
        _check("live_evidence_research_ready", _first_bool(evidence_summary, "research_ready"), "is", True, _first_bool(evidence_summary, "research_ready") or not config.require_research_ready, "live evidence is not research-ready"),
        _check("synthetic_sidecar_proof_carried", sidecar_proof_count, "==", synthetic_count, sidecar_proof_count_matches if sidecar_proof_required else True, "synthetic smoke handoff requires live-evidence rehearsal sidecar proof for every synthetic fold"),
        _check("synthetic_sidecar_proof_ready", sidecar_proof_ready, "is", True, sidecar_proof_ready if sidecar_proof_required else True, "synthetic smoke handoff requires ready rehearsal sidecar proof"),
        _check("synthetic_rehearsal_absent", synthetic_count, "==", 0 if not config.allow_synthetic_smoke else "allowed", synthetic_count == 0 or config.allow_synthetic_smoke, "synthetic rehearsal captures cannot be handed to strategy research"),
        _check("tick_folds_present", dataset_count, ">=", config.min_tick_folds, dataset_count >= config.min_tick_folds, "not enough tick folds for walk-forward research"),
        _check("tick_fold_files_exist", int(datasets["capture_exists"].astype(bool).sum()) if not datasets.empty else 0, "==", dataset_count, bool(dataset_count and datasets["capture_exists"].astype(bool).all()), "all tick fold files must exist"),
        _check("tick_fold_rows_positive", int((datasets["capture_rows"].astype(int) > 0).sum()) if not datasets.empty else 0, "==", dataset_count, bool(dataset_count and (datasets["capture_rows"].astype(int) > 0).all()), "all tick folds must contain rows"),
        _check("requested_strategies_supported", ";".join(unsupported), "is", "", not unsupported, "some requested strategies need extra inputs before provider tick handoff"),
        _check("ready_research_commands_present", ready_commands, ">=", 1, ready_commands >= 1, "at least one ready research command is required"),
        _check("blocked_research_commands_absent", blocked_commands, "==", 0, blocked_commands == 0, "blocked research commands remain"),
        _check("tick_size_positive", config.tick_size, ">", 0, config.tick_size > 0, "tick size must be positive"),
    ]


def _summary(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    capture_provenance: dict[str, Any],
    config: ProviderMarketDataResearchHandoffConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    ready_actions = int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    source_session = _mapping(capture_provenance.get("source_session"))
    market_session = _mapping(capture_provenance.get("market_session"))
    bundle_source_session = _mapping(capture_provenance.get("capture_bundle_source_session"))
    bundle_market_session = _mapping(capture_provenance.get("capture_bundle_market_session"))
    provider_capture_command_count = int(capture_provenance["provider_capture_command_count"])
    bundle_provider_capture_command_count = int(capture_provenance["capture_bundle_provider_capture_command_count"])
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "research_ready": bool(ready and _first_bool(evidence_summary, "research_ready")),
                "live_evidence_dir": str(evidence_dir),
                "provider": _first_text(evidence_summary, "provider"),
                "transport": _first_text(evidence_summary, "transport"),
                "market": _effective_market(evidence_summary, config),
                "exchange": str(capture_provenance["exchange"]),
                "kind": _first_text(evidence_summary, "kind"),
                "source_session_timezone": _text(source_session.get("timezone")),
                "source_session_open_local": _text(source_session.get("open_local")),
                "source_session_close_local": _text(source_session.get("close_local")),
                "market_session_timezone": _text(market_session.get("timezone")),
                "market_session_open_local": _text(market_session.get("open_local")),
                "market_session_close_local": _text(market_session.get("close_local")),
                "strategy": ";".join(config.strategies),
                "strategy_profiles": ";".join(config.strategies),
                "capture_bundle_path": str(capture_provenance["capture_bundle_path"]),
                "capture_bundle_provided": bool(capture_provenance["capture_bundle_provided"]),
                "capture_bundle_exists": bool(capture_provenance["capture_bundle_exists"]),
                "capture_bundle_ready": bool(capture_provenance["capture_bundle_ready"]),
                "capture_env_template_path": str(capture_provenance["capture_env_template_path"]),
                "capture_env_template_provided": bool(capture_provenance["capture_env_template_provided"]),
                "capture_env_template_exists": bool(capture_provenance["capture_env_template_exists"]),
                "capture_env_template_sha256": str(capture_provenance["capture_env_template_sha256"]),
                "adapter_handoff_path": str(capture_provenance["adapter_handoff_path"]),
                "adapter_handoff_provided": bool(capture_provenance["adapter_handoff_provided"]),
                "adapter_handoff_exists": bool(capture_provenance["adapter_handoff_exists"]),
                "adapter_handoff_sha256": str(capture_provenance["adapter_handoff_sha256"]),
                "source_credential_env_template_path": str(capture_provenance["source_credential_env_template_path"]),
                "source_credential_env_template_exists": bool(capture_provenance["source_credential_env_template_exists"]),
                "source_credential_env_template_sha256": str(capture_provenance["source_credential_env_template_sha256"]),
                "source_live_fetch_contract_available": bool(capture_provenance["source_live_fetch_contract_available"]),
                "source_live_fetch_contract_next_gate": str(capture_provenance["source_live_fetch_contract_next_gate"]),
                "source_live_fetch_contract_command_template": str(capture_provenance["source_live_fetch_contract_command_template"]),
                "source_live_fetch_contract_exchange": str(capture_provenance["source_live_fetch_contract_exchange"]),
                "source_live_fetch_contract_market": str(capture_provenance["source_live_fetch_contract_market"]),
                "source_live_fetch_contract_session_timezone": str(capture_provenance["source_live_fetch_contract_session_timezone"]),
                "source_live_fetch_contract_session_open_local": str(capture_provenance["source_live_fetch_contract_session_open_local"]),
                "source_live_fetch_contract_session_close_local": str(capture_provenance["source_live_fetch_contract_session_close_local"]),
                "adapter_contract_provider": str(capture_provenance["adapter_contract_provider"]),
                "adapter_contract_transport": str(capture_provenance["adapter_contract_transport"]),
                "adapter_contract_market": str(capture_provenance["adapter_contract_market"]),
                "adapter_contract_exchange": str(capture_provenance["adapter_contract_exchange"]),
                "adapter_contract_values_stored": bool(capture_provenance["adapter_contract_values_stored"]),
                "adapter_contract_metadata_matches_evidence": bool(
                    capture_provenance["adapter_contract_metadata_matches_evidence"]
                ),
                "provider_profile_sha256": str(capture_provenance["provider_profile_sha256"]),
                "provider_profile_adapter": str(capture_provenance["provider_profile_adapter"]),
                "provider_profile_auth_required": bool(capture_provenance["provider_profile_auth_required"]),
                "provider_profile_transports": str(capture_provenance["provider_profile_transports"]),
                "provider_profile_capabilities": str(capture_provenance["provider_profile_capabilities"]),
                "capture_bundle_provider_profile_sha256": str(
                    capture_provenance["capture_bundle_provider_profile_sha256"]
                ),
                "provider_profile_matches_session": bool(capture_provenance["provider_profile_matches_session"]),
                "provider_profile_matches_bundle": bool(capture_provenance["provider_profile_matches_bundle"])
                if bool(capture_provenance["capture_bundle_provided"])
                else True,
                "adapter_contract_provider_profile_sha256": str(
                    capture_provenance["adapter_contract_provider_profile_sha256"]
                ),
                "adapter_contract_provider_profile_matches_evidence": bool(
                    capture_provenance["adapter_contract_provider_profile_matches_evidence"]
                )
                if bool(capture_provenance["capture_bundle_provided"])
                else True,
                "provider_capture_command_count": provider_capture_command_count,
                "provider_capture_command_providers": str(capture_provenance["provider_capture_command_providers"]),
                "provider_capture_command_transports": str(capture_provenance["provider_capture_command_transports"]),
                "capture_bundle_provider_capture_command_count": bundle_provider_capture_command_count,
                "capture_bundle_provider_capture_command_missing_count": max(
                    provider_capture_command_count - bundle_provider_capture_command_count,
                    0,
                )
                if bool(capture_provenance["capture_bundle_provided"])
                else 0,
                "capture_bundle_provider_capture_commands_match_session": bool(
                    capture_provenance["capture_bundle_provider_capture_commands_match_session"]
                )
                if bool(capture_provenance["capture_bundle_provided"])
                else True,
                "capture_bundle_exchange": str(capture_provenance["capture_bundle_exchange"]),
                "capture_bundle_source_session_timezone": _text(bundle_source_session.get("timezone")),
                "capture_bundle_source_session_open_local": _text(bundle_source_session.get("open_local")),
                "capture_bundle_source_session_close_local": _text(bundle_source_session.get("close_local")),
                "capture_bundle_market_session_timezone": _text(bundle_market_session.get("timezone")),
                "capture_bundle_market_session_open_local": _text(bundle_market_session.get("open_local")),
                "capture_bundle_market_session_close_local": _text(bundle_market_session.get("close_local")),
                "capture_bundle_metadata_matches_session": bool(capture_provenance["capture_bundle_metadata_matches_session"]),
                "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                    capture_provenance["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
                "dataset_count": int(len(datasets)),
                "synthetic_sidecar_proof_ready": bool(capture_provenance["synthetic_sidecar_proof_ready"]),
                "synthetic_sidecar_count": int(capture_provenance["synthetic_sidecar_count"]),
                "synthetic_sidecar_readable_count": int(capture_provenance["synthetic_sidecar_readable_count"]),
                "synthetic_sidecar_source_count": int(capture_provenance["synthetic_sidecar_source_count"]),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    capture_provenance["synthetic_sidecar_adapter_command_hash_count"]
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    capture_provenance["synthetic_sidecar_capture_env_template_match_count"]
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    capture_provenance["synthetic_sidecar_adapter_handoff_match_count"]
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    capture_provenance["synthetic_sidecar_source_env_template_match_count"]
                ),
                "synthetic_sidecar_live_fetch_contract_count": int(
                    capture_provenance["synthetic_sidecar_live_fetch_contract_count"]
                ),
                "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    capture_provenance["synthetic_sidecar_adapter_execution_contract_safe_count"]
                ),
                "synthetic_sidecar_invariant_count": int(capture_provenance["synthetic_sidecar_invariant_count"]),
                "ready_command_count": int((commands["queue_status"].astype(str) == "ready").sum()) if not commands.empty else 0,
                "blocked_command_count": int((commands["queue_status"].astype(str) == "blocked").sum()) if not commands.empty else 0,
                "synthetic_dataset_count": int(datasets["synthetic_rehearsal"].astype(bool).sum()) if not datasets.empty else 0,
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": ready_actions,
                "blocked_action_count": blocked,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "run_provider_market_data_strategy_research" if ready else "fix_provider_market_data_research_handoff",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, commands: pd.DataFrame, ready: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        check = str(row["check"])
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": str(row["reason"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and ready:
        for _, command in commands.loc[commands["queue_status"].astype(str) == "ready"].iterrows():
            rows.append(
                {
                    "priority": len(rows) + 1,
                    "queue_status": "ready",
                    "action": f"run_{command['run_type']}",
                    "reason": str(command["reason"]),
                    "next_gate": str(command["next_gate"]),
                    "next_gate_help_command": str(command["command"]),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _config(
    summary: pd.Series,
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    manifest: dict[str, Any],
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    capture_provenance: dict[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "research_ready": bool(summary["research_ready"]),
        "parameters": asdict(config),
        "live_evidence_dir": str(evidence_dir),
        "evidence_summary": _first_record(evidence_summary),
        "evidence_manifest_run_type": _text(manifest.get("run_type")),
        "evidence_config_ready": bool(evidence_config.get("ready", False)),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(capture_provenance.get("provider_profile")),
        "live_session_provider_profile": _mapping(capture_provenance.get("live_session_provider_profile")),
        "provider_capture_commands": _list(capture_provenance.get("provider_capture_commands")),
        "capture_bundle_provider_capture_commands": _list(
            capture_provenance.get("capture_bundle_provider_capture_commands")
        ),
        "adapter_execution_contract": _mapping(capture_provenance.get("adapter_execution_contract")),
        "capture_bundle": capture_provenance,
        "synthetic_sidecar_proof": _mapping(capture_provenance.get("synthetic_sidecar_proof")),
        "datasets": _records(datasets),
        "commands": _records(commands),
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": actions[0] if actions else {},
    }


def _next_gate_for_check(check: str) -> str:
    if check in {
        "capture_bundle_adapter_execution_contract_carried",
        "capture_bundle_adapter_execution_contract_matches_evidence",
        "adapter_execution_contract_provider_profile_matches_evidence",
        "live_evidence_provider_profile_carried",
        "live_evidence_provider_profile_matches_session",
        "capture_bundle_provider_profile_carried",
        "capture_bundle_provider_profile_matches_evidence",
    }:
        return "review-provider-market-data-live-evidence"
    if check.startswith("synthetic_sidecar"):
        return "review-provider-market-data-live-evidence"
    if (
        check.startswith("capture_bundle")
        or check.startswith("capture_env_template")
        or check.startswith("adapter_handoff")
    ):
        return "bundle-provider-market-data-live-capture"
    if check.startswith("live_evidence"):
        return "review-provider-market-data-live-evidence"
    if check.startswith("synthetic"):
        return "provider_fetcher_live_run"
    if check.startswith("tick_fold"):
        return "review-provider-market-data-live-evidence"
    if check.startswith("requested_strategies"):
        return "handoff-provider-market-data-research"
    if check.startswith("ready_research") or check.startswith("blocked_research"):
        return "handoff-provider-market-data-research"
    return "handoff-provider-market-data-research"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "bundle-provider-market-data-live-capture",
        "review-provider-market-data-live-evidence",
        "handoff-provider-market-data-research",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_fetcher_live_run":
        return "replace synthetic captures with real Arrow.money/iRage provider captures"
    return ""


def _repair_action(check: str) -> str:
    if check == "capture_bundle_source_credential_env_template_carried":
        return "regenerate_capture_bundle_with_source_env_template"
    if check == "capture_bundle_live_fetch_contract_carried":
        return "regenerate_capture_bundle_with_live_fetch_contract"
    if check == "capture_bundle_provider_capture_commands_carried":
        return "regenerate_capture_bundle_with_provider_capture_commands"
    if check == "capture_bundle_provider_capture_commands_match_session":
        return "regenerate_live_evidence_with_session_provider_capture_commands"
    if check == "capture_bundle_adapter_execution_contract_carried":
        return "regenerate_live_evidence_with_adapter_execution_contract"
    if check == "capture_bundle_adapter_execution_contract_matches_evidence":
        return "regenerate_live_evidence_with_session_adapter_execution_contract"
    if check == "adapter_execution_contract_provider_profile_matches_evidence":
        return "regenerate_live_evidence_with_adapter_provider_profile_sha"
    if check.startswith("live_evidence_provider_profile"):
        return "regenerate_live_evidence_with_provider_profile"
    if check.startswith("capture_bundle_provider_profile"):
        return "regenerate_live_evidence_with_capture_bundle_provider_profile"
    if check in {
        "live_evidence_exchange_carried",
        "live_evidence_source_session_carried",
        "live_evidence_market_session_carried",
        "capture_bundle_exchange_matches_evidence",
        "capture_bundle_source_session_matches_evidence",
        "capture_bundle_market_session_matches_evidence",
        "capture_bundle_metadata_matches_session",
    }:
        return "regenerate_live_evidence_with_session_metadata"
    if check == "capture_bundle_live_fetch_contract_metadata_matches_session":
        return "regenerate_live_evidence_with_live_fetch_contract_metadata"
    if check.startswith("synthetic_sidecar"):
        return "regenerate_live_evidence_with_synthetic_sidecar_proof"
    if (
        check.startswith("capture_bundle")
        or check.startswith("capture_env_template")
        or check.startswith("adapter_handoff")
    ):
        return "repair_provider_live_capture_bundle"
    if check.startswith("live_evidence"):
        return "repair_live_evidence_review"
    if check.startswith("synthetic"):
        return "replace_synthetic_captures_with_real_provider_data"
    if check.startswith("tick_fold"):
        return "collect_more_provider_tick_folds"
    if check.startswith("requested_strategies"):
        return "provide_extra_strategy_inputs_or_select_imbalance"
    return "repair_provider_market_data_research_handoff"


def _unsupported_gate(strategy: str) -> str:
    if strategy == "leadlag":
        return "walkforward-leadlag-replay"
    if strategy == "settlement":
        return "walkforward-settlement-convergence"
    if strategy == "surface_mm":
        return "pipeline-surface-mm-research"
    if strategy == "parity":
        return "audit-parity-edge"
    return "handoff-provider-market-data-research"


def _unsupported_reason(strategy: str) -> str:
    if strategy == "leadlag":
        return "lead-lag needs explicit leader/laggard capture groups"
    if strategy in {"settlement", "parity", "surface_mm"}:
        return "this strategy needs option-chain or surface inputs in addition to top-of-book ticks"
    return "strategy is not supported by provider tick research handoff"


def _effective_market(evidence_summary: pd.DataFrame, config: ProviderMarketDataResearchHandoffConfig) -> str:
    return config.market or _first_text(evidence_summary, "market") or "india_nse_index_derivatives"


def _runbook_markdown(summary: pd.Series, datasets: pd.DataFrame, commands: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Research Handoff",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Strategies: {summary['strategy_profiles']}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Adapter execution contract: {summary['adapter_contract_provider'] or 'missing'} / {summary['adapter_contract_transport'] or 'missing'} (evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'}",
        f"- Tick folds: {summary['dataset_count']}",
        f"- Ready commands: {summary['ready_command_count']}",
        "",
        "## Datasets",
        "",
        _datasets_table(datasets),
        "",
        "## Research Commands",
        "",
        _commands_table(commands),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _datasets_table(datasets: pd.DataFrame) -> str:
    if datasets.empty:
        return "_None_"
    rows = []
    for row in datasets.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("fold_label")),
                _text(row.get("capture_path")),
                str(row.get("capture_rows", "")),
                "yes" if _truthy(row.get("synthetic_rehearsal")) else "no",
            ]
        )
    return _markdown_table(["#", "Fold", "Capture", "Rows", "Synthetic"], rows)


def _commands_table(commands: pd.DataFrame) -> str:
    if commands.empty:
        return "_None_"
    rows = []
    for row in commands.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("queue_status")),
                _text(row.get("strategy")),
                _text(row.get("run_type")),
                _text(row.get("command")),
            ]
        )
    return _markdown_table(["#", "Status", "Strategy", "Run type", "Command"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = []
    for row in action_queue.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("queue_status")),
                _text(row.get("action")),
                _text(row.get("next_gate")),
                _text(row.get("reason")),
            ]
        )
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


def _normalize_config(config: ProviderMarketDataResearchHandoffConfig) -> ProviderMarketDataResearchHandoffConfig:
    strategies = tuple(_normalize_strategy(item) for item in config.strategies if _normalize_strategy(item))
    return ProviderMarketDataResearchHandoffConfig(
        strategies=strategies or DEFAULT_STRATEGIES,
        require_research_ready=bool(config.require_research_ready),
        allow_synthetic_smoke=bool(config.allow_synthetic_smoke),
        min_tick_folds=int(config.min_tick_folds),
        tick_size=float(config.tick_size),
        market=str(config.market or "").strip(),
        instrument_id=str(config.instrument_id or "PROVIDER_BOOK").strip(),
        output_root=str(config.output_root or "runs/provider_market_data_research").strip(),
    )


def _normalize_strategy(value: object) -> str:
    text = _text(value).lower().replace("-", "_")
    aliases = {
        "microprice_imbalance": "imbalance",
        "lead_lag": "leadlag",
        "lead_lag_taker": "leadlag",
        "settlement_convergence": "settlement",
        "parity_box": "parity",
        "surface_market_making": "surface_mm",
    }
    return aliases.get(text, text)


def _coalesced_bool(*values: object) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return _truthy(value)
    return False


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _truthy(value)


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


def _session_contracts_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not (_session_contract_carried(left) and _session_contract_carried(right)):
        return False
    return (
        _text(left.get("timezone")) == _text(right.get("timezone"))
        and _wall_clock_seconds(left.get("open_local")) == _wall_clock_seconds(right.get("open_local"))
        and _wall_clock_seconds(left.get("close_local")) == _wall_clock_seconds(right.get("close_local"))
    )


def _session_contract_carried(session: dict[str, Any]) -> bool:
    return all(_text(session.get(key)) for key in ("timezone", "open_local", "close_local"))


def _session_contract_text(session: dict[str, Any]) -> str:
    return (
        f"{_text(session.get('timezone'))}|"
        f"{_text(session.get('open_local'))}|"
        f"{_text(session.get('close_local'))}"
    )


def _adapter_contract_matches_evidence(
    contract: dict[str, Any],
    evidence_contract: dict[str, Any],
    session_contract: dict[str, Any],
) -> bool:
    reference = evidence_contract or session_contract
    if not (contract and reference):
        return False
    return (
        _adapter_contract_signature(contract) == _adapter_contract_signature(reference)
        and bool(contract.get("values_stored", True)) is False
        and bool(reference.get("values_stored", True)) is False
    )


def _adapter_contract_signature(contract: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(contract.get(key))
        for key in (
            "provider",
            "transport",
            "market",
            "exchange",
            "kind",
            "endpoint",
        )
    )


def _adapter_contract_metadata_text(contract: dict[str, Any]) -> str:
    return (
        f"{_text(contract.get('provider'))}|"
        f"{_text(contract.get('transport'))}|"
        f"{_text(contract.get('market'))}|"
        f"{_text(contract.get('exchange'))}|"
        f"{_text(contract.get('kind'))}|"
        f"{_text(contract.get('endpoint'))}"
    )


def _provider_profile_carried(profile: dict[str, Any]) -> bool:
    return (
        bool(_text(profile.get("sha256")))
        and bool(_text(profile.get("provider")))
        and bool(_text(profile.get("adapter")))
        and bool(_string_list(profile.get("transports")))
        and bool(profile.get("values_stored", True)) is False
    )


def _provider_profiles_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    return (
        _text(left.get("sha256")) == _text(right.get("sha256"))
        and _text(left.get("provider")) == _text(right.get("provider"))
        and _text(left.get("adapter")) == _text(right.get("adapter"))
        and _string_list(left.get("transports")) == _string_list(right.get("transports"))
    )


def _provider_capture_command_records(value: object) -> list[dict[str, str]]:
    rows = _list(value)
    commands: list[dict[str, str]] = []
    for row in rows:
        item = _mapping(row)
        command_template = _text(
            item.get("command_template")
            or item.get("capture_command_template")
            or item.get("capture_command_hint")
            or item.get("provider_capture_command_template")
        )
        if not command_template:
            continue
        commands.append(
            {
                "label": _text(item.get("label")),
                "provider": _text(item.get("provider") or item.get("capture_command_provider") or item.get("provider_capture_command_provider")),
                "transport": _text(item.get("transport") or item.get("capture_command_transport") or item.get("provider_capture_command_transport")),
                "endpoint": _text(item.get("endpoint") or item.get("capture_command_endpoint") or item.get("provider_capture_command_endpoint")),
                "kind": _text(item.get("kind") or item.get("capture_command_kind") or item.get("provider_capture_command_kind")),
                "exchange": _text(item.get("exchange") or item.get("capture_command_exchange") or item.get("provider_capture_command_exchange")),
                "start_local": _text(item.get("start_local")),
                "end_local": _text(item.get("end_local")),
                "output": _text(item.get("output") or item.get("capture_path")),
                "required_env_vars": _text(
                    item.get("required_env_vars")
                    or item.get("capture_command_env_vars")
                    or item.get("provider_capture_command_env_vars")
                ),
                "command_base": _text(item.get("command_base") or item.get("capture_command_base") or item.get("provider_capture_command_base")),
                "command_template": command_template,
            }
        )
    return commands


def _provider_capture_commands_match(left: list[dict[str, str]], right: list[dict[str, str]]) -> bool:
    if not left or len(left) != len(right):
        return False
    return [_provider_capture_command_signature(item) for item in left] == [
        _provider_capture_command_signature(item) for item in right
    ]


def _provider_capture_command_signature(item: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        _text(item.get(key))
        for key in (
            "label",
            "provider",
            "transport",
            "endpoint",
            "kind",
            "exchange",
            "start_local",
            "end_local",
            "output",
            "required_env_vars",
            "command_base",
            "command_template",
        )
    )


def _unique_command_values(commands: list[dict[str, str]], key: str) -> str:
    values = sorted({_text(item.get(key)) for item in commands if _text(item.get(key))})
    return ";".join(values)


def _wall_clock_seconds(value: object) -> int | None:
    parts = _text(value).split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour * 3600 + minute * 60 + second


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _first_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame, column: str) -> bool:
    if frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(";") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "ready"}


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


def _shell_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() or ch in "'\"`" for ch in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
