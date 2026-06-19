import json

import pandas as pd

from hft_cli import main
from reports.fill_model_drift import (
    FillModelDriftThresholds,
    evaluate_fill_model_drift,
    write_fill_model_drift_report,
)


def fill_model_config(
    *,
    ready=True,
    queue=2.0,
    latency=100.0,
    slippage=1.0,
    edge=2.0,
    instruments=True,
):
    config = {
        "schema_version": 1,
        "ready": ready,
        "tick_size": 0.05,
        "global": {
            "queue_conservatism": queue,
            "order_latency_us": latency,
            "slippage_ticks": slippage,
            "min_edge_ticks": edge,
        },
        "failed_checks": [] if ready else ["orders"],
    }
    config["by_instrument"] = (
        [
            {
                "instrument_id": "NIFTY_C_22000",
                "queue_conservatism": queue,
                "order_latency_us": latency,
                "slippage_ticks": slippage,
                "min_edge_ticks": edge,
            }
        ]
        if instruments
        else []
    )
    return config


def write_fill_model(path, config):
    path.mkdir(parents=True, exist_ok=True)
    (path / "fill_model_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def test_fill_model_drift_passes_small_changes():
    report = evaluate_fill_model_drift(
        fill_model_config(queue=2.0, latency=100.0, slippage=1.0, edge=2.0),
        fill_model_config(queue=2.2, latency=150.0, slippage=1.5, edge=2.5),
        thresholds=FillModelDriftThresholds(
            max_queue_conservatism_increase_pct=0.25,
            max_order_latency_increase_us=100.0,
            max_slippage_tick_increase=1.0,
            max_min_edge_tick_increase=1.0,
        ),
    )

    assert report.passed
    assert report.summary.iloc[0]["recommendation"] == "reuse_existing_proof_assumptions"
    assert report.summary.iloc[0]["global_order_latency_us_delta"] == 50.0
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.summary.iloc[0]["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty


def test_fill_model_drift_blocks_large_queue_and_latency_worsening():
    report = evaluate_fill_model_drift(
        fill_model_config(queue=2.0, latency=100.0),
        fill_model_config(queue=3.0, latency=260.0),
        thresholds=FillModelDriftThresholds(
            max_queue_conservatism_increase_pct=0.25,
            max_order_latency_increase_us=100.0,
        ),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"queue_conservatism_delta_pct", "order_latency_us_delta"} <= failed
    summary = report.summary.iloc[0]
    assert int(summary["action_queue_count"]) == 2
    assert int(summary["blocked_action_count"]) == 2
    assert summary["next_gate"] == "compare-fill-models"
    assert summary["next_gate_help_command"] == "python -m hft_cli compare-fill-models --help"
    assert report.action_queue is not None
    assert set(report.action_queue["check"]) == {"queue_conservatism_delta_pct", "order_latency_us_delta"}
    assert report.action_queue.loc[0, "component"] == "queue_model"


def test_write_fill_model_drift_outputs_artifacts(tmp_path):
    baseline = tmp_path / "baseline"
    latest = tmp_path / "latest"
    out_dir = tmp_path / "drift"
    write_fill_model(baseline, fill_model_config())
    write_fill_model(latest, fill_model_config(queue=2.1))

    report = write_fill_model_drift_report(
        baseline_path=baseline,
        latest_path=latest,
        output_dir=out_dir,
    )

    assert report.output_dir == out_dir
    assert (out_dir / "fill_model_drift.csv").exists()
    assert (out_dir / "fill_model_drift_checks.csv").exists()
    assert (out_dir / "fill_model_drift_summary.csv").exists()
    assert (out_dir / "fill_model_drift_action_queue.csv").exists()
    assert (out_dir / "fill_model_drift_config.json").exists()
    assert (out_dir / "fill_model_drift_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "fill_model_drift_action_queue.csv")
    config = json.loads((out_dir / "fill_model_drift_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "fill_model_drift_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert queue.empty
    assert config["passed"] is True
    assert config["action_queue_count"] == 0
    assert config["primary_action"] == {}
    assert "# Fill Model Drift Runbook" in runbook
    assert "No fill-model drift actions." in runbook
    assert "fill_model_drift_action_queue.csv" in artifact_paths
    assert "fill_model_drift_config.json" in artifact_paths
    assert "fill_model_drift_runbook.md" in artifact_paths


def test_cli_fill_model_drift_can_fail_on_new_instrument_set(tmp_path):
    baseline = tmp_path / "baseline"
    latest = tmp_path / "latest"
    out_dir = tmp_path / "drift"
    write_fill_model(baseline, fill_model_config(instruments=False))
    write_fill_model(latest, fill_model_config(instruments=True))

    code = main(
        [
            "compare-fill-models",
            "--baseline",
            str(baseline),
            "--latest",
            str(latest),
            "--out",
            str(out_dir),
            "--require-same-instruments",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "fill_model_drift_summary.csv")
    queue = pd.read_csv(out_dir / "fill_model_drift_action_queue.csv")
    config = json.loads((out_dir / "fill_model_drift_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "fill_model_drift_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert int(summary.loc[0, "blocked_action_count"]) == 1
    assert summary.loc[0, "primary_blocker_check"] == "instrument_set_unchanged"
    assert queue.loc[0, "check"] == "instrument_set_unchanged"
    assert queue.loc[0, "component"] == "instrument_coverage"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli compare-fill-models --help"
    assert config["primary_action"]["check"] == "instrument_set_unchanged"
    assert "instrument_set_unchanged" in runbook


def test_cli_fill_model_drift_can_fail_on_actions(tmp_path):
    baseline = tmp_path / "baseline"
    latest = tmp_path / "latest"
    out_dir = tmp_path / "drift"
    write_fill_model(baseline, fill_model_config(queue=2.0))
    write_fill_model(latest, fill_model_config(queue=3.0))

    code = main(
        [
            "compare-fill-models",
            "--baseline",
            str(baseline),
            "--latest",
            str(latest),
            "--out",
            str(out_dir),
            "--max-queue-conservatism-increase-pct",
            "0.25",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "fill_model_drift_summary.csv")
    queue = pd.read_csv(out_dir / "fill_model_drift_action_queue.csv")
    assert code == 2
    assert int(summary.loc[0, "action_queue_count"]) == 1
    assert queue.loc[0, "check"] == "queue_conservatism_delta_pct"
    assert queue.loc[0, "component"] == "queue_model"
