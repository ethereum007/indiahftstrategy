from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.evidence import (
    EVIDENCE_PROFILE_RUN_TYPES,
    EvidenceThresholds,
    evaluate_strategy_evidence,
    evidence_profile_run_types,
    _market_identity,
    _normalize_identity,
    _normalize_strategy,
    _strategy_identity,
)
from reports.manifest import write_experiment_manifest


DEFAULT_SCORECARD_PROFILES = ("leadlag", "imbalance", "parity", "settlement", "surface_mm")
PROFILE_STRATEGY_HINTS = {
    "leadlag": "lead_lag_taker",
    "imbalance": "imbalance",
    "parity": "parity_box",
    "settlement": "settlement_convergence",
    "surface_mm": "surface_mm",
}
READY_NEXT_GATES = {
    "ops_launch": "review-route-readiness",
}
PROMOTION_NEXT_GATES = {
    "leadlag": "promote-leadlag-candidate",
    "imbalance": "promote-imbalance-candidate",
    "parity": "promote-parity-candidate",
    "settlement": "promote-settlement-candidate",
}
RUN_TYPE_NEXT_GATES = {
    "proof_report": "proof-report",
    "proof_refresh_gate": "review-proof-refresh",
    "stress_report": "stress-replay",
    "promotion_report": "promote-scenario",
    "shadow_session_comparison": "compare-shadow-sessions",
    "leadlag_edge_audit": "audit-leadlag-edge",
    "leadlag_replay_walkforward": "walkforward-leadlag-replay",
    "leadlag_order_plan": "plan-leadlag-orders",
    "leadlag_launch_pipeline": "pipeline-leadlag-launch",
    "imbalance_edge_walkforward": "walkforward-imbalance-edge",
    "imbalance_replay_walkforward": "walkforward-imbalance-replay",
    "imbalance_research_pipeline": "pipeline-imbalance-research",
    "imbalance_order_plan": "plan-imbalance-orders",
    "imbalance_launch_pipeline": "pipeline-imbalance-launch",
    "parity_edge_audit": "audit-parity-edge",
    "parity_sweep": "sweep-parity",
    "parity_order_plan": "plan-parity-orders",
    "parity_launch_pipeline": "pipeline-parity-launch",
    "settlement_convergence_walkforward": "walkforward-settlement-convergence",
    "settlement_order_plan": "plan-settlement-orders",
    "settlement_launch_pipeline": "pipeline-settlement-launch",
    "surface_quality_report": "review-surface-quality",
    "quote_risk_report": "review-quotes",
    "surface_mm_research_pipeline": "pipeline-surface-mm-research",
    "surface_mm_launch_pipeline": "pipeline-surface-mm-launch",
    "scaleup_plan": "plan-scaleup",
    "runtime_telemetry_snapshot": "build-runtime-telemetry",
    "runtime_guard": "monitor-scaleup-guard",
    "runtime_session_monitor": "monitor-runtime-session",
    "broker_readiness": "review-broker-readiness",
    "cutover_gate": "review-cutover-gate",
    "route_enable_packet": "review-route-enable",
    "broker_dispatch_plan": "plan-broker-dispatch",
    "broker_dispatch_send_packet": "prepare-broker-dispatch-send",
    "broker_dispatch_ack_reconciliation": "reconcile-broker-dispatch",
    "broker_dispatch_roundtrip": "review-broker-dispatch-roundtrip",
}
NEXT_GATE_HELP_COMMANDS = {
    gate: f"python -m hft_cli {gate} --help"
    for gate in sorted({*READY_NEXT_GATES.values(), *PROMOTION_NEXT_GATES.values(), *RUN_TYPE_NEXT_GATES.values()})
}


@dataclass(frozen=True)
class StrategyScorecardThresholds:
    profiles: tuple[str, ...] = DEFAULT_SCORECARD_PROFILES
    expected_market: str | None = None
    expected_ops_strategy: str | None = None
    allow_dirty_git: bool = False
    require_file_inputs: bool = False


