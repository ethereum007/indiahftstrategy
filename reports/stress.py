from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class StressConfig:
    cost_multipliers: list[float]
    slippage_ticks: list[float]
    adverse_bps: list[float]
    tick_size: float = 0.05
    contract_multiplier: float = 1.0
    min_net_pnl: float = 0.0
    min_fills: int = 1
    max_drawdown: float | None = None


@dataclass(frozen=True)
class StressReport:
    results: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["all_scenarios_passed"]) if not self.summary.empty else False


def stress_replay_dirs(
    run_dirs: list[str | Path],
    *,
    config: StressConfig,
    run_names: list[str] | None = None,
) -> StressReport:
    if not run_dirs:
        raise ValueError("at least one replay run directory is required")
    if run_names is not None and len(run_names) != len(run_dirs):
        raise ValueError("run_names must match run_dirs length")
    _validate_config(config)

    rows = []
    for idx, raw_run_dir in enumerate(run_dirs):
        run_dir = Path(raw_run_dir)
        run_name = run_names[idx] if run_names is not None else run_dir.name
        summary = _read_required(run_dir / "summary.csv")
        fills = _read_optional(run_dir / "fills.csv")
        equity = _read_optional(run_dir / "equity.csv")
        base = summary.iloc[0]
        for cost_multiplier, slippage_ticks, adverse_bps in product(
            config.cost_multipliers,
            config.slippage_ticks,
            config.adverse_bps,
        ):
            rows.append(
                _stress_row(
                    run_name=run_name,
                    run_dir=run_dir,
                    base=base,
                    fills=fills,
                    equity=equity,
                    config=config,
                    cost_multiplier=float(cost_multiplier),
                    slippage_ticks=float(slippage_ticks),
                    adverse_bps=float(adverse_bps),
                )
            )
    results = pd.DataFrame(rows)
    summary = _stress_summary(results)
    return StressReport(results=results, summary=summary)


def write_stress_report(
    run_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    config: StressConfig,
    run_names: list[str] | None = None,
) -> StressReport:
    report = stress_replay_dirs(run_dirs, config=config, run_names=run_names)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.results.to_csv(out / "stress_results.csv", index=False)
    report.summary.to_csv(out / "stress_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="stress_report",
        parameters={"config": config.__dict__, "run_names": run_names},
        inputs={"run_dirs": run_dirs},
    )
    return StressReport(report.results, report.summary, out)


def _stress_row(
    *,
    run_name: str,
    run_dir: Path,
    base: pd.Series,
    fills: pd.DataFrame,
    equity: pd.DataFrame,
    config: StressConfig,
    cost_multiplier: float,
    slippage_ticks: float,
    adverse_bps: float,
) -> dict[str, float | int | str | bool]:
    fills = _normalize_fills(fills)
    base_net_pnl = _float(base, "net_pnl")
    base_total_costs = _float(base, "total_costs")
    fills_count = _int(base, "fills")
    turnover = _float(base, "turnover")

    penalty = _fill_penalties(
        fills,
        cost_multiplier=cost_multiplier,
        slippage_ticks=slippage_ticks,
        adverse_bps=adverse_bps,
        tick_size=config.tick_size,
        contract_multiplier=config.contract_multiplier,
    )
    extra_cost = float(penalty["extra_cost"].sum()) if not penalty.empty else 0.0
    slippage_cost = float(penalty["slippage_cost"].sum()) if not penalty.empty else 0.0
    adverse_cost = float(penalty["adverse_cost"].sum()) if not penalty.empty else 0.0
    total_penalty = extra_cost + slippage_cost + adverse_cost
    stressed_net_pnl, stressed_max_drawdown = _stressed_equity_stats(
        equity,
        penalty,
        fallback_net_pnl=base_net_pnl - total_penalty,
    )
    stressed_total_costs = base_total_costs + total_penalty
    passed = (
        stressed_net_pnl >= config.min_net_pnl
        and fills_count >= config.min_fills
        and (config.max_drawdown is None or stressed_max_drawdown <= config.max_drawdown)
    )
    return {
        "run": run_name,
        "run_dir": str(run_dir),
        "scenario": _scenario_name(cost_multiplier, slippage_ticks, adverse_bps),
        "cost_multiplier": cost_multiplier,
        "slippage_ticks": slippage_ticks,
        "adverse_bps": adverse_bps,
        "base_net_pnl": base_net_pnl,
        "stressed_net_pnl": stressed_net_pnl,
        "pnl_penalty": total_penalty,
        "extra_cost": extra_cost,
        "slippage_cost": slippage_cost,
        "adverse_cost": adverse_cost,
        "base_total_costs": base_total_costs,
        "stressed_total_costs": stressed_total_costs,
        "turnover": turnover,
        "stressed_cost_bps": 1e4 * stressed_total_costs / turnover if turnover > 0 else np.nan,
        "fills": fills_count,
        "stressed_max_drawdown": stressed_max_drawdown,
        "passed": bool(passed),
    }


