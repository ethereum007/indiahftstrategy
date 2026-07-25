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
