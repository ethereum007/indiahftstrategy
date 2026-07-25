from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from hft_cli import main
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
