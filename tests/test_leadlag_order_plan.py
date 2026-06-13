import json

import pandas as pd

from adapters.orders import OrderStagingLimits, stage_orders
from hft_cli import main
from reports.leadlag_order_plan import (
    LeadLagOrderPlanConfig,
    build_leadlag_order_plan,
    write_leadlag_order_plan,
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


def promoted_candidate_config(*, ready=True, strategy="lead_lag_taker"):
    return {
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
        "metrics": {
            "total_net_pnl": 42.0,
            "median_markout_mean": 0.15,
        },
        "failed_checks": [] if ready else ["walkforward_passed"],
    }


def scenario_key():
    return (
        "strategy=lead_lag_taker|market=india_nse_index_derivatives|trigger_ticks=10|"
        "delta=1|leader_tick=0.05|laggard_tick=0.05"
    )


def write_promotion(path, *, ready=True, strategy="lead_lag_taker"):
    path.mkdir(parents=True, exist_ok=True)
    promotion_summary(ready=ready).to_csv(path / "promotion_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(promoted_candidate_config(ready=ready, strategy=strategy), indent=2) + "\n",
        encoding="utf-8",
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
