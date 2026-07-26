import json

import pandas as pd
import pytest

from hft_cli import main
from reports.manifest import verify_experiment_manifest
from reports.proof import verify_proof_report
from strategies.run_box_sweep import (
    BOX_SWEEP_REQUIRED_ARTIFACTS,
    BOX_SWEEP_RUN_TYPE,
    run_box_sweep,
)


def _ns_ist(value: str) -> int:
    return pd.Timestamp(
        value,
        tz="Asia/Kolkata",
    ).value


def _write_box_chain(tmp_path):
    timestamps = [
        _ns_ist("2026-06-10 09:15:00"),
        _ns_ist("2026-06-10 09:15:00.000100"),
    ]
    rows = []
    for ts in timestamps:
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
    path = tmp_path / "chain.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_box_sweep_proves_seed_robust_four_leg_execution(
    tmp_path,
):
    chain_path = _write_box_chain(tmp_path)
    out_dir = tmp_path / "box_sweep"

    result = run_box_sweep(
        chain_path=chain_path,
        output_dir=out_dir,
        depth_fraction_values=[0.25],
        fair_value_adjustment_values=[0.0],
        feed_latency_us_values=[10.0],
        order_latency_us_values=[10.0],
        latency_jitter_us_values=[5.0],
        latency_seed_values=[101, 202],
        signal_limit=1,
    )

    assert len(result.runs) == 2
    assert result.runs["proof_passed"].all()
    assert (
        result.runs["box_execution_complete_count"] == 1
    ).all()
    assert (
        result.runs[
            "box_execution_fill_evidence_evaluable_legs"
        ]
        == 4
    ).all()
    assert (
        result.runs[
            "box_execution_realized_edge_consistency_violations"
        ]
        == 0
    ).all()
    assert (
        result.runs["parity_execution_guard_enabled"]
        == False
    ).all()
    robustness = result.seed_robustness.iloc[0]
    assert robustness["latency_seed_values"] == "101,202"
    assert int(robustness["latency_seed_runs"]) == 2
    assert int(robustness["latency_seed_passed_runs"]) == 2
    assert bool(robustness["latency_seed_group_passed"])
    assert (
        int(robustness["latency_seed_bound_violations"])
        == 0
    )
    summary = result.summary.iloc[0]
    assert int(summary["scenario_count"]) == 2
    assert int(summary["passed_scenarios"]) == 2
    assert int(summary["total_complete_executions"]) == 2
    assert float(summary["min_package_realized_net_edge"]) > 0
    assert verify_proof_report(out_dir / "proof").verified

    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=BOX_SWEEP_RUN_TYPE,
        required_artifacts=BOX_SWEEP_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    assert integrity.passed, integrity.error
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["parameters"]["latency_seed"] is None
    assert manifest["parameters"]["latency_seed_values"] == [
        101,
        202,
    ]


def test_box_sweep_rejects_duplicate_latency_seeds(tmp_path):
    chain_path = _write_box_chain(tmp_path)

    with pytest.raises(
        ValueError,
        match="latency_seed_values must be unique",
    ):
        run_box_sweep(
            chain_path=chain_path,
            output_dir=tmp_path / "duplicate",
            depth_fraction_values=[0.25],
            fair_value_adjustment_values=[0.0],
            feed_latency_us_values=[0.0],
            order_latency_us_values=[0.0],
            latency_seed_values=[7, 7],
        )


def test_unified_cli_sweep_box_runs_proof_pipeline(tmp_path):
    chain_path = _write_box_chain(tmp_path)
    out_dir = tmp_path / "cli_box_sweep"

    code = main(
        [
            "sweep-box",
            "--chain",
            str(chain_path),
            "--out",
            str(out_dir),
            "--depth-fraction",
            "0.25",
            "--fair-value-adjustment",
            "0",
            "--feed-latency-us",
            "10",
            "--order-latency-us",
            "10",
            "--latency-jitter-us",
            "5",
            "--latency-seeds",
            "11",
            "22",
            "--signal-limit",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 0
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "proof" / "proof_checks.csv").exists()
