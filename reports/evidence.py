from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


DEFAULT_REQUIRED_RUN_TYPES = ("proof_report", "stress_report", "promotion_report")
LEADLAG_REQUIRED_RUN_TYPES = (
    "leadlag_edge_audit",
    "leadlag_replay_walkforward",
    "stress_report",
    "promotion_report",
    "leadlag_order_plan",
    "leadlag_launch_pipeline",
)
IMBALANCE_REQUIRED_RUN_TYPES = (
    "imbalance_edge_walkforward",
    "imbalance_replay_walkforward",
    "promotion_report",
    "imbalance_research_pipeline",
    "imbalance_order_plan",
    "imbalance_launch_pipeline",
)
SETTLEMENT_REQUIRED_RUN_TYPES = (
    "settlement_convergence_walkforward",
    "promotion_report",
    "settlement_order_plan",
    "settlement_launch_pipeline",
)
PARITY_REQUIRED_RUN_TYPES = (
    "parity_edge_audit",
    "parity_sweep",
    "promotion_report",
    "parity_order_plan",
    "parity_launch_pipeline",
)
SURFACE_MM_REQUIRED_RUN_TYPES = ("surface_quality_report", "quote_risk_report", "surface_mm_research_pipeline")
EVIDENCE_PROFILE_RUN_TYPES = {
    "default": DEFAULT_REQUIRED_RUN_TYPES,
    "leadlag": LEADLAG_REQUIRED_RUN_TYPES,
    "imbalance": IMBALANCE_REQUIRED_RUN_TYPES,
    "settlement": SETTLEMENT_REQUIRED_RUN_TYPES,
    "parity": PARITY_REQUIRED_RUN_TYPES,
    "surface_mm": SURFACE_MM_REQUIRED_RUN_TYPES,
}
EVIDENCE_PROFILE_ALIASES = {
    "lead_lag": "leadlag",
    "lead_lag_taker": "leadlag",
    "leadlag_taker": "leadlag",
    "microprice_imbalance": "imbalance",
    "settlement_convergence": "settlement",
    "parity_box": "parity",
    "surface_market_making": "surface_mm",
}


def evidence_profile_run_types(profile: str | None = None) -> tuple[str, ...]:
    key = _normalize_identity(profile or "default")
    key = EVIDENCE_PROFILE_ALIASES.get(key, key)
    if key not in EVIDENCE_PROFILE_RUN_TYPES:
        profiles = ", ".join(sorted(EVIDENCE_PROFILE_RUN_TYPES))
        raise ValueError(f"unknown evidence profile {profile!r}; expected one of: {profiles}")
    return EVIDENCE_PROFILE_RUN_TYPES[key]


