import pandas as pd

from hft_cli import main
from reports.sweeps import compare_sweeps, write_sweep_comparison


def write_sweep(path, rows):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)


def sweep_rows(day_pnl_a, day_pnl_b, *, b_passed):
    return [
        {
            "run": "trigger_2__feed_0us__order_100us",
            "trigger_ticks": 2.0,
            "feed_latency_us": 0.0,
            "order_latency_us": 100.0,
            "net_pnl": day_pnl_a,
            "fills": 10,
            "proof_passed": True,
            "robust_score": day_pnl_a - 2.0,
            "max_drawdown": 2.0,
            "losing_regimes": 0,
            "worst_regime_equity_change": 3.0,
            "input_quarantine_tracking_enabled": True,
            "input_dataset_count": 1,
            "input_total_rows": 10,
            "input_kept_rows": 9,
            "input_dropped_rows": 1,
            "input_integrity_dropped_rows": 0,
            "input_session_filtered_rows": 1,
            "input_empty_datasets": 0,
            "parity_futures_asof_freshness_enabled": True,
            "parity_futures_join_rows": 2,
            "parity_futures_fresh_join_rows": 2,
            "parity_futures_stale_join_rows": 0,
            "parity_futures_unmatched_join_rows": 0,
            "parity_futures_signal_count": 1,
            "parity_futures_signals_without_age": 0,
            "parity_futures_signal_age_violations": 0,
            "parity_futures_max_signal_age_ns": 20,
            "parity_execution_guard_enabled": True,
            "parity_execution_guard_declared": True,
            "parity_execution_signal_source_causality_enabled": True,
            "parity_execution_signal_source_causality_declared": True,
            "parity_execution_signal_source_checks": 1,
            "parity_execution_signal_source_ready_attempts": 1,
            "parity_execution_signal_source_pending_attempts": 0,
            "parity_execution_signal_source_missing_evidence_rows": 0,
            "parity_execution_signal_source_consistency_violations": 0,
            "parity_execution_max_signal_source_lag_ns": 0,
            "parity_execution_edge_revalidation_enabled": True,
            "parity_execution_edge_revalidation_declared": True,
            "parity_execution_edge_revalidation_attempts": 1,
            "parity_execution_edge_revalidation_passed_attempts": 1,
            "parity_execution_edge_revalidation_rejected_attempts": 0,
            "parity_execution_edge_revalidation_missing_evidence_rows": 0,
            "parity_execution_edge_revalidation_consistency_violations": 0,
            "parity_execution_min_routed_net_edge": 100.0,
            "parity_execution_max_observed_edge_decay": 0.0,
            "parity_execution_realized_edge_enabled": True,
            "parity_execution_realized_edge_declared": True,
            "parity_execution_fills_present": True,
            "parity_execution_realized_edge_evaluable_count": 1,
            "parity_execution_realized_edge_positive_count": 1,
            "parity_execution_realized_edge_nonpositive_count": 0,
            "parity_execution_realized_edge_missing_evidence_rows": 0,
            "parity_execution_realized_edge_consistency_violations": 0,
            "parity_execution_min_realized_net_edge": 90.0,
            "parity_execution_total_realized_net_edge": 90.0,
            "parity_execution_min_realized_vs_decision_net_edge": -10.0,
            "parity_execution_max_fill_span_ns": 20,
            "parity_execution_ioc_batch_preflight_enabled": True,
            "parity_execution_ioc_batch_preflight_declared": True,
            "parity_execution_ioc_batch_preflight_attempts": 1,
            "parity_execution_ioc_batch_preflight_passed_attempts": 1,
            "parity_execution_ioc_batch_preflight_rejected_attempts": 0,
            "parity_execution_ioc_batch_preflight_missing_evidence_rows": 0,
            "parity_execution_ioc_batch_preflight_consistency_violations": 0,
            "parity_execution_ioc_visible_not_marketable_attempts": 0,
            "parity_execution_ioc_visible_capacity_shortfall_attempts": 0,
            "parity_execution_ioc_visible_capacity_missing_evidence_rows": 0,
            "parity_execution_ioc_visible_capacity_consistency_violations": 0,
            "parity_execution_min_routed_visible_fill_ratio": 2.0,
            "parity_execution_guard_present": True,
            "parity_execution_legging_present": True,
            "parity_execution_guard_attempts": 3,
            "parity_execution_guard_passed_attempts": 1,
            "parity_execution_guard_deferred_attempts": 2,
            "parity_execution_guard_missing_evidence_rows": 0,
            "parity_execution_guard_unclassified_rows": 0,
            "parity_execution_guard_consistency_violations": 0,
            "parity_execution_signal_expiry_events": 0,
            "parity_execution_stale_book_attempts": 0,
            "parity_execution_negative_book_age_attempts": 0,
            "parity_execution_skew_attempts": 0,
            "parity_execution_routing_complete_attempts": 1,
            "parity_execution_routing_incomplete_attempts": 0,
            "parity_execution_guard_passed_missing_age_rows": 0,
            "parity_execution_guard_age_violations": 0,
            "parity_execution_guard_skew_violations": 0,
            "parity_execution_max_routed_book_age_ns": 20,
            "parity_execution_max_routed_book_skew_ns": 10,
            "parity_execution_count": 1,
            "parity_execution_legging_missing_evidence_rows": 0,
            "parity_execution_legging_consistency_violations": 0,
            "parity_execution_complete_count": 1,
            "parity_execution_incomplete_count": 0,
            "parity_execution_route_rejected_legs": 0,
            "parity_execution_unfilled_legs": 0,
            "persistent_displayed_liquidity_enabled": True,
            "lot_conserving_fills_enabled": True,
            "causal_event_ordering_enabled": True,
            "order_horizon_tracking_enabled": True,
            "open_orders_at_replay_end": 0,
            "open_order_qty_at_replay_end": 0,
            "pending_activation_orders_at_replay_end": 0,
            "active_ioc_orders_at_replay_end": 0,
            "active_limit_orders_at_replay_end": 0,
            "cancel_pending_orders_at_replay_end": 0,
            "arrival_queue_initialization_enabled": True,
            "limit_orders_sent": 1,
            "queue_initialization_events": 1,
            "deferred_queue_initialization_events": 1,
            "uninitialized_limit_orders": 0,
            "max_queue_initialization_lag_ns": 100_000,
            "residual_resting_transition_events": 1,
            "residual_resting_transition_qty": 25,
            "deferred_residual_queue_events": 1,
            "unresolved_residual_queue_events": 0,
            "max_residual_queue_initialization_lag_ns": 2_000,
            "passive_price_through_depth_constrained_enabled": True,
            "passive_price_through_events": 1,
            "passive_price_through_requested_qty": 75,
            "passive_price_through_filled_qty": 50,
            "passive_price_through_shortfall_qty": 25,
            "passive_price_through_incomplete_events": 1,
            "terminal_liquidation_depth_constrained_enabled": True,
            "terminal_liquidation_events": 1,
            "terminal_liquidation_requested_qty": 75,
            "terminal_liquidation_filled_qty": 75,
            "terminal_liquidation_shortfall_qty": 0,
            "terminal_liquidation_incomplete_events": 0,
            "terminal_residual_position_qty": 0,
            "terminal_residual_instruments": 0,
            "terminal_liquidation_complete": True,
            "carried_depletion_shortfall_events": 1,
            "carried_depletion_shortfall_qty": 25,
        },
        {
            "run": "trigger_3__feed_0us__order_100us",
            "trigger_ticks": 3.0,
            "feed_latency_us": 0.0,
            "order_latency_us": 100.0,
            "net_pnl": day_pnl_b,
            "fills": 8,
            "proof_passed": b_passed,
            "robust_score": day_pnl_b - 4.0,
            "max_drawdown": 4.0,
            "losing_regimes": 1,
            "worst_regime_equity_change": -1.0,
            "input_quarantine_tracking_enabled": True,
            "input_dataset_count": 1,
            "input_total_rows": 10,
            "input_kept_rows": 9,
            "input_dropped_rows": 1,
            "input_integrity_dropped_rows": 1,
            "input_session_filtered_rows": 0,
            "input_empty_datasets": 0,
            "parity_futures_asof_freshness_enabled": True,
            "parity_futures_join_rows": 2,
            "parity_futures_fresh_join_rows": 1,
            "parity_futures_stale_join_rows": 1,
            "parity_futures_unmatched_join_rows": 0,
            "parity_futures_signal_count": 1,
            "parity_futures_signals_without_age": 0,
            "parity_futures_signal_age_violations": 1,
            "parity_futures_max_signal_age_ns": 150,
            "parity_execution_guard_enabled": True,
            "parity_execution_guard_declared": True,
            "parity_execution_signal_source_causality_enabled": True,
            "parity_execution_signal_source_causality_declared": True,
            "parity_execution_signal_source_checks": 1,
            "parity_execution_signal_source_ready_attempts": 0,
            "parity_execution_signal_source_pending_attempts": 1,
            "parity_execution_signal_source_missing_evidence_rows": 1,
            "parity_execution_signal_source_consistency_violations": 1,
            "parity_execution_max_signal_source_lag_ns": 100,
            "parity_execution_edge_revalidation_enabled": True,
            "parity_execution_edge_revalidation_declared": True,
            "parity_execution_edge_revalidation_attempts": 1,
            "parity_execution_edge_revalidation_passed_attempts": 1,
            "parity_execution_edge_revalidation_rejected_attempts": 0,
            "parity_execution_edge_revalidation_missing_evidence_rows": 1,
            "parity_execution_edge_revalidation_consistency_violations": 1,
            "parity_execution_min_routed_net_edge": 0.5,
            "parity_execution_max_observed_edge_decay": 100.0,
            "parity_execution_realized_edge_enabled": True,
            "parity_execution_realized_edge_declared": True,
            "parity_execution_fills_present": True,
            "parity_execution_realized_edge_evaluable_count": 0,
            "parity_execution_realized_edge_positive_count": 0,
            "parity_execution_realized_edge_nonpositive_count": 0,
            "parity_execution_realized_edge_missing_evidence_rows": 1,
            "parity_execution_realized_edge_consistency_violations": 1,
            "parity_execution_min_realized_net_edge": 0.0,
            "parity_execution_total_realized_net_edge": 0.0,
            "parity_execution_min_realized_vs_decision_net_edge": 0.0,
            "parity_execution_max_fill_span_ns": 100,
            "parity_execution_ioc_batch_preflight_enabled": True,
            "parity_execution_ioc_batch_preflight_declared": True,
            "parity_execution_ioc_batch_preflight_attempts": 1,
            "parity_execution_ioc_batch_preflight_passed_attempts": 0,
            "parity_execution_ioc_batch_preflight_rejected_attempts": 1,
            "parity_execution_ioc_batch_preflight_missing_evidence_rows": 1,
            "parity_execution_ioc_batch_preflight_consistency_violations": 1,
            "parity_execution_ioc_visible_not_marketable_attempts": 0,
            "parity_execution_ioc_visible_capacity_shortfall_attempts": 1,
            "parity_execution_ioc_visible_capacity_missing_evidence_rows": 1,
            "parity_execution_ioc_visible_capacity_consistency_violations": 1,
            "parity_execution_min_routed_visible_fill_ratio": 0.5,
            "parity_execution_guard_present": True,
            "parity_execution_legging_present": True,
            "parity_execution_guard_attempts": 4,
            "parity_execution_guard_passed_attempts": 1,
            "parity_execution_guard_deferred_attempts": 3,
            "parity_execution_guard_missing_evidence_rows": 1,
            "parity_execution_guard_unclassified_rows": 1,
            "parity_execution_guard_consistency_violations": 1,
            "parity_execution_signal_expiry_events": 1,
            "parity_execution_stale_book_attempts": 1,
            "parity_execution_negative_book_age_attempts": 1,
            "parity_execution_skew_attempts": 1,
            "parity_execution_routing_complete_attempts": 0,
            "parity_execution_routing_incomplete_attempts": 1,
            "parity_execution_guard_passed_missing_age_rows": 1,
            "parity_execution_guard_age_violations": 1,
            "parity_execution_guard_skew_violations": 1,
            "parity_execution_max_routed_book_age_ns": 150,
            "parity_execution_max_routed_book_skew_ns": 60,
            "parity_execution_count": 1,
            "parity_execution_legging_missing_evidence_rows": 1,
            "parity_execution_legging_consistency_violations": 1,
            "parity_execution_complete_count": 0,
            "parity_execution_incomplete_count": 1,
            "parity_execution_route_rejected_legs": 1,
            "parity_execution_unfilled_legs": 1,
            "persistent_displayed_liquidity_enabled": True,
            "lot_conserving_fills_enabled": True,
            "causal_event_ordering_enabled": True,
            "order_horizon_tracking_enabled": True,
            "open_orders_at_replay_end": 1,
            "open_order_qty_at_replay_end": 75,
            "pending_activation_orders_at_replay_end": 0,
            "active_ioc_orders_at_replay_end": 1,
            "active_limit_orders_at_replay_end": 0,
            "cancel_pending_orders_at_replay_end": 0,
            "arrival_queue_initialization_enabled": True,
            "limit_orders_sent": 1,
            "queue_initialization_events": 1,
            "deferred_queue_initialization_events": 1,
            "uninitialized_limit_orders": 0,
            "max_queue_initialization_lag_ns": 100_000,
            "residual_resting_transition_events": 1,
            "residual_resting_transition_qty": 25,
            "deferred_residual_queue_events": 1,
            "unresolved_residual_queue_events": 0,
            "max_residual_queue_initialization_lag_ns": 2_000,
            "passive_price_through_depth_constrained_enabled": True,
            "passive_price_through_events": 1,
            "passive_price_through_requested_qty": 75,
            "passive_price_through_filled_qty": 50,
            "passive_price_through_shortfall_qty": 25,
            "passive_price_through_incomplete_events": 1,
            "terminal_liquidation_depth_constrained_enabled": True,
            "terminal_liquidation_events": 1,
            "terminal_liquidation_requested_qty": 75,
            "terminal_liquidation_filled_qty": 75,
            "terminal_liquidation_shortfall_qty": 0,
            "terminal_liquidation_incomplete_events": 0,
            "terminal_residual_position_qty": 0,
            "terminal_residual_instruments": 0,
            "terminal_liquidation_complete": True,
            "carried_depletion_shortfall_events": 1,
            "carried_depletion_shortfall_qty": 25,
        },
    ]


