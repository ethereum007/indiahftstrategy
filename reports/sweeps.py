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
    "input_quarantine_tracking_enabled",
    "input_dataset_count",
    "input_total_rows",
    "input_kept_rows",
    "input_dropped_rows",
    "input_integrity_dropped_rows",
    "input_session_filtered_rows",
    "input_empty_datasets",
    "parity_futures_asof_freshness_enabled",
    "parity_futures_max_quote_age_ns",
    "parity_futures_join_audit_present",
    "parity_futures_signals_present",
    "parity_futures_join_rows",
    "parity_futures_fresh_join_rows",
    "parity_futures_stale_join_rows",
    "parity_futures_unmatched_join_rows",
    "parity_futures_unclassified_join_rows",
    "parity_futures_max_observed_join_age_ns",
    "parity_futures_signal_count",
    "parity_futures_signals_without_age",
    "parity_futures_signal_age_violations",
    "parity_futures_max_signal_age_ns",
    "parity_execution_guard_enabled",
    "parity_execution_guard_declared",
    "parity_execution_run_detected",
    "parity_execution_max_leg_book_age_ns",
    "parity_execution_max_leg_book_skew_ns",
    "parity_execution_guard_present",
    "parity_execution_legging_present",
    "parity_execution_guard_rows",
    "parity_execution_guard_attempts",
    "parity_execution_guard_passed_attempts",
    "parity_execution_guard_deferred_attempts",
    "parity_execution_ioc_batch_preflight_enabled",
    "parity_execution_ioc_batch_preflight_declared",
    "parity_execution_ioc_batch_preflight_attempts",
    "parity_execution_ioc_batch_preflight_passed_attempts",
    "parity_execution_ioc_batch_preflight_rejected_attempts",
    "parity_execution_ioc_batch_preflight_missing_evidence_rows",
    "parity_execution_ioc_batch_preflight_consistency_violations",
    "parity_execution_ioc_visible_not_marketable_attempts",
    "parity_execution_ioc_visible_capacity_shortfall_attempts",
    "parity_execution_ioc_visible_capacity_missing_evidence_rows",
    "parity_execution_ioc_visible_capacity_consistency_violations",
    "parity_execution_min_routed_visible_fill_ratio",
    "parity_execution_guard_missing_evidence_rows",
    "parity_execution_guard_unclassified_rows",
    "parity_execution_guard_consistency_violations",
    "parity_execution_signal_expiry_events",
    "parity_execution_stale_book_attempts",
    "parity_execution_negative_book_age_attempts",
    "parity_execution_skew_attempts",
    "parity_execution_routing_complete_attempts",
    "parity_execution_routing_incomplete_attempts",
    "parity_execution_guard_passed_missing_age_rows",
    "parity_execution_guard_age_violations",
    "parity_execution_guard_skew_violations",
    "parity_execution_max_routed_book_age_ns",
    "parity_execution_max_routed_book_skew_ns",
    "parity_execution_count",
    "parity_execution_legging_missing_evidence_rows",
    "parity_execution_legging_consistency_violations",
    "parity_execution_complete_count",
    "parity_execution_incomplete_count",
    "parity_execution_route_rejected_legs",
    "parity_execution_unfilled_legs",
    "pending_order_risk_reservation_enabled",
    "aggressive_self_cross_prevention_enabled",
    "venue_order_validation_enabled",
    "shared_event_liquidity_enabled",
    "persistent_displayed_liquidity_enabled",
    "lot_conserving_fills_enabled",
    "causal_event_ordering_enabled",
    "cancel_lifecycle_tracking_enabled",
    "cancel_requests",
    "cancel_effective_events",
    "cancel_effective_after_partial_fill_events",
    "cancel_filled_before_effective_events",
    "cancel_closed_before_effective_events",
    "cancel_pending_at_replay_end_events",
    "cancel_inflight_filled_qty",
    "order_horizon_tracking_enabled",
    "open_orders_at_replay_end",
    "open_order_qty_at_replay_end",
    "pending_activation_orders_at_replay_end",
    "active_ioc_orders_at_replay_end",
    "active_limit_orders_at_replay_end",
    "cancel_pending_orders_at_replay_end",
    "arrival_queue_initialization_enabled",
    "limit_orders_sent",
    "queue_initialization_events",
    "deferred_queue_initialization_events",
    "uninitialized_limit_orders",
    "max_queue_initialization_lag_ns",
    "residual_resting_transition_events",
    "residual_resting_transition_qty",
    "deferred_residual_queue_events",
    "unresolved_residual_queue_events",
    "max_residual_queue_initialization_lag_ns",
    "passive_price_through_depth_constrained_enabled",
    "passive_price_through_events",
    "passive_price_through_requested_qty",
    "passive_price_through_filled_qty",
    "passive_price_through_shortfall_qty",
    "passive_price_through_incomplete_events",
    "terminal_liquidation_depth_constrained_enabled",
    "terminal_liquidation_events",
    "terminal_liquidation_requested_qty",
    "terminal_liquidation_filled_qty",
    "terminal_liquidation_shortfall_qty",
    "terminal_liquidation_incomplete_events",
    "terminal_residual_position_qty",
    "terminal_residual_instruments",
    "terminal_liquidation_complete",
    "liquidity_shortfall_events",
    "liquidity_shortfall_qty",
    "displayed_liquidity_shortfall_events",
    "displayed_liquidity_shortfall_qty",
    "trade_print_shortfall_events",
    "trade_print_shortfall_qty",
    "carried_depletion_shortfall_events",
    "carried_depletion_shortfall_qty",
    "pretrade_rejections",
    "venue_rule_rejections",
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
        input_quarantine_tracking_enabled = _bool_series(
            group.get(
                "input_quarantine_tracking_enabled",
                pd.Series(False, index=group.index),
            )
        )
        input_dataset_count = _numeric(
            group,
            "input_dataset_count",
        ).fillna(0.0)
        input_total_rows = _numeric(
            group,
            "input_total_rows",
        ).fillna(0.0)
        input_kept_rows = _numeric(
            group,
            "input_kept_rows",
        ).fillna(0.0)
        input_dropped_rows = _numeric(
            group,
            "input_dropped_rows",
        ).fillna(0.0)
        input_integrity_dropped_rows = _numeric(
            group,
            "input_integrity_dropped_rows",
        ).fillna(0.0)
        input_session_filtered_rows = _numeric(
            group,
            "input_session_filtered_rows",
        ).fillna(0.0)
        input_empty_datasets = _numeric(
            group,
            "input_empty_datasets",
        ).fillna(0.0)
        parity_futures_asof_freshness_enabled = _bool_series(
            group.get(
                "parity_futures_asof_freshness_enabled",
                pd.Series(False, index=group.index),
            )
        )
        parity_futures_join_rows = _numeric(
            group,
            "parity_futures_join_rows",
        ).fillna(0.0)
        parity_futures_fresh_join_rows = _numeric(
            group,
            "parity_futures_fresh_join_rows",
        ).fillna(0.0)
        parity_futures_stale_join_rows = _numeric(
            group,
            "parity_futures_stale_join_rows",
        ).fillna(0.0)
        parity_futures_unmatched_join_rows = _numeric(
            group,
            "parity_futures_unmatched_join_rows",
        ).fillna(0.0)
        parity_futures_signal_count = _numeric(
            group,
            "parity_futures_signal_count",
        ).fillna(0.0)
        parity_futures_signals_without_age = _numeric(
            group,
            "parity_futures_signals_without_age",
        ).fillna(0.0)
        parity_futures_signal_age_violations = _numeric(
            group,
            "parity_futures_signal_age_violations",
        ).fillna(0.0)
        parity_futures_max_signal_age_ns = _numeric(
            group,
            "parity_futures_max_signal_age_ns",
        ).fillna(0.0)
        pretrade_rejections = _numeric(group, "pretrade_rejections").fillna(0.0)
        venue_rule_rejections = _numeric(
            group,
            "venue_rule_rejections",
        ).fillna(0.0)
        position_risk_rejections = _numeric(
            group,
            "position_risk_rejections",
        ).fillna(0.0)
        self_cross_rejections = _numeric(
            group,
            "self_cross_rejections",
        ).fillna(0.0)
        cancel_requests = _numeric(
            group,
            "cancel_requests",
        ).fillna(0.0)
        cancel_effective_events = _numeric(
            group,
            "cancel_effective_events",
        ).fillna(0.0)
        cancel_effective_after_partial_fill_events = _numeric(
            group,
            "cancel_effective_after_partial_fill_events",
        ).fillna(0.0)
        cancel_filled_before_effective_events = _numeric(
            group,
            "cancel_filled_before_effective_events",
        ).fillna(0.0)
        cancel_closed_before_effective_events = _numeric(
            group,
            "cancel_closed_before_effective_events",
        ).fillna(0.0)
        cancel_pending_at_replay_end_events = _numeric(
            group,
            "cancel_pending_at_replay_end_events",
        ).fillna(0.0)
        cancel_inflight_filled_qty = _numeric(
            group,
            "cancel_inflight_filled_qty",
        ).fillna(0.0)
        order_horizon_tracking_enabled = _bool_series(
            group.get(
                "order_horizon_tracking_enabled",
                pd.Series(False, index=group.index),
            )
        )
        open_orders_at_replay_end = _numeric(
            group,
            "open_orders_at_replay_end",
        ).fillna(0.0)
        open_order_qty_at_replay_end = _numeric(
            group,
            "open_order_qty_at_replay_end",
        ).fillna(0.0)
        pending_activation_orders_at_replay_end = _numeric(
            group,
            "pending_activation_orders_at_replay_end",
        ).fillna(0.0)
        active_ioc_orders_at_replay_end = _numeric(
            group,
            "active_ioc_orders_at_replay_end",
        ).fillna(0.0)
        active_limit_orders_at_replay_end = _numeric(
            group,
            "active_limit_orders_at_replay_end",
        ).fillna(0.0)
        cancel_pending_orders_at_replay_end = _numeric(
            group,
            "cancel_pending_orders_at_replay_end",
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
        limit_orders_sent = _numeric(group, "limit_orders_sent").fillna(0.0)
        queue_initialization_events = _numeric(
            group,
            "queue_initialization_events",
        ).fillna(0.0)
        deferred_queue_initialization_events = _numeric(
            group,
            "deferred_queue_initialization_events",
        ).fillna(0.0)
        uninitialized_limit_orders = _numeric(
            group,
            "uninitialized_limit_orders",
        ).fillna(0.0)
        queue_initialization_lag_ns = _numeric(
            group,
            "max_queue_initialization_lag_ns",
        ).fillna(0.0)
        residual_resting_transition_events = _numeric(
            group,
            "residual_resting_transition_events",
        ).fillna(0.0)
        residual_resting_transition_qty = _numeric(
            group,
            "residual_resting_transition_qty",
        ).fillna(0.0)
        deferred_residual_queue_events = _numeric(
            group,
            "deferred_residual_queue_events",
        ).fillna(0.0)
        unresolved_residual_queue_events = _numeric(
            group,
            "unresolved_residual_queue_events",
        ).fillna(0.0)
        residual_queue_initialization_lag_ns = _numeric(
            group,
            "max_residual_queue_initialization_lag_ns",
        ).fillna(0.0)
        passive_price_through_events = _numeric(
            group,
            "passive_price_through_events",
        ).fillna(0.0)
        passive_price_through_requested_qty = _numeric(
            group,
            "passive_price_through_requested_qty",
        ).fillna(0.0)
        passive_price_through_filled_qty = _numeric(
            group,
            "passive_price_through_filled_qty",
        ).fillna(0.0)
        passive_price_through_shortfall_qty = _numeric(
            group,
            "passive_price_through_shortfall_qty",
        ).fillna(0.0)
        passive_price_through_incomplete_events = _numeric(
            group,
            "passive_price_through_incomplete_events",
        ).fillna(0.0)
        terminal_liquidation_events = _numeric(
            group,
            "terminal_liquidation_events",
        ).fillna(0.0)
        terminal_liquidation_requested_qty = _numeric(
            group,
            "terminal_liquidation_requested_qty",
        ).fillna(0.0)
        terminal_liquidation_filled_qty = _numeric(
            group,
            "terminal_liquidation_filled_qty",
        ).fillna(0.0)
        terminal_liquidation_shortfall_qty = _numeric(
            group,
            "terminal_liquidation_shortfall_qty",
        ).fillna(0.0)
        terminal_liquidation_incomplete_events = _numeric(
            group,
            "terminal_liquidation_incomplete_events",
        ).fillna(0.0)
        terminal_residual_position_qty = _numeric(
            group,
            "terminal_residual_position_qty",
        ).fillna(0.0)
        terminal_residual_instruments = _numeric(
            group,
            "terminal_residual_instruments",
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
                "input_quarantine_tracking_enabled_runs": int(
                    input_quarantine_tracking_enabled.sum()
                ),
                "total_input_datasets": int(input_dataset_count.sum()),
                "total_input_rows": int(input_total_rows.sum()),
                "total_input_kept_rows": int(input_kept_rows.sum()),
                "total_input_dropped_rows": int(input_dropped_rows.sum()),
                "total_input_integrity_dropped_rows": int(
                    input_integrity_dropped_rows.sum()
                ),
                "total_input_session_filtered_rows": int(
                    input_session_filtered_rows.sum()
                ),
                "total_input_empty_datasets": int(
                    input_empty_datasets.sum()
                ),
                "parity_futures_asof_freshness_enabled_runs": int(
                    parity_futures_asof_freshness_enabled.sum()
                ),
                "total_parity_futures_join_rows": int(
                    parity_futures_join_rows.sum()
                ),
                "total_parity_futures_fresh_join_rows": int(
                    parity_futures_fresh_join_rows.sum()
                ),
                "total_parity_futures_stale_join_rows": int(
                    parity_futures_stale_join_rows.sum()
                ),
                "total_parity_futures_unmatched_join_rows": int(
                    parity_futures_unmatched_join_rows.sum()
                ),
                "total_parity_futures_signal_count": int(
                    parity_futures_signal_count.sum()
                ),
                "total_parity_futures_signals_without_age": int(
                    parity_futures_signals_without_age.sum()
                ),
                "total_parity_futures_signal_age_violations": int(
                    parity_futures_signal_age_violations.sum()
                ),
                "max_parity_futures_signal_age_ns": int(
                    parity_futures_max_signal_age_ns.max()
                ),
                **_parity_execution_aggregates(group),
                "total_pretrade_rejections": int(pretrade_rejections.sum()),
                "total_venue_rule_rejections": int(
                    venue_rule_rejections.sum()
                ),
                "total_position_risk_rejections": int(
                    position_risk_rejections.sum()
                ),
                "total_self_cross_rejections": int(
                    self_cross_rejections.sum()
                ),
                "total_cancel_requests": int(cancel_requests.sum()),
                "total_cancel_effective_events": int(
                    cancel_effective_events.sum()
                ),
                "total_cancel_effective_after_partial_fill_events": int(
                    cancel_effective_after_partial_fill_events.sum()
                ),
                "total_cancel_filled_before_effective_events": int(
                    cancel_filled_before_effective_events.sum()
                ),
                "total_cancel_closed_before_effective_events": int(
                    cancel_closed_before_effective_events.sum()
                ),
                "total_cancel_pending_at_replay_end_events": int(
                    cancel_pending_at_replay_end_events.sum()
                ),
                "total_cancel_inflight_filled_qty": int(
                    cancel_inflight_filled_qty.sum()
                ),
                "order_horizon_tracking_enabled_runs": int(
                    order_horizon_tracking_enabled.sum()
                ),
                "total_open_orders_at_replay_end": int(
                    open_orders_at_replay_end.sum()
                ),
                "total_open_order_qty_at_replay_end": int(
                    open_order_qty_at_replay_end.sum()
                ),
                "total_pending_activation_orders_at_replay_end": int(
                    pending_activation_orders_at_replay_end.sum()
                ),
                "total_active_ioc_orders_at_replay_end": int(
                    active_ioc_orders_at_replay_end.sum()
                ),
                "total_active_limit_orders_at_replay_end": int(
                    active_limit_orders_at_replay_end.sum()
                ),
                "total_cancel_pending_orders_at_replay_end": int(
                    cancel_pending_orders_at_replay_end.sum()
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
                "total_limit_orders_sent": int(limit_orders_sent.sum()),
                "total_queue_initialization_events": int(
                    queue_initialization_events.sum()
                ),
                "total_deferred_queue_initialization_events": int(
                    deferred_queue_initialization_events.sum()
                ),
                "total_uninitialized_limit_orders": int(
                    uninitialized_limit_orders.sum()
                ),
                "max_queue_initialization_lag_ns": int(
                    queue_initialization_lag_ns.max()
                ),
                "total_residual_resting_transition_events": int(
                    residual_resting_transition_events.sum()
                ),
                "total_residual_resting_transition_qty": int(
                    residual_resting_transition_qty.sum()
                ),
                "total_deferred_residual_queue_events": int(
                    deferred_residual_queue_events.sum()
                ),
                "total_unresolved_residual_queue_events": int(
                    unresolved_residual_queue_events.sum()
                ),
                "max_residual_queue_initialization_lag_ns": int(
                    residual_queue_initialization_lag_ns.max()
                ),
                "total_passive_price_through_events": int(
                    passive_price_through_events.sum()
                ),
                "total_passive_price_through_requested_qty": int(
                    passive_price_through_requested_qty.sum()
                ),
                "total_passive_price_through_filled_qty": int(
                    passive_price_through_filled_qty.sum()
                ),
                "total_passive_price_through_shortfall_qty": int(
                    passive_price_through_shortfall_qty.sum()
                ),
                "total_passive_price_through_incomplete_events": int(
                    passive_price_through_incomplete_events.sum()
                ),
                "total_terminal_liquidation_events": int(
                    terminal_liquidation_events.sum()
                ),
                "total_terminal_liquidation_requested_qty": int(
                    terminal_liquidation_requested_qty.sum()
                ),
                "total_terminal_liquidation_filled_qty": int(
                    terminal_liquidation_filled_qty.sum()
                ),
                "total_terminal_liquidation_shortfall_qty": int(
                    terminal_liquidation_shortfall_qty.sum()
                ),
                "total_terminal_liquidation_incomplete_events": int(
                    terminal_liquidation_incomplete_events.sum()
                ),
                "total_terminal_residual_position_qty": int(
                    terminal_residual_position_qty.sum()
                ),
                "total_terminal_residual_instruments": int(
                    terminal_residual_instruments.sum()
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
                    "input_quarantine_tracking_enabled_runs": 0,
                    "total_input_datasets": 0,
                    "total_input_rows": 0,
                    "total_input_kept_rows": 0,
                    "total_input_dropped_rows": 0,
                    "total_input_integrity_dropped_rows": 0,
                    "total_input_session_filtered_rows": 0,
                    "total_input_empty_datasets": 0,
                    "parity_futures_asof_freshness_enabled_runs": 0,
                    "total_parity_futures_join_rows": 0,
                    "total_parity_futures_fresh_join_rows": 0,
                    "total_parity_futures_stale_join_rows": 0,
                    "total_parity_futures_unmatched_join_rows": 0,
                    "total_parity_futures_signal_count": 0,
                    "total_parity_futures_signals_without_age": 0,
                    "total_parity_futures_signal_age_violations": 0,
                    "max_parity_futures_signal_age_ns": 0,
                    **_parity_execution_aggregates(pd.DataFrame()),
                    "total_pretrade_rejections": 0,
                    "total_venue_rule_rejections": 0,
                    "total_position_risk_rejections": 0,
                    "total_self_cross_rejections": 0,
                    "total_cancel_requests": 0,
                    "total_cancel_effective_events": 0,
                    "total_cancel_effective_after_partial_fill_events": 0,
                    "total_cancel_filled_before_effective_events": 0,
                    "total_cancel_closed_before_effective_events": 0,
                    "total_cancel_pending_at_replay_end_events": 0,
                    "total_cancel_inflight_filled_qty": 0,
                    "order_horizon_tracking_enabled_runs": 0,
                    "total_open_orders_at_replay_end": 0,
                    "total_open_order_qty_at_replay_end": 0,
                    "total_pending_activation_orders_at_replay_end": 0,
                    "total_active_ioc_orders_at_replay_end": 0,
                    "total_active_limit_orders_at_replay_end": 0,
                    "total_cancel_pending_orders_at_replay_end": 0,
                    "total_liquidity_shortfall_events": 0,
                    "total_liquidity_shortfall_qty": 0,
                    "total_carried_depletion_shortfall_events": 0,
                    "total_carried_depletion_shortfall_qty": 0,
                    "total_limit_orders_sent": 0,
                    "total_queue_initialization_events": 0,
                    "total_deferred_queue_initialization_events": 0,
                    "total_uninitialized_limit_orders": 0,
                    "max_queue_initialization_lag_ns": 0,
                    "total_residual_resting_transition_events": 0,
                    "total_residual_resting_transition_qty": 0,
                    "total_deferred_residual_queue_events": 0,
                    "total_unresolved_residual_queue_events": 0,
                    "max_residual_queue_initialization_lag_ns": 0,
                    "total_passive_price_through_events": 0,
                    "total_passive_price_through_requested_qty": 0,
                    "total_passive_price_through_filled_qty": 0,
                    "total_passive_price_through_shortfall_qty": 0,
                    "total_passive_price_through_incomplete_events": 0,
                    "total_terminal_liquidation_events": 0,
                    "total_terminal_liquidation_requested_qty": 0,
                    "total_terminal_liquidation_filled_qty": 0,
                    "total_terminal_liquidation_shortfall_qty": 0,
                    "total_terminal_liquidation_incomplete_events": 0,
                    "total_terminal_residual_position_qty": 0,
                    "total_terminal_residual_instruments": 0,
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
                "input_quarantine_tracking_enabled_runs": int(
                    _bool_series(
                        scenario_runs.get(
                            "input_quarantine_tracking_enabled",
                            pd.Series(False, index=scenario_runs.index),
                        )
                    ).sum()
                ),
                "total_input_datasets": int(
                    _numeric(scenario_runs, "input_dataset_count")
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_rows": int(
                    _numeric(scenario_runs, "input_total_rows")
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_kept_rows": int(
                    _numeric(scenario_runs, "input_kept_rows")
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_dropped_rows": int(
                    _numeric(scenario_runs, "input_dropped_rows")
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_integrity_dropped_rows": int(
                    _numeric(
                        scenario_runs,
                        "input_integrity_dropped_rows",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_session_filtered_rows": int(
                    _numeric(
                        scenario_runs,
                        "input_session_filtered_rows",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_input_empty_datasets": int(
                    _numeric(scenario_runs, "input_empty_datasets")
                    .fillna(0.0)
                    .sum()
                ),
                "parity_futures_asof_freshness_enabled_runs": int(
                    _bool_series(
                        scenario_runs.get(
                            "parity_futures_asof_freshness_enabled",
                            pd.Series(False, index=scenario_runs.index),
                        )
                    ).sum()
                ),
                "total_parity_futures_join_rows": int(
                    _numeric(scenario_runs, "parity_futures_join_rows")
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_fresh_join_rows": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_fresh_join_rows",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_stale_join_rows": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_stale_join_rows",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_unmatched_join_rows": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_unmatched_join_rows",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_signal_count": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_signal_count",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_signals_without_age": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_signals_without_age",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_parity_futures_signal_age_violations": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_signal_age_violations",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "max_parity_futures_signal_age_ns": int(
                    _numeric(
                        scenario_runs,
                        "parity_futures_max_signal_age_ns",
                    )
                    .fillna(0.0)
                    .max()
                ),
                **_parity_execution_aggregates(scenario_runs),
                "total_pretrade_rejections": int(
                    _numeric(scenario_runs, "pretrade_rejections")
                    .fillna(0.0)
                    .sum()
                ),
                "total_venue_rule_rejections": int(
                    _numeric(scenario_runs, "venue_rule_rejections")
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
                "total_cancel_requests": int(
                    _numeric(scenario_runs, "cancel_requests")
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_effective_events": int(
                    _numeric(scenario_runs, "cancel_effective_events")
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_effective_after_partial_fill_events": int(
                    _numeric(
                        scenario_runs,
                        "cancel_effective_after_partial_fill_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_filled_before_effective_events": int(
                    _numeric(
                        scenario_runs,
                        "cancel_filled_before_effective_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_closed_before_effective_events": int(
                    _numeric(
                        scenario_runs,
                        "cancel_closed_before_effective_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_pending_at_replay_end_events": int(
                    _numeric(
                        scenario_runs,
                        "cancel_pending_at_replay_end_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_inflight_filled_qty": int(
                    _numeric(
                        scenario_runs,
                        "cancel_inflight_filled_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "order_horizon_tracking_enabled_runs": int(
                    _bool_series(
                        scenario_runs.get(
                            "order_horizon_tracking_enabled",
                            pd.Series(False, index=scenario_runs.index),
                        )
                    ).sum()
                ),
                "total_open_orders_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "open_orders_at_replay_end",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_open_order_qty_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "open_order_qty_at_replay_end",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_pending_activation_orders_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "pending_activation_orders_at_replay_end",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_active_ioc_orders_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "active_ioc_orders_at_replay_end",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_active_limit_orders_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "active_limit_orders_at_replay_end",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_cancel_pending_orders_at_replay_end": int(
                    _numeric(
                        scenario_runs,
                        "cancel_pending_orders_at_replay_end",
                    )
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
                "total_limit_orders_sent": int(
                    _numeric(scenario_runs, "limit_orders_sent")
                    .fillna(0.0)
                    .sum()
                ),
                "total_queue_initialization_events": int(
                    _numeric(scenario_runs, "queue_initialization_events")
                    .fillna(0.0)
                    .sum()
                ),
                "total_deferred_queue_initialization_events": int(
                    _numeric(
                        scenario_runs,
                        "deferred_queue_initialization_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_uninitialized_limit_orders": int(
                    _numeric(scenario_runs, "uninitialized_limit_orders")
                    .fillna(0.0)
                    .sum()
                ),
                "max_queue_initialization_lag_ns": int(
                    _numeric(
                        scenario_runs,
                        "max_queue_initialization_lag_ns",
                    )
                    .fillna(0.0)
                    .max()
                ),
                "total_residual_resting_transition_events": int(
                    _numeric(
                        scenario_runs,
                        "residual_resting_transition_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_residual_resting_transition_qty": int(
                    _numeric(
                        scenario_runs,
                        "residual_resting_transition_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_deferred_residual_queue_events": int(
                    _numeric(
                        scenario_runs,
                        "deferred_residual_queue_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_unresolved_residual_queue_events": int(
                    _numeric(
                        scenario_runs,
                        "unresolved_residual_queue_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "max_residual_queue_initialization_lag_ns": int(
                    _numeric(
                        scenario_runs,
                        "max_residual_queue_initialization_lag_ns",
                    )
                    .fillna(0.0)
                    .max()
                ),
                "total_passive_price_through_events": int(
                    _numeric(
                        scenario_runs,
                        "passive_price_through_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_passive_price_through_requested_qty": int(
                    _numeric(
                        scenario_runs,
                        "passive_price_through_requested_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_passive_price_through_filled_qty": int(
                    _numeric(
                        scenario_runs,
                        "passive_price_through_filled_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_passive_price_through_shortfall_qty": int(
                    _numeric(
                        scenario_runs,
                        "passive_price_through_shortfall_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_passive_price_through_incomplete_events": int(
                    _numeric(
                        scenario_runs,
                        "passive_price_through_incomplete_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_liquidation_events": int(
                    _numeric(scenario_runs, "terminal_liquidation_events")
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_liquidation_requested_qty": int(
                    _numeric(
                        scenario_runs,
                        "terminal_liquidation_requested_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_liquidation_filled_qty": int(
                    _numeric(
                        scenario_runs,
                        "terminal_liquidation_filled_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_liquidation_shortfall_qty": int(
                    _numeric(
                        scenario_runs,
                        "terminal_liquidation_shortfall_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_liquidation_incomplete_events": int(
                    _numeric(
                        scenario_runs,
                        "terminal_liquidation_incomplete_events",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_residual_position_qty": int(
                    _numeric(
                        scenario_runs,
                        "terminal_residual_position_qty",
                    )
                    .fillna(0.0)
                    .sum()
                ),
                "total_terminal_residual_instruments": int(
                    _numeric(
                        scenario_runs,
                        "terminal_residual_instruments",
                    )
                    .fillna(0.0)
                    .sum()
                ),
            }
        ]
    )


def _parity_execution_aggregates(
    frame: pd.DataFrame,
) -> dict[str, int | float]:
    enabled = _bool_series(
        frame.get(
            "parity_execution_guard_enabled",
            pd.Series(False, index=frame.index),
        )
    )
    declared = _bool_series(
        frame.get(
            "parity_execution_guard_declared",
            pd.Series(False, index=frame.index),
        )
    )
    preflight_enabled = _bool_series(
        frame.get(
            "parity_execution_ioc_batch_preflight_enabled",
            pd.Series(False, index=frame.index),
        )
    )
    preflight_declared = _bool_series(
        frame.get(
            "parity_execution_ioc_batch_preflight_declared",
            pd.Series(False, index=frame.index),
        )
    )
    guard_present = _bool_series(
        frame.get(
            "parity_execution_guard_present",
            pd.Series(False, index=frame.index),
        )
    )
    legging_present = _bool_series(
        frame.get(
            "parity_execution_legging_present",
            pd.Series(False, index=frame.index),
        )
    )
    sum_columns = {
        "total_parity_execution_guard_attempts": (
            "parity_execution_guard_attempts"
        ),
        "total_parity_execution_guard_passed_attempts": (
            "parity_execution_guard_passed_attempts"
        ),
        "total_parity_execution_guard_deferred_attempts": (
            "parity_execution_guard_deferred_attempts"
        ),
        "total_parity_execution_ioc_batch_preflight_attempts": (
            "parity_execution_ioc_batch_preflight_attempts"
        ),
        "total_parity_execution_ioc_batch_preflight_passed_attempts": (
            "parity_execution_ioc_batch_preflight_passed_attempts"
        ),
        "total_parity_execution_ioc_batch_preflight_rejected_attempts": (
            "parity_execution_ioc_batch_preflight_rejected_attempts"
        ),
        "total_parity_execution_ioc_batch_preflight_missing_evidence_rows": (
            "parity_execution_ioc_batch_preflight_missing_evidence_rows"
        ),
        "total_parity_execution_ioc_batch_preflight_consistency_violations": (
            "parity_execution_ioc_batch_preflight_consistency_violations"
        ),
        "total_parity_execution_ioc_visible_not_marketable_attempts": (
            "parity_execution_ioc_visible_not_marketable_attempts"
        ),
        "total_parity_execution_ioc_visible_capacity_shortfall_attempts": (
            "parity_execution_ioc_visible_capacity_shortfall_attempts"
        ),
        "total_parity_execution_ioc_visible_capacity_missing_evidence_rows": (
            "parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ),
        "total_parity_execution_ioc_visible_capacity_consistency_violations": (
            "parity_execution_ioc_visible_capacity_consistency_violations"
        ),
        "total_parity_execution_guard_missing_evidence_rows": (
            "parity_execution_guard_missing_evidence_rows"
        ),
        "total_parity_execution_guard_unclassified_rows": (
            "parity_execution_guard_unclassified_rows"
        ),
        "total_parity_execution_guard_consistency_violations": (
            "parity_execution_guard_consistency_violations"
        ),
        "total_parity_execution_signal_expiry_events": (
            "parity_execution_signal_expiry_events"
        ),
        "total_parity_execution_stale_book_attempts": (
            "parity_execution_stale_book_attempts"
        ),
        "total_parity_execution_negative_book_age_attempts": (
            "parity_execution_negative_book_age_attempts"
        ),
        "total_parity_execution_skew_attempts": (
            "parity_execution_skew_attempts"
        ),
        "total_parity_execution_routing_complete_attempts": (
            "parity_execution_routing_complete_attempts"
        ),
        "total_parity_execution_routing_incomplete_attempts": (
            "parity_execution_routing_incomplete_attempts"
        ),
        "total_parity_execution_guard_passed_missing_age_rows": (
            "parity_execution_guard_passed_missing_age_rows"
        ),
        "total_parity_execution_guard_age_violations": (
            "parity_execution_guard_age_violations"
        ),
        "total_parity_execution_guard_skew_violations": (
            "parity_execution_guard_skew_violations"
        ),
        "total_parity_execution_count": "parity_execution_count",
        "total_parity_execution_legging_missing_evidence_rows": (
            "parity_execution_legging_missing_evidence_rows"
        ),
        "total_parity_execution_legging_consistency_violations": (
            "parity_execution_legging_consistency_violations"
        ),
        "total_parity_execution_complete_count": (
            "parity_execution_complete_count"
        ),
        "total_parity_execution_incomplete_count": (
            "parity_execution_incomplete_count"
        ),
        "total_parity_execution_route_rejected_legs": (
            "parity_execution_route_rejected_legs"
        ),
        "total_parity_execution_unfilled_legs": (
            "parity_execution_unfilled_legs"
        ),
    }
    totals = {
        output: int(_numeric(frame, column).fillna(0.0).sum())
        for output, column in sum_columns.items()
    }
    return {
        "parity_execution_guard_enabled_runs": int(enabled.sum()),
        "parity_execution_guard_declared_runs": int(declared.sum()),
        "parity_execution_ioc_batch_preflight_enabled_runs": int(
            preflight_enabled.sum()
        ),
        "parity_execution_ioc_batch_preflight_declared_runs": int(
            preflight_declared.sum()
        ),
        "parity_execution_guard_artifact_present_runs": int(
            guard_present.sum()
        ),
        "parity_execution_legging_artifact_present_runs": int(
            legging_present.sum()
        ),
        **totals,
        "max_parity_execution_routed_book_age_ns": _max_int(
            frame,
            "parity_execution_max_routed_book_age_ns",
        ),
        "max_parity_execution_routed_book_skew_ns": _max_int(
            frame,
            "parity_execution_max_routed_book_skew_ns",
        ),
        "min_parity_execution_routed_visible_fill_ratio": (
            _min_routed_visible_fill_ratio(frame)
        ),
    }


def _min_routed_visible_fill_ratio(frame: pd.DataFrame) -> float:
    routed = _numeric(
        frame,
        "parity_execution_guard_passed_attempts",
    ).fillna(0.0).gt(0.0)
    values = _numeric(
        frame,
        "parity_execution_min_routed_visible_fill_ratio",
    ).loc[routed].dropna()
    return float(values.min()) if not values.empty else 0.0


def _max_int(frame: pd.DataFrame, column: str) -> int:
    values = _numeric(frame, column).dropna()
    return int(values.max()) if not values.empty else 0


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
