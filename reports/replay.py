from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Mapping

import pandas as pd

from engine.hft_backtest import VENUE_ORDER_REJECTION_REASONS
from engine.multi_engine import MultiBacktestResult
from reports.manifest import write_experiment_manifest
from reports.pnl import pnl_decomposition
from reports.regime import equity_change_by_regime, fill_summary_by_regime
from reports.spread import pair_round_trips, residual_inventory, spread_capture_summary
from risk.compliance import check_order_to_trade_ratio


INPUT_INTEGRITY_DROP_COLUMNS = [
    "dropped_null_rows",
    "dropped_nonfinite_rows",
    "dropped_nonintegral_rows",
    "dropped_duplicate_rows",
    "dropped_integer_overflow_rows",
    "dropped_negative_depth_rows",
    "dropped_invalid_trade_rows",
    "dropped_nonpositive_strike_rows",
    "dropped_nonpositive_quote_rows",
    "dropped_crossed_quote_rows",
    "dropped_nonmonotonic_rows",
]
INPUT_SESSION_FILTER_COLUMNS = [
    "dropped_non_trading_day_rows",
    "dropped_out_of_session_rows",
]
INPUT_QUARANTINE_DIAGNOSTIC_COLUMNS = [
    "dropped_calendar_closed_rows",
    "dropped_calendar_out_of_range_rows",
]
INPUT_QUARANTINE_COLUMNS = [
    "dataset",
    "dataset_type",
    "total_rows",
    "kept_rows",
    "dropped_rows",
    "integrity_dropped_rows",
    "session_filtered_rows",
    "unclassified_dropped_rows",
    "empty_after_normalization",
    *INPUT_INTEGRITY_DROP_COLUMNS,
    *INPUT_SESSION_FILTER_COLUMNS,
    *INPUT_QUARANTINE_DIAGNOSTIC_COLUMNS,
]


