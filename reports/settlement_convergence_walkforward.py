from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.settlement_convergence import (
    SettlementConvergenceReport,
    SettlementConvergenceThresholds,
    write_settlement_convergence_audit,
)


@dataclass(frozen=True)
class SettlementConvergenceWalkForwardThresholds:
    min_folds: int = 1
    min_pass_rate: float = 1.0
    min_total_opportunities: int = 1
    min_total_net_edge: float = 0.0
    min_median_best_net_edge: float = 0.0
    min_median_known_fraction: float = 0.0


@dataclass(frozen=True)
class SettlementConvergenceWalkForwardReport:
    folds: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    audits: list[SettlementConvergenceReport]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def write_settlement_convergence_walkforward(
    index_tick_paths: list[str | Path],
    option_chain_paths: list[str | Path],
    *,
    output_dir: str | Path,
    data_readiness_comparison_dir: str | Path | None = None,
    require_data_readiness_comparison: bool = False,
    window_start_ns: int | list[int],
    window_end_ns: int | list[int],
    labels: list[str] | None = None,
    index_price_col: str | None = None,
    lot_size: int = 75,
    tick_size: float = 0.05,
    qty: int = 75,
    depth_fraction: float = 1.0,
    min_known_fraction: float = 0.0,
    min_gross_edge_ticks: float = 0.0,
    min_net_edge: float = 0.0,
    audit_thresholds: SettlementConvergenceThresholds | None = None,
    thresholds: SettlementConvergenceWalkForwardThresholds | None = None,
) -> SettlementConvergenceWalkForwardReport:
    index_paths = [Path(path) for path in index_tick_paths]
    chain_paths = [Path(path) for path in option_chain_paths]
    if not index_paths:
        raise ValueError("at least one index tick file is required")
    if len(index_paths) != len(chain_paths):
        raise ValueError("index_tick_paths and option_chain_paths must have the same length")
    fold_labels = _fold_labels(index_paths, labels)
    starts = _expand_windows(window_start_ns, len(index_paths), "window_start_ns")
    ends = _expand_windows(window_end_ns, len(index_paths), "window_end_ns")
    audit_thresholds = audit_thresholds or SettlementConvergenceThresholds()
    thresholds = thresholds or SettlementConvergenceWalkForwardThresholds(min_folds=len(index_paths))
    _validate_thresholds(thresholds)
    comparison_summary = _read_data_readiness_comparison_summary(data_readiness_comparison_dir)
    comparison_check = _data_readiness_comparison_check(
        comparison_summary,
        required=require_data_readiness_comparison,
        input_dir=data_readiness_comparison_dir,
    )

    out = Path(output_dir)
    runs_root = out / "runs"
    out.mkdir(parents=True, exist_ok=True)
    parameters = {
        "strategy": "settlement_convergence",
        "market": INDIA_NSE_INDEX_DERIVATIVES.name,
        "window_start_ns": starts,
        "window_end_ns": ends,
        "index_price_col": index_price_col,
        "lot_size": int(lot_size),
        "tick_size": float(tick_size),
        "qty": int(qty),
        "depth_fraction": float(depth_fraction),
        "min_known_fraction": float(min_known_fraction),
        "min_gross_edge_ticks": float(min_gross_edge_ticks),
        "min_net_edge": float(min_net_edge),
        "require_data_readiness_comparison": bool(require_data_readiness_comparison),
        "data_readiness_comparison": _comparison_parameters(comparison_summary, data_readiness_comparison_dir),
        "audit_thresholds": asdict(audit_thresholds),
        "thresholds": asdict(thresholds),
    }

    if comparison_check is not None and not bool(comparison_check["passed"]):
        folds = _empty_folds()
        checks = pd.DataFrame([comparison_check])
        summary = _summary(folds, checks, market=INDIA_NSE_INDEX_DERIVATIVES.name)
        config = _candidate_config(checks, summary.iloc[0], parameters=parameters, folds=folds)
        _write_outputs(
            out,
            folds=folds,
            checks=checks,
            summary=summary,
            config=config,
            labels=fold_labels,
            parameters=parameters,
            index_paths=index_paths,
            chain_paths=chain_paths,
            run_dirs=[],
            data_readiness_comparison_dir=data_readiness_comparison_dir,
        )
        return SettlementConvergenceWalkForwardReport(folds, checks, summary, config, [], out)

    audits: list[SettlementConvergenceReport] = []
    run_dirs: list[Path] = []
    fold_rows: list[dict[str, Any]] = []
    for idx, (index_path, chain_path, label, start, end) in enumerate(
        zip(index_paths, chain_paths, fold_labels, starts, ends),
        start=1,
    ):
        run_dir = runs_root / f"{idx:02d}_{_safe_label(label)}"
        audit = write_settlement_convergence_audit(
            index_path,
            chain_path,
            output_dir=run_dir,
            window_start_ns=start,
            window_end_ns=end,
            index_price_col=index_price_col,
            lot_size=lot_size,
            tick_size=tick_size,
            qty=qty,
            depth_fraction=depth_fraction,
            min_known_fraction=min_known_fraction,
            min_gross_edge_ticks=min_gross_edge_ticks,
            min_net_edge=min_net_edge,
            thresholds=audit_thresholds,
        )
        audits.append(audit)
        run_dirs.append(run_dir)
        fold_rows.append(_fold_row(idx, label, index_path, chain_path, run_dir, start, end, audit))

    folds = pd.DataFrame(fold_rows)
    checks = _checks(folds, thresholds)
    if comparison_check is not None:
        checks = pd.concat([pd.DataFrame([comparison_check]), checks], ignore_index=True)
    summary = _summary(folds, checks, market=INDIA_NSE_INDEX_DERIVATIVES.name)
    config = _candidate_config(
        checks,
        summary.iloc[0],
        parameters=parameters,
        folds=folds,
    )

    _write_outputs(
        out,
        folds=folds,
        checks=checks,
        summary=summary,
        config=config,
        labels=fold_labels,
        parameters=parameters,
        index_paths=index_paths,
        chain_paths=chain_paths,
        run_dirs=run_dirs,
        data_readiness_comparison_dir=data_readiness_comparison_dir,
    )
    return SettlementConvergenceWalkForwardReport(folds, checks, summary, config, audits, out)


