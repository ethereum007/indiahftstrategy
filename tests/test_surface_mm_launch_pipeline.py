import json

import pandas as pd

from hft_cli import main
from reports.surface_mm_launch_pipeline import (
    SurfaceMMLaunchPipelineConfig,
    write_surface_mm_launch_pipeline,
)
from tests.broker_vendor_data_helpers import path_tail, write_broker_vendor_data_proof


def surface_quotes():
    return pd.DataFrame(
        [
            {
                "ts": 100,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000",
                "side": 1,
                "price": 100.0,
                "qty": 75,
                "theo": 100.2,
                "quote_edge": 0.2,
                "market_bid": 99.8,
                "market_ask": 100.3,
                "marketable": False,
                "market_spread_ticks": 10.0,
            },
            {
                "ts": 100,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000",
                "side": -1,
                "price": 100.4,
                "qty": 75,
                "theo": 100.2,
                "quote_edge": 0.2,
                "market_bid": 99.8,
                "market_ask": 100.3,
                "marketable": False,
                "market_spread_ticks": 10.0,
            },
        ]
    )


def multi_snapshot_surface_quotes():
    quotes = surface_quotes()
    second = quotes.copy()
    second["ts"] = 200
    second = second.iloc[[0, 1]].copy()
    second.loc[second["side"] == 1, "price"] = 100.1
    return pd.concat([quotes, second], ignore_index=True, sort=False)


def write_surface_pipeline(
    path,
    *,
    quote_review_passed=True,
    promotion_ready=True,
    surface_ready=True,
    strategy="surface_mm",
    market="india_nse_index_derivatives",
):
    quotes_dir = path / "01_quotes"
    review_dir = path / "02_quote_review"
    promotion_dir = path / "05_promotion"
    quotes_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)
    promotion_dir.mkdir(parents=True)
    surface_quotes().to_csv(quotes_dir / "surface_quotes.csv", index=False)
    pd.DataFrame(
        [
            {
                "ready": surface_ready,
                "failed_stages": 0 if surface_ready else 1,
                "skipped_stages": 0 if surface_ready else 1,
                "recommendation": "paper_or_shadow_candidate" if surface_ready else "keep_researching",
                "quote_generation_passed": True,
                "quote_review_passed": quote_review_passed,
                "sweep_proof_passed": surface_ready,
                "selection_has_scenario": surface_ready,
                "promotion_ready": promotion_ready,
                "candidate_scenario_key": "quote_ttl_ns=1000000000|order_latency_us=0",
                "quotes": 2,
                "marketable_quotes": 0 if quote_review_passed else 1,
                "sweep_scenarios": 1,
                "sweep_pass_rate": 1.0 if surface_ready else 0.0,
                "selectable_scenarios": 1 if surface_ready else 0,
            }
        ]
    ).to_csv(path / "surface_mm_pipeline_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": surface_ready,
                "strategy": strategy,
                "market": market,
                "source_run_type": "surface_mm_research_pipeline",
                "scenario_key": "quote_ttl_ns=1000000000|order_latency_us=0",
                "parameters": {"quote_ttl_ns": 1000000000, "order_latency_us": 0},
                "metrics": {"pass_rate": 1.0 if surface_ready else 0.0},
                "recommendation": "paper_or_shadow_candidate" if surface_ready else "keep_researching",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_type": "surface_mm_research_pipeline",
                "parameters": {"market": market, "strategy": strategy},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "snapshots": 1,
                "quotes": 2,
                "instruments": 1,
                "bid_quotes": 1,
                "ask_quotes": 1,
                "bid_share": 0.5,
                "marketable_quotes": 0 if quote_review_passed else 1,
                "min_quote_edge": 0.2 if quote_review_passed else -0.1,
                "avg_quote_edge": 0.2,
                "max_market_spread_ticks": 10.0,
                "max_quotes_per_instrument": 2,
                "all_passed": quote_review_passed,
            }
        ]
    ).to_csv(review_dir / "quote_risk_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "ready": promotion_ready,
                "candidate_scenario_key": "quote_ttl_ns=1000000000|order_latency_us=0",
                "checks": 4,
                "failed_checks": 0 if promotion_ready else 1,
                "recommendation": "paper_or_shadow_candidate" if promotion_ready else "keep_in_research",
            }
        ]
    ).to_csv(promotion_dir / "promotion_summary.csv", index=False)
    (promotion_dir / "candidate_config.json").write_text(
        "{\n"
        '  "schema_version": 1,\n'
        f'  "ready": {str(promotion_ready).lower()},\n'
        '  "strategy": "surface_mm",\n'
        f'  "market": "{market}",\n'
        '  "scenario_key": "quote_ttl_ns=1000000000|order_latency_us=0",\n'
        '  "parameters": {"quote_ttl_ns": 1000000000, "order_latency_us": 0},\n'
        '  "metrics": {"pass_rate": 1.0}\n'
        "}\n",
        encoding="utf-8",
    )


