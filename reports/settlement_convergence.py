from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind
from reports.manifest import write_experiment_manifest
from research.settlement import (
    expiring_option_intrinsic,
    projected_settlement,
    running_settlement_average,
)


@dataclass(frozen=True)
class SettlementConvergenceThresholds:
    min_opportunities: int = 1
    min_total_net_edge: float = 0.0
    min_best_net_edge: float = 0.0
    min_median_known_fraction: float = 0.0
    min_direction_count: int = 1


@dataclass(frozen=True)
class SettlementConvergenceReport:
    settlement: pd.DataFrame
    opportunities: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def evaluate_settlement_convergence(
    index_ticks: pd.DataFrame,
    option_chain: pd.DataFrame,
    *,
    window_start_ns: int,
    window_end_ns: int,
    index_price_col: str | None = None,
    lot_size: int = 75,
    tick_size: float = 0.05,
    qty: int = 75,
    depth_fraction: float = 1.0,
    min_known_fraction: float = 0.0,
    min_gross_edge_ticks: float = 0.0,
    min_net_edge: float = 0.0,
    thresholds: SettlementConvergenceThresholds | None = None,
) -> SettlementConvergenceReport:
    _validate_inputs(
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
        lot_size=lot_size,
        tick_size=tick_size,
        qty=qty,
        depth_fraction=depth_fraction,
        min_known_fraction=min_known_fraction,
        min_gross_edge_ticks=min_gross_edge_ticks,
        min_net_edge=min_net_edge,
    )
    thresholds = thresholds or SettlementConvergenceThresholds()
    _validate_thresholds(thresholds)
    _require(
        option_chain,
        [
            "ts",
            "expiry",
            "strike",
            "call_bid",
            "call_ask",
            "call_bid_qty",
            "call_ask_qty",
            "put_bid",
            "put_ask",
            "put_bid_qty",
            "put_ask_qty",
        ],
        "option_chain",
    )
    settlement = running_settlement_average(
        index_ticks,
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
        price_col=index_price_col,
    )
    opportunities = _opportunities(
        option_chain,
        settlement,
        lot_size=lot_size,
        tick_size=tick_size,
        qty=qty,
        depth_fraction=depth_fraction,
        min_known_fraction=min_known_fraction,
        min_gross_edge_ticks=min_gross_edge_ticks,
        min_net_edge=min_net_edge,
    )
    checks = _checks(opportunities, thresholds)
    summary = _summary(opportunities, checks)
    candidate = _candidate_config(
        checks,
        summary.iloc[0],
        parameters={
            "window_start_ns": int(window_start_ns),
            "window_end_ns": int(window_end_ns),
            "index_price_col": index_price_col,
            "lot_size": int(lot_size),
            "tick_size": float(tick_size),
            "qty": int(qty),
            "depth_fraction": float(depth_fraction),
            "min_known_fraction": float(min_known_fraction),
            "min_gross_edge_ticks": float(min_gross_edge_ticks),
            "min_net_edge": float(min_net_edge),
            "thresholds": asdict(thresholds),
        },
        opportunities=opportunities,
    )
    return SettlementConvergenceReport(
        settlement=settlement,
        opportunities=opportunities,
        checks=checks,
        summary=summary,
        candidate_config=candidate,
    )


