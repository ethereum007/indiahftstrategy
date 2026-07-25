import json

import pandas as pd

from hft_cli import main
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.proof import (
    ProofThresholds,
    _parity_ioc_event_depth_metrics,
    evaluate_replay_dirs,
    verify_proof_report,
    write_proof_report,
)
from tests.data_readiness_helpers import reseal_experiment_manifest


def write_run(
    path,
    *,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    net_pnl=120.0,
    fills=12,
    turnover=6000.0,
    total_costs=6.0,
    maker_share=0.75,
    otr=3.0,
    otr_breached=False,
    equity_values=(0.0, 80.0, 65.0, 150.0),
    regime_changes=(50.0, 70.0),
    spread_net=40.0,
    markouts=(10.0, -2.0, 4.0),
):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "strategy": strategy,
                "market": market,
                "scenario_key": f"strategy={strategy}|market={market}|trigger_ticks=2",
                "net_pnl": net_pnl,
                "total_costs": total_costs,
                "orders_sent": 20,
                "fills": fills,
                "order_to_trade_ratio": otr,
                "otr_limit": 50.0,
                "otr_breached": otr_breached,
                "input_quarantine_tracking_enabled": True,
                "input_dataset_count": 1,
                "input_total_rows": 20,
                "input_kept_rows": 18,
                "input_dropped_rows": 2,
                "input_integrity_dropped_rows": 0,
                "input_session_filtered_rows": 2,
                "input_empty_datasets": 0,
                "pending_order_risk_reservation_enabled": True,
                "aggressive_self_cross_prevention_enabled": True,
                "venue_order_validation_enabled": True,
                "shared_event_liquidity_enabled": True,
                "persistent_displayed_liquidity_enabled": True,
                "lot_conserving_fills_enabled": True,
                "causal_event_ordering_enabled": True,
                "cancel_lifecycle_tracking_enabled": True,
                "cancel_requests": 3,
                "cancel_effective_events": 2,
                "cancel_effective_after_partial_fill_events": 1,
                "cancel_filled_before_effective_events": 1,
                "cancel_closed_before_effective_events": 0,
                "cancel_pending_at_replay_end_events": 0,
                "cancel_inflight_filled_qty": 75,
                "order_horizon_tracking_enabled": True,
                "open_orders_at_replay_end": 0,
                "open_order_qty_at_replay_end": 0,
                "pending_activation_orders_at_replay_end": 0,
                "active_ioc_orders_at_replay_end": 0,
                "active_limit_orders_at_replay_end": 0,
                "cancel_pending_orders_at_replay_end": 0,
                "arrival_queue_initialization_enabled": True,
                "limit_orders_sent": 4,
                "queue_initialization_events": 4,
                "deferred_queue_initialization_events": 3,
                "uninitialized_limit_orders": 0,
                "max_queue_initialization_lag_ns": 125_000,
                "residual_resting_transition_events": 2,
                "residual_resting_transition_qty": 50,
                "deferred_residual_queue_events": 1,
                "unresolved_residual_queue_events": 0,
                "max_residual_queue_initialization_lag_ns": 2_000,
                "passive_price_through_depth_constrained_enabled": True,
                "passive_price_through_events": 3,
                "passive_price_through_requested_qty": 225,
                "passive_price_through_filled_qty": 150,
                "passive_price_through_shortfall_qty": 75,
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
                "liquidity_shortfall_events": 2,
                "liquidity_shortfall_qty": 75,
                "displayed_liquidity_shortfall_events": 1,
                "displayed_liquidity_shortfall_qty": 50,
                "trade_print_shortfall_events": 1,
                "trade_print_shortfall_qty": 25,
                "carried_depletion_shortfall_events": 1,
                "carried_depletion_shortfall_qty": 50,
                "pretrade_rejections": 0,
                "venue_rule_rejections": 0,
                "position_risk_rejections": 0,
                "self_cross_rejections": 0,
                "turnover": turnover,
                "maker_share": maker_share,
                "portfolio_delta": 0.0,
                "portfolio_vega": 0.0,
            }
        ]
    ).to_csv(path / "summary.csv", index=False)
    pd.DataFrame(
        [{"ts": idx, "equity": value} for idx, value in enumerate(equity_values)]
    ).to_csv(path / "equity.csv", index=False)
    pd.DataFrame(
        [{"regime": f"r{idx}", "equity_change": value} for idx, value in enumerate(regime_changes)]
    ).to_csv(path / "equity_by_regime.csv", index=False)
    pd.DataFrame([{"instrument_id": "OPT", "net_spread": spread_net}]).to_csv(
        path / "spread_summary.csv",
        index=False,
    )
    pd.DataFrame([{"horizon_ns": 100, "markout": value} for value in markouts]).to_csv(
        path / "markouts.csv",
        index=False,
    )
    source = path.parent / f"{path.name}_source.csv"
    source.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    write_experiment_manifest(
        path,
        run_type="unit_replay",
        inputs={"source": source},
    )
    return source


