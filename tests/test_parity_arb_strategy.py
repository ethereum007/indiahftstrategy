import numpy as np
import pandas as pd
import pytest

from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import (
    IOCBatchPreflightResult,
    InstrumentConfig,
    MultiInstrumentEngine,
    VenueConfig,
)
from strategies.parity_arb import ParityArbConfig, ParityArbTakerStrategy, ParityLegMap


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def book(rows):
    return pd.DataFrame(
        rows,
        columns=["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"],
    )


def venue(*, order_us=0):
    return VenueConfig(
        "NSE",
        LatencyModel(
            feed_us=0,
            order_us=order_us,
            jitter_us=0,
            _rng=np.random.default_rng(1),
        ),
    )


def test_parity_arb_taker_routes_three_ioc_legs_and_tracks_fills():
    signals = pd.DataFrame(
        [
            {
                "ts": 0,
                "strike": 1000.0,
                "direction": "buy_synthetic_sell_future",
                "qty": 75,
            }
        ]
    )
    strategy = ParityArbTakerStrategy(
        signals,
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(max_signal_age_ns=1_000),
    )
    engine = MultiInstrumentEngine(
        instruments={
            "CALL1000": InstrumentConfig(
                Instrument("CALL1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 54.0, 55.0, 75, 75, np.nan, 0),
                        (100, 54.0, 55.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "PUT1000": InstrumentConfig(
                Instrument("PUT1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 60.0, 61.0, 75, 75, np.nan, 0),
                        (100, 60.0, 61.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "FUT": InstrumentConfig(
                Instrument("FUT", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 1008.0, 1009.0, 75, 75, np.nan, 0),
                        (100, 1008.0, 1009.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    assert engine.orders_sent == 3
    strategy_fills = result.fills.loc[result.fills["oid"].isin([1, 2, 3])]
    assert len(strategy_fills) == 3
    assert set(strategy_fills["instrument_id"]) == {"CALL1000", "PUT1000", "FUT"}
    assert engine.positions == {"CALL1000": 0, "PUT1000": 0, "FUT": 0}
    legging = strategy.legging_report()
    assert not bool(legging.iloc[0]["partial"])
    assert legging.iloc[0]["fill_count"] == 3
    outcome = legging.iloc[0]
    assert bool(outcome["realized_edge_evidence_enabled"])
    assert bool(outcome["realized_edge_evaluable"])
    assert bool(outcome["realized_edge_positive"])
    assert int(outcome["call_order_id"]) == 1
    assert int(outcome["put_order_id"]) == 2
    assert int(outcome["future_order_id"]) == 3
    assert int(outcome["call_filled_qty"]) == 75
    assert int(outcome["put_filled_qty"]) == 75
    assert int(outcome["future_filled_qty"]) == 75
    assert float(outcome["realized_edge_per_unit"]) == 13.0
    assert float(outcome["realized_gross_edge"]) == 975.0
    assert float(outcome["realized_total_cost"]) == 0.0
    assert float(outcome["realized_net_edge"]) == 975.0
    assert float(outcome["realized_vs_decision_net_edge"]) == 0.0
    assert int(outcome["fill_span_ns"]) == 0
    routed_guard = strategy.execution_guard_report().loc[
        lambda frame: frame["guard_passed"]
    ].iloc[0]
    assert bool(routed_guard["edge_revalidation_checked"])
    assert int(routed_guard["edge_revalidation_qty"]) == 75
    assert float(routed_guard["decision_edge_per_unit"]) == 13.0
    assert float(routed_guard["decision_gross_edge"]) == 975.0
    assert float(routed_guard["decision_total_cost"]) == 0.0
    assert float(routed_guard["decision_net_edge"]) == 975.0
    assert bool(
        routed_guard[
            "ioc_batch_preflight_visible_capacity_checked"
        ]
    )
    assert routed_guard[
        "ioc_batch_preflight_min_visible_fill_ratio"
    ] == 1
    assert (
        routed_guard[
            "ioc_batch_preflight_limiting_instrument_id"
        ]
        == "CALL1000"
    )


def test_parity_arb_taker_revalidates_decayed_edge_before_preflight():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                    "net_edge": 500.0,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        future_bid=990.0,
        future_ask=991.0,
    )

    result = engine.run()

    guard = strategy.execution_guard_report()
    rejected = guard.loc[
        guard["guard_reason"].eq("execution_edge_below_threshold")
    ]
    assert engine.orders_sent == 0
    assert result.fills.empty
    assert not rejected.empty
    assert rejected["edge_revalidation_checked"].all()
    assert set(rejected["signal_net_edge"]) == {500.0}
    assert set(rejected["decision_edge_per_unit"]) == {-5.0}
    assert set(rejected["decision_net_edge"]) == {-375.0}
    assert not rejected["ioc_batch_preflight_attempted"].any()
    assert strategy.legging_report().empty


def test_parity_arb_taker_recomputes_realized_edge_from_favorable_fills():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        order_latency_us=0.1,
        call_quotes=[
            (0, 54.0, 55.0, 75, 75, np.nan, 0),
            (50, 53.0, 54.0, 75, 75, np.nan, 0),
            (100, 53.0, 54.0, 75, 75, np.nan, 0),
        ],
        put_quotes=[
            (0, 60.0, 61.0, 75, 75, np.nan, 0),
            (50, 61.0, 62.0, 75, 75, np.nan, 0),
            (100, 61.0, 62.0, 75, 75, np.nan, 0),
        ],
        future_quotes=[
            (0, 1008.0, 1009.0, 75, 75, np.nan, 0),
            (50, 1009.0, 1010.0, 75, 75, np.nan, 0),
            (100, 1009.0, 1010.0, 75, 75, np.nan, 0),
        ],
    )

    result = engine.run()

    outcome = strategy.legging_report().iloc[0]
    assert len(result.fills.loc[result.fills["oid"].isin([1, 2, 3])]) == 3
    assert float(outcome["decision_net_edge"]) == 975.0
    assert float(outcome["call_fill_vwap"]) == 54.0
    assert float(outcome["put_fill_vwap"]) == 61.0
    assert float(outcome["future_fill_vwap"]) == 1009.0
    assert float(outcome["realized_edge_per_unit"]) == 16.0
    assert float(outcome["realized_gross_edge"]) == 1200.0
    assert float(outcome["realized_net_edge"]) == 1200.0
    assert float(outcome["realized_vs_decision_net_edge"]) == 225.0
    assert bool(outcome["realized_edge_positive"])


def test_parity_arb_taker_recomputes_reverse_realized_edge():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "sell_synthetic_buy_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        order_latency_us=0.1,
        call_quotes=[
            (0, 54.0, 55.0, 75, 75, np.nan, 0),
            (50, 55.0, 56.0, 75, 75, np.nan, 0),
            (100, 55.0, 56.0, 75, 75, np.nan, 0),
        ],
        put_quotes=[
            (0, 60.0, 61.0, 75, 75, np.nan, 0),
            (50, 59.0, 60.0, 75, 75, np.nan, 0),
            (100, 59.0, 60.0, 75, 75, np.nan, 0),
        ],
        future_quotes=[
            (0, 979.0, 980.0, 75, 75, np.nan, 0),
            (50, 978.0, 979.0, 75, 75, np.nan, 0),
            (100, 978.0, 979.0, 75, 75, np.nan, 0),
        ],
    )

    result = engine.run()

    outcome = strategy.legging_report().iloc[0]
    strategy_fills = result.fills.loc[
        result.fills["oid"].isin([1, 2, 3])
    ]
    assert len(strategy_fills) == 3
    assert int(outcome["call_side"]) == -1
    assert int(outcome["put_side"]) == 1
    assert int(outcome["future_side"]) == 1
    assert float(outcome["decision_net_edge"]) == 975.0
    assert float(outcome["call_fill_vwap"]) == 55.0
    assert float(outcome["put_fill_vwap"]) == 60.0
    assert float(outcome["future_fill_vwap"]) == 979.0
    assert float(outcome["realized_edge_per_unit"]) == 16.0
    assert float(outcome["realized_gross_edge"]) == 1200.0
    assert float(outcome["realized_net_edge"]) == 1200.0
    assert float(outcome["realized_vs_decision_net_edge"]) == 225.0
    assert bool(outcome["realized_edge_positive"])


def test_parity_arb_taker_resets_run_state_when_reused():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(max_signal_age_ns=1_000),
    )

    first = _parity_engine(strategy)
    first.run()
    assert len(strategy.executions) == 1
    assert len(strategy.order_to_execution) == 3

    second = _parity_engine(strategy)
    second.run()
    assert len(strategy.executions) == 1
    assert len(strategy.order_to_execution) == 3
    assert strategy.legging_report().iloc[0]["fill_count"] == 3


def test_parity_arb_taker_defers_stale_cached_leg_books():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 100,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(
            max_signal_age_ns=1_000,
            max_leg_book_age_ns=50,
            max_leg_book_skew_ns=1_000,
        ),
    )
    engine = _parity_engine(
        strategy,
        call_timestamps=[100],
        put_timestamps=[200],
        future_timestamps=[200],
    )

    engine.run()

    guard = strategy.execution_guard_report()
    assert engine.orders_sent == 0
    assert not guard["guard_passed"].any()
    assert "stale_leg_book" in set(guard["guard_reason"])
    assert guard.iloc[-1]["guard_reason"] == "stale_leg_book"
    assert guard.iloc[-1]["affected_legs"] == "call"
    assert int(guard.iloc[-1]["call_book_age_ns"]) == 100


def test_parity_arb_taker_defers_cross_leg_book_skew():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 100,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(
            max_signal_age_ns=1_000,
            max_leg_book_age_ns=1_000,
            max_leg_book_skew_ns=50,
        ),
    )
    engine = _parity_engine(
        strategy,
        call_timestamps=[100],
        put_timestamps=[200],
        future_timestamps=[200],
    )

    engine.run()

    guard = strategy.execution_guard_report()
    assert engine.orders_sent == 0
    assert "leg_book_skew_exceeded" in set(guard["guard_reason"])
    assert guard.iloc[-1]["guard_reason"] == "leg_book_skew_exceeded"
    assert int(guard.iloc[-1]["leg_book_skew_ns"]) == 100


def test_parity_arb_taker_preflights_rejected_third_leg_before_routing():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        future_max_position_lots=0,
    )

    result = engine.run()

    guard = strategy.execution_guard_report()
    attempted = guard.loc[
        guard["ioc_batch_preflight_attempted"]
    ]
    assert engine.orders_sent == 0
    assert result.fills.empty
    assert result.order_rejections.empty
    assert not attempted.empty
    assert not attempted["guard_passed"].any()
    assert set(attempted["guard_reason"]) == {
        "ioc_batch_preflight_rejected"
    }
    assert set(attempted["ioc_batch_preflight_reason"]) == {
        "instrument_position_limit"
    }
    assert set(attempted["ioc_batch_preflight_instrument_id"]) == {
        "FUT"
    }
    assert set(attempted["affected_legs"]) == {"future"}
    assert strategy.legging_report().empty


def test_parity_arb_taker_preflights_visible_third_leg_capacity():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        future_quote_qty=50,
    )

    result = engine.run()

    guard = strategy.execution_guard_report()
    rejected = guard.loc[
        guard["guard_reason"].eq("ioc_batch_preflight_rejected")
    ]
    assert engine.orders_sent == 0
    assert result.fills.empty
    assert result.order_rejections.empty
    assert not rejected.empty
    assert set(rejected["ioc_batch_preflight_reason"]) == {
        "visible_ioc_capacity_shortfall"
    }
    assert set(
        rejected["ioc_batch_preflight_limiting_instrument_id"]
    ) == {"FUT"}
    assert set(
        rejected["ioc_batch_preflight_requested_qty"]
    ) == {75}
    assert set(
        rejected["ioc_batch_preflight_available_qty"]
    ) == {0}
    assert strategy.legging_report().empty


def test_parity_arb_taker_marks_post_preflight_rejection_incomplete(
    monkeypatch,
):
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
    )
    engine = _parity_engine(
        strategy,
        future_max_position_lots=0,
    )
    monkeypatch.setattr(
        engine,
        "preflight_ioc_batch",
        lambda intents: IOCBatchPreflightResult(
            passed=True,
            reason="passed",
            visible_capacity_checked=True,
            min_visible_fill_ratio=1.0,
            limiting_instrument_id="CALL1000",
            requested_qty=75,
            available_qty=75,
            touch_price=55.0,
            limit_price=55.0,
        ),
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin([1, 2])]
    guard = strategy.execution_guard_report()
    legging = strategy.legging_report()
    routed_guard = guard.loc[guard["guard_passed"]].iloc[0]
    assert engine.orders_sent == 2
    assert len(strategy_fills) == 2
    assert bool(routed_guard["ioc_batch_preflight_attempted"])
    assert bool(routed_guard["ioc_batch_preflight_passed"])
    assert routed_guard["ioc_batch_preflight_reason"] == "passed"
    assert routed_guard["routing_status"] == "partial"
    assert int(routed_guard["orders_accepted"]) == 2
    assert bool(legging.iloc[0]["partial"])
    assert not bool(legging.iloc[0]["routing_complete"])
    assert int(legging.iloc[0]["route_rejection_count"]) == 1
    assert int(legging.iloc[0]["fully_filled_leg_count"]) == 2
    assert int(legging.iloc[0]["unfilled_leg_count"]) == 1


def test_parity_arb_taker_rejects_negative_execution_guard_limits():
    with pytest.raises(
        ValueError,
        match="max_leg_book_age_ns must be a non-negative integer",
    ):
        ParityArbTakerStrategy(
            pd.DataFrame(
                [
                    {
                        "ts": 0,
                        "strike": 1000.0,
                        "direction": "buy_synthetic_sell_future",
                        "qty": 75,
                    }
                ]
            ),
            ParityLegMap(
                future_id="FUT",
                call_by_strike={1000.0: "CALL1000"},
                put_by_strike={1000.0: "PUT1000"},
            ),
            ParityArbConfig(max_leg_book_age_ns=-1),
        )


def _parity_engine(
    strategy,
    *,
    call_timestamps=(0, 100),
    put_timestamps=(0, 100),
    future_timestamps=(0, 100),
    future_max_position_lots=20,
    future_quote_qty=75,
    future_bid=1008.0,
    future_ask=1009.0,
    call_quotes=None,
    put_quotes=None,
    future_quotes=None,
    order_latency_us=0,
):
    return MultiInstrumentEngine(
        instruments={
            "CALL1000": InstrumentConfig(
                Instrument("CALL1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    call_quotes
                    or [
                        (
                            ts,
                            54.0,
                            55.0,
                            75,
                            75,
                            np.nan,
                            0,
                        )
                        for ts in call_timestamps
                    ]
                ),
                costs=no_costs(),
            ),
            "PUT1000": InstrumentConfig(
                Instrument("PUT1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    put_quotes
                    or [
                        (
                            ts,
                            60.0,
                            61.0,
                            75,
                            75,
                            np.nan,
                            0,
                        )
                        for ts in put_timestamps
                    ]
                ),
                costs=no_costs(),
            ),
            "FUT": InstrumentConfig(
                Instrument("FUT", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    future_quotes
                    or [
                        (
                            ts,
                            future_bid,
                            future_ask,
                            future_quote_qty,
                            future_quote_qty,
                            np.nan,
                            0,
                        )
                        for ts in future_timestamps
                    ]
                ),
                costs=no_costs(),
                max_position_lots=future_max_position_lots,
            ),
        },
        venues={"NSE": venue(order_us=order_latency_us)},
        strategy=strategy,
    )
