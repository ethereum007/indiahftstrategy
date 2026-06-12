from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


SCORE_METRIC_COLUMNS = {
    "rank",
    "scenario_key",
    "sweeps_seen",
    "scenario_runs",
    "passed_runs",
    "pass_rate",
    "median_net_pnl",
    "mean_net_pnl",
    "min_net_pnl",
    "total_net_pnl",
    "median_robust_score",
    "min_robust_score",
    "worst_drawdown",
    "median_fills",
    "min_fills",
    "worst_regime_equity_change",
    "runs_with_losing_regimes",
    "selection_passed",
}


@dataclass(frozen=True)
class PromotionThresholds:
    min_pass_rate: float = 1.0
    min_sweeps: int = 1
    min_median_net_pnl: float = 0.0
    min_min_net_pnl: float | None = None
    max_worst_drawdown: float | None = None
    min_median_fills: float = 1.0
    max_runs_with_losing_regimes: int | None = None
    max_otr: float | None = None
    min_maker_share: float | None = None
    min_markout_mean: float | None = None


@dataclass(frozen=True)
class PromotionReport:
    candidate: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_promotion(
    scenario_scores: pd.DataFrame,
    scenario_runs: pd.DataFrame,
    *,
    thresholds: PromotionThresholds | None = None,
) -> PromotionReport:
    thresholds = thresholds or PromotionThresholds()
    _validate_thresholds(thresholds)
    scores = scenario_scores.copy()
    runs = scenario_runs.copy()
    _require(scores, ["scenario_key", "selection_passed"], "scenario_scores")
    _require(runs, ["run"], "scenario_runs")

    candidate = _select_candidate(scores)
    if candidate.empty:
        checks = pd.DataFrame([_check("selection_available", 0, ">=", 1, False, "no scenarios available")])
        summary = _summary(candidate, checks)
        return PromotionReport(candidate=candidate, checks=checks, summary=summary)

    row = candidate.iloc[0]
    candidate_runs = _candidate_runs(runs, row, _parameter_columns(scores))
    checks = _checks(row, candidate_runs, thresholds)
    summary = _summary(candidate, checks)
    return PromotionReport(candidate=candidate, checks=checks, summary=summary)


def write_promotion_report(
    selection_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: PromotionThresholds | None = None,
) -> PromotionReport:
    selection = Path(selection_path)
    scores_path = selection / "scenario_scores.csv"
    runs_path = selection / "scenario_runs.csv"
    if not scores_path.exists():
        raise FileNotFoundError(f"scenario_scores.csv not found: {scores_path}")
    if not runs_path.exists():
        raise FileNotFoundError(f"scenario_runs.csv not found: {runs_path}")

    thresholds = thresholds or PromotionThresholds()
    report = evaluate_promotion(
        pd.read_csv(scores_path),
        pd.read_csv(runs_path),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.candidate.to_csv(out / "promotion_candidate.csv", index=False)
    report.checks.to_csv(out / "promotion_checks.csv", index=False)
    report.summary.to_csv(out / "promotion_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_candidate_config(report, thresholds), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"selection": selection},
    )
    return PromotionReport(report.candidate, report.checks, report.summary, out)


def _select_candidate(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=scores.columns)
    work = scores.copy()
    work["selection_passed"] = work["selection_passed"].map(_to_bool)
    if "rank" in work.columns:
        work["_rank_sort"] = pd.to_numeric(work["rank"], errors="coerce").fillna(len(work) + 1)
    else:
        work["_rank_sort"] = np.arange(1, len(work) + 1)
    selectable = work.loc[work["selection_passed"]].sort_values("_rank_sort")
    chosen = selectable.head(1) if not selectable.empty else work.sort_values("_rank_sort").head(1)
    return chosen.drop(columns=["_rank_sort"]).reset_index(drop=True)


def _checks(row: pd.Series, candidate_runs: pd.DataFrame, thresholds: PromotionThresholds) -> pd.DataFrame:
    checks = [
        _check(
            "selection_passed",
            _to_bool(row.get("selection_passed", False)),
            "is",
            True,
            _to_bool(row.get("selection_passed", False)),
            "candidate was not marked selectable by compare-sweeps",
        ),
        _numeric_check(row, "pass_rate", ">=", thresholds.min_pass_rate),
        _numeric_check(row, "sweeps_seen", ">=", thresholds.min_sweeps),
        _numeric_check(row, "median_net_pnl", ">=", thresholds.min_median_net_pnl),
        _numeric_check(row, "median_fills", ">=", thresholds.min_median_fills),
    ]
    if thresholds.min_min_net_pnl is not None:
        checks.append(_numeric_check(row, "min_net_pnl", ">=", thresholds.min_min_net_pnl))
    if thresholds.max_worst_drawdown is not None:
        checks.append(_numeric_check(row, "worst_drawdown", "<=", thresholds.max_worst_drawdown))
    if thresholds.max_runs_with_losing_regimes is not None:
        checks.append(
            _numeric_check(row, "runs_with_losing_regimes", "<=", thresholds.max_runs_with_losing_regimes)
        )
    if thresholds.max_otr is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "order_to_trade_ratio",
                "max_order_to_trade_ratio",
                "<=",
                thresholds.max_otr,
                reducer="max",
            )
        )
    if thresholds.min_maker_share is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "maker_share",
                "min_maker_share",
                ">=",
                thresholds.min_maker_share,
                reducer="min",
            )
        )
    if thresholds.min_markout_mean is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "markout_mean",
                "min_markout_mean",
                ">=",
                thresholds.min_markout_mean,
                reducer="min",
            )
        )
    return pd.DataFrame(checks)


