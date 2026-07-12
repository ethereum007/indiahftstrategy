from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.strategy_scorecard import StrategyScorecardReport, StrategyScorecardThresholds, write_strategy_scorecard


PROFILE = "imbalance"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceScorecardConfig:
    require_launch_evidence_ready: bool = True
    require_scorecard_ready: bool = True
    allow_dirty_git: bool = False
    expected_market: str = ""
    require_file_inputs: bool = False
    research_family_path: str = ""
    require_research_family: bool = False


@dataclass(frozen=True)
class ProviderMarketDataImbalanceScorecardReport:
    scorecard: StrategyScorecardReport | None
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


def write_provider_market_data_imbalance_scorecard(
    provider_launch_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceScorecardConfig | None = None,
) -> ProviderMarketDataImbalanceScorecardReport:
    config = config or ProviderMarketDataImbalanceScorecardConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    evidence_dir = Path(provider_launch_evidence_dir)
    evidence_summary, evidence_summary_error = _read_csv(
        evidence_dir / "provider_market_data_imbalance_launch_evidence_summary.csv"
    )
    evidence_config, evidence_config_error = _read_json(
        evidence_dir / "provider_market_data_imbalance_launch_evidence_config.json"
    )
    evidence_manifest, evidence_manifest_error = _read_json(
        evidence_dir / "manifest.json"
    )
    catalog_path = evidence_dir / "catalog" / "experiment_catalog.csv"
    scorecard = None
    scorecard_error = ""
    scorecard_dir = out / "scorecard"
    if catalog_path.exists() and _adapter_receipt_proof_allows_scorecard(
        evidence_summary,
        evidence_config,
        evidence_manifest,
    ):
        try:
            scorecard = write_strategy_scorecard(
                catalog_path,
                output_dir=scorecard_dir,
                research_family_path=config.research_family_path or None,
                thresholds=StrategyScorecardThresholds(
                    profiles=(PROFILE,),
                    expected_market=config.expected_market or _first_text(evidence_summary, "market") or None,
                    allow_dirty_git=config.allow_dirty_git,
                    require_file_inputs=config.require_file_inputs,
                    require_research_family=config.require_research_family,
                ),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            scorecard_error = str(exc)
    checks = _checks(
        evidence_dir,
        evidence_summary,
        evidence_summary_error,
        evidence_config,
        evidence_config_error,
        evidence_manifest,
        evidence_manifest_error,
        catalog_path,
        scorecard,
        scorecard_error,
        config,
    )
    summary = _summary(
        evidence_dir,
        evidence_summary,
        evidence_config,
        evidence_manifest,
        catalog_path,
        scorecard,
        checks,
        out,
        config,
    )
    action_queue = _action_queue(summary.iloc[0], checks, scorecard)
    payload = _config(
        summary.iloc[0],
        evidence_summary,
        evidence_config,
        evidence_manifest,
        scorecard,
        checks,
        action_queue,
        config,
    )

    checks.to_csv(out / "provider_market_data_imbalance_scorecard_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_scorecard_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_scorecard_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_scorecard_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_scorecard_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"provider_launch_evidence_dir": evidence_dir}
    if catalog_path.exists():
        inputs["catalog"] = catalog_path
    if scorecard is not None and scorecard.output_dir is not None:
        inputs["scorecard"] = scorecard.output_dir
    research_family = Path(config.research_family_path).resolve() if config.research_family_path else None
    if research_family is not None and research_family.exists():
        inputs["research_family_audit"] = research_family
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
    receipt_paths, capture_paths = _adapter_receipt_proof_paths(
        _mapping(payload.get("adapter_receipt_proof"))
    )
    if receipt_paths:
        inputs["adapter_receipts"] = receipt_paths
    if capture_paths:
        inputs["provider_captures"] = capture_paths
    write_experiment_manifest(
        out,
        run_type="provider_market_data_imbalance_scorecard",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary_row["ready"]),
            "launch_evidence_ready": bool(summary_row["launch_evidence_ready"]),
            "scorecard_ready": bool(summary_row["scorecard_ready"]),
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
            "synthetic_sidecar_proof": _mapping(payload.get("synthetic_sidecar_proof")),
            "synthetic_dataset_count": int(summary_row["synthetic_dataset_count"]),
            "synthetic_sidecar_proof_ready": bool(summary_row["synthetic_sidecar_proof_ready"]),
            "synthetic_sidecar_count": int(summary_row["synthetic_sidecar_count"]),
            "synthetic_sidecar_readable_count": int(summary_row["synthetic_sidecar_readable_count"]),
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
        },
    )
    return ProviderMarketDataImbalanceScorecardReport(scorecard, checks, summary, action_queue, payload, out)


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


def _adapter_receipt_proof_allows_scorecard(
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    evidence_manifest: dict[str, Any],
) -> bool:
    if not _first_bool(evidence_summary, "capture_bundle_provided"):
        return True
    config_proof = _mapping(evidence_config.get("adapter_receipt_proof"))
    manifest_proof = _mapping(
        _mapping(evidence_manifest.get("extra")).get("adapter_receipt_proof")
    )
    status = _adapter_receipt_proof_status(config_proof)
    return bool(
        config_proof
        and config_proof == manifest_proof
        and status["ready"]
        and _first_bool(evidence_summary, "adapter_receipt_proof_ready")
        and _first_bool(evidence_summary, "adapter_receipt_proof_matches_manifest")
    )


def _checks(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_summary_error: str,
    evidence_config: dict[str, Any],
    evidence_config_error: str,
    evidence_manifest: dict[str, Any],
    evidence_manifest_error: str,
    catalog_path: Path,
    scorecard: StrategyScorecardReport | None,
    scorecard_error: str,
    config: ProviderMarketDataImbalanceScorecardConfig,
) -> pd.DataFrame:
    scorecard_summary = scorecard.summary if scorecard is not None else pd.DataFrame()
    scorecard_ready = bool(scorecard.ready) if scorecard is not None else False
    best_profile = _first_text(scorecard_summary, "best_profile")
    bundle_provided = _first_bool(evidence_summary, "capture_bundle_provided")
    provider_capture_command_count = int(_first_number(evidence_summary, "provider_capture_command_count"))
    bundle_provider_capture_command_count = int(
        _first_number(evidence_summary, "capture_bundle_provider_capture_command_count")
    )
    bundle_provider_capture_command_missing_count = int(
        _first_number(evidence_summary, "capture_bundle_provider_capture_command_missing_count")
    )
    bundle_provider_capture_commands_carried = (
        provider_capture_command_count >= 1
        and bundle_provider_capture_command_count == provider_capture_command_count
        and bundle_provider_capture_command_missing_count == 0
    )
    bundle_provider_capture_commands_match_session = (
        bundle_provider_capture_commands_carried
        and _first_bool(evidence_summary, "capture_bundle_provider_capture_commands_match_session")
    )
    adapter_contract_carried = _adapter_contract_carried(evidence_summary)
    provider_profile_carried = _provider_profile_carried(evidence_summary)
    synthetic_dataset_count = int(_first_number(evidence_summary, "synthetic_dataset_count"))
    sidecar_proof_count = int(_first_number(evidence_summary, "synthetic_sidecar_count"))
    sidecar_proof_required = synthetic_dataset_count > 0
    sidecar_proof_count_matches = sidecar_proof_count == synthetic_dataset_count
    sidecar_proof_ready = _first_bool(evidence_summary, "synthetic_sidecar_proof_ready")
    config_receipt_proof = _mapping(evidence_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(evidence_manifest.get("extra")).get("adapter_receipt_proof")
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
                "launch_evidence_dir_exists",
                str(evidence_dir),
                "exists",
                True,
                evidence_dir.exists(),
                "provider imbalance launch evidence directory is required",
            ),
            _check(
                "launch_evidence_summary_readable",
                evidence_summary_error or "ok",
                "is",
                "ok",
                not evidence_summary_error,
                evidence_summary_error or "provider imbalance launch evidence summary could not be read",
            ),
            _check(
                "launch_evidence_config_readable",
                evidence_config_error or "ok",
                "is",
                "ok",
                not evidence_config_error,
                evidence_config_error or "provider imbalance launch evidence config could not be read",
            ),
            _check(
                "launch_evidence_manifest_readable",
                evidence_manifest_error or "ok",
                "is",
                "ok",
                not evidence_manifest_error,
                evidence_manifest_error or "provider imbalance launch evidence manifest could not be read",
            ),
            _check(
                "launch_evidence_manifest_type",
                _text(evidence_manifest.get("run_type")),
                "is",
                "provider_market_data_imbalance_launch_evidence_review",
                _text(evidence_manifest.get("run_type"))
                == "provider_market_data_imbalance_launch_evidence_review",
                "provider imbalance launch evidence manifest run_type is not expected",
            ),
            _check(
                "provider_imbalance_launch_evidence_ready",
                _first_bool(evidence_summary, "ready"),
                "is",
                True,
                _first_bool(evidence_summary, "ready") or not config.require_launch_evidence_ready,
                "provider imbalance launch evidence is not ready",
            ),
            _check(
                "launch_evidence_provider_capture_commands_carried",
                bundle_provider_capture_command_count,
                "==",
                provider_capture_command_count,
                bundle_provider_capture_commands_carried if bundle_provided else True,
                "provider imbalance launch evidence is missing capture-bundle provider command proof",
            ),
            _check(
                "launch_evidence_provider_capture_commands_match_session",
                bundle_provider_capture_command_count,
                "matches",
                provider_capture_command_count,
                bundle_provider_capture_commands_match_session if bundle_provided else True,
                "provider imbalance launch evidence command proof no longer matches the session packet",
            ),
            _check(
                "launch_evidence_adapter_execution_contract_carried",
                _adapter_contract_metadata_text(evidence_summary),
                "is_not",
                "",
                adapter_contract_carried if bundle_provided else True,
                "provider imbalance launch evidence is missing credential-safe adapter execution contract proof",
            ),
            _check(
                "launch_evidence_adapter_execution_contract_matches_evidence",
                _adapter_contract_metadata_text(evidence_summary),
                "matches",
                "live evidence",
                _first_bool(evidence_summary, "adapter_contract_metadata_matches_evidence")
                if bundle_provided
                else True,
                "provider imbalance launch evidence adapter execution contract no longer matches live evidence",
            ),
            _check(
                "launch_evidence_provider_profile_carried",
                _first_text(evidence_summary, "provider_profile_sha256"),
                "has",
                "provider profile",
                provider_profile_carried,
                "provider imbalance launch evidence is missing provider-profile proof",
            ),
            _check(
                "launch_evidence_provider_profile_matches_session",
                _first_text(evidence_summary, "provider_profile_sha256"),
                "matches",
                "live session",
                _first_bool(evidence_summary, "provider_profile_matches_session"),
                "provider imbalance launch evidence provider-profile proof no longer matches the live session packet",
            ),
            _check(
                "launch_evidence_provider_profile_matches_bundle",
                _first_text(evidence_summary, "capture_bundle_provider_profile_sha256"),
                "matches",
                _first_text(evidence_summary, "provider_profile_sha256"),
                _first_bool(evidence_summary, "provider_profile_matches_bundle") if bundle_provided else True,
                "provider imbalance launch evidence provider-profile proof no longer matches the capture bundle",
            ),
            _check(
                "launch_evidence_adapter_provider_profile_matches_evidence",
                _first_text(evidence_summary, "adapter_contract_provider_profile_sha256"),
                "==",
                _first_text(evidence_summary, "provider_profile_sha256"),
                _first_bool(evidence_summary, "adapter_contract_provider_profile_matches_evidence")
                if bundle_provided
                else True,
                "provider imbalance launch evidence adapter contract provider-profile SHA no longer matches live evidence",
            ),
            _check(
                "launch_evidence_adapter_receipt_proof_carried",
                bool(config_receipt_proof),
                "is",
                True,
                bool(config_receipt_proof)
                and _truthy(config_receipt_proof.get("ready"))
                if bundle_provided
                else True,
                "provider imbalance launch evidence is missing ready adapter receipt proof",
            ),
            _check(
                "launch_evidence_adapter_receipt_proof_matches_manifest",
                receipt_proofs_match,
                "is",
                True,
                receipt_proofs_match if bundle_provided else True,
                "adapter receipt proof differs between launch-evidence config and manifest",
            ),
            _check(
                "launch_evidence_adapter_receipts_valid",
                receipt_status["valid_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["valid_count"] == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider imbalance launch evidence did not preserve valid required adapter receipts",
            ),
            _check(
                "launch_evidence_adapter_receipt_fingerprints_current",
                receipt_status["receipt_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["receipt_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "adapter receipt files changed after launch-evidence review",
            ),
            _check(
                "launch_evidence_capture_fingerprints_current",
                receipt_status["capture_fingerprint_match_count"],
                "==",
                receipt_status["required_count"],
                receipt_status["capture_fingerprint_match_count"]
                == receipt_status["required_count"]
                if bundle_provided
                else True,
                "provider capture files changed after launch-evidence review",
            ),
            _check(
                "launch_evidence_synthetic_sidecar_proof_carried",
                sidecar_proof_count,
                "==",
                synthetic_dataset_count,
                sidecar_proof_count_matches if sidecar_proof_required else True,
                "provider imbalance launch evidence synthetic folds are missing rehearsal sidecar proof",
            ),
            _check(
                "launch_evidence_synthetic_sidecar_proof_ready",
                sidecar_proof_ready,
                "is",
                True,
                sidecar_proof_ready if sidecar_proof_required else True,
                "provider imbalance launch evidence synthetic folds require ready rehearsal sidecar proof",
            ),
            _check(
                "launch_evidence_catalog_exists",
                str(catalog_path),
                "exists",
                True,
                catalog_path.exists(),
                "launch evidence catalog is required for scorecard",
            ),
            _check(
                "strategy_scorecard_ready",
                scorecard_error or scorecard_ready,
                "is",
                True,
                (scorecard is not None and scorecard_ready) or not config.require_scorecard_ready,
                scorecard_error or "imbalance scorecard is not ready",
            ),
            _check(
                "scorecard_profile_imbalance",
                best_profile,
                "is",
                PROFILE,
                best_profile == PROFILE,
                "scorecard best profile did not resolve to imbalance",
            ),
            _check(
                "scorecard_strategy_imbalance",
                _first_text(scorecard_summary, "best_strategy"),
                "is",
                PROFILE,
                _first_text(scorecard_summary, "best_strategy") == PROFILE,
                "scorecard best strategy did not resolve to imbalance",
            ),
            _check(
                "scorecard_market_present",
                _first_text(scorecard_summary, "best_market"),
                "is_not",
                "",
                bool(_first_text(scorecard_summary, "best_market")),
                "scorecard best market is missing",
            ),
        ]
    )


