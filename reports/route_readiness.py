from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


ROUTE_READY_STATUS = "ready_for_live_dryrun_route_review"
PORTABLE_STATUSES = {"india_ready", "portable_research"}


@dataclass(frozen=True)
class RouteReadinessReview:
    pairs: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def build_route_readiness_review(
    market_portability_config: dict[str, Any],
    *,
    strategy_evidence_summaries: pd.DataFrame | None = None,
    ops_evidence_summaries: pd.DataFrame | None = None,
    require_ops_file_inputs: bool = True,
) -> RouteReadinessReview:
    strategy_evidence = _normalize_evidence_frame(strategy_evidence_summaries)
    ops_evidence = _normalize_evidence_frame(ops_evidence_summaries)
    pair_rows = [
        _pair_row(
            pair,
            strategy_evidence,
            ops_evidence,
            require_ops_file_inputs=require_ops_file_inputs,
        )
        for pair in _portability_pairs(market_portability_config)
    ]
    pairs = pd.DataFrame(pair_rows)
    gaps = pairs.loc[~pairs["route_ready"].astype(bool)].reset_index(drop=True) if not pairs.empty else pairs
    summary = _summary(pairs, gaps, require_ops_file_inputs=require_ops_file_inputs)
    config = _config(pairs, gaps, summary, market_portability_config, require_ops_file_inputs)
    return RouteReadinessReview(pairs=pairs, gaps=gaps, summary=summary, config=config)


