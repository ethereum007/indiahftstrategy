from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


PARAMETER_COLUMNS = ["entry_imbalance", "min_microprice_edge_ticks", "forward_horizon_ns"]


@dataclass(frozen=True)
class ImbalanceEdgeSelectionThresholds:
    min_sweeps: int = 1
    min_pass_rate: float = 1.0
    min_median_usable_signals: float = 1.0
    min_median_mean_forward_edge_ticks: float = 0.0
    min_min_win_rate: float = 0.0
    min_median_robust_score: float | None = None


@dataclass(frozen=True)
class ImbalanceEdgeSelectionReport:
    scenario_runs: pd.DataFrame
    scenario_scores: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def has_selection(self) -> bool:
        if self.summary.empty:
            return False
        return int(self.summary.iloc[0]["selectable_scenarios"]) > 0


def compare_imbalance_edge_sweeps(
    sweep_paths: list[str | Path],
    *,
    labels: list[str] | None = None,
    thresholds: ImbalanceEdgeSelectionThresholds | None = None,
) -> ImbalanceEdgeSelectionReport:
    thresholds = thresholds or ImbalanceEdgeSelectionThresholds()
    _validate_thresholds(thresholds)
    scenario_runs = _read_sweeps(sweep_paths, labels=labels)
    scenario_scores = _score_scenarios(scenario_runs, thresholds)
    checks = _checks(scenario_scores, thresholds)
    summary = _summary(scenario_scores, scenario_runs, checks)
    candidate_config = _candidate_config(scenario_scores, checks, summary.iloc[0], thresholds)
    return ImbalanceEdgeSelectionReport(
        scenario_runs=scenario_runs,
        scenario_scores=scenario_scores,
        checks=checks,
        summary=summary,
        candidate_config=candidate_config,
    )


