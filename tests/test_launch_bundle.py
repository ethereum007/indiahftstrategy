import json

import pandas as pd

from hft_cli import main
from reports.launch import LaunchThresholds, evaluate_launch_bundle, write_launch_bundle


def promotion_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": "trigger_ticks=2|order_latency_us=100",
                "checks": 8,
                "failed_checks": 0 if ready else 1,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def candidate_config(ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "scenario_key": "trigger_ticks=2|order_latency_us=100",
        "parameters": {"trigger_ticks": 2.0, "order_latency_us": 100.0},
        "metrics": {"pass_rate": 1.0, "median_net_pnl": 12.0},
        "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
    }


def staged_summary(rejected_orders=0, *, quote_risk_review_passed=None):
    row = {
        "total_orders": 2 + rejected_orders,
        "accepted_orders": 2,
        "rejected_orders": rejected_orders,
        "acceptance_rate": 2 / (2 + rejected_orders),
        "buy_orders": 1,
        "sell_orders": 1,
        "accepted_notional": 1500.0,
        "rejected_notional": 100.0 if rejected_orders else 0.0,
        "total_notional": 1600.0 if rejected_orders else 1500.0,
        "max_order_notional": 800.0,
        "all_passed": rejected_orders == 0,
    }
    if quote_risk_review_passed is not None:
        row.update(
            {
                "quote_risk_review_required": True,
                "quote_risk_review_provided": True,
                "quote_risk_review_passed": quote_risk_review_passed,
                "quote_risk_review_reason": "accepted" if quote_risk_review_passed else "quote_risk_review_not_passed",
            }
        )
    return pd.DataFrame([row])


def staged_orders():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-000001",
                "source": "surface_quotes",
                "source_row": 0,
                "strategy": "surface_mm",
                "instrument_id": "CALL_1000_0",
                "side": 1,
                "side_text": "BUY",
                "qty": 75,
                "price": 10.0,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "ts_signal_ns": 1,
                "notional": 750.0,
            },
            {
                "client_order_id": "STG-000002",
                "source": "surface_quotes",
                "source_row": 1,
                "strategy": "surface_mm",
                "instrument_id": "PUT_1000_0",
                "side": -1,
                "side_text": "SELL",
                "qty": 75,
                "price": 10.0,
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "ts_signal_ns": 1,
                "notional": 750.0,
            },
        ]
    )


def staged_rejections():
    return pd.DataFrame(
        [
            {
                "client_order_id": "STG-BAD",
                "instrument_id": "BAD",
                "side": 1,
                "qty": 75,
                "price": 10.0,
                "rejection_reason": "marketable_order",
            }
        ]
    )


def write_inputs(tmp_path, *, promotion_ready=True, rejected_orders=0, quote_risk_review_passed=None):
    promotion_dir = tmp_path / "promotion"
    staged_dir = tmp_path / "staged"
    promotion_dir.mkdir()
    staged_dir.mkdir()
    promotion_summary(promotion_ready).to_csv(promotion_dir / "promotion_summary.csv", index=False)
    (promotion_dir / "candidate_config.json").write_text(
        json.dumps(candidate_config(promotion_ready), indent=2) + "\n",
        encoding="utf-8",
    )
    staged_summary(rejected_orders, quote_risk_review_passed=quote_risk_review_passed).to_csv(
        staged_dir / "staged_order_summary.csv",
        index=False,
    )
    staged_orders().to_csv(staged_dir / "staged_orders.csv", index=False)
    rejections = staged_rejections() if rejected_orders else pd.DataFrame()
    rejections.to_csv(staged_dir / "staged_order_rejections.csv", index=False)
    return promotion_dir, staged_dir


def test_evaluate_launch_bundle_ready_for_promoted_clean_orders():
    report = evaluate_launch_bundle(
        promotion_summary=promotion_summary(True),
        candidate_config=candidate_config(True),
        staged_summary=staged_summary(0),
        staged_orders=staged_orders(),
        staged_rejections=pd.DataFrame(),
        thresholds=LaunchThresholds(max_total_notional=2_000.0, max_order_notional=1_000.0),
        mode="paper",
        adapter="normalized",
    )

    assert report.ready
    assert report.launch_orders.iloc[0]["launch_mode"] == "paper"
    assert report.launch_orders.iloc[0]["scenario_key"] == "trigger_ticks=2|order_latency_us=100"
    assert report.summary.iloc[0]["recommendation"] == "paper_or_shadow_launch"


def test_write_launch_bundle_outputs_orders_config_and_manifest(tmp_path):
    promotion_dir, staged_dir = write_inputs(tmp_path)
    out_dir = tmp_path / "launch"

    report = write_launch_bundle(
        promotion_dir=promotion_dir,
        staged_orders_dir=staged_dir,
        output_dir=out_dir,
        thresholds=LaunchThresholds(max_total_notional=2_000.0),
        mode="shadow",
        adapter="arrow_money",
    )

    config = json.loads((out_dir / "launch_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert config["adapter"] == "arrow_money"
    assert config["order_batch"]["accepted_orders"] == 2
    assert (out_dir / "launch_orders.csv").exists()
    assert (out_dir / "launch_checks.csv").exists()
    assert (out_dir / "launch_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_launch_bundle_can_require_quote_risk_review_for_surface_orders():
    report = evaluate_launch_bundle(
        promotion_summary=promotion_summary(True),
        candidate_config=candidate_config(True),
        staged_summary=staged_summary(0, quote_risk_review_passed=True),
        staged_orders=staged_orders(),
        staged_rejections=pd.DataFrame(),
        thresholds=LaunchThresholds(require_quote_risk_review=True),
        mode="paper",
        adapter="normalized",
    )

    checks = report.checks.set_index("check")
    assert report.ready
    assert bool(checks.loc["surface_quote_risk_review", "passed"])
    assert bool(report.summary.loc[0, "quote_risk_review_required"])
    assert bool(report.summary.loc[0, "quote_risk_review_passed"])


def test_launch_bundle_fails_surface_orders_without_quote_risk_review():
    report = evaluate_launch_bundle(
        promotion_summary=promotion_summary(True),
        candidate_config=candidate_config(True),
        staged_summary=staged_summary(0),
        staged_orders=staged_orders(),
        staged_rejections=pd.DataFrame(),
        thresholds=LaunchThresholds(require_quote_risk_review=True),
        mode="shadow",
        adapter="arrow_money",
    )

    failed = report.checks.loc[~report.checks["passed"]]
    assert not report.ready
    assert set(failed["check"]) == {"surface_quote_risk_review"}


def test_unified_cli_launch_bundle_fails_closed_on_rejections(tmp_path):
    promotion_dir, staged_dir = write_inputs(tmp_path, rejected_orders=1)
    out_dir = tmp_path / "cli_launch"

    code = main(
        [
            "launch-bundle",
            "--promotion",
            str(promotion_dir),
            "--staged-orders",
            str(staged_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "launch_checks.csv").exists()
    assert (out_dir / "launch_config.json").exists()


def test_unified_cli_launch_bundle_requires_quote_risk_review(tmp_path):
    promotion_dir, staged_dir = write_inputs(tmp_path)
    out_dir = tmp_path / "cli_launch_quote_review"

    code = main(
        [
            "launch-bundle",
            "--promotion",
            str(promotion_dir),
            "--staged-orders",
            str(staged_dir),
            "--out",
            str(out_dir),
            "--require-quote-risk-review",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "launch_checks.csv")
    assert code == 2
    assert "surface_quote_risk_review" in set(checks.loc[~checks["passed"], "check"])