def write_runtime_session(path, *, adapter="normalized", ready=True, halted=False):
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


def test_surface_mm_launch_pipeline_runs_to_broker_readiness(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    runtime_dir = tmp_path / "runtime_session"
    out_dir = tmp_path / "launch_pipeline"
    write_surface_pipeline(surface_pipeline)
    write_runtime_session(runtime_dir)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(
            adapter="normalized",
            mode="paper",
            require_reviewed_schema=True,
            broker_runtime_session_dir=runtime_dir,
            require_broker_runtime_session=True,
        ),
    )

    components = report.components.set_index("component")
    broker_summary = pd.read_csv(out_dir / "05_broker_readiness" / "broker_readiness_summary.csv")
    assert report.ready
    assert bool(components.loc["surface_research", "ready"])
    assert report.summary.loc[0, "strategy"] == "surface_mm"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert bool(components.loc["quote_lifecycle", "ready"])
    assert bool(components.loc["staged_orders", "ready"])
    assert bool(components.loc["launch", "ready"])
    assert bool(components.loc["export", "ready"])
    assert bool(components.loc["upload_pack", "ready"])
    assert bool(components.loc["broker_readiness", "ready"])
    assert bool(broker_summary.loc[0, "runtime_session_ready"])
    assert broker_summary.loc[0, "runtime_guard_action"] == "continue"
    assert (out_dir / "00_quote_lifecycle" / "quote_lifecycle_summary.csv").exists()
    assert (out_dir / "01_staged_orders" / "staged_orders.csv").exists()
    assert (out_dir / "02_launch" / "launch_config.json").exists()
    assert (out_dir / "03_export" / "broker_orders.csv").exists()
    assert (out_dir / "04_upload_pack" / "broker_upload_summary.csv").exists()
    assert (out_dir / "05_broker_readiness" / "broker_readiness_summary.csv").exists()
    assert (out_dir / "surface_mm_launch_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_surface_mm_launch_pipeline_consumes_broker_vendor_data_proof_root(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    proof_dir = write_broker_vendor_data_proof(tmp_path / "broker_vendor_data", adapter="normalized")
    out_dir = tmp_path / "launch_pipeline"
    write_surface_pipeline(surface_pipeline)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(
            adapter="normalized",
            mode="paper",
            require_reviewed_schema=True,
            broker_vendor_data_readiness_dir=proof_dir,
        ),
    )

    assert report.ready
    broker_manifest = json.loads((out_dir / "05_broker_readiness" / "manifest.json").read_text(encoding="utf-8"))
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