def _write_outputs(
    out: Path,
    *,
    folds: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    config: dict[str, Any],
    labels: list[str],
    parameters: dict[str, Any],
    index_paths: list[Path],
    chain_paths: list[Path],
    run_dirs: list[Path],
    data_readiness_comparison_dir: str | Path | None,
) -> None:
    folds.to_csv(out / "settlement_convergence_walkforward_folds.csv", index=False)
    checks.to_csv(out / "settlement_convergence_walkforward_checks.csv", index=False)
    summary.to_csv(out / "settlement_convergence_walkforward_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"index_ticks": index_paths, "option_chains": chain_paths, "run_dirs": run_dirs}
    if data_readiness_comparison_dir is not None:
        inputs["data_readiness_comparison"] = Path(data_readiness_comparison_dir)
    write_experiment_manifest(
        out,
        run_type="settlement_convergence_walkforward",
        parameters={"labels": labels, **parameters},
        inputs=inputs,
    )


def _empty_folds() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "fold_index",
            "fold",
            "index_ticks_path",
            "option_chain_path",
            "run_dir",
            "window_start_ns",
            "window_end_ns",
            "passed",
            "failed_checks",
            "opportunities",
            "buy_opportunities",
            "sell_opportunities",
            "total_net_edge",
            "median_net_edge",
            "best_net_edge",
            "median_known_fraction",
            "best_ts",
            "best_expiry",
            "best_strike",
            "best_option_type",
            "best_direction",
            "best_side",
            "best_touch_price",
            "best_trade_qty",
            "best_projected_settlement",
            "best_projected_intrinsic",
            "best_gross_edge",
            "best_gross_edge_ticks",
            "best_cost",
        ]
    )


def _read_data_readiness_comparison_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "data_readiness_comparison_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"data readiness comparison summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"data readiness comparison summary is empty: {candidate}")
    return frame


def _data_readiness_comparison_check(
    summary: pd.DataFrame,
    *,
    required: bool,
    input_dir: str | Path | None,
) -> dict[str, Any] | None:
    if summary.empty and not required:
        return None
    provided = not summary.empty
    row = summary.iloc[0] if provided else pd.Series(dtype=object)
    accepted = _to_bool(row.get("accepted", False)) if provided else False
    passed = provided and accepted
    reason = "accepted" if passed else "data_readiness_comparison_missing"
    if provided and not accepted:
        reason = "data_readiness_comparison_not_accepted"
    return {
        "check": "data_readiness_comparison",
        "value": bool(accepted),
        "operator": "accepted",
        "threshold": True,
        "passed": bool(passed),
        "reason": reason,
        "input_dir": str(input_dir or ""),
        "failed_checks": _int(row, "total_failed_checks") if provided else 1,
        "recommendation": str(row.get("recommendation", reason)) if provided else reason,
    }


