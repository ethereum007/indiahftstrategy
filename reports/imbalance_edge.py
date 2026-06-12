from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.loaders import load_tick_csv
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ImbalanceEdgeThresholds:
    entry_imbalance: float = 0.6
    min_microprice_edge_ticks: float = 0.25
    max_spread_ticks: float = 2.0
    min_depth: int = 1
    forward_horizon_ns: int = 100_000_000
    min_signals: int = 1
    min_direction_count: int = 1
    min_mean_forward_edge_ticks: float = 0.0
    min_win_rate: float = 0.0
    min_median_forward_edge_ticks: float | None = None


@dataclass(frozen=True)
class ImbalanceEdgeAudit:
    signals: pd.DataFrame
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def evaluate_imbalance_edge(
    ticks: pd.DataFrame,
    *,
    thresholds: ImbalanceEdgeThresholds | None = None,
    tick_size: float = 0.05,
) -> ImbalanceEdgeAudit:
    thresholds = thresholds or ImbalanceEdgeThresholds()
    _validate_thresholds(thresholds, tick_size=tick_size)
    features = _feature_frame(ticks, tick_size=tick_size)
    signals = _signal_frame(features, thresholds=thresholds, tick_size=tick_size)
    metrics = pd.DataFrame([_metrics(signals)])
    checks = _checks(metrics.iloc[0], thresholds)
    summary = _summary(metrics, checks)
    return ImbalanceEdgeAudit(signals=signals, metrics=metrics, checks=checks, summary=summary)