def test_surface_mm_launch_pipeline_blocks_unready_surface_research(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "launch_pipeline_unready_research"
    write_surface_pipeline(surface_pipeline, surface_ready=False)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(adapter="normalized", mode="paper"),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert not bool(components.loc["surface_research", "ready"])
    assert components.loc["quote_lifecycle", "status"] == "skipped"
    assert components.loc["quote_lifecycle", "reason"] == "surface_research_not_ready"
    assert "surface_pipeline_ready" in str(components.loc["surface_research", "reason"])
    assert not bool(report.summary.loc[0, "surface_pipeline_ready"])


def test_surface_mm_launch_pipeline_blocks_market_mismatch(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "launch_pipeline_market_mismatch"
    write_surface_pipeline(surface_pipeline, market="us_options_regular")

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(adapter="normalized", mode="paper"),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert not bool(components.loc["surface_research", "ready"])
    assert report.summary.loc[0, "market"] == "us_options_regular"
    assert report.summary.loc[0, "expected_market"] == "india_nse_index_derivatives"
    assert "surface_market_matches" in str(components.loc["surface_research", "reason"])


def test_surface_mm_launch_pipeline_blocks_failed_quote_review(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "launch_pipeline_blocked"
    write_surface_pipeline(surface_pipeline, quote_review_passed=False)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(adapter="normalized", mode="paper"),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert bool(components.loc["surface_research", "ready"])
    assert not bool(components.loc["quote_lifecycle", "ready"])
    assert not bool(components.loc["staged_orders", "ready"])
    assert components.loc["launch", "status"] == "skipped"
    assert int(report.summary.loc[0, "skipped_components"]) >= 1


def test_surface_mm_launch_pipeline_blocks_quote_lifecycle_message_breach(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "launch_pipeline_lifecycle_blocked"
    write_surface_pipeline(surface_pipeline)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(
            adapter="normalized",
            mode="paper",
            max_quote_order_messages=1,
        ),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert not bool(components.loc["quote_lifecycle", "ready"])
    assert components.loc["staged_orders", "status"] == "skipped"
    assert components.loc["staged_orders", "reason"] == "quote_lifecycle_not_ready"


def test_surface_mm_launch_pipeline_stages_lifecycle_route_orders_not_raw_quotes(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "launch_pipeline_route_orders"
    write_surface_pipeline(surface_pipeline)
    raw_quotes = multi_snapshot_surface_quotes()
    raw_quotes.to_csv(surface_pipeline / "01_quotes" / "surface_quotes.csv", index=False)

    report = write_surface_mm_launch_pipeline(
        surface_pipeline,
        output_dir=out_dir,
        config=SurfaceMMLaunchPipelineConfig(adapter="normalized", mode="paper"),
    )

    route_orders = pd.read_csv(out_dir / "00_quote_lifecycle" / "quote_lifecycle_route_orders.csv")
    staged = pd.read_csv(out_dir / "01_staged_orders" / "staged_orders.csv")
    launch = pd.read_csv(out_dir / "02_launch" / "launch_orders.csv")
    broker_orders = pd.read_csv(out_dir / "03_export" / "broker_orders.csv")
    upload_orders = pd.read_csv(out_dir / "04_upload_pack" / "broker_upload_orders.csv")
    assert report.ready
    assert len(raw_quotes) == 4
    assert len(route_orders) == 3
    assert len(staged) == 3
    assert set(staged["client_order_id"]) == set(route_orders["client_order_id"])
    assert "replace" in set(route_orders["lifecycle_action"])
    assert "replace" in set(staged["lifecycle_action"])
    assert "replace" in set(launch["lifecycle_action"])
    assert "replace" in set(broker_orders["lifecycle_action"])
    replace = broker_orders.loc[broker_orders["lifecycle_action"] == "replace"].iloc[0]
    assert str(replace["replaces_order_id"]).startswith("QLF-")
    assert str(replace["lifecycle_action_id"]).startswith("ACT-")
    assert "replace" in set(upload_orders["lifecycle_action"])
    assert "replaces_order_id" in upload_orders.columns


def test_cli_surface_mm_launch_pipeline_can_fail_on_breach(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "cli_launch_pipeline"
    write_surface_pipeline(surface_pipeline, quote_review_passed=False)

    code = main(
        [
            "pipeline-surface-mm-launch",
            "--surface-pipeline",
            str(surface_pipeline),
            "--out",
            str(out_dir),
            "--adapter",
            "normalized",
            "--mode",
            "paper",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "surface_mm_launch_pipeline_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])


def test_cli_surface_mm_launch_pipeline_can_require_runtime_session(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "cli_launch_pipeline_runtime"
    write_surface_pipeline(surface_pipeline)

    code = main(
        [
            "pipeline-surface-mm-launch",
            "--surface-pipeline",
            str(surface_pipeline),
            "--out",
            str(out_dir),
            "--adapter",
            "normalized",
            "--mode",
            "paper",
            "--require-broker-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "05_broker_readiness" / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed


def test_cli_surface_mm_launch_pipeline_blocks_market_mismatch(tmp_path):
    surface_pipeline = tmp_path / "surface_pipeline"
    out_dir = tmp_path / "cli_launch_pipeline_market_mismatch"
    write_surface_pipeline(surface_pipeline, market="us_options_regular")

    code = main(
        [
            "pipeline-surface-mm-launch",
            "--surface-pipeline",
            str(surface_pipeline),
            "--out",
            str(out_dir),
            "--adapter",
            "normalized",
            "--mode",
            "paper",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "surface_mm_launch_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "surface_mm_launch_pipeline_components.csv").set_index("component")
    assert code == 2
    assert summary.loc[0, "market"] == "us_options_regular"
    assert summary.loc[0, "expected_market"] == "india_nse_index_derivatives"
    assert "surface_market_matches" in str(components.loc["surface_research", "reason"])