def _summary(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    evidence_manifest: dict[str, Any],
    catalog_path: Path,
    scorecard: StrategyScorecardReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    config: ProviderMarketDataImbalanceScorecardConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    scorecard_summary = scorecard.summary if scorecard is not None else pd.DataFrame()
    scorecard_items = scorecard.scorecard if scorecard is not None else pd.DataFrame()
    config_receipt_proof = _mapping(evidence_config.get("adapter_receipt_proof"))
    manifest_receipt_proof = _mapping(
        _mapping(evidence_manifest.get("extra")).get("adapter_receipt_proof")
    )
    receipt_status = _adapter_receipt_proof_status(config_receipt_proof)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "launch_evidence_ready": _first_bool(evidence_summary, "ready"),
                "scorecard_ready": bool(scorecard.ready) if scorecard is not None else False,
                "provider_launch_evidence_dir": str(evidence_dir),
                "provider_launch_dir": _first_text(evidence_summary, "provider_launch_dir"),
                "provider_research_dir": _first_text(evidence_summary, "provider_research_dir"),
                "exchange": _first_text(evidence_summary, "exchange"),
                "source_session_timezone": _first_text(evidence_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(evidence_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(evidence_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(evidence_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(evidence_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(evidence_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(evidence_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(evidence_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(evidence_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(evidence_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(evidence_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    evidence_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    evidence_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    evidence_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    evidence_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    evidence_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    evidence_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    evidence_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    evidence_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(evidence_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(evidence_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(evidence_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(evidence_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(evidence_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(evidence_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(evidence_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(evidence_summary, "adapter_handoff_sha256"),
                "launch_evidence_manifest_run_type": _text(
                    evidence_manifest.get("run_type")
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
                    evidence_summary, "source_credential_env_template_path"
                ),
                "source_credential_env_template_exists": _first_bool(
                    evidence_summary, "source_credential_env_template_exists"
                ),
                "source_credential_env_template_sha256": _first_text(
                    evidence_summary, "source_credential_env_template_sha256"
                ),
                "source_live_fetch_contract_available": _first_bool(
                    evidence_summary, "source_live_fetch_contract_available"
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    evidence_summary, "source_live_fetch_contract_next_gate"
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    evidence_summary, "source_live_fetch_contract_command_template"
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    evidence_summary, "source_live_fetch_contract_exchange"
                ),
                "source_live_fetch_contract_market": _first_text(
                    evidence_summary, "source_live_fetch_contract_market"
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_timezone"
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_open_local"
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    evidence_summary, "source_live_fetch_contract_session_close_local"
                ),
                "adapter_contract_provider": _first_text(evidence_summary, "adapter_contract_provider"),
                "adapter_contract_transport": _first_text(evidence_summary, "adapter_contract_transport"),
                "adapter_contract_market": _first_text(evidence_summary, "adapter_contract_market"),
                "adapter_contract_exchange": _first_text(evidence_summary, "adapter_contract_exchange"),
                "adapter_contract_values_stored": _first_bool(evidence_summary, "adapter_contract_values_stored"),
                "adapter_contract_metadata_matches_evidence": _first_bool(
                    evidence_summary, "adapter_contract_metadata_matches_evidence"
                ),
                "provider_profile_sha256": _first_text(evidence_summary, "provider_profile_sha256"),
                "provider_profile_adapter": _first_text(evidence_summary, "provider_profile_adapter"),
                "provider_profile_auth_required": _first_bool(evidence_summary, "provider_profile_auth_required"),
                "provider_profile_transports": _first_text(evidence_summary, "provider_profile_transports"),
                "provider_profile_capabilities": _first_text(evidence_summary, "provider_profile_capabilities"),
                "capture_bundle_provider_profile_sha256": _first_text(
                    evidence_summary, "capture_bundle_provider_profile_sha256"
                ),
                "provider_profile_matches_session": _first_bool(evidence_summary, "provider_profile_matches_session"),
                "provider_profile_matches_bundle": _first_bool(evidence_summary, "provider_profile_matches_bundle")
                if _first_bool(evidence_summary, "capture_bundle_provided")
                else True,
                "adapter_contract_provider_profile_sha256": _first_text(
                    evidence_summary, "adapter_contract_provider_profile_sha256"
                ),
                "adapter_contract_provider_profile_matches_evidence": _first_bool(
                    evidence_summary, "adapter_contract_provider_profile_matches_evidence"
                )
                if _first_bool(evidence_summary, "capture_bundle_provided")
                else True,
                "provider_capture_command_count": int(
                    _first_number(evidence_summary, "provider_capture_command_count")
                ),
                "provider_capture_command_providers": _first_text(
                    evidence_summary, "provider_capture_command_providers"
                ),
                "provider_capture_command_transports": _first_text(
                    evidence_summary, "provider_capture_command_transports"
                ),
                "capture_bundle_provider_capture_command_count": int(
                    _first_number(evidence_summary, "capture_bundle_provider_capture_command_count")
                ),
                "capture_bundle_provider_capture_command_missing_count": int(
                    _first_number(evidence_summary, "capture_bundle_provider_capture_command_missing_count")
                ),
                "capture_bundle_provider_capture_commands_match_session": _first_bool(
                    evidence_summary, "capture_bundle_provider_capture_commands_match_session"
                )
                if _first_bool(evidence_summary, "capture_bundle_provided")
                else True,
                "synthetic_dataset_count": int(_first_number(evidence_summary, "synthetic_dataset_count")),
                "synthetic_sidecar_proof_ready": _first_bool(evidence_summary, "synthetic_sidecar_proof_ready"),
                "synthetic_sidecar_count": int(_first_number(evidence_summary, "synthetic_sidecar_count")),
                "synthetic_sidecar_readable_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_readable_count")
                ),
                "synthetic_sidecar_source_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_source_count")
                ),
                "synthetic_sidecar_adapter_command_hash_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_adapter_command_hash_count")
                ),
                "synthetic_sidecar_capture_env_template_match_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_capture_env_template_match_count")
                ),
                "synthetic_sidecar_adapter_handoff_match_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_adapter_handoff_match_count")
                ),
                "synthetic_sidecar_source_env_template_match_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_source_env_template_match_count")
                ),
                "synthetic_sidecar_live_fetch_contract_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_live_fetch_contract_count")
                ),
                "synthetic_sidecar_adapter_execution_contract_safe_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_adapter_execution_contract_safe_count")
                ),
                "synthetic_sidecar_invariant_count": int(
                    _first_number(evidence_summary, "synthetic_sidecar_invariant_count")
                ),
                "catalog": str(catalog_path if catalog_path.exists() else ""),
                "scorecard_dir": "" if scorecard is None else str(scorecard.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(evidence_summary, "provider"),
                "transport": _first_text(evidence_summary, "transport"),
                "market": _first_text(scorecard_summary, "best_market") or _first_text(evidence_summary, "market"),
                "strategy": _first_text(scorecard_summary, "best_strategy") or _first_text(evidence_summary, "strategy"),
                "readiness_score": _first_number(scorecard_summary, "best_readiness_score"),
                "passed_required_run_types": int(_first_number(scorecard_items, "passed_required_run_types")),
                "required_run_type_count": int(_first_number(scorecard_items, "required_run_type_count")),
                "research_family_required": bool(
                    config.require_research_family
                    or _first_bool(
                        scorecard_items,
                        "research_family_required",
                    )
                ),
                "research_family_path": config.research_family_path,
                "registered_research_detected": _first_bool(
                    scorecard_items,
                    "registered_research_detected",
                ),
                "research_family_provided": _first_bool(
                    scorecard_items,
                    "research_family_provided",
                ),
                "research_family_gate_passed": _first_bool(
                    scorecard_items,
                    "research_family_gate_passed",
                ),
                "research_family_reason": _first_text(
                    scorecard_items,
                    "research_family_reason",
                ),
                "research_family_id": _first_text(
                    scorecard_items,
                    "research_family_id",
                ),
                "research_family_registration_id": _first_text(
                    scorecard_items,
                    "research_family_registration_id",
                ),
                "research_family_manifest_sha256": _first_text(
                    scorecard_items,
                    "research_family_manifest_sha256",
                ),
                "research_family_candidate_match": _first_bool(
                    scorecard_items,
                    "research_family_candidate_match",
                ),
                "research_family_matched_study_label": _first_text(
                    scorecard_items,
                    "research_family_matched_study_label",
                ),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "plan_provider_imbalance_shadow_scaleup"
                if ready
                else "repair_provider_imbalance_scorecard",
                "next_gate": "plan-provider-market-data-imbalance-scaleup" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _text(
                    "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help",
                )
                if ready
                else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
                "allow_dirty_git": bool(config.allow_dirty_git),
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    scorecard: StrategyScorecardReport | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "plan_provider_imbalance_shadow_scaleup",
                    "reason": "provider imbalance scorecard is ready for shadow scale-up planning",
                    "next_gate": str(summary["next_gate"]),
                    "next_gate_help_command": str(summary["next_gate_help_command"]),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    for check in failed:
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": _reason_for_check(check, scorecard),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_scorecard",
                "reason": "provider imbalance scorecard is not ready",
                "next_gate": "score-provider-market-data-imbalance-readiness",
                "next_gate_help_command": "python -m hft_cli score-provider-market-data-imbalance-readiness --help",
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    evidence_manifest: dict[str, Any],
    scorecard: StrategyScorecardReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceScorecardConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "provider_profile": _mapping(evidence_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(evidence_config.get("live_session_provider_profile")),
        "provider_capture_commands": _provider_capture_commands(evidence_config),
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(evidence_config),
        "adapter_execution_contract": _mapping(evidence_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            evidence_config.get("adapter_receipt_proof")
        ),
        "synthetic_sidecar_proof": _mapping(evidence_config.get("synthetic_sidecar_proof")),
        "capture_bundle": _provider_capture_bundle(summary, evidence_config),
        "provider_launch_evidence": _first_record(evidence_summary),
        "provider_launch_evidence_config": _jsonable(evidence_config),
        "provider_launch_evidence_manifest_run_type": _text(
            evidence_manifest.get("run_type")
        ),
        "scorecard": {
            "ready": False if scorecard is None else bool(scorecard.ready),
            "output_dir": "" if scorecard is None else str(scorecard.output_dir or ""),
            "summary": _first_record(None if scorecard is None else scorecard.summary),
            "scorecard": _records(None if scorecard is None else scorecard.scorecard),
            "gaps": _records(None if scorecard is None else scorecard.gaps),
            "config": {} if scorecard is None else scorecard.config,
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
        return "score-provider-market-data-imbalance-readiness"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("launch_evidence") or check.startswith("provider_imbalance_launch_evidence"):
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("strategy_scorecard") or check.startswith("scorecard"):
        return "score-strategy-readiness"
    return "score-provider-market-data-imbalance-readiness"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-launch-evidence":
        return "python -m hft_cli review-provider-market-data-imbalance-launch-evidence --help"
    if next_gate == "score-strategy-readiness":
        return "python -m hft_cli score-strategy-readiness --profile imbalance --help"
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "plan-scaleup":
        return "python -m hft_cli plan-scaleup --help"
    return "python -m hft_cli score-provider-market-data-imbalance-readiness --help"


def _repair_action(check: str) -> str:
    if check.startswith("launch_evidence") or check.startswith("provider_imbalance_launch_evidence"):
        return "review_full_provider_imbalance_launch_evidence"
    if check.startswith("strategy_scorecard") or check.startswith("scorecard"):
        return "score_provider_imbalance_readiness"
    return "repair_provider_imbalance_scorecard"


def _reason_for_check(check: str, scorecard: StrategyScorecardReport | None) -> str:
    if scorecard is not None and scorecard.config:
        reason = str(scorecard.config.get("first_failed_reason", ""))
        if reason and (check.startswith("strategy_scorecard") or check.startswith("scorecard")):
            return reason
    return check.replace("_", " ")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Scorecard",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Profile: {summary['profile']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Readiness score: {summary['readiness_score']}",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        f"- Live fetch contract: {'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Adapter execution contract: {summary['adapter_contract_provider'] or 'missing'} / {summary['adapter_contract_transport'] or 'missing'} (evidence match: {'yes' if bool(summary['adapter_contract_metadata_matches_evidence']) else 'no'})",
        f"- Provider profile: {summary['provider_profile_sha256'] or 'missing'} (bundle match: {'yes' if bool(summary['provider_profile_matches_bundle']) else 'no'})",
        f"- Provider capture commands: {summary['provider_capture_command_count']} (bundle match: {'yes' if bool(summary['capture_bundle_provider_capture_commands_match_session']) else 'no'})",
        f"- Adapter receipt proof: {'ready' if bool(summary['adapter_receipt_proof_ready']) else 'blocked'} ({summary['adapter_receipt_fingerprint_match_count']}/{summary['adapter_receipt_required_count']} sealed; launch-evidence manifest match: {'yes' if bool(summary['adapter_receipt_proof_matches_manifest']) else 'no'})",
        f"- Synthetic sidecar proof: {'yes' if bool(summary['synthetic_sidecar_proof_ready']) else 'no'} ({summary['synthetic_sidecar_count']}/{summary['synthetic_dataset_count']})",
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


def _adapter_contract_carried(evidence_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(evidence_summary, "adapter_contract_provider"))
        and bool(_first_text(evidence_summary, "adapter_contract_transport"))
        and bool(_first_text(evidence_summary, "adapter_contract_market"))
        and bool(_first_text(evidence_summary, "adapter_contract_exchange"))
        and not _first_bool(evidence_summary, "adapter_contract_values_stored")
    )


def _provider_profile_carried(evidence_summary: pd.DataFrame) -> bool:
    return (
        bool(_first_text(evidence_summary, "provider_profile_sha256"))
        and bool(_first_text(evidence_summary, "provider_profile_adapter"))
        and bool(_first_text(evidence_summary, "provider_profile_transports"))
    )


def _adapter_contract_metadata_text(evidence_summary: pd.DataFrame) -> str:
    return (
        f"{_first_text(evidence_summary, 'adapter_contract_provider')}|"
        f"{_first_text(evidence_summary, 'adapter_contract_transport')}|"
        f"{_first_text(evidence_summary, 'adapter_contract_market')}|"
        f"{_first_text(evidence_summary, 'adapter_contract_exchange')}"
    )


def _provider_capture_bundle(summary: pd.Series, evidence_config: dict[str, Any]) -> dict[str, Any]:
    payload = _mapping(evidence_config.get("capture_bundle"))
    if payload:
        return {str(key): _jsonable(value) for key, value in payload.items()}
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
        "source_live_fetch_contract_session_open_local": str(
            summary["source_live_fetch_contract_session_open_local"]
        ),
        "source_live_fetch_contract_session_close_local": str(
            summary["source_live_fetch_contract_session_close_local"]
        ),
        "adapter_execution_contract": _mapping(evidence_config.get("adapter_execution_contract")),
        "adapter_receipt_proof": _mapping(
            evidence_config.get("adapter_receipt_proof")
        ),
        "adapter_contract_provider": str(summary["adapter_contract_provider"]),
        "adapter_contract_transport": str(summary["adapter_contract_transport"]),
        "adapter_contract_market": str(summary["adapter_contract_market"]),
        "adapter_contract_exchange": str(summary["adapter_contract_exchange"]),
        "adapter_contract_values_stored": bool(summary["adapter_contract_values_stored"]),
        "adapter_contract_metadata_matches_evidence": bool(
            summary["adapter_contract_metadata_matches_evidence"]
        ),
        "provider_profile": _mapping(evidence_config.get("provider_profile")),
        "live_session_provider_profile": _mapping(evidence_config.get("live_session_provider_profile")),
        "capture_bundle_provider_profile": _mapping(
            _mapping(evidence_config.get("capture_bundle")).get("capture_bundle_provider_profile")
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
        "capture_bundle_provider_capture_commands": _bundle_provider_capture_commands(evidence_config),
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
            _text(record.get("adapter_receipt_path")),
            _text(record.get("adapter_receipt_current_sha256"))
            or _text(record.get("adapter_receipt_ingest_sha256")),
        )
        for record in records
    )
    capture_fingerprint_match_count = sum(
        _proof_file_matches(
            _text(record.get("capture_path")),
            _text(record.get("capture_sha256")),
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
        receipt_path = _path_from_text(_text(record.get("adapter_receipt_path")))
        if (
            receipt_path is not None
            and receipt_path.exists()
            and receipt_path.is_file()
            and receipt_path not in receipt_paths
        ):
            receipt_paths.append(receipt_path)
        capture_path = _path_from_text(_text(record.get("capture_path")))
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


def _provider_capture_commands(evidence_config: dict[str, Any]) -> list[Any]:
    return _list(evidence_config.get("provider_capture_commands"))


def _bundle_provider_capture_commands(evidence_config: dict[str, Any]) -> list[Any]:
    bundle = _mapping(evidence_config.get("capture_bundle"))
    return (
        _list(evidence_config.get("capture_bundle_provider_capture_commands"))
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


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    if not text:
        return None
    return Path(text)


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
