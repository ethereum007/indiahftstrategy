from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.loaders import load_tick_csv
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.imbalance_edge import ImbalanceEdgeThresholds, evaluate_imbalance_edge
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ImbalanceEdgeSweepThresholds:
    min_passed_configs: int = 1
    min_best_usable_signals: int = 1
    min_best_mean_forward_edge_ticks: float = 0.0
    min_best_win_rate: float = 0.0


@dataclass(frozen=True)
class ImbalanceEdgeSweepReport:
    runs: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def evaluate_imbalance_edge_sweep(
    ticks: pd.DataFrame,
    *,
    entry_imbalance_values: list[float],
    min_microprice_edge_ticks_values: list[float],
    forward_horizon_ns_values: list[int],
    tick_size: float = 0.05,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    min_signals: int = 1,
    min_direction_count: int = 1,
    min_mean_forward_edge_ticks: float = 0.0,
    min_win_rate: float = 0.0,
    min_median_forward_edge_ticks: float | None = None,
    thresholds: ImbalanceEdgeSweepThresholds | None = None,
) -> ImbalanceEdgeSweepReport:
    thresholds = thresholds or ImbalanceEdgeSweepThresholds()
    _validate_grid(
        entry_imbalance_values=entry_imbalance_values,
        min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
        forward_horizon_ns_values=forward_horizon_ns_values,
        thresholds=thresholds,
    )
    rows = []
    for entry_imbalance, min_edge, horizon_ns in product(
        entry_imbalance_values,
        min_microprice_edge_ticks_values,
        forward_horizon_ns_values,
    ):
        audit_thresholds = ImbalanceEdgeThresholds(
            entry_imbalance=entry_imbalance,
            min_microprice_edge_ticks=min_edge,
            max_spread_ticks=max_spread_ticks,
            min_depth=min_depth,
            forward_horizon_ns=horizon_ns,
            min_signals=min_signals,
            min_direction_count=min_direction_count,
            min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
            min_win_rate=min_win_rate,
            min_median_forward_edge_ticks=min_median_forward_edge_ticks,
        )
        audit = evaluate_imbalance_edge(ticks, thresholds=audit_thresholds, tick_size=tick_size)
        metrics = audit.metrics.iloc[0].to_dict()
        summary = audit.summary.iloc[0].to_dict()
        rows.append(
            {
                "run": _run_name(entry_imbalance, min_edge, horizon_ns),
                "entry_imbalance": float(entry_imbalance),
                "min_microprice_edge_ticks": float(min_edge),
                "forward_horizon_ns": int(horizon_ns),
                "passed": bool(audit.passed),
                "failed_checks": int(summary["failed_checks"]),
                "recommendation": str(summary["recommendation"]),
                **metrics,
            }
        )

    runs = pd.DataFrame(rows)
    runs = _score_runs(runs)
    checks = _checks(runs, thresholds)
    summary = _summary(runs, checks)
    candidate_config = _candidate_config(runs, checks, summary.iloc[0], thresholds, tick_size=tick_size)
    return ImbalanceEdgeSweepReport(runs=runs, checks=checks, summary=summary, candidate_config=candidate_config)


def write_imbalance_edge_sweep(
    ticks_path: str | Path,
    *,
    output_dir: str | Path,
    entry_imbalance_values: list[float],
    min_microprice_edge_ticks_values: list[float],
    forward_horizon_ns_values: list[int],
    tick_size: float = 0.05,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    min_signals: int = 1,
    min_direction_count: int = 1,
    min_mean_forward_edge_ticks: float = 0.0,
    min_win_rate: float = 0.0,
    min_median_forward_edge_ticks: float | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    thresholds: ImbalanceEdgeSweepThresholds | None = None,
) -> ImbalanceEdgeSweepReport:
    thresholds = thresholds or ImbalanceEdgeSweepThresholds()
    ticks_file = Path(ticks_path)
    ticks = load_tick_csv(
        ticks_file,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    ).data
    report = evaluate_imbalance_edge_sweep(
        ticks,
        entry_imbalance_values=entry_imbalance_values,
        min_microprice_edge_ticks_values=min_microprice_edge_ticks_values,
        forward_horizon_ns_values=forward_horizon_ns_values,
        tick_size=tick_size,
        max_spread_ticks=max_spread_ticks,
        min_depth=min_depth,
        min_signals=min_signals,
        min_direction_count=min_direction_count,
        min_mean_forward_edge_ticks=min_mean_forward_edge_ticks,
        min_win_rate=min_win_rate,
        min_median_forward_edge_ticks=min_median_forward_edge_ticks,
        thresholds=thresholds,
    )
    report.candidate_config.setdefault("replay_defaults", {})["market"] = market
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.runs.to_csv(out / "imbalance_edge_sweep_runs.csv", index=False)
    report.checks.to_csv(out / "imbalance_edge_sweep_checks.csv", index=False)
    report.summary.to_csv(out / "imbalance_edge_sweep_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(report.candidate_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="imbalance_edge_sweep",
        parameters={
            "entry_imbalance_values": entry_imbalance_values,
            "min_microprice_edge_ticks_values": min_microprice_edge_ticks_values,
            "forward_horizon_ns_values": forward_horizon_ns_values,
            "tick_size": tick_size,
            "max_spread_ticks": max_spread_ticks,
            "min_depth": min_depth,
            "min_signals": min_signals,
            "min_direction_count": min_direction_count,
            "min_mean_forward_edge_ticks": min_mean_forward_edge_ticks,
            "min_win_rate": min_win_rate,
            "min_median_forward_edge_ticks": min_median_forward_edge_ticks,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "market": market,
            "thresholds": asdict(thresholds),
        },
        inputs={"ticks": ticks_file},
    )
    return ImbalanceEdgeSweepReport(report.runs, report.checks, report.summary, report.candidate_config, out)