def write_settlement_convergence_audit(
    index_ticks_path: str | Path,
    option_chain_path: str | Path,
    *,
    output_dir: str | Path,
    window_start_ns: int,
    window_end_ns: int,
    index_price_col: str | None = None,
    lot_size: int = 75,
    tick_size: float = 0.05,
    qty: int = 75,
    depth_fraction: float = 1.0,
    min_known_fraction: float = 0.0,
    min_gross_edge_ticks: float = 0.0,
    min_net_edge: float = 0.0,
    thresholds: SettlementConvergenceThresholds | None = None,
) -> SettlementConvergenceReport:
    index_file = Path(index_ticks_path)
    chain_file = Path(option_chain_path)
    if not index_file.exists():
        raise FileNotFoundError(f"index ticks not found: {index_file}")
    if not chain_file.exists():
        raise FileNotFoundError(f"option chain not found: {chain_file}")
    report = evaluate_settlement_convergence(
        pd.read_csv(index_file),
        pd.read_csv(chain_file),
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
        index_price_col=index_price_col,
        lot_size=lot_size,
        tick_size=tick_size,
        qty=qty,
        depth_fraction=depth_fraction,
        min_known_fraction=min_known_fraction,
        min_gross_edge_ticks=min_gross_edge_ticks,
        min_net_edge=min_net_edge,
        thresholds=thresholds,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.settlement.to_csv(out / "settlement_running_average.csv", index=False)
    report.opportunities.to_csv(out / "settlement_convergence_opportunities.csv", index=False)
    report.checks.to_csv(out / "settlement_convergence_checks.csv", index=False)
    report.summary.to_csv(out / "settlement_convergence_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(report.candidate_config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="settlement_convergence_audit",
        parameters={
            "window_start_ns": int(window_start_ns),
            "window_end_ns": int(window_end_ns),
            "index_price_col": index_price_col,
            "lot_size": int(lot_size),
            "tick_size": float(tick_size),
            "qty": int(qty),
            "depth_fraction": float(depth_fraction),
            "min_known_fraction": float(min_known_fraction),
            "min_gross_edge_ticks": float(min_gross_edge_ticks),
            "min_net_edge": float(min_net_edge),
            "thresholds": asdict(thresholds or SettlementConvergenceThresholds()),
        },
        inputs={"index_ticks": index_file, "option_chain": chain_file},
    )
    return SettlementConvergenceReport(
        settlement=report.settlement,
        opportunities=report.opportunities,
        checks=report.checks,
        summary=report.summary,
        candidate_config=report.candidate_config,
        output_dir=out,
    )


def _opportunities(
    option_chain: pd.DataFrame,
    settlement: pd.DataFrame,
    *,
    lot_size: int,
    tick_size: float,
    qty: int,
    depth_fraction: float,
    min_known_fraction: float,
    min_gross_edge_ticks: float,
    min_net_edge: float,
) -> pd.DataFrame:
    columns = [
        "ts",
        "expiry",
        "strike",
        "option_type",
        "direction",
        "side",
        "touch_price",
        "available_qty",
        "trade_qty",
        "running_average",
        "known_fraction",
        "current_index",
        "projected_settlement",
        "projected_intrinsic",
        "gross_edge",
        "gross_edge_ticks",
        "cost",
        "net_edge",
    ]
    if settlement.empty:
        return pd.DataFrame(columns=columns)
    chain = option_chain.sort_values("ts").copy().reset_index(drop=True)
    state = settlement.rename(columns={"settlement_price": "current_index"}).sort_values("ts")
    joined = pd.merge_asof(
        chain,
        state[["ts", "running_average", "known_fraction", "current_index"]],
        on="ts",
        direction="backward",
    )
    joined = joined.loc[joined["running_average"].notna()].copy()
    joined = joined.loc[joined["known_fraction"] >= min_known_fraction].copy()
    if joined.empty:
        return pd.DataFrame(columns=columns)

    cost_model = IndianCostModel.nse_index_options()
    instrument = Instrument("SETTLEMENT_CONVERGENCE_OPT", Kind.OPT, lot_size=lot_size, tick=tick_size)
    rows: list[dict[str, Any]] = []
    for row in joined.itertuples(index=False):
        projected = projected_settlement(
            running_average=float(row.running_average),
            known_fraction=float(row.known_fraction),
            current_index=float(row.current_index),
        )
        for option_type, bid, ask, bid_qty, ask_qty in (
            ("C", row.call_bid, row.call_ask, row.call_bid_qty, row.call_ask_qty),
            ("P", row.put_bid, row.put_ask, row.put_bid_qty, row.put_ask_qty),
        ):
            intrinsic = expiring_option_intrinsic(
                option_type=option_type,
                strike=float(row.strike),
                projected_settlement_value=projected,
            )
            rows.extend(
                [
                    _opportunity_row(
                        row,
                        option_type=option_type,
                        direction="buy_underpriced",
                        side=1,
                        touch_price=ask,
                        available_qty=ask_qty,
                        projected=projected,
                        intrinsic=intrinsic,
                        gross_edge=intrinsic - float(ask),
                        qty=qty,
                        depth_fraction=depth_fraction,
                        tick_size=tick_size,
                        instrument=instrument,
                        cost_model=cost_model,
                    ),
                    _opportunity_row(
                        row,
                        option_type=option_type,
                        direction="sell_overpriced",
                        side=-1,
                        touch_price=bid,
                        available_qty=bid_qty,
                        projected=projected,
                        intrinsic=intrinsic,
                        gross_edge=float(bid) - intrinsic,
                        qty=qty,
                        depth_fraction=depth_fraction,
                        tick_size=tick_size,
                        instrument=instrument,
                        cost_model=cost_model,
                    ),
                ]
            )
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    frame = frame.loc[
        (frame["trade_qty"] > 0)
        & (frame["touch_price"] > 0)
        & (frame["gross_edge_ticks"] >= min_gross_edge_ticks)
        & (frame["net_edge"] >= min_net_edge)
    ].copy()
    return frame.sort_values(["net_edge", "gross_edge_ticks"], ascending=[False, False]).reset_index(drop=True)


def _opportunity_row(
    source: Any,
    *,
    option_type: str,
    direction: str,
    side: int,
    touch_price: float,
    available_qty: float,
    projected: float,
    intrinsic: float,
    gross_edge: float,
    qty: int,
    depth_fraction: float,
    tick_size: float,
    instrument: Instrument,
    cost_model: IndianCostModel,
) -> dict[str, Any]:
    depth_qty = max(int(np.floor(float(available_qty) * depth_fraction)), 0) if not pd.isna(available_qty) else 0
    trade_qty = min(int(qty), depth_qty)
    cost = cost_model.cost(side, float(touch_price), trade_qty, instrument) if trade_qty > 0 else 0.0
    net_edge = gross_edge * trade_qty * instrument.multiplier - cost
    return {
        "ts": int(source.ts),
        "expiry": source.expiry,
        "strike": float(source.strike),
        "option_type": option_type,
        "direction": direction,
        "side": int(side),
        "touch_price": float(touch_price),
        "available_qty": int(depth_qty),
        "trade_qty": int(trade_qty),
        "running_average": float(source.running_average),
        "known_fraction": float(source.known_fraction),
        "current_index": float(source.current_index),
        "projected_settlement": float(projected),
        "projected_intrinsic": float(intrinsic),
        "gross_edge": float(gross_edge),
        "gross_edge_ticks": float(gross_edge / tick_size),
        "cost": float(cost),
        "net_edge": float(net_edge),
    }


def _checks(
    opportunities: pd.DataFrame,
    thresholds: SettlementConvergenceThresholds,
) -> pd.DataFrame:
    count = int(len(opportunities))
    total_net_edge = _sum(opportunities, "net_edge")
    best_net_edge = _max(opportunities, "net_edge")
    median_known_fraction = _median(opportunities, "known_fraction")
    direction_count = int(opportunities["direction"].nunique()) if not opportunities.empty else 0
    return pd.DataFrame(
        [
            _threshold_check("opportunity_count", count, ">=", thresholds.min_opportunities),
            _threshold_check("total_net_edge", total_net_edge, ">=", thresholds.min_total_net_edge),
            _threshold_check("best_net_edge", best_net_edge, ">=", thresholds.min_best_net_edge),
            _threshold_check(
                "median_known_fraction",
                median_known_fraction,
                ">=",
                thresholds.min_median_known_fraction,
            ),
            _threshold_check("direction_count", direction_count, ">=", thresholds.min_direction_count),
        ]
    )


def _summary(opportunities: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    best = opportunities.iloc[0] if not opportunities.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0,
                "recommendation": "candidate_for_replay" if passed else "keep_researching",
                "opportunities": int(len(opportunities)),
                "buy_opportunities": int((opportunities["side"] == 1).sum()) if not opportunities.empty else 0,
                "sell_opportunities": int((opportunities["side"] == -1).sum()) if not opportunities.empty else 0,
                "call_opportunities": int((opportunities["option_type"] == "C").sum()) if not opportunities.empty else 0,
                "put_opportunities": int((opportunities["option_type"] == "P").sum()) if not opportunities.empty else 0,
                "direction_count": int(opportunities["direction"].nunique()) if not opportunities.empty else 0,
                "total_trade_qty": _sum(opportunities, "trade_qty"),
                "total_net_edge": _sum(opportunities, "net_edge"),
                "median_net_edge": _median(opportunities, "net_edge"),
                "best_net_edge": _max(opportunities, "net_edge"),
                "median_known_fraction": _median(opportunities, "known_fraction"),
                "best_ts": _jsonable(best.get("ts")),
                "best_expiry": _jsonable(best.get("expiry")),
                "best_strike": _jsonable(best.get("strike")),
                "best_option_type": _jsonable(best.get("option_type")),
                "best_direction": _jsonable(best.get("direction")),
            }
        ]
    )