@dataclass(frozen=True)
class StrategyScorecardReport:
    scorecard: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_scorecard(
    catalog: pd.DataFrame,
    *,
    thresholds: StrategyScorecardThresholds | None = None,
) -> StrategyScorecardReport:
    thresholds = thresholds or StrategyScorecardThresholds()
    _validate_thresholds(thresholds)
    rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    for profile in thresholds.profiles:
        profile_key = _profile_key(profile)
        expected_strategy = _expected_strategy(profile_key, thresholds)
        expected_market = _normalize_identity(thresholds.expected_market)
        profile_catalog = _filter_catalog(catalog, strategy=expected_strategy, market=expected_market)
        required_run_types = evidence_profile_run_types(profile_key)
        evidence = evaluate_strategy_evidence(
            profile_catalog,
            thresholds=EvidenceThresholds(
                required_run_types=required_run_types,
                allow_dirty_git=thresholds.allow_dirty_git,
                require_same_strategy=bool(expected_strategy) or profile_key == "ops_launch",
                require_same_market=bool(expected_market),
                expected_strategy=expected_strategy or None,
                expected_market=expected_market or None,
                require_file_inputs=thresholds.require_file_inputs,
            ),
        )
        rows.append(_scorecard_row(profile_key, expected_strategy, expected_market, evidence))
        gap_rows.extend(_gap_rows(profile_key, expected_strategy, expected_market, evidence.evidence))

    scorecard = _rank_scorecard(pd.DataFrame(rows))
    gaps = pd.DataFrame(gap_rows)
    summary = _summary(scorecard)
    config = _config(scorecard, gaps, summary)
    return StrategyScorecardReport(scorecard=scorecard, gaps=gaps, summary=summary, config=config)


def write_strategy_scorecard(
    catalog_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: StrategyScorecardThresholds | None = None,
) -> StrategyScorecardReport:
    catalog_file = _catalog_path(catalog_path)
    catalog = pd.read_csv(catalog_file)
    thresholds = thresholds or StrategyScorecardThresholds()
    report = evaluate_strategy_scorecard(catalog, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.scorecard.to_csv(out / "strategy_scorecard.csv", index=False)
    report.gaps.to_csv(out / "strategy_scorecard_gaps.csv", index=False)
    report.summary.to_csv(out / "strategy_scorecard_summary.csv", index=False)
    (out / "strategy_scorecard_next_actions.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "strategy_scorecard_runbook.md").write_text(
        _runbook_markdown(report.config),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="strategy_scorecard",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"catalog": catalog_file},
    )
    return StrategyScorecardReport(report.scorecard, report.gaps, report.summary, report.config, out)


def _scorecard_row(
    profile: str,
    expected_strategy: str,
    expected_market: str,
    evidence: Any,
) -> dict[str, Any]:
    summary = evidence.summary.iloc[0].to_dict() if not evidence.summary.empty else {}
    items = evidence.evidence.copy()
    required_count = int(summary.get("required_run_type_count", len(items)))
    passed_count = int(summary.get("passed_required_run_types", 0))
    missing = items.loc[items["total_runs"].astype(int) == 0, "required_run_type"].astype(str).tolist()
    blocked = items.loc[
        (items["total_runs"].astype(int) > 0) & (~items["passed"].astype(bool)),
        "required_run_type",
    ].astype(str).tolist()
    latest_generated = _latest_generated_at(items)
    score = passed_count / required_count if required_count else 0.0
    ready = bool(summary.get("ready", False))
    next_required_run_type = _next_required_run_type(items)
    return {
        "profile": profile,
        "strategy": expected_strategy or str(summary.get("strategy", "")),
        "market": expected_market or str(summary.get("market", "")),
        "ready": ready,
        "readiness_score": float(score),
        "passed_required_run_types": passed_count,
        "required_run_type_count": required_count,
        "missing_required_run_types": ";".join(missing),
        "blocked_required_run_types": ";".join(blocked),
        "next_required_run_type": next_required_run_type,
        "next_gate": _next_gate(profile, ready, next_required_run_type),
        "next_gate_help_command": _next_gate_help_command(_next_gate(profile, ready, next_required_run_type)),
        "failed_checks": int(_numeric(summary.get("failed_checks", 0))),
        "dirty_runs": int(_numeric(summary.get("dirty_runs", 0))),
        "git_commit_count": int(_numeric(summary.get("git_commit_count", 0))),
        "latest_generated_at_utc": latest_generated,
        "recommendation": _score_recommendation(profile, ready, score),
    }


