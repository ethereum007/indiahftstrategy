from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.catalog import ExperimentCatalog, write_experiment_catalog
from reports.evidence import (
    EvidenceThresholds,
    StrategyEvidenceReview,
    evidence_profile_run_types,
    write_strategy_evidence_review,
)
from reports.manifest import write_experiment_manifest


PROFILE = "provider_imbalance_research"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceEvidenceConfig:
    require_provider_research_ready: bool = True
    require_strategy_evidence_ready: bool = True
    allow_dirty_git: bool = False
    require_same_git_commit: bool = False
    require_same_strategy: bool = True
    require_same_market: bool = True
    expected_market: str = ""
    min_passed_per_type: int = 1
    require_file_inputs: bool = False


@dataclass(frozen=True)
class ProviderMarketDataImbalanceEvidenceReport:
    catalog: ExperimentCatalog | None
    evidence: StrategyEvidenceReview | None
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


def write_provider_market_data_imbalance_evidence_review(
    provider_research_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceEvidenceConfig | None = None,
) -> ProviderMarketDataImbalanceEvidenceReport:
    config = config or ProviderMarketDataImbalanceEvidenceConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    provider_dir = Path(provider_research_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_dir / "provider_market_data_imbalance_research_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_dir / "provider_market_data_imbalance_research_config.json"
    )
    provider_manifest, provider_manifest_error = _read_json(
        provider_dir / "manifest.json"
    )
    catalog = None
    evidence = None
    catalog_error = ""
    evidence_error = ""
    catalog_dir = out / "catalog"
    evidence_dir = out / "strategy_evidence"
    if provider_dir.exists():
        try:
            catalog = write_experiment_catalog([provider_dir], output_dir=catalog_dir)
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            catalog_error = str(exc)
        if catalog is not None:
            try:
                evidence = write_strategy_evidence_review(
                    catalog.output_dir / "experiment_catalog.csv",
                    output_dir=evidence_dir,
                    thresholds=EvidenceThresholds(
                        required_run_types=evidence_profile_run_types(PROFILE),
                        min_passed_per_type=config.min_passed_per_type,
                        allow_dirty_git=config.allow_dirty_git,
                        require_same_git_commit=config.require_same_git_commit,
                        require_same_strategy=config.require_same_strategy,
                        require_same_market=config.require_same_market,
                        expected_strategy="imbalance",
                        expected_market=config.expected_market or _first_text(provider_summary, "market") or None,
                        require_file_inputs=config.require_file_inputs,
                    ),
                )
            except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
                evidence_error = str(exc)
    checks = _checks(
        provider_dir,
        provider_summary,
        provider_summary_error,
        provider_config,
        provider_config_error,
        provider_manifest,
        provider_manifest_error,
        catalog,
        catalog_error,
        evidence,
        evidence_error,
        config,
    )
    summary = _summary(
        provider_dir,
        provider_summary,
        provider_config,
        provider_manifest,
        catalog,
        evidence,
        checks,
        out,
        catalog_dir,
        evidence_dir,
        config,
    )
    action_queue = _action_queue(summary.iloc[0], provider_dir, catalog, evidence)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        provider_manifest,
        catalog,
        evidence,
        checks,
        action_queue,
        config,
    )

    checks.to_csv(out / "provider_market_data_imbalance_evidence_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_evidence_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_evidence_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_evidence_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_evidence_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"provider_research_dir": provider_dir}
    if catalog is not None and catalog.output_dir is not None:
        inputs["catalog"] = catalog.output_dir
    if evidence is not None and evidence.output_dir is not None:
        inputs["strategy_evidence"] = evidence.output_dir
    summary_row = summary.iloc[0]
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
    receipt_paths = [
        _path_from_text(_text(_mapping(item).get("adapter_receipt_path")))
        for item in _list(_mapping(payload.get("adapter_receipt_proof")).get("receipts"))
    ]
    existing_receipts = [
        path for path in receipt_paths if path is not None and path.exists() and path.is_file()
    ]
    if existing_receipts:
        inputs["adapter_receipts"] = existing_receipts
    write_experiment_manifest(
        out,
        run_type="provider_market_data_imbalance_evidence_review",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "provider_research_ready": bool(summary.iloc[0]["provider_research_ready"]),
            "strategy_evidence_ready": bool(summary.iloc[0]["strategy_evidence_ready"]),
            "evidence_profile": PROFILE,
            "exchange": str(summary.iloc[0]["exchange"]),
            "source_session": _source_session_contract_from_summary(summary.iloc[0]),
            "market_session": _market_session_contract_from_summary(summary.iloc[0]),
            "provider_profile": _mapping(payload.get("provider_profile")),
            "adapter_receipt_proof": _mapping(payload.get("adapter_receipt_proof")),
            "provider_profile_matches_session": bool(summary.iloc[0]["provider_profile_matches_session"]),
            "provider_profile_matches_bundle": bool(summary.iloc[0]["provider_profile_matches_bundle"]),
            "synthetic_sidecar_proof": _mapping(payload.get("synthetic_sidecar_proof")),
            "synthetic_dataset_count": int(summary.iloc[0]["synthetic_dataset_count"]),
            "synthetic_sidecar_proof_ready": bool(summary.iloc[0]["synthetic_sidecar_proof_ready"]),
            "synthetic_sidecar_count": int(summary.iloc[0]["synthetic_sidecar_count"]),
            "synthetic_sidecar_readable_count": int(summary.iloc[0]["synthetic_sidecar_readable_count"]),
            "capture_bundle_provided": bool(summary.iloc[0]["capture_bundle_provided"]),
            "capture_env_template_exists": bool(summary.iloc[0]["capture_env_template_exists"]),
            "adapter_handoff_exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
            "capture_env_template": {
                "path": str(summary.iloc[0]["capture_env_template_path"]),
                "exists": bool(summary.iloc[0]["capture_env_template_exists"]),
                "sha256": str(summary.iloc[0]["capture_env_template_sha256"]),
            },
            "adapter_handoff": {
                "path": str(summary.iloc[0]["adapter_handoff_path"]),
                "exists": bool(summary.iloc[0]["adapter_handoff_exists"]),
                "sha256": str(summary.iloc[0]["adapter_handoff_sha256"]),
            },
            "capture_bundle_metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "provider_capture_command_count": int(summary.iloc[0]["provider_capture_command_count"]),
            "provider_capture_command_providers": str(summary.iloc[0]["provider_capture_command_providers"]),
            "provider_capture_command_transports": str(summary.iloc[0]["provider_capture_command_transports"]),
            "capture_bundle_provider_capture_command_count": int(
                summary.iloc[0]["capture_bundle_provider_capture_command_count"]
            ),
            "capture_bundle_provider_capture_command_missing_count": int(
                summary.iloc[0]["capture_bundle_provider_capture_command_missing_count"]
            ),
            "capture_bundle_provider_capture_commands_match_session": bool(
                summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
            ),
            "adapter_execution_contract": _mapping(payload.get("adapter_execution_contract")),
            "adapter_contract_provider_profile_sha256": str(
                summary.iloc[0]["adapter_contract_provider_profile_sha256"]
            ),
            "adapter_contract_provider_profile_matches_evidence": bool(
                summary.iloc[0]["adapter_contract_provider_profile_matches_evidence"]
            ),
            "capture_bundle": {
                "exchange": str(summary.iloc[0]["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary.iloc[0]),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary.iloc[0]),
                "provider_profile": _mapping(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_profile")
                ),
                "provider_capture_commands": _list(
                    _mapping(payload.get("capture_bundle")).get("capture_bundle_provider_capture_commands")
                ),
                "provider_capture_command_count": int(
                    summary.iloc[0]["capture_bundle_provider_capture_command_count"]
                ),
                "provider_capture_commands_match_session": bool(
                    summary.iloc[0]["capture_bundle_provider_capture_commands_match_session"]
                ),
                "adapter_execution_contract": _mapping(
                    _mapping(payload.get("capture_bundle")).get("adapter_execution_contract")
                ),
                "adapter_receipt_proof": _mapping(
                    payload.get("adapter_receipt_proof")
                ),
                "metadata_matches_session": bool(summary.iloc[0]["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary.iloc[0]["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary.iloc[0]["source_credential_env_template_path"]),
                "exists": bool(summary.iloc[0]["source_credential_env_template_exists"]),
                "sha256": str(summary.iloc[0]["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary.iloc[0]["source_live_fetch_contract_available"]),
                "next_gate": str(summary.iloc[0]["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary.iloc[0]["source_live_fetch_contract_command_template"]),
                "exchange": str(summary.iloc[0]["source_live_fetch_contract_exchange"]),
                "market": str(summary.iloc[0]["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary.iloc[0]),
            },
            "provider_capture_commands": _list(payload.get("provider_capture_commands")),
            "capture_bundle_provider_capture_commands": _list(
                payload.get("capture_bundle_provider_capture_commands")
            ),
        },
    )
    return ProviderMarketDataImbalanceEvidenceReport(catalog, evidence, checks, summary, action_queue, payload, out)


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


def _checks(
    provider_dir: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    provider_config: dict[str, Any],
    provider_config_error: str,
    provider_manifest: dict[str, Any],
    provider_manifest_error: str,
    catalog: ExperimentCatalog | None,
    catalog_error: str,
    evidence: StrategyEvidenceReview | None,
    evidence_error: str,
    config: ProviderMarketDataImbalanceEvidenceConfig,
) -> pd.DataFrame:
    provider_ready = _first_bool(provider_summary, "ready")
    evidence_ready = bool(evidence.ready) if evidence is not None else False
    catalog_count = 0 if catalog is None else catalog.run_count
    evidence_summary = evidence.summary if evidence is not None else pd.DataFrame()
    passed_required = int(_first_number(evidence_summary, "passed_required_run_types"))
    required_count = int(_first_number(evidence_summary, "required_run_type_count"))
    bundle_provided = _first_bool(provider_summary, "capture_bundle_provided")
    provider_capture_command_count = int(_first_number(provider_summary, "provider_capture_command_count"))
    bundle_provider_capture_command_count = int(
        _first_number(provider_summary, "capture_bundle_provider_capture_command_count")
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(provider_summary, "capture_bundle_provider_capture_command_missing_count")
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(provider_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    adapter_contract_carried = (
        bool(_first_text(provider_summary, "adapter_contract_provider"))
        and bool(_first_text(provider_summary, "adapter_contract_transport"))
        and bool(_first_text(provider_summary, "adapter_contract_market"))
        and bool(_first_text(provider_summary, "adapter_contract_exchange"))
        and not _first_bool(provider_summary, "adapter_contract_values_stored")
    )
    provider_profile_carried = (
        bool(_first_text(provider_summary, "provider_profile_sha256"))
        and bool(_first_text(provider_summary, "provider_profile_adapter"))
        and bool(_first_text(provider_summary, "provider_profile_transports"))
    )
    synthetic_dataset_count = int(_first_number(provider_summary, "synthetic_dataset_count"))
    sidecar_proof_count = int(_first_number(provider_summary, "synthetic_sidecar_count"))
    sidecar_proof_required = synthetic_dataset_count > 0
    sidecar_proof_count_matches = sidecar_proof_count == synthetic_dataset_count
    sidecar_proof_ready = _first_bool(provider_summary, "synthetic_sidecar_proof_ready")
    config_receipt_proof = _mapping(provider_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(provider_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_proofs_match = bool(
        config_receipt_proof
        and manifest_receipt_proof
        and config_receipt_proof == manifest_receipt_proof
    )
    receipt_required_count = int(
        _first_number(provider_summary, "adapter_receipt_required_count")
    )
    receipt_valid_count = int(
        _first_number(provider_summary, "adapter_receipt_valid_count")
    )
    receipt_fingerprint_match_count = int(
        _first_number(provider_summary, "adapter_receipt_fingerprint_match_count")
    )
    capture_fingerprint_match_count = int(
        _first_number(provider_summary, "capture_fingerprint_match_count")
    )
    dataset_count = int(_first_number(provider_summary, "dataset_count"))
    return pd.DataFrame(
        [
            _check(
                "provider_research_dir_exists",
                str(provider_dir),
                "exists",
                True,
                provider_dir.exists(),
                "provider imbalance research directory is required",
            ),
            _check(
                "provider_research_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance research summary could not be read",
            ),
            _check(
                "provider_research_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider imbalance research config could not be read",
            ),
            _check(
                "provider_research_manifest_readable",
                provider_manifest_error or "ok",
                "is",
                "ok",
                not provider_manifest_error,
                provider_manifest_error or "provider imbalance research manifest could not be read",
            ),
            _check(
                "provider_research_manifest_type",
                _text(provider_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_research",
                _text(provider_manifest.get("run_type"))
                == "provider_market_data_imbalance_research",
                "provider imbalance research manifest run_type is not expected",
            ),
            _check(
                "provider_imbalance_research_ready",
                provider_ready,
                "is",
                True,
                provider_ready or not config.require_provider_research_ready,
                "provider imbalance research is not ready",
            ),
            _check(
                "provider_research_provider_capture_commands_carried",
                bundle_provider_capture_command_count,
                "==",
                provider_capture_command_count,
                bundle_provider_capture_commands_carried if bundle_provided else True,
                "provider imbalance research is missing capture-bundle provider command proof",
            ),
            _check(
                "provider_research_provider_capture_commands_match_session",
                bundle_provider_capture_command_count,
                "matches",
                provider_capture_command_count,
                bundle_provider_capture_commands_match_session if bundle_provided else True,
                "provider imbalance research command proof no longer matches the session packet",
            ),
            _check(
                "provider_research_adapter_execution_contract_carried",
                _adapter_contract_metadata_text(provider_summary),
                "is_not",
                "",
                adapter_contract_carried if bundle_provided else True,
                "provider imbalance research is missing credential-safe adapter execution contract proof",
            ),
            _check(
                "provider_research_adapter_execution_contract_matches_evidence",
                _adapter_contract_metadata_text(provider_summary),
                "matches",
                "live evidence",
                _first_bool(provider_summary, "adapter_contract_metadata_matches_evidence") if bundle_provided else True,
                "provider imbalance research adapter execution contract no longer matches live evidence",
            ),
            _check(
                "provider_research_provider_profile_carried",
                _first_text(provider_summary, "provider_profile_sha256"),
                "has",
                "provider profile",
                provider_profile_carried,
                "provider imbalance research is missing provider-profile proof",
            ),
            _check(
                "provider_research_provider_profile_matches_session",
                _first_text(provider_summary, "provider_profile_sha256"),
                "matches",
                "live session",
                _first_bool(provider_summary, "provider_profile_matches_session"),
                "provider imbalance research provider-profile proof no longer matches the live session packet",
            ),
            _check(
                "provider_research_provider_profile_matches_bundle",
                _first_text(provider_summary, "capture_bundle_provider_profile_sha256"),
                "matches",
                _first_text(provider_summary, "provider_profile_sha256"),
                _first_bool(provider_summary, "provider_profile_matches_bundle") if bundle_provided else True,
                "provider imbalance research provider-profile proof no longer matches the capture bundle",
            ),
            _check(
                "provider_research_adapter_provider_profile_matches_evidence",
                _first_text(provider_summary, "adapter_contract_provider_profile_sha256"),
                "==",
                _first_text(provider_summary, "provider_profile_sha256"),
                _first_bool(provider_summary, "adapter_contract_provider_profile_matches_evidence")
                if bundle_provided
                else True,
                "provider imbalance research adapter contract provider-profile SHA no longer matches live evidence",
            ),
            _check(
                "provider_research_adapter_receipt_proof_carried",
                bool(config_receipt_proof),
                "is",
                True,
                bool(config_receipt_proof) and _truthy(config_receipt_proof.get("ready"))
                if bundle_provided
                else True,
                "provider imbalance research is missing ready adapter receipt proof",
            ),
            _check(
                "provider_research_adapter_receipt_proof_matches_manifest",
                receipt_proofs_match,
                "is",
                True,
                receipt_proofs_match if bundle_provided else True,
                "adapter receipt proof differs between provider research config and manifest",
            ),
            _check(
                "provider_research_adapter_receipts_valid",
                receipt_valid_count,
                "==",
                receipt_required_count,
                receipt_valid_count == receipt_required_count if bundle_provided else True,
                "provider imbalance research did not preserve valid required adapter receipts",
            ),
            _check(
                "provider_research_adapter_receipt_fingerprints_match_evidence",
                receipt_fingerprint_match_count,
                "==",
                receipt_required_count,
                receipt_fingerprint_match_count == receipt_required_count
                if bundle_provided
                else True,
                "provider imbalance research receipt fingerprints no longer match evidence",
            ),
            _check(
                "provider_research_capture_fingerprints_match_evidence",
                capture_fingerprint_match_count,
                "==",
                dataset_count,
                bool(dataset_count and capture_fingerprint_match_count == dataset_count),
                "provider imbalance research capture fingerprints no longer match evidence",
            ),
            _check(
                "provider_research_synthetic_sidecar_proof_carried",
                sidecar_proof_count,
                "==",
                synthetic_dataset_count,
                sidecar_proof_count_matches if sidecar_proof_required else True,
                "provider imbalance research synthetic folds are missing rehearsal sidecar proof",
            ),
            _check(
                "provider_research_synthetic_sidecar_proof_ready",
                sidecar_proof_ready,
                "is",
                True,
                sidecar_proof_ready if sidecar_proof_required else True,
                "provider imbalance research synthetic folds require ready rehearsal sidecar proof",
            ),
            _check(
                "experiment_catalog_ready",
                catalog_error or catalog_count,
                ">=",
                1,
                catalog is not None and catalog_count >= 1,
                catalog_error or "provider imbalance research did not produce cataloged manifests",
            ),
            _check(
                "strategy_evidence_review_ready",
                evidence_error or evidence_ready,
                "is",
                True,
                (evidence is not None and evidence_ready) or not config.require_strategy_evidence_ready,
                evidence_error or "provider imbalance research evidence review is not ready",
            ),
            _check(
                "provider_research_profile_complete",
                passed_required,
                "==",
                required_count,
                bool(required_count and passed_required == required_count),
                "not all provider imbalance research profile run types passed",
            ),
            _check(
                "strategy_identity_imbalance",
                _first_text(evidence_summary, "strategy"),
                "is",
                "imbalance",
                _first_text(evidence_summary, "strategy") == "imbalance",
                "strategy evidence did not resolve to imbalance",
            ),
            _check(
                "market_identity_present",
                _first_text(evidence_summary, "market"),
                "is_not",
                "",
                bool(_first_text(evidence_summary, "market")),
                "strategy evidence did not resolve a market identity",
            ),
        ]
    )


def _summary(
    provider_dir: Path,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    provider_manifest: dict[str, Any],
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
    checks: pd.DataFrame,
    output_dir: Path,
    catalog_dir: Path,
    evidence_dir: Path,
    config: ProviderMarketDataImbalanceEvidenceConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    evidence_summary = evidence.summary if evidence is not None else pd.DataFrame()
    passed_required = int(_first_number(evidence_summary, "passed_required_run_types"))
    required_count = int(_first_number(evidence_summary, "required_run_type_count"))
    config_receipt_proof = _mapping(provider_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(provider_manifest.get("extra")).get("adapter_receipt_proof")
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_research_ready": _first_bool(provider_summary, "ready"),
                "strategy_evidence_ready": bool(evidence.ready) if evidence is not None else False,
                "provider_research_dir": str(provider_dir),
                "output_dir": str(output_dir),
                "catalog_dir": str(catalog_dir if catalog is not None else ""),
                "strategy_evidence_dir": str(evidence_dir if evidence is not None else ""),
                "evidence_profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "exchange": _first_text(provider_summary, "exchange"),
                "source_session_timezone": _first_text(provider_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(provider_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(provider_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(provider_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(provider_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(provider_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(provider_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(provider_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(provider_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(provider_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(provider_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    provider_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    provider_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    provider_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    provider_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    provider_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    provider_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    provider_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    provider_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(provider_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(provider_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(provider_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(provider_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(provider_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(provider_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(provider_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(provider_summary, "adapter_handoff_sha256"),
                "provider_research_manifest_run_type": _text(
                    provider_manifest.get("run_type")
                ),
                "adapter_receipt_proof_ready": _first_bool(
                    provider_summary, "adapter_receipt_proof_ready"
                ),
                "adapter_receipt_proof_matches_manifest": bool(
                    config_receipt_proof
                    and manifest_receipt_proof
                    and config_receipt_proof == manifest_receipt_proof
                ),
                "adapter_receipts_required": _first_bool(
                    provider_summary, "adapter_receipts_required"
                ),
                "adapter_receipt_required_count": int(
                    _first_number(provider_summary, "adapter_receipt_required_count")
                ),
                "adapter_receipt_valid_count": int(
                    _first_number(provider_summary, "adapter_receipt_valid_count")
                ),
                "adapter_receipt_fingerprint_match_count": int(
                    _first_number(
                        provider_summary,
                        "adapter_receipt_fingerprint_match_count",
                    )
                ),
                "capture_fingerprint_match_count": int(
                    _first_number(provider_summary, "capture_fingerprint_match_count")
                ),
                "source_credential_env_template_path": _first_text(
                    provider_summary, "source_credential_env_template_path"
                ),
                "source_credential_env_template_exists": _first_bool(
                    provider_summary, "source_credential_env_template_exists"
                ),
                "source_credential_env_template_sha256": _first_text(
                    provider_summary, "source_credential_env_template_sha256"
                ),
                "source_live_fetch_contract_available": _first_bool(
                    provider_summary, "source_live_fetch_contract_available"
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    provider_summary, "source_live_fetch_contract_next_gate"
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    provider_summary, "source_live_fetch_contract_command_template"
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    provider_summary, "source_live_fetch_contract_exchange"
                ),
                "source_live_fetch_contract_market": _first_text(
                    provider_summary, "source_live_fetch_contract_market"
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    provider_summary, "source_live_fetch_contract_session_timezone"
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    provider_summary, "source_live_fetch_contract_session_open_local"
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    provider_summary, "source_live_fetch_contract_session_close_local"
                ),
                "adapter_contract_provider": _first_text(provider_summary, "adapter_contract_provider"),
                "adapter_contract_transport": _first_text(provider_summary, "adapter_contract_transport"),
                "adapter_contract_market": _first_text(provider_summary, "adapter_contract_market"),
                "adapter_contract_exchange": _first_text(provider_summary, "adapter_contract_exchange"),
                "adapter_contract_values_stored": _first_bool(provider_summary, "adapter_contract_values_stored"),
                "adapter_contract_metadata_matches_evidence": _first_bool(
                    provider_summary, "adapter_contract_metadata_matches_evidence"
                ),
                "provider_profile_sha256": _first_text(provider_summary, "provider_profile_sha256"),
                "provider_profile_adapter": _first_text(provider_summary, "provider_profile_adapter"),
                "provider_profile_auth_required": _first_bool(provider_summary, "provider_profile_auth_required"),
                "provider_profile_transports": _first_text(provider_summary, "provider_profile_transports"),
                "provider_profile_capabilities": _first_text(provider_summary, "provider_profile_capabilities"),
                "capture_bundle_provider_profile_sha256": _first_text(
                    provider_summary, "capture_bundle_provider_profile_sha256"
                ),
                "provider_profile_matches_session": _first_bool(provider_summary, "provider_profile_matches_session"),
                "provider_profile_matches_bundle": _first_bool(provider_summary, "provider_profile_matches_bundle")
                if _first_bool(provider_summary, "capture_bundle_provided")
                else True,
                "adapter_contract_provider_profile_sha256": _first_text(
                    provider_summary, "adapter_contract_provider_profile_sha256"
                ),
                "adapter_contract_provider_profile_matches_evidence": _first_bool(
                    provider_summary, "adapter_contract_provider_profile_matches_evidence"
                )
                if _first_bool(provider_summary, "capture_bundle_provided")
                else True,
                "provider_capture_command_count": int(
                    _first_number(provider_summary, "provider_capture_command_count")
                ),
                "provider_capture_command_providers": _first_text(
                    provider_summary, "provider_capture_command_providers"
                ),
                "provider_capture_command_transports": _first_text(
                    provider_summary, "provider_capture_command_transports"
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(provider_summary, "capture_bundle_provider_capture_command_count")
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(provider_summary, "capture_bundle_provider_capture_command_missing_count")
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    provider_summary, "capture_bundle_provider_capture_commands_match_session"
                )
                if _first_bool(provider_summary, "capture_bundle_provided")
                else True,
                "synthetic_dataset_count": int(_first_number(provider_summary, "synthetic_dataset_count")),
                "synthetic_sidecar_proof_ready": _first_bool(provider_summary, "synthetic_sidecar_proof_ready"),
                "synthetic_sidecar_count": int(_first_number(provider_summary, "synthetic_sidecar_count")),
                "synthetic_sidecar_readable_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_readable_count")
                ),
                "synthetic_sidecar_source_count": int(_first_number(provider_summary, "synthetic_sidecar_source_count")),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_command_hash_count")
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_capture_env_template_match_count")
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_handoff_match_count")
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_source_env_template_match_count")
                ),
                "synthetic_sidecar_live_fetch_contract_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_live_fetch_contract_count")
                ),
                "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_adapter_execution_contract_safe_count")
                ),
                "synthetic_sidecar_invariant_count": int(
                    _first_number(provider_summary, "synthetic_sidecar_invariant_count")
                ),
                "market": _first_text(evidence_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(evidence_summary, "strategy") or "imbalance",
                "catalog_run_count": 0 if catalog is None else catalog.run_count,
                "passed_required_run_types": passed_required,
                "required_run_type_count": required_count,
                "dirty_runs": int(_first_number(evidence_summary, "dirty_runs")),
                "allow_dirty_git": bool(config.allow_dirty_git),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "build_provider_imbalance_launch_packet" if ready else "repair_provider_imbalance_evidence",
                "next_gate": "pipeline-imbalance-launch" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _ready_help_command(provider_dir) if ready else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    provider_dir: Path,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "build_provider_imbalance_launch_packet",
                    "reason": "provider imbalance research evidence profile is complete",
                    "next_gate": "pipeline-imbalance-launch",
                    "next_gate_help_command": _ready_help_command(provider_dir),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed = summary.get("failed_check_names", "")
    for check in [item for item in str(failed).split(";") if item]:
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": _reason_for_check(check, catalog, evidence),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_evidence",
                "reason": "provider imbalance evidence review is not ready",
                "next_gate": "review-provider-market-data-imbalance-evidence",
                "next_gate_help_command": "python -m hft_cli review-provider-market-data-imbalance-evidence --help",
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    provider_manifest: dict[str, Any],
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceEvidenceConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "provider_research": _first_record(provider_summary),
        "provider_research_config": _jsonable(provider_config),
        "provider_research_manifest_run_type": _text(provider_manifest.get("run_type")),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(provider_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(provider_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(provider_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(provider_config),
        "adapter_execution_contract": _mapping(provider_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            provider_config.get("adapter_receipt_proof")
        ),
        "synthetic_sidecar_proof": _mapping(provider_config.get("synthetic_sidecar_proof")),
        "capture_bundle": _provider_capture_bundle(provider_summary, provider_config),
        "catalog": {
            "run_count": 0 if catalog is None else catalog.run_count,
            "output_dir": "" if catalog is None else str(catalog.output_dir or ""),
            "summary": _first_record(None if catalog is None else catalog.summary),
        },
        "strategy_evidence": {
            "ready": False if evidence is None else bool(evidence.ready),
            "output_dir": "" if evidence is None else str(evidence.output_dir or ""),
            "summary": _first_record(None if evidence is None else evidence.summary),
            "items": _records(None if evidence is None else evidence.evidence),
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _blocked_next_gate(checks: pd.DataFrame) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "review-provider-market-data-imbalance-evidence"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("provider_research") or check.startswith("provider_imbalance"):
        return "run-provider-market-data-imbalance-research"
    if check.startswith("experiment_catalog"):
        return "catalog-runs"
    if check.startswith("strategy_evidence") or check.startswith("provider_research_profile"):
        return "review-strategy-evidence"
    if check.startswith("strategy_identity") or check.startswith("market_identity"):
        return "review-strategy-evidence"
    return "review-provider-market-data-imbalance-evidence"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "run-provider-market-data-imbalance-research":
        return "python -m hft_cli run-provider-market-data-imbalance-research --help"
    if next_gate == "catalog-runs":
        return "python -m hft_cli catalog-runs --help"
    if next_gate == "review-strategy-evidence":
        return "python -m hft_cli review-strategy-evidence --profile provider_imbalance_research --help"
    if next_gate == "pipeline-imbalance-launch":
        return "python -m hft_cli pipeline-imbalance-launch --help"
    return "python -m hft_cli review-provider-market-data-imbalance-evidence --help"


def _ready_help_command(provider_dir: Path) -> str:
    promotion = provider_dir / "imbalance_research" / "promotion"
    return f"python -m hft_cli pipeline-imbalance-launch --promotion {promotion} --help"


def _repair_action(check: str) -> str:
    if check.startswith("provider_research") or check.startswith("provider_imbalance"):
        return "rerun_provider_imbalance_research"
    if check.startswith("experiment_catalog"):
        return "catalog_provider_imbalance_research"
    if check.startswith("strategy_evidence") or check.startswith("provider_research_profile"):
        return "review_provider_imbalance_research_evidence"
    return "repair_provider_imbalance_evidence"


def _reason_for_check(
    check: str,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
) -> str:
    if evidence is not None and not evidence.checks.empty:
        failed = evidence.checks.loc[~evidence.checks["passed"].astype(bool)]
        if not failed.empty and (
            check.startswith("strategy_evidence")
            or check.startswith("provider_research_profile")
            or check.startswith("strategy_identity")
            or check.startswith("market_identity")
        ):
            return str(failed.iloc[0].get("reason", "strategy evidence review is not ready"))
    if catalog is not None and catalog.summary is not None and not catalog.summary.empty and check.startswith("experiment_catalog"):
        return str(catalog.summary.iloc[0].get("recommendation", "catalog provider imbalance research"))
    return check.replace("_", " ")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Evidence",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Profile: {summary['evidence_profile']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Capture bundle: {summary['capture_bundle_path']}",
        f"- Credential env template: {summary['capture_env_template_path']}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Adapter execution contract: {summary['adapter_contract_provider'] or 'missing'} / {summary['adapter_contract_transport'] or 'missing'} (evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Adapter receipt proof: {'ready' if bool(summary['adapter_receipt_proof_ready']) else 'blocked'} (research manifest match: {'yes' if bool(summary['adapter_receipt_proof_matches_manifest']) else 'no'})",
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
        f"- Catalog runs: {summary['catalog_run_count']}",
        f"- Required run types: {summary['passed_required_run_types']}/{summary['required_run_type_count']}",
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


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _series_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


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


def _adapter_contract_metadata_text(provider_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(provider_summary, 'adapter_contract_provider')}|"
        f"{_first_text(provider_summary, 'adapter_contract_transport')}|"
        f"{_first_text(provider_summary, 'adapter_contract_market')}|"
        f"{_first_text(provider_summary, 'adapter_contract_exchange')}"
    )


def _provider_capture_bundle(provider_summary: pd.DataFrame, provider_config: dict[str, Any]) -> dict[str, Any]:
    payload = _mapping(provider_config.get("capture_bundle"))
    if payload:
        return {str(key): _jsonable(value) for key, value in payload.items()}
    return {
        "capture_bundle_path": _first_text(provider_summary, "capture_bundle_path"),
        "capture_bundle_provided": _first_bool(provider_summary, "capture_bundle_provided"),
        "capture_bundle_exists": _first_bool(provider_summary, "capture_bundle_exists"),
        "capture_bundle_ready": _first_bool(provider_summary, "capture_bundle_ready"),
        "exchange": _first_text(provider_summary, "capture_bundle_exchange"),
        "source_session": {
            "timezone": _first_text(provider_summary, "capture_bundle_source_session_timezone"),
            "open_local": _first_text(provider_summary, "capture_bundle_source_session_open_local"),
            "close_local": _first_text(provider_summary, "capture_bundle_source_session_close_local"),
        },
        "market_session": {
            "timezone": _first_text(provider_summary, "capture_bundle_market_session_timezone"),
            "open_local": _first_text(provider_summary, "capture_bundle_market_session_open_local"),
            "close_local": _first_text(provider_summary, "capture_bundle_market_session_close_local"),
        },
        "capture_bundle_metadata_matches_session": _first_bool(
            provider_summary, "capture_bundle_metadata_matches_session"
        ),
        "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
            provider_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "metadata_matches_session": _first_bool(provider_summary, "capture_bundle_metadata_matches_session"),
        "live_fetch_contract_metadata_matches_session": _first_bool(
            provider_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "capture_env_template_path": _first_text(provider_summary, "capture_env_template_path"),
        "capture_env_template_provided": _first_bool(provider_summary, "capture_env_template_provided"),
        "capture_env_template_exists": _first_bool(provider_summary, "capture_env_template_exists"),
        "capture_env_template_sha256": _first_text(provider_summary, "capture_env_template_sha256"),
        "adapter_handoff_path": _first_text(provider_summary, "adapter_handoff_path"),
        "adapter_handoff_provided": _first_bool(provider_summary, "adapter_handoff_provided"),
        "adapter_handoff_exists": _first_bool(provider_summary, "adapter_handoff_exists"),
        "adapter_handoff_sha256": _first_text(provider_summary, "adapter_handoff_sha256"),
        "source_credential_env_template_path": _first_text(
            provider_summary, "source_credential_env_template_path"
        ),
        "source_credential_env_template_exists": _first_bool(
            provider_summary, "source_credential_env_template_exists"
        ),
        "source_credential_env_template_sha256": _first_text(
            provider_summary, "source_credential_env_template_sha256"
        ),
        "source_live_fetch_contract_available": _first_bool(
            provider_summary, "source_live_fetch_contract_available"
        ),
        "source_live_fetch_contract_next_gate": _first_text(
            provider_summary, "source_live_fetch_contract_next_gate"
        ),
        "source_live_fetch_contract_command_template": _first_text(
            provider_summary, "source_live_fetch_contract_command_template"
        ),
        "source_live_fetch_contract_exchange": _first_text(
            provider_summary, "source_live_fetch_contract_exchange"
        ),
        "source_live_fetch_contract_market": _first_text(
            provider_summary, "source_live_fetch_contract_market"
        ),
        "source_live_fetch_contract_session_timezone": _first_text(
            provider_summary, "source_live_fetch_contract_session_timezone"
        ),
        "source_live_fetch_contract_session_open_local": _first_text(
            provider_summary, "source_live_fetch_contract_session_open_local"
        ),
        "source_live_fetch_contract_session_close_local": _first_text(
            provider_summary, "source_live_fetch_contract_session_close_local"
        ),
        "adapter_execution_contract": _mapping(provider_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            provider_config.get("adapter_receipt_proof")
        ),
        "adapter_contract_provider": _first_text(provider_summary, "adapter_contract_provider"),
        "adapter_contract_transport": _first_text(provider_summary, "adapter_contract_transport"),
        "adapter_contract_market": _first_text(provider_summary, "adapter_contract_market"),
        "adapter_contract_exchange": _first_text(provider_summary, "adapter_contract_exchange"),
        "adapter_contract_values_stored": _first_bool(provider_summary, "adapter_contract_values_stored"),
        "adapter_contract_metadata_matches_evidence": _first_bool(
            provider_summary, "adapter_contract_metadata_matches_evidence"
        ),
        "provider_profile": _mapping(provider_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(provider_config.get("live_session_provider_profile")),
        "capture_bundle_provider_profile": _mapping(
            _mapping(provider_config.get("capture_bundle")).get("capture_bundle_provider_profile")
        ),
        "provider_profile_sha256": _first_text(provider_summary, "provider_profile_sha256"),
        "provider_profile_matches_session": _first_bool(provider_summary, "provider_profile_matches_session"),
        "provider_profile_matches_bundle": _first_bool(provider_summary, "provider_profile_matches_bundle")
        if _first_bool(provider_summary, "capture_bundle_provided")
        else True,
        "adapter_contract_provider_profile_sha256": _first_text(
            provider_summary, "adapter_contract_provider_profile_sha256"
        ),
        "adapter_contract_provider_profile_matches_evidence": _first_bool(
            provider_summary, "adapter_contract_provider_profile_matches_evidence"
        )
        if _first_bool(provider_summary, "capture_bundle_provided")
        else True,
        "provider_capture_command_count": int(_first_number(provider_summary, "provider_capture_command_count")),
        "provider_capture_command_providers": _first_text(provider_summary, "provider_capture_command_providers"),
        "provider_capture_command_transports": _first_text(provider_summary, "provider_capture_command_transports"),
        "capture_bundle_provider_capture_command_count": int(
            _first_number(provider_summary, "capture_bundle_provider_capture_command_count")
        ),
        "capture_bundle_provider_capture_command_missing_count": int(
            _first_number(provider_summary, "capture_bundle_provider_capture_command_missing_count")
        ),
        "capture_bundle_provider_capture_commands_match_session": _first_bool(
            provider_summary, "capture_bundle_provider_capture_commands_match_session"
        )
        if _first_bool(provider_summary, "capture_bundle_provided")
        else True,
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(provider_config),
    }


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    return _list(provider_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(provider_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(provider_config.get("capture_bundle"))
    return (
        _list(provider_config.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("capture_bundle_provider_capture_commands"))
        or _list(bundle.get("provider_capture_commands"))
    )


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return _number(frame.iloc[0][column])


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
    return _text(value).lower() in {"1", "true", "yes", "ready", "pass"}


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


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