def _summary(candidate: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    key = "" if candidate.empty or "scenario_key" not in candidate.columns else str(candidate.iloc[0]["scenario_key"])
    recommendation = "paper_or_shadow_candidate" if ready else "keep_in_research"
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": key,
                "checks": int(len(checks)),
                "failed_checks": failed,
                "recommendation": recommendation,
            }
        ]
    )


def _candidate_config(report: PromotionReport, thresholds: PromotionThresholds) -> dict[str, Any]:
    if report.candidate.empty:
        return {
            "schema_version": 1,
            "ready": False,
            "scenario_key": "",
            "parameters": {},
            "metrics": {},
            "thresholds": asdict(thresholds),
            "recommendation": "keep_in_research",
        }
    row = report.candidate.iloc[0]
    parameters = {col: _jsonable(row[col]) for col in _parameter_columns(report.candidate)}
    metrics = {
        col: _jsonable(row[col])
        for col in report.candidate.columns
        if col not in parameters and col not in {"scenario_key"}
    }
    return {
        "schema_version": 1,
        "ready": report.ready,
        "scenario_key": str(row.get("scenario_key", "")),
        "parameters": parameters,
        "metrics": metrics,
        "thresholds": asdict(thresholds),
        "recommendation": str(report.summary.iloc[0]["recommendation"]),
    }


def _parameter_columns(frame: pd.DataFrame) -> list[str]:
    return [col for col in frame.columns if col not in SCORE_METRIC_COLUMNS]


def _candidate_runs(runs: pd.DataFrame, candidate: pd.Series, parameter_cols: list[str]) -> pd.DataFrame:
    if runs.empty:
        return runs.copy()
    mask = pd.Series(True, index=runs.index)
    for col in parameter_cols:
        if col not in runs.columns or col not in candidate:
            continue
        mask &= _same_value_series(runs[col], candidate[col])
    matched = runs.loc[mask].copy()
    if matched.empty and "scenario_key" in runs.columns and "scenario_key" in candidate:
        matched = runs.loc[runs["scenario_key"].astype(str) == str(candidate["scenario_key"])].copy()
    return matched


def _same_value_series(series: pd.Series, value: object) -> pd.Series:
    if pd.isna(value):
        return series.isna()
    numeric = pd.to_numeric(series, errors="coerce")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = np.nan
    if not np.isnan(numeric_value) and numeric.notna().any():
        return np.isclose(numeric, numeric_value, equal_nan=False)
    return series.astype(str) == str(value)


def _numeric_check(row: pd.Series, column: str, operator: str, threshold: float | int) -> dict[str, Any]:
    value = float(row[column]) if column in row and not pd.isna(row[column]) else np.nan
    return _threshold_check(column, value, operator, threshold)


def _run_metric_check(
    runs: pd.DataFrame,
    column: str,
    check_name: str,
    operator: str,
    threshold: float | int,
    *,
    reducer: str,
) -> dict[str, Any]:
    if runs.empty or column not in runs.columns:
        return _check(check_name, np.nan, operator, threshold, False, f"{column} is unavailable")
    values = pd.to_numeric(runs[column], errors="coerce")
    value = float(values.max(skipna=True)) if reducer == "max" else float(values.min(skipna=True))
    return _threshold_check(check_name, value, operator, threshold)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
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


def _validate_thresholds(thresholds: PromotionThresholds) -> None:
    if not 0 <= thresholds.min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if thresholds.min_sweeps <= 0:
        raise ValueError("min_sweeps must be positive")
    if thresholds.min_median_fills < 0:
        raise ValueError("min_median_fills must be non-negative")
    if thresholds.max_runs_with_losing_regimes is not None and thresholds.max_runs_with_losing_regimes < 0:
        raise ValueError("max_runs_with_losing_regimes must be non-negative")
    if thresholds.max_otr is not None and thresholds.max_otr <= 0:
        raise ValueError("max_otr must be positive")
    if thresholds.min_maker_share is not None and not 0 <= thresholds.min_maker_share <= 1:
        raise ValueError("min_maker_share must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if pd.isna(value):
        return None
    return value