def _gap_rows(
    profile: str,
    expected_strategy: str,
    expected_market: str,
    evidence: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in evidence.to_dict(orient="records"):
        total_runs = int(_numeric(row.get("total_runs", 0)))
        passed = bool(row.get("passed", False))
        required_run_type = row.get("required_run_type", "")
        rows.append(
            {
                "profile": profile,
                "strategy": expected_strategy,
                "market": expected_market,
                "required_run_type": required_run_type,
                "passed": passed,
                "passed_runs": int(_numeric(row.get("passed_runs", 0))),
                "failed_runs": int(_numeric(row.get("failed_runs", 0))),
                "unknown_status_runs": int(_numeric(row.get("unknown_status_runs", 0))),
                "total_runs": total_runs,
                "latest_status": bool(row.get("latest_status", False)),
                "latest_generated_at_utc": row.get("latest_generated_at_utc", ""),
                "latest_run_dir": row.get("latest_run_dir", ""),
                "next_gate": "" if passed else _next_gate(profile, False, str(required_run_type)),
                "next_gate_help_command": ""
                if passed
                else _next_gate_help_command(_next_gate(profile, False, str(required_run_type))),
                "gap": "" if passed else ("missing_required_run_type" if total_runs == 0 else "required_run_type_not_passing"),
            }
        )
    return rows


def _summary(scorecard: pd.DataFrame) -> pd.DataFrame:
    if scorecard.empty:
        return pd.DataFrame(
            [
                {
                    "ready": False,
                    "profile_count": 0,
                    "ready_profiles": 0,
                    "blocked_profiles": 0,
                    "best_profile": "",
                    "best_strategy": "",
                    "best_market": "",
                    "best_readiness_score": 0.0,
                "best_next_required_run_type": "",
                "best_next_gate": "",
                "best_next_gate_help_command": "",
                "ready_profile_names": "",
                    "blocked_profile_names": "",
                    "recommendation": "no_profiles_to_score",
                }
            ]
        )
    ready = scorecard.loc[scorecard["ready"].astype(bool)]
    blocked = scorecard.loc[~scorecard["ready"].astype(bool)]
    best = scorecard.sort_values(
        ["ready", "readiness_score", "passed_required_run_types", "latest_generated_at_utc"],
        ascending=[False, False, False, False],
    ).iloc[0]
    has_ready = not ready.empty
    return pd.DataFrame(
        [
            {
                "ready": has_ready,
                "profile_count": int(len(scorecard)),
                "ready_profiles": int(len(ready)),
                "blocked_profiles": int(len(blocked)),
                "best_profile": best["profile"],
                "best_strategy": best["strategy"],
                "best_market": best["market"],
                "best_readiness_score": float(best["readiness_score"]),
                "best_next_required_run_type": best["next_required_run_type"],
                "best_next_gate": best["next_gate"],
                "best_next_gate_help_command": best["next_gate_help_command"],
                "ready_profile_names": ";".join(ready["profile"].astype(str).tolist()),
                "blocked_profile_names": ";".join(blocked["profile"].astype(str).tolist()),
                "recommendation": _summary_recommendation(str(best["profile"]), has_ready),
            }
        ]
    )


def _config(scorecard: pd.DataFrame, gaps: pd.DataFrame, summary: pd.DataFrame) -> dict[str, Any]:
    summary_row = _jsonable_row(summary.iloc[0].to_dict()) if not summary.empty else {}
    next_actions = [_action(row) for row in _records(scorecard)]
    ready_actions = [action for action in next_actions if action["ready"]]
    blocked_actions = [action for action in next_actions if not action["ready"]]
    gap_actions = [_gap_action(row) for row in _records(gaps) if str(row.get("gap", ""))]
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "best_profile": str(summary_row.get("best_profile", "")),
        "best_strategy": str(summary_row.get("best_strategy", "")),
        "best_market": str(summary_row.get("best_market", "")),
        "best_next_required_run_type": str(summary_row.get("best_next_required_run_type", "")),
        "best_next_gate": str(summary_row.get("best_next_gate", "")),
        "best_next_gate_help_command": str(summary_row.get("best_next_gate_help_command", "")),
        "recommendation": str(summary_row.get("recommendation", "")),
        "ready_action_count": len(ready_actions),
        "blocked_action_count": len(blocked_actions),
        "gap_count": len(gap_actions),
        "next_actions": next_actions,
        "ready_actions": ready_actions,
        "blocked_actions": blocked_actions,
        "gaps": gap_actions,
    }


def _action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(_numeric(row.get("rank", 0))),
        "profile": str(row.get("profile", "")),
        "strategy": str(row.get("strategy", "")),
        "market": str(row.get("market", "")),
        "ready": bool(row.get("ready", False)),
        "readiness_score": float(_numeric(row.get("readiness_score", 0.0))),
        "passed_required_run_types": int(_numeric(row.get("passed_required_run_types", 0))),
        "required_run_type_count": int(_numeric(row.get("required_run_type_count", 0))),
        "next_required_run_type": str(row.get("next_required_run_type", "")),
        "next_gate": str(row.get("next_gate", "")),
        "next_gate_help_command": str(row.get("next_gate_help_command", "")),
        "missing_required_run_types": _split_items(row.get("missing_required_run_types", "")),
        "blocked_required_run_types": _split_items(row.get("blocked_required_run_types", "")),
        "recommendation": str(row.get("recommendation", "")),
    }


def _gap_action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": str(row.get("profile", "")),
        "strategy": str(row.get("strategy", "")),
        "market": str(row.get("market", "")),
        "required_run_type": str(row.get("required_run_type", "")),
        "gap": str(row.get("gap", "")),
        "next_gate": str(row.get("next_gate", "")),
        "next_gate_help_command": str(row.get("next_gate_help_command", "")),
        "passed_runs": int(_numeric(row.get("passed_runs", 0))),
        "failed_runs": int(_numeric(row.get("failed_runs", 0))),
        "unknown_status_runs": int(_numeric(row.get("unknown_status_runs", 0))),
        "latest_run_dir": str(row.get("latest_run_dir", "")),
    }


def _runbook_markdown(config: dict[str, Any]) -> str:
    ready_label = "yes" if bool(config.get("ready", False)) else "no"
    lines = [
        "# Strategy Scorecard Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Best profile: {_text(config.get('best_profile'))}",
        f"- Best strategy: {_text(config.get('best_strategy'))}",
        f"- Best market: {_text(config.get('best_market'))}",
        f"- Recommendation: {_text(config.get('recommendation'))}",
        f"- Best next gate: {_code(config.get('best_next_gate'))}",
        f"- Best next gate help: {_code(config.get('best_next_gate_help_command'))}",
        f"- Ready actions: {int(_numeric(config.get('ready_action_count', 0)))}",
        f"- Blocked actions: {int(_numeric(config.get('blocked_action_count', 0)))}",
        f"- Open gaps: {int(_numeric(config.get('gap_count', 0)))}",
        "",
        "## Ready Actions",
        "",
        _actions_table(config.get("ready_actions", []), include_gaps=False),
        "",
        "## Blocked Actions",
        "",
        _actions_table(config.get("blocked_actions", []), include_gaps=True),
        "",
        "## Open Gaps",
        "",
        _gaps_table(config.get("gaps", [])),
        "",
    ]
    return "\n".join(lines)


def _actions_table(actions: Any, *, include_gaps: bool) -> str:
    rows = actions if isinstance(actions, list) else []
    if not rows:
        return "_None_"
    headers = ["Rank", "Profile", "Strategy", "Score", "Next gate", "Help"]
    table_rows = [
        [
            str(int(_numeric(row.get("rank", 0)))),
            _text(row.get("profile")),
            _text(row.get("strategy")),
            _format_score(row.get("readiness_score")),
            _code(row.get("next_gate")),
            _code(row.get("next_gate_help_command")),
        ]
        for row in rows
        if isinstance(row, dict)
    ]
    if include_gaps:
        headers.extend(["Missing", "Blocked"])
        for row, source in zip(table_rows, rows):
            if isinstance(source, dict):
                row.extend(
                    [
                        _list_text(source.get("missing_required_run_types")),
                        _list_text(source.get("blocked_required_run_types")),
                    ]
                )
    return _markdown_table(headers, table_rows)


def _gaps_table(gaps: Any) -> str:
    rows = gaps if isinstance(gaps, list) else []
    if not rows:
        return "_None_"
    return _markdown_table(
        ["Profile", "Required run type", "Gap", "Next gate", "Latest run"],
        [
            [
                _text(row.get("profile")),
                _text(row.get("required_run_type")),
                _text(row.get("gap")),
                _code(row.get("next_gate")),
                _text(row.get("latest_run_dir")),
            ]
            for row in rows
            if isinstance(row, dict)
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _format_score(value: Any) -> str:
    return f"{_numeric(value):.3f}"


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        items = [str(item) for item in value if str(item)]
    else:
        items = _split_items(value)
    return ", ".join(items)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_row(row) for row in frame.to_dict(orient="records")]


def _rank_scorecard(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ranked = frame.sort_values(
        ["ready", "readiness_score", "passed_required_run_types", "latest_generated_at_utc", "profile"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1, dtype=int))
    return ranked


def _filter_catalog(catalog: pd.DataFrame, *, strategy: str, market: str) -> pd.DataFrame:
    if catalog.empty:
        return catalog.copy()
    frame = catalog.copy()
    keep = []
    for _, row in frame.iterrows():
        keep.append(_matches_identity(row, strategy=strategy, market=market))
    return frame.loc[keep].copy()


def _matches_identity(row: pd.Series, *, strategy: str, market: str) -> bool:
    if strategy and _strategy_identity(row) != strategy:
        return False
    if market and _market_identity(row) != market:
        return False
    return True


def _profile_key(profile: str) -> str:
    required_run_types = evidence_profile_run_types(profile)
    for key, value in EVIDENCE_PROFILE_RUN_TYPES.items():
        if tuple(value) == tuple(required_run_types):
            return key
    return _normalize_identity(profile)


def _expected_strategy(profile: str, thresholds: StrategyScorecardThresholds) -> str:
    if profile == "ops_launch":
        return _normalize_strategy(thresholds.expected_ops_strategy)
    return _normalize_strategy(PROFILE_STRATEGY_HINTS.get(profile, ""))


def _latest_generated_at(items: pd.DataFrame) -> str:
    if items.empty or "latest_generated_at_utc" not in items.columns:
        return ""
    values = [str(value) for value in items["latest_generated_at_utc"].dropna() if str(value)]
    return max(values) if values else ""


def _next_required_run_type(items: pd.DataFrame) -> str:
    if items.empty or "passed" not in items.columns:
        return ""
    gaps = items.loc[~items["passed"].astype(bool)]
    if gaps.empty:
        return ""
    return str(gaps.iloc[0].get("required_run_type", ""))


def _next_gate(profile: str, ready: bool, required_run_type: str) -> str:
    if ready:
        return READY_NEXT_GATES.get(profile, "plan-scaleup")
    if required_run_type == "promotion_report":
        return PROMOTION_NEXT_GATES.get(profile, RUN_TYPE_NEXT_GATES[required_run_type])
    return RUN_TYPE_NEXT_GATES.get(required_run_type, "review-strategy-evidence")


def _next_gate_help_command(next_gate: str) -> str:
    if not next_gate:
        return ""
    return NEXT_GATE_HELP_COMMANDS.get(next_gate, f"python -m hft_cli {next_gate} --help")


def _score_recommendation(profile: str, ready: bool, score: float) -> str:
    if ready:
        if profile == "ops_launch":
            return "ready_for_live_dryrun_route_review"
        return "ready_for_shadow_scaleup_review"
    if score <= 0:
        if profile == "ops_launch":
            return "start_ops_launch_evidence"
        return "start_profile_research_evidence"
    if score < 1:
        if profile == "ops_launch":
            return "complete_ops_launch_evidence_gaps"
        return "complete_profile_evidence_gaps"
    if profile == "ops_launch":
        return "review_ops_launch_checks"
    return "review_profile_checks"


def _summary_recommendation(best_profile: str, has_ready: bool) -> str:
    if not has_ready:
        return "complete_missing_research_evidence"
    if best_profile == "ops_launch":
        return "promote_ready_route_to_live_dryrun_review"
    return "promote_ready_strategy_to_shadow_scaleup_review"


def _catalog_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "experiment_catalog.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"experiment catalog not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: StrategyScorecardThresholds) -> None:
    if not thresholds.profiles:
        raise ValueError("profiles must not be empty")
    for profile in thresholds.profiles:
        evidence_profile_run_types(profile)


def _split_items(value: Any) -> list[str]:
    return [item for item in str(value).split(";") if item]


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number
