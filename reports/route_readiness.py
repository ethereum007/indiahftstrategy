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
                    "pair_count": 0,
                    "route_ready_pairs": 0,
                    "gap_pairs": 0,
                    "strategy_evidence_ready_pairs": 0,
                    "ops_evidence_ready_pairs": 0,
                    "portability_blocked_pairs": 0,
                    "ops_file_provenance_blocked_pairs": 0,
                    "require_ops_file_inputs": bool(require_ops_file_inputs),
                    "recommendation": "route_readiness_inputs_missing",
                }
            ]
        )
    route_ready = int(pairs["route_ready"].astype(bool).sum())
    gap_count = int(len(gaps))
    ready = bool(route_ready > 0 and gap_count == 0)
    return pd.DataFrame(
        [
            {
                "ready": ready,
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
                "recommendation": "eligible_for_live_dryrun_route_review"
                if ready
                else "complete_route_readiness_gaps",
            }
        ]
    )


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
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    columns = [
        "strategy",
        "market",
        "portability_status",
        "strategy_evidence_profile",
        "strategy_evidence_ready",
        "ops_evidence_ready",
        "ops_file_inputs_required",
        "ops_non_file_input_count",
        "route_ready",
        "status",
        "blocker",
        "next_gate",
    ]
    available = [column for column in columns if column in frame.columns]
    return [_jsonable_row(row) for row in frame[available].to_dict(orient="records")]


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
