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
