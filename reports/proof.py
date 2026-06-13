from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ProofThresholds:
    min_net_pnl: float = 0.0
    min_fills: int = 1
    max_drawdown: float | None = None
    max_otr: float | None = None
    min_maker_share: float | None = None
    min_worst_regime_equity_change: float | None = None
    min_markout_mean: float | None = None
    min_spread_net: float | None = None


@dataclass(frozen=True)
class ProofReport:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["all_passed"]) if not self.summary.empty else False


def evaluate_replay_dir(
    run_dir: str | Path,
    *,
    thresholds: ProofThresholds | None = None,
    run_name: str | None = None,
) -> ProofReport:
    return evaluate_replay_dirs(
        [run_dir],
        thresholds=thresholds,
        run_names=[run_name] if run_name is not None else None,
    )


def evaluate_replay_dirs(
    run_dirs: list[str | Path],
    *,
    thresholds: ProofThresholds | None = None,
    run_names: list[str] | None = None,
) -> ProofReport:
    if not run_dirs:
        raise ValueError("at least one replay run directory is required")
    thresholds = thresholds or ProofThresholds()
    if run_names is not None and len(run_names) != len(run_dirs):
        raise ValueError("run_names must match run_dirs length")

    metric_rows = []
    check_frames = []
    for idx, run_dir in enumerate(run_dirs):
        path = Path(run_dir)
        name = run_names[idx] if run_names is not None else path.name
        metrics = _run_metrics(path, name)
        metric_rows.append(metrics)
        check_frames.append(_run_checks(metrics, thresholds))

    metrics_df = pd.DataFrame(metric_rows)
    checks_df = pd.concat([*check_frames, _identity_checks(metrics_df)], ignore_index=True, sort=False)
    summary_df = _proof_summary(metrics_df, checks_df)
    return ProofReport(metrics=metrics_df, checks=checks_df, summary=summary_df)


def write_proof_report(
    run_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    thresholds: ProofThresholds | None = None,
    run_names: list[str] | None = None,
) -> ProofReport:
    report = evaluate_replay_dirs(run_dirs, thresholds=thresholds, run_names=run_names)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "proof_metrics.csv", index=False)
    report.checks.to_csv(out / "proof_checks.csv", index=False)
    report.summary.to_csv(out / "proof_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="proof_report",
        parameters={"thresholds": asdict(thresholds or ProofThresholds())},
        inputs={"run_dirs": run_dirs},
    )
    return ProofReport(report.metrics, report.checks, report.summary, out)


def _run_metrics(run_dir: Path, run_name: str) -> dict[str, float | int | str | bool]:
    summary = _read_required(run_dir / "summary.csv")
    row = summary.iloc[0]
    manifest = _read_manifest(run_dir)
    equity = _read_optional(run_dir / "equity.csv")
    equity_by_regime = _read_optional(run_dir / "equity_by_regime.csv")
    spread_summary = _read_optional(run_dir / "spread_summary.csv")
    markouts = _read_optional(run_dir / "markouts.csv")
    strategy = _strategy_key(_first_identity(row, manifest, ("strategy", "strategy_name", "strategy_id")))
    market = _identity_key(_first_identity(row, manifest, ("market", "market_profile", "market_name", "market_id")))

    net_pnl = _float(row, "net_pnl")
    fills = _int(row, "fills")
    turnover = _float(row, "turnover")
    total_costs = _float(row, "total_costs")
    maker_share = _float(row, "maker_share")
    otr = _float(row, "order_to_trade_ratio")
    max_drawdown = _max_drawdown(equity)
    worst_regime = _worst_regime_equity_change(equity_by_regime)
    markout_mean, markout_win_rate = _markout_quality(markouts)
    spread_net = _spread_net(spread_summary)

    return {
        "run": run_name,
        "strategy": strategy,
        "market": market,
        "net_pnl": net_pnl,
        "fills": fills,
        "turnover": turnover,
        "total_costs": total_costs,
        "cost_bps": 1e4 * total_costs / turnover if turnover > 0 else np.nan,
        "pnl_per_fill": net_pnl / fills if fills > 0 else np.nan,
        "maker_share": maker_share,
        "order_to_trade_ratio": otr,
        "otr_breached": _bool(row.get("otr_breached", False)),
        "max_drawdown": max_drawdown,
        "regime_count": int(len(equity_by_regime)) if not equity_by_regime.empty else 0,
        "losing_regimes": _losing_regimes(equity_by_regime),
        "worst_regime_equity_change": worst_regime,
        "spread_net": spread_net,
        "markout_mean": markout_mean,
        "markout_win_rate": markout_win_rate,
    }