def input_quarantine_frame(
    reports: Mapping[str, object],
    *,
    dataset_types: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    rows = []
    for dataset, report in reports.items():
        if not is_dataclass(report):
            raise TypeError(
                "input quarantine reports must be dataclass instances"
            )
        values = asdict(report)
        total_rows = int(values.get("total_rows", 0))
        kept_rows = int(values.get("kept_rows", 0))
        dropped_rows = max(total_rows - kept_rows, 0)
        drops = {
            column: int(values.get(column, 0))
            for column in (
                INPUT_INTEGRITY_DROP_COLUMNS
                + INPUT_SESSION_FILTER_COLUMNS
                + INPUT_QUARANTINE_DIAGNOSTIC_COLUMNS
            )
        }
        classified_integrity = sum(
            drops[column]
            for column in INPUT_INTEGRITY_DROP_COLUMNS
        )
        session_filtered = sum(
            drops[column]
            for column in INPUT_SESSION_FILTER_COLUMNS
        )
        unclassified = max(
            dropped_rows - classified_integrity - session_filtered,
            0,
        )
        rows.append(
            {
                "dataset": str(dataset),
                "dataset_type": str(
                    (dataset_types or {}).get(dataset, "unknown")
                ),
                "total_rows": total_rows,
                "kept_rows": kept_rows,
                "dropped_rows": dropped_rows,
                "integrity_dropped_rows": (
                    classified_integrity + unclassified
                ),
                "session_filtered_rows": session_filtered,
                "unclassified_dropped_rows": unclassified,
                "empty_after_normalization": kept_rows == 0,
                **drops,
            }
        )
    return pd.DataFrame(rows, columns=INPUT_QUARANTINE_COLUMNS)


def replay_summary(
    result: MultiBacktestResult,
    *,
    otr_limit: float = 50.0,
    strategy_orders: list[int] | None = None,
    input_quarantine: pd.DataFrame | None = None,
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
    order_cancellations = result.order_cancellations
    cancellation_statuses = (
        order_cancellations["status"]
        if not order_cancellations.empty
        else pd.Series(dtype="object")
    )
    cancellation_inflight_filled_qty = (
        pd.to_numeric(
            order_cancellations["filled_while_pending_qty"],
            errors="coerce",
        ).fillna(0)
        if not order_cancellations.empty
        else pd.Series(dtype="float64")
    )
    order_horizon_states = result.order_horizon_states
    horizon_order_states = (
        order_horizon_states["state"]
        if not order_horizon_states.empty
        else pd.Series(dtype="object")
    )
    horizon_order_remaining_qty = (
        pd.to_numeric(
            order_horizon_states["remaining_qty"],
            errors="coerce",
        ).fillna(0)
        if not order_horizon_states.empty
        else pd.Series(dtype="float64")
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
    input_quarantine_tracking_enabled = input_quarantine is not None
    input_quarantine = (
        input_quarantine
        if input_quarantine is not None
        else pd.DataFrame(columns=INPUT_QUARANTINE_COLUMNS)
    )
    input_total_rows = _numeric_sum(input_quarantine, "total_rows")
    input_kept_rows = _numeric_sum(input_quarantine, "kept_rows")
    input_dropped_rows = _numeric_sum(input_quarantine, "dropped_rows")
    input_integrity_dropped_rows = _numeric_sum(
        input_quarantine,
        "integrity_dropped_rows",
    )
    input_session_filtered_rows = _numeric_sum(
        input_quarantine,
        "session_filtered_rows",
    )
    input_empty_datasets = (
        int(
            input_quarantine["empty_after_normalization"]
            .fillna(False)
            .astype(bool)
            .sum()
        )
        if "empty_after_normalization" in input_quarantine.columns
        else 0
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
                "input_quarantine_tracking_enabled": bool(
                    input_quarantine_tracking_enabled
                ),
                "input_dataset_count": int(len(input_quarantine)),
                "input_total_rows": input_total_rows,
                "input_kept_rows": input_kept_rows,
                "input_dropped_rows": input_dropped_rows,
                "input_integrity_dropped_rows": (
                    input_integrity_dropped_rows
                ),
                "input_session_filtered_rows": (
                    input_session_filtered_rows
                ),
                "input_empty_datasets": input_empty_datasets,
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
                "causal_event_ordering_enabled": bool(
                    result.engine.causal_event_ordering_enabled
                ),
                "cancel_lifecycle_tracking_enabled": bool(
                    result.engine.cancel_lifecycle_tracking_enabled
                ),
                "cancel_requests": int(len(order_cancellations)),
                "cancel_effective_events": int(
                    cancellation_statuses.isin(
                        {
                            "effective",
                            "effective_after_partial_fill",
                        }
                    ).sum()
                ),
                "cancel_effective_after_partial_fill_events": int(
                    (
                        cancellation_statuses
                        == "effective_after_partial_fill"
                    ).sum()
                ),
                "cancel_filled_before_effective_events": int(
                    (
                        cancellation_statuses
                        == "filled_before_effective"
                    ).sum()
                ),
                "cancel_closed_before_effective_events": int(
                    (
                        cancellation_statuses
                        == "closed_before_effective"
                    ).sum()
                ),
                "cancel_pending_at_replay_end_events": int(
                    (
                        cancellation_statuses
                        == "pending_at_replay_end"
                    ).sum()
                ),
                "cancel_inflight_filled_qty": int(
                    cancellation_inflight_filled_qty.sum()
                ),
                "order_horizon_tracking_enabled": bool(
                    result.engine.order_horizon_tracking_enabled
                ),
                "open_orders_at_replay_end": int(
                    len(order_horizon_states)
                ),
                "open_order_qty_at_replay_end": int(
                    horizon_order_remaining_qty.sum()
                ),
                "pending_activation_orders_at_replay_end": int(
                    (
                        horizon_order_states
                        == "pending_activation"
                    ).sum()
                ),
                "active_ioc_orders_at_replay_end": int(
                    (horizon_order_states == "active_ioc").sum()
                ),
                "active_limit_orders_at_replay_end": int(
                    (horizon_order_states == "active_limit").sum()
                ),
                "cancel_pending_orders_at_replay_end": int(
                    (horizon_order_states == "cancel_pending").sum()
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


def _numeric_sum(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns or frame.empty:
        return 0
    return int(
        pd.to_numeric(frame[column], errors="coerce")
        .fillna(0)
        .sum()
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
    result.order_submissions.to_csv(
        out / "order_submissions.csv",
        index=False,
    )
    result.order_rejections.to_csv(out / "order_rejections.csv", index=False)
    result.order_cancellations.to_csv(
        out / "order_cancellations.csv",
        index=False,
    )
    result.order_horizon_states.to_csv(
        out / "order_horizon_states.csv",
        index=False,
    )
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
