import json
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from hft_cli import main
from reports.manifest import verify_experiment_manifest
from reports.proof import (
    ProofThresholds,
    evaluate_replay_dir,
)
from strategies.run_box_replay import (
    BOX_REPLAY_REQUIRED_ARTIFACTS,
    BOX_REPLAY_RUN_TYPE,
    run_box_replay,
)


def ns_ist(value: str) -> int:
    return pd.Timestamp(
        value,
        tz="Asia/Kolkata",
    ).value


def planted_box_chain():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist(
        "2026-06-10 09:15:00.000100"
    )
    rows = []
    for ts in (ts0, ts1):
        rows.extend(
            [
                {
                    "ts": ts,
                    "expiry": "2026-06-30",
                    "strike": 1000.0,
                    "call_bid": 51.0,
                    "call_ask": 52.0,
                    "call_bid_qty": 300,
                    "call_ask_qty": 300,
                    "put_bid": 45.0,
                    "put_ask": 46.0,
                    "put_bid_qty": 300,
                    "put_ask_qty": 300,
                },
                {
                    "ts": ts,
                    "expiry": "2026-06-30",
                    "strike": 1010.0,
                    "call_bid": 45.0,
                    "call_ask": 46.0,
                    "call_bid_qty": 300,
                    "call_ask_qty": 300,
                    "put_bid": 45.0,
                    "put_ask": 46.0,
                    "put_bid_qty": 300,
                    "put_ask_qty": 300,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_run_box_replay_writes_manifest_backed_four_leg_evidence(
    tmp_path,
):
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "box_replay"
    planted_box_chain().to_csv(chain_path, index=False)

    replay = run_box_replay(
        chain_path=chain_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        order_latency_us=50.0,
        signal_limit=1,
    )

    assert len(replay.signals) == 1
    assert replay.signals.iloc[0]["direction"] == "buy_box"
    assert replay.result.engine.orders_sent == 4
    assert len(replay.legging) == 1
    outcome = replay.legging.iloc[0]
    assert int(outcome["expected_order_count"]) == 4
    assert int(outcome["order_count"]) == 4
    assert int(outcome["fully_filled_leg_count"]) == 4
    assert not bool(outcome["partial"])
    assert bool(outcome["realized_edge_evaluable"])
    assert bool(outcome["realized_edge_positive"])
    assert float(outcome["realized_net_edge"]) > 0.0
    assert (
        outcome["low_call_instrument_id"]
        == "CALL_2026_06_30_1000_0"
    )
    assert (
        outcome["high_put_instrument_id"]
        == "PUT_2026_06_30_1010_0"
    )

    expected_artifacts = {
        "fills.csv",
        "feed_deliveries.csv",
        "order_submissions.csv",
        "ioc_arrival_audit.csv",
        "terminal_liquidations.csv",
        "equity.csv",
        "summary.csv",
        "pnl_decomposition.csv",
        "signals.csv",
        "legging.csv",
        "box_execution_guard.csv",
        "input_quarantine.csv",
        "manifest.json",
    }
    assert expected_artifacts.issubset(
        {path.name for path in out_dir.iterdir()}
    )
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=BOX_REPLAY_RUN_TYPE,
        required_artifacts=BOX_REPLAY_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    assert integrity.passed, integrity.error
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["run_type"] == "box_replay"
    assert set(manifest["inputs"]) == {"chain"}
    assert (
        manifest["parameters"]["latency_seed"]
        == 17
    )
    assert (
        manifest["parameters"]["fair_value_adjustment"]
        == 0.0
    )

    summary = replay.summary.iloc[0]
    assert int(summary["fills"]) == 4
    assert int(summary["input_dataset_count"]) == 1
    assert int(summary["input_total_rows"]) == 4
    assert int(summary["input_kept_rows"]) == 4
    assert bool(summary["box_execution_guard_enabled"])
    assert int(summary["box_execution_guard_attempts"]) >= 1
    assert (
        int(
            summary[
                "box_execution_guard_passed_attempts"
            ]
        )
        == 1
    )
    assert int(summary["box_execution_count"]) == 1
    assert int(summary["box_execution_complete_count"]) == 1
    assert int(summary["box_execution_incomplete_count"]) == 0
    assert (
        int(
            summary[
                "box_execution_realized_edge_evaluable_count"
            ]
        )
        == 1
    )
    assert (
        int(
            summary[
                "box_execution_realized_edge_positive_count"
            ]
        )
        == 1
    )
    assert (
        int(
            summary[
                "box_execution_order_timing_evaluable_legs"
            ]
        )
        == 4
    )
    assert (
        int(
            summary[
                "box_execution_order_timing_consistency_violations"
            ]
        )
        == 0
    )
    assert (
        int(
            summary[
                "box_execution_ioc_arrival_evaluable_legs"
            ]
        )
        == 4
    )
    assert (
        int(
            summary[
                "box_execution_ioc_arrival_consistency_violations"
            ]
        )
        == 0
    )
    assert bool(summary["box_latency_sampling_audit_enabled"])
    assert int(summary["box_feed_latency_bound_violations"]) == 0
    assert int(summary["box_order_latency_bound_violations"]) == 0


def test_run_box_replay_handles_no_executable_boxes(
    tmp_path,
):
    chain = planted_box_chain()
    chain.loc[
        chain["strike"].eq(1010.0),
        ["call_bid", "call_ask"],
    ] = [40.0, 41.0]
    chain_path = tmp_path / "chain.csv"
    chain.to_csv(chain_path, index=False)

    replay = run_box_replay(
        chain_path=chain_path,
        signal_limit=1,
    )

    assert replay.result.engine.orders_sent == 0
    assert replay.signals.empty
    assert replay.legging.empty
    assert replay.execution_guard.empty
    summary = replay.summary.iloc[0]
    assert int(summary["box_execution_guard_attempts"]) == 0
    assert int(summary["box_execution_count"]) == 0


def test_box_replay_proof_binds_four_leg_raw_evidence(
    tmp_path,
):
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "box_replay"
    planted_box_chain().to_csv(chain_path, index=False)
    run_box_replay(
        chain_path=chain_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        order_latency_us=50.0,
        signal_limit=1,
    )

    proof = evaluate_replay_dir(
        out_dir,
        thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    assert proof.passed
    metrics = proof.metrics.iloc[0]
    assert bool(metrics["box_execution_guard_enabled"])
    assert not bool(
        metrics["parity_execution_guard_enabled"]
    )
    assert int(metrics["box_execution_complete_count"]) == 1
    assert (
        int(
            metrics[
                "box_execution_fill_evidence_evaluable_legs"
            ]
        )
        == 4
    )
    assert (
        int(
            metrics[
                "box_execution_guard_execution_lineage_violations"
            ]
        )
        == 0
    )
    assert (
        float(
            metrics[
                "box_execution_min_realized_net_edge"
            ]
        )
        > 0.0
    )


def test_box_replay_proof_rejects_tampered_realized_edge(
    tmp_path,
):
    chain_path = tmp_path / "chain.csv"
    out_dir = tmp_path / "box_replay"
    planted_box_chain().to_csv(chain_path, index=False)
    run_box_replay(
        chain_path=chain_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        signal_limit=1,
    )
    legging_path = out_dir / "legging.csv"
    legging = pd.read_csv(legging_path)
    legging.loc[0, "realized_net_edge"] += 1.0
    legging.to_csv(legging_path, index=False)

    proof = evaluate_replay_dir(
        out_dir,
        thresholds=ProofThresholds(
            min_net_pnl=-1_000_000.0,
            min_fills=1,
        ),
    )

    assert not proof.passed
    failed = proof.checks.loc[
        ~proof.checks["passed"].astype(bool),
        "check",
    ].tolist()
    assert (
        "box_execution_realized_edge_consistency_violations"
        in failed
    )


def test_unified_cli_replay_box_forwards_execution_guards(
    tmp_path,
):
    fake_result = SimpleNamespace(
        summary=pd.DataFrame([{"fills": 0}])
    )
    with patch(
        "hft_cli.run_box_replay",
        return_value=fake_result,
    ) as replay:
        code = main(
            [
                "replay-box",
                "--chain",
                str(tmp_path / "chain.csv"),
                "--out",
                str(tmp_path / "out"),
                "--depth-fraction",
                "0.5",
                "--fair-value-adjustment",
                "0.25",
                "--feed-latency-us",
                "10",
                "--order-latency-us",
                "20",
                "--latency-jitter-us",
                "5",
                "--latency-seed",
                "99",
                "--max-signal-age-ns",
                "400000",
                "--max-leg-book-age-ns",
                "300000",
                "--max-leg-book-skew-ns",
                "200000",
                "--max-qty",
                "75",
            ]
        )

    assert code == 0
    kwargs = replay.call_args.kwargs
    assert kwargs["depth_fraction"] == 0.5
    assert kwargs["fair_value_adjustment"] == 0.25
    assert kwargs["feed_latency_us"] == 10.0
    assert kwargs["order_latency_us"] == 20.0
    assert kwargs["latency_jitter_us"] == 5.0
    assert kwargs["latency_seed"] == 99
    assert kwargs["max_signal_age_ns"] == 400_000
    assert kwargs["max_leg_book_age_ns"] == 300_000
    assert kwargs["max_leg_book_skew_ns"] == 200_000
    assert kwargs["max_qty"] == 75
