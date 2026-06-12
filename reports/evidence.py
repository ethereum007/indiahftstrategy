from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


DEFAULT_REQUIRED_RUN_TYPES = ("proof_report", "stress_report", "promotion_report")


@dataclass(frozen=True)
class EvidenceThresholds:
    required_run_types: tuple[str, ...] = DEFAULT_REQUIRED_RUN_TYPES
    min_passed_per_type: int = 1
    allow_dirty_git: bool = False
    require_same_git_commit: bool = False


@dataclass(frozen=True)
class StrategyEvidenceReview:
    evidence: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_strategy_evidence(
    catalog: pd.DataFrame,
    *,
    thresholds: EvidenceThresholds | None = None,
) -> StrategyEvidenceReview:
    thresholds = thresholds or EvidenceThresholds()
    _validate_thresholds(thresholds)
    frame = _normalize_catalog(catalog)
    evidence = pd.DataFrame([_evidence_row(frame, run_type, thresholds) for run_type in thresholds.required_run_types])
    checks = _checks(frame, evidence, thresholds)
    summary = _summary(frame, evidence, checks, thresholds)
    return StrategyEvidenceReview(evidence=evidence, checks=checks, summary=summary)


def write_strategy_evidence_review(
    catalog_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: EvidenceThresholds | None = None,
) -> StrategyEvidenceReview:
    catalog_file = _catalog_path(catalog_path)
    catalog = pd.read_csv(catalog_file)
    thresholds = thresholds or EvidenceThresholds()
    review = evaluate_strategy_evidence(catalog, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    review.evidence.to_csv(out / "strategy_evidence_items.csv", index=False)
    review.checks.to_csv(out / "strategy_evidence_checks.csv", index=False)
    review.summary.to_csv(out / "strategy_evidence_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="strategy_evidence_review",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"catalog": catalog_file},
    )
    return StrategyEvidenceReview(review.evidence, review.checks, review.summary, out)


def _evidence_row(catalog: pd.DataFrame, run_type: str, thresholds: EvidenceThresholds) -> dict[str, Any]:
    matched = catalog.loc[catalog["run_type"].astype(str) == run_type].copy()
    if matched.empty:
        return {
            "required_run_type": run_type,
            "total_runs": 0,
            "passed_runs": 0,
            "failed_runs": 0,
            "unknown_status_runs": 0,
            "latest_run_dir": "",
            "latest_status": False,
            "latest_generated_at_utc": "",
            "latest_git_commit": "",
            "passed": False,
        }
    matched["summary_status_bool"] = matched["summary_status"].map(_to_optional_bool)
    latest = _latest_row(matched)
    passed_runs = int((matched["summary_status_bool"] == True).sum())  # noqa: E712 - pandas scalar comparison
    failed_runs = int((matched["summary_status_bool"] == False).sum())  # noqa: E712
    unknown_runs = int(matched["summary_status_bool"].isna().sum())
    return {
        "required_run_type": run_type,
        "total_runs": int(len(matched)),
        "passed_runs": passed_runs,
        "failed_runs": failed_runs,
        "unknown_status_runs": unknown_runs,
        "latest_run_dir": str(latest.get("run_dir", "")),
        "latest_status": bool(_to_bool(latest.get("summary_status", False))),
        "latest_generated_at_utc": str(latest.get("generated_at_utc", "")),
        "latest_git_commit": str(latest.get("git_commit", "")),
        "passed": bool(passed_runs >= thresholds.min_passed_per_type),
    }


def _checks(catalog: pd.DataFrame, evidence: pd.DataFrame, thresholds: EvidenceThresholds) -> pd.DataFrame:
    rows = [
        _check(
            f"required_run_type:{row.required_run_type}",
            int(row.passed_runs),
            ">=",
            thresholds.min_passed_per_type,
            bool(row.passed),
            f"{row.required_run_type} does not have enough passed runs",
        )
        for row in evidence.itertuples(index=False)
    ]
    dirty_runs = int(catalog["git_dirty"].map(_to_bool).sum()) if not catalog.empty else 0
    if not thresholds.allow_dirty_git:
        rows.append(
            _check(
                "clean_git_artifacts",
                dirty_runs,
                "==",
                0,
                dirty_runs == 0,
                "catalog contains runs generated from a dirty git tree",
            )
        )
    if thresholds.require_same_git_commit:
        commits = _passed_required_commits(catalog, evidence)
        rows.append(
            _check(
                "same_git_commit",
                len(commits),
                "==",
                1,
                len(commits) == 1,
                "passed required evidence spans multiple git commits or no commit",
            )
        )
    return pd.DataFrame(rows)


def _summary(
    catalog: pd.DataFrame,
    evidence: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: EvidenceThresholds,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    passed_required = int(evidence["passed"].astype(bool).sum()) if not evidence.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "failed_checks": failed,
                "recommendation": "eligible_for_shadow_scaleup_review" if ready else "evidence_incomplete",
                "run_count": int(len(catalog)),
                "required_run_types": ";".join(thresholds.required_run_types),
                "passed_required_run_types": passed_required,
                "required_run_type_count": int(len(thresholds.required_run_types)),
                "min_passed_per_type": int(thresholds.min_passed_per_type),
                "dirty_runs": int(catalog["git_dirty"].map(_to_bool).sum()) if not catalog.empty else 0,
                "git_commit_count": int(catalog["git_commit"].dropna().nunique()) if not catalog.empty else 0,
            }
        ]
    )


def _normalize_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    frame = catalog.copy()
    for column in [
        "run_dir",
        "run_type",
        "generated_at_utc",
        "git_commit",
        "git_dirty",
        "summary_status",
    ]:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame


def _latest_row(frame: pd.DataFrame) -> pd.Series:
    work = frame.copy()
    work["_generated_sort"] = work["generated_at_utc"].astype(str)
    return work.sort_values("_generated_sort").iloc[-1]


def _passed_required_commits(catalog: pd.DataFrame, evidence: pd.DataFrame) -> set[str]:
    required = set(evidence.loc[evidence["passed"].astype(bool), "required_run_type"].astype(str))
    if not required:
        return set()
    work = catalog.copy()
    work["summary_status_bool"] = work["summary_status"].map(_to_optional_bool)
    passed = work.loc[work["run_type"].astype(str).isin(required) & (work["summary_status_bool"] == True)]  # noqa: E712
    return {str(value) for value in passed["git_commit"].dropna() if str(value)}


def _catalog_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "experiment_catalog.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"experiment catalog not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: EvidenceThresholds) -> None:
    if not thresholds.required_run_types:
        raise ValueError("required_run_types must not be empty")
    if thresholds.min_passed_per_type <= 0:
        raise ValueError("min_passed_per_type must be positive")
    blanks = [run_type for run_type in thresholds.required_run_types if not str(run_type).strip()]
    if blanks:
        raise ValueError("required_run_types must not contain blanks")


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _to_optional_bool(value: Any) -> bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None
    return bool(value)


def _to_bool(value: Any) -> bool:
    result = _to_optional_bool(value)
    return bool(result) if result is not None else False
