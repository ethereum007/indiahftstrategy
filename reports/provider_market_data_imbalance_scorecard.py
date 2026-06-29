from __future__ import annotations

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
    catalog_path = evidence_dir / "catalog" / "experiment_catalog.csv"
    scorecard = None
    scorecard_error = ""
    scorecard_dir = out / "scorecard"
    if catalog_path.exists():
        try:
            scorecard = write_strategy_scorecard(
                catalog_path,
                output_dir=scorecard_dir,
                thresholds=StrategyScorecardThresholds(
                    profiles=(PROFILE,),
                    expected_market=config.expected_market or _first_text(evidence_summary, "market") or None,
                    allow_dirty_git=config.allow_dirty_git,
                    require_file_inputs=config.require_file_inputs,
                ),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            scorecard_error = str(exc)
    checks = _checks(
        evidence_dir,
        evidence_summary,
        evidence_summary_error,
        catalog_path,
        scorecard,
        scorecard_error,
        config,
    )
    summary = _summary(evidence_dir, evidence_summary, catalog_path, scorecard, checks, out, config)
    action_queue = _action_queue(summary.iloc[0], checks, scorecard)
    payload = _config(summary.iloc[0], evidence_summary, scorecard, checks, action_queue, config)

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
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
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


def _checks(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_summary_error: str,
    catalog_path: Path,
    scorecard: StrategyScorecardReport | None,
    scorecard_error: str,
    config: ProviderMarketDataImbalanceScorecardConfig,
) -> pd.DataFrame:
    scorecard_summary = scorecard.summary if scorecard is not None else pd.DataFrame()
    scorecard_ready = bool(scorecard.ready) if scorecard is not None else False
    best_profile = _first_text(scorecard_summary, "best_profile")
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
                "provider_imbalance_launch_evidence_ready",
                _first_bool(evidence_summary, "ready"),
                "is",
                True,
                _first_bool(evidence_summary, "ready") or not config.require_launch_evidence_ready,
                "provider imbalance launch evidence is not ready",
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
        "capture_bundle": {
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
            "source_live_fetch_contract_command_template": str(
                summary["source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_exchange": str(summary["source_live_fetch_contract_exchange"]),
            "source_live_fetch_contract_market": str(summary["source_live_fetch_contract_market"]),
            "source_live_fetch_contract_session_timezone": str(
                summary["source_live_fetch_contract_session_timezone"]
            ),
            "source_live_fetch_contract_session_open_local": str(
                summary["source_live_fetch_contract_session_open_local"]
            ),
            "source_live_fetch_contract_session_close_local": str(
                summary["source_live_fetch_contract_session_close_local"]
            ),
        },
        "provider_launch_evidence": _first_record(evidence_summary),
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
