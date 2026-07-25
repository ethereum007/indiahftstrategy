from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds, evaluate_replay_dirs
from strategies.run_parity_replay import run_parity_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_run_parity_replay_writes_outputs_and_executes_signal(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for ts in [ts0, ts1]
        ]
    )
    futures = pd.DataFrame(
        [
            {"ts": ts, "bid": 1100.0, "ask": 1101.0, "bid_qty": 300, "ask_qty": 300}
            for ts in [ts0, ts1]
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "replay"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    replay = run_parity_replay(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        order_latency_us=50.0,
        signal_limit=1,
    )

    assert not replay.signals.empty
    assert replay.result.engine.orders_sent == 3
    assert replay.legging.iloc[0]["fill_count"] == 3
    assert not bool(replay.legging.iloc[0]["partial"])
    assert bool(replay.legging.iloc[0]["routing_complete"])
    assert bool(replay.legging.iloc[0]["fills_complete"])
    assert int(replay.legging.iloc[0]["fully_filled_leg_count"]) == 3
    assert int(replay.legging.iloc[0]["unfilled_leg_count"]) == 0
    assert replay.summary.iloc[0]["fills"] == 3
    assert (out_dir / "fills.csv").exists()
    assert (out_dir / "order_submissions.csv").exists()
    assert (out_dir / "terminal_liquidations.csv").exists()
    assert (out_dir / "equity.csv").exists()
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "pnl_decomposition.csv").exists()
    assert (out_dir / "spread_pairs.csv").exists()
    assert (out_dir / "spread_summary.csv").exists()
    assert (out_dir / "residual_inventory.csv").exists()
    assert (out_dir / "fills_by_regime.csv").exists()
    assert (out_dir / "equity_by_regime.csv").exists()
    assert (out_dir / "signals.csv").exists()
    assert (out_dir / "legging.csv").exists()
    assert (out_dir / "parity_execution_guard.csv").exists()
    assert (out_dir / "input_quarantine.csv").exists()
    assert (out_dir / "parity_futures_join_audit.csv").exists()
    assert (out_dir / "manifest.json").exists()
    input_quarantine = pd.read_csv(out_dir / "input_quarantine.csv")
    assert input_quarantine["dataset"].tolist() == ["chain", "futures"]
    assert input_quarantine["dataset_type"].tolist() == [
        "option_chain",
        "l1_ticks",
    ]
    summary = replay.summary.iloc[0]
    assert bool(summary["input_quarantine_tracking_enabled"])
    assert int(summary["input_dataset_count"]) == 2
    assert int(summary["input_total_rows"]) == 4
    assert int(summary["input_kept_rows"]) == 4
    assert int(summary["input_integrity_dropped_rows"]) == 0
    assert int(summary["input_empty_datasets"]) == 0
    assert bool(summary["parity_futures_asof_freshness_enabled"])
    assert int(summary["parity_futures_max_quote_age_ns"]) == 1_000_000
    assert int(summary["parity_futures_join_rows"]) == 2
    assert int(summary["parity_futures_fresh_join_rows"]) == 2
    assert int(summary["parity_futures_stale_join_rows"]) == 0
    assert int(summary["parity_futures_unmatched_join_rows"]) == 0
    assert int(summary["parity_futures_signal_count"]) == 1
    assert int(summary["parity_futures_signals_without_age"]) == 0
    assert int(summary["parity_futures_signal_age_violations"]) == 0
    assert int(summary["parity_futures_max_signal_age_ns"]) == 0
    assert set(replay.futures_join_audit["reason"]) == {"fresh"}
    assert bool(summary["parity_execution_guard_enabled"])
    assert int(summary["parity_execution_max_leg_book_age_ns"]) == 1_000_000
    assert int(summary["parity_execution_max_leg_book_skew_ns"]) == 1_000_000
    assert int(summary["parity_execution_guard_attempts"]) == 3
    assert int(summary["parity_execution_guard_passed_attempts"]) == 1
    assert int(summary["parity_execution_guard_deferred_attempts"]) == 2
    assert bool(
        summary["parity_execution_signal_source_causality_enabled"]
    )
    assert int(
        summary["parity_execution_signal_source_checks"]
    ) == 1
    assert int(
        summary["parity_execution_signal_source_ready_attempts"]
    ) == 1
    assert int(
        summary["parity_execution_signal_source_pending_attempts"]
    ) == 0
    assert int(
        summary[
            "parity_execution_signal_source_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_signal_source_consistency_violations"
        ]
    ) == 0
    assert int(
        summary["parity_execution_max_signal_source_lag_ns"]
    ) == 0
    assert bool(
        summary["parity_execution_edge_revalidation_enabled"]
    )
    assert int(
        summary["parity_execution_edge_revalidation_attempts"]
    ) == 1
    assert int(
        summary["parity_execution_edge_revalidation_passed_attempts"]
    ) == 1
    assert int(
        summary["parity_execution_edge_revalidation_rejected_attempts"]
    ) == 0
    assert int(
        summary[
            "parity_execution_edge_revalidation_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_edge_revalidation_consistency_violations"
        ]
    ) == 0
    assert float(
        summary["parity_execution_min_routed_net_edge"]
    ) > 7_800.0
    assert float(
        summary["parity_execution_max_observed_edge_decay"]
    ) == 0.0
    assert bool(summary["parity_execution_realized_edge_enabled"])
    assert int(
        summary["parity_execution_realized_edge_evaluable_count"]
    ) == 1
    assert int(
        summary["parity_execution_realized_edge_positive_count"]
    ) == 1
    assert int(
        summary["parity_execution_realized_edge_nonpositive_count"]
    ) == 0
    assert int(
        summary[
            "parity_execution_realized_edge_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_realized_edge_consistency_violations"
        ]
    ) == 0
    assert float(
        summary["parity_execution_min_realized_net_edge"]
    ) > 7_800.0
    assert float(
        summary["parity_execution_total_realized_net_edge"]
    ) == float(
        summary["parity_execution_min_realized_net_edge"]
    )
    assert float(
        summary[
            "parity_execution_min_realized_vs_decision_net_edge"
        ]
    ) == 0.0
    assert int(summary["parity_execution_max_fill_span_ns"]) == 0
    assert int(
        summary["parity_execution_fill_timing_evaluable_count"]
    ) == 1
    assert int(
        summary["parity_execution_negative_fill_latency_count"]
    ) == 0
    assert int(
        summary["parity_execution_min_first_fill_latency_ns"]
    ) == 100_000
    assert int(
        summary["parity_execution_max_completion_latency_ns"]
    ) == 100_000
    assert bool(
        summary["parity_execution_order_timing_enabled"]
    )
    assert int(
        summary["parity_execution_order_timing_evaluable_legs"]
    ) == 3
    assert int(
        summary[
            "parity_execution_order_timing_missing_evidence_legs"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_order_timing_consistency_violations"
        ]
    ) == 0
    assert int(
        summary["parity_execution_pre_activation_fill_legs"]
    ) == 0
    assert int(
        summary[
            "parity_execution_min_activation_to_first_fill_latency_ns"
        ]
    ) == 50_000
    assert int(
        summary[
            "parity_execution_max_activation_to_completion_latency_ns"
        ]
    ) == 50_000
    order_submissions = pd.read_csv(
        out_dir / "order_submissions.csv"
    )
    assert len(order_submissions) == 3
    assert set(order_submissions["order_type"]) == {"IOC"}
    assert order_submissions["ts_sent_ns"].nunique() == 1
    assert (
        order_submissions["ts_active_ns"]
        - order_submissions["ts_sent_ns"]
    ).eq(50_000).all()
    assert bool(
        summary["parity_execution_ioc_batch_preflight_enabled"]
    )
    assert int(
        summary["parity_execution_ioc_batch_preflight_attempts"]
    ) == 1
    assert int(
        summary[
            "parity_execution_ioc_batch_preflight_passed_attempts"
        ]
    ) == 1
    assert int(
        summary[
            "parity_execution_ioc_batch_preflight_rejected_attempts"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_batch_preflight_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_batch_preflight_consistency_violations"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_visible_not_marketable_attempts"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_visible_capacity_shortfall_attempts"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_visible_capacity_missing_evidence_rows"
        ]
    ) == 0
    assert int(
        summary[
            "parity_execution_ioc_visible_capacity_consistency_violations"
        ]
    ) == 0
    assert float(
        summary[
            "parity_execution_min_routed_visible_fill_ratio"
        ]
    ) == 4.0
    assert int(summary["parity_execution_signal_expiry_events"]) == 0
    assert int(summary["parity_execution_stale_book_attempts"]) == 0
    assert int(summary["parity_execution_negative_book_age_attempts"]) == 0
    assert int(summary["parity_execution_skew_attempts"]) == 0
    assert int(summary["parity_execution_routing_complete_attempts"]) == 1
    assert int(summary["parity_execution_routing_incomplete_attempts"]) == 0
    assert int(summary["parity_execution_guard_passed_missing_age_rows"]) == 0
    assert int(summary["parity_execution_guard_age_violations"]) == 0
    assert int(summary["parity_execution_guard_skew_violations"]) == 0
    assert int(summary["parity_execution_max_routed_book_age_ns"]) == 0
    assert int(summary["parity_execution_max_routed_book_skew_ns"]) == 0
    assert int(summary["parity_execution_count"]) == 1
    assert int(summary["parity_execution_complete_count"]) == 1
    assert int(summary["parity_execution_incomplete_count"]) == 0
    assert int(summary["parity_execution_route_rejected_legs"]) == 0
    assert int(summary["parity_execution_unfilled_legs"]) == 0
    assert set(replay.execution_guard["guard_reason"]) == {
        "missing_leg_book",
        "ready",
    }
    routed_guard = replay.execution_guard.loc[
        replay.execution_guard["guard_passed"]
    ].iloc[0]
    assert bool(routed_guard["edge_revalidation_checked"])
    assert int(routed_guard["edge_revalidation_qty"]) == 75
    assert float(routed_guard["decision_edge_per_unit"]) == 105.0
    assert float(routed_guard["decision_gross_edge"]) == 7_875.0
    assert float(routed_guard["decision_total_cost"]) > 0.0
    assert float(routed_guard["decision_net_edge"]) == (
        float(routed_guard["decision_gross_edge"])
        - float(routed_guard["decision_total_cost"])
    )
    outcome = replay.legging.iloc[0]
    assert bool(outcome["realized_edge_evaluable"])
    assert bool(outcome["realized_edge_positive"])
    assert float(outcome["call_fill_vwap"]) == 55.0
    assert float(outcome["put_fill_vwap"]) == 60.0
    assert float(outcome["future_fill_vwap"]) == 1100.0
    assert float(outcome["realized_edge_per_unit"]) == 105.0
    assert float(outcome["realized_total_cost"]) == (
        float(outcome["call_fill_cost"])
        + float(outcome["put_fill_cost"])
        + float(outcome["future_fill_cost"])
    )
    assert float(outcome["realized_net_edge"]) == float(
        routed_guard["decision_net_edge"]
    )
    assert float(outcome["realized_vs_decision_net_edge"]) == 0.0
    assert bool(routed_guard["ioc_batch_preflight_enabled"])
    assert bool(routed_guard["ioc_batch_preflight_attempted"])
    assert bool(routed_guard["ioc_batch_preflight_passed"])
    assert routed_guard["ioc_batch_preflight_reason"] == "passed"
    assert bool(
        routed_guard[
            "ioc_batch_preflight_visible_capacity_checked"
        ]
    )
    assert float(
        routed_guard[
            "ioc_batch_preflight_min_visible_fill_ratio"
        ]
    ) == 4.0


def test_run_parity_replay_proves_reverse_realized_package_edge(
    tmp_path,
):
    timestamps = [
        ns_ist("2026-06-10 09:15:00"),
        ns_ist("2026-06-10 09:15:00.000100"),
    ]
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for ts in timestamps
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": ts,
                "bid": 979.0,
                "ask": 980.0,
                "bid_qty": 300,
                "ask_qty": 300,
            }
            for ts in timestamps
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "reverse_replay"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    replay = run_parity_replay(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        signal_limit=1,
    )
    proof = evaluate_replay_dirs(
        [out_dir],
        thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    outcome = replay.legging.iloc[0]
    proof_metrics = proof.metrics.iloc[0]
    assert replay.signals.iloc[0]["direction"] == (
        "sell_synthetic_buy_future"
    )
    assert int(outcome["call_side"]) == -1
    assert int(outcome["put_side"]) == 1
    assert int(outcome["future_side"]) == 1
    assert float(outcome["realized_edge_per_unit"]) == 13.0
    assert float(outcome["realized_net_edge"]) > 900.0
    assert bool(outcome["realized_edge_positive"])
    assert proof.passed
    assert int(
        proof_metrics[
            "parity_execution_realized_edge_evaluable_count"
        ]
    ) == 1
    assert int(
        proof_metrics[
            "parity_execution_realized_edge_consistency_violations"
        ]
    ) == 0
    assert int(
        proof_metrics[
            "parity_execution_fill_timing_evaluable_count"
        ]
    ) == 1
    assert int(
        proof_metrics[
            "parity_execution_negative_fill_latency_count"
        ]
    ) == 0
    assert int(
        proof_metrics[
            "parity_execution_min_first_fill_latency_ns"
        ]
    ) == 100_000
    assert int(
        proof_metrics[
            "parity_execution_max_completion_latency_ns"
        ]
    ) == 100_000
    assert int(
        proof_metrics[
            "parity_execution_order_timing_evaluable_legs"
        ]
    ) == 3
    assert int(
        proof_metrics[
            "parity_execution_pre_activation_fill_legs"
        ]
    ) == 0
    assert int(
        proof_metrics[
            "parity_execution_min_activation_to_first_fill_latency_ns"
        ]
    ) == 100_000
    assert int(
        proof_metrics[
            "parity_execution_max_activation_to_completion_latency_ns"
        ]
    ) == 100_000
    assert float(
        proof_metrics["parity_execution_min_realized_net_edge"]
    ) == float(outcome["realized_net_edge"])


def test_run_parity_replay_rejects_edge_that_decays_during_feed_latency(
    tmp_path,
):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for ts in [ts0, ts1]
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": ts0,
                "bid": 1100.0,
                "ask": 1101.0,
                "bid_qty": 300,
                "ask_qty": 300,
            },
            {
                "ts": ts1 - 1,
                "bid": 990.0,
                "ask": 991.0,
                "bid_qty": 300,
                "ask_qty": 300,
            },
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    replay = run_parity_replay(
        chain_path=chain_path,
        futures_path=futures_path,
        depth_fraction=0.25,
        asof_latency_ns=100_000,
        feed_latency_us=200.0,
        signal_limit=1,
    )

    summary = replay.summary.iloc[0]
    edge_rejections = replay.execution_guard.loc[
        replay.execution_guard["guard_reason"].eq(
            "execution_edge_below_threshold"
        )
    ]
    assert replay.signals.iloc[0]["direction"] == (
        "buy_synthetic_sell_future"
    )
    assert replay.result.engine.orders_sent == 0
    assert replay.result.fills.empty
    assert not edge_rejections.empty
    assert (
        edge_rejections["decision_net_edge"].astype(float) < 0.0
    ).all()
    assert int(
        summary["parity_execution_edge_revalidation_attempts"]
    ) >= 1
    assert int(
        summary["parity_execution_signal_source_pending_attempts"]
    ) >= 1
    assert int(
        summary["parity_execution_max_signal_source_lag_ns"]
    ) == 100_000
    assert int(
        summary["parity_execution_edge_revalidation_passed_attempts"]
    ) == 0
    assert int(
        summary["parity_execution_edge_revalidation_rejected_attempts"]
    ) == int(
        summary["parity_execution_edge_revalidation_attempts"]
    )
    assert float(
        summary["parity_execution_max_observed_edge_decay"]
    ) > 0.0
    assert int(
        summary["parity_execution_ioc_batch_preflight_attempts"]
    ) == 0


