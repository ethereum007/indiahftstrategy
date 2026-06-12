from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.multi_engine import MultiBacktestResult
from reports.pnl import pnl_decomposition
from reports.regime import equity_change_by_regime, fill_summary_by_regime
from reports.spread import pair_round_trips, residual_inventory, spread_capture_summary
from risk.compliance import check_order_to_trade_ratio


def replay_summary(
    result: MultiBacktestResult,
    *,
    otr_limit: float = 50.0,
    strategy_orders: list[int] | None = None,
) -> pd.DataFrame:
    fills = result.fills
    strategy_fills = fills
    if strategy_orders is not None and not fills.empty:
        strategy_fills = fills.loc[fills["oid"].isin(strategy_orders)]
    final_equity = 0.0 if result.equity.empty else float(result.equity.iloc[-1]["equity"])
    fill_count = int(len(strategy_fills))
    turnover = (
        float((strategy_fills["qty"] * strategy_fills["price"]).sum())
        if fill_count
        else 0.0
    )
    maker_share = float(strategy_fills["maker"].mean()) if fill_count else 0.0
    otr = check_order_to_trade_ratio(
        orders_sent=result.engine.orders_sent,
        fills=fill_count,
        limit=otr_limit,
    )
    return pd.DataFrame(
        [
            {
                "net_pnl": final_equity,
                "total_costs": float(result.engine.total_costs),
                "orders_sent": int(result.engine.orders_sent),
                "fills": fill_count,
                "order_to_trade_ratio": float(otr.ratio),
                "otr_limit": float(otr.limit),
                "otr_breached": bool(otr.breached),
                "turnover": turnover,
                "maker_share": maker_share,
                "portfolio_delta": float(result.engine.portfolio_delta()),
                "portfolio_vega": float(result.engine.portfolio_vega()),
            }
        ]
    )


def write_replay_outputs(
    *,
    result: MultiBacktestResult,
    output_dir: str | Path,
    summary: pd.DataFrame,
    extra_frames: dict[str, pd.DataFrame] | None = None,
    include_regime: bool = True,
    strategy_order_ids: list[int] | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.equity.to_csv(out / "equity.csv", index=False)
    result.fills.to_csv(out / "fills.csv", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    pnl_decomposition(
        result.fills,
        strategy_order_ids=strategy_order_ids,
        group_cols=["instrument_id"] if "instrument_id" in result.fills.columns else None,
    ).to_csv(out / "pnl_decomposition.csv", index=False)
    spread_pairs = pair_round_trips(result.fills)
    spread_pairs.to_csv(out / "spread_pairs.csv", index=False)
    spread_capture_summary(spread_pairs).to_csv(out / "spread_summary.csv", index=False)
    residual_inventory(result.fills).to_csv(out / "residual_inventory.csv", index=False)
    if include_regime:
        fill_summary_by_regime(result.fills).to_csv(out / "fills_by_regime.csv", index=False)
        equity_change_by_regime(result.equity).to_csv(out / "equity_by_regime.csv", index=False)
    for name, frame in (extra_frames or {}).items():
        frame.to_csv(out / f"{name}.csv", index=False)
    return out