def test_evaluate_replay_dirs_passes_explicit_proof_thresholds(tmp_path):
    run_dir = tmp_path / "leadlag_pass"
    write_run(run_dir)

    report = evaluate_replay_dirs(
        [run_dir],
        thresholds=ProofThresholds(
            min_net_pnl=50.0,
            min_fills=5,
            max_drawdown=20.0,
            max_otr=10.0,
            min_maker_share=0.5,
            min_worst_regime_equity_change=0.0,
            min_markout_mean=0.0,
            min_spread_net=10.0,
        ),
    )

    assert report.passed
    assert report.metrics.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.metrics.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.metrics.iloc[0]["max_drawdown"] == 15.0
    assert report.metrics.iloc[0]["worst_regime_equity_change"] == 50.0
    assert report.metrics.iloc[0]["markout_mean"] == 4.0
    assert bool(
        report.metrics.iloc[0]["pending_order_risk_reservation_enabled"]
    )
    assert bool(
        report.metrics.iloc[0]["aggressive_self_cross_prevention_enabled"]
    )
    assert bool(report.metrics.iloc[0]["venue_order_validation_enabled"])
    assert bool(report.metrics.iloc[0]["shared_event_liquidity_enabled"])
    assert bool(
        report.metrics.iloc[0]["persistent_displayed_liquidity_enabled"]
    )
    assert bool(report.metrics.iloc[0]["lot_conserving_fills_enabled"])
    assert bool(report.metrics.iloc[0]["causal_event_ordering_enabled"])
    assert bool(report.metrics.iloc[0]["cancel_lifecycle_tracking_enabled"])
    assert int(report.metrics.iloc[0]["cancel_requests"]) == 3
    assert int(report.metrics.iloc[0]["cancel_effective_events"]) == 2
    assert int(
        report.metrics.iloc[0][
            "cancel_effective_after_partial_fill_events"
        ]
    ) == 1
    assert int(
        report.metrics.iloc[0]["cancel_filled_before_effective_events"]
    ) == 1
    assert int(
        report.metrics.iloc[0]["cancel_pending_at_replay_end_events"]
    ) == 0
    assert int(report.metrics.iloc[0]["cancel_inflight_filled_qty"]) == 75
    assert bool(
        report.metrics.iloc[0]["input_quarantine_tracking_enabled"]
    )
    assert int(report.metrics.iloc[0]["input_dataset_count"]) == 1
    assert int(report.metrics.iloc[0]["input_total_rows"]) == 20
    assert int(report.metrics.iloc[0]["input_kept_rows"]) == 18
    assert int(report.metrics.iloc[0]["input_dropped_rows"]) == 2
    assert int(
        report.metrics.iloc[0]["input_integrity_dropped_rows"]
    ) == 0
    assert int(
        report.metrics.iloc[0]["input_session_filtered_rows"]
    ) == 2
    assert int(report.metrics.iloc[0]["input_empty_datasets"]) == 0
    assert bool(report.metrics.iloc[0]["order_horizon_tracking_enabled"])
    assert int(report.metrics.iloc[0]["open_orders_at_replay_end"]) == 0
    assert int(report.metrics.iloc[0]["open_order_qty_at_replay_end"]) == 0
    assert int(
        report.metrics.iloc[0]["pending_activation_orders_at_replay_end"]
    ) == 0
    assert int(report.metrics.iloc[0]["active_ioc_orders_at_replay_end"]) == 0
    assert int(
        report.metrics.iloc[0]["active_limit_orders_at_replay_end"]
    ) == 0
    assert int(
        report.metrics.iloc[0]["cancel_pending_orders_at_replay_end"]
    ) == 0
    assert bool(report.metrics.iloc[0]["arrival_queue_initialization_enabled"])
    assert int(report.metrics.iloc[0]["limit_orders_sent"]) == 4
    assert int(report.metrics.iloc[0]["queue_initialization_events"]) == 4
    assert int(
        report.metrics.iloc[0]["deferred_queue_initialization_events"]
    ) == 3
    assert int(report.metrics.iloc[0]["uninitialized_limit_orders"]) == 0
    assert int(report.metrics.iloc[0]["max_queue_initialization_lag_ns"]) == 125_000
    assert int(
        report.metrics.iloc[0]["residual_resting_transition_events"]
    ) == 2
    assert int(report.metrics.iloc[0]["residual_resting_transition_qty"]) == 50
    assert int(report.metrics.iloc[0]["deferred_residual_queue_events"]) == 1
    assert int(report.metrics.iloc[0]["unresolved_residual_queue_events"]) == 0
    assert int(
        report.metrics.iloc[0]["max_residual_queue_initialization_lag_ns"]
    ) == 2_000
    assert bool(
        report.metrics.iloc[0][
            "passive_price_through_depth_constrained_enabled"
        ]
    )
    assert int(report.metrics.iloc[0]["passive_price_through_events"]) == 3
    assert int(
        report.metrics.iloc[0]["passive_price_through_requested_qty"]
    ) == 225
    assert int(
        report.metrics.iloc[0]["passive_price_through_filled_qty"]
    ) == 150
    assert int(
        report.metrics.iloc[0]["passive_price_through_shortfall_qty"]
    ) == 75
    assert int(
        report.metrics.iloc[0]["passive_price_through_incomplete_events"]
    ) == 1
    assert bool(
        report.metrics.iloc[0][
            "terminal_liquidation_depth_constrained_enabled"
        ]
    )
    assert int(report.metrics.iloc[0]["terminal_liquidation_events"]) == 1
    assert int(
        report.metrics.iloc[0]["terminal_liquidation_requested_qty"]
    ) == 75
    assert int(report.metrics.iloc[0]["terminal_liquidation_filled_qty"]) == 75
    assert int(
        report.metrics.iloc[0]["terminal_liquidation_shortfall_qty"]
    ) == 0
    assert bool(report.metrics.iloc[0]["terminal_liquidation_complete"])
    assert int(report.metrics.iloc[0]["liquidity_shortfall_events"]) == 2
    assert int(report.metrics.iloc[0]["liquidity_shortfall_qty"]) == 75
    assert int(report.metrics.iloc[0]["carried_depletion_shortfall_events"]) == 1
    assert int(report.metrics.iloc[0]["carried_depletion_shortfall_qty"]) == 50
    assert int(report.metrics.iloc[0]["pretrade_rejections"]) == 0
    assert int(report.metrics.iloc[0]["venue_rule_rejections"]) == 0
    assert report.checks["passed"].all()


def test_proof_report_rejects_incomplete_terminal_liquidation(tmp_path):
    run_dir = tmp_path / "residual_inventory"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "terminal_liquidation_filled_qty"] = 25
    summary.loc[0, "terminal_liquidation_shortfall_qty"] = 50
    summary.loc[0, "terminal_liquidation_incomplete_events"] = 1
    summary.loc[0, "terminal_residual_position_qty"] = 50
    summary.loc[0, "terminal_residual_instruments"] = 1
    summary.loc[0, "terminal_liquidation_complete"] = False
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == ["terminal_liquidation_complete"]
    assert failed.iloc[0]["reason"] == (
        "terminal liquidation left residual inventory"
    )


def test_proof_report_rejects_cancel_pending_at_replay_end(tmp_path):
    run_dir = tmp_path / "pending_cancel"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "cancel_pending_at_replay_end_events"] = 1
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == [
        "cancel_pending_at_replay_end_events"
    ]
    assert failed.iloc[0]["reason"] == (
        "1 cancel request(s) remained in flight at replay end"
    )


def test_proof_report_rejects_orders_live_beyond_replay_horizon(tmp_path):
    run_dir = tmp_path / "open_order_horizon"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "open_orders_at_replay_end"] = 1
    summary.loc[0, "open_order_qty_at_replay_end"] = 75
    summary.loc[0, "active_ioc_orders_at_replay_end"] = 1
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == ["open_orders_at_replay_end"]
    assert failed.iloc[0]["reason"] == (
        "1 order(s) remained live beyond the replay evidence horizon"
    )


def test_proof_report_rejects_input_integrity_repairs(tmp_path):
    run_dir = tmp_path / "input_repairs"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "input_dropped_rows"] = 2
    summary.loc[0, "input_integrity_dropped_rows"] = 2
    summary.loc[0, "input_session_filtered_rows"] = 0
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == [
        "input_integrity_dropped_rows"
    ]
    assert failed.iloc[0]["reason"] == (
        "2 input row(s) required integrity repair before replay"
    )


def test_proof_report_rejects_enabled_input_tracking_without_datasets(tmp_path):
    run_dir = tmp_path / "no_tracked_input"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "input_dataset_count"] = 0
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == ["input_dataset_count"]
    assert failed.iloc[0]["reason"] == (
        "input quarantine tracking contains no datasets"
    )


def test_proof_report_rejects_empty_normalized_input(tmp_path):
    run_dir = tmp_path / "empty_normalized_input"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "input_kept_rows"] = 0
    summary.loc[0, "input_dropped_rows"] = 20
    summary.loc[0, "input_session_filtered_rows"] = 20
    summary.loc[0, "input_empty_datasets"] = 1
    summary.to_csv(summary_path, index=False)

    report = evaluate_replay_dirs([run_dir])

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.passed
    assert failed["check"].tolist() == ["input_empty_datasets"]
    assert failed.iloc[0]["reason"] == (
        "1 input dataset(s) were empty after normalization"
    )


def test_proof_report_recomputes_parity_futures_signal_freshness(tmp_path):
    run_dir = tmp_path / "parity_futures_freshness"
    write_run(run_dir)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "parity_futures_asof_freshness_enabled"] = True
    summary.loc[0, "parity_futures_max_quote_age_ns"] = 100
    summary.to_csv(summary_path, index=False)
    pd.DataFrame(
        [{"ts": 200, "future_asof_age_ns": 100}]
    ).to_csv(run_dir / "signals.csv", index=False)
    pd.DataFrame(
        [{"ts": 200, "reason": "fresh"}]
    ).to_csv(run_dir / "parity_futures_join_audit.csv", index=False)

    valid = evaluate_replay_dirs([run_dir])

    assert valid.passed
    metrics = valid.metrics.iloc[0]
    assert bool(metrics["parity_futures_join_audit_present"])
    assert bool(metrics["parity_futures_signals_present"])
    assert int(metrics["parity_futures_join_rows"]) == 1
    assert int(metrics["parity_futures_fresh_join_rows"]) == 1
    assert int(metrics["parity_futures_signals_without_age"]) == 0
    assert int(metrics["parity_futures_signal_age_violations"]) == 0
    assert int(metrics["parity_futures_max_signal_age_ns"]) == 100

    pd.DataFrame(
        [{"ts": 200, "future_asof_age_ns": 101}]
    ).to_csv(run_dir / "signals.csv", index=False)
    invalid = evaluate_replay_dirs([run_dir])

    failed = invalid.checks.loc[~invalid.checks["passed"]]
    assert not invalid.passed
    assert failed["check"].tolist() == [
        "parity_futures_signal_age_violations",
        "parity_futures_max_signal_age_ns",
    ]