def write_route_readiness_review(
    output_dir: str | Path,
    *,
    market_portability: str | Path,
    strategy_evidence: tuple[str | Path, ...] = (),
    ops_evidence: tuple[str | Path, ...] = (),
    require_ops_file_inputs: bool = True,
) -> RouteReadinessReview:
    portability_path = _market_portability_config_path(market_portability)
    market_portability_config = json.loads(portability_path.read_text(encoding="utf-8"))
    strategy_paths, strategy_summaries = _read_evidence_summaries(strategy_evidence)
    ops_paths, ops_summaries = _read_evidence_summaries(ops_evidence)
    review = build_route_readiness_review(
        market_portability_config,
        strategy_evidence_summaries=strategy_summaries,
        ops_evidence_summaries=ops_summaries,
        require_ops_file_inputs=require_ops_file_inputs,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    review.pairs.to_csv(out / "route_readiness_pairs.csv", index=False)
    review.gaps.to_csv(out / "route_readiness_gaps.csv", index=False)
    review.summary.to_csv(out / "route_readiness_summary.csv", index=False)
    action_queue = _action_queue(review.pairs)
    action_queue.to_csv(out / "route_readiness_action_queue.csv", index=False)
    (out / "route_readiness_runbook.md").write_text(
        _runbook_markdown(review.summary.iloc[0], review.pairs, review.gaps, action_queue),
        encoding="utf-8",
    )
    (out / "route_readiness_config.json").write_text(
        json.dumps(review.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="route_readiness_review",
        parameters={"require_ops_file_inputs": bool(require_ops_file_inputs)},
        inputs={
            "market_portability_config": portability_path,
            "strategy_evidence_summaries": strategy_paths,
            "ops_evidence_summaries": ops_paths,
        },
    )
    return RouteReadinessReview(review.pairs, review.gaps, review.summary, out, review.config)


def _portability_pairs(config: dict[str, Any]) -> list[dict[str, Any]]:
    ready = config.get("ready_pairs", []) or []
    gaps = config.get("gap_pairs", []) or []
    if not isinstance(ready, list) or not isinstance(gaps, list):
        raise ValueError("market portability config must contain list ready_pairs and gap_pairs")
    pairs = []
    for item in [*ready, *gaps]:
        if isinstance(item, dict):
            pairs.append(item)
    return pairs


def _pair_row(
    pair: dict[str, Any],
    strategy_evidence: pd.DataFrame,
    ops_evidence: pd.DataFrame,
    *,
    require_ops_file_inputs: bool,
) -> dict[str, Any]:
    strategy = _text(pair.get("strategy"))
    market = _text(pair.get("market"))
    portability_status = _text(pair.get("status"))
    strategy_profile = _text(pair.get("strategy_evidence_profile"))
    ops_profile = _text(pair.get("ops_evidence_profile")) or "ops_launch"
    portability_ready = portability_status in PORTABLE_STATUSES
    strategy_match = _match_evidence(
        strategy_evidence,
        expected_profile=strategy_profile,
        expected_strategy=strategy,
        expected_market=market,
        label="strategy",
    )
    ops_match = _match_evidence(
        ops_evidence,
        expected_profile=ops_profile,
        expected_strategy=strategy,
        expected_market=market,
        label="ops",
    )
    ops_non_file_inputs = (
        _number(ops_match.row.get("input_directory_count", 0))
        + _number(ops_match.row.get("input_other_count", 0))
        + _number(ops_match.row.get("input_unfingerprinted_count", 0))
        if ops_match.row
        else 0
    )
    ops_file_inputs_required = _to_bool(ops_match.row.get("require_file_inputs", False)) if ops_match.row else False
    ops_file_inputs_clean = bool(ops_file_inputs_required and ops_non_file_inputs == 0)
    status = _route_status(
        portability_ready=portability_ready,
        strategy_match=strategy_match,
        ops_match=ops_match,
        require_ops_file_inputs=require_ops_file_inputs,
        ops_file_inputs_clean=ops_file_inputs_clean,
    )
    route_ready = status == ROUTE_READY_STATUS
    return {
        "strategy": strategy,
        "market": market,
        "portability_status": portability_status,
        "portability_ready": bool(portability_ready),
        "strategy_evidence_profile": strategy_profile,
        "strategy_evidence_ready": bool(strategy_match.ready),
        "strategy_evidence_status": strategy_match.status,
        "strategy_evidence_source": strategy_match.source,
        "strategy_evidence_recommendation": strategy_match.recommendation,
        "ops_evidence_profile": ops_profile,
        "ops_evidence_ready": bool(ops_match.ready),
        "ops_evidence_status": ops_match.status,
        "ops_evidence_source": ops_match.source,
        "ops_evidence_recommendation": ops_match.recommendation,
        "ops_file_inputs_required": bool(ops_file_inputs_required),
        "ops_non_file_input_count": int(ops_non_file_inputs),
        "route_ready": bool(route_ready),
        "status": status,
        "blocker": "" if route_ready else _blocker(pair, status),
        "next_gate": "live_dryrun_route_review" if route_ready else _next_gate(pair, status),
        "next_gate_help_command": _next_gate_help_command(
            "live_dryrun_route_review" if route_ready else _next_gate(pair, status)
        ),
    }


@dataclass(frozen=True)
class EvidenceMatch:
    found: bool
    ready: bool
    status: str
    source: str
    recommendation: str
    row: dict[str, Any]


def _match_evidence(
    frame: pd.DataFrame,
    *,
    expected_profile: str,
    expected_strategy: str,
    expected_market: str,
    label: str,
) -> EvidenceMatch:
    empty = EvidenceMatch(
        found=False,
        ready=False,
        status=f"{label}_evidence_missing",
        source="",
        recommendation="",
        row={},
    )
    if frame.empty:
        return empty
    profile = _normalize_identity(expected_profile)
    candidates = frame.loc[frame["evidence_profile"].map(_normalize_identity) == profile].copy()
    if candidates.empty:
        return empty
    strategy_key = _normalize_strategy(expected_strategy)
    market_key = _normalize_identity(expected_market)
    identity = candidates.loc[
        (candidates["strategy"].map(_normalize_strategy) == strategy_key)
        & (candidates["market"].map(_normalize_identity) == market_key)
    ].copy()
    if identity.empty:
        return EvidenceMatch(
            found=False,
            ready=False,
            status=f"{label}_evidence_identity_mismatch",
            source="",
            recommendation="",
            row={},
        )
    identity["_ready_sort"] = identity["ready"].map(_to_bool)
    row = identity.sort_values("_ready_sort").iloc[-1].drop(labels=["_ready_sort"], errors="ignore").to_dict()
    ready = _to_bool(row.get("ready", False))
    return EvidenceMatch(
        found=True,
        ready=ready,
        status=f"{label}_evidence_ready" if ready else f"{label}_evidence_incomplete",
        source=_text(row.get("source_path")),
        recommendation=_text(row.get("recommendation")),
        row=row,
    )


def _route_status(
    *,
    portability_ready: bool,
    strategy_match: EvidenceMatch,
    ops_match: EvidenceMatch,
    require_ops_file_inputs: bool,
    ops_file_inputs_clean: bool,
) -> str:
    if not portability_ready:
        return "blocked_by_portability"
    if not strategy_match.found:
        return strategy_match.status
    if not strategy_match.ready:
        return "strategy_evidence_incomplete"
    if not ops_match.found:
        return ops_match.status
    if not ops_match.ready:
        return "ops_evidence_incomplete"
    if require_ops_file_inputs and not ops_file_inputs_clean:
        return "ops_file_provenance_not_gated"
    return ROUTE_READY_STATUS


def _next_gate(pair: dict[str, Any], status: str) -> str:
    if status == "blocked_by_portability":
        return _text(pair.get("next_gate"))
    if status.startswith("strategy_evidence"):
        return _text(pair.get("strategy_evidence_gate"))
    if status.startswith("ops") or status == "ops_file_provenance_not_gated":
        return _text(pair.get("ops_evidence_gate"))
    return ""


def _next_gate_help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    if not gate or gate in {"live_dryrun_route_review", "run_walkforward_and_paper_shadow_gates"}:
        return ""
    if gate == "run_market_profile_report_with_fee_assumptions":
        return "python -m hft_cli market-portability-report --help"
    command = gate.split()[0]
    cli_commands = {
        "market-portability-report",
        "review-route-readiness",
        "review-strategy-evidence",
    }
    if command in cli_commands:
        return f"python -m hft_cli {gate} --help"
    return ""


def _blocker(pair: dict[str, Any], status: str) -> str:
    if status == "blocked_by_portability":
        return _text(pair.get("blocker")) or status
    return status


def _summary(
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    *,
    require_ops_file_inputs: bool,
) -> pd.DataFrame:
    if pairs.empty:
        return pd.DataFrame(
            [
                {
                    "ready": False,
                    "strategy": "",
                    "market": "",
                    "strategy_count": 0,
                    "market_count": 0,
                    "pair_count": 0,
                    "route_ready_pairs": 0,
                    "gap_pairs": 0,
                    "strategy_evidence_ready_pairs": 0,
                    "ops_evidence_ready_pairs": 0,
                    "portability_blocked_pairs": 0,
                    "ops_file_provenance_blocked_pairs": 0,
                    "require_ops_file_inputs": bool(require_ops_file_inputs),
                    "ready_action_count": 0,
                    "blocked_action_count": 0,
                    "next_gate": "",
                    "next_gate_help_command": "",
                    "recommendation": "route_readiness_inputs_missing",
                }
            ]
        )
    route_ready = int(pairs["route_ready"].astype(bool).sum())
    gap_count = int(len(gaps))
    ready = bool(route_ready > 0 and gap_count == 0)
    route_pairs = pairs.loc[pairs["route_ready"].astype(bool)]
    identity_pairs = route_pairs if not route_pairs.empty else pairs
    strategies = sorted(set(identity_pairs["strategy"].astype(str))) if "strategy" in identity_pairs else []
    markets = sorted(set(identity_pairs["market"].astype(str))) if "market" in identity_pairs else []
    next_gate = _primary_next_gate(pairs, gaps, ready=ready)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategies[0] if len(strategies) == 1 else "",
                "market": markets[0] if len(markets) == 1 else "",
                "strategy_count": int(len(strategies)),
                "market_count": int(len(markets)),
                "pair_count": int(len(pairs)),
                "route_ready_pairs": route_ready,
                "gap_pairs": gap_count,
                "strategy_evidence_ready_pairs": int(pairs["strategy_evidence_ready"].astype(bool).sum()),
                "ops_evidence_ready_pairs": int(pairs["ops_evidence_ready"].astype(bool).sum()),
                "portability_blocked_pairs": int((pairs["status"].astype(str) == "blocked_by_portability").sum()),
                "ops_file_provenance_blocked_pairs": int(
                    (pairs["status"].astype(str) == "ops_file_provenance_not_gated").sum()
                ),
                "require_ops_file_inputs": bool(require_ops_file_inputs),
                "ready_action_count": route_ready,
                "blocked_action_count": int((~pairs["route_ready"].astype(bool)).sum()),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
                "recommendation": "eligible_for_live_dryrun_route_review"
                if ready
                else "complete_route_readiness_gaps",
            }
        ]
    )


