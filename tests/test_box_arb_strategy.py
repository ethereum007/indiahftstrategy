import numpy as np
import pandas as pd
import pytest

from engine.hft_backtest import (
    IndianCostModel,
    Instrument,
    Kind,
    LatencyModel,
)
from engine.multi_engine import (
    InstrumentConfig,
    MultiInstrumentEngine,
    VenueConfig,
)
from strategies.box_arb import (
    BoxArbConfig,
    BoxArbTakerStrategy,
    BoxLegMap,
)


EXPIRY = "2026-06-30"


def no_costs():
    return IndianCostModel(
        stt_sell=0.0,
        exch_txn=0.0,
        sebi_fee=0.0,
        stamp_buy=0.0,
    )


def book(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "ts",
            "bid",
            "ask",
            "bid_qty",
            "ask_qty",
            "last",
            "last_qty",
        ],
    )


def venue(*, order_us=0.0):
    return VenueConfig(
        "NSE",
        LatencyModel(
            feed_us=0.0,
            order_us=order_us,
            jitter_us=0.0,
            _rng=np.random.default_rng(1),
        ),
    )


def box_signals(direction="buy_box", **updates):
    row = {
        "ts": 0,
        "expiry": EXPIRY,
        "low_strike": 1000.0,
        "high_strike": 1010.0,
        "direction": direction,
        "qty": 75,
        "net_edge": 150.0,
    }
    row.update(updates)
    return pd.DataFrame([row])


def leg_map():
    return BoxLegMap(
        call_by_contract={
            (EXPIRY, 1000.0): "LOW_CALL",
            (EXPIRY, 1010.0): "HIGH_CALL",
        },
        put_by_contract={
            (EXPIRY, 1000.0): "LOW_PUT",
            (EXPIRY, 1010.0): "HIGH_PUT",
        },
    )


def test_box_arb_taker_routes_four_ioc_legs_and_proves_realized_edge():
    strategy = BoxArbTakerStrategy(
        box_signals(),
        leg_map(),
        BoxArbConfig(max_signal_age_ns=1_000),
    )
    engine = box_engine(strategy)

    result = engine.run()

    strategy_fills = result.fills.loc[
        result.fills["oid"].isin([1, 2, 3, 4])
    ]
    assert engine.orders_sent == 4
    assert len(strategy_fills) == 4
    assert set(strategy_fills["instrument_id"]) == {
        "LOW_CALL",
        "LOW_PUT",
        "HIGH_CALL",
        "HIGH_PUT",
    }
    outcome = strategy.legging_report().iloc[0]
    assert int(outcome["expected_order_count"]) == 4
    assert int(outcome["fully_filled_leg_count"]) == 4
    assert not bool(outcome["partial"])
    assert bool(outcome["routing_complete"])
    assert bool(outcome["fills_complete"])
    assert bool(outcome["realized_edge_evaluable"])
    assert bool(outcome["realized_edge_positive"])
    assert float(outcome["fair_box"]) == 10.0
    assert float(outcome["realized_edge_per_unit"]) == 2.0
    assert float(outcome["realized_gross_edge"]) == 150.0
    assert float(outcome["realized_total_cost"]) == 0.0
    assert float(outcome["realized_net_edge"]) == 150.0
    assert float(outcome["realized_vs_decision_net_edge"]) == 0.0
    assert int(outcome["low_call_side"]) == 1
    assert int(outcome["low_put_side"]) == -1
    assert int(outcome["high_call_side"]) == -1
    assert int(outcome["high_put_side"]) == 1

    guard = strategy.execution_guard_report()
    routed = guard.loc[guard["guard_passed"]].iloc[0]
    assert int(routed["edge_revalidation_qty"]) == 75
    assert bool(routed["decision_multiplier_consistent"])
    assert float(routed["decision_edge_per_unit"]) == 2.0
    assert float(routed["decision_net_edge"]) == 150.0
    assert bool(routed["ioc_batch_preflight_passed"])
    assert int(routed["orders_requested"]) == 4
    assert int(routed["orders_accepted"]) == 4


def test_box_arb_taker_replays_sell_box_direction():
    strategy = BoxArbTakerStrategy(
        box_signals("sell_box"),
        leg_map(),
    )
    engine = box_engine(
        strategy,
        quotes={
            "LOW_CALL": (60.0, 61.0),
            "LOW_PUT": (44.0, 45.0),
            "HIGH_CALL": (3.0, 4.0),
            "HIGH_PUT": (1.0, 2.0),
        },
    )

    engine.run()

    outcome = strategy.legging_report().iloc[0]
    assert int(outcome["low_call_side"]) == -1
    assert int(outcome["low_put_side"]) == 1
    assert int(outcome["high_call_side"]) == 1
    assert int(outcome["high_put_side"]) == -1
    assert float(outcome["realized_edge_per_unit"]) == 2.0
    assert float(outcome["realized_net_edge"]) == 150.0
    assert bool(outcome["realized_edge_positive"])


