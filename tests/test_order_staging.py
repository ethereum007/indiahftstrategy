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