@dataclass(frozen=True)
class EvidenceThresholds:
    required_run_types: tuple[str, ...] = DEFAULT_REQUIRED_RUN_TYPES
    min_passed_per_type: int = 1
    allow_dirty_git: bool = False
    require_same_git_commit: bool = False
    require_same_strategy: bool = False
    require_same_market: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None


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
    passed = matched.loc[matched["summary_status_bool"] == True]  # noqa: E712
    identity = _latest_row(passed) if not passed.empty else latest
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
        "latest_strategy": _strategy_identity(identity),
        "latest_market": _market_identity(identity),
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
    passed_required = _passed_required_rows(catalog, evidence)
    if thresholds.require_same_strategy:
        strategies = _identity_values(passed_required, _strategy_identity)
        rows.append(
            _check(
                "same_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "count==",
                1,
                len(strategies) == 1 and _missing_identities(passed_required, _strategy_identity) == 0,
                "passed required evidence has missing or multiple strategy identities",
            )
        )
    if thresholds.expected_strategy is not None:
        expected = _normalize_strategy(thresholds.expected_strategy)
        strategies = _identity_values(passed_required, _strategy_identity)
        rows.append(
            _check(
                "expected_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "==",
                expected,
                strategies == {expected} and _missing_identities(passed_required, _strategy_identity) == 0,
                "passed required evidence does not match the expected strategy",
            )
        )
    if thresholds.require_same_market:
        markets = _identity_values(passed_required, _market_identity)
        rows.append(
            _check(
                "same_market",
                ";".join(sorted(markets)) if markets else "",
                "count==",
                1,
                len(markets) == 1 and _missing_identities(passed_required, _market_identity) == 0,
                "passed required evidence has missing or multiple market identities",
            )
        )
    if thresholds.expected_market is not None:
        expected = _normalize_identity(thresholds.expected_market)
        markets = _identity_values(passed_required, _market_identity)
        rows.append(
            _check(
                "expected_market",
                ";".join(sorted(markets)) if markets else "",
                "==",
                expected,
                markets == {expected} and _missing_identities(passed_required, _market_identity) == 0,
                "passed required evidence does not match the expected market",
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
    passed_required_rows = _passed_required_rows(catalog, evidence)
    strategies = _identity_values(passed_required_rows, _strategy_identity)
    markets = _identity_values(passed_required_rows, _market_identity)
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
                "strategy": next(iter(strategies)) if len(strategies) == 1 else "",
                "strategy_count": int(len(strategies)),
                "missing_strategy_runs": _missing_identities(passed_required_rows, _strategy_identity),
                "expected_strategy": _normalize_strategy(thresholds.expected_strategy)
                if thresholds.expected_strategy is not None
                else "",
                "market": next(iter(markets)) if len(markets) == 1 else "",
                "market_count": int(len(markets)),
                "missing_market_runs": _missing_identities(passed_required_rows, _market_identity),
                "expected_market": _normalize_identity(thresholds.expected_market)
                if thresholds.expected_market is not None
                else "",
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
    passed = _passed_required_rows(catalog, evidence)
    return {str(value) for value in passed["git_commit"].dropna() if str(value)}


def _passed_required_rows(catalog: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    required = set(evidence.loc[evidence["passed"].astype(bool), "required_run_type"].astype(str))
    if not required:
        return catalog.iloc[0:0].copy()
    work = catalog.copy()
    work["summary_status_bool"] = work["summary_status"].map(_to_optional_bool)
    return work.loc[work["run_type"].astype(str).isin(required) & (work["summary_status_bool"] == True)].copy()  # noqa: E712


def _identity_values(frame: pd.DataFrame, extractor: Any) -> set[str]:
    values: set[str] = set()
    for _, row in frame.iterrows():
        value = extractor(row)
        if value:
            values.add(value)
    return values


def _missing_identities(frame: pd.DataFrame, extractor: Any) -> int:
    if frame.empty:
        return 0
    return int(sum(1 for _, row in frame.iterrows() if not extractor(row)))


def _strategy_identity(row: pd.Series) -> str:
    return _normalize_strategy(_first_identity(row, ("strategy", "strategy_name", "strategy_id")))


def _market_identity(row: pd.Series) -> str:
    return _normalize_identity(_first_identity(row, ("market", "market_profile", "market_name", "market_id")))


def _first_identity(row: pd.Series, keys: tuple[str, ...]) -> str:
    for column in _summary_columns(keys):
        value = _row_text(row, column)
        if value:
            return value
    for scenario_column in (
        "summary_candidate_scenario_key",
        "summary_best_scenario_key",
        "summary_selected_scenario_key",
        "summary_scenario_key",
        "scenario_key",
    ):
        parsed = _parse_scenario_key(_row_text(row, scenario_column))
        for key in keys:
            if key in parsed:
                return parsed[key]
    for json_column in ("parameters_json", "inputs_json"):
        parsed_json = _parse_json(_row_text(row, json_column))
        value = _find_json_key(parsed_json, keys)
        if value:
            return value
    return ""


def _summary_columns(keys: tuple[str, ...]) -> tuple[str, ...]:
    columns: list[str] = []
    for key in keys:
        columns.append(f"summary_{key}")
        columns.append(f"summary_runtime_{key}")
        columns.append(f"summary_broker_runtime_{key}")
    if "market" in keys:
        columns.extend(["summary_market_key", "summary_market_profile_name"])
    return tuple(dict.fromkeys(columns))


def _parse_scenario_key(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in value.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        key = key.strip()
        item = item.strip()
        if key and item:
            parsed[key] = item
    return parsed


def _parse_json(value: str) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _find_json_key(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, (str, int, float)) and str(item).strip():
                return str(item)
        for item in value.values():
            found = _find_json_key(item, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_json_key(item, keys)
            if found:
                return found
    return ""


def _row_text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value)


def _normalize_strategy(value: str | None) -> str:
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


def _normalize_identity(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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
