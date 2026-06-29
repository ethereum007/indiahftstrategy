from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


BATCH_SUMMARY_NAME = "provider_market_data_batch_summary.csv"


@dataclass(frozen=True)
class ProviderMarketDataLiveEvidenceConfig:
    allow_synthetic_rehearsal: bool = False
    require_ingest_ready: bool = True
    require_batch_ready: bool = True
    require_manifest: bool = True
    min_capture_rows: int = 1


@dataclass(frozen=True)
class ProviderMarketDataLiveEvidenceReport:
    captures: pd.DataFrame
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


def write_provider_market_data_live_evidence_review(
    live_ingest_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLiveEvidenceConfig | None = None,
) -> ProviderMarketDataLiveEvidenceReport:
    report = evaluate_provider_market_data_live_evidence(live_ingest_dir, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.captures.to_csv(out / "provider_market_data_live_evidence_captures.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_evidence_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_evidence_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_evidence_action_queue.csv", index=False)
    (out / "provider_market_data_live_evidence_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_evidence_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.captures, report.action_queue),
        encoding="utf-8",
    )
    ingest_dir = Path(live_ingest_dir)
    inputs: dict[str, Any] = {"live_ingest_dir": ingest_dir} if ingest_dir.exists() else {}
    capture_bundle = _path_from_text(str(report.summary.iloc[0]["capture_bundle_path"]))
    if capture_bundle is not None and capture_bundle.exists():
        inputs["capture_bundle"] = capture_bundle
    capture_env_template = _path_from_text(str(report.summary.iloc[0]["capture_env_template_path"]))
    if capture_env_template is not None and capture_env_template.exists():
        inputs["capture_env_template"] = capture_env_template
    adapter_handoff = _path_from_text(str(report.summary.iloc[0]["adapter_handoff_path"]))
    if adapter_handoff is not None and adapter_handoff.exists():
        inputs["adapter_handoff"] = adapter_handoff
    source_env_template = _path_from_text(str(report.summary.iloc[0]["source_credential_env_template_path"]))
    if source_env_template is not None and source_env_template.exists():
        inputs["source_credential_env_template"] = source_env_template
    live_packet = Path(str(report.summary.iloc[0]["live_session_packet_path"]))
    if live_packet.exists():
        inputs["live_session_packet"] = live_packet
    capture_paths = [Path(str(path)) for path in report.captures["capture_path"].astype(str).tolist()] if not report.captures.empty else []
    if capture_paths:
        inputs["captures"] = [path for path in capture_paths if path.exists()]
    batch_manifest = Path(str(report.summary.iloc[0]["batch_output_dir"])) / "manifest.json"
    if batch_manifest.exists():
        inputs["batch_manifest"] = batch_manifest
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_evidence_review",
        parameters={"config": asdict(config or ProviderMarketDataLiveEvidenceConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "research_ready": bool(report.summary.iloc[0]["research_ready"]),
            "synthetic_capture_count": int(report.summary.iloc[0]["synthetic_capture_count"]),
            "blocked_action_count": int(report.summary.iloc[0]["blocked_action_count"]),
            "exchange": str(report.summary.iloc[0]["exchange"]),
            "source_session": _source_session_contract_from_summary(report.summary.iloc[0]),
            "market_session": _market_session_contract_from_summary(report.summary.iloc[0]),
            "capture_bundle_metadata_matches_session": bool(report.summary.iloc[0]["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                report.summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(report.summary.iloc[0]["provider_capture_command_count"]),
            "provider_capture_command_providers": str(report.summary.iloc[0]["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(report.summary.iloc[0]["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                report.summary.iloc[0]["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                report.summary.iloc[0]["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                report.summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
            ),
            "capture_bundle": {
                "exchange": str(report.summary.iloc[0]["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(report.summary.iloc[0]),
                "market_session": _capture_bundle_market_session_contract_from_summary(report.summary.iloc[0]),
                "provider_capture_commands": _list(
                    _mapping(report.config.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(
                    report.summary.iloc[0]["capture_bundle_provider_capture_command_count"]
                ),
                "provider_capture_commands_match_session": bool(
                    report.summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
                ),
                "metadata_matches_session": bool(report.summary.iloc[0]["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    report.summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "capture_env_template": {
                "path": str(report.summary.iloc[0]["capture_env_template_path"]),
                "exists": bool(report.summary.iloc[0]["capture_env_template_exists"]),
                "sha256": str(report.summary.iloc[0]["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(report.summary.iloc[0]["adapter_handoff_path"]),
                "provided": bool(report.summary.iloc[0]["adapter_handoff_provided"]),
                "exists": bool(report.summary.iloc[0]["adapter_handoff_exists"]),
                "sha256": str(report.summary.iloc[0]["adapter_handoff_sha256"]),
            },
            "source_credential_env_template": {
                "path": str(report.summary.iloc[0]["source_credential_env_template_path"]),
                "exists": bool(report.summary.iloc[0]["source_credential_env_template_exists"]),
                "sha256": str(report.summary.iloc[0]["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(report.summary.iloc[0]["source_live_fetch_contract_available"]),
                "next_gate": str(report.summary.iloc[0]["source_live_fetch_contract_next_gate"]),
                "command_template": str(report.summary.iloc[0]["source_live_fetch_contract_command_template"]),
                "exchange": str(report.summary.iloc[0]["source_live_fetch_contract_exchange"]),
                "market": str(report.summary.iloc[0]["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(report.summary.iloc[0]),
            },
            "provider_capture_commands": _list(report.config.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                _mapping(report.config.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
            ),
        },
    )
    return ProviderMarketDataLiveEvidenceReport(
        report.captures,
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_live_evidence(
    live_ingest_dir: str | Path,
    *,
    config: ProviderMarketDataLiveEvidenceConfig | None = None,
) -> ProviderMarketDataLiveEvidenceReport:
    config = _normalize_config(config or ProviderMarketDataLiveEvidenceConfig())
    ingest_dir = Path(live_ingest_dir)
    ingest_summary, summary_error = _read_csv(ingest_dir / "provider_market_data_live_ingest_summary.csv")
    ingest_windows, windows_error = _read_csv(ingest_dir / "provider_market_data_live_ingest_windows.csv")
    ingest_config, config_error = _read_json(ingest_dir / "provider_market_data_live_ingest_config.json")
    manifest, manifest_error = _read_json(ingest_dir / "manifest.json")
    live_packet_path = Path(_first_text(ingest_summary, "live_session_packet_path"))
    live_packet, packet_error = _read_json(live_packet_path)
    captures = _captures(ingest_windows, config)
    batch = _batch_status(ingest_summary, ingest_config)
    capture_provenance = _capture_provenance(ingest_config, manifest)
    checks = pd.DataFrame(
        _checks(
            ingest_dir,
            ingest_summary,
            summary_error,
            ingest_windows,
            windows_error,
            ingest_config,
            config_error,
            manifest,
            manifest_error,
            live_packet_path,
            live_packet,
            packet_error,
            captures,
            batch,
            capture_provenance,
            config,
        )
    )
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    research_ready = bool(ready and int(captures["synthetic_rehearsal"].astype(bool).sum()) == 0)
    action_queue = _action_queue(checks, ready, research_ready, captures)
    summary = _summary(
        ingest_dir,
        ingest_summary,
        live_packet_path,
        live_packet,
        captures,
        batch,
        capture_provenance,
        checks,
        action_queue,
        config,
        ready,
        research_ready,
    )
    evidence_config = _config(
        summary.iloc[0],
        ingest_dir,
        ingest_summary,
        ingest_config,
        manifest,
        live_packet,
        captures,
        batch,
        capture_provenance,
        checks,
        action_queue,
        config,
    )
    return ProviderMarketDataLiveEvidenceReport(captures, checks, summary, action_queue, evidence_config)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not str(path) or str(path) == ".":
        return {}, "JSON path is missing"
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


def _captures(windows: pd.DataFrame, config: ProviderMarketDataLiveEvidenceConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(windows.to_dict(orient="records") if not windows.empty else [], start=1):
        capture_path = Path(_text(row.get("capture_path")))
        sidecar_path = capture_path.with_suffix(capture_path.suffix + ".rehearsal.json") if str(capture_path) else Path("")
        sidecar, sidecar_error = _read_json(sidecar_path) if str(sidecar_path) and sidecar_path.exists() else ({}, "")
        capture_exists = bool(str(capture_path) and capture_path.exists() and capture_path.is_file())
        capture_rows = _capture_rows(capture_path) if capture_exists else 0
        synthetic = bool(sidecar_path.exists() and _truthy(sidecar.get("synthetic_only", True)))
        rows.append(
            {
                "priority": index,
                "label": _text(row.get("label"), f"window_{index}"),
                "pipeline_label": _text(row.get("pipeline_label"), _text(row.get("label"), f"window_{index}")),
                "capture_path": str(capture_path),
                "capture_exists": capture_exists,
                "capture_size_bytes": int(capture_path.stat().st_size) if capture_exists else 0,
                "capture_rows": int(capture_rows),
                "min_capture_rows": int(config.min_capture_rows),
                "row_count_ok": bool(capture_rows >= config.min_capture_rows),
                "rehearsal_sidecar_path": str(sidecar_path),
                "rehearsal_sidecar_exists": bool(sidecar_path.exists()),
                "synthetic_rehearsal": synthetic,
                "sidecar_source": _text(sidecar.get("source")),
                "sidecar_error": sidecar_error,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "label",
            "pipeline_label",
            "capture_path",
            "capture_exists",
            "capture_size_bytes",
            "capture_rows",
            "min_capture_rows",
            "row_count_ok",
            "rehearsal_sidecar_path",
            "rehearsal_sidecar_exists",
            "synthetic_rehearsal",
            "sidecar_source",
            "sidecar_error",
        ],
    )


def _capture_rows(path: Path) -> int:
    try:
        return int(len(pd.read_csv(path)))
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return 0


def _batch_status(summary: pd.DataFrame, ingest_config: dict[str, Any]) -> dict[str, Any]:
    batch_output = _first_text(summary, "batch_output_dir") or _text(_mapping(ingest_config.get("effective_batch_config")).get("batch_output_dir"))
    batch_dir = Path(batch_output)
    batch_summary_path = batch_dir / BATCH_SUMMARY_NAME
    batch_summary, batch_summary_error = _read_csv(batch_summary_path)
    batch_ready = _first_bool(batch_summary, "ready") if not batch_summary.empty else False
    return {
        "batch_output_dir": str(batch_dir),
        "batch_summary_path": str(batch_summary_path),
        "batch_summary_exists": bool(batch_summary_path.exists()),
        "batch_summary_error": batch_summary_error,
        "batch_ready": bool(batch_ready),
        "batch_dataset_count": int(_first_number(batch_summary, "dataset_count")) if not batch_summary.empty else 0,
    }


def _capture_provenance(ingest_config: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    bundle = _mapping(ingest_config.get("capture_bundle"))
    manifest_inputs = _mapping(manifest.get("inputs"))
    manifest_bundle = _mapping(manifest_inputs.get("capture_bundle"))
    manifest_env = _mapping(manifest_inputs.get("capture_env_template"))
    manifest_handoff = _mapping(manifest_inputs.get("adapter_handoff"))
    manifest_source_env = _mapping(manifest_inputs.get("source_credential_env_template"))
    manifest_extra = _mapping(manifest.get("extra"))
    manifest_extra_bundle = _mapping(manifest_extra.get("capture_bundle"))
    manifest_extra_capture_env = _mapping(manifest_extra.get("capture_env_template"))
    manifest_extra_handoff = _mapping(manifest_extra.get("adapter_handoff"))
    bundle_source_env = _mapping(bundle.get("source_credential_env_template"))
    manifest_extra_source_env = _mapping(manifest_extra.get("source_credential_env_template"))
    live_fetch_contract = _mapping(bundle.get("live_fetch_contract")) or _mapping(manifest_extra.get("live_fetch_contract"))
    live_fetch_session = _mapping(live_fetch_contract.get("session"))
    source_session = _mapping(bundle.get("source_session")) or _mapping(manifest_extra_bundle.get("source_session"))
    market_session = _mapping(bundle.get("market_session")) or _mapping(manifest_extra_bundle.get("market_session"))
    provider_capture_commands = _provider_capture_command_records(
        ingest_config.get("provider_capture_commands")
    ) or _provider_capture_command_records(manifest_extra.get("provider_capture_commands"))
    bundle_provider_capture_commands = _provider_capture_command_records(
        bundle.get("provider_capture_commands")
    ) or _provider_capture_command_records(manifest_extra.get("capture_bundle_provider_capture_commands"))
    reported_commands_match = _optional_bool(bundle.get("provider_capture_commands_match_session"))
    if reported_commands_match is None:
        reported_commands_match = _optional_bool(manifest_extra.get("capture_bundle_provider_capture_commands_match_session"))
    computed_commands_match = _provider_capture_commands_match(provider_capture_commands, bundle_provider_capture_commands)
    provider_commands_match = (
        computed_commands_match if reported_commands_match is None else bool(reported_commands_match and computed_commands_match)
    )
    bundle_path = _path_from_text(_text(bundle.get("path")) or _text(manifest_bundle.get("path")))
    env_template_path = _path_from_text(
        _text(bundle.get("env_template_path"))
        or _text(manifest_env.get("path"))
    )
    adapter_handoff_path = _path_from_text(
        _text(bundle.get("adapter_handoff_path"))
        or _text(manifest_handoff.get("path"))
    )
    source_env_template_path = _path_from_text(
        _text(bundle_source_env.get("path"))
        or _text(manifest_source_env.get("path"))
        or _text(manifest_extra_source_env.get("path"))
    )
    return {
        "capture_bundle_path": _path_text(bundle_path),
        "capture_bundle_provided": bool(bundle_path),
        "capture_bundle_exists": bool(bundle_path is not None and bundle_path.exists()),
        "capture_bundle_ready": _truthy(bundle.get("ready")),
        "capture_env_template_path": _path_text(env_template_path),
        "capture_env_template_provided": bool(env_template_path),
        "capture_env_template_exists": bool(env_template_path is not None and env_template_path.exists()),
        "capture_env_template_sha256": _text(bundle.get("env_template_sha256"))
        or _text(manifest_env.get("sha256"))
        or _text(manifest_extra_capture_env.get("sha256")),
        "adapter_handoff_path": _path_text(adapter_handoff_path),
        "adapter_handoff_provided": bool(adapter_handoff_path),
        "adapter_handoff_exists": bool(
            adapter_handoff_path is not None and adapter_handoff_path.exists()
        ),
        "adapter_handoff_sha256": _text(bundle.get("adapter_handoff_sha256"))
        or _text(manifest_handoff.get("sha256"))
        or _text(manifest_extra_handoff.get("sha256")),
        "source_credential_env_template_path": _path_text(source_env_template_path),
        "source_credential_env_template_provided": bool(source_env_template_path),
        "source_credential_env_template_exists": bool(
            source_env_template_path is not None and source_env_template_path.exists()
        ),
        "source_credential_env_template_sha256": _text(
            bundle_source_env.get("sha256")
        )
        or _text(manifest_source_env.get("sha256"))
        or _text(manifest_extra_source_env.get("sha256")),
        "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
        "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
        "source_live_fetch_contract_command_template": _text(live_fetch_contract.get("command_template")),
        "source_live_fetch_contract_exchange": _text(live_fetch_contract.get("exchange")),
        "source_live_fetch_contract_market": _text(live_fetch_contract.get("market")),
        "source_live_fetch_contract_session_timezone": _text(live_fetch_session.get("timezone")),
        "source_live_fetch_contract_session_open_local": _text(live_fetch_session.get("open_local")),
        "source_live_fetch_contract_session_close_local": _text(live_fetch_session.get("close_local")),
        "provider_capture_commands": provider_capture_commands,
        "provider_capture_command_count": int(len(provider_capture_commands)),
        "provider_capture_command_providers": _unique_command_values(provider_capture_commands, "provider"),
        "provider_capture_command_transports": _unique_command_values(provider_capture_commands, "transport"),
        "capture_bundle_provider_capture_commands": bundle_provider_capture_commands,
        "capture_bundle_provider_capture_command_count": int(len(bundle_provider_capture_commands)),
        "capture_bundle_provider_capture_commands_match_session": provider_commands_match,
        "capture_bundle_exchange": _text(bundle.get("exchange")) or _text(manifest_extra_bundle.get("exchange")),
        "capture_bundle_source_session": source_session,
        "capture_bundle_market_session": market_session,
        "capture_bundle_metadata_matches_session": _coalesced_bool(
            bundle.get("metadata_matches_session"),
            manifest_extra_bundle.get("metadata_matches_session"),
            manifest_extra.get("capture_bundle_metadata_matches_session"),
        ),
        "capture_bundle_live_fetch_contract_metadata_matches_session": _coalesced_bool(
            bundle.get("live_fetch_contract_metadata_matches_session"),
            manifest_extra_bundle.get("live_fetch_contract_metadata_matches_session"),
            manifest_extra.get("capture_bundle_live_fetch_contract_metadata_matches_session"),
        ),
    }


def _checks(
    ingest_dir: Path,
    ingest_summary: pd.DataFrame,
    summary_error: str,
    ingest_windows: pd.DataFrame,
    windows_error: str,
    ingest_config: dict[str, Any],
    config_error: str,
    manifest: dict[str, Any],
    manifest_error: str,
    live_packet_path: Path,
    live_packet: dict[str, Any],
    packet_error: str,
    captures: pd.DataFrame,
    batch: dict[str, Any],
    capture_provenance: dict[str, Any],
    config: ProviderMarketDataLiveEvidenceConfig,
) -> list[dict[str, Any]]:
    capture_count = int(len(captures))
    synthetic_count = int(captures["synthetic_rehearsal"].astype(bool).sum()) if not captures.empty else 0
    captures_exist = bool(captures["capture_exists"].astype(bool).all()) if not captures.empty else False
    row_counts_ok = bool(captures["row_count_ok"].astype(bool).all()) if not captures.empty else False
    ingest_ready = _first_bool(ingest_summary, "ready")
    summary_packet = _first_text(ingest_summary, "live_session_packet_path")
    bundle_provided = bool(capture_provenance["capture_bundle_provided"])
    bundle_source_session = _mapping(capture_provenance.get("capture_bundle_source_session"))
    bundle_market_session = _mapping(capture_provenance.get("capture_bundle_market_session"))
    packet_source_session = _mapping(live_packet.get("source_session"))
    packet_market_session = _mapping(live_packet.get("market_session"))
    bundle_metadata_matches_session = _capture_bundle_metadata_matches_packet(live_packet, capture_provenance)
    live_fetch_metadata_matches_session = _live_contract_metadata_matches_packet(live_packet, capture_provenance)
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
    return [
        _check("live_ingest_dir_exists", str(ingest_dir), "exists", True, ingest_dir.exists(), "live ingest directory is required"),
        _check("live_ingest_summary_readable", summary_error or "ok", "is", "ok", not summary_error, summary_error or "live ingest summary could not be read"),
        _check("live_ingest_windows_readable", windows_error or "ok", "is", "ok", not windows_error, windows_error or "live ingest windows could not be read"),
        _check("live_ingest_config_readable", config_error or "ok", "is", "ok", not config_error, config_error or "live ingest config could not be read"),
        _check("live_ingest_manifest_exists", manifest_error or "ok", "is", "ok", not manifest_error or not config.require_manifest, manifest_error or "live ingest manifest is required"),
        _check("live_ingest_manifest_type", _text(manifest.get("run_type")), "is", "provider_market_data_live_session_ingest", _text(manifest.get("run_type")) == "provider_market_data_live_session_ingest" or not config.require_manifest, "live ingest manifest run_type is not the expected provider live ingest"),
        _check("capture_bundle_exists", capture_provenance["capture_bundle_path"], "exists", True, bool(capture_provenance["capture_bundle_exists"]) if bundle_provided else True, "capture bundle referenced by ingest provenance is missing"),
        _check("capture_env_template_exists", capture_provenance["capture_env_template_path"], "exists", True, bool(capture_provenance["capture_env_template_exists"]) if bundle_provided else True, "credential env-template referenced by ingest provenance is missing"),
        _check("capture_env_template_fingerprinted", capture_provenance["capture_env_template_sha256"], "has", "sha256", bool(capture_provenance["capture_env_template_sha256"]) if bundle_provided else True, "credential env-template fingerprint is missing from ingest provenance"),
        _check("adapter_handoff_exists", capture_provenance["adapter_handoff_path"], "exists", True, bool(capture_provenance["adapter_handoff_exists"]) if bool(capture_provenance["adapter_handoff_provided"]) else True, "adapter handoff referenced by ingest provenance is missing"),
        _check("adapter_handoff_fingerprinted", capture_provenance["adapter_handoff_sha256"], "has", "sha256", bool(capture_provenance["adapter_handoff_sha256"]) if bool(capture_provenance["adapter_handoff_provided"]) else True, "adapter handoff fingerprint is missing from ingest provenance"),
        _check("capture_bundle_source_credential_env_template_carried", capture_provenance["source_credential_env_template_path"], "exists", True, bool(capture_provenance["source_credential_env_template_exists"]) and bool(capture_provenance["source_credential_env_template_sha256"]) if bundle_provided else True, "source credential env-template referenced by ingest provenance is missing"),
        _check("capture_bundle_live_fetch_contract_carried", bool(capture_provenance["source_live_fetch_contract_available"]), "is", True, bool(capture_provenance["source_live_fetch_contract_available"]) and str(capture_provenance["source_live_fetch_contract_next_gate"]) == "provider_fetcher" if bundle_provided else True, "live fetch-contract referenced by ingest provenance is missing"),
        _check("capture_bundle_provider_capture_commands_carried", bundle_provider_capture_command_count, "==", provider_capture_command_count, bundle_provider_capture_commands_carried if bundle_provided else True, "capture bundle provider capture command handoffs are missing from ingest provenance"),
        _check("capture_bundle_provider_capture_commands_match_session", bundle_provider_capture_command_count, "matches", provider_capture_command_count, bundle_provider_capture_commands_match_session if bundle_provided else True, "capture bundle provider capture command handoffs must match the live session packet"),
        _check("capture_bundle_exchange_carried", capture_provenance["capture_bundle_exchange"], "is_not", "", bool(capture_provenance["capture_bundle_exchange"]) if bundle_provided else True, "capture bundle exchange metadata is missing from ingest provenance"),
        _check("capture_bundle_source_session_carried", _session_contract_text(bundle_source_session), "has", "timezone/open/close", _session_contract_carried(bundle_source_session) if bundle_provided else True, "capture bundle source-session metadata is missing from ingest provenance"),
        _check("capture_bundle_market_session_carried", _session_contract_text(bundle_market_session), "has", "timezone/open/close", _session_contract_carried(bundle_market_session) if bundle_provided else True, "capture bundle market-session metadata is missing from ingest provenance"),
        _check("capture_bundle_metadata_matches_session", _session_contract_text(bundle_source_session), "==", _session_contract_text(packet_source_session), bool(capture_provenance["capture_bundle_metadata_matches_session"]) and bundle_metadata_matches_session if bundle_provided else True, "capture bundle exchange/session metadata must match the live session packet"),
        _check("capture_bundle_live_fetch_contract_metadata_matches_session", _live_contract_metadata_text(capture_provenance), "==", "live session source metadata", bool(capture_provenance["capture_bundle_live_fetch_contract_metadata_matches_session"]) and live_fetch_metadata_matches_session if bundle_provided else True, "capture bundle live fetch-contract exchange/session metadata must match the live session packet"),
        _check("live_ingest_ready", ingest_ready, "is", True, ingest_ready or not config.require_ingest_ready, "live ingest summary is not ready"),
        _check("live_session_packet_path_present", summary_packet, "is_not", "", bool(summary_packet), "live ingest summary must point to the live session packet"),
        _check("live_session_packet_json_readable", packet_error or "ok", "is", "ok", not packet_error, packet_error or "live session packet could not be read"),
        _check("credential_values_not_stored", bool(_mapping(live_packet.get("authentication")).get("values_stored", True)), "is", False, bool(_mapping(live_packet.get("authentication")).get("values_stored", True)) is False, "live session packet must not store credential values"),
        _check("capture_windows_present", capture_count, ">=", 1, capture_count >= 1, "live evidence requires at least one capture window"),
        _check("capture_files_exist", int(captures["capture_exists"].astype(bool).sum()) if not captures.empty else 0, "==", capture_count, captures_exist, "all expected capture files must exist"),
        _check("capture_rows_meet_minimum", int(captures["row_count_ok"].astype(bool).sum()) if not captures.empty else 0, "==", capture_count, row_counts_ok, "all captures must meet minimum row count"),
        _check("synthetic_rehearsal_absent", synthetic_count, "==", 0 if not config.allow_synthetic_rehearsal else "allowed", synthetic_count == 0 or config.allow_synthetic_rehearsal, "synthetic rehearsal captures cannot be treated as live provider evidence"),
        _check("batch_summary_exists", bool(batch["batch_summary_exists"]), "is", True, bool(batch["batch_summary_exists"]), "provider batch summary is required"),
        _check("batch_ready", bool(batch["batch_ready"]), "is", True, bool(batch["batch_ready"]) or not config.require_batch_ready, "provider batch summary is not ready"),
    ]


def _summary(
    ingest_dir: Path,
    ingest_summary: pd.DataFrame,
    live_packet_path: Path,
    live_packet: dict[str, Any],
    captures: pd.DataFrame,
    batch: dict[str, Any],
    capture_provenance: dict[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveEvidenceConfig,
    ready: bool,
    research_ready: bool,
) -> pd.DataFrame:
    synthetic_count = int(captures["synthetic_rehearsal"].astype(bool).sum()) if not captures.empty else 0
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    source_session = _mapping(live_packet.get("source_session"))
    market_session = _mapping(live_packet.get("market_session"))
    bundle_source_session = _mapping(capture_provenance.get("capture_bundle_source_session"))
    bundle_market_session = _mapping(capture_provenance.get("capture_bundle_market_session"))
    provider_capture_command_count = int(capture_provenance["provider_capture_command_count"])
    bundle_provider_capture_command_count = int(capture_provenance["capture_bundle_provider_capture_command_count"])
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "research_ready": research_ready,
                "synthetic_only": bool(synthetic_count > 0),
                "live_ingest_dir": str(ingest_dir),
                "live_session_packet_path": str(live_packet_path),
                "capture_bundle_path": str(capture_provenance["capture_bundle_path"]),
                "capture_bundle_provided": bool(capture_provenance["capture_bundle_provided"]),
                "capture_bundle_ready": bool(capture_provenance["capture_bundle_ready"]),
                "capture_env_template_path": str(capture_provenance["capture_env_template_path"]),
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
                "provider": _text(live_packet.get("provider"), _first_text(ingest_summary, "provider")),
                "transport": _text(live_packet.get("transport"), _first_text(ingest_summary, "transport")),
                "market": _text(live_packet.get("market"), _first_text(ingest_summary, "market")),
                "exchange": _text(live_packet.get("exchange"), _first_text(ingest_summary, "exchange")),
                "kind": _text(live_packet.get("kind"), _first_text(ingest_summary, "kind")),
                "source_session_timezone": _text(source_session.get("timezone"), _first_text(ingest_summary, "source_session_timezone")),
                "source_session_open_local": _text(source_session.get("open_local"), _first_text(ingest_summary, "source_session_open_local")),
                "source_session_close_local": _text(source_session.get("close_local"), _first_text(ingest_summary, "source_session_close_local")),
                "market_session_timezone": _text(market_session.get("timezone"), _first_text(ingest_summary, "market_session_timezone")),
                "market_session_open_local": _text(market_session.get("open_local"), _first_text(ingest_summary, "market_session_open_local")),
                "market_session_close_local": _text(market_session.get("close_local"), _first_text(ingest_summary, "market_session_close_local")),
                "capture_bundle_exchange": str(capture_provenance["capture_bundle_exchange"]),
                "capture_bundle_source_session_timezone": _text(bundle_source_session.get("timezone")),
                "capture_bundle_source_session_open_local": _text(bundle_source_session.get("open_local")),
                "capture_bundle_source_session_close_local": _text(bundle_source_session.get("close_local")),
                "capture_bundle_market_session_timezone": _text(bundle_market_session.get("timezone")),
                "capture_bundle_market_session_open_local": _text(bundle_market_session.get("open_local")),
                "capture_bundle_market_session_close_local": _text(bundle_market_session.get("close_local")),
                "capture_bundle_metadata_matches_session": bool(capture_provenance["capture_bundle_metadata_matches_session"])
                and _capture_bundle_metadata_matches_packet(live_packet, capture_provenance)
                if bool(capture_provenance["capture_bundle_provided"])
                else True,
                "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                    capture_provenance["capture_bundle_live_fetch_contract_metadata_matches_session"]
                )
                and _live_contract_metadata_matches_packet(live_packet, capture_provenance)
                if bool(capture_provenance["capture_bundle_provided"])
                else True,
                "capture_count": int(len(captures)),
                "synthetic_capture_count": synthetic_count,
                "min_capture_rows": int(config.min_capture_rows),
                "batch_output_dir": str(batch["batch_output_dir"]),
                "batch_ready": bool(batch["batch_ready"]),
                "allow_synthetic_rehearsal": bool(config.allow_synthetic_rehearsal),
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0,
                "blocked_action_count": blocked,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": _recommendation(ready, research_ready, synthetic_count),
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, ready: bool, research_ready: bool, captures: pd.DataFrame) -> pd.DataFrame:
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
    synthetic_count = int(captures["synthetic_rehearsal"].astype(bool).sum()) if not captures.empty else 0
    if not rows and ready and research_ready:
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "feed_live_provider_market_data_to_research",
                "reason": "live ingest passed and no synthetic rehearsal captures were detected",
                "next_gate": "review-data-readiness",
                "next_gate_help_command": "batch output contains provider live data-readiness evidence for research",
            }
        )
    elif not rows and ready and synthetic_count > 0:
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "replace_synthetic_captures_with_provider_live_captures",
                "reason": "synthetic rehearsal evidence passed only as backend smoke test",
                "next_gate": "provider_fetcher_live_run",
                "next_gate_help_command": "run the approved provider adapter against Arrow.money/iRage, then rerun ingest and live evidence review",
            }
        )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _config(
    summary: pd.Series,
    ingest_dir: Path,
    ingest_summary: pd.DataFrame,
    ingest_config: dict[str, Any],
    manifest: dict[str, Any],
    live_packet: dict[str, Any],
    captures: pd.DataFrame,
    batch: dict[str, Any],
    capture_provenance: dict[str, Any],
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveEvidenceConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "research_ready": bool(summary["research_ready"]),
        "synthetic_only": bool(summary["synthetic_only"]),
        "parameters": asdict(config),
        "live_ingest_dir": str(ingest_dir),
        "ingest_summary": _first_record(ingest_summary),
        "ingest_config": ingest_config,
        "ingest_manifest_run_type": _text(manifest.get("run_type")),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_capture_commands": _list(capture_provenance.get("provider_capture_commands")),
        "capture_bundle_provider_capture_commands": _list(
            capture_provenance.get("capture_bundle_provider_capture_commands")
        ),
        "capture_bundle": capture_provenance,
        "live_session_packet": _safe_packet(live_packet),
        "captures": _records(captures),
        "batch": batch,
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": actions[0] if actions else {},
    }


def _safe_packet(packet: dict[str, Any]) -> dict[str, Any]:
    auth = _mapping(packet.get("authentication"))
    return {
        "schema_version": packet.get("schema_version"),
        "ready": bool(packet.get("ready")),
        "provider": _text(packet.get("provider")),
        "transport": _text(packet.get("transport")),
        "market": _text(packet.get("market")),
        "exchange": _text(packet.get("exchange")),
        "kind": _text(packet.get("kind")),
        "source_session": _mapping(packet.get("source_session")),
        "market_session": _mapping(packet.get("market_session")),
        "client_packet_path": _text(packet.get("client_packet_path")),
        "authentication": {
            "env_vars": _string_list(auth.get("env_vars")),
            "values_stored": bool(auth.get("values_stored", True)),
            "injection": _text(auth.get("injection")),
        },
        "capture_window_count": len(_list(packet.get("capture_windows"))),
    }


def _recommendation(ready: bool, research_ready: bool, synthetic_count: int) -> str:
    if research_ready:
        return "feed_walkforward_research"
    if ready and synthetic_count > 0:
        return "rehearsal_backend_smoke_only"
    return "fix_provider_market_data_live_evidence"


def _next_gate_for_check(check: str) -> str:
    if check.startswith("live_ingest"):
        return "ingest-provider-market-data-live-session"
    if (
        check.startswith("capture_bundle")
        or check.startswith("capture_env_template")
        or check.startswith("adapter_handoff")
    ):
        return "bundle-provider-market-data-live-capture"
    if check.startswith("live_session_packet") or check.startswith("credential"):
        return "plan-provider-market-data-live-session"
    if check.startswith("capture"):
        return "provider_fetcher_live_run"
    if check.startswith("synthetic"):
        return "provider_fetcher_live_run"
    if check.startswith("batch"):
        return "pipeline-provider-market-data-batch"
    return "review-provider-market-data-live-evidence"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "ingest-provider-market-data-live-session",
        "bundle-provider-market-data-live-capture",
        "plan-provider-market-data-live-session",
        "pipeline-provider-market-data-batch",
        "review-provider-market-data-live-evidence",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_fetcher_live_run":
        return "run the approved provider adapter against Arrow.money/iRage and replace rehearsal captures"
    if next_gate == "review-data-readiness":
        return "batch output contains provider live data-readiness evidence for research"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("live_ingest"):
        return "repair_provider_live_ingest_artifacts"
    if check == "capture_bundle_source_credential_env_template_carried":
        return "regenerate_capture_bundle_with_source_env_template"
    if check == "capture_bundle_live_fetch_contract_carried":
        return "regenerate_capture_bundle_with_live_fetch_contract"
    if check == "capture_bundle_provider_capture_commands_carried":
        return "regenerate_capture_bundle_with_provider_capture_commands"
    if check == "capture_bundle_provider_capture_commands_match_session":
        return "regenerate_capture_bundle_with_session_provider_capture_commands"
    if check in {
        "capture_bundle_exchange_carried",
        "capture_bundle_source_session_carried",
        "capture_bundle_market_session_carried",
        "capture_bundle_metadata_matches_session",
    }:
        return "regenerate_capture_bundle_with_session_metadata"
    if check == "capture_bundle_live_fetch_contract_metadata_matches_session":
        return "regenerate_capture_bundle_with_live_fetch_contract_metadata"
    if (
        check.startswith("capture_bundle")
        or check.startswith("capture_env_template")
        or check.startswith("adapter_handoff")
    ):
        return "repair_provider_live_capture_bundle"
    if check.startswith("live_session_packet") or check.startswith("credential"):
        return "repair_provider_live_session_packet"
    if check.startswith("capture"):
        return "produce_real_provider_live_captures"
    if check.startswith("synthetic"):
        return "replace_synthetic_rehearsal_captures"
    if check.startswith("batch"):
        return "repair_provider_market_data_batch"
    return "repair_provider_market_data_live_evidence"


def _runbook_markdown(summary: pd.Series, captures: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Evidence Review",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Research ready: {'yes' if bool(summary['research_ready']) else 'no'}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Synthetic captures: {summary['synthetic_capture_count']}",
        f"- Batch ready: {'yes' if bool(summary['batch_ready']) else 'no'}",
        f"- Recommendation: {summary['recommendation']}",
        "",
        "## Captures",
        "",
        _captures_table(captures),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _captures_table(captures: pd.DataFrame) -> str:
    if captures.empty:
        return "_None_"
    rows = []
    for row in captures.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("label")),
                _text(row.get("capture_path")),
                str(row.get("capture_rows", "")),
                "yes" if _truthy(row.get("synthetic_rehearsal")) else "no",
            ]
        )
    return _markdown_table(["#", "Label", "Capture", "Rows", "Synthetic"], rows)


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


def _normalize_config(config: ProviderMarketDataLiveEvidenceConfig) -> ProviderMarketDataLiveEvidenceConfig:
    return ProviderMarketDataLiveEvidenceConfig(
        allow_synthetic_rehearsal=bool(config.allow_synthetic_rehearsal),
        require_ingest_ready=bool(config.require_ingest_ready),
        require_batch_ready=bool(config.require_batch_ready),
        require_manifest=bool(config.require_manifest),
        min_capture_rows=int(config.min_capture_rows),
    )


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


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


def _capture_bundle_metadata_matches_packet(packet: dict[str, Any], capture_provenance: dict[str, Any]) -> bool:
    return (
        _text(capture_provenance.get("capture_bundle_exchange")) == _text(packet.get("exchange"))
        and _session_contracts_match(
            _mapping(capture_provenance.get("capture_bundle_source_session")),
            _mapping(packet.get("source_session")),
        )
        and _session_contracts_match(
            _mapping(capture_provenance.get("capture_bundle_market_session")),
            _mapping(packet.get("market_session")),
        )
    )


def _live_contract_metadata_matches_packet(packet: dict[str, Any], capture_provenance: dict[str, Any]) -> bool:
    if not bool(capture_provenance.get("source_live_fetch_contract_available")):
        return True
    contract_session = {
        "timezone": _text(capture_provenance.get("source_live_fetch_contract_session_timezone")),
        "open_local": _text(capture_provenance.get("source_live_fetch_contract_session_open_local")),
        "close_local": _text(capture_provenance.get("source_live_fetch_contract_session_close_local")),
    }
    return (
        _text(capture_provenance.get("source_live_fetch_contract_exchange")) == _text(packet.get("exchange"))
        and _text(capture_provenance.get("source_live_fetch_contract_market")) == _text(packet.get("market"))
        and _session_contracts_match(contract_session, _mapping(packet.get("source_session")))
    )


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


def _live_contract_metadata_text(capture_provenance: dict[str, Any]) -> str:
    session = {
        "timezone": _text(capture_provenance.get("source_live_fetch_contract_session_timezone")),
        "open_local": _text(capture_provenance.get("source_live_fetch_contract_session_open_local")),
        "close_local": _text(capture_provenance.get("source_live_fetch_contract_session_close_local")),
    }
    return (
        f"{_text(capture_provenance.get('source_live_fetch_contract_market'))}|"
        f"{_text(capture_provenance.get('source_live_fetch_contract_exchange'))}|"
        f"{_session_contract_text(session)}"
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


def _first_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame, column: str) -> bool:
    if frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    try:
        return float(frame.iloc[0][column])
    except (TypeError, ValueError):
        return 0.0


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


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


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


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
