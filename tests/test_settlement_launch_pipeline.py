import json

import pandas as pd

from hft_cli import main
from reports.settlement_launch_pipeline import (
    SettlementLaunchPipelineConfig,
    write_settlement_launch_pipeline,
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
        "strategy": "settlement_convergence",
        "scenario_key": scenario_key(),
        "parameters": {
            "best_ts": 200,
            "best_expiry": "2026-06-10",
            "best_strike": 100.0,
            "best_option_type": "C",
            "best_direction": "buy_underpriced",
            "best_side": 1,
            "best_touch_price": 1.0,
            "best_trade_qty": 75,
            "best_projected_settlement": 103.0,
            "best_projected_intrinsic": 3.0,
            "best_gross_edge": 2.0,
            "best_gross_edge_ticks": 40.0,
            "best_cost": 0.05,
            "best_net_edge": 150.0,
        },
        "metrics": {"total_net_edge": 450.0},
        "failed_checks": [] if ready else ["walkforward_passed"],
    }


def scenario_key():
    return (
        "strategy=settlement_convergence|direction=buy_underpriced|"
        "option_type=C|strike=100|min_known_fraction=0.5|min_net_edge=100"
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


def test_write_settlement_launch_pipeline_runs_full_paper_handoff(tmp_path):
    promotion_dir = tmp_path / "promotion"
    runtime_dir = tmp_path / "runtime_session"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)
    write_runtime_session(runtime_dir)

    report = write_settlement_launch_pipeline(
        promotion_dir,
        output_dir=out_dir,
        config=SettlementLaunchPipelineConfig(
            adapter="arrow_money",
            require_reviewed_schema=False,
            route_tag="settlement_shadow",
            max_order_qty=75,
            max_notional=10_000,
            max_orders=1,
            broker_runtime_session_dir=runtime_dir,
            require_broker_runtime_session=True,
        ),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    broker_summary = pd.read_csv(out_dir / "06_broker_readiness" / "broker_readiness_summary.csv")
    assert report.ready
    assert report.summary.loc[0, "strategy"] == "settlement_convergence"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "settlement_convergence"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert report.output_dir == out_dir
    assert report.broker_readiness is not None
    assert bool(broker_summary.loc[0, "runtime_session_ready"])
    assert broker_summary.loc[0, "runtime_guard_action"] == "continue"
    assert report.components["status"].tolist() == ["ready", "ready", "ready", "ready", "ready", "ready"]
    assert (out_dir / "01_order_plan" / "settlement_order_candidates.csv").exists()
    assert (out_dir / "02_staged_orders" / "staged_orders.csv").exists()
    assert (out_dir / "03_launch" / "launch_orders.csv").exists()
    assert (out_dir / "04_export" / "broker_orders.csv").exists()
    assert (out_dir / "05_upload_pack" / "broker_upload_orders.csv").exists()
    assert (out_dir / "06_broker_readiness" / "broker_readiness_summary.csv").exists()
    assert (out_dir / "settlement_launch_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_settlement_launch_pipeline_skips_downstream_when_promotion_unready(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir, ready=False)

    report = write_settlement_launch_pipeline(
        promotion_dir,
        output_dir=out_dir,
        config=SettlementLaunchPipelineConfig(require_reviewed_schema=False),
    )

    components = report.components.set_index("component")
    assert not report.ready
    assert report.staging is None
    assert components.loc["order_plan", "status"] == "not_ready"
    assert components.loc["staged_orders", "status"] == "skipped"
    assert components.loc["upload_pack", "reason"] == "export_not_ready"
    assert components.loc["broker_readiness", "reason"] == "upload_pack_not_available"


def test_cli_pipeline_settlement_launch_fails_until_placeholder_schema_allowed(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-settlement-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_launch_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "settlement_launch_pipeline_components.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert components.set_index("component").loc["upload_pack", "status"] == "not_ready"
    assert components.set_index("component").loc["broker_readiness", "status"] == "not_ready"
    assert (out_dir / "05_upload_pack" / "broker_upload_orders.csv").exists()
    assert (out_dir / "06_broker_readiness" / "broker_readiness_summary.csv").exists()


def test_cli_pipeline_settlement_launch_can_require_broker_reconciliation(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-settlement-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--allow-placeholder-schema",
            "--require-broker-reconciliation",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_launch_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "settlement_launch_pipeline_components.csv")
    checks = pd.read_csv(out_dir / "06_broker_readiness" / "broker_readiness_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert components.set_index("component").loc["broker_readiness", "status"] == "not_ready"
    assert "reconciliation_provided" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_pipeline_settlement_launch_can_require_runtime_session(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "pipeline"
    write_promotion(promotion_dir)

    code = main(
        [
            "pipeline-settlement-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--allow-placeholder-schema",
            "--require-broker-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "06_broker_readiness" / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed
