from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


KNOWN_NON_PARAM_COLUMNS = {
    "run",
    "run_dir",
    "sweep",
    "sweep_path",
    "net_pnl",
    "fills",
    "orders_sent",
    "total_costs",
    "turnover",
    "cost_bps",
    "pnl_per_fill",
    "maker_share",
    "order_to_trade_ratio",
    "otr_limit",
    "otr_breached",
    "pending_order_risk_reservation_enabled",
    "aggressive_self_cross_prevention_enabled",
    "shared_event_liquidity_enabled",
    "persistent_displayed_liquidity_enabled",
    "liquidity_shortfall_events",
    "liquidity_shortfall_qty",
    "displayed_liquidity_shortfall_events",
    "displayed_liquidity_shortfall_qty",
    "trade_print_shortfall_events",
    "trade_print_shortfall_qty",
    "carried_depletion_shortfall_events",
    "carried_depletion_shortfall_qty",
    "pretrade_rejections",
    "position_risk_rejections",
    "self_cross_rejections",
    "portfolio_delta",
    "portfolio_vega",
    "max_drawdown",
    "regime_count",
    "losing_regimes",
    "worst_regime_equity_change",
    "spread_net",
    "markout_mean",
    "markout_win_rate",
    "proof_passed",
    "robust_score",
    "signal_count",
    "execution_count",
    "full_execution_count",
    "partial_execution_count",
}


@dataclass(frozen=True)
class SweepComparison:
    scenario_scores: pd.DataFrame
    scenario_runs: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def has_selection(self) -> bool:
        return bool(self.summary.iloc[0]["selectable_scenarios"] > 0) if not self.summary.empty else False


def compare_sweeps(
    sweep_paths: list[str | Path],
    *,
    labels: list[str] | None = None,
    group_cols: list[str] | None = None,
    min_pass_rate: float = 1.0,
    min_sweeps: int = 1,
    min_median_net_pnl: float = 0.0,
    max_worst_drawdown: float | None = None,
) -> SweepComparison:
    if not sweep_paths:
        raise ValueError("at least one sweep path is required")
    if labels is not None and len(labels) != len(sweep_paths):
        raise ValueError("labels must match sweep_paths length")
    if not 0 <= min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if min_sweeps <= 0:
        raise ValueError("min_sweeps must be positive")

    scenario_runs = _read_sweeps(sweep_paths, labels=labels)
    group_cols = group_cols or _infer_group_cols(scenario_runs)
    _require_group_cols(scenario_runs, group_cols)
    scenario_scores = _score_scenarios(
        scenario_runs,
        group_cols=group_cols,
        min_pass_rate=min_pass_rate,
        min_sweeps=min_sweeps,
        min_median_net_pnl=min_median_net_pnl,
        max_worst_drawdown=max_worst_drawdown,
    )
    summary = _comparison_summary(scenario_scores, scenario_runs)
    return SweepComparison(scenario_scores=scenario_scores, scenario_runs=scenario_runs, summary=summary)


