import json

import pandas as pd

from adapters.orders import OrderStagingLimits, stage_orders
from hft_cli import main
from reports.manifest import write_experiment_manifest
from reports.parity_order_plan import (
    ParityOrderPlanConfig,
    build_parity_order_plan,
    write_parity_order_plan,
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


def candidate_config(*, ready=True, strategy="parity_box"):
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": strategy,
        "scenario_key": scenario_key(),
        "parameters": {
            "market": "india_nse_index_derivatives",
            "direction": "buy_synthetic_sell_future",
            "expiry": "2026-06-30",
            "strike": 25000.0,
            "qty": 75,
            "call_price": 105.0,
            "put_price": 95.0,
            "future_price": 25020.0,
            "net_edge": 450.0,
            "ts": 200,
        },
        "metrics": {
            "median_net_pnl": 42.0,
        },
        "failed_checks": [] if ready else ["promotion_ready"],
    }


def box_candidate_config(*, ready=True):
    config = candidate_config(ready=ready)
    config["parameters"] = {
        "market": "india_nse_index_derivatives",
        "direction": "buy_box",
        "expiry": "2026-06-30",
        "low_strike": 25000.0,
        "high_strike": 25100.0,
        "qty": 75,
        "low_call_price": 110.0,
        "low_put_price": 90.0,
        "high_call_price": 50.0,
        "high_put_price": 135.0,
        "net_edge": 300.0,
    }
    return config


def scenario_key():
    return "strategy=parity_box|market=india_nse_index_derivatives|direction=buy_synthetic_sell_future|strike=25000"


def write_promotion(path, *, ready=True, config=None):
    path.mkdir(parents=True, exist_ok=True)
    candidate = config or candidate_config(ready=ready)
    promotion_summary(ready=ready).to_csv(path / "promotion_summary.csv", index=False)
    pd.DataFrame(
        [{"scenario_key": candidate["scenario_key"]}]
    ).to_csv(path / "promotion_candidate.csv", index=False)
    pd.DataFrame(
        [{"check": "proof", "passed": ready}]
    ).to_csv(path / "promotion_checks.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(candidate, indent=2) + "\n",
        encoding="utf-8",
    )
    source = path.parent / f"{path.name}_source.csv"
    pd.DataFrame([{"proof": "current"}]).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        path,
        run_type="promotion_report",
        inputs={"source": source},
    )


def test_build_parity_order_plan_creates_stageable_three_leg_template():
    report = build_parity_order_plan(
        promotion_summary(),
        candidate_config(),
        config=ParityOrderPlanConfig(max_order_qty=75, max_notional=2_000_000),
    )

    assert report.ready
    assert report.summary.loc[0, "strategy"] == "parity_box"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert report.summary.loc[0, "direction"] == "buy_synthetic_sell_future"
    assert report.summary.loc[0, "orders"] == 3
    assert set(report.orders["leg_role"]) == {"CALL", "PUT", "FUTURE"}
    assert set(report.orders["side"]) == {1, -1}
    assert set(report.orders["client_order_id"].str[:4]) == {"PAR-"}
    assert set(report.orders["lifecycle_action"]) == {"MULTI_LEG_TEMPLATE"}
    assert report.orders["lifecycle_action_id"].nunique() == 1
    assert set(report.orders["template_only"]) == {True}

    staged = stage_orders(
        report.orders,
        source="orders",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=2_000_000, require_nonmarketable=True),
    )
    assert staged.passed
    assert len(staged.accepted) == 3
    assert set(staged.accepted["lifecycle_action"]) == {"MULTI_LEG_TEMPLATE"}
    assert staged.accepted["lifecycle_action_id"].nunique() == 1


def test_build_parity_order_plan_creates_stageable_four_leg_box_template():
    report = build_parity_order_plan(
        promotion_summary(),
        box_candidate_config(),
        config=ParityOrderPlanConfig(max_order_qty=75, max_notional=20_000),
    )

    assert report.ready
    assert report.summary.loc[0, "leg_family"] == "box"
    assert report.summary.loc[0, "orders"] == 4
    assert set(report.orders["leg_role"]) == {"LOW_CALL", "LOW_PUT", "HIGH_CALL", "HIGH_PUT"}
    assert int(report.orders["lifecycle_message_count"].max()) == 4


def test_write_parity_order_plan_outputs_files_and_manifest(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)

    report = write_parity_order_plan(
        promotion_dir,
        output_dir=out_dir,
        config=ParityOrderPlanConfig(max_order_qty=75, max_notional=2_000_000),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.output_dir == out_dir
    assert manifest["run_type"] == "parity_order_plan"
    assert manifest["parameters"]["strategy"] == "parity_box"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert bool(report.summary.loc[0, "promotion_manifest_current"])
    assert manifest["extra"]["promotion_manifest_current"]
    assert "promotion_manifest" in manifest["inputs"]
    assert "promotion_dependencies" in manifest["inputs"]
    assert (out_dir / "parity_order_candidates.csv").exists()
    assert (out_dir / "parity_order_checks.csv").exists()
    assert (out_dir / "parity_order_summary.csv").exists()


def test_parity_order_plan_fails_closed_for_missing_direction():
    config = candidate_config()
    config["parameters"].pop("direction")

    report = build_parity_order_plan(promotion_summary(), config)

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert report.orders.empty
    assert "valid_direction" in failed


def test_cli_plan_parity_orders_fails_closed_for_unready_promotion(tmp_path):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir, ready=False)

    code = main(
        [
            "plan-parity-orders",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(out_dir),
            "--max-order-qty",
            "75",
            "--max-notional",
            "2000000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "parity_order_summary.csv")
    orders = pd.read_csv(out_dir / "parity_order_candidates.csv")
    checks = pd.read_csv(out_dir / "parity_order_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert orders.empty
    assert {"promotion_ready", "candidate_config_ready"}.issubset(set(checks["check"]))


def test_write_parity_order_plan_rejects_drifted_promotion(
    tmp_path,
):
    promotion_dir = tmp_path / "promotion"
    out_dir = tmp_path / "orders"
    write_promotion(promotion_dir)
    candidate_path = promotion_dir / "candidate_config.json"
    candidate = json.loads(
        candidate_path.read_text(encoding="utf-8")
    )
    candidate["parameters"]["call_price"] = 999.0
    candidate_path.write_text(
        json.dumps(candidate, indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_parity_order_plan(
        promotion_dir,
        output_dir=out_dir,
        config=ParityOrderPlanConfig(
            max_order_qty=75,
            max_notional=2_000_000,
        ),
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert report.orders.empty
    assert failed == {"promotion_manifest_current"}
    assert not bool(
        report.summary.loc[0, "promotion_manifest_current"]
    )
    assert (
        report.summary.loc[0, "promotion_manifest_error"]
        == "artifact_drift"
    )