def _primary_next_gate(pairs: pd.DataFrame, gaps: pd.DataFrame, *, ready: bool) -> str:
    if ready:
        ready_pairs = pairs.loc[pairs["route_ready"].astype(bool)] if not pairs.empty else pairs
        if not ready_pairs.empty:
            return _text(ready_pairs.iloc[0].get("next_gate"))
        return "live_dryrun_route_review"
    if not gaps.empty:
        return _text(gaps.iloc[0].get("next_gate"))
    return ""


def _config(
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    summary: pd.DataFrame,
    market_portability_config: dict[str, Any],
    require_ops_file_inputs: bool,
) -> dict[str, Any]:
    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    ready_pairs = pairs.loc[pairs["route_ready"].astype(bool)].copy() if not pairs.empty else pairs
    return {
        "schema_version": 1,
        "ready": bool(summary_row.get("ready", False)),
        "summary": _jsonable_row(summary_row),
        "require_ops_file_inputs": bool(require_ops_file_inputs),
        "market_portability_ready": bool(market_portability_config.get("ready", False)),
        "route_ready_pairs": _records(ready_pairs),
        "gap_pairs": _records(gaps),
        "next_gates": sorted(set(gaps["next_gate"].astype(str))) if not gaps.empty else [],
        "ready_action_count": int(pairs["route_ready"].astype(bool).sum()) if not pairs.empty else 0,
        "blocked_action_count": int((~pairs["route_ready"].astype(bool)).sum()) if not pairs.empty else 0,
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    columns = [
        "strategy",
        "market",
        "portability_status",
        "strategy_evidence_profile",
        "strategy_evidence_status",
        "strategy_evidence_source",
        "strategy_evidence_recommendation",
        "strategy_evidence_ready",
        "ops_evidence_profile",
        "ops_evidence_status",
        "ops_evidence_source",
        "ops_evidence_recommendation",
        "ops_evidence_ready",
        "ops_file_inputs_required",
        "ops_non_file_input_count",
        "route_ready",
        "status",
        "blocker",
        "next_gate",
        "next_gate_help_command",
    ]
    available = [column for column in columns if column in frame.columns]
    return [_jsonable_row(row) for row in frame[available].to_dict(orient="records")]


def _action_queue(pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not pairs.empty:
        ordered = pairs.sort_values(["route_ready", "strategy", "market"], ascending=[False, True, True])
        for priority, row in enumerate(ordered.to_dict(orient="records"), start=1):
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "ready" if bool(row.get("route_ready", False)) else "blocked",
                    "strategy": _text(row.get("strategy")),
                    "market": _text(row.get("market")),
                    "status": _text(row.get("status")),
                    "blocker": _text(row.get("blocker")),
                    "next_gate": _text(row.get("next_gate")),
                    "next_gate_help_command": _text(row.get("next_gate_help_command")),
                    "strategy_evidence_profile": _text(row.get("strategy_evidence_profile")),
                    "strategy_evidence_status": _text(row.get("strategy_evidence_status")),
                    "ops_evidence_profile": _text(row.get("ops_evidence_profile")),
                    "ops_evidence_status": _text(row.get("ops_evidence_status")),
                    "ops_file_inputs_required": bool(row.get("ops_file_inputs_required", False)),
                    "ops_non_file_input_count": int(_number(row.get("ops_non_file_input_count", 0))),
                    "recommendation": _route_action_recommendation(row),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "strategy",
            "market",
            "status",
            "blocker",
            "next_gate",
            "next_gate_help_command",
            "strategy_evidence_profile",
            "strategy_evidence_status",
            "ops_evidence_profile",
            "ops_evidence_status",
            "ops_file_inputs_required",
            "ops_non_file_input_count",
            "recommendation",
        ],
    )