def write_sweep_comparison(
    sweep_paths: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    group_cols: list[str] | None = None,
    min_pass_rate: float = 1.0,
    min_sweeps: int = 1,
    min_median_net_pnl: float = 0.0,
    max_worst_drawdown: float | None = None,
) -> SweepComparison:
    comparison = compare_sweeps(
        sweep_paths,
        labels=labels,
        group_cols=group_cols,
        min_pass_rate=min_pass_rate,
        min_sweeps=min_sweeps,
        min_median_net_pnl=min_median_net_pnl,
        max_worst_drawdown=max_worst_drawdown,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    comparison.scenario_runs.to_csv(out / "scenario_runs.csv", index=False)
    comparison.scenario_scores.to_csv(out / "scenario_scores.csv", index=False)
    comparison.summary.to_csv(out / "selection_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="sweep_comparison",
        parameters={
            "labels": labels,
            "group_cols": group_cols,
            "min_pass_rate": min_pass_rate,
            "min_sweeps": min_sweeps,
            "min_median_net_pnl": min_median_net_pnl,
            "max_worst_drawdown": max_worst_drawdown,
        },
        inputs={"sweeps": sweep_paths},
    )
    return SweepComparison(comparison.scenario_scores, comparison.scenario_runs, comparison.summary, out)


def _read_sweeps(paths: list[str | Path], *, labels: list[str] | None) -> pd.DataFrame:
    frames = []
    for idx, raw_path in enumerate(paths):
        path = Path(raw_path)
        csv_path = path / "sweep_runs.csv" if path.is_dir() else path
        if not csv_path.exists():
            raise FileNotFoundError(f"sweep_runs.csv not found for {path}")
        frame = pd.read_csv(csv_path)
        if frame.empty:
            raise ValueError(f"sweep run file is empty: {csv_path}")
        label = labels[idx] if labels is not None else path.stem
        frame = frame.copy()
        frame["sweep"] = label
        frame["sweep_path"] = str(path)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def _infer_group_cols(frame: pd.DataFrame) -> list[str]:
    preferred = [
        "trigger_ticks",
        "depth_fraction",
        "asof_latency_ns",
        "feed_latency_us",
        "order_latency_us",
    ]
    found = [col for col in preferred if col in frame.columns]
    if found:
        return found
    inferred = [col for col in frame.columns if col not in KNOWN_NON_PARAM_COLUMNS]
    return inferred or ["run"]


def _require_group_cols(frame: pd.DataFrame, group_cols: list[str]) -> None:
    missing = [col for col in group_cols if col not in frame.columns]
    if missing:
        raise ValueError(f"scenario group columns missing from sweep data: {missing}")


def _score_scenarios(
    frame: pd.DataFrame,
    *,
    group_cols: list[str],
    min_pass_rate: float,
    min_sweeps: int,
    min_median_net_pnl: float,
    max_worst_drawdown: float | None,
) -> pd.DataFrame:
    rows = []
    grouped = frame.groupby(group_cols, dropna=False, sort=True)
    for keys, group in grouped:
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        passed = _bool_series(group.get("proof_passed", pd.Series(False, index=group.index)))
        max_drawdown = _numeric(group, "max_drawdown")
        net_pnl = _numeric(group, "net_pnl")
        robust_score = _numeric(group, "robust_score")
        fills = _numeric(group, "fills")
        pretrade_rejections = _numeric(group, "pretrade_rejections").fillna(0.0)
        position_risk_rejections = _numeric(
            group,
            "position_risk_rejections",
        ).fillna(0.0)
        self_cross_rejections = _numeric(
            group,
            "self_cross_rejections",
        ).fillna(0.0)
        liquidity_shortfall_events = _numeric(
            group,
            "liquidity_shortfall_events",
        ).fillna(0.0)
        liquidity_shortfall_qty = _numeric(
            group,
            "liquidity_shortfall_qty",
        ).fillna(0.0)
        carried_depletion_shortfall_events = _numeric(
            group,
            "carried_depletion_shortfall_events",
        ).fillna(0.0)
        carried_depletion_shortfall_qty = _numeric(
            group,
            "carried_depletion_shortfall_qty",
        ).fillna(0.0)
        worst_regime = _numeric(group, "worst_regime_equity_change")
        losing_regimes = _numeric(group, "losing_regimes")

        sweeps_seen = int(group["sweep"].nunique())
        scenario_runs = int(len(group))
        pass_rate = float(passed.mean()) if scenario_runs else 0.0
        worst_drawdown = float(max_drawdown.max(skipna=True))
        median_net_pnl = float(net_pnl.median(skipna=True))
        selection_passed = (
            sweeps_seen >= min_sweeps
            and pass_rate >= min_pass_rate
            and median_net_pnl >= min_median_net_pnl
            and (max_worst_drawdown is None or worst_drawdown <= max_worst_drawdown)
        )

        row = {col: value for col, value in zip(group_cols, key_tuple)}
        row.update(
            {
                "scenario_key": _scenario_key(group_cols, key_tuple),
                "sweeps_seen": sweeps_seen,
                "scenario_runs": scenario_runs,
                "passed_runs": int(passed.sum()),
                "pass_rate": pass_rate,
                "median_net_pnl": median_net_pnl,
                "mean_net_pnl": float(net_pnl.mean(skipna=True)),
                "min_net_pnl": float(net_pnl.min(skipna=True)),
                "total_net_pnl": float(net_pnl.sum(skipna=True)),
                "median_robust_score": float(robust_score.median(skipna=True)),
                "min_robust_score": float(robust_score.min(skipna=True)),
                "worst_drawdown": worst_drawdown,
                "median_fills": float(fills.median(skipna=True)),
                "min_fills": float(fills.min(skipna=True)),
                "total_pretrade_rejections": int(pretrade_rejections.sum()),
                "total_position_risk_rejections": int(
                    position_risk_rejections.sum()
                ),
                "total_self_cross_rejections": int(
                    self_cross_rejections.sum()
                ),
                "total_liquidity_shortfall_events": int(
                    liquidity_shortfall_events.sum()
                ),
                "total_liquidity_shortfall_qty": int(
                    liquidity_shortfall_qty.sum()
                ),
                "total_carried_depletion_shortfall_events": int(
                    carried_depletion_shortfall_events.sum()
                ),
                "total_carried_depletion_shortfall_qty": int(
                    carried_depletion_shortfall_qty.sum()
                ),
                "worst_regime_equity_change": float(worst_regime.min(skipna=True)),
                "runs_with_losing_regimes": int((losing_regimes > 0).sum()),
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
            "median_net_pnl",
            "min_net_pnl",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    scores.insert(0, "rank", np.arange(1, len(scores) + 1))
    return scores


def _comparison_summary(scores: pd.DataFrame, scenario_runs: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(
            [
                {
                    "sweep_count": int(scenario_runs["sweep"].nunique()),
                    "scenario_count": 0,
                    "selectable_scenarios": 0,
                    "best_scenario_key": "",
                    "best_pass_rate": np.nan,
                    "best_median_net_pnl": np.nan,
                    "best_worst_drawdown": np.nan,
                    "total_runs": int(len(scenario_runs)),
                    "total_pretrade_rejections": 0,
                    "total_position_risk_rejections": 0,
                    "total_self_cross_rejections": 0,
                    "total_liquidity_shortfall_events": 0,
                    "total_liquidity_shortfall_qty": 0,
                    "total_carried_depletion_shortfall_events": 0,
                    "total_carried_depletion_shortfall_qty": 0,
                }
            ]
        )
    selectable = scores.loc[scores["selection_passed"]]
    best = selectable.iloc[0] if not selectable.empty else scores.iloc[0]
    return pd.DataFrame(
        [
            {
                "sweep_count": int(scenario_runs["sweep"].nunique()),
                "scenario_count": int(len(scores)),
                "selectable_scenarios": int(len(selectable)),
                "best_scenario_key": best["scenario_key"],
                "best_pass_rate": float(best["pass_rate"]),
                "best_median_net_pnl": float(best["median_net_pnl"]),
                "best_worst_drawdown": float(best["worst_drawdown"]),
                "total_runs": int(len(scenario_runs)),
                "total_pretrade_rejections": int(
                    _numeric(scenario_runs, "pretrade_rejections")
                    .fillna(0.0)
                    .sum()
                ),
                "total_position_risk_rejections": int(
                    _numeric(scenario_runs, "position_risk_rejections")
                    .fillna(0.0)
                    .sum()
                ),
                "total_self_cross_rejections": int(
                    _numeric(scenario_runs, "self_cross_rejections")
                    .fillna(0.0)
                    .sum()
                ),
                "total_liquidity_shortfall_events": int(
                    _numeric(scenario_runs, "liquidity_shortfall_events")
                    .fillna(0.0)
                    .sum()
                ),
                "total_liquidity_shortfall_qty": int(
                    _numeric(scenario_runs, "liquidity_shortfall_qty")
                    .fillna(0.0)
                    .sum()
                ),
                "total_carried_depletion_shortfall_events": int(
                    _numeric(
                        scenario_runs,
                        "carried_depletion_shortfall_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_carried_depletion_shortfall_qty": int(
                    _numeric(
                        scenario_runs,
                        "carried_depletion_shortfall_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
            }
        ]
    )


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _bool_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    return values.map(_to_bool).fillna(False)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _scenario_key(group_cols: list[str], key_tuple: tuple[object, ...]) -> str:
    return "|".join(f"{col}={_format_value(value)}" for col, value in zip(group_cols, key_tuple))


def _format_value(value: object) -> str:
    if pd.isna(value):
        return "NA"
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)