def write_imbalance_edge_audit(
    ticks_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: ImbalanceEdgeThresholds | None = None,
    tick_size: float = 0.05,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> ImbalanceEdgeAudit:
    thresholds = thresholds or ImbalanceEdgeThresholds()
    ticks_file = Path(ticks_path)
    ticks = load_tick_csv(
        ticks_file,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    ).data
    audit = evaluate_imbalance_edge(ticks, thresholds=thresholds, tick_size=tick_size)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit.signals.to_csv(out / "imbalance_signals.csv", index=False)
    audit.metrics.to_csv(out / "imbalance_edge_metrics.csv", index=False)
    audit.checks.to_csv(out / "imbalance_edge_checks.csv", index=False)
    audit.summary.to_csv(out / "imbalance_edge_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="imbalance_edge_audit",
        parameters={
            "thresholds": asdict(thresholds),
            "tick_size": tick_size,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "market": market,
        },
        inputs={"ticks": ticks_file},
    )
    return ImbalanceEdgeAudit(audit.signals, audit.metrics, audit.checks, audit.summary, out)


def _feature_frame(ticks: pd.DataFrame, *, tick_size: float) -> pd.DataFrame:
    _require(ticks, ["ts", "bid", "ask", "bid_qty", "ask_qty"], "ticks")
    frame = ticks.sort_values("ts").reset_index(drop=True).copy()
    frame["bid"] = pd.to_numeric(frame["bid"], errors="coerce")
    frame["ask"] = pd.to_numeric(frame["ask"], errors="coerce")
    frame["bid_qty"] = pd.to_numeric(frame["bid_qty"], errors="coerce")
    frame["ask_qty"] = pd.to_numeric(frame["ask_qty"], errors="coerce")
    frame = frame.loc[
        (frame["bid"] > 0)
        & (frame["ask"] >= frame["bid"])
        & (frame["bid_qty"] > 0)
        & (frame["ask_qty"] > 0)
    ].copy()
    depth = frame["bid_qty"] + frame["ask_qty"]
    frame["mid"] = 0.5 * (frame["bid"] + frame["ask"])
    frame["spread_ticks"] = (frame["ask"] - frame["bid"]) / tick_size
    frame["imbalance"] = (frame["bid_qty"] - frame["ask_qty"]) / depth
    frame["microprice"] = (frame["ask"] * frame["bid_qty"] + frame["bid"] * frame["ask_qty"]) / depth
    frame["microprice_edge_ticks"] = (frame["microprice"] - frame["mid"]) / tick_size
    return frame.reset_index(drop=True)


def _signal_frame(
    features: pd.DataFrame,
    *,
    thresholds: ImbalanceEdgeThresholds,
    tick_size: float,
) -> pd.DataFrame:
    if features.empty:
        return _empty_signals()
    work = features.copy()
    depth_ok = work[["bid_qty", "ask_qty"]].min(axis=1) >= thresholds.min_depth
    spread_ok = work["spread_ticks"] <= thresholds.max_spread_ticks
    long_signal = (
        (work["imbalance"] >= thresholds.entry_imbalance)
        & (work["microprice_edge_ticks"] >= thresholds.min_microprice_edge_ticks)
    )
    short_signal = (
        (work["imbalance"] <= -thresholds.entry_imbalance)
        & (work["microprice_edge_ticks"] <= -thresholds.min_microprice_edge_ticks)
    )
    work["signal_side"] = np.select([long_signal, short_signal], [1, -1], default=0)
    signals = work.loc[depth_ok & spread_ok & (work["signal_side"] != 0)].copy()
    if signals.empty:
        return _empty_signals()

    future = work[["ts", "mid"]].rename(columns={"ts": "future_ts", "mid": "future_mid"})
    target = signals.sort_values("ts").copy()
    target["target_ts"] = target["ts"] + int(thresholds.forward_horizon_ns)
    joined = pd.merge_asof(
        target.sort_values("target_ts"),
        future.sort_values("future_ts"),
        left_on="target_ts",
        right_on="future_ts",
        direction="forward",
    )
    joined["forward_edge_ticks"] = (
        joined["signal_side"].astype(float) * (joined["future_mid"] - joined["mid"]) / tick_size
    )
    joined["forward_edge"] = joined["forward_edge_ticks"] * tick_size
    joined["win"] = joined["forward_edge_ticks"] > 0
    joined["usable_forward"] = joined["future_mid"].notna()
    if "regime" not in joined.columns:
        joined["regime"] = ""
    return joined[
        [
            "ts",
            "target_ts",
            "future_ts",
            "signal_side",
            "bid",
            "ask",
            "bid_qty",
            "ask_qty",
            "mid",
            "future_mid",
            "spread_ticks",
            "imbalance",
            "microprice",
            "microprice_edge_ticks",
            "forward_edge",
            "forward_edge_ticks",
            "win",
            "usable_forward",
            "regime",
        ]
    ].reset_index(drop=True)


def _metrics(signals: pd.DataFrame) -> dict[str, Any]:
    usable = signals.loc[signals["usable_forward"].astype(bool)] if not signals.empty else signals
    edge = pd.to_numeric(usable["forward_edge_ticks"], errors="coerce").dropna() if not usable.empty else pd.Series(dtype=float)
    return {
        "signal_count": int(len(signals)),
        "usable_signals": int(len(usable)),
        "long_signals": int((signals["signal_side"] > 0).sum()) if not signals.empty else 0,
        "short_signals": int((signals["signal_side"] < 0).sum()) if not signals.empty else 0,
        "direction_count": int(signals["signal_side"].dropna().nunique()) if not signals.empty else 0,
        "mean_forward_edge_ticks": float(edge.mean()) if not edge.empty else np.nan,
        "median_forward_edge_ticks": float(edge.median()) if not edge.empty else np.nan,
        "best_forward_edge_ticks": float(edge.max()) if not edge.empty else np.nan,
        "worst_forward_edge_ticks": float(edge.min()) if not edge.empty else np.nan,
        "win_rate": float((usable["forward_edge_ticks"] > 0).mean()) if not usable.empty else 0.0,
        "median_spread_ticks": float(signals["spread_ticks"].median()) if not signals.empty else np.nan,
        "median_abs_imbalance": float(signals["imbalance"].abs().median()) if not signals.empty else np.nan,
        "median_microprice_edge_ticks": float(signals["microprice_edge_ticks"].abs().median())
        if not signals.empty
        else np.nan,
        "regime_count": int(signals["regime"].dropna().nunique()) if not signals.empty else 0,
    }


def _checks(row: pd.Series, thresholds: ImbalanceEdgeThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check(row, "usable_signals", ">=", thresholds.min_signals),
        _threshold_check(row, "direction_count", ">=", thresholds.min_direction_count),
        _threshold_check(row, "mean_forward_edge_ticks", ">=", thresholds.min_mean_forward_edge_ticks),
        _threshold_check(row, "win_rate", ">=", thresholds.min_win_rate),
    ]
    if thresholds.min_median_forward_edge_ticks is not None:
        checks.append(
            _threshold_check(
                row,
                "median_forward_edge_ticks",
                ">=",
                thresholds.min_median_forward_edge_ticks,
            )
        )
    return pd.DataFrame(checks)


def _summary(metrics: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    row = metrics.iloc[0]
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "replay_or_sweep_candidate" if passed else "keep_researching",
                "signal_count": int(row["signal_count"]),
                "usable_signals": int(row["usable_signals"]),
                "direction_count": int(row["direction_count"]),
                "mean_forward_edge_ticks": row["mean_forward_edge_ticks"],
                "median_forward_edge_ticks": row["median_forward_edge_ticks"],
                "win_rate": float(row["win_rate"]),
                "median_spread_ticks": row["median_spread_ticks"],
            }
        ]
    )


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
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _validate_thresholds(thresholds: ImbalanceEdgeThresholds, *, tick_size: float) -> None:
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if not 0 < thresholds.entry_imbalance < 1:
        raise ValueError("entry_imbalance must be between 0 and 1")
    if thresholds.min_microprice_edge_ticks < 0:
        raise ValueError("min_microprice_edge_ticks must be non-negative")
    if thresholds.max_spread_ticks <= 0:
        raise ValueError("max_spread_ticks must be positive")
    if thresholds.min_depth <= 0:
        raise ValueError("min_depth must be positive")
    if thresholds.forward_horizon_ns <= 0:
        raise ValueError("forward_horizon_ns must be positive")
    if thresholds.min_signals < 0:
        raise ValueError("min_signals must be non-negative")
    if thresholds.min_direction_count < 0:
        raise ValueError("min_direction_count must be non-negative")
    if not 0 <= thresholds.min_win_rate <= 1:
        raise ValueError("min_win_rate must be between 0 and 1")


def _empty_signals() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ts",
            "target_ts",
            "future_ts",
            "signal_side",
            "bid",
            "ask",
            "bid_qty",
            "ask_qty",
            "mid",
            "future_mid",
            "spread_ticks",
            "imbalance",
            "microprice",
            "microprice_edge_ticks",
            "forward_edge",
            "forward_edge_ticks",
            "win",
            "usable_forward",
            "regime",
        ]
    )


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan
