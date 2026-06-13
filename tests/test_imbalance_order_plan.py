import json

import pandas as pd

from adapters.orders import OrderStagingLimits, stage_orders
from hft_cli import main
from reports.imbalance_order_plan import (
    ImbalanceOrderPlanConfig,
    build_imbalance_order_plan,
    write_imbalance_order_plan,
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


def promoted_candidate_config(*, ready=True, strategy="imbalance"):
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": strategy,
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


def write_promotion(path, *, ready=True, strategy="imbalance"):
    path.mkdir(parents=True, exist_ok=True)
    promotion_summary(ready=ready).to_csv(path / "promotion_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(promoted_candidate_config(ready=ready, strategy=strategy), indent=2) + "\n",
        encoding="utf-8",
    )


def test_build_imbalance_order_plan_creates_stageable_buy_and_sell_templates():
    report = build_imbalance_order_plan(
        promotion_summary(),
        promoted_candidate_config(),
        config=ImbalanceOrderPlanConfig(
            instrument_id="NIFTY_20260610_25000C",
            reference_price=10.0,
            entry_offset_ticks=1.0,
            max_order_qty=75,
            max_notional=1_000,
            price_band_pct=0.01,
        ),
    )

    assert report.ready
    assert report.summary.loc[0, "strategy"] == "imbalance"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert report.summary.loc[0, "orders"] == 2
    assert set(report.orders["trigger"]) == {"bid_pressure_buy", "ask_pressure_sell"}
    assert set(report.orders["side"]) == {1, -1}
    assert report.orders.loc[report.orders["side"] == 1, "price"].iloc[0] == 10.05
    assert report.orders.loc[report.orders["side"] == -1, "price"].iloc[0] == 9.95
    assert set(report.orders["client_order_id"].str[:4]) == {"IMB-"}
    assert set(report.orders["lifecycle_action"]) == {"SIGNAL_TEMPLATE"}
    assert set(report.orders["template_only"]) == {True}
    assert set(report.orders["entry_imbalance"]) == {0.6}

    staged = stage_orders(
        report.orders,
        source="orders",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=1_000, require_nonmarketable=True),
    )
    assert staged.passed
    assert len(staged.accepted) == 2
    assert set(staged.accepted["lifecycle_action"]) == {"SIGNAL_TEMPLATE"}


def test_write_imbalance_order_plan_outputs_files_and_manifest(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)

    report = write_imbalance_order_plan(
        promotion_dir,
        output_dir=out_dir,
        config=ImbalanceOrderPlanConfig(
            instrument_id="NIFTY_20260610_25000C",
            buy_limit_price=10.05,
            sell_limit_price=9.95,
        ),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.output_dir == out_dir
    assert manifest["run_type"] == "imbalance_order_plan"
    assert manifest["parameters"]["strategy"] == "imbalance"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert (out_dir / "imbalance_order_candidates.csv").exists()
    assert (out_dir / "imbalance_order_checks.csv").exists()
    assert (out_dir / "imbalance_order_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_imbalance_order_plan_fails_closed_for_wrong_strategy():
    report = build_imbalance_order_plan(
        promotion_summary(),
        promoted_candidate_config(strategy="lead_lag_taker"),
        config=ImbalanceOrderPlanConfig(reference_price=10.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.orders.empty
    assert "valid_strategy" in failed


def test_cli_plan_imbalance_orders_fails_closed_for_unready_promotion(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir, ready=False)

    code = main(
        [
            "plan-imbalance-orders",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--reference-price",
            "10",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_order_summary.csv")
    orders = pd.read_csv(out_dir / "imbalance_order_candidates.csv")
    checks = pd.read_csv(out_dir / "imbalance_order_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert orders.empty
    assert {"promotion_ready", "candidate_config_ready"}.issubset(set(checks["check"]))