def test_compare_sweeps_ranks_consistent_scenario_across_days(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    write_sweep(day1, sweep_rows(10.0, 4.0, b_passed=False))
    write_sweep(day2, sweep_rows(12.0, 6.0, b_passed=True))

    comparison = compare_sweeps(
        [day1, day2],
        labels=["2026-06-10", "2026-06-11"],
        min_pass_rate=1.0,
        min_sweeps=2,
        min_median_net_pnl=8.0,
    )

    best = comparison.scenario_scores.iloc[0]
    weak = comparison.scenario_scores.loc[comparison.scenario_scores["trigger_ticks"] == 3.0].iloc[0]

    assert comparison.has_selection
    assert best["trigger_ticks"] == 2.0
    assert best["sweeps_seen"] == 2
    assert best["pass_rate"] == 1.0
    assert best["median_net_pnl"] == 11.0
    assert bool(best["selection_passed"])
    assert weak["pass_rate"] == 0.5
    assert not bool(weak["selection_passed"])
    assert comparison.summary.iloc[0]["selectable_scenarios"] == 1
    assert int(best["total_pretrade_rejections"]) == 0
    assert int(best["total_venue_rule_rejections"]) == 0
    assert int(best["total_position_risk_rejections"]) == 0
    assert int(best["total_self_cross_rejections"]) == 0
    assert int(best["input_quarantine_tracking_enabled_runs"]) == 2
    assert int(best["total_input_datasets"]) == 2
    assert int(best["total_input_rows"]) == 20
    assert int(best["total_input_kept_rows"]) == 18
    assert int(best["total_input_dropped_rows"]) == 2
    assert int(best["total_input_integrity_dropped_rows"]) == 0
    assert int(best["total_input_session_filtered_rows"]) == 2
    assert int(best["total_input_empty_datasets"]) == 0
    assert int(weak["total_input_integrity_dropped_rows"]) == 2
    assert int(best["parity_futures_asof_freshness_enabled_runs"]) == 2
    assert int(best["total_parity_futures_join_rows"]) == 4
    assert int(best["total_parity_futures_fresh_join_rows"]) == 4
    assert int(best["total_parity_futures_stale_join_rows"]) == 0
    assert int(best["total_parity_futures_unmatched_join_rows"]) == 0
    assert int(best["total_parity_futures_signal_count"]) == 2
    assert int(best["total_parity_futures_signals_without_age"]) == 0
    assert int(best["total_parity_futures_signal_age_violations"]) == 0
    assert int(best["max_parity_futures_signal_age_ns"]) == 20
    assert int(weak["total_parity_futures_stale_join_rows"]) == 2
    assert int(weak["total_parity_futures_signal_age_violations"]) == 2
    assert int(weak["max_parity_futures_signal_age_ns"]) == 150
    assert int(best["parity_execution_guard_enabled_runs"]) == 2
    assert int(best["parity_execution_guard_declared_runs"]) == 2
    assert int(
        best["parity_execution_edge_revalidation_enabled_runs"]
    ) == 2
    assert int(
        best[
            "parity_execution_signal_source_causality_enabled_runs"
        ]
    ) == 2
    assert int(
        best[
            "parity_execution_signal_source_causality_declared_runs"
        ]
    ) == 2
    assert int(
        best["parity_execution_edge_revalidation_declared_runs"]
    ) == 2
    assert int(
        best["parity_execution_realized_edge_enabled_runs"]
    ) == 2
    assert int(
        best["parity_execution_realized_edge_declared_runs"]
    ) == 2
    assert int(
        best["parity_execution_ioc_batch_preflight_enabled_runs"]
    ) == 2
    assert int(
        best["parity_execution_ioc_batch_preflight_declared_runs"]
    ) == 2
    assert int(best["parity_execution_guard_artifact_present_runs"]) == 2
    assert int(best["parity_execution_legging_artifact_present_runs"]) == 2
    assert int(best["parity_execution_fills_artifact_present_runs"]) == 2
    assert int(best["total_parity_execution_guard_attempts"]) == 6
    assert int(best["total_parity_execution_guard_passed_attempts"]) == 2
    assert int(best["total_parity_execution_guard_deferred_attempts"]) == 4
    assert int(
        best["total_parity_execution_edge_revalidation_attempts"]
    ) == 2
    assert int(
        best["total_parity_execution_signal_source_checks"]
    ) == 2
    assert int(
        best["total_parity_execution_signal_source_ready_attempts"]
    ) == 2
    assert int(
        best["total_parity_execution_signal_source_pending_attempts"]
    ) == 0
    assert int(
        best[
            "total_parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        best[
            "total_parity_execution_signal_source_consistency_violations"
        ]
    ) == 0
    assert int(
        best["max_parity_execution_signal_source_lag_ns"]
    ) == 0
    assert int(
        best["total_parity_execution_edge_revalidation_passed_attempts"]
    ) == 2
    assert int(
        best["total_parity_execution_edge_revalidation_rejected_attempts"]
    ) == 0
    assert int(
        best[
            "total_parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        best[
            "total_parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 0
    assert float(
        best["min_parity_execution_routed_net_edge"]
    ) == 100.0
    assert float(
        best["max_parity_execution_observed_edge_decay"]
    ) == 0.0
    assert int(
        best["total_parity_execution_realized_edge_evaluable_count"]
    ) == 2
    assert int(
        best["total_parity_execution_realized_edge_positive_count"]
    ) == 2
    assert int(
        best["total_parity_execution_realized_edge_nonpositive_count"]
    ) == 0
    assert int(
        best[
            "total_parity_execution_realized_edge_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        best[
            "total_parity_execution_realized_edge_consistency_violations"
        ]
    ) == 0
    assert float(
        best["total_parity_execution_realized_net_edge"]
    ) == 180.0
    assert float(
        best["min_parity_execution_realized_net_edge"]
    ) == 90.0
    assert float(
        best[
            "min_parity_execution_realized_vs_decision_net_edge"
        ]
    ) == -10.0
    assert int(best["max_parity_execution_fill_span_ns"]) == 20
    assert int(
        best["total_parity_execution_ioc_batch_preflight_attempts"]
    ) == 2
    assert int(
        best[
            "total_parity_execution_ioc_batch_preflight_passed_attempts"
        ]
    ) == 2
    assert int(
        best[
            "total_parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 0
    assert int(
        best["total_parity_execution_ioc_visible_not_marketable_attempts"]
    ) == 0
    assert int(
        best["total_parity_execution_ioc_visible_capacity_shortfall_attempts"]
    ) == 0
    assert int(
        best[
            "total_parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        best[
            "total_parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 0
    assert float(
        best["min_parity_execution_routed_visible_fill_ratio"]
    ) == 2.0
    assert int(best["total_parity_execution_routing_complete_attempts"]) == 2
    assert int(best["total_parity_execution_complete_count"]) == 2
    assert int(best["total_parity_execution_incomplete_count"]) == 0
    assert int(best["max_parity_execution_routed_book_age_ns"]) == 20
    assert int(best["max_parity_execution_routed_book_skew_ns"]) == 10
    assert int(weak["total_parity_execution_guard_unclassified_rows"]) == 2
    assert int(
        weak["total_parity_execution_guard_missing_evidence_rows"]
    ) == 2
    assert int(
        weak["total_parity_execution_guard_consistency_violations"]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        weak["total_parity_execution_signal_source_pending_attempts"]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_signal_source_consistency_violations"
        ]
    ) == 2
    assert int(
        weak["max_parity_execution_signal_source_lag_ns"]
    ) == 100
    assert int(
        weak[
            "total_parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 2
    assert float(
        weak["min_parity_execution_routed_net_edge"]
    ) == 0.5
    assert float(
        weak["max_parity_execution_observed_edge_decay"]
    ) == 100.0
    assert int(
        weak["total_parity_execution_realized_edge_evaluable_count"]
    ) == 0
    assert int(
        weak[
            "total_parity_execution_realized_edge_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_realized_edge_consistency_violations"
        ]
    ) == 2
    assert float(
        weak["total_parity_execution_realized_net_edge"]
    ) == 0.0
    assert float(
        weak["min_parity_execution_realized_net_edge"]
    ) == 0.0
    assert int(weak["max_parity_execution_fill_span_ns"]) == 100
    assert int(
        weak[
            "total_parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_ioc_batch_preflight_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_ioc_batch_preflight_consistency_violations"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_ioc_visible_capacity_shortfall_attempts"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        weak[
            "total_parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 2
    assert float(
        weak["min_parity_execution_routed_visible_fill_ratio"]
    ) == 0.5
    assert int(weak["total_parity_execution_signal_expiry_events"]) == 2
    assert int(weak["total_parity_execution_stale_book_attempts"]) == 2
    assert int(
        weak["total_parity_execution_negative_book_age_attempts"]
    ) == 2
    assert int(weak["total_parity_execution_skew_attempts"]) == 2
    assert int(
        weak["total_parity_execution_routing_incomplete_attempts"]
    ) == 2
    assert int(weak["total_parity_execution_guard_age_violations"]) == 2
    assert int(weak["total_parity_execution_guard_skew_violations"]) == 2
    assert int(weak["total_parity_execution_incomplete_count"]) == 2
    assert int(
        weak["total_parity_execution_legging_missing_evidence_rows"]
    ) == 2
    assert int(
        weak["total_parity_execution_legging_consistency_violations"]
    ) == 2
    assert int(weak["total_parity_execution_route_rejected_legs"]) == 2
    assert int(weak["total_parity_execution_unfilled_legs"]) == 2
    assert int(weak["max_parity_execution_routed_book_age_ns"]) == 150
    assert int(weak["max_parity_execution_routed_book_skew_ns"]) == 60
    assert int(best["order_horizon_tracking_enabled_runs"]) == 2
    assert int(best["total_open_orders_at_replay_end"]) == 0
    assert int(best["total_open_order_qty_at_replay_end"]) == 0
    assert int(weak["total_open_orders_at_replay_end"]) == 2
    assert int(weak["total_open_order_qty_at_replay_end"]) == 150
    assert int(weak["total_active_ioc_orders_at_replay_end"]) == 2
    assert int(best["total_carried_depletion_shortfall_events"]) == 2
    assert int(best["total_carried_depletion_shortfall_qty"]) == 50
    assert int(best["total_limit_orders_sent"]) == 2
    assert int(best["total_queue_initialization_events"]) == 2
    assert int(best["total_deferred_queue_initialization_events"]) == 2
    assert int(best["total_uninitialized_limit_orders"]) == 0
    assert int(best["max_queue_initialization_lag_ns"]) == 100_000
    assert int(best["total_residual_resting_transition_events"]) == 2
    assert int(best["total_residual_resting_transition_qty"]) == 50
    assert int(best["total_deferred_residual_queue_events"]) == 2
    assert int(best["total_unresolved_residual_queue_events"]) == 0
    assert int(best["max_residual_queue_initialization_lag_ns"]) == 2_000
    assert int(best["total_passive_price_through_events"]) == 2
    assert int(best["total_passive_price_through_requested_qty"]) == 150
    assert int(best["total_passive_price_through_filled_qty"]) == 100
    assert int(best["total_passive_price_through_shortfall_qty"]) == 50
    assert int(best["total_passive_price_through_incomplete_events"]) == 2
    assert int(best["total_terminal_liquidation_events"]) == 2
    assert int(best["total_terminal_liquidation_requested_qty"]) == 150
    assert int(best["total_terminal_liquidation_filled_qty"]) == 150
    assert int(best["total_terminal_liquidation_shortfall_qty"]) == 0
    assert int(best["total_terminal_residual_position_qty"]) == 0
    assert int(comparison.summary.iloc[0]["total_pretrade_rejections"]) == 0
    assert int(
        comparison.summary.iloc[0]["total_venue_rule_rejections"]
    ) == 0
    assert int(
        comparison.summary.iloc[0][
            "input_quarantine_tracking_enabled_runs"
        ]
    ) == 4
    assert int(comparison.summary.iloc[0]["total_input_datasets"]) == 4
    assert int(comparison.summary.iloc[0]["total_input_rows"]) == 40
    assert int(comparison.summary.iloc[0]["total_input_kept_rows"]) == 36
    assert int(comparison.summary.iloc[0]["total_input_dropped_rows"]) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_input_integrity_dropped_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_input_session_filtered_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0]["total_input_empty_datasets"]
    ) == 0
    assert int(
        comparison.summary.iloc[0][
            "parity_futures_asof_freshness_enabled_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0]["total_parity_futures_join_rows"]
    ) == 8
    assert int(
        comparison.summary.iloc[0][
            "total_parity_futures_fresh_join_rows"
        ]
    ) == 6
    assert int(
        comparison.summary.iloc[0][
            "total_parity_futures_stale_join_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_futures_signal_age_violations"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "max_parity_futures_signal_age_ns"
        ]
    ) == 150
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_guard_enabled_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_guard_declared_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_edge_revalidation_enabled_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_signal_source_causality_enabled_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_signal_source_causality_declared_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_edge_revalidation_declared_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_ioc_batch_preflight_enabled_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_ioc_batch_preflight_declared_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "parity_execution_guard_artifact_present_runs"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_guard_attempts"
        ]
    ) == 14
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_guard_passed_attempts"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_guard_deferred_attempts"
        ]
    ) == 10
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_edge_revalidation_attempts"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_signal_source_checks"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_signal_source_ready_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_signal_source_pending_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_signal_source_consistency_violations"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "max_parity_execution_signal_source_lag_ns"
        ]
    ) == 100
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_edge_revalidation_passed_attempts"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 2
    assert float(
        comparison.summary.iloc[0][
            "min_parity_execution_routed_net_edge"
        ]
    ) == 0.5
    assert float(
        comparison.summary.iloc[0][
            "max_parity_execution_observed_edge_decay"
        ]
    ) == 100.0
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_attempts"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_passed_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_shortfall_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 2
    assert float(
        comparison.summary.iloc[0][
            "min_parity_execution_routed_visible_fill_ratio"
        ]
    ) == 0.5
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_routing_incomplete_attempts"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_complete_count"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "total_parity_execution_incomplete_count"
        ]
    ) == 2
    assert int(
        comparison.summary.iloc[0][
            "max_parity_execution_routed_book_age_ns"
        ]
    ) == 150
    assert int(
        comparison.summary.iloc[0][
            "max_parity_execution_routed_book_skew_ns"
        ]
    ) == 60
    assert int(
        comparison.summary.iloc[0]["order_horizon_tracking_enabled_runs"]
    ) == 4
    assert int(
        comparison.summary.iloc[0]["total_open_orders_at_replay_end"]
    ) == 2
    assert int(
        comparison.summary.iloc[0]["total_open_order_qty_at_replay_end"]
    ) == 150
    assert int(
        comparison.summary.iloc[0]["total_active_ioc_orders_at_replay_end"]
    ) == 2
    assert int(
        comparison.summary.iloc[0]["total_carried_depletion_shortfall_events"]
    ) == 4
    assert int(comparison.summary.iloc[0]["total_carried_depletion_shortfall_qty"]) == 100
    assert int(comparison.summary.iloc[0]["total_limit_orders_sent"]) == 4
    assert int(
        comparison.summary.iloc[0]["total_queue_initialization_events"]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_deferred_queue_initialization_events"
        ]
    ) == 4
    assert int(comparison.summary.iloc[0]["total_uninitialized_limit_orders"]) == 0
    assert int(comparison.summary.iloc[0]["max_queue_initialization_lag_ns"]) == 100_000
    assert int(
        comparison.summary.iloc[0][
            "total_residual_resting_transition_events"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0]["total_residual_resting_transition_qty"]
    ) == 100
    assert int(
        comparison.summary.iloc[0]["total_deferred_residual_queue_events"]
    ) == 4
    assert int(
        comparison.summary.iloc[0]["total_unresolved_residual_queue_events"]
    ) == 0
    assert int(
        comparison.summary.iloc[0][
            "max_residual_queue_initialization_lag_ns"
        ]
    ) == 2_000
    assert int(
        comparison.summary.iloc[0]["total_passive_price_through_events"]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_passive_price_through_requested_qty"
        ]
    ) == 300
    assert int(
        comparison.summary.iloc[0]["total_passive_price_through_filled_qty"]
    ) == 200
    assert int(
        comparison.summary.iloc[0][
            "total_passive_price_through_shortfall_qty"
        ]
    ) == 100
    assert int(
        comparison.summary.iloc[0][
            "total_passive_price_through_incomplete_events"
        ]
    ) == 4
    assert int(
        comparison.summary.iloc[0]["total_terminal_liquidation_events"]
    ) == 4
    assert int(
        comparison.summary.iloc[0][
            "total_terminal_liquidation_requested_qty"
        ]
    ) == 300
    assert int(
        comparison.summary.iloc[0][
            "total_terminal_liquidation_filled_qty"
        ]
    ) == 300
    assert int(
        comparison.summary.iloc[0][
            "total_terminal_liquidation_shortfall_qty"
        ]
    ) == 0


def test_write_sweep_comparison_outputs_selection_artifacts(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "selection"
    write_sweep(day1, sweep_rows(10.0, 4.0, b_passed=False))
    write_sweep(day2, sweep_rows(12.0, 6.0, b_passed=True))

    comparison = write_sweep_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        group_cols=["trigger_ticks", "feed_latency_us", "order_latency_us"],
        min_pass_rate=1.0,
        min_sweeps=2,
        min_median_net_pnl=8.0,
    )

    assert comparison.output_dir == out_dir
    assert (out_dir / "scenario_runs.csv").exists()
    assert (out_dir / "scenario_scores.csv").exists()
    assert (out_dir / "selection_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_compare_sweeps_can_fail_on_no_selection(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "cli_selection"
    write_sweep(day1, sweep_rows(10.0, 4.0, b_passed=False))
    write_sweep(day2, sweep_rows(12.0, 6.0, b_passed=True))

    code = main(
        [
            "compare-sweeps",
            "--sweeps",
            str(day1),
            str(day2),
            "--out",
            str(out_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--min-pass-rate",
            "1",
            "--min-sweeps",
            "2",
            "--min-median-net-pnl",
            "20",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "scenario_scores.csv").exists()
    assert (out_dir / "selection_summary.csv").exists()
