import json

import pandas as pd

from hft_cli import main
from reports.imbalance_launch_pipeline import (
    ImbalanceLaunchPipelineConfig,
    write_imbalance_launch_pipeline,
)
from tests.broker_vendor_data_helpers import (
    assert_broker_vendor_data_proof_forwarded,
    path_tail,
    write_broker_vendor_data_proof,
)


def promotion_summary(*, ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": scenario_key(),
                "failed_checks": 0 if ready else 1,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def candidate_config(*, ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": "imbalance",
        "scenario_key": scenario_key(),
        "parameters": {
            "market": "india_nse_index_derivatives",
            "instrument_id": "NIFTY_20260610_25000C",
            "instrument_kind": "OPT",
            "lot_size": 75,
            "tick_size": 0.05,
            "qty": 75,
            "entry_imbalance": 0.6,
            "exit_imbalance": 0.15,
            "min_microprice_edge_ticks": 0.25,
            "max_spread_ticks": 2.0,
            "min_depth": 1,
            "hold_ns": 1_000_000,
            "cooloff_ns": 1000,
        },
        "metrics": {
            "total_net_pnl": 42.0,
            "median_markout_mean": 0.15,
        },
        "failed_checks": [] if ready else ["walkforward_passed"],
    }


def scenario_key():
    return (
        "strategy=imbalance|market=india_nse_index_derivatives|entry_imbalance=0.6|"
        "min_microprice_edge_ticks=0.25|hold_ns=1000000"
    )


def write_promotion(path, *, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    promotion_summary(ready=ready).to_csv(path / "promotion_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(candidate_config(ready=ready), indent=2) + "\n",
        encoding="utf-8",
    )


def write_runtime_session(path, *, adapter="arrow_money", ready=True, halted=False):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "failed_checks": 1 if halted else 0,
                "recommendation": "stop_routing_and_execute_halt_response" if halted else "continue_with_controls",
            }
        ]
    ).to_csv(path / "runtime_session_summary.csv", index=False)


def test_write_imbalance_launch_pipeline_runs_full_shadow_handoff(tmp_path):
    promotion_dir = tmp_path / "promotion"
    runtime_dir = tmp_path / "runtime_session"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)
    write_runtime_session(runtime_dir)

    report = write_imbalance_launch_pipeline(
        promotion_dir,
        output_dir=out_dir,
        config=ImbalanceLaunchPipelineConfig(
            adapter="arrow_money",
            require_reviewed_schema=False,
            route_tag="imbalance_shadow",
            instrument_id="NIFTY_20260610_25000C",
            reference_price=10.0,
            max_order_qty=75,
            max_notional=10_000,
            max_orders=2,
            broker_runtime_session_dir=runtime_dir,
            require_broker_runtime_session=True,
        ),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    broker_summary = pd.read_csv(out_dir / "06_broker_readiness" / "broker_readiness_summary.csv")
    launch_orders = pd.read_csv(out_dir / "03_launch" / "launch_orders.csv")
    assert report.ready
    assert report.summary.loc[0, "strategy"] == "imbalance"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "imbalance"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert report.output_dir == out_dir
    assert report.broker_readiness is not None
    assert bool(broker_summary.loc[0, "runtime_session_ready"])
    assert broker_summary.loc[0, "runtime_guard_action"] == "continue"
    assert set(launch_orders["lifecycle_action"]) == {"SIGNAL_TEMPLATE"}
    assert report.components["status"].tolist() == ["ready", "ready", "ready", "ready", "ready", "ready"]
    assert (out_dir / "01_order_plan" / "imbalance_order_candidates.csv").exists()
    assert (out_dir / "02_staged_orders" / "staged_orders.csv").exists()
    assert (out_dir / "03_launch" / "launch_orders.csv").exists()
    assert (out_dir / "04_export" / "broker_orders.csv").exists()
    assert (out_dir / "05_upload_pack" / "broker_upload_orders.csv").exists()
    assert (out_dir / "06_broker_readiness" / "broker_readiness_summary.csv").exists()
    assert (out_dir / "imbalance_launch_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_imbalance_launch_pipeline_consumes_broker_vendor_data_proof_root(tmp_path):
    promotion_dir = tmp_path / "promotion"
    proof_dir = write_broker_vendor_data_proof(tmp_path / "broker_vendor_data")
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    report = write_imbalance_launch_pipeline(
        promotion_dir,
        output_dir=out_dir,
        config=ImbalanceLaunchPipelineConfig(
            adapter="arrow_money",
            require_reviewed_schema=False,
            route_tag="imbalance_shadow",
            instrument_id="NIFTY_20260610_25000C",
            reference_price=10.0,
            max_order_qty=75,
            max_notional=10_000,
            max_orders=2,
            broker_vendor_data_readiness_dir=proof_dir,
        ),
    )

    assert report.ready
    broker_manifest = json.loads((out_dir / "06_broker_readiness" / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(broker_manifest["inputs"]["vendor_market_data_batch_config"]["path"]).endswith(
        "/broker_vendor_data/01_vendor_market_data_batch/vendor_market_data_batch_config.json"
    )
    assert path_tail(broker_manifest["inputs"]["vendor_market_data_batch_manifest"]["path"]).endswith(
        "/broker_vendor_data/01_vendor_market_data_batch/manifest.json"
    )
    pipeline_manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(pipeline_manifest["parameters"]["config"]["broker_vendor_data_readiness_dir"]).endswith(
        "/broker_vendor_data"
    )


def test_cli_pipeline_imbalance_launch_forwards_broker_vendor_data_proof_root(tmp_path):
    promotion_dir = tmp_path / "promotion"
    proof_dir = write_broker_vendor_data_proof(tmp_path / "broker_vendor_data")
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-imbalance-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--route-tag",
            "imbalance_shadow",
            "--instrument-id",
            "NIFTY_20260610_25000C",
            "--reference-price",
            "10",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--broker-vendor-data-readiness",
            str(proof_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_launch_pipeline_summary.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert_broker_vendor_data_proof_forwarded(out_dir)


def test_imbalance_launch_pipeline_skips_downstream_when_promotion_unready(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir, ready=False)

    report = write_imbalance_launch_pipeline(
        promotion_dir,
        output_dir=out_dir,
        config=ImbalanceLaunchPipelineConfig(reference_price=10.0, require_reviewed_schema=False),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert report.staging is None
    assert components.loc["order_plan", "status"] == "not_ready"
    assert components.loc["staged_orders", "status"] == "skipped"
    assert components.loc["upload_pack", "reason"] == "export_not_ready"
    assert components.loc["broker_readiness", "reason"] == "upload_pack_not_available"


def test_cli_pipeline_imbalance_launch_fails_until_placeholder_schema_allowed(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-imbalance-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--reference-price",
            "10",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_launch_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "imbalance_launch_pipeline_components.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert components.set_index("component").loc["upload_pack", "status"] == "not_ready"
    assert components.set_index("component").loc["broker_readiness", "status"] == "not_ready"
    assert (out_dir / "05_upload_pack" / "broker_upload_orders.csv").exists()
    assert (out_dir / "06_broker_readiness" / "broker_readiness_summary.csv").exists()


def test_cli_pipeline_imbalance_launch_can_require_runtime_session(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-imbalance-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--reference-price",
            "10",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--allow-placeholder-schema",
            "--require-broker-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "06_broker_readiness" / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed
