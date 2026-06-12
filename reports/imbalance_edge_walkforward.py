from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.imbalance_edge_selection import (
    ImbalanceEdgeSelectionReport,
    ImbalanceEdgeSelectionThresholds,
    write_imbalance_edge_selection,
)
from reports.imbalance_edge_sweep import (
    ImbalanceEdgeSweepReport,
    ImbalanceEdgeSweepThresholds,
    write_imbalance_edge_sweep,
)
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ImbalanceEdgeWalkForwardThresholds:
    min_folds: int = 1
    min_passed_sweeps: int = 1
    require_selection: bool = True


@dataclass(frozen=True)
class ImbalanceEdgeWalkForwardReport:
    folds: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    selection: ImbalanceEdgeSelectionReport
    sweeps: list[ImbalanceEdgeSweepReport]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def write_imbalance_edge_walkforward(
    tick_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
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
    sweep_thresholds: ImbalanceEdgeSweepThresholds | None = None,
    selection_thresholds: ImbalanceEdgeSelectionThresholds | None = None,
    walkforward_thresholds: ImbalanceEdgeWalkForwardThresholds | None = None,
) -> ImbalanceEdgeWalkForwardReport:
    paths = [Path(path) for path in tick_paths]
    fold_labels = _fold_labels(paths, labels)
    sweep_thresholds = sweep_thresholds or ImbalanceEdgeSweepThresholds()
    selection_thresholds = selection_thresholds or ImbalanceEdgeSelectionThresholds(min_sweeps=len(paths))
    walkforward_thresholds = walkforward_thresholds or ImbalanceEdgeWalkForwardThresholds(
        min_folds=len(paths),
        min_passed_sweeps=len(paths),
    )
    _validate_thresholds(walkforward_thresholds)

    out = Path(output_dir)
    sweep_root = out / "sweeps"
    selection_dir = out / "selection"
    out.mkdir(parents=True, exist_ok=True)

    sweep_dirs: list[Path] = []
    sweeps: list[ImbalanceEdgeSweepReport] = []
    fold_rows: list[dict[str, Any]] = []
    for idx, (ticks_path, label) in enumerate(zip(paths, fold_labels), start=1):
        sweep_dir = sweep_root / f"{idx:02d}_{_safe_label(label)}"
        sweep = write_imbalance_edge_sweep(
            ticks_path,
            output_dir=sweep_dir,
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
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            thresholds=sweep_thresholds,
        )
        sweep_dirs.append(sweep_dir)
        sweeps.append(sweep)
        fold_rows.append(_fold_row(idx, label, ticks_path, sweep_dir, sweep))

    folds = pd.DataFrame(fold_rows)
    selection = write_imbalance_edge_selection(
        sweep_dirs,
        output_dir=selection_dir,
        labels=fold_labels,
        thresholds=selection_thresholds,
    )
    checks = _checks(folds, selection, walkforward_thresholds)
    summary = _summary(folds, selection, checks)
    candidate_config = _candidate_config(selection, checks, summary.iloc[0], tick_size=tick_size)

    folds.to_csv(out / "imbalance_edge_walkforward_folds.csv", index=False)
    checks.to_csv(out / "imbalance_edge_walkforward_checks.csv", index=False)
    summary.to_csv(out / "imbalance_edge_walkforward_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(candidate_config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="imbalance_edge_walkforward",
        parameters={
            "labels": fold_labels,
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
            "sweep_thresholds": asdict(sweep_thresholds),
            "selection_thresholds": asdict(selection_thresholds),
            "walkforward_thresholds": asdict(walkforward_thresholds),
        },
        inputs={"ticks": paths, "sweeps": sweep_dirs, "selection": selection_dir},
    )
    return ImbalanceEdgeWalkForwardReport(
        folds=folds,
        checks=checks,
        summary=summary,
        candidate_config=candidate_config,
        selection=selection,
        sweeps=sweeps,
        output_dir=out,
    )


def _fold_labels(paths: list[Path], labels: list[str] | None) -> list[str]:
    if not paths:
        raise ValueError("at least one tick file is required")
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match tick_paths length")
    return [str(label) for label in labels] if labels is not None else [path.stem for path in paths]


def _fold_row(
    index: int,
    label: str,
    ticks_path: Path,
    sweep_dir: Path,
    sweep: ImbalanceEdgeSweepReport,
) -> dict[str, Any]:
    row = sweep.summary.iloc[0] if not sweep.summary.empty else pd.Series(dtype=object)
    return {
        "fold_index": int(index),
        "fold": label,
        "ticks_path": str(ticks_path),
        "sweep_dir": str(sweep_dir),
        "passed": bool(row.get("passed", False)),
        "failed_checks": _int(row, "failed_checks"),
        "scenario_count": _int(row, "scenario_count"),
        "passed_configs": _int(row, "passed_configs"),
        "best_run": str(row.get("best_run", "")),
        "best_entry_imbalance": _float(row, "best_entry_imbalance"),
        "best_min_microprice_edge_ticks": _float(row, "best_min_microprice_edge_ticks"),
        "best_forward_horizon_ns": _int(row, "best_forward_horizon_ns"),
        "best_usable_signals": _int(row, "best_usable_signals"),
        "best_mean_forward_edge_ticks": _float(row, "best_mean_forward_edge_ticks"),
        "best_win_rate": _float(row, "best_win_rate"),
        "best_robust_score": _float(row, "best_robust_score"),
    }


