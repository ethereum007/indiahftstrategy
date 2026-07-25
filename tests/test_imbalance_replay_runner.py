import json

import pandas as pd

from hft_cli import main
from reports.proof import evaluate_replay_dirs
from strategies.run_imbalance_replay import run_imbalance_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def ns_us(value: str) -> int:
    return pd.Timestamp(value, tz="America/New_York").value


def imbalance_ticks():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    ts3 = ns_ist("2026-06-10 09:15:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
        ]
    )


def write_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "imbalance",
                "failed_checks": [],
                "replay_defaults": {
                    "entry_imbalance": 0.6,
                    "min_microprice_edge_ticks": 0.25,
                    "hold_ns": 1_000_000,
                    "markout_horizons_ns": [100_000],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_us_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "imbalance",
                "failed_checks": [],
                "replay_defaults": {
                    "market": "us_equities_regular",
                    "tick_size": 0.01,
                    "entry_imbalance": 0.6,
                    "min_microprice_edge_ticks": 0.25,
                    "hold_ns": 1_000_000,
                    "markout_horizons_ns": [100_000],
                    "generic_costs": {
                        "buy_notional_rate": 0.0,
                        "sell_notional_rate": 0.0,
                        "per_unit_fee": 0.0,
                        "per_contract_fee": 0.0,
                        "per_order_fee": 0.01,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def us_imbalance_ticks():
    ts0 = ns_us("2026-06-10 09:29:59")
    ts1 = ns_us("2026-06-10 09:30:00")
    ts2 = ns_us("2026-06-10 09:30:00.000100")
    ts3 = ns_us("2026-06-10 09:30:00.000200")
    ts4 = ns_us("2026-06-10 09:30:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 99.00, "ask": 99.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.00, "ask": 100.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts3, "bid": 100.10, "ask": 100.11, "bid_qty": 500, "ask_qty": 500},
            {"ts": ts4, "bid": 100.10, "ask": 100.11, "bid_qty": 500, "ask_qty": 500},
        ]
    )


def test_run_imbalance_replay_writes_outputs_and_signals(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)

    replay = run_imbalance_replay(
        ticks_path=ticks_path,
        output_dir=out_dir,
        tick_size=0.05,
        qty=75,
        entry_imbalance=0.6,
        exit_imbalance=0.15,
        min_microprice_edge_ticks=0.25,
        hold_ns=1_000_000,
        cooloff_ns=1_000_000,
        markout_horizons_ns=[100_000],
    )

    assert replay.result.engine.orders_sent == 2
    assert replay.summary.iloc[0]["fills"] == 2
    assert set(replay.signals["action"]) == {"entry", "exit_decay"}
    assert not replay.markouts.empty
    assert (out_dir / "fills.csv").exists()
    assert (out_dir / "order_rejections.csv").exists()
    assert (out_dir / "order_cancellations.csv").exists()
    assert (out_dir / "liquidity_shortfalls.csv").exists()
    assert (out_dir / "queue_initializations.csv").exists()
    assert (out_dir / "resting_transitions.csv").exists()
    assert (out_dir / "passive_price_throughs.csv").exists()
    assert (out_dir / "terminal_liquidations.csv").exists()
    assert (out_dir / "equity.csv").exists()
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "signals.csv").exists()
    assert (out_dir / "markouts.csv").exists()
    assert (out_dir / "input_quarantine.csv").exists()
    assert (out_dir / "pnl_decomposition.csv").exists()
    assert (out_dir / "spread_pairs.csv").exists()
    assert (out_dir / "spread_summary.csv").exists()
    assert (out_dir / "residual_inventory.csv").exists()
    assert (out_dir / "fills_by_regime.csv").exists()
    assert (out_dir / "equity_by_regime.csv").exists()
    assert (out_dir / "manifest.json").exists()
    order_cancellations = pd.read_csv(out_dir / "order_cancellations.csv")
    assert {
        "ts_sent_ns",
        "ts_effective_ns",
        "ts_status_ns",
        "instrument_id",
        "oid",
        "requested_qty",
        "filled_while_pending_qty",
        "remaining_qty",
        "status",
    }.issubset(order_cancellations.columns)
    queue_initializations = pd.read_csv(out_dir / "queue_initializations.csv")
    assert {
        "arrival_ts_ns",
        "arrival_lag_ns",
        "arrival_book_relation",
        "initialization_lag_ns",
        "mode",
        "book_relation",
    }.issubset(queue_initializations.columns)
    resting_transitions = pd.read_csv(out_dir / "resting_transitions.csv")
    assert {
        "transition_lag_ns",
        "remaining_qty",
        "book_relation",
        "deferred_at_transition",
        "queue_initialized",
        "queue_initialization_ts_ns",
        "queue_initialization_lag_ns",
        "initialization_book_relation",
    }.issubset(resting_transitions.columns)
    passive_price_throughs = pd.read_csv(
        out_dir / "passive_price_throughs.csv"
    )
    assert {
        "limit_price",
        "contra_touch_price",
        "requested_qty",
        "available_qty",
        "filled_qty",
        "shortfall_qty",
        "queue_ahead_before",
        "own_queue_tail",
        "liquidity_source",
        "complete",
    }.issubset(passive_price_throughs.columns)
    summary = replay.summary.iloc[0]
    input_quarantine = pd.read_csv(out_dir / "input_quarantine.csv")
    assert input_quarantine["dataset"].tolist() == ["ticks"]
    assert input_quarantine["dataset_type"].tolist() == ["l1_ticks"]
    assert int(input_quarantine.loc[0, "integrity_dropped_rows"]) == 0
    assert int(input_quarantine.loc[0, "session_filtered_rows"]) == 0
    assert bool(summary["input_quarantine_tracking_enabled"])
    assert int(summary["input_dataset_count"]) == 1
    assert int(summary["input_total_rows"]) == 4
    assert int(summary["input_kept_rows"]) == 4
    assert int(summary["input_dropped_rows"]) == 0
    assert int(summary["input_integrity_dropped_rows"]) == 0
    assert int(summary["input_session_filtered_rows"]) == 0
    assert int(summary["input_empty_datasets"]) == 0
    assert bool(summary["pending_order_risk_reservation_enabled"])
    assert bool(summary["aggressive_self_cross_prevention_enabled"])
    assert bool(summary["venue_order_validation_enabled"])
    assert bool(summary["shared_event_liquidity_enabled"])
    assert bool(summary["persistent_displayed_liquidity_enabled"])
    assert bool(summary["lot_conserving_fills_enabled"])
    assert bool(summary["causal_event_ordering_enabled"])
    assert bool(summary["cancel_lifecycle_tracking_enabled"])
    assert int(summary["cancel_requests"]) == 0
    assert int(summary["cancel_effective_events"]) == 0
    assert int(summary["cancel_effective_after_partial_fill_events"]) == 0
    assert int(summary["cancel_filled_before_effective_events"]) == 0
    assert int(summary["cancel_closed_before_effective_events"]) == 0
    assert int(summary["cancel_pending_at_replay_end_events"]) == 0
    assert int(summary["cancel_inflight_filled_qty"]) == 0
    assert bool(summary["arrival_queue_initialization_enabled"])
    assert int(summary["limit_orders_sent"]) == 0
    assert int(summary["queue_initialization_events"]) == 0
    assert int(summary["deferred_queue_initialization_events"]) == 0
    assert int(summary["uninitialized_limit_orders"]) == 0
    assert int(summary["max_queue_initialization_lag_ns"]) == 0
    assert int(summary["residual_resting_transition_events"]) == 0
    assert int(summary["residual_resting_transition_qty"]) == 0
    assert int(summary["deferred_residual_queue_events"]) == 0
    assert int(summary["unresolved_residual_queue_events"]) == 0
    assert int(summary["max_residual_queue_initialization_lag_ns"]) == 0
    assert bool(summary["passive_price_through_depth_constrained_enabled"])
    assert int(summary["passive_price_through_events"]) == 0
    assert int(summary["passive_price_through_requested_qty"]) == 0
    assert int(summary["passive_price_through_filled_qty"]) == 0
    assert int(summary["passive_price_through_shortfall_qty"]) == 0
    assert int(summary["passive_price_through_incomplete_events"]) == 0
    assert bool(summary["terminal_liquidation_depth_constrained_enabled"])
    assert int(summary["terminal_liquidation_events"]) == 0
    assert int(summary["terminal_liquidation_requested_qty"]) == 0
    assert int(summary["terminal_liquidation_filled_qty"]) == 0
    assert int(summary["terminal_liquidation_shortfall_qty"]) == 0
    assert int(summary["terminal_liquidation_incomplete_events"]) == 0
    assert int(summary["terminal_residual_position_qty"]) == 0
    assert int(summary["terminal_residual_instruments"]) == 0
    assert bool(summary["terminal_liquidation_complete"])
    assert int(summary["liquidity_shortfall_events"]) == 0
    assert int(summary["liquidity_shortfall_qty"]) == 0
    assert int(summary["carried_depletion_shortfall_events"]) == 0
    assert int(summary["carried_depletion_shortfall_qty"]) == 0
    assert int(summary["pretrade_rejections"]) == 0
    assert int(summary["venue_rule_rejections"]) == 0
    assert int(summary["position_risk_rejections"]) == 0
    assert int(summary["self_cross_rejections"]) == 0


def test_imbalance_replay_exposes_quarantined_integrity_rows(tmp_path):
    ticks_path = tmp_path / "ticks_with_crossed_row.csv"
    out_dir = tmp_path / "imbalance_replay"
    source = imbalance_ticks()
    source.loc[len(source)] = {
        "ts": ns_ist("2026-06-10 09:15:00.000400"),
        "bid": 101.00,
        "ask": 100.00,
        "bid_qty": 100,
        "ask_qty": 100,
    }
    source.to_csv(ticks_path, index=False)

    replay = run_imbalance_replay(
        ticks_path=ticks_path,
        output_dir=out_dir,
        tick_size=0.05,
        qty=75,
        entry_imbalance=0.6,
        exit_imbalance=0.15,
        min_microprice_edge_ticks=0.25,
        hold_ns=1_000_000,
        cooloff_ns=1_000_000,
    )

    summary = replay.summary.iloc[0]
    quarantine = replay.input_quarantine.iloc[0]
    assert int(quarantine["dropped_crossed_quote_rows"]) == 1
    assert int(quarantine["integrity_dropped_rows"]) == 1
    assert int(summary["input_total_rows"]) == 5
    assert int(summary["input_kept_rows"]) == 4
    assert int(summary["input_dropped_rows"]) == 1
    assert int(summary["input_integrity_dropped_rows"]) == 1
    assert int(summary["input_session_filtered_rows"]) == 0
    proof = evaluate_replay_dirs([out_dir])
    failed = proof.checks.loc[~proof.checks["passed"].astype(bool)]
    assert not proof.passed
    assert failed["check"].tolist() == [
        "input_integrity_dropped_rows"
    ]


def test_imbalance_replay_audits_inflight_position_rejections(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_replay"
    start = ns_ist("2026-06-10 09:15:00")
    pd.DataFrame(
        [
            {
                "ts": start + offset,
                "bid": 100.00,
                "ask": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
            }
            for offset in (0, 100_000, 200_000, 600_000)
        ]
    ).to_csv(ticks_path, index=False)

    replay = run_imbalance_replay(
        ticks_path=ticks_path,
        output_dir=out_dir,
        tick_size=0.05,
        qty=75,
        entry_imbalance=0.6,
        min_microprice_edge_ticks=0.25,
        order_latency_us=500.0,
        max_position_lots=1,
    )

    rejections = pd.read_csv(out_dir / "order_rejections.csv")
    summary = replay.summary.iloc[0]
    assert int(summary["pretrade_rejections"]) == 2
    assert int(summary["venue_rule_rejections"]) == 0
    assert int(summary["position_risk_rejections"]) == 2
    assert int(summary["self_cross_rejections"]) == 0
    assert rejections["reason"].tolist() == [
        "instrument_position_limit",
        "instrument_position_limit",
    ]
    assert rejections["projected_max"].tolist() == [150.0, 150.0]
    assert rejections["limit"].tolist() == [75.0, 75.0]


def test_cli_imbalance_replay_writes_summary(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)

    code = main(
        [
            "replay-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--exit-imbalance",
            "0.15",
            "--min-microprice-edge-ticks",
            "0.25",
            "--hold-ns",
            "1000000",
            "--cooloff-ns",
            "1000000",
        ]
    )

    summary = pd.read_csv(out_dir / "summary.csv")
    assert code == 0
    assert int(summary.loc[0, "fills"]) == 2
    assert (out_dir / "order_horizon_states.csv").exists()
    assert bool(summary.loc[0, "order_horizon_tracking_enabled"])
    assert int(summary.loc[0, "open_orders_at_replay_end"]) == 0
    assert int(summary.loc[0, "open_order_qty_at_replay_end"]) == 0


def test_cli_imbalance_replay_uses_candidate_config(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    candidate_dir = tmp_path / "edge_sweep"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)
    write_candidate(candidate_dir)

    code = main(
        [
            "replay-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--cooloff-ns",
            "1000000",
        ]
    )

    summary = pd.read_csv(out_dir / "summary.csv")
    markouts = pd.read_csv(out_dir / "markouts.csv")
    assert code == 0
    assert int(summary.loc[0, "fills"]) == 2
    assert set(markouts["horizon_ns"]) == {100_000}


def test_cli_imbalance_replay_inherits_us_market_and_tick_size_from_candidate(tmp_path):
    ticks_path = tmp_path / "us_ticks.csv"
    candidate_dir = tmp_path / "us_edge"
    out_dir = tmp_path / "us_imbalance_replay"
    us_imbalance_ticks().to_csv(ticks_path, index=False)
    write_us_candidate(candidate_dir)

    code = main(
        [
            "replay-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--instrument-kind",
            "EQ",
            "--lot-size",
            "1",
            "--qty",
            "1",
            "--cooloff-ns",
            "1000000",
        ]
    )

    summary = pd.read_csv(out_dir / "summary.csv")
    signals = pd.read_csv(out_dir / "signals.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert int(summary.loc[0, "fills"]) == 2
    assert float(summary.loc[0, "total_costs"]) == 0.02
    assert len(signals) == 2
    assert manifest["parameters"]["market"] == "us_equities_regular"
    assert manifest["parameters"]["tick_size"] == 0.01
    assert manifest["parameters"]["generic_costs"]["per_order_fee"] == 0.01
    assert int(summary.loc[0, "input_total_rows"]) == 5
    assert int(summary.loc[0, "input_kept_rows"]) == 4
    assert int(summary.loc[0, "input_dropped_rows"]) == 1
    assert int(summary.loc[0, "input_integrity_dropped_rows"]) == 0
    assert int(summary.loc[0, "input_session_filtered_rows"]) == 1