def test_box_arb_taker_revalidates_decayed_edge_before_preflight():
    strategy = BoxArbTakerStrategy(
        box_signals(net_edge=500.0),
        leg_map(),
    )
    engine = box_engine(
        strategy,
        quotes={
            "LOW_CALL": (54.0, 55.0),
            "LOW_PUT": (44.0, 45.0),
            "HIGH_CALL": (44.0, 45.0),
            "HIGH_PUT": (49.0, 50.0),
        },
    )

    result = engine.run()

    rejected = strategy.execution_guard_report().loc[
        lambda frame: frame["guard_reason"].eq(
            "execution_edge_below_threshold"
        )
    ]
    assert engine.orders_sent == 0
    assert result.fills.empty
    assert not rejected.empty
    assert rejected["edge_revalidation_checked"].all()
    assert set(rejected["signal_net_edge"]) == {500.0}
    assert set(rejected["decision_edge_per_unit"]) == {-7.0}
    assert set(rejected["decision_net_edge"]) == {-525.0}
    assert not rejected["ioc_batch_preflight_attempted"].any()
    assert strategy.legging_report().empty


def test_box_arb_taker_preflights_all_visible_leg_capacity():
    strategy = BoxArbTakerStrategy(
        box_signals(),
        leg_map(),
    )
    engine = box_engine(
        strategy,
        quote_qty_by_instrument={"HIGH_PUT": 50},
    )

    result = engine.run()

    rejected = strategy.execution_guard_report().loc[
        lambda frame: frame["guard_reason"].eq(
            "ioc_batch_preflight_rejected"
        )
    ]
    assert engine.orders_sent == 0
    assert result.fills.empty
    assert not rejected.empty
    assert set(rejected["ioc_batch_preflight_reason"]) == {
        "visible_ioc_capacity_shortfall"
    }
    assert set(
        rejected[
            "ioc_batch_preflight_limiting_instrument_id"
        ]
    ) == {"HIGH_PUT"}
    assert set(rejected["affected_legs"]) == {"high_put"}
    assert strategy.legging_report().empty


def test_box_arb_taker_uses_expiry_aware_contract_mapping():
    other_expiry = "2026-07-31"
    mapped = leg_map()
    mapped.call_by_contract.update(
        {
            (other_expiry, 1000.0): "OTHER_LOW_CALL",
            (other_expiry, 1010.0): "OTHER_HIGH_CALL",
        }
    )
    mapped.put_by_contract.update(
        {
            (other_expiry, 1000.0): "OTHER_LOW_PUT",
            (other_expiry, 1010.0): "OTHER_HIGH_PUT",
        }
    )
    strategy = BoxArbTakerStrategy(
        box_signals(expiry=other_expiry),
        mapped,
    )
    engine = box_engine(
        strategy,
        quotes={
            "OTHER_LOW_CALL": (51.0, 52.0),
            "OTHER_LOW_PUT": (45.0, 46.0),
            "OTHER_HIGH_CALL": (45.0, 46.0),
            "OTHER_HIGH_PUT": (45.0, 46.0),
        },
    )

    result = engine.run()

    strategy_fills = result.fills.loc[
        result.fills["oid"].isin([1, 2, 3, 4])
    ]
    assert engine.orders_sent == 4
    assert set(strategy_fills["instrument_id"]) == {
        "OTHER_LOW_CALL",
        "OTHER_LOW_PUT",
        "OTHER_HIGH_CALL",
        "OTHER_HIGH_PUT",
    }


def test_box_arb_taker_rejects_invalid_config():
    with pytest.raises(
        ValueError,
        match="max_leg_book_skew_ns must be a non-negative integer",
    ):
        BoxArbTakerStrategy(
            box_signals(),
            leg_map(),
            BoxArbConfig(max_leg_book_skew_ns=-1),
        )


def test_box_arb_taker_rejects_duplicate_leg_mapping():
    mapped = leg_map()
    mapped.put_by_contract[(EXPIRY, 1010.0)] = "HIGH_CALL"
    strategy = BoxArbTakerStrategy(
        box_signals(),
        mapped,
    )
    engine = box_engine(strategy)

    result = engine.run()

    assert engine.orders_sent == 0
    assert result.fills.empty
    guard = strategy.execution_guard_report()
    assert set(guard["guard_reason"]) == {
        "duplicate_leg_instrument"
    }
    assert set(guard["affected_legs"]) == {
        "low_call,low_put,high_call,high_put"
    }


def box_engine(
    strategy,
    *,
    quotes=None,
    quote_qty_by_instrument=None,
    timestamps=(0, 100),
    order_latency_us=0.0,
):
    quotes = quotes or {
        "LOW_CALL": (51.0, 52.0),
        "LOW_PUT": (45.0, 46.0),
        "HIGH_CALL": (45.0, 46.0),
        "HIGH_PUT": (45.0, 46.0),
    }
    quote_qty_by_instrument = quote_qty_by_instrument or {}
    instruments = {}
    for instrument_id, (bid, ask) in quotes.items():
        qty = quote_qty_by_instrument.get(
            instrument_id,
            75,
        )
        instruments[instrument_id] = InstrumentConfig(
            Instrument(
                instrument_id,
                Kind.OPT,
                lot_size=75,
                tick=0.05,
            ),
            "NSE",
            book(
                [
                    (
                        ts,
                        bid,
                        ask,
                        qty,
                        qty,
                        np.nan,
                        0,
                    )
                    for ts in timestamps
                ]
            ),
            costs=no_costs(),
        )
    return MultiInstrumentEngine(
        instruments=instruments,
        venues={"NSE": venue(order_us=order_latency_us)},
        strategy=strategy,
    )