def _checks(
    folds: pd.DataFrame,
    selection: ImbalanceEdgeSelectionReport,
    thresholds: ImbalanceEdgeWalkForwardThresholds,
) -> pd.DataFrame:
    passed_sweeps = int(folds["passed"].map(_to_bool).sum()) if not folds.empty else 0
    selection_row = selection.summary.iloc[0] if not selection.summary.empty else pd.Series(dtype=object)
    selection_passed = _to_bool(selection_row.get("passed", False))
    selectable = int(selection_row.get("selectable_scenarios", 0) or 0)
    rows = [
        _check(
            "fold_count",
            len(folds),
            ">=",
            thresholds.min_folds,
            len(folds) >= thresholds.min_folds,
            "not enough tick folds were evaluated",
        ),
        _check(
            "passed_sweeps",
            passed_sweeps,
            ">=",
            thresholds.min_passed_sweeps,
            passed_sweeps >= thresholds.min_passed_sweeps,
            "not enough per-fold imbalance edge sweeps passed",
        ),
    ]
    if thresholds.require_selection:
        rows.extend(
            [
                _check(
                    "selection_passed",
                    int(selection_passed),
                    ">=",
                    1,
                    selection_passed,
                    "cross-fold imbalance edge selection did not pass",
                ),
                _check(
                    "selectable_scenarios",
                    selectable,
                    ">=",
                    1,
                    selectable >= 1,
                    "no stable imbalance edge scenario was selected",
                ),
            ]
        )
    return pd.DataFrame(rows)


def _summary(
    folds: pd.DataFrame,
    selection: ImbalanceEdgeSelectionReport,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    selection_row = selection.summary.iloc[0] if not selection.summary.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "run_imbalance_replay_sweep" if passed else "keep_researching",
                "fold_count": int(len(folds)),
                "passed_sweeps": int(folds["passed"].map(_to_bool).sum()) if not folds.empty else 0,
                "selection_passed": _to_bool(selection_row.get("passed", False)),
                "selectable_scenarios": int(selection_row.get("selectable_scenarios", 0) or 0),
                "best_scenario_key": str(selection_row.get("best_scenario_key", "")),
                "best_entry_imbalance": _float(selection_row, "best_entry_imbalance"),
                "best_min_microprice_edge_ticks": _float(selection_row, "best_min_microprice_edge_ticks"),
                "best_forward_horizon_ns": _int(selection_row, "best_forward_horizon_ns"),
                "best_pass_rate": _float(selection_row, "best_pass_rate"),
                "best_median_usable_signals": _float(selection_row, "best_median_usable_signals"),
                "best_median_mean_forward_edge_ticks": _float(
                    selection_row,
                    "best_median_mean_forward_edge_ticks",
                ),
                "best_min_win_rate": _float(selection_row, "best_min_win_rate"),
                "best_median_robust_score": _float(selection_row, "best_median_robust_score"),
            }
        ]
    )


def _candidate_config(
    selection: ImbalanceEdgeSelectionReport,
    checks: pd.DataFrame,
    summary: pd.Series,
    *,
    tick_size: float,
) -> dict[str, Any]:
    config = copy.deepcopy(selection.candidate_config)
    config["ready"] = bool(summary.get("passed", False))
    config["source_run_type"] = "imbalance_edge_walkforward"
    failed_checks = list(config.get("failed_checks", []) or [])
    failed_checks.extend(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist())
    config["failed_checks"] = list(dict.fromkeys(failed_checks))
    replay_defaults = config.setdefault("replay_defaults", {})
    if isinstance(replay_defaults, dict):
        replay_defaults.setdefault("tick_size", float(tick_size))
    config["walkforward"] = {
        "fold_count": _jsonable(summary.get("fold_count")),
        "passed_sweeps": _jsonable(summary.get("passed_sweeps")),
        "selection_passed": _jsonable(summary.get("selection_passed")),
        "selectable_scenarios": _jsonable(summary.get("selectable_scenarios")),
        "best_scenario_key": _jsonable(summary.get("best_scenario_key")),
    }
    return config


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


def _validate_thresholds(thresholds: ImbalanceEdgeWalkForwardThresholds) -> None:
    if thresholds.min_folds <= 0:
        raise ValueError("min_folds must be positive")
    if thresholds.min_passed_sweeps < 0:
        raise ValueError("min_passed_sweeps must be non-negative")


def _safe_label(label: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip())
    return text.strip("._-") or "fold"


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _int(row: pd.Series, column: str) -> int:
    value = _float(row, column)
    return int(value) if not pd.isna(value) else 0


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