def test_proof_report_recomputes_parity_execution_safety(tmp_path):
    run_dir = tmp_path / "parity_execution_safety"
    write_run(run_dir, strategy="parity_arb_taker", fills=3)
    summary_path = run_dir / "summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "parity_futures_asof_freshness_enabled"] = True
    summary.loc[0, "parity_futures_max_quote_age_ns"] = 100
    summary.loc[0, "parity_execution_guard_enabled"] = True
    summary.loc[
        0,
        "parity_execution_ioc_batch_preflight_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_edge_revalidation_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_signal_source_causality_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_realized_edge_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_order_timing_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_ioc_arrival_audit_enabled",
    ] = True
    summary.loc[
        0,
        "parity_execution_ioc_arrival_event_lineage_enabled",
    ] = True
    summary.loc[0, "parity_execution_max_leg_book_age_ns"] = 100
    summary.loc[0, "parity_execution_max_leg_book_skew_ns"] = 50
    summary.to_csv(summary_path, index=False)
    pd.DataFrame(
        [{"ts": 200, "future_asof_age_ns": 0}]
    ).to_csv(run_dir / "signals.csv", index=False)
    pd.DataFrame(
        [{"ts": 200, "reason": "fresh"}]
    ).to_csv(run_dir / "parity_futures_join_audit.csv", index=False)
    guard = pd.DataFrame(
        [
                {
                    "signal_index": 0,
                    "signal_ts_ns": 200,
                    "decision_ts_ns": 200,
                    "direction": "buy_synthetic_sell_future",
                "strike": 1000.0,
                "call_instrument_id": "CALL1000",
                "put_instrument_id": "PUT1000",
                "future_instrument_id": "FUT",
                "signal_age_ns": 100,
                "guard_passed": True,
                "guard_reason": "ready",
                "routing_status": "complete",
                "orders_requested": 3,
                "orders_accepted": 3,
                "routing_complete": True,
                "signal_source_causality_enabled": True,
                "signal_source_books_checked": True,
                "signal_source_books_ready": True,
                "signal_source_max_lag_ns": 0,
                "edge_revalidation_enabled": True,
                "edge_revalidation_checked": True,
                "edge_revalidation_qty": 75,
                "signal_net_edge": 1000.0,
                "decision_call_side": 1,
                "decision_call_price": 55.0,
                "decision_put_side": -1,
                "decision_put_price": 60.0,
                "decision_future_side": -1,
                "decision_future_price": 1008.0,
                "decision_contract_multiplier": 1.0,
                "decision_edge_per_unit": 13.0,
                "decision_gross_edge": 975.0,
                "decision_call_cost": 1.0,
                "decision_put_cost": 2.0,
                "decision_future_cost": 3.0,
                "decision_total_cost": 6.0,
                "decision_net_edge": 969.0,
                "decision_min_net_edge": 0.0,
                "ioc_batch_preflight_enabled": True,
                "ioc_batch_preflight_attempted": True,
                "ioc_batch_preflight_passed": True,
                "ioc_batch_preflight_reason": "passed",
                "ioc_batch_preflight_visible_capacity_checked": True,
                "ioc_batch_preflight_min_visible_fill_ratio": 2.0,
                "ioc_batch_preflight_limiting_instrument_id": "CALL1000",
                "ioc_batch_preflight_requested_qty": 75,
                "ioc_batch_preflight_available_qty": 150,
                "ioc_batch_preflight_touch_price": 55.0,
                "ioc_batch_preflight_limit_price": 55.0,
                "call_book_age_ns": 100,
                "put_book_age_ns": 80,
                "future_book_age_ns": 50,
                "leg_book_skew_ns": 50,
            }
        ]
    )
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    legging = pd.DataFrame(
        [
                {
                    "signal_index": 0,
                    "signal_ts_ns": 200,
                    "decision_ts_ns": 200,
                    "direction": "buy_synthetic_sell_future",
                "strike": 1000.0,
                "requested_qty": 75,
                "expected_order_count": 3,
                "order_count": 3,
                "fill_count": 3,
                "filled_leg_count": 3,
                "partial": False,
                "route_rejection_count": 0,
                "fully_filled_leg_count": 3,
                "unfilled_leg_count": 0,
                "routing_complete": True,
                "fills_complete": True,
                "realized_edge_evidence_enabled": True,
                "call_instrument_id": "CALL1000",
                "call_order_id": 1,
                "call_side": 1,
                "call_limit_price": 55.0,
                "call_filled_qty": 75,
                "call_fill_vwap": 55.0,
                "call_fill_cost": 1.0,
                "call_first_fill_ts_ns": 300,
                "call_last_fill_ts_ns": 300,
                "put_instrument_id": "PUT1000",
                "put_order_id": 2,
                "put_side": -1,
                "put_limit_price": 60.0,
                "put_filled_qty": 75,
                "put_fill_vwap": 60.0,
                "put_fill_cost": 2.0,
                "put_first_fill_ts_ns": 301,
                "put_last_fill_ts_ns": 301,
                "future_instrument_id": "FUT",
                "future_order_id": 3,
                "future_side": -1,
                "future_limit_price": 1008.0,
                "future_filled_qty": 75,
                "future_fill_vwap": 1008.0,
                "future_fill_cost": 3.0,
                "future_first_fill_ts_ns": 302,
                "future_last_fill_ts_ns": 302,
                "contract_multiplier": 1.0,
                "decision_net_edge": 969.0,
                "realized_edge_evaluable": True,
                "realized_edge_per_unit": 13.0,
                "realized_gross_edge": 975.0,
                "realized_total_cost": 6.0,
                "realized_net_edge": 969.0,
                "realized_vs_decision_net_edge": 0.0,
                "realized_edge_positive": True,
                "first_fill_ts_ns": 300,
                "last_fill_ts_ns": 302,
                "fill_span_ns": 2,
            }
        ]
    )
    legging.to_csv(run_dir / "legging.csv", index=False)
    fills_frame = pd.DataFrame(
        [
            {
                "instrument_id": "CALL1000",
                "ts_ns": 300,
                "oid": 1,
                "side": 1,
                "qty": 75,
                "price": 55.0,
                "cost": 1.0,
                "maker": False,
            },
            {
                "instrument_id": "PUT1000",
                "ts_ns": 301,
                "oid": 2,
                "side": -1,
                "qty": 75,
                "price": 60.0,
                "cost": 2.0,
                "maker": False,
            },
            {
                "instrument_id": "FUT",
                "ts_ns": 302,
                "oid": 3,
                "side": -1,
                "qty": 75,
                "price": 1008.0,
                "cost": 3.0,
                "maker": False,
            },
        ]
    )
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    order_submissions = pd.DataFrame(
        [
            {
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "order_latency_ns": 50,
                "instrument_id": "CALL1000",
                "oid": 1,
                "side": 1,
                "qty": 75,
                "price": 55.0,
                "order_type": "IOC",
            },
            {
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "order_latency_ns": 50,
                "instrument_id": "PUT1000",
                "oid": 2,
                "side": -1,
                "qty": 75,
                "price": 60.0,
                "order_type": "IOC",
            },
            {
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "order_latency_ns": 50,
                "instrument_id": "FUT",
                "oid": 3,
                "side": -1,
                "qty": 75,
                "price": 1008.0,
                "order_type": "IOC",
            },
        ]
    )
    order_submissions.to_csv(
        run_dir / "order_submissions.csv",
        index=False,
    )
    ioc_arrival_audit = pd.DataFrame(
        [
            {
                "arrival_ts_ns": 300,
                "market_event_seq": 10,
                "event_order_rank": 0,
                "instrument_id": "CALL1000",
                "oid": 1,
                "side": 1,
                "order_type": "IOC",
                "limit_price": 55.0,
                "requested_qty": 75,
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "arrival_lag_ns": 50,
                "bid": 54.95,
                "ask": 55.0,
                "bid_qty": 150,
                "ask_qty": 150,
                "touch_price": 55.0,
                "book_relation": "marketable",
                "marketable": True,
                "lot_size": 75,
                "available_qty": 150,
                "available_after_qty": 75,
                "observed_qty": 150,
                "carried_depletion_qty": 0,
                "event_consumed_qty": 0,
                "filled_qty": 75,
                "shortfall_qty": 0,
                "liquidity_source": "ask_display",
                "outcome": "filled",
                "complete": True,
            },
            {
                "arrival_ts_ns": 301,
                "market_event_seq": 12,
                "event_order_rank": 0,
                "instrument_id": "PUT1000",
                "oid": 2,
                "side": -1,
                "order_type": "IOC",
                "limit_price": 60.0,
                "requested_qty": 75,
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "arrival_lag_ns": 51,
                "bid": 60.0,
                "ask": 60.05,
                "bid_qty": 150,
                "ask_qty": 150,
                "touch_price": 60.0,
                "book_relation": "marketable",
                "marketable": True,
                "lot_size": 75,
                "available_qty": 150,
                "available_after_qty": 75,
                "observed_qty": 150,
                "carried_depletion_qty": 0,
                "event_consumed_qty": 0,
                "filled_qty": 75,
                "shortfall_qty": 0,
                "liquidity_source": "bid_display",
                "outcome": "filled",
                "complete": True,
            },
            {
                "arrival_ts_ns": 302,
                "market_event_seq": 14,
                "event_order_rank": 0,
                "instrument_id": "FUT",
                "oid": 3,
                "side": -1,
                "order_type": "IOC",
                "limit_price": 1008.0,
                "requested_qty": 75,
                "ts_sent_ns": 200,
                "ts_active_ns": 250,
                "arrival_lag_ns": 52,
                "bid": 1008.0,
                "ask": 1008.05,
                "bid_qty": 150,
                "ask_qty": 150,
                "touch_price": 1008.0,
                "book_relation": "marketable",
                "marketable": True,
                "lot_size": 75,
                "available_qty": 150,
                "available_after_qty": 75,
                "observed_qty": 150,
                "carried_depletion_qty": 0,
                "event_consumed_qty": 0,
                "filled_qty": 75,
                "shortfall_qty": 0,
                "liquidity_source": "bid_display",
                "outcome": "filled",
                "complete": True,
            },
        ]
    )
    ioc_arrival_audit.to_csv(
        run_dir / "ioc_arrival_audit.csv",
        index=False,
    )

    valid = evaluate_replay_dirs([run_dir])

    assert valid.passed
    metrics = valid.metrics.iloc[0]
    assert bool(metrics["parity_execution_guard_present"])
    assert bool(metrics["parity_execution_legging_present"])
    assert int(metrics["parity_execution_guard_passed_attempts"]) == 1
    assert int(
        metrics["parity_execution_guard_missing_evidence_rows"]
    ) == 0
    assert bool(
        metrics["parity_execution_ioc_batch_preflight_declared"]
    )
    assert int(
        metrics["parity_execution_ioc_batch_preflight_attempts"]
    ) == 1
    assert int(
        metrics[
            "parity_execution_ioc_batch_preflight_passed_attempts"
        ]
    ) == 1
    assert int(
        metrics[
            "parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_batch_preflight_missing_evidence_rows"
        ]
    ) == 0
    assert bool(
        metrics["parity_execution_edge_revalidation_declared"]
    )
    assert bool(
        metrics[
            "parity_execution_signal_source_causality_declared"
        ]
    )
    assert int(
        metrics["parity_execution_signal_source_checks"]
    ) == 1
    assert int(
        metrics["parity_execution_signal_source_ready_attempts"]
    ) == 1
    assert int(
        metrics["parity_execution_signal_source_pending_attempts"]
    ) == 0
    assert int(
        metrics[
            "parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_signal_source_consistency_violations"
        ]
    ) == 0
    assert int(
        metrics["parity_execution_max_signal_source_lag_ns"]
    ) == 0
    assert int(
        metrics["parity_execution_edge_revalidation_attempts"]
    ) == 1
    assert int(
        metrics["parity_execution_edge_revalidation_passed_attempts"]
    ) == 1
    assert int(
        metrics["parity_execution_edge_revalidation_rejected_attempts"]
    ) == 0
    assert int(
        metrics[
            "parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 0
    assert float(
        metrics["parity_execution_min_routed_net_edge"]
    ) == 969.0
    assert float(
        metrics["parity_execution_max_observed_edge_decay"]
    ) == 31.0
    assert bool(
        metrics["parity_execution_realized_edge_declared"]
    )
    assert bool(metrics["parity_execution_fills_present"])
    assert int(
        metrics["parity_execution_realized_edge_evaluable_count"]
    ) == 1
    assert int(
        metrics["parity_execution_realized_edge_positive_count"]
    ) == 1
    assert int(
        metrics["parity_execution_realized_edge_nonpositive_count"]
    ) == 0
    assert int(
        metrics[
            "parity_execution_realized_edge_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_realized_edge_consistency_violations"
        ]
    ) == 0
    assert float(
        metrics["parity_execution_min_realized_net_edge"]
    ) == 969.0
    assert float(
        metrics["parity_execution_total_realized_net_edge"]
    ) == 969.0
    assert float(
        metrics[
            "parity_execution_min_realized_vs_decision_net_edge"
        ]
    ) == 0.0
    assert int(metrics["parity_execution_max_fill_span_ns"]) == 2
    assert int(
        metrics["parity_execution_fill_timing_evaluable_count"]
    ) == 1
    assert int(
        metrics["parity_execution_negative_fill_latency_count"]
    ) == 0
    assert int(
        metrics["parity_execution_min_first_fill_latency_ns"]
    ) == 100
    assert int(
        metrics["parity_execution_max_completion_latency_ns"]
    ) == 102
    assert bool(
        metrics["parity_execution_order_timing_declared"]
    )
    assert bool(
        metrics["parity_execution_order_submissions_present"]
    )
    assert int(
        metrics["parity_execution_order_timing_evaluable_legs"]
    ) == 3
    assert int(
        metrics[
            "parity_execution_order_timing_missing_evidence_legs"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_order_timing_consistency_violations"
        ]
    ) == 0
    assert int(
        metrics["parity_execution_pre_activation_fill_legs"]
    ) == 0
    assert int(
        metrics[
            "parity_execution_min_activation_to_first_fill_latency_ns"
        ]
    ) == 50
    assert int(
        metrics[
            "parity_execution_max_activation_to_completion_latency_ns"
        ]
    ) == 52
    assert bool(
        metrics[
            "parity_execution_ioc_arrival_audit_declared"
        ]
    )
    assert bool(
        metrics[
            "parity_execution_ioc_arrival_event_lineage_declared"
        ]
    )
    assert bool(
        metrics[
            "parity_execution_ioc_arrival_audit_present"
        ]
    )
    assert int(
        metrics[
            "parity_execution_ioc_arrival_evaluable_legs"
        ]
    ) == 3
    assert int(
        metrics[
            "parity_execution_ioc_arrival_missing_evidence_legs"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_arrival_consistency_violations"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_arrival_not_marketable_legs"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_arrival_capacity_shortfall_legs"
        ]
    ) == 0
    assert float(
        metrics[
            "parity_execution_min_ioc_arrival_fill_ratio"
        ]
    ) == 1.0
    assert int(
        metrics[
            "parity_execution_max_ioc_arrival_lag_ns"
        ]
    ) == 52
    assert int(
        metrics[
            "parity_execution_ioc_arrival_market_events"
        ]
    ) == 3
    assert int(
        metrics[
            "parity_execution_ioc_arrival_competing_depth_events"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_arrival_event_depth_consistency_violations"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        metrics[
            "parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 0
    assert float(
        metrics[
            "parity_execution_min_routed_visible_fill_ratio"
        ]
    ) == 2.0
    assert int(metrics["parity_execution_max_routed_book_age_ns"]) == 100
    assert int(metrics["parity_execution_max_routed_book_skew_ns"]) == 50
    assert int(
        metrics["parity_execution_legging_missing_evidence_rows"]
    ) == 0
    assert int(
        metrics["parity_execution_legging_consistency_violations"]
    ) == 0
    assert int(metrics["parity_execution_complete_count"]) == 1

    summary.loc[0, "parity_execution_guard_enabled"] = False
    summary.to_csv(summary_path, index=False)
    undeclared = evaluate_replay_dirs([run_dir])

    undeclared_failed = undeclared.checks.loc[
        ~undeclared.checks["passed"]
    ]
    assert not undeclared.passed
    assert undeclared_failed["check"].tolist() == [
        "parity_execution_guard_declared"
    ]
    summary.loc[0, "parity_execution_guard_enabled"] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_ioc_batch_preflight_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    preflight_undeclared = evaluate_replay_dirs([run_dir])

    preflight_undeclared_failed = preflight_undeclared.checks.loc[
        ~preflight_undeclared.checks["passed"]
    ]
    assert not preflight_undeclared.passed
    assert preflight_undeclared_failed["check"].tolist() == [
        "parity_execution_ioc_batch_preflight_declared"
    ]
    summary.loc[
        0,
        "parity_execution_ioc_batch_preflight_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_edge_revalidation_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    edge_undeclared = evaluate_replay_dirs([run_dir])

    edge_undeclared_failed = edge_undeclared.checks.loc[
        ~edge_undeclared.checks["passed"]
    ]
    assert not edge_undeclared.passed
    assert edge_undeclared_failed["check"].tolist() == [
        "parity_execution_edge_revalidation_declared"
    ]
    summary.loc[
        0,
        "parity_execution_edge_revalidation_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_realized_edge_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    realized_edge_undeclared = evaluate_replay_dirs([run_dir])

    realized_edge_undeclared_failed = (
        realized_edge_undeclared.checks.loc[
            ~realized_edge_undeclared.checks["passed"]
        ]
    )
    assert not realized_edge_undeclared.passed
    assert realized_edge_undeclared_failed["check"].tolist() == [
        "parity_execution_realized_edge_declared"
    ]
    summary.loc[
        0,
        "parity_execution_realized_edge_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_order_timing_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    order_timing_undeclared = evaluate_replay_dirs([run_dir])

    order_timing_undeclared_failed = (
        order_timing_undeclared.checks.loc[
            ~order_timing_undeclared.checks["passed"]
        ]
    )
    assert not order_timing_undeclared.passed
    assert order_timing_undeclared_failed["check"].tolist() == [
        "parity_execution_order_timing_declared"
    ]
    summary.loc[
        0,
        "parity_execution_order_timing_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_ioc_arrival_audit_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    ioc_arrival_undeclared = evaluate_replay_dirs([run_dir])

    ioc_arrival_undeclared_failed = (
        ioc_arrival_undeclared.checks.loc[
            ~ioc_arrival_undeclared.checks["passed"]
        ]
    )
    assert not ioc_arrival_undeclared.passed
    assert ioc_arrival_undeclared_failed["check"].tolist() == [
        "parity_execution_ioc_arrival_audit_declared"
    ]
    summary.loc[
        0,
        "parity_execution_ioc_arrival_audit_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_ioc_arrival_event_lineage_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    ioc_event_lineage_undeclared = evaluate_replay_dirs(
        [run_dir]
    )

    ioc_event_lineage_undeclared_failed = (
        ioc_event_lineage_undeclared.checks.loc[
            ~ioc_event_lineage_undeclared.checks["passed"]
        ]
    )
    assert not ioc_event_lineage_undeclared.passed
    assert (
        ioc_event_lineage_undeclared_failed["check"].tolist()
        == [
            "parity_execution_ioc_arrival_event_lineage_declared"
        ]
    )
    summary.loc[
        0,
        "parity_execution_ioc_arrival_event_lineage_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    summary.loc[
        0,
        "parity_execution_signal_source_causality_enabled",
    ] = False
    summary.to_csv(summary_path, index=False)
    signal_source_undeclared = evaluate_replay_dirs([run_dir])

    signal_source_undeclared_failed = (
        signal_source_undeclared.checks.loc[
            ~signal_source_undeclared.checks["passed"]
        ]
    )
    assert not signal_source_undeclared.passed
    assert signal_source_undeclared_failed["check"].tolist() == [
        "parity_execution_signal_source_causality_declared"
    ]
    summary.loc[
        0,
        "parity_execution_signal_source_causality_enabled",
    ] = True
    summary.to_csv(summary_path, index=False)

    ioc_arrival_audit.loc[
        ioc_arrival_audit["instrument_id"].eq("FUT"),
        "available_qty",
    ] = 74
    ioc_arrival_audit.to_csv(
        run_dir / "ioc_arrival_audit.csv",
        index=False,
    )
    ioc_arrival_tampered = evaluate_replay_dirs([run_dir])

    ioc_arrival_tampered_failed = (
        ioc_arrival_tampered.checks.loc[
            ~ioc_arrival_tampered.checks["passed"]
        ]
    )
    assert not ioc_arrival_tampered.passed
    assert ioc_arrival_tampered_failed["check"].tolist() == [
        "parity_execution_ioc_arrival_consistency_violations",
        (
            "parity_execution_ioc_arrival_"
            "event_depth_consistency_violations"
        ),
    ]
    ioc_arrival_audit.loc[
        ioc_arrival_audit["instrument_id"].eq("FUT"),
        "available_qty",
    ] = 150
    ioc_arrival_audit.to_csv(
        run_dir / "ioc_arrival_audit.csv",
        index=False,
    )

    order_submissions.loc[
        order_submissions["instrument_id"].eq("CALL1000"),
        "ts_active_ns",
    ] = 251
    order_submissions.to_csv(
        run_dir / "order_submissions.csv",
        index=False,
    )
    order_schedule_tampered = evaluate_replay_dirs([run_dir])

    order_schedule_tampered_failed = (
        order_schedule_tampered.checks.loc[
            ~order_schedule_tampered.checks["passed"]
        ]
    )
    assert not order_schedule_tampered.passed
    assert order_schedule_tampered_failed["check"].tolist() == [
        "parity_execution_order_timing_consistency_violations",
        "parity_execution_ioc_arrival_consistency_violations",
    ]
    order_submissions.loc[
        order_submissions["instrument_id"].eq("CALL1000"),
        "ts_active_ns",
    ] = 250
    order_submissions.to_csv(
        run_dir / "order_submissions.csv",
        index=False,
    )

    fills_frame.loc[
        fills_frame["instrument_id"].eq("FUT"),
        "price",
    ] = 1007.0
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    fill_price_tampered = evaluate_replay_dirs([run_dir])

    fill_price_tampered_failed = fill_price_tampered.checks.loc[
        ~fill_price_tampered.checks["passed"]
    ]
    assert not fill_price_tampered.passed
    assert fill_price_tampered_failed["check"].tolist() == [
        "parity_execution_realized_edge_consistency_violations",
        "parity_execution_ioc_arrival_consistency_violations",
    ]
    fills_frame.loc[
        fills_frame["instrument_id"].eq("FUT"),
        "price",
    ] = 1008.0
    fills_frame.to_csv(run_dir / "fills.csv", index=False)

    fills_frame.loc[
        fills_frame["instrument_id"].eq("CALL1000"),
        "ts_ns",
    ] = 249
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    legging.loc[0, "call_first_fill_ts_ns"] = 249
    legging.loc[0, "call_last_fill_ts_ns"] = 249
    legging.loc[0, "first_fill_ts_ns"] = 249
    legging.loc[0, "fill_span_ns"] = 53
    legging.to_csv(run_dir / "legging.csv", index=False)
    pre_activation_fill = evaluate_replay_dirs([run_dir])

    pre_activation_fill_failed = pre_activation_fill.checks.loc[
        ~pre_activation_fill.checks["passed"]
    ]
    assert not pre_activation_fill.passed
    assert pre_activation_fill_failed["check"].tolist() == [
        "parity_execution_pre_activation_fill_legs",
        "parity_execution_ioc_arrival_consistency_violations",
    ]

    fills_frame.loc[
        fills_frame["instrument_id"].eq("CALL1000"),
        "ts_ns",
    ] = 199
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    legging.loc[0, "call_first_fill_ts_ns"] = 199
    legging.loc[0, "call_last_fill_ts_ns"] = 199
    legging.loc[0, "first_fill_ts_ns"] = 199
    legging.loc[0, "fill_span_ns"] = 103
    legging.to_csv(run_dir / "legging.csv", index=False)
    negative_fill_latency = evaluate_replay_dirs([run_dir])

    negative_fill_latency_failed = (
        negative_fill_latency.checks.loc[
            ~negative_fill_latency.checks["passed"]
        ]
    )
    assert not negative_fill_latency.passed
    assert negative_fill_latency_failed["check"].tolist() == [
        "parity_execution_realized_edge_consistency_violations",
        "parity_execution_negative_fill_latency_count",
        "parity_execution_pre_activation_fill_legs",
        "parity_execution_ioc_arrival_consistency_violations",
    ]
    fills_frame.loc[
        fills_frame["instrument_id"].eq("CALL1000"),
        "ts_ns",
    ] = 300
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    legging.loc[0, "call_first_fill_ts_ns"] = 300
    legging.loc[0, "call_last_fill_ts_ns"] = 300
    legging.loc[0, "first_fill_ts_ns"] = 300
    legging.loc[0, "fill_span_ns"] = 2
    legging.to_csv(run_dir / "legging.csv", index=False)

    fills_frame.loc[
        fills_frame["instrument_id"].eq("FUT"),
        "cost",
    ] = 1000.0
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    legging.loc[0, "future_fill_cost"] = 1000.0
    legging.loc[0, "realized_total_cost"] = 1003.0
    legging.loc[0, "realized_net_edge"] = -28.0
    legging.loc[0, "realized_vs_decision_net_edge"] = -997.0
    legging.loc[0, "realized_edge_positive"] = False
    legging.to_csv(run_dir / "legging.csv", index=False)
    realized_edge_lost = evaluate_replay_dirs([run_dir])

    realized_edge_lost_failed = realized_edge_lost.checks.loc[
        ~realized_edge_lost.checks["passed"]
    ]
    assert not realized_edge_lost.passed
    assert realized_edge_lost_failed["check"].tolist() == [
        "parity_execution_realized_edge_nonpositive_count",
        "parity_execution_min_realized_net_edge",
    ]
    fills_frame.loc[
        fills_frame["instrument_id"].eq("FUT"),
        "cost",
    ] = 3.0
    fills_frame.to_csv(run_dir / "fills.csv", index=False)
    legging.loc[0, "future_fill_cost"] = 3.0
    legging.loc[0, "realized_total_cost"] = 6.0
    legging.loc[0, "realized_net_edge"] = 969.0
    legging.loc[0, "realized_vs_decision_net_edge"] = 0.0
    legging.loc[0, "realized_edge_positive"] = True
    legging.to_csv(run_dir / "legging.csv", index=False)

    guard.loc[0, "guard_passed"] = False
    guard.loc[0, "guard_reason"] = "ioc_batch_preflight_rejected"
    guard.loc[0, "routing_status"] = "not_attempted"
    guard.loc[0, "orders_requested"] = 0
    guard.loc[0, "orders_accepted"] = 0
    guard.loc[0, "routing_complete"] = False
    guard.loc[0, "ioc_batch_preflight_passed"] = False
    guard.loc[
        0,
        "ioc_batch_preflight_reason",
    ] = "instrument_position_limit"
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    preflight_rejected = evaluate_replay_dirs([run_dir])

    preflight_rejected_failed = preflight_rejected.checks.loc[
        ~preflight_rejected.checks["passed"]
    ]
    assert not preflight_rejected.passed
    assert preflight_rejected_failed["check"].tolist() == [
        "parity_execution_ioc_batch_preflight_rejected_attempts"
    ]

    guard.loc[0, "guard_passed"] = True
    guard.loc[0, "guard_reason"] = "ready"
    guard.loc[0, "routing_status"] = "complete"
    guard.loc[0, "orders_requested"] = 3
    guard.loc[0, "orders_accepted"] = 3
    guard.loc[0, "routing_complete"] = True
    guard.loc[0, "ioc_batch_preflight_passed"] = True
    guard.loc[0, "ioc_batch_preflight_reason"] = "passed"

    guard.loc[
        0,
        "ioc_batch_preflight_available_qty",
    ] = float("nan")
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    capacity_missing = evaluate_replay_dirs([run_dir])

    capacity_missing_failed = capacity_missing.checks.loc[
        ~capacity_missing.checks["passed"]
    ]
    assert not capacity_missing.passed
    assert capacity_missing_failed["check"].tolist() == [
        "parity_execution_ioc_visible_capacity_missing_evidence_rows"
    ]
    guard.loc[0, "ioc_batch_preflight_available_qty"] = 150

    guard.loc[
        0,
        "ioc_batch_preflight_min_visible_fill_ratio",
    ] = 0.5
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    capacity_inconsistent = evaluate_replay_dirs([run_dir])

    capacity_inconsistent_failed = capacity_inconsistent.checks.loc[
        ~capacity_inconsistent.checks["passed"]
    ]
    assert not capacity_inconsistent.passed
    assert capacity_inconsistent_failed["check"].tolist() == [
        "parity_execution_ioc_visible_capacity_consistency_violations"
    ]
    guard.loc[
        0,
        "ioc_batch_preflight_min_visible_fill_ratio",
    ] = 2.0

    guard.loc[0, "decision_net_edge"] = -1.0
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    edge_inconsistent = evaluate_replay_dirs([run_dir])

    edge_inconsistent_failed = edge_inconsistent.checks.loc[
        ~edge_inconsistent.checks["passed"]
    ]
    assert not edge_inconsistent.passed
    assert edge_inconsistent_failed["check"].tolist() == [
        "parity_execution_edge_revalidation_consistency_violations",
        "parity_execution_realized_edge_consistency_violations",
        "parity_execution_min_routed_net_edge",
    ]
    guard.loc[0, "decision_net_edge"] = 969.0

    guard.loc[0, "signal_source_max_lag_ns"] = 1
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    signal_source_inconsistent = evaluate_replay_dirs([run_dir])

    signal_source_inconsistent_failed = (
        signal_source_inconsistent.checks.loc[
            ~signal_source_inconsistent.checks["passed"]
        ]
    )
    assert not signal_source_inconsistent.passed
    assert signal_source_inconsistent_failed["check"].tolist() == [
        "parity_execution_signal_source_consistency_violations"
    ]
    guard.loc[0, "signal_source_max_lag_ns"] = 0

    guard.loc[0, "ioc_batch_preflight_limit_price"] = 54.0
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    capacity_unmarketable = evaluate_replay_dirs([run_dir])

    capacity_unmarketable_failed = capacity_unmarketable.checks.loc[
        ~capacity_unmarketable.checks["passed"]
    ]
    assert not capacity_unmarketable.passed
    assert capacity_unmarketable_failed["check"].tolist() == [
        "parity_execution_ioc_visible_capacity_consistency_violations"
    ]
    guard.loc[0, "ioc_batch_preflight_limit_price"] = 55.0

    guard.loc[0, "signal_age_ns"] = 101
    guard.loc[0, "call_book_age_ns"] = 101
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    stale = evaluate_replay_dirs([run_dir])

    stale_failed = stale.checks.loc[~stale.checks["passed"]]
    assert not stale.passed
    assert stale_failed["check"].tolist() == [
        "parity_execution_guard_age_violations",
        "parity_execution_max_routed_book_age_ns",
    ]

    guard.loc[0, "signal_age_ns"] = 100
    guard.loc[0, "call_book_age_ns"] = 100
    guard.loc[0, "routing_status"] = "partial"
    guard.loc[0, "orders_accepted"] = 2
    guard.loc[0, "routing_complete"] = False
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    legging.loc[0, "order_count"] = 2
    legging.loc[0, "fill_count"] = 2
    legging.loc[0, "filled_leg_count"] = 2
    legging.loc[0, "partial"] = True
    legging.loc[0, "route_rejection_count"] = 1
    legging.loc[0, "fully_filled_leg_count"] = 2
    legging.loc[0, "unfilled_leg_count"] = 1
    legging.loc[0, "routing_complete"] = False
    legging.loc[0, "fills_complete"] = False
    legging.loc[0, "future_order_id"] = float("nan")
    legging.loc[0, "future_filled_qty"] = 0
    legging.loc[0, "future_fill_vwap"] = float("nan")
    legging.loc[0, "future_fill_cost"] = float("nan")
    legging.loc[0, "future_first_fill_ts_ns"] = float("nan")
    legging.loc[0, "future_last_fill_ts_ns"] = float("nan")
    legging.loc[0, "realized_edge_evaluable"] = False
    legging.loc[0, "realized_edge_per_unit"] = float("nan")
    legging.loc[0, "realized_gross_edge"] = float("nan")
    legging.loc[0, "realized_total_cost"] = float("nan")
    legging.loc[0, "realized_net_edge"] = float("nan")
    legging.loc[0, "realized_vs_decision_net_edge"] = float("nan")
    legging.loc[0, "realized_edge_positive"] = False
    legging.loc[0, "last_fill_ts_ns"] = 301
    legging.loc[0, "fill_span_ns"] = 1
    legging.to_csv(run_dir / "legging.csv", index=False)
    incomplete = evaluate_replay_dirs([run_dir])

    incomplete_failed = incomplete.checks.loc[
        ~incomplete.checks["passed"]
    ]
    assert not incomplete.passed
    assert incomplete_failed["check"].tolist() == [
        "parity_execution_routing_incomplete_attempts",
        "parity_execution_incomplete_count",
        "parity_execution_route_rejected_legs",
        "parity_execution_unfilled_legs",
        "parity_execution_complete_count",
    ]

    guard.loc[0, "routing_status"] = "complete"
    guard.loc[0, "orders_accepted"] = 3
    guard.loc[0, "routing_complete"] = True
    guard.to_csv(run_dir / "parity_execution_guard.csv", index=False)
    legging.loc[0, "order_count"] = 3
    legging.loc[0, "fill_count"] = 3
    legging.loc[0, "filled_leg_count"] = 3
    legging.loc[0, "partial"] = False
    legging.loc[0, "route_rejection_count"] = 0
    legging.loc[0, "fully_filled_leg_count"] = 3
    legging.loc[0, "unfilled_leg_count"] = 0
    legging.loc[0, "routing_complete"] = True
    legging.loc[0, "future_order_id"] = 3
    legging.loc[0, "future_filled_qty"] = 75
    legging.loc[0, "future_fill_vwap"] = 1008.0
    legging.loc[0, "future_fill_cost"] = 3.0
    legging.loc[0, "future_first_fill_ts_ns"] = 302
    legging.loc[0, "future_last_fill_ts_ns"] = 302
    legging.loc[0, "realized_edge_evaluable"] = True
    legging.loc[0, "realized_edge_per_unit"] = 13.0
    legging.loc[0, "realized_gross_edge"] = 975.0
    legging.loc[0, "realized_total_cost"] = 6.0
    legging.loc[0, "realized_net_edge"] = 969.0
    legging.loc[0, "realized_vs_decision_net_edge"] = 0.0
    legging.loc[0, "realized_edge_positive"] = True
    legging.loc[0, "last_fill_ts_ns"] = 302
    legging.loc[0, "fill_span_ns"] = 2
    legging = legging.drop(columns=["fills_complete"])
    legging.to_csv(run_dir / "legging.csv", index=False)
    missing = evaluate_replay_dirs([run_dir])

    missing_failed = missing.checks.loc[~missing.checks["passed"]]
    assert not missing.passed
    assert missing_failed["check"].tolist() == [
        "parity_execution_realized_edge_missing_evidence_rows",
        "parity_execution_legging_missing_evidence_rows",
        "parity_execution_incomplete_count",
        "parity_execution_complete_count",
    ]


def test_write_proof_report_outputs_metrics_checks_and_summary(tmp_path):
    run_dir = tmp_path / "parity_pass"
    out_dir = tmp_path / "proof"
    write_run(run_dir, net_pnl=25.0, fills=4)

    report = write_proof_report(
        [run_dir],
        output_dir=out_dir,
        thresholds=ProofThresholds(min_net_pnl=10.0, min_fills=1),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "proof_metrics.csv").exists()
    assert (out_dir / "proof_checks.csv").exists()
    assert (out_dir / "proof_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "proof_summary.csv")
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    verification = verify_proof_report(out_dir)
    assert bool(summary.loc[0, "non_authorizing"])
    assert not bool(summary.loc[0, "authorizes_routing"])
    assert not bool(summary.loc[0, "authorizes_submission"])
    assert manifest["parameters"]["run_names"] is None
    assert set(manifest["inputs"]) == {
        "run_dependencies",
        "run_dirs",
        "run_manifests",
    }
    assert manifest["extra"] == {
        "all_passed": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
        "non_authorizing": True,
    }
    assert verification.verified
    assert verification.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.replay_manifests_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert verification.replay_manifest_count == 1
    assert verification.replay_manifest_current_count == 1


def test_proof_report_blocks_mixed_strategy_or_market_runs(tmp_path):
    leadlag = tmp_path / "leadlag_pass"
    imbalance = tmp_path / "imbalance_pass"
    write_run(leadlag, strategy="leadlag", market="india_nse_index_derivatives")
    write_run(imbalance, strategy="imbalance", market="us_equities_regular")

    report = evaluate_replay_dirs(
        [leadlag, imbalance],
        thresholds=ProofThresholds(min_net_pnl=1.0, min_fills=1),
    )

    assert not report.passed
    summary = report.summary.iloc[0]
    assert bool(summary["mixed_identity"])
    assert int(summary["strategy_count"]) == 2
    assert int(summary["market_count"]) == 2
    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert {"same_strategy", "same_market"} <= failed


def test_proof_report_fails_with_actionable_reasons(tmp_path):
    run_dir = tmp_path / "bad_run"
    write_run(
        run_dir,
        net_pnl=-5.0,
        fills=0,
        otr=75.0,
        otr_breached=True,
        equity_values=(0.0, 20.0, -20.0),
        regime_changes=(-15.0,),
        markouts=(-3.0, -1.0),
    )

    report = evaluate_replay_dirs(
        [run_dir],
        thresholds=ProofThresholds(
            min_net_pnl=1.0,
            min_fills=1,
            max_drawdown=10.0,
            max_otr=50.0,
            min_worst_regime_equity_change=0.0,
            min_markout_mean=0.0,
        ),
    )

    failed_checks = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert failed_checks == {
        "net_pnl",
        "fills",
        "otr_not_breached",
        "max_drawdown",
        "order_to_trade_ratio",
        "worst_regime_equity_change",
        "markout_mean",
    }
    assert report.summary.iloc[0]["failed_runs"] == 1
    assert report.checks.loc[~report.checks["passed"], "reason"].str.len().min() > 0


def test_unified_cli_proof_report_dispatch_and_fail_on_breach(tmp_path):
    pass_run = tmp_path / "pass_run"
    fail_run = tmp_path / "fail_run"
    pass_out = tmp_path / "pass_proof"
    fail_out = tmp_path / "fail_proof"
    write_run(pass_run, net_pnl=20.0, fills=3)
    write_run(fail_run, net_pnl=-1.0, fills=0)

    pass_code = main(
        [
            "proof-report",
            "--runs",
            str(pass_run),
            "--out",
            str(pass_out),
            "--min-net-pnl",
            "1",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )
    fail_code = main(
        [
            "proof-report",
            "--runs",
            str(fail_run),
            "--out",
            str(fail_out),
            "--min-net-pnl",
            "1",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )
    failed_proof_verification = verify_proof_report(fail_out)
    failed_verify_code = main(
        [
            "verify-proof-report",
            "--report",
            str(fail_out),
            "--fail-on-breach",
        ]
    )

    assert pass_code == 0
    assert fail_code == 2
    assert failed_proof_verification.verified
    assert not failed_proof_verification.passed
    assert failed_verify_code == 0
    assert (pass_out / "proof_summary.csv").exists()
    assert (fail_out / "proof_checks.csv").exists()


def test_proof_verifier_rejects_resealed_artifact_tampering(tmp_path):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    write_run(run_dir)
    write_proof_report(
        [run_dir],
        output_dir=out_dir,
        thresholds=ProofThresholds(min_net_pnl=1.0, min_fills=1),
    )
    summary_path = out_dir / "proof_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "total_net_pnl"] = 999999.0
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)
    code = main(
        [
            "verify-proof-report",
            "--report",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    assert generic.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.replay_manifests_current
    assert not verification.artifacts_consistent
    assert not verification.verified
    assert verification.error == (
        "artifacts do not reconstruct from replay inputs"
    )
    assert code == 2


def test_proof_verifier_rejects_resealed_extra_order_sidecar(tmp_path):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    write_run(run_dir)
    write_proof_report([run_dir], output_dir=out_dir)
    pd.DataFrame(
        [{"instrument_id": "NIFTY", "side": "BUY", "qty": 1}]
    ).to_csv(out_dir / "unexpected_orders.csv", index=False)
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)

    assert generic.passed
    assert generic.artifact_count == 4
    assert not verification.artifacts_consistent
    assert not verification.verified


def test_proof_verifier_rejects_resealed_outer_manifest_after_source_drift(
    tmp_path,
):
    run_dir = tmp_path / "replay"
    out_dir = tmp_path / "proof"
    source = write_run(run_dir)
    write_proof_report([run_dir], output_dir=out_dir)
    source.write_text("ts,bid,ask\n1,99,102\n", encoding="utf-8")
    reseal_experiment_manifest(out_dir)

    generic = verify_experiment_manifest(out_dir / "manifest.json")
    verification = verify_proof_report(out_dir)

    assert generic.passed
    assert verification.inputs_current
    assert not verification.replay_manifests_current
    assert verification.replay_manifest_count == 1
    assert verification.replay_manifest_current_count == 0
    assert not verification.verified
    assert verification.error == (
        "replay manifests are missing, stale, or unfingerprinted"
    )


def test_parity_ioc_event_depth_proof_rejects_collective_overbooking():
    rows = [
        {
            "instrument_id": "NIFTY-FUT",
            "arrival_ts_ns": 1_000,
            "market_event_seq": 8,
            "event_order_rank": 0,
            "side": 1,
            "bid": 99.95,
            "ask": 100.0,
            "bid_qty": 150,
            "ask_qty": 150,
            "observed_qty": 150,
            "carried_depletion_qty": 0,
            "event_consumed_qty": 0,
            "available_qty": 150,
            "filled_qty": 75,
        },
        {
            "instrument_id": "NIFTY-FUT",
            "arrival_ts_ns": 1_000,
            "market_event_seq": 8,
            "event_order_rank": 1,
            "side": 1,
            "bid": 99.95,
            "ask": 100.0,
            "bid_qty": 150,
            "ask_qty": 150,
            "observed_qty": 150,
            "carried_depletion_qty": 0,
            "event_consumed_qty": 75,
            "available_qty": 75,
            "filled_qty": 75,
        },
    ]

    valid = _parity_ioc_event_depth_metrics(rows)

    assert valid["parity_execution_ioc_arrival_market_events"] == 1
    assert (
        valid[
            "parity_execution_ioc_arrival_competing_depth_events"
        ]
        == 1
    )
    assert (
        valid[
            "parity_execution_ioc_arrival_event_depth_consistency_violations"
        ]
        == 0
    )

    rows[1]["event_consumed_qty"] = 0
    rows[1]["available_qty"] = 150
    overbooked = _parity_ioc_event_depth_metrics(rows)

    assert (
        overbooked[
            "parity_execution_ioc_arrival_event_depth_consistency_violations"
        ]
        == 1
    )