def _fill_penalties(
    fills: pd.DataFrame,
    *,
    cost_multiplier: float,
    slippage_ticks: float,
    adverse_bps: float,
    tick_size: float,
    contract_multiplier: float,
) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(columns=["ts_ns", "extra_cost", "slippage_cost", "adverse_cost", "total_penalty"])
    required = ["ts_ns", "qty", "price", "cost"]
    missing = [col for col in required if col not in fills.columns]
    if missing:
        raise ValueError(f"fills missing required columns: {missing}")
    out = fills.copy()
    qty = out["qty"].astype(float)
    price = out["price"].astype(float)
    notional = price * qty * contract_multiplier
    out["extra_cost"] = np.maximum(cost_multiplier - 1.0, 0.0) * out["cost"].astype(float)
    out["slippage_cost"] = abs(slippage_ticks) * tick_size * qty * contract_multiplier
    out["adverse_cost"] = abs(adverse_bps) * notional / 1e4
    out["total_penalty"] = out["extra_cost"] + out["slippage_cost"] + out["adverse_cost"]
    return out[["ts_ns", "extra_cost", "slippage_cost", "adverse_cost", "total_penalty"]]


def _stressed_equity_stats(
    equity: pd.DataFrame,
    penalty: pd.DataFrame,
    *,
    fallback_net_pnl: float,
) -> tuple[float, float]:
    if equity.empty or "equity" not in equity.columns or "ts" not in equity.columns:
        return float(fallback_net_pnl), 0.0
    stressed = equity.sort_values("ts").copy()
    stressed["equity"] = stressed["equity"].astype(float)
    if penalty.empty:
        stressed["stressed_equity"] = stressed["equity"]
    else:
        penalty_by_ts = (
            penalty.groupby("ts_ns", dropna=False)["total_penalty"]
            .sum()
            .sort_index()
            .cumsum()
        )
        fill_ts = penalty_by_ts.index.to_numpy(dtype=np.int64)
        cumulative = penalty_by_ts.to_numpy(dtype=float)
        equity_ts = stressed["ts"].astype("int64").to_numpy()
        idx = np.searchsorted(fill_ts, equity_ts, side="right") - 1
        applied = np.where(idx >= 0, cumulative[np.maximum(idx, 0)], 0.0)
        stressed["stressed_equity"] = stressed["equity"] - applied
    values = pd.Series([0.0] + stressed["stressed_equity"].astype(float).tolist())
    max_drawdown = float((values.cummax() - values).max())
    return float(stressed.iloc[-1]["stressed_equity"]), max_drawdown


def _stress_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(
            columns=[
                "scenario_count",
                "run_count",
                "passed_rows",
                "failed_rows",
                "all_scenarios_passed",
                "worst_stressed_net_pnl",
                "median_stressed_net_pnl",
                "worst_stressed_drawdown",
            ]
        )
    return pd.DataFrame(
        [
            {
                "scenario_count": int(results["scenario"].nunique()),
                "run_count": int(results["run"].nunique()),
                "passed_rows": int(results["passed"].sum()),
                "failed_rows": int((~results["passed"]).sum()),
                "all_scenarios_passed": bool(results["passed"].all()),
                "worst_stressed_net_pnl": float(results["stressed_net_pnl"].min()),
                "median_stressed_net_pnl": float(results["stressed_net_pnl"].median()),
                "worst_stressed_drawdown": float(results["stressed_max_drawdown"].max()),
            }
        ]
    )


def _normalize_fills(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return fills
    out = fills.copy()
    if "ts_ns" not in out.columns and "ts" in out.columns:
        out = out.rename(columns={"ts": "ts_ns"})
    return out


def _validate_config(config: StressConfig) -> None:
    if not config.cost_multipliers:
        raise ValueError("cost_multipliers must not be empty")
    if not config.slippage_ticks:
        raise ValueError("slippage_ticks must not be empty")
    if not config.adverse_bps:
        raise ValueError("adverse_bps must not be empty")
    if any(value < 0 for value in config.cost_multipliers):
        raise ValueError("cost_multipliers must be non-negative")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if config.contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive")


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required replay artifact missing: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required replay artifact is empty: {path}")
    return frame


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else 0.0


def _int(row: pd.Series, column: str) -> int:
    return int(row[column]) if column in row and not pd.isna(row[column]) else 0


def _scenario_name(cost_multiplier: float, slippage_ticks: float, adverse_bps: float) -> str:
    return (
        f"cost_{_label_number(cost_multiplier)}x"
        f"__slip_{_label_number(slippage_ticks)}ticks"
        f"__adverse_{_label_number(adverse_bps)}bps"
    )


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")
