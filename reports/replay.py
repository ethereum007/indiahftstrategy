from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine.hft_backtest import VENUE_ORDER_REJECTION_REASONS
from engine.multi_engine import MultiBacktestResult
from reports.manifest import write_experiment_manifest
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
    order_rejections = result.order_rejections
    rejection_reasons = (
        order_rejections["reason"]
        if not order_rejections.empty
        else pd.Series(dtype="object")
    )
    venue_rule_rejections = rejection_reasons.isin(
        VENUE_ORDER_REJECTION_REASONS
    )
    liquidity_shortfalls = result.liquidity_shortfalls
    liquidity_sources = (
        liquidity_shortfalls["liquidity_source"]
        if not liquidity_shortfalls.empty
        else pd.Series(dtype="object")
    )
    shortfall_qty = (
        pd.to_numeric(
            liquidity_shortfalls["shortfall_qty"],
            errors="coerce",
        ).fillna(0)
        if not liquidity_shortfalls.empty
        else pd.Series(dtype="float64")
    )
    displayed_mask = liquidity_sources.isin(
        {
            "ask_display",
            "bid_display",
            "passive_ask_price_through_display",
            "passive_bid_price_through_display",
            "terminal_ask_display",
            "terminal_bid_display",
        }
    )
    trade_print_mask = liquidity_sources == "trade_print"
    carried_depletion = (
        pd.to_numeric(
            liquidity_shortfalls["carried_depletion_qty"],
            errors="coerce",
        ).fillna(0)
        if not liquidity_shortfalls.empty
        else pd.Series(dtype="float64")
    )
    carried_depletion_mask = displayed_mask & carried_depletion.gt(0)
    queue_initializations = result.queue_initializations
    queue_modes = (
        queue_initializations["mode"]
        if not queue_initializations.empty
        else pd.Series(dtype="object")
    )
    queue_initialization_lag_ns = (
        pd.to_numeric(
            queue_initializations["initialization_lag_ns"],
            errors="coerce",
        ).fillna(0)
        if not queue_initializations.empty
        else pd.Series(dtype="float64")
    )
    limit_orders_sent = int(result.engine.limit_orders_sent)
    queue_initialization_events = int(len(queue_initializations))
    resting_transitions = result.resting_transitions
    transition_remaining_qty = (
        pd.to_numeric(
            resting_transitions["remaining_qty"],
            errors="coerce",
        ).fillna(0)
        if not resting_transitions.empty
        else pd.Series(dtype="float64")
    )
    transition_deferred = (
        resting_transitions["deferred_at_transition"].fillna(False).astype(bool)
        if not resting_transitions.empty
        else pd.Series(dtype="bool")
    )
    transition_initialized = (
        resting_transitions["queue_initialized"].fillna(False).astype(bool)
        if not resting_transitions.empty
        else pd.Series(dtype="bool")
    )
    transition_initialization_lag_ns = (
        pd.to_numeric(
            resting_transitions["queue_initialization_lag_ns"],
            errors="coerce",
        ).fillna(0)
        if not resting_transitions.empty
        else pd.Series(dtype="float64")
    )
    passive_price_throughs = result.passive_price_throughs
    price_through_requested_qty = (
        pd.to_numeric(
            passive_price_throughs["requested_qty"],
            errors="coerce",
        ).fillna(0)
        if not passive_price_throughs.empty
        else pd.Series(dtype="float64")
    )
    price_through_filled_qty = (
        pd.to_numeric(
            passive_price_throughs["filled_qty"],
            errors="coerce",
        ).fillna(0)
        if not passive_price_throughs.empty
        else pd.Series(dtype="float64")
    )
    price_through_shortfall_qty = (
        pd.to_numeric(
            passive_price_throughs["shortfall_qty"],
            errors="coerce",
        ).fillna(0)
        if not passive_price_throughs.empty
        else pd.Series(dtype="float64")
    )
    terminal_liquidations = result.terminal_liquidations
    terminal_requested_qty = (
        pd.to_numeric(
            terminal_liquidations["requested_qty"],
            errors="coerce",
        ).fillna(0)
        if not terminal_liquidations.empty
        else pd.Series(dtype="float64")
    )
    terminal_filled_qty = (
        pd.to_numeric(
            terminal_liquidations["filled_qty"],
            errors="coerce",
        ).fillna(0)
        if not terminal_liquidations.empty
        else pd.Series(dtype="float64")
    )
    terminal_shortfall_qty = (
        pd.to_numeric(
            terminal_liquidations["shortfall_qty"],
            errors="coerce",
        ).fillna(0)
        if not terminal_liquidations.empty
        else pd.Series(dtype="float64")
    )
    terminal_residual_positions = (
        pd.to_numeric(
            terminal_liquidations["residual_position"],
            errors="coerce",
        ).fillna(0)
        if not terminal_liquidations.empty
        else pd.Series(dtype="float64")
    )
    terminal_incomplete_mask = (
        terminal_shortfall_qty.gt(0)
        | terminal_residual_positions.ne(0)
    )
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
                "pending_order_risk_reservation_enabled": bool(
                    result.engine.reserve_open_order_risk
                ),
                "aggressive_self_cross_prevention_enabled": bool(
                    result.engine.ban_aggressive_self_cross
                ),
                "venue_order_validation_enabled": bool(
                    result.engine.venue_order_validation_enabled
                ),
                "shared_event_liquidity_enabled": bool(
                    result.engine.shared_event_liquidity_enabled
                ),
                "persistent_displayed_liquidity_enabled": bool(
                    result.engine.persist_displayed_liquidity_depletion
                ),
                "lot_conserving_fills_enabled": bool(
                    result.engine.lot_conserving_fills_enabled
                ),
                "arrival_queue_initialization_enabled": bool(
                    result.engine.arrival_queue_initialization_enabled
                ),
                "limit_orders_sent": limit_orders_sent,
                "queue_initialization_events": queue_initialization_events,
                "deferred_queue_initialization_events": int(
                    (queue_modes != "send_snapshot").sum()
                ),
                "uninitialized_limit_orders": max(
                    limit_orders_sent - queue_initialization_events,
                    0,
                ),
                "max_queue_initialization_lag_ns": int(
                    queue_initialization_lag_ns.max()
                    if not queue_initialization_lag_ns.empty
                    else 0
                ),
                "residual_resting_transition_events": int(
                    len(resting_transitions)
                ),
                "residual_resting_transition_qty": int(
                    transition_remaining_qty.sum()
                ),
                "deferred_residual_queue_events": int(
                    transition_deferred.sum()
                ),
                "unresolved_residual_queue_events": int(
                    (~transition_initialized).sum()
                ),
                "max_residual_queue_initialization_lag_ns": int(
                    transition_initialization_lag_ns.max()
                    if not transition_initialization_lag_ns.empty
                    else 0
                ),
                "passive_price_through_depth_constrained_enabled": bool(
                    result.engine
                    .passive_price_through_depth_constrained_enabled
                ),
                "passive_price_through_events": int(
                    len(passive_price_throughs)
                ),
                "passive_price_through_requested_qty": int(
                    price_through_requested_qty.sum()
                ),
                "passive_price_through_filled_qty": int(
                    price_through_filled_qty.sum()
                ),
                "passive_price_through_shortfall_qty": int(
                    price_through_shortfall_qty.sum()
                ),
                "passive_price_through_incomplete_events": int(
                    price_through_shortfall_qty.gt(0).sum()
                ),
                "terminal_liquidation_depth_constrained_enabled": bool(
                    result.engine.terminal_liquidation_depth_constrained_enabled
                ),
                "terminal_liquidation_events": int(len(terminal_liquidations)),
                "terminal_liquidation_requested_qty": int(
                    terminal_requested_qty.sum()
                ),
                "terminal_liquidation_filled_qty": int(
                    terminal_filled_qty.sum()
                ),
                "terminal_liquidation_shortfall_qty": int(
                    terminal_shortfall_qty.sum()
                ),
                "terminal_liquidation_incomplete_events": int(
                    terminal_incomplete_mask.sum()
                ),
                "terminal_residual_position_qty": int(
                    terminal_residual_positions.abs().sum()
                ),
                "terminal_residual_instruments": int(
                    terminal_residual_positions.ne(0).sum()
                ),
                "terminal_liquidation_complete": bool(
                    not terminal_incomplete_mask.any()
                ),
                "liquidity_shortfall_events": int(len(liquidity_shortfalls)),
                "liquidity_shortfall_qty": int(shortfall_qty.sum()),
                "displayed_liquidity_shortfall_events": int(
                    displayed_mask.sum()
                ),
                "displayed_liquidity_shortfall_qty": int(
                    shortfall_qty.loc[displayed_mask].sum()
                ),
                "trade_print_shortfall_events": int(trade_print_mask.sum()),
                "trade_print_shortfall_qty": int(
                    shortfall_qty.loc[trade_print_mask].sum()
                ),
                "carried_depletion_shortfall_events": int(
                    carried_depletion_mask.sum()
                ),
                "carried_depletion_shortfall_qty": int(
                    shortfall_qty.loc[carried_depletion_mask].sum()
                ),
                "pretrade_rejections": int(len(order_rejections)),
                "venue_rule_rejections": int(venue_rule_rejections.sum()),
                "position_risk_rejections": int(
                    rejection_reasons.isin(
                        {
                            "instrument_position_limit",
                            "portfolio_gross_position_limit",
                            "portfolio_delta_limit",
                            "portfolio_vega_limit",
                        }
                    ).sum()
                ),
                "self_cross_rejections": int(
                    (rejection_reasons == "aggressive_self_cross").sum()
                ),
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
    manifest_run_type: str | None = None,
    manifest_parameters: dict | None = None,
    manifest_inputs: dict | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.equity.to_csv(out / "equity.csv", index=False)
    result.fills.to_csv(out / "fills.csv", index=False)
    result.order_rejections.to_csv(out / "order_rejections.csv", index=False)
    result.liquidity_shortfalls.to_csv(
        out / "liquidity_shortfalls.csv",
        index=False,
    )
    result.queue_initializations.to_csv(
        out / "queue_initializations.csv",
        index=False,
    )
    result.resting_transitions.to_csv(
        out / "resting_transitions.csv",
        index=False,
    )
    result.passive_price_throughs.to_csv(
        out / "passive_price_throughs.csv",
        index=False,
    )
    result.terminal_liquidations.to_csv(
        out / "terminal_liquidations.csv",
        index=False,
    )
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
    if manifest_run_type is not None:
        write_experiment_manifest(
            out,
            run_type=manifest_run_type,
            parameters=manifest_parameters,
            inputs=manifest_inputs,
        )
    return out
