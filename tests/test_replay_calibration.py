import json

import pandas as pd

from hft_cli import main
from reports.replay_calibration import apply_fill_model_to_replay_params, write_calibrated_replay_plan


def fill_model_config(ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "tick_size": 0.05,
        "global": {
            "queue_conservatism": 4.0,
            "order_latency_us": 250.0,
            "slippage_ticks": 2.0,
            "min_edge_ticks": 3.0,
        },
        "by_instrument": [],
        "failed_checks": [] if ready else ["orders"],
    }


def write_fill_model(path, *, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    (path / "fill_model_config.json").write_text(
        json.dumps(fill_model_config(ready), indent=2) + "\n",
        encoding="utf-8",
    )


def test_fill_model_calibrates_leadlag_latency_and_trigger():
    report = apply_fill_model_to_replay_params(
        "leadlag",
        {"order_latency_us": 100.0, "trigger_ticks": 2.0},
        fill_model_config(),
    )

    assert report.ready
    assert report.params["order_latency_us"] == 250.0
    assert report.params["trigger_ticks"] == 3.0
    assert set(report.summary.iloc[0]["applied_fields"].split(";")) == {"order_latency_us", "trigger_ticks"}


def test_fill_model_calibrates_depth_without_loosening_existing_conservatism():
    parity = apply_fill_model_to_replay_params(
        "parity",
        {"order_latency_us": 0.0, "depth_fraction": 1.0},
        fill_model_config(),
    )
    box = apply_fill_model_to_replay_params(
        "box_replay",
        {"order_latency_us": 0.0, "depth_fraction": 1.0},
        fill_model_config(),
    )
    surface = apply_fill_model_to_replay_params(
        "surface_mm",
        {"order_latency_us": 500.0, "fill_depth_fraction": 0.1},
        fill_model_config(),
    )

    assert parity.params["order_latency_us"] == 250.0
    assert parity.params["depth_fraction"] == 0.25
    assert box.params == parity.params
    assert surface.params["order_latency_us"] == 500.0
    assert surface.params["fill_depth_fraction"] == 0.1


def test_fill_model_calibrates_imbalance_latency_and_edge():
    report = apply_fill_model_to_replay_params(
        "microprice_imbalance",
        {"order_latency_us": 100.0, "min_microprice_edge_ticks": 1.0},
        fill_model_config(),
    )

    assert report.ready
    assert report.params["order_latency_us"] == 250.0
    assert report.params["min_microprice_edge_ticks"] == 3.0
    assert set(report.summary.iloc[0]["applied_fields"].split(";")) == {
        "order_latency_us",
        "min_microprice_edge_ticks",
    }


def test_write_calibrated_replay_plan_outputs_artifacts(tmp_path):
    fill_model_dir = tmp_path / "fill_model"
    out_dir = tmp_path / "calibrated"
    write_fill_model(fill_model_dir)

    report = write_calibrated_replay_plan(
        strategy="surface_quotes",
        fill_model_path=fill_model_dir,
        output_dir=out_dir,
        base_params={"edge_ticks": 1.0},
    )

    assert report.output_dir == out_dir
    assert report.params["edge_ticks"] == 3.0
    assert (out_dir / "calibrated_replay_params.json").exists()
    assert (out_dir / "calibrated_replay_checks.csv").exists()
    assert (out_dir / "calibrated_replay_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_calibrated_replay_plan_fails_on_unready_fill_model(tmp_path):
    fill_model_dir = tmp_path / "fill_model"
    out_dir = tmp_path / "calibrated"
    write_fill_model(fill_model_dir, ready=False)

    code = main(
        [
            "plan-calibrated-replay",
            "--strategy",
            "leadlag",
            "--fill-model",
            str(fill_model_dir),
            "--order-latency-us",
            "10",
            "--trigger-ticks",
            "2",
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "calibrated_replay_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
