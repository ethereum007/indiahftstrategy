import json

import pandas as pd

from adapters.orders import OrderStagingLimits, stage_orders
from hft_cli import main
from reports.leadlag_order_plan import (
    LeadLagOrderPlanConfig,
    build_leadlag_order_plan,
    write_leadlag_order_plan,
)
from reports.manifest import write_experiment_manifest


def promotion_summary(*, ready=True, edge_bound=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": scenario_key(),
                "failed_checks": 0 if ready else 1,
                "edge_audit_bound": edge_bound,
                "edge_candidate_manifest_bound": edge_bound,
                "edge_candidate_manifest_current": edge_bound,
                "edge_candidate_manifest_sha256": "b" * 64 if edge_bound else "",
                "edge_latency_budget_ns": 100_000 if edge_bound else None,
                "total_replay_latency_ns": 50_000,
                "edge_latency_headroom_ns": 50_000 if edge_bound else None,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def promoted_candidate_config(*, ready=True, strategy="lead_lag_taker", edge_bound=True):
    candidate = {
        "schema_version": 1,
        "ready": ready,
        "strategy": strategy,
        "scenario_key": scenario_key(),
        "parameters": {
            "market": "india_nse_index_derivatives",
            "leader_tick": 0.05,
            "laggard_tick": 0.05,
            "delta": 1.0,
            "trigger_ticks": 10.0,
            "qty": 75,
            "flat_after_ns": 200_000,
            "cooloff_ns": 1000,
        },
        "replay_defaults": {
            "feed_latency_us": 25.0,
            "order_latency_us": 25.0,
        },
        "metrics": {
            "total_net_pnl": 42.0,
            "median_markout_mean": 0.15,
        },
        "failed_checks": [] if ready else ["walkforward_passed"],
    }
    if edge_bound:
        candidate["edge_audit"] = {
            "passed": True,
            "measurement_manifest_current": True,
            "measurement_manifest_sha256": "a" * 64,
            "max_profitable_latency_ns": 100_000,
            "metrics": {
                "max_profitable_latency_ns": 100_000,
                "best_latency_avg_net_edge": 5.0,
                "best_latency_cost_drag_ratio": 0.2,
                "best_latency_net_edge_bps": 2.0,
            },
        }
        candidate["edge_candidate_manifest"] = {
            "edge_candidate_manifest_required": True,
            "edge_candidate_manifest_current": True,
            "edge_candidate_manifest_sha256": "b" * 64,
            "edge_measurement_manifest_sha256": "a" * 64,
        }
    return candidate


def scenario_key():
    return (
        "strategy=lead_lag_taker|market=india_nse_index_derivatives|trigger_ticks=10|"
        "delta=1|leader_tick=0.05|laggard_tick=0.05"
    )


def write_promotion(path, *, ready=True, strategy="lead_lag_taker", edge_bound=True):
    path.mkdir(parents=True, exist_ok=True)
    promotion_summary(ready=ready, edge_bound=edge_bound).to_csv(
        path / "promotion_summary.csv", index=False
    )
    pd.DataFrame([{"scenario_key": scenario_key()}]).to_csv(
        path / "promotion_candidate.csv", index=False
    )
    pd.DataFrame([{"check": "proof", "passed": ready}]).to_csv(
        path / "promotion_checks.csv", index=False
    )
    (path / "candidate_config.json").write_text(
        json.dumps(
            promoted_candidate_config(
                ready=ready,
                strategy=strategy,
                edge_bound=edge_bound,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    source = path.parent / f"{path.name}_source.csv"
    pd.DataFrame([{"proof": "current"}]).to_csv(source, index=False)
    write_experiment_manifest(
        path,
        run_type="promotion_report",
        inputs={"source": source},
    )


def test_build_leadlag_order_plan_creates_stageable_buy_and_sell_templates():
    report = build_leadlag_order_plan(
        promotion_summary(),
        promoted_candidate_config(),
        config=LeadLagOrderPlanConfig(
            laggard_instrument_id="NIFTY_20260610_25000C",
            reference_price=10.0,
            entry_offset_ticks=1.0,
            max_order_qty=75,
            max_notional=1_000,
            price_band_pct=0.01,
        ),
    )

    assert report.ready
    assert report.summary.loc[0, "strategy"] == "lead_lag_taker"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert report.summary.loc[0, "orders"] == 2
    assert set(report.orders["trigger"]) == {"leader_up_buy_laggard", "leader_down_sell_laggard"}
    assert set(report.orders["side"]) == {1, -1}
    assert report.orders.loc[report.orders["side"] == 1, "price"].iloc[0] == 10.05
    assert report.orders.loc[report.orders["side"] == -1, "price"].iloc[0] == 9.95
    assert set(report.orders["client_order_id"].str[:5]) == {"LLAG-"}
    assert set(report.orders["lifecycle_action"]) == {"SIGNAL_TEMPLATE"}
    assert set(report.orders["template_only"]) == {True}
    assert set(report.orders["edge_measurement_manifest_sha256"]) == {"a" * 64}
    assert set(report.orders["edge_candidate_manifest_sha256"]) == {"b" * 64}
    assert set(report.orders["edge_latency_budget_ns"]) == {100_000}
    assert set(report.orders["total_replay_latency_ns"]) == {50_000}
    assert set(report.orders["edge_latency_headroom_ns"]) == {50_000}
    assert bool(report.summary.loc[0, "edge_audit_bound"])
    assert bool(report.summary.loc[0, "edge_candidate_manifest_bound"])
    assert bool(report.summary.loc[0, "edge_latency_budget_respected"])

    staged = stage_orders(
        report.orders,
        source="orders",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=1_000, require_nonmarketable=True),
    )
    assert staged.passed
    assert len(staged.accepted) == 2
    assert set(staged.accepted["lifecycle_action"]) == {"SIGNAL_TEMPLATE"}


def test_write_leadlag_order_plan_outputs_files_and_manifest(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)

    report = write_leadlag_order_plan(
        promotion_dir,
        output_dir=out_dir,
        config=LeadLagOrderPlanConfig(
            laggard_instrument_id="NIFTY_20260610_25000C",
            buy_limit_price=10.05,
            sell_limit_price=9.95,
        ),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.output_dir == out_dir
    assert manifest["run_type"] == "leadlag_order_plan"
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert bool(report.summary.loc[0, "promotion_manifest_current"])
    assert manifest["extra"]["promotion_manifest_current"]
    assert manifest["extra"]["edge_audit_bound"]
    assert manifest["extra"]["edge_candidate_manifest_bound"]
    assert "promotion_manifest" in manifest["inputs"]
    assert "promotion_dependencies" in manifest["inputs"]
    assert (out_dir / "leadlag_order_candidates.csv").exists()
    assert (out_dir / "leadlag_order_checks.csv").exists()
    assert (out_dir / "leadlag_order_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_leadlag_order_plan_fails_closed_for_wrong_strategy():
    report = build_leadlag_order_plan(
        promotion_summary(),
        promoted_candidate_config(strategy="settlement_convergence"),
        config=LeadLagOrderPlanConfig(reference_price=10.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.orders.empty
    assert "valid_strategy" in failed


def test_leadlag_order_plan_rejects_legacy_unverified_edge_candidate():
    summary = promotion_summary()
    summary.loc[0, "edge_candidate_manifest_bound"] = False
    legacy = promoted_candidate_config()
    legacy.pop("edge_candidate_manifest")

    report = build_leadlag_order_plan(
        summary,
        legacy,
        config=LeadLagOrderPlanConfig(reference_price=10.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.orders.empty
    assert failed == {
        "edge_candidate_manifest_bound",
        "promotion_edge_candidate_manifest_bound",
    }


def test_write_leadlag_order_plan_fails_closed_for_drifted_promotion(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)
    candidate_path = promotion_dir / "candidate_config.json"
    candidate_path.write_text(
        candidate_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    report = write_leadlag_order_plan(
        promotion_dir,
        output_dir=out_dir,
        config=LeadLagOrderPlanConfig(reference_price=10.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.orders.empty
    assert failed == {"promotion_manifest_current"}
    assert not bool(report.summary.loc[0, "promotion_manifest_current"])
    assert report.summary.loc[0, "promotion_manifest_error"] == "artifact_drift"


def test_cli_plan_leadlag_orders_allows_explicit_unbound_research_override(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir, edge_bound=False)

    code = main(
        [
            "plan-leadlag-orders",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--reference-price",
            "10",
            "--allow-unbound-edge-audit",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "leadlag_order_summary.csv")
    checks = pd.read_csv(out_dir / "leadlag_order_checks.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "edge_audit_bound"])
    assert bool(summary.loc[0, "edge_audit_override_used"])
    assert summary.loc[0, "recommendation"] == "research_only_unbound_edge"
    assert checks.loc[
        checks["check"] == "edge_audit_bound", "passed"
    ].astype(bool).all()


def test_cli_plan_leadlag_orders_fails_closed_for_unready_promotion(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir, ready=False)

    code = main(
        [
            "plan-leadlag-orders",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--reference-price",
            "10",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "leadlag_order_summary.csv")
    orders = pd.read_csv(out_dir / "leadlag_order_candidates.csv")
    checks = pd.read_csv(out_dir / "leadlag_order_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert orders.empty
    assert {"promotion_ready", "candidate_config_ready"}.issubset(set(checks["check"]))
