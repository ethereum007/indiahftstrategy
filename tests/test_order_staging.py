import json

import pandas as pd

from adapters.orders import (
    OrderStagingLimits,
    stage_orders,
    stage_surface_quote_orders,
    write_staged_orders,
)
from hft_cli import main


def safe_surface_quotes():
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


def write_quote_risk_review(path, *, passed=True):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "snapshots": 1,
                "quotes": 2,
                "instruments": 1,
                "bid_quotes": 1,
                "ask_quotes": 1,
                "bid_share": 0.5,
                "marketable_quotes": 0 if passed else 1,
                "min_quote_edge": 0.2 if passed else -0.1,
                "avg_quote_edge": 0.2,
                "max_market_spread_ticks": 10.0,
                "max_quotes_per_instrument": 2,
                "all_passed": passed,
            }
        ]
    ).to_csv(path / "quote_risk_summary.csv", index=False)


def write_surface_quality_review(path, *, passed=True):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "horizon_ns": 1_000_000_000,
                "observations": 2,
                "unmatched_observations": 0,
                "instruments": 1,
                "theo_mae": 0.10 if passed else 1.0,
                "mid_mae": 0.50,
                "mae_improvement": 0.40 if passed else -0.50,
                "relative_mae_improvement": 0.80 if passed else -1.0,
                "improvement_rate": 1.0 if passed else 0.0,
                "all_passed": passed,
                "failed_checks": 0 if passed else 1,
                "recommendation": "surface_model_usable" if passed else "improve_surface_before_quoting",
            }
        ]
    ).to_csv(path / "surface_quality_summary.csv", index=False)


def test_stage_surface_quotes_accepts_safe_limit_orders():
    report = stage_surface_quote_orders(
        safe_surface_quotes(),
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000, price_band_pct=0.02),
    )

    assert report.passed
    assert len(report.accepted) == 2
    assert report.accepted.iloc[0]["client_order_id"].startswith("STG-")
    assert report.accepted.iloc[0]["order_type"] == "LIMIT"
    assert report.summary.iloc[0]["accepted_orders"] == 2
    assert report.summary.iloc[0]["all_passed"]


def test_stage_orders_preserves_quote_lifecycle_metadata():
    orders = safe_surface_quotes()
    orders["client_order_id"] = ["QLF-000001", "QLF-000002"]
    orders["lifecycle_action"] = ["submit", "replace"]
    orders["lifecycle_action_id"] = ["ACT-000001", "ACT-000002"]
    orders["lifecycle_reason"] = ["new_quote", "price_or_qty_change"]
    orders["lifecycle_message_count"] = [1, 2]
    orders["quote_age_ns"] = [0, 100]
    orders["replaces_order_id"] = ["", "QLF-000001"]

    report = stage_orders(orders, source="surface_quotes")

    assert report.passed
    assert report.accepted["lifecycle_action"].tolist() == ["submit", "replace"]
    assert report.accepted["lifecycle_reason"].tolist() == ["new_quote", "price_or_qty_change"]
    assert report.accepted.loc[1, "replaces_order_id"] == "QLF-000001"


def test_stage_orders_preserves_broker_contract_and_multi_leg_identity():
    orders = safe_surface_quotes()
    orders["research_instrument_id"] = [
        "NIFTY_20260630_1000C",
        "NIFTY_20260630_1000P",
    ]
    orders["broker_instrument_token"] = ["10001", "10002"]
    orders["instrument_resolution_method"] = [
        "semantic_option_identity",
        "semantic_option_identity",
    ]
    orders["instrument_resolution_status"] = ["resolved", "resolved"]
    orders["leg_group_id"] = ["BOX-1", "BOX-1"]
    orders["leg_role"] = ["LOW_CALL", "LOW_PUT"]
    orders["leg_index"] = [0, 1]
    orders["leg_count"] = [2, 2]

    report = stage_orders(orders, source="orders")

    assert report.passed
    assert report.accepted["research_instrument_id"].tolist() == [
        "NIFTY_20260630_1000C",
        "NIFTY_20260630_1000P",
    ]
    assert report.accepted["broker_instrument_token"].tolist() == [
        "10001",
        "10002",
    ]
    assert report.accepted["instrument_resolution_status"].tolist() == [
        "resolved",
        "resolved",
    ]
    assert report.accepted["leg_group_id"].tolist() == ["BOX-1", "BOX-1"]
    assert report.accepted["leg_role"].tolist() == ["LOW_CALL", "LOW_PUT"]
    assert report.accepted["leg_count"].tolist() == [2, 2]


def test_stage_orders_rejects_unsafe_candidates():
    orders = safe_surface_quotes()
    bad = pd.DataFrame(
        [
            {
                "ts": 101,
                "instrument_id": "CALL_1000",
                "side": 1,
                "price": 101.0,
                "qty": 75,
                "market_bid": 99.8,
                "market_ask": 100.3,
                "marketable": True,
            },
            {
                "ts": 102,
                "instrument_id": "PUT_1000",
                "side": "BUY",
                "price": 10.0,
                "qty": 150,
                "market_bid": 9.8,
                "market_ask": 10.3,
            },
            {
                "ts": 103,
                "instrument_id": "PUT_1000",
                "side": "SELL",
                "price": 1000.0,
                "qty": 75,
                "market_bid": 9.8,
                "market_ask": 10.3,
            },
        ]
    )
    combined = pd.concat([orders, bad], ignore_index=True, sort=False)

    report = stage_orders(
        combined,
        source="surface_quotes",
        limits=OrderStagingLimits(
            max_order_qty=75,
            max_notional=10_000,
            price_band_pct=0.05,
            max_orders=1,
        ),
    )

    reasons = ";".join(report.rejected["rejection_reason"])
    assert len(report.accepted) == 1
    assert "max_orders_exceeded" in reasons
    assert "marketable_order" in reasons
    assert "qty_limit" in reasons
    assert "notional_limit" in reasons
    assert "price_band" in reasons