def test_run_parity_replay_quarantines_stale_futures_join(tmp_path):
    future_ts = ns_ist("2026-06-10 09:15:00")
    chain_ts = ns_ist("2026-06-10 09:15:00.000100")
    chain = pd.DataFrame(
        [
            {
                "ts": chain_ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": future_ts,
                "bid": 1100.0,
                "ask": 1101.0,
                "bid_qty": 300,
                "ask_qty": 300,
            }
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "replay"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    replay = run_parity_replay(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        max_futures_quote_age_ns=99_999,
        depth_fraction=0.25,
    )

    assert replay.signals.empty
    assert replay.futures_join_audit.iloc[0]["reason"] == (
        "stale_future_quote"
    )
    assert int(
        replay.futures_join_audit.iloc[0]["future_asof_age_ns"]
    ) == 100_000
    summary = replay.summary.iloc[0]
    assert int(summary["parity_futures_join_rows"]) == 1
    assert int(summary["parity_futures_fresh_join_rows"]) == 0
    assert int(summary["parity_futures_stale_join_rows"]) == 1
    assert int(summary["parity_futures_signal_count"]) == 0
    assert int(summary["parity_futures_signal_age_violations"]) == 0
    assert int(summary["parity_execution_guard_attempts"]) == 0
    assert int(summary["parity_execution_count"]) == 0
    assert replay.execution_guard.empty


def test_unified_cli_replay_parity_forwards_execution_guard_limits(
    tmp_path,
):
    fake_result = SimpleNamespace(summary=pd.DataFrame([{"fills": 0}]))
    with patch(
        "hft_cli.run_parity_replay",
        return_value=fake_result,
    ) as replay:
        code = main(
            [
                "replay-parity",
                "--chain",
                str(tmp_path / "chain.csv"),
                "--futures",
                str(tmp_path / "futures.csv"),
                "--out",
                str(tmp_path / "out"),
                "--max-signal-age-ns",
                "400000",
                "--max-leg-book-age-ns",
                "300000",
                "--max-leg-book-skew-ns",
                "200000",
            ]
        )

    assert code == 0
    kwargs = replay.call_args.kwargs
    assert kwargs["max_signal_age_ns"] == 400_000
    assert kwargs["max_leg_book_age_ns"] == 300_000
    assert kwargs["max_leg_book_skew_ns"] == 200_000
