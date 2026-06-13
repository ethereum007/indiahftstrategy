import json

import pandas as pd

from adapters.orders import OrderStagingLimits, stage_orders
from hft_cli import main
from reports.settlement_order_plan import (
    SettlementOrderPlanConfig,
    build_settlement_order_plan,
    write_settlement_order_plan,
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


def promoted_candidate_config(*, ready=True):
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
        json.dumps(promoted_candidate_config(ready=ready), indent=2) + "\n",
        encoding="utf-8",
    )


def test_build_settlement_order_plan_creates_stageable_order_candidate():
    report = build_settlement_order_plan(
        promotion_summary(),
        promoted_candidate_config(),
        config=SettlementOrderPlanConfig(price_offset_ticks=1.0, tick_size=0.05),
    )

    assert report.ready
    assert report.summary.loc[0, "strategy"] == "settlement_convergence"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert len(report.orders) == 1
    order = report.orders.iloc[0]
    assert order["client_order_id"].startswith("SETTLE-")
    assert order["instrument_id"] == "NIFTY_20260610_100C"
    assert order["side"] == 1
    assert order["side_text"] == "BUY"
    assert order["qty"] == 75
    assert order["price"] == 1.05
    assert not bool(order["marketable"])
    assert order["quote_edge"] == 150.0

    staged = stage_orders(
        report.orders,
        source="orders",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000, require_nonmarketable=True),
    )
    assert staged.passed
    assert len(staged.accepted) == 1
    assert staged.accepted.iloc[0]["client_order_id"].startswith("SETTLE-")


def test_write_settlement_order_plan_outputs_files_and_manifest(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)

    report = write_settlement_order_plan(promotion_dir, output_dir=out_dir)

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.output_dir == out_dir
    assert report.summary.loc[0, "strategy"] == "settlement_convergence"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "settlement_convergence"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert (out_dir / "settlement_order_candidates.csv").exists()
    assert (out_dir / "settlement_order_checks.csv").exists()
    assert (out_dir / "settlement_order_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_plan_settlement_orders_fails_closed_for_unready_promotion(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir, ready=False)

    code = main(
        [
            "plan-settlement-orders",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "settlement_order_summary.csv")
    orders = pd.read_csv(out_dir / "settlement_order_candidates.csv")
    checks = pd.read_csv(out_dir / "settlement_order_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert orders.empty
    assert {"promotion_ready", "candidate_config_ready"}.issubset(set(checks["check"]))