def _route_action_recommendation(row: dict[str, Any]) -> str:
    if bool(row.get("route_ready", False)):
        return "ready_for_live_dryrun_route_review"
    status = _text(row.get("status"))
    if status == "ops_evidence_incomplete":
        return _text(row.get("ops_evidence_recommendation")) or "complete_ops_launch_evidence"
    if status.startswith("ops"):
        return "complete_ops_launch_evidence"
    if status == "strategy_evidence_incomplete":
        return _text(row.get("strategy_evidence_recommendation")) or "complete_strategy_evidence"
    if status.startswith("strategy"):
        return "complete_strategy_evidence"
    if status == "blocked_by_portability":
        return "resolve_market_portability_gap"
    return "complete_route_readiness_gaps"


def _runbook_markdown(
    summary_row: pd.Series,
    pairs: pd.DataFrame,
    gaps: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Route Readiness Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Route-ready pairs: {int(_number(summary_row.get('route_ready_pairs', 0)))}",
        f"- Gap pairs: {int(_number(summary_row.get('gap_pairs', 0)))}",
        f"- Require ops file inputs: {str(_to_bool(summary_row.get('require_ops_file_inputs', False))).lower()}",
        "",
        "## Action Queue",
        "",
        _action_queue_table(action_queue),
        "",
        "## Route Pairs",
        "",
        _pairs_table(pairs),
        "",
        "## Gaps",
        "",
        _pairs_table(gaps),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    return _markdown_table(
        ["Priority", "Status", "Strategy", "Market", "Next gate", "Help", "Recommendation"],
        [
            [
                str(int(_number(row.get("priority", 0)))),
                _text(row.get("queue_status")),
                _text(row.get("strategy")),
                _text(row.get("market")),
                _code(row.get("next_gate")),
                _code(row.get("next_gate_help_command")),
                _text(row.get("recommendation")),
            ]
            for row in action_queue.to_dict(orient="records")
        ],
    )


def _pairs_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_None_"
    return _markdown_table(
        ["Strategy", "Market", "Status", "Blocker", "Next gate"],
        [
            [
                _text(row.get("strategy")),
                _text(row.get("market")),
                _text(row.get("status")),
                _text(row.get("blocker")),
                _code(row.get("next_gate")),
            ]
            for row in frame.to_dict(orient="records")
        ],
    )


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _code(value: Any) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _escape_cell(value: Any) -> str:
    return _text(value).replace("|", "\\|")


def _read_evidence_summaries(paths: tuple[str | Path, ...]) -> tuple[list[Path], pd.DataFrame]:
    summary_paths = [_evidence_summary_path(path) for path in paths]
    rows: list[dict[str, Any]] = []
    for path in summary_paths:
        frame = pd.read_csv(path)
        for _, row in frame.iterrows():
            item = row.to_dict()
            item["source_path"] = str(path)
            rows.append(item)
    return summary_paths, pd.DataFrame(rows)


def _normalize_evidence_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(
            columns=[
                "ready",
                "evidence_profile",
                "strategy",
                "market",
                "recommendation",
                "require_file_inputs",
                "input_directory_count",
                "input_other_count",
                "input_unfingerprinted_count",
                "source_path",
            ]
        )
    normalized = frame.copy()
    for column in [
        "ready",
        "evidence_profile",
        "strategy",
        "market",
        "recommendation",
        "require_file_inputs",
        "input_directory_count",
        "input_other_count",
        "input_unfingerprinted_count",
        "source_path",
    ]:
        if column not in normalized.columns:
            normalized[column] = "" if column not in {"ready", "require_file_inputs"} else False
    return normalized


def _market_portability_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "market_portability_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"market portability config not found: {candidate}")
    return candidate


def _evidence_summary_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "strategy_evidence_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"strategy evidence summary not found: {candidate}")
    return candidate


def _normalize_strategy(value: Any) -> str:
    normalized = _normalize_identity(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(normalized, normalized)


def _normalize_identity(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _number(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if pd.isna(number):
        return 0
    return int(number)


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
