from __future__ import annotations

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


@dataclass(frozen=True)
class StrategyScorecardThresholds:
    profiles: tuple[str, ...] = DEFAULT_SCORECARD_PROFILES
    expected_market: str | None = None
    allow_dirty_git: bool = False
    require_file_inputs: bool = False


@dataclass(frozen=True)
class StrategyScorecardReport:
    scorecard: pd.DataFrame
    gaps: pd.DataFrame
    summary: pd.DataFrame
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
        expected_strategy = _expected_strategy(profile_key)
        expected_market = _normalize_identity(thresholds.expected_market)
        profile_catalog = _filter_catalog(catalog, strategy=expected_strategy, market=expected_market)
        required_run_types = evidence_profile_run_types(profile_key)
        evidence = evaluate_strategy_evidence(
            profile_catalog,
            thresholds=EvidenceThresholds(
                required_run_types=required_run_types,
                allow_dirty_git=thresholds.allow_dirty_git,
                require_same_strategy=bool(expected_strategy),
                require_same_market=bool(expected_market),
                expected_strategy=expected_strategy,
                expected_market=expected_market or None,
                require_file_inputs=thresholds.require_file_inputs,
            ),
        )
        rows.append(_scorecard_row(profile_key, expected_strategy, expected_market, evidence))
        gap_rows.extend(_gap_rows(profile_key, expected_strategy, expected_market, evidence.evidence))

    scorecard = _rank_scorecard(pd.DataFrame(rows))
    gaps = pd.DataFrame(gap_rows)
    summary = _summary(scorecard)
    return StrategyScorecardReport(scorecard=scorecard, gaps=gaps, summary=summary)


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
    write_experiment_manifest(
        out,
        run_type="strategy_scorecard",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"catalog": catalog_file},
    )
    return StrategyScorecardReport(report.scorecard, report.gaps, report.summary, out)


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
    return {
        "profile": profile,
        "strategy": expected_strategy or str(summary.get("strategy", "")),
        "market": expected_market or str(summary.get("market", "")),
        "ready": bool(summary.get("ready", False)),
        "readiness_score": float(score),
        "passed_required_run_types": passed_count,
        "required_run_type_count": required_count,
        "missing_required_run_types": ";".join(missing),
        "blocked_required_run_types": ";".join(blocked),
        "failed_checks": int(_numeric(summary.get("failed_checks", 0))),
        "dirty_runs": int(_numeric(summary.get("dirty_runs", 0))),
        "git_commit_count": int(_numeric(summary.get("git_commit_count", 0))),
        "latest_generated_at_utc": latest_generated,
        "recommendation": _score_recommendation(profile, bool(summary.get("ready", False)), score),
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
        rows.append(
            {
                "profile": profile,
                "strategy": expected_strategy,
                "market": expected_market,
                "required_run_type": row.get("required_run_type", ""),
                "passed": passed,
                "passed_runs": int(_numeric(row.get("passed_runs", 0))),
                "failed_runs": int(_numeric(row.get("failed_runs", 0))),
                "unknown_status_runs": int(_numeric(row.get("unknown_status_runs", 0))),
                "total_runs": total_runs,
                "latest_status": bool(row.get("latest_status", False)),
                "latest_generated_at_utc": row.get("latest_generated_at_utc", ""),
                "latest_run_dir": row.get("latest_run_dir", ""),
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
                "ready_profile_names": ";".join(ready["profile"].astype(str).tolist()),
                "blocked_profile_names": ";".join(blocked["profile"].astype(str).tolist()),
                "recommendation": "promote_ready_strategy_to_shadow_scaleup_review"
                if has_ready
                else "complete_missing_research_evidence",
            }
        ]
    )


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


def _expected_strategy(profile: str) -> str:
    return _normalize_strategy(PROFILE_STRATEGY_HINTS.get(profile, ""))


def _latest_generated_at(items: pd.DataFrame) -> str:
    if items.empty or "latest_generated_at_utc" not in items.columns:
        return ""
    values = [str(value) for value in items["latest_generated_at_utc"].dropna() if str(value)]
    return max(values) if values else ""


def _score_recommendation(profile: str, ready: bool, score: float) -> str:
    if ready:
        return "ready_for_shadow_scaleup_review"
    if score <= 0:
        return "start_profile_research_evidence"
    if score < 1:
        return "complete_profile_evidence_gaps"
    if profile == "ops_launch":
        return "review_ops_launch_checks"
    return "review_profile_checks"


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


def _numeric(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number