def _score_runs(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return runs
    out = runs.copy()
    usable = pd.to_numeric(out["usable_signals"], errors="coerce").fillna(0.0).clip(lower=0.0)
    mean_edge = pd.to_numeric(out["mean_forward_edge_ticks"], errors="coerce").fillna(0.0)
    median_edge = pd.to_numeric(out["median_forward_edge_ticks"], errors="coerce").fillna(0.0)
    win_rate = pd.to_numeric(out["win_rate"], errors="coerce").fillna(0.0)
    direction_bonus = pd.to_numeric(out["direction_count"], errors="coerce").fillna(0.0).clip(upper=2.0) / 2.0
    out["robust_score"] = mean_edge * np.sqrt(usable) + 0.25 * median_edge + win_rate + 0.25 * direction_bonus
    return out.sort_values(
        ["passed", "robust_score", "usable_signals", "mean_forward_edge_ticks"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def _checks(runs: pd.DataFrame, thresholds: ImbalanceEdgeSweepThresholds) -> pd.DataFrame:
    best = runs.iloc[0] if not runs.empty else pd.Series(dtype=object)
    passed_configs = int(runs["passed"].astype(bool).sum()) if not runs.empty else 0
    return pd.DataFrame(
        [
            _check(
                "passed_configs",
                passed_configs,
                ">=",
                thresholds.min_passed_configs,
                passed_configs >= thresholds.min_passed_configs,
                "not enough imbalance edge configurations passed",
            ),
            _threshold_check(best, "usable_signals", ">=", thresholds.min_best_usable_signals),
            _threshold_check(best, "mean_forward_edge_ticks", ">=", thresholds.min_best_mean_forward_edge_ticks),
            _threshold_check(best, "win_rate", ">=", thresholds.min_best_win_rate),
        ]
    )


def _summary(runs: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    best = runs.iloc[0] if not runs.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "run_imbalance_replay_sweep" if passed else "keep_researching",
                "scenario_count": int(len(runs)),
                "passed_configs": int(runs["passed"].astype(bool).sum()) if not runs.empty else 0,
                "best_run": str(best.get("run", "")),
                "best_entry_imbalance": _float(best, "entry_imbalance"),
                "best_min_microprice_edge_ticks": _float(best, "min_microprice_edge_ticks"),
                "best_forward_horizon_ns": int(_float(best, "forward_horizon_ns")) if not pd.isna(_float(best, "forward_horizon_ns")) else np.nan,
                "best_usable_signals": int(_float(best, "usable_signals")) if not pd.isna(_float(best, "usable_signals")) else 0,
                "best_mean_forward_edge_ticks": _float(best, "mean_forward_edge_ticks"),
                "best_win_rate": _float(best, "win_rate"),
                "best_robust_score": _float(best, "robust_score"),
            }
        ]
    )


def _candidate_config(
    runs: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.Series,
    thresholds: ImbalanceEdgeSweepThresholds,
    *,
    tick_size: float,
) -> dict[str, Any]:
    ready = bool(summary.get("passed", False))
    best = runs.iloc[0] if not runs.empty else pd.Series(dtype=object)
    horizon = int(_float(best, "forward_horizon_ns")) if not pd.isna(_float(best, "forward_horizon_ns")) else None
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": "imbalance",
        "source_run": str(best.get("run", "")),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
        "edge_sweep_thresholds": asdict(thresholds),
        "replay_defaults": {
            "tick_size": float(tick_size),
            "entry_imbalance": _jsonable(_float(best, "entry_imbalance")),
            "min_microprice_edge_ticks": _jsonable(_float(best, "min_microprice_edge_ticks")),
            "hold_ns": horizon,
            "markout_horizons_ns": [horizon] if horizon is not None else [],
        },
        "evidence": {
            "usable_signals": _jsonable(_float(best, "usable_signals")),
            "mean_forward_edge_ticks": _jsonable(_float(best, "mean_forward_edge_ticks")),
            "median_forward_edge_ticks": _jsonable(_float(best, "median_forward_edge_ticks")),
            "win_rate": _jsonable(_float(best, "win_rate")),
            "robust_score": _jsonable(_float(best, "robust_score")),
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


def _validate_grid(
    *,
    entry_imbalance_values: list[float],
    min_microprice_edge_ticks_values: list[float],
    forward_horizon_ns_values: list[int],
    thresholds: ImbalanceEdgeSweepThresholds,
) -> None:
    if not entry_imbalance_values:
        raise ValueError("entry_imbalance_values must not be empty")
    if not min_microprice_edge_ticks_values:
        raise ValueError("min_microprice_edge_ticks_values must not be empty")
    if not forward_horizon_ns_values:
        raise ValueError("forward_horizon_ns_values must not be empty")
    if thresholds.min_passed_configs <= 0:
        raise ValueError("min_passed_configs must be positive")
    if thresholds.min_best_usable_signals < 0:
        raise ValueError("min_best_usable_signals must be non-negative")
    if not 0 <= thresholds.min_best_win_rate <= 1:
        raise ValueError("min_best_win_rate must be between 0 and 1")


def _run_name(entry_imbalance: float, min_edge: float, horizon_ns: int) -> str:
    return (
        f"imb_{_label_number(entry_imbalance)}"
        f"__edge_{_label_number(min_edge)}"
        f"__horizon_{int(horizon_ns)}ns"
    )


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _jsonable(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