def _comparison_parameters(summary: pd.DataFrame, input_dir: str | Path | None) -> dict[str, Any]:
    if summary.empty:
        return {
            "provided": False,
            "input_dir": str(input_dir or ""),
            "accepted": False,
            "dataset_count": 0,
            "ready_rate": 0.0,
            "failed_checks": 0,
            "recommendation": "",
        }
    row = summary.iloc[0]
    return {
        "provided": True,
        "input_dir": str(input_dir or ""),
        "accepted": _to_bool(row.get("accepted", False)),
        "dataset_count": _int(row, "dataset_count"),
        "ready_rate": _float(row, "ready_rate"),
        "failed_checks": _int(row, "total_failed_checks"),
        "recommendation": str(row.get("recommendation", "")),
    }


def _fold_row(
    index: int,
    label: str,
    index_path: Path,
    chain_path: Path,
    run_dir: Path,
    window_start_ns: int,
    window_end_ns: int,
    audit: SettlementConvergenceReport,
) -> dict[str, Any]:
    row = audit.summary.iloc[0] if not audit.summary.empty else pd.Series(dtype=object)
    best = (
        audit.candidate_config.get("best_opportunity", {})
        if isinstance(audit.candidate_config.get("best_opportunity", {}), dict)
        else {}
    )
    return {
        "fold_index": int(index),
        "fold": label,
        "index_ticks_path": str(index_path),
        "option_chain_path": str(chain_path),
        "run_dir": str(run_dir),
        "window_start_ns": int(window_start_ns),
        "window_end_ns": int(window_end_ns),
        "passed": bool(row.get("passed", False)),
        "failed_checks": _int(row, "failed_checks"),
        "opportunities": _int(row, "opportunities"),
        "buy_opportunities": _int(row, "buy_opportunities"),
        "sell_opportunities": _int(row, "sell_opportunities"),
        "total_net_edge": _float(row, "total_net_edge"),
        "median_net_edge": _float(row, "median_net_edge"),
        "best_net_edge": _float(row, "best_net_edge"),
        "median_known_fraction": _float(row, "median_known_fraction"),
        "best_ts": _jsonable(row.get("best_ts")),
        "best_expiry": _jsonable(row.get("best_expiry")),
        "best_strike": _jsonable(row.get("best_strike")),
        "best_option_type": _jsonable(row.get("best_option_type")),
        "best_direction": _jsonable(row.get("best_direction")),
        "best_side": _jsonable(best.get("side")),
        "best_touch_price": _jsonable(best.get("touch_price")),
        "best_trade_qty": _jsonable(best.get("trade_qty")),
        "best_projected_settlement": _jsonable(best.get("projected_settlement")),
        "best_projected_intrinsic": _jsonable(best.get("projected_intrinsic")),
        "best_gross_edge": _jsonable(best.get("gross_edge")),
        "best_gross_edge_ticks": _jsonable(best.get("gross_edge_ticks")),
        "best_cost": _jsonable(best.get("cost")),
    }


def _checks(
    folds: pd.DataFrame,
    thresholds: SettlementConvergenceWalkForwardThresholds,
) -> pd.DataFrame:
    pass_rate = float(folds["passed"].map(_to_bool).mean()) if not folds.empty else 0.0
    return pd.DataFrame(
        [
            _threshold_check("fold_count", len(folds), ">=", thresholds.min_folds),
            _threshold_check("pass_rate", pass_rate, ">=", thresholds.min_pass_rate),
            _threshold_check(
                "total_opportunities",
                _sum(folds, "opportunities"),
                ">=",
                thresholds.min_total_opportunities,
            ),
            _threshold_check("total_net_edge", _sum(folds, "total_net_edge"), ">=", thresholds.min_total_net_edge),
            _threshold_check(
                "median_best_net_edge",
                _median(folds, "best_net_edge"),
                ">=",
                thresholds.min_median_best_net_edge,
            ),
            _threshold_check(
                "median_known_fraction",
                _median(folds, "median_known_fraction"),
                ">=",
                thresholds.min_median_known_fraction,
            ),
        ]
    )


def _summary(folds: pd.DataFrame, checks: pd.DataFrame, *, market: str) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    best = folds.sort_values("best_net_edge", ascending=False).iloc[0] if not folds.empty else pd.Series(dtype=object)
    pass_rate = float(folds["passed"].map(_to_bool).mean()) if not folds.empty else 0.0
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0,
                "strategy": "settlement_convergence",
                "market": market,
                "recommendation": "candidate_for_replay" if passed else "keep_researching",
                "fold_count": int(len(folds)),
                "passed_folds": int(folds["passed"].map(_to_bool).sum()) if not folds.empty else 0,
                "pass_rate": pass_rate,
                "total_opportunities": _sum(folds, "opportunities"),
                "total_net_edge": _sum(folds, "total_net_edge"),
                "median_best_net_edge": _median(folds, "best_net_edge"),
                "best_net_edge": _max(folds, "best_net_edge"),
                "median_known_fraction": _median(folds, "median_known_fraction"),
                "best_fold": _jsonable(best.get("fold")),
                "best_ts": _jsonable(best.get("best_ts")),
                "best_expiry": _jsonable(best.get("best_expiry")),
                "best_strike": _jsonable(best.get("best_strike")),
                "best_option_type": _jsonable(best.get("best_option_type")),
                "best_direction": _jsonable(best.get("best_direction")),
            }
        ]
    )


def _candidate_config(
    checks: pd.DataFrame,
    summary: pd.Series,
    *,
    parameters: dict[str, Any],
    folds: pd.DataFrame,
) -> dict[str, Any]:
    failed_checks = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    best = folds.sort_values("best_net_edge", ascending=False).iloc[0] if not folds.empty else pd.Series(dtype=object)
    return {
        "schema_version": 1,
        "ready": bool(summary.get("passed", False)),
        "strategy": "settlement_convergence",
        "source_run_type": "settlement_convergence_walkforward",
        "failed_checks": failed_checks,
        "research_defaults": _jsonable(parameters),
        "walkforward": {
            "fold_count": _jsonable(summary.get("fold_count")),
            "passed_folds": _jsonable(summary.get("passed_folds")),
            "pass_rate": _jsonable(summary.get("pass_rate")),
            "total_opportunities": _jsonable(summary.get("total_opportunities")),
            "total_net_edge": _jsonable(summary.get("total_net_edge")),
            "median_best_net_edge": _jsonable(summary.get("median_best_net_edge")),
            "median_known_fraction": _jsonable(summary.get("median_known_fraction")),
        },
        "best_fold": {
            "fold": _jsonable(best.get("fold")),
            "ts": _jsonable(best.get("best_ts")),
            "expiry": _jsonable(best.get("best_expiry")),
            "strike": _jsonable(best.get("best_strike")),
            "option_type": _jsonable(best.get("best_option_type")),
            "direction": _jsonable(best.get("best_direction")),
            "side": _jsonable(best.get("best_side")),
            "touch_price": _jsonable(best.get("best_touch_price")),
            "trade_qty": _jsonable(best.get("best_trade_qty")),
            "projected_settlement": _jsonable(best.get("best_projected_settlement")),
            "projected_intrinsic": _jsonable(best.get("best_projected_intrinsic")),
            "gross_edge": _jsonable(best.get("best_gross_edge")),
            "gross_edge_ticks": _jsonable(best.get("best_gross_edge_ticks")),
            "cost": _jsonable(best.get("best_cost")),
            "best_net_edge": _jsonable(best.get("best_net_edge")),
        },
    }


def _fold_labels(paths: list[Path], labels: list[str] | None) -> list[str]:
    if labels is not None and len(labels) != len(paths):
        raise ValueError("labels must match index_tick_paths length")
    return [str(label) for label in labels] if labels is not None else [path.stem for path in paths]


def _expand_windows(value: int | list[int], count: int, name: str) -> list[int]:
    values = value if isinstance(value, list) else [value]
    if len(values) == 1:
        return [int(values[0])] * count
    if len(values) != count:
        raise ValueError(f"{name} must have length 1 or match the number of folds")
    return [int(item) for item in values]


def _safe_label(label: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")
    return slug or "fold"


def _threshold_check(name: str, value: Any, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else f"{name} {operator} {threshold} not met",
    }


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _max(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.max(skipna=True)) if values.notna().any() else 0.0


def _median(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.median(skipna=True)) if values.notna().any() else 0.0


def _float(row: pd.Series, column: str) -> float:
    try:
        return float(row.get(column, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _int(row: pd.Series, column: str) -> int:
    try:
        return int(float(row.get(column, 0)))
    except (TypeError, ValueError):
        return 0


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _validate_thresholds(thresholds: SettlementConvergenceWalkForwardThresholds) -> None:
    if thresholds.min_folds < 0:
        raise ValueError("min_folds must be non-negative")
    if not 0 <= thresholds.min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if thresholds.min_total_opportunities < 0:
        raise ValueError("min_total_opportunities must be non-negative")
    if not 0 <= thresholds.min_median_known_fraction <= 1:
        raise ValueError("min_median_known_fraction must be between 0 and 1")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