def _candidate_config(
    checks: pd.DataFrame,
    summary: pd.Series,
    *,
    parameters: dict[str, Any],
    opportunities: pd.DataFrame,
) -> dict[str, Any]:
    failed_checks = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    best = opportunities.iloc[0] if not opportunities.empty else pd.Series(dtype=object)
    return {
        "schema_version": 1,
        "ready": bool(summary.get("passed", False)),
        "strategy": "settlement_convergence",
        "source_run_type": "settlement_convergence_audit",
        "failed_checks": failed_checks,
        "research_defaults": _jsonable(parameters),
        "best_opportunity": {
            "ts": _jsonable(best.get("ts")),
            "expiry": _jsonable(best.get("expiry")),
            "strike": _jsonable(best.get("strike")),
            "option_type": _jsonable(best.get("option_type")),
            "direction": _jsonable(best.get("direction")),
            "side": _jsonable(best.get("side")),
            "touch_price": _jsonable(best.get("touch_price")),
            "trade_qty": _jsonable(best.get("trade_qty")),
            "projected_settlement": _jsonable(best.get("projected_settlement")),
            "projected_intrinsic": _jsonable(best.get("projected_intrinsic")),
            "gross_edge": _jsonable(best.get("gross_edge")),
            "gross_edge_ticks": _jsonable(best.get("gross_edge_ticks")),
            "cost": _jsonable(best.get("cost")),
            "net_edge": _jsonable(best.get("net_edge")),
            "known_fraction": _jsonable(best.get("known_fraction")),
        },
    }


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