def write_imbalance_edge_selection(
    sweep_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    thresholds: ImbalanceEdgeSelectionThresholds | None = None,
) -> ImbalanceEdgeSelectionReport:
    thresholds = thresholds or ImbalanceEdgeSelectionThresholds()
    report = compare_imbalance_edge_sweeps(sweep_paths, labels=labels, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.scenario_runs.to_csv(out / "imbalance_edge_scenario_runs.csv", index=False)
    report.scenario_scores.to_csv(out / "imbalance_edge_scenario_scores.csv", index=False)
    report.checks.to_csv(out / "imbalance_edge_selection_checks.csv", index=False)
    report.summary.to_csv(out / "imbalance_edge_selection_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(report.candidate_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="imbalance_edge_selection",
        parameters={"labels": labels, "thresholds": asdict(thresholds)},
        inputs={"sweeps": sweep_paths},
    )
    return ImbalanceEdgeSelectionReport(
        report.scenario_runs,
        report.scenario_scores,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


def _read_sweeps(sweep_paths: list[str | Path], *, labels: list[str] | None) -> pd.DataFrame:
    if not sweep_paths:
        raise ValueError("at least one imbalance edge sweep is required")
    if labels is not None and len(labels) != len(sweep_paths):
        raise ValueError("labels must match sweep_paths length")
    frames = []
    for idx, raw_path in enumerate(sweep_paths):
        path = Path(raw_path)
        csv_path = path / "imbalance_edge_sweep_runs.csv" if path.is_dir() else path
        if not csv_path.exists():
            raise FileNotFoundError(f"imbalance_edge_sweep_runs.csv not found for {path}")
        frame = pd.read_csv(csv_path)
        if frame.empty:
            raise ValueError(f"imbalance edge sweep run file is empty: {csv_path}")
        _require(frame, PARAMETER_COLUMNS + ["passed", "usable_signals", "mean_forward_edge_ticks", "win_rate"])
        label = labels[idx] if labels is not None else path.stem
        frame = frame.copy()
        frame["sweep"] = label
        frame["sweep_path"] = str(path)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def _score_scenarios(
    runs: pd.DataFrame,
    thresholds: ImbalanceEdgeSelectionThresholds,
) -> pd.DataFrame:
    rows = []
    grouped = runs.groupby(PARAMETER_COLUMNS, dropna=False, sort=True)
    for keys, group in grouped:
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        passed = group["passed"].map(_to_bool)
        usable = _numeric(group, "usable_signals")
        mean_edge = _numeric(group, "mean_forward_edge_ticks")
        median_edge = _numeric(group, "median_forward_edge_ticks")
        win_rate = _numeric(group, "win_rate")
        robust_score = _numeric(group, "robust_score")
        direction_count = _numeric(group, "direction_count")

        sweeps_seen = int(group["sweep"].nunique())
        scenario_runs = int(len(group))
        pass_rate = float(passed.mean()) if scenario_runs else 0.0
        median_usable = float(usable.median(skipna=True))
        median_mean_edge = float(mean_edge.median(skipna=True))
        min_mean_edge = float(mean_edge.min(skipna=True))
        median_win_rate = float(win_rate.median(skipna=True))
        min_win_rate = float(win_rate.min(skipna=True))
        median_robust_score = float(robust_score.median(skipna=True))
        selection_passed = (
            sweeps_seen >= thresholds.min_sweeps
            and pass_rate >= thresholds.min_pass_rate
            and median_usable >= thresholds.min_median_usable_signals
            and median_mean_edge >= thresholds.min_median_mean_forward_edge_ticks
            and min_win_rate >= thresholds.min_min_win_rate
            and (
                thresholds.min_median_robust_score is None
                or median_robust_score >= thresholds.min_median_robust_score
            )
        )

        row = {col: value for col, value in zip(PARAMETER_COLUMNS, key_tuple)}
        row.update(
            {
                "scenario_key": _scenario_key(key_tuple),
                "sweeps_seen": sweeps_seen,
                "scenario_runs": scenario_runs,
                "passed_runs": int(passed.sum()),
                "pass_rate": pass_rate,
                "median_usable_signals": median_usable,
                "min_usable_signals": float(usable.min(skipna=True)),
                "median_mean_forward_edge_ticks": median_mean_edge,
                "min_mean_forward_edge_ticks": min_mean_edge,
                "median_forward_edge_ticks": float(median_edge.median(skipna=True)),
                "median_win_rate": median_win_rate,
                "min_win_rate": min_win_rate,
                "median_robust_score": median_robust_score,
                "min_robust_score": float(robust_score.min(skipna=True)),
                "min_direction_count": float(direction_count.min(skipna=True)),
                "selection_passed": bool(selection_passed),
            }
        )
        rows.append(row)

    scores = pd.DataFrame(rows)
    if scores.empty:
        return scores
    scores = scores.sort_values(
        [
            "selection_passed",
            "pass_rate",
            "median_robust_score",
            "median_mean_forward_edge_ticks",
            "median_usable_signals",
            "min_win_rate",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    scores.insert(0, "rank", np.arange(1, len(scores) + 1))
    return scores


def _checks(scores: pd.DataFrame, thresholds: ImbalanceEdgeSelectionThresholds) -> pd.DataFrame:
    best = scores.iloc[0] if not scores.empty else pd.Series(dtype=object)
    selectable = int(scores["selection_passed"].map(_to_bool).sum()) if not scores.empty else 0
    rows = [
        _check(
            "selection_available",
            selectable,
            ">=",
            1,
            selectable >= 1,
            "no imbalance edge scenario passed selection thresholds",
        ),
        _threshold_check(best, "sweeps_seen", ">=", thresholds.min_sweeps),
        _threshold_check(best, "pass_rate", ">=", thresholds.min_pass_rate),
        _threshold_check(best, "median_usable_signals", ">=", thresholds.min_median_usable_signals),
        _threshold_check(
            best,
            "median_mean_forward_edge_ticks",
            ">=",
            thresholds.min_median_mean_forward_edge_ticks,
        ),
        _threshold_check(best, "min_win_rate", ">=", thresholds.min_min_win_rate),
    ]
    if thresholds.min_median_robust_score is not None:
        rows.append(_threshold_check(best, "median_robust_score", ">=", thresholds.min_median_robust_score))
    return pd.DataFrame(rows)


def _summary(scenario_scores: pd.DataFrame, scenario_runs: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    selectable = scenario_scores.loc[scenario_scores["selection_passed"].map(_to_bool)] if not scenario_scores.empty else scenario_scores
    best = selectable.iloc[0] if not selectable.empty else (scenario_scores.iloc[0] if not scenario_scores.empty else pd.Series(dtype=object))
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "run_imbalance_replay_sweep" if passed else "keep_researching",
                "sweep_count": int(scenario_runs["sweep"].nunique()) if not scenario_runs.empty else 0,
                "scenario_count": int(len(scenario_scores)),
                "selectable_scenarios": int(len(selectable)) if not scenario_scores.empty else 0,
                "best_scenario_key": str(best.get("scenario_key", "")),
                "best_entry_imbalance": _float(best, "entry_imbalance"),
                "best_min_microprice_edge_ticks": _float(best, "min_microprice_edge_ticks"),
                "best_forward_horizon_ns": _int_or_nan(best, "forward_horizon_ns"),
                "best_pass_rate": _float(best, "pass_rate"),
                "best_median_usable_signals": _float(best, "median_usable_signals"),
                "best_median_mean_forward_edge_ticks": _float(best, "median_mean_forward_edge_ticks"),
                "best_min_win_rate": _float(best, "min_win_rate"),
                "best_median_robust_score": _float(best, "median_robust_score"),
            }
        ]
    )


def _candidate_config(
    scores: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.Series,
    thresholds: ImbalanceEdgeSelectionThresholds,
) -> dict[str, Any]:
    selectable = scores.loc[scores["selection_passed"].map(_to_bool)] if not scores.empty else scores
    best = selectable.iloc[0] if not selectable.empty else (scores.iloc[0] if not scores.empty else pd.Series(dtype=object))
    horizon = _int_or_none(best, "forward_horizon_ns")
    return {
        "schema_version": 1,
        "ready": bool(summary.get("passed", False)),
        "strategy": "imbalance",
        "source_run": str(best.get("scenario_key", "")),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
        "edge_selection_thresholds": asdict(thresholds),
        "replay_defaults": {
            "entry_imbalance": _jsonable(_float(best, "entry_imbalance")),
            "min_microprice_edge_ticks": _jsonable(_float(best, "min_microprice_edge_ticks")),
            "hold_ns": horizon,
            "markout_horizons_ns": [horizon] if horizon is not None else [],
        },
        "evidence": {
            "sweeps_seen": _jsonable(_float(best, "sweeps_seen")),
            "pass_rate": _jsonable(_float(best, "pass_rate")),
            "median_usable_signals": _jsonable(_float(best, "median_usable_signals")),
            "median_mean_forward_edge_ticks": _jsonable(_float(best, "median_mean_forward_edge_ticks")),
            "min_win_rate": _jsonable(_float(best, "min_win_rate")),
            "median_robust_score": _jsonable(_float(best, "median_robust_score")),
        },
    }


def _threshold_check(row: pd.Series, name: str, operator: str, threshold: float | int) -> dict[str, Any]:
    value = _float(row, name)
    threshold_float = float(threshold)
    missing = np.isnan(value)
    if operator == ">=":
        passed = (not missing) and value >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value, operator, threshold_float, passed, reason)


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


def _validate_thresholds(thresholds: ImbalanceEdgeSelectionThresholds) -> None:
    if thresholds.min_sweeps <= 0:
        raise ValueError("min_sweeps must be positive")
    if not 0 <= thresholds.min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if thresholds.min_median_usable_signals < 0:
        raise ValueError("min_median_usable_signals must be non-negative")
    if not 0 <= thresholds.min_min_win_rate <= 1:
        raise ValueError("min_min_win_rate must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"imbalance edge sweep runs missing columns: {missing}")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _scenario_key(key_tuple: tuple[object, ...]) -> str:
    return "|".join(f"{column}={_format_value(value)}" for column, value in zip(PARAMETER_COLUMNS, key_tuple))


def _format_value(value: object) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _int_or_nan(row: pd.Series, column: str) -> int | float:
    value = _float(row, column)
    return int(value) if not pd.isna(value) else np.nan


def _int_or_none(row: pd.Series, column: str) -> int | None:
    value = _float(row, column)
    return int(value) if not pd.isna(value) else None


def _jsonable(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