def test_write_staged_orders_outputs_artifacts_and_manifest(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "staged"
    safe_surface_quotes().to_csv(quotes_path, index=False)

    report = write_staged_orders(
        quotes_path,
        output_dir=out_dir,
        source="surface_quotes",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000),
    )

    assert report.output_dir == out_dir
    assert (out_dir / "staged_orders.csv").exists()
    assert (out_dir / "staged_order_rejections.csv").exists()
    assert (out_dir / "staged_order_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_write_staged_orders_accepts_passed_quote_risk_review(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    quote_risk_dir = tmp_path / "quote_review"
    out_dir = tmp_path / "staged_with_quote_review"
    safe_surface_quotes().to_csv(quotes_path, index=False)
    write_quote_risk_review(quote_risk_dir, passed=True)

    report = write_staged_orders(
        quotes_path,
        output_dir=out_dir,
        source="surface_quotes",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000),
        quote_risk_review_dir=quote_risk_dir,
        require_quote_risk_review=True,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert len(report.accepted) == 2
    assert bool(report.summary.loc[0, "quote_risk_review_passed"])
    assert manifest["parameters"]["require_quote_risk_review"]
    assert manifest["parameters"]["quote_risk_review"]["accepted"]
    assert "quote_risk_review" in manifest["inputs"]


def test_write_staged_orders_accepts_passed_surface_quality_review(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    quality_dir = tmp_path / "surface_quality"
    out_dir = tmp_path / "staged_with_surface_quality"
    safe_surface_quotes().to_csv(quotes_path, index=False)
    write_surface_quality_review(quality_dir, passed=True)

    report = write_staged_orders(
        quotes_path,
        output_dir=out_dir,
        source="surface_quotes",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000),
        surface_quality_review_dir=quality_dir,
        require_surface_quality=True,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert len(report.accepted) == 2
    assert bool(report.summary.loc[0, "surface_quality_passed"])
    assert manifest["parameters"]["require_surface_quality"]
    assert manifest["parameters"]["surface_quality"]["accepted"]
    assert "surface_quality" in manifest["inputs"]


def test_write_staged_orders_blocks_surface_quotes_without_required_quote_review(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "staged_missing_quote_review"
    safe_surface_quotes().to_csv(quotes_path, index=False)

    report = write_staged_orders(
        quotes_path,
        output_dir=out_dir,
        source="surface_quotes",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000),
        require_quote_risk_review=True,
    )

    assert not report.passed
    assert report.accepted.empty
    assert len(report.rejected) == 2
    assert set(report.rejected["rejection_reason"]) == {"quote_risk_review_missing"}
    assert not bool(report.summary.loc[0, "all_passed"])
    assert not bool(report.summary.loc[0, "quote_risk_review_provided"])


def test_write_staged_orders_blocks_surface_quotes_without_required_surface_quality(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "staged_missing_surface_quality"
    safe_surface_quotes().to_csv(quotes_path, index=False)

    report = write_staged_orders(
        quotes_path,
        output_dir=out_dir,
        source="surface_quotes",
        limits=OrderStagingLimits(max_order_qty=75, max_notional=10_000),
        require_surface_quality=True,
    )

    assert not report.passed
    assert report.accepted.empty
    assert len(report.rejected) == 2
    assert set(report.rejected["rejection_reason"]) == {"surface_quality_missing"}
    assert not bool(report.summary.loc[0, "all_passed"])
    assert not bool(report.summary.loc[0, "surface_quality_provided"])


def test_unified_cli_stage_orders_can_fail_on_reject(tmp_path):
    orders = pd.DataFrame(
        [
            {"instrument_id": "OPT", "side": 0, "qty": 75, "price": 100.0},
        ]
    )
    orders_path = tmp_path / "orders.csv"
    out_dir = tmp_path / "stage_cli"
    orders.to_csv(orders_path, index=False)

    code = main(
        [
            "stage-orders",
            "--orders",
            str(orders_path),
            "--out",
            str(out_dir),
            "--fail-on-reject",
        ]
    )

    assert code == 2
    assert (out_dir / "staged_order_rejections.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_stage_orders_requires_quote_risk_review(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "stage_quote_review_cli"
    safe_surface_quotes().to_csv(quotes_path, index=False)

    code = main(
        [
            "stage-orders",
            "--orders",
            str(quotes_path),
            "--source",
            "surface_quotes",
            "--out",
            str(out_dir),
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--require-quote-risk-review",
        ]
    )

    summary = pd.read_csv(out_dir / "staged_order_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "all_passed"])
    assert summary.loc[0, "quote_risk_review_reason"] == "quote_risk_review_missing"


def test_unified_cli_stage_orders_requires_surface_quality_review(tmp_path):
    quotes_path = tmp_path / "surface_quotes.csv"
    out_dir = tmp_path / "stage_surface_quality_cli"
    safe_surface_quotes().to_csv(quotes_path, index=False)

    code = main(
        [
            "stage-orders",
            "--orders",
            str(quotes_path),
            "--source",
            "surface_quotes",
            "--out",
            str(out_dir),
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--require-surface-quality",
        ]
    )

    summary = pd.read_csv(out_dir / "staged_order_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "all_passed"])
    assert summary.loc[0, "surface_quality_reason"] == "surface_quality_missing"