def _validate_inputs(
    *,
    window_start_ns: int,
    window_end_ns: int,
    lot_size: int,
    tick_size: float,
    qty: int,
    depth_fraction: float,
    min_known_fraction: float,
    min_gross_edge_ticks: float,
    min_net_edge: float,
) -> None:
    if window_end_ns <= window_start_ns:
        raise ValueError("window_end_ns must be greater than window_start_ns")
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if qty <= 0:
        raise ValueError("qty must be positive")
    if not 0 < depth_fraction <= 1:
        raise ValueError("depth_fraction must be in (0, 1]")
    if not 0 <= min_known_fraction <= 1:
        raise ValueError("min_known_fraction must be between 0 and 1")
    if min_gross_edge_ticks < 0:
        raise ValueError("min_gross_edge_ticks must be non-negative")
    if min_net_edge < 0:
        raise ValueError("min_net_edge must be non-negative")


def _validate_thresholds(thresholds: SettlementConvergenceThresholds) -> None:
    if thresholds.min_opportunities < 0:
        raise ValueError("min_opportunities must be non-negative")
    if thresholds.min_direction_count < 0:
        raise ValueError("min_direction_count must be non-negative")
    if not 0 <= thresholds.min_median_known_fraction <= 1:
        raise ValueError("min_median_known_fraction must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


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
