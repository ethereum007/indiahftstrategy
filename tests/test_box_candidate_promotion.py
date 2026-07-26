import json

import pandas as pd

from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.parity_candidate_promotion import (
    write_parity_candidate_promotion,
)
from reports.parity_edge import write_parity_edge_audit
from reports.parity_launch_pipeline import (
    ParityLaunchPipelineConfig,
    write_parity_launch_pipeline,
)
from reports.parity_order_plan import (
    ParityOrderPlanConfig,
    build_parity_order_plan,
)
from scanners.run_parity_box import run_scan
from strategies.run_box_sweep import (
    BOX_SWEEP_RUN_TYPE,
    run_box_sweep,
)


def _ns_ist(value: str) -> int:
    return pd.Timestamp(
        value,
        tz="Asia/Kolkata",
    ).value


def _write_market_data(root):
    timestamps = [
        _ns_ist("2026-06-10 09:15:00"),
        _ns_ist("2026-06-10 09:15:00.000100"),
    ]
    chain_rows = []
    for ts in timestamps:
        chain_rows.extend(
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
    chain_path = root / "chain.csv"
    futures_path = root / "futures.csv"
    pd.DataFrame(chain_rows).to_csv(
        chain_path,
        index=False,
    )
    pd.DataFrame(
        [
            {
                "ts": ts,
                "bid": 1006.0,
                "ask": 1007.0,
                "bid_qty": 300,
                "ask_qty": 300,
            }
            for ts in timestamps
        ]
    ).to_csv(futures_path, index=False)
    return chain_path, futures_path


def _write_box_research_pipeline(root):
    chain_path, futures_path = _write_market_data(root)
    scan_dir = root / "scan"
    edge_dir = root / "edge"
    sweep_dir = root / "sweep"
    run_scan(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=scan_dir,
        depth_fraction=0.25,
        fair_value_adjustment=0.0,
    )
    edge = write_parity_edge_audit(
        scan_dir,
        output_dir=edge_dir,
    )
    assert edge.passed
    sweep = run_box_sweep(
        chain_path=chain_path,
        output_dir=sweep_dir,
        depth_fraction_values=[0.25],
        fair_value_adjustment_values=[0.0],
        feed_latency_us_values=[10.0],
        order_latency_us_values=[10.0],
        latency_jitter_us_values=[5.0],
        latency_seed_values=[101, 202],
        signal_limit=1,
    )
    assert sweep.proof.passed
    return (
        chain_path,
        scan_dir,
        edge_dir,
        sweep_dir,
        sweep,
    )


def _refresh_manifest(
    directory,
    *,
    chain_path,
    parameter_updates=None,
):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    inputs = {"chain": chain_path}
    parameters = dict(manifest["parameters"])
    parameters.update(parameter_updates or {})
    write_experiment_manifest(
        directory,
        run_type=manifest["run_type"],
        parameters=parameters,
        inputs=inputs,
        extra=manifest.get("extra"),
    )


def test_box_sweep_promotes_exact_worst_seed_execution(
    tmp_path,
):
    (
        _,
        scan_dir,
        edge_dir,
        sweep_dir,
        sweep,
    ) = _write_box_research_pipeline(tmp_path)
    promotion_dir = tmp_path / "promotion"

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=promotion_dir,
    )

    assert report.ready
    candidate = report.candidate.iloc[0]
    assert candidate["leg_family"] == "box"
    assert candidate["direction"] == "buy_box"
    assert candidate["sweep_best_run"] == (
        sweep.seed_robustness.iloc[0][
            "latency_seed_worst_run"
        ]
    )
    assert bool(candidate["selected_replay_manifest_current"])
    assert bool(candidate["selected_replay_source_match"])
    assert bool(candidate["selected_replay_parameters_match"])
    assert int(candidate["candidate_replay_signal_match_count"]) == 1
    assert int(candidate["candidate_replay_guard_passed_attempts"]) == 1
    assert bool(candidate["candidate_replay_execution_complete"])
    assert bool(candidate["candidate_replay_realized_edge_positive"])
    assert float(
        candidate["candidate_replay_realized_net_edge"]
    ) > 0.0
    config = report.candidate_config
    assert config["replay_defaults"]["fair_value_adjustment"] == 0.0
    assert (
        config["metrics"][
            "latency_seed_worst_total_realized_net_edge"
        ]
        > 0.0
    )

    order_plan = build_parity_order_plan(
        report.summary,
        config,
        config=ParityOrderPlanConfig(
            max_order_qty=75,
            max_notional=1_000_000,
        ),
    )
    assert order_plan.ready
    assert int(order_plan.summary.iloc[0]["orders"]) == 4
    assert set(order_plan.orders["leg_role"]) == {
        "LOW_CALL",
        "LOW_PUT",
        "HIGH_CALL",
        "HIGH_PUT",
    }
    manifest = json.loads(
        (promotion_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["extra"]["sweep_leg_family"] == "box"
    assert (
        manifest["extra"]["selected_replay_run_type"]
        == "box_replay"
    )
    integrity = verify_experiment_manifest(
        promotion_dir / "manifest.json",
        expected_run_type="promotion_report",
        required_artifacts=(
            "promotion_candidate.csv",
            "promotion_checks.csv",
            "promotion_summary.csv",
            "candidate_config.json",
        ),
        require_input_fingerprints=True,
    )
    assert integrity.passed, integrity.error

    launch_dir = tmp_path / "launch"
    launch = write_parity_launch_pipeline(
        promotion_dir,
        output_dir=launch_dir,
        config=ParityLaunchPipelineConfig(
            adapter="arrow_money",
            mode="shadow",
            route_tag="box_shadow",
            require_reviewed_schema=False,
            max_order_qty=75,
            max_notional=1_000_000,
            max_orders=4,
        ),
    )
    assert launch.ready
    assert launch.summary.iloc[0]["leg_family"] == "box"
    assert bool(
        launch.summary.iloc[0][
            "order_plan_promotion_manifest_current"
        ]
    )
    assert launch.order_plan is not None
    assert int(
        launch.order_plan.summary.iloc[0]["orders"]
    ) == 4
    assert launch.staging is not None
    assert int(
        launch.staging.summary.iloc[0]["accepted_orders"]
    ) == 4
    assert launch.launch is not None
    assert len(launch.launch.launch_orders) == 4
    assert set(
        launch.launch.launch_orders["lifecycle_action"]
    ) == {"MULTI_LEG_TEMPLATE"}
    assert (
        launch.launch.launch_orders[
            "lifecycle_action_id"
        ].nunique()
        == 1
    )
    assert set(
        launch.launch.launch_orders[
            "lifecycle_message_count"
        ]
    ) == {4}
    launch_manifest = json.loads(
        (launch_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert launch_manifest["extra"][
        "order_plan_promotion_manifest_current"
    ]
    assert "promotion_manifest" in launch_manifest["inputs"]
    assert "order_plan_manifest" in launch_manifest["inputs"]
    assert "order_plan_dependencies" in launch_manifest["inputs"]
    launch_integrity = verify_experiment_manifest(
        launch_dir / "manifest.json",
        expected_run_type="parity_launch_pipeline",
        required_artifacts=(
            "parity_launch_pipeline_components.csv",
            "parity_launch_pipeline_summary.csv",
        ),
        require_input_fingerprints=True,
    )
    assert launch_integrity.passed, launch_integrity.error


def test_box_promotion_rejects_refingerprinted_incomplete_package(
    tmp_path,
):
    (
        chain_path,
        scan_dir,
        edge_dir,
        sweep_dir,
        sweep,
    ) = _write_box_research_pipeline(tmp_path)
    selected_run = str(
        sweep.seed_robustness.iloc[0][
            "latency_seed_worst_run"
        ]
    )
    replay_dir = sweep_dir / "runs" / selected_run
    legging_path = replay_dir / "legging.csv"
    legging = pd.read_csv(legging_path)
    legging.loc[0, "fully_filled_leg_count"] = 3
    legging.to_csv(legging_path, index=False)
    _refresh_manifest(
        replay_dir,
        chain_path=chain_path,
    )
    _refresh_manifest(
        sweep_dir,
        chain_path=chain_path,
    )

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    assert not report.ready
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert "candidate_replay_execution_complete" in failed


def test_box_promotion_rejects_refingerprinted_fair_value_mismatch(
    tmp_path,
):
    (
        chain_path,
        scan_dir,
        edge_dir,
        sweep_dir,
        sweep,
    ) = _write_box_research_pipeline(tmp_path)
    selected_run = str(
        sweep.seed_robustness.iloc[0][
            "latency_seed_worst_run"
        ]
    )
    replay_dir = sweep_dir / "runs" / selected_run
    _refresh_manifest(
        replay_dir,
        chain_path=chain_path,
        parameter_updates={"fair_value_adjustment": 0.25},
    )
    _refresh_manifest(
        sweep_dir,
        chain_path=chain_path,
    )

    report = write_parity_candidate_promotion(
        scan_dir,
        edge_audit_dir=edge_dir,
        sweep_dir=sweep_dir,
        output_dir=tmp_path / "promotion",
    )

    assert not report.ready
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert "selected_replay_parameters_match" in failed
    assert bool(
        report.summary.iloc[0][
            "selected_replay_manifest_current"
        ]
    )