def _run_checks(metrics: dict[str, float | int | str | bool], thresholds: ProofThresholds) -> pd.DataFrame:
    rows = [
        _check(metrics, "net_pnl", metrics["net_pnl"], ">=", thresholds.min_net_pnl),
        _check(metrics, "fills", metrics["fills"], ">=", thresholds.min_fills),
        {
            "run": metrics["run"],
            "check": "otr_not_breached",
            "value": metrics["otr_breached"],
            "operator": "is",
            "threshold": False,
            "passed": not bool(metrics["otr_breached"]),
            "reason": "summary.csv reported an OTR breach" if bool(metrics["otr_breached"]) else "",
        },
    ]
    if thresholds.max_drawdown is not None:
        rows.append(_check(metrics, "max_drawdown", metrics["max_drawdown"], "<=", thresholds.max_drawdown))
    if thresholds.max_otr is not None:
        rows.append(_check(metrics, "order_to_trade_ratio", metrics["order_to_trade_ratio"], "<=", thresholds.max_otr))
    if thresholds.min_maker_share is not None:
        rows.append(_check(metrics, "maker_share", metrics["maker_share"], ">=", thresholds.min_maker_share))
    if thresholds.min_worst_regime_equity_change is not None:
        rows.append(
            _check(
                metrics,
                "worst_regime_equity_change",
                metrics["worst_regime_equity_change"],
                ">=",
                thresholds.min_worst_regime_equity_change,
            )
        )
    if thresholds.min_markout_mean is not None:
        rows.append(_check(metrics, "markout_mean", metrics["markout_mean"], ">=", thresholds.min_markout_mean))
    if thresholds.min_spread_net is not None:
        rows.append(_check(metrics, "spread_net", metrics["spread_net"], ">=", thresholds.min_spread_net))
    return pd.DataFrame(rows)


def _check(
    metrics: dict[str, float | int | str | bool],
    name: str,
    value: float | int | str | bool,
    operator: str,
    threshold: float | int | bool,
) -> dict[str, float | int | str | bool]:
    value_float = float(value)
    threshold_float = float(threshold)
    is_missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not is_missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not is_missing) and value_float <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if is_missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "run": metrics["run"],
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _proof_summary(metrics: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    metric_runs = set(metrics["run"].astype(str))
    failed_runs = checks.loc[
        (~checks["passed"]) & checks["run"].astype(str).isin(metric_runs),
        "run",
    ].drop_duplicates()
    strategies = _identity_values(metrics, "strategy", normalizer=_strategy_key)
    markets = _identity_values(metrics, "market", normalizer=_identity_key)
    missing_strategies = _missing_identity_count(metrics, "strategy")
    missing_markets = _missing_identity_count(metrics, "market")
    mixed_identity = bool((len(strategies) > 1) or (len(markets) > 1))
    all_checks_passed = bool(checks["passed"].all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "run_count": int(len(metrics)),
                "passed_runs": int(len(metrics) - len(failed_runs)),
                "failed_runs": int(len(failed_runs)),
                "all_passed": bool(all_checks_passed and not mixed_identity),
                "strategy": next(iter(strategies)) if len(strategies) == 1 else "",
                "strategy_count": int(len(strategies)),
                "missing_strategy_runs": missing_strategies,
                "market": next(iter(markets)) if len(markets) == 1 else "",
                "market_count": int(len(markets)),
                "missing_market_runs": missing_markets,
                "mixed_identity": mixed_identity,
                "total_net_pnl": float(metrics["net_pnl"].sum()),
                "total_fills": int(metrics["fills"].sum()),
                "worst_drawdown": float(metrics["max_drawdown"].max(skipna=True)),
                "worst_regime_equity_change": float(metrics["worst_regime_equity_change"].min(skipna=True)),
            }
        ]
    )


