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


PROFILE = "imbalance"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLaunchEvidenceConfig:
    require_provider_launch_ready: bool = True
    require_strategy_evidence_ready: bool = True
    allow_dirty_git: bool = False
    require_same_git_commit: bool = False
    require_same_strategy: bool = True
    require_same_market: bool = True
    expected_market: str = ""
    min_passed_per_type: int = 1
    require_file_inputs: bool = False
    require_no_placeholder_schema: bool = False
    require_no_blocked_placeholder_schema: bool = False


@dataclass(frozen=True)
class ProviderMarketDataImbalanceLaunchEvidenceReport:
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


def write_provider_market_data_imbalance_launch_evidence_review(
    provider_launch_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataImbalanceLaunchEvidenceConfig | None = None,
) -> ProviderMarketDataImbalanceLaunchEvidenceReport:
    config = config or ProviderMarketDataImbalanceLaunchEvidenceConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    launch_dir = Path(provider_launch_dir)
    launch_summary, launch_summary_error = _read_csv(
        launch_dir / "provider_market_data_imbalance_launch_summary.csv"
    )
    provider_research_dir = _provider_research_dir(launch_summary)
    catalog = None
    evidence = None
    catalog_error = ""
    evidence_error = ""
    catalog_dir = out / "catalog"
    evidence_dir = out / "strategy_evidence"
    roots = _catalog_roots(provider_research_dir, launch_dir)
    if roots:
        try:
            catalog = write_experiment_catalog(roots, output_dir=catalog_dir)
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
                        expected_market=config.expected_market or _first_text(launch_summary, "market") or None,
                        require_file_inputs=config.require_file_inputs,
                        require_no_placeholder_schema=config.require_no_placeholder_schema,
                        require_no_blocked_placeholder_schema=config.require_no_blocked_placeholder_schema,
                    ),
                )
            except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
                evidence_error = str(exc)
    checks = _checks(
        launch_dir,
        launch_summary,
        launch_summary_error,
        provider_research_dir,
        catalog,
        catalog_error,
        evidence,
        evidence_error,
        config,
    )
    summary = _summary(launch_dir, launch_summary, provider_research_dir, catalog, evidence, checks, out, config)
    action_queue = _action_queue(summary.iloc[0], checks, catalog, evidence)
    payload = _config(summary.iloc[0], launch_summary, catalog, evidence, checks, action_queue, config)

    checks.to_csv(out / "provider_market_data_imbalance_launch_evidence_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_launch_evidence_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_launch_evidence_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_launch_evidence_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_launch_evidence_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"provider_launch_dir": launch_dir}
    if provider_research_dir.exists():
        inputs["provider_research_dir"] = provider_research_dir
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
    write_experiment_manifest(
        out,
        run_type="provider_market_data_imbalance_launch_evidence_review",
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "provider_launch_ready": bool(summary.iloc[0]["provider_launch_ready"]),
            "strategy_evidence_ready": bool(summary.iloc[0]["strategy_evidence_ready"]),
            "evidence_profile": PROFILE,
            "exchange": str(summary.iloc[0]["exchange"]),
            "source_session": _source_session_contract_from_summary(summary.iloc[0]),
            "market_session": _market_session_contract_from_summary(summary.iloc[0]),
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
            "capture_bundle": {
                "exchange": str(summary.iloc[0]["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary.iloc[0]),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary.iloc[0]),
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
        },
    )
    return ProviderMarketDataImbalanceLaunchEvidenceReport(catalog, evidence, checks, summary, action_queue, payload, out)


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _provider_research_dir(launch_summary: pd.DataFrame) -> Path:
    provider_dir = _first_text(launch_summary, "provider_research_dir")
    return Path(provider_dir) if provider_dir else Path("")


def _catalog_roots(provider_research_dir: Path, launch_dir: Path) -> list[Path]:
    roots: list[Path] = []
    if provider_research_dir.exists():
        roots.append(provider_research_dir)
    if launch_dir.exists():
        roots.append(launch_dir)
    return roots


def _checks(
    launch_dir: Path,
    launch_summary: pd.DataFrame,
    launch_summary_error: str,
    provider_research_dir: Path,
    catalog: ExperimentCatalog | None,
    catalog_error: str,
    evidence: StrategyEvidenceReview | None,
    evidence_error: str,
    config: ProviderMarketDataImbalanceLaunchEvidenceConfig,
) -> pd.DataFrame:
    launch_ready = _first_bool(launch_summary, "ready")
    evidence_ready = bool(evidence.ready) if evidence is not None else False
    catalog_count = 0 if catalog is None else catalog.run_count
    evidence_summary = evidence.summary if evidence is not None else pd.DataFrame()
    passed_required = int(_first_number(evidence_summary, "passed_required_run_types"))
    required_count = int(_first_number(evidence_summary, "required_run_type_count"))
    return pd.DataFrame(
        [
            _check(
                "provider_launch_dir_exists",
                str(launch_dir),
                "exists",
                True,
                launch_dir.exists(),
                "provider imbalance launch directory is required",
            ),
            _check(
                "provider_launch_summary_readable",
                launch_summary_error or "ok",
                "is",
                "ok",
                not launch_summary_error,
                launch_summary_error or "provider imbalance launch summary could not be read",
            ),
            _check(
                "provider_imbalance_launch_ready",
                launch_ready,
                "is",
                True,
                launch_ready or not config.require_provider_launch_ready,
                "provider imbalance launch packet is not ready",
            ),
            _check(
                "provider_research_dir_exists",
                str(provider_research_dir),
                "exists",
                True,
                bool(str(provider_research_dir)) and provider_research_dir.exists(),
                "provider research root is required to review the full imbalance profile",
            ),
            _check(
                "experiment_catalog_ready",
                catalog_error or catalog_count,
                ">=",
                1,
                catalog is not None and catalog_count >= 1,
                catalog_error or "provider launch plus research roots did not produce cataloged manifests",
            ),
            _check(
                "strategy_evidence_review_ready",
                evidence_error or evidence_ready,
                "is",
                True,
                (evidence is not None and evidence_ready) or not config.require_strategy_evidence_ready,
                evidence_error or "full imbalance strategy evidence review is not ready",
            ),
            _check(
                "imbalance_launch_profile_complete",
                passed_required,
                "==",
                required_count,
                bool(required_count and passed_required == required_count),
                "not all full imbalance profile run types passed",
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
    launch_dir: Path,
    launch_summary: pd.DataFrame,
    provider_research_dir: Path,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
    checks: pd.DataFrame,
    output_dir: Path,
    config: ProviderMarketDataImbalanceLaunchEvidenceConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    evidence_summary = evidence.summary if evidence is not None else pd.DataFrame()
    passed_required = int(_first_number(evidence_summary, "passed_required_run_types"))
    required_count = int(_first_number(evidence_summary, "required_run_type_count"))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_launch_ready": _first_bool(launch_summary, "ready"),
                "strategy_evidence_ready": bool(evidence.ready) if evidence is not None else False,
                "provider_launch_dir": str(launch_dir),
                "provider_research_dir": str(provider_research_dir),
                "output_dir": str(output_dir),
                "catalog_dir": "" if catalog is None else str(catalog.output_dir or ""),
                "strategy_evidence_dir": "" if evidence is None else str(evidence.output_dir or ""),
                "evidence_profile": PROFILE,
                "provider": _first_text(launch_summary, "provider"),
                "transport": _first_text(launch_summary, "transport"),
                "exchange": _first_text(launch_summary, "exchange"),
                "source_session_timezone": _first_text(launch_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(launch_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(launch_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(launch_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(launch_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(launch_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(launch_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(launch_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(launch_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(launch_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(launch_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    launch_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    launch_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    launch_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    launch_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    launch_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    launch_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    launch_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    launch_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
                ),
                "capture_env_template_path": _first_text(launch_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(launch_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(launch_summary, "capture_env_template_exists"),
                "capture_env_template_sha256": _first_text(launch_summary, "capture_env_template_sha256"),
                "adapter_handoff_path": _first_text(launch_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(launch_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(launch_summary, "adapter_handoff_exists"),
                "adapter_handoff_sha256": _first_text(launch_summary, "adapter_handoff_sha256"),
                "source_credential_env_template_path": _first_text(
                    launch_summary, "source_credential_env_template_path"
                ),
                "source_credential_env_template_exists": _first_bool(
                    launch_summary, "source_credential_env_template_exists"
                ),
                "source_credential_env_template_sha256": _first_text(
                    launch_summary, "source_credential_env_template_sha256"
                ),
                "source_live_fetch_contract_available": _first_bool(
                    launch_summary, "source_live_fetch_contract_available"
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    launch_summary, "source_live_fetch_contract_next_gate"
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    launch_summary, "source_live_fetch_contract_command_template"
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    launch_summary, "source_live_fetch_contract_exchange"
                ),
                "source_live_fetch_contract_market": _first_text(
                    launch_summary, "source_live_fetch_contract_market"
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    launch_summary, "source_live_fetch_contract_session_timezone"
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    launch_summary, "source_live_fetch_contract_session_open_local"
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    launch_summary, "source_live_fetch_contract_session_close_local"
                ),
                "market": _first_text(evidence_summary, "market") or _first_text(launch_summary, "market"),
                "strategy": _first_text(evidence_summary, "strategy") or _first_text(launch_summary, "strategy"),
                "catalog_run_count": 0 if catalog is None else catalog.run_count,
                "passed_required_run_types": passed_required,
                "required_run_type_count": required_count,
                "dirty_runs": int(_first_number(evidence_summary, "dirty_runs")),
                "allow_dirty_git": bool(config.allow_dirty_git),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "score_provider_imbalance_shadow_readiness"
                if ready
                else "repair_provider_imbalance_launch_evidence",
                "next_gate": "score-strategy-readiness" if ready else _blocked_next_gate(checks),
                "next_gate_help_command": _ready_help_command() if ready else _blocked_help_command(checks),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "score_provider_imbalance_shadow_readiness",
                    "reason": "provider imbalance launch evidence satisfies the full imbalance profile",
                    "next_gate": "score-strategy-readiness",
                    "next_gate_help_command": _ready_help_command(),
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
                "action": "repair_provider_imbalance_launch_evidence",
                "reason": "provider imbalance launch evidence review is not ready",
                "next_gate": "review-provider-market-data-imbalance-launch-evidence",
                "next_gate_help_command": (
                    "python -m hft_cli review-provider-market-data-imbalance-launch-evidence --help"
                ),
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    launch_summary: pd.DataFrame,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceLaunchEvidenceConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "provider_launch": _first_record(launch_summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "capture_bundle": _provider_capture_bundle(launch_summary),
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
        return "review-provider-market-data-imbalance-launch-evidence"
    return _next_gate_for_check(failed[0])


def _blocked_help_command(checks: pd.DataFrame) -> str:
    return _help_command_for_gate(_blocked_next_gate(checks))


def _next_gate_for_check(check: str) -> str:
    if check.startswith("provider_launch") or check.startswith("provider_imbalance_launch"):
        return "pipeline-provider-market-data-imbalance-launch"
    if check.startswith("provider_research"):
        return "run-provider-market-data-imbalance-research"
    if check.startswith("experiment_catalog"):
        return "catalog-runs"
    if (
        check.startswith("strategy_evidence")
        or check.startswith("imbalance_launch_profile")
        or check.startswith("strategy_identity")
        or check.startswith("market_identity")
    ):
        return "review-strategy-evidence"
    return "review-provider-market-data-imbalance-launch-evidence"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "pipeline-provider-market-data-imbalance-launch":
        return "python -m hft_cli pipeline-provider-market-data-imbalance-launch --help"
    if next_gate == "run-provider-market-data-imbalance-research":
        return "python -m hft_cli run-provider-market-data-imbalance-research --help"
    if next_gate == "catalog-runs":
        return "python -m hft_cli catalog-runs --help"
    if next_gate == "review-strategy-evidence":
        return "python -m hft_cli review-strategy-evidence --profile imbalance --help"
    if next_gate == "score-strategy-readiness":
        return _ready_help_command()
    return "python -m hft_cli review-provider-market-data-imbalance-launch-evidence --help"


def _ready_help_command() -> str:
    return "python -m hft_cli score-strategy-readiness --profile imbalance --help"


def _repair_action(check: str) -> str:
    if check.startswith("provider_launch") or check.startswith("provider_imbalance_launch"):
        return "build_provider_imbalance_launch_packet"
    if check.startswith("provider_research"):
        return "rerun_provider_imbalance_research"
    if check.startswith("experiment_catalog"):
        return "catalog_provider_imbalance_launch_evidence"
    if check.startswith("strategy_evidence") or check.startswith("imbalance_launch_profile"):
        return "review_full_imbalance_launch_evidence"
    return "repair_provider_imbalance_launch_evidence"


def _reason_for_check(
    check: str,
    catalog: ExperimentCatalog | None,
    evidence: StrategyEvidenceReview | None,
) -> str:
    if evidence is not None and not evidence.checks.empty:
        failed = evidence.checks.loc[~evidence.checks["passed"].astype(bool)]
        if not failed.empty and (
            check.startswith("strategy_evidence")
            or check.startswith("imbalance_launch_profile")
            or check.startswith("strategy_identity")
            or check.startswith("market_identity")
        ):
            return str(failed.iloc[0].get("reason", "strategy evidence review is not ready"))
    if catalog is not None and catalog.summary is not None and not catalog.summary.empty and check.startswith("experiment_catalog"):
        return str(catalog.summary.iloc[0].get("recommendation", "catalog provider imbalance launch evidence"))
    return check.replace("_", " ")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Launch Evidence",
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


def _provider_capture_bundle(launch_summary: pd.DataFrame) -> dict[str, Any]:
    return {
        "capture_bundle_path": _first_text(launch_summary, "capture_bundle_path"),
        "capture_bundle_provided": _first_bool(launch_summary, "capture_bundle_provided"),
        "capture_bundle_exists": _first_bool(launch_summary, "capture_bundle_exists"),
        "capture_bundle_ready": _first_bool(launch_summary, "capture_bundle_ready"),
        "exchange": _first_text(launch_summary, "capture_bundle_exchange"),
        "source_session": {
            "timezone": _first_text(launch_summary, "capture_bundle_source_session_timezone"),
            "open_local": _first_text(launch_summary, "capture_bundle_source_session_open_local"),
            "close_local": _first_text(launch_summary, "capture_bundle_source_session_close_local"),
        },
        "market_session": {
            "timezone": _first_text(launch_summary, "capture_bundle_market_session_timezone"),
            "open_local": _first_text(launch_summary, "capture_bundle_market_session_open_local"),
            "close_local": _first_text(launch_summary, "capture_bundle_market_session_close_local"),
        },
        "capture_bundle_metadata_matches_session": _first_bool(
            launch_summary, "capture_bundle_metadata_matches_session"
        ),
        "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
            launch_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "metadata_matches_session": _first_bool(launch_summary, "capture_bundle_metadata_matches_session"),
        "live_fetch_contract_metadata_matches_session": _first_bool(
            launch_summary, "capture_bundle_live_fetch_contract_metadata_matches_session"
        ),
        "capture_env_template_path": _first_text(launch_summary, "capture_env_template_path"),
        "capture_env_template_provided": _first_bool(launch_summary, "capture_env_template_provided"),
        "capture_env_template_exists": _first_bool(launch_summary, "capture_env_template_exists"),
        "capture_env_template_sha256": _first_text(launch_summary, "capture_env_template_sha256"),
        "adapter_handoff_path": _first_text(launch_summary, "adapter_handoff_path"),
        "adapter_handoff_provided": _first_bool(launch_summary, "adapter_handoff_provided"),
        "adapter_handoff_exists": _first_bool(launch_summary, "adapter_handoff_exists"),
        "adapter_handoff_sha256": _first_text(launch_summary, "adapter_handoff_sha256"),
        "source_credential_env_template_path": _first_text(
            launch_summary, "source_credential_env_template_path"
        ),
        "source_credential_env_template_exists": _first_bool(
            launch_summary, "source_credential_env_template_exists"
        ),
        "source_credential_env_template_sha256": _first_text(
            launch_summary, "source_credential_env_template_sha256"
        ),
        "source_live_fetch_contract_available": _first_bool(
            launch_summary, "source_live_fetch_contract_available"
        ),
        "source_live_fetch_contract_next_gate": _first_text(
            launch_summary, "source_live_fetch_contract_next_gate"
        ),
        "source_live_fetch_contract_command_template": _first_text(
            launch_summary, "source_live_fetch_contract_command_template"
        ),
        "source_live_fetch_contract_exchange": _first_text(
            launch_summary, "source_live_fetch_contract_exchange"
        ),
        "source_live_fetch_contract_market": _first_text(
            launch_summary, "source_live_fetch_contract_market"
        ),
        "source_live_fetch_contract_session_timezone": _first_text(
            launch_summary, "source_live_fetch_contract_session_timezone"
        ),
        "source_live_fetch_contract_session_open_local": _first_text(
            launch_summary, "source_live_fetch_contract_session_open_local"
        ),
        "source_live_fetch_contract_session_close_local": _first_text(
            launch_summary, "source_live_fetch_contract_session_close_local"
        ),
    }


def _path_from_text(value: str) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


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