def _identity_checks(metrics: pd.DataFrame) -> pd.DataFrame:
    strategies = _identity_values(metrics, "strategy", normalizer=_strategy_key)
    markets = _identity_values(metrics, "market", normalizer=_identity_key)
    strategy_passed = len(strategies) <= 1
    market_passed = len(markets) <= 1
    return pd.DataFrame(
        [
            {
                "run": "__proof__",
                "check": "same_strategy",
                "value": ";".join(sorted(strategies)) if strategies else "",
                "operator": "count<=",
                "threshold": 1,
                "passed": strategy_passed,
                "reason": "" if strategy_passed else "proof bundle mixes strategy identities",
            },
            {
                "run": "__proof__",
                "check": "same_market",
                "value": ";".join(sorted(markets)) if markets else "",
                "operator": "count<=",
                "threshold": 1,
                "passed": market_passed,
                "reason": "" if market_passed else "proof bundle mixes market identities",
            },
        ]
    )


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


def _read_manifest(run_dir: Path) -> dict:
    path = run_dir / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row else np.nan


def _int(row: pd.Series, column: str) -> int:
    return int(row[column]) if column in row and not pd.isna(row[column]) else 0


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _max_drawdown(equity: pd.DataFrame) -> float:
    if equity.empty or "equity" not in equity.columns:
        return np.nan
    values = pd.Series([0.0] + equity["equity"].astype(float).tolist())
    return float((values.cummax() - values).max())


def _worst_regime_equity_change(equity_by_regime: pd.DataFrame) -> float:
    if equity_by_regime.empty or "equity_change" not in equity_by_regime.columns:
        return np.nan
    return float(equity_by_regime["equity_change"].min())


def _losing_regimes(equity_by_regime: pd.DataFrame) -> int:
    if equity_by_regime.empty or "equity_change" not in equity_by_regime.columns:
        return 0
    return int((equity_by_regime["equity_change"] < 0).sum())


def _spread_net(spread_summary: pd.DataFrame) -> float:
    if spread_summary.empty or "net_spread" not in spread_summary.columns:
        return np.nan
    return float(spread_summary["net_spread"].sum())


def _markout_quality(markouts: pd.DataFrame) -> tuple[float, float]:
    if markouts.empty:
        return np.nan, np.nan
    if "markout" in markouts.columns:
        values = markouts["markout"].astype(float)
    elif "surface_markout" in markouts.columns:
        values = markouts["surface_markout"].astype(float)
    else:
        return np.nan, np.nan
    return float(values.mean()), float((values > 0).mean())


def _first_identity(row: pd.Series, manifest: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    parsed = _parse_scenario_key(_text(row, "scenario_key"))
    for key in keys:
        if key in parsed:
            return parsed[key]
    for section in ("parameters", "extra", "inputs"):
        value = _find_json_key(manifest.get(section, {}), keys)
        if value:
            return value
    return ""


def _identity_values(frame: pd.DataFrame, column: str, *, normalizer) -> set[str]:
    if frame.empty or column not in frame.columns:
        return set()
    return {value for value in frame[column].map(normalizer) if value}


def _missing_identity_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty:
        return 0
    if column not in frame.columns:
        return int(len(frame))
    return int((frame[column].map(_identity_key) == "").sum())


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


def _find_json_key(value: object, keys: tuple[str, ...]) -> str:
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


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _strategy_key(value: object) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")
