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


def venue():
    return VenueConfig(
        "NSE",
        LatencyModel(feed_us=0, order_us=0, jitter_us=0, _rng=np.random.default_rng(1)),
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
        call_timestamps=[0],
        put_timestamps=[0, 100],
        future_timestamps=[0, 100],
    )

    engine.run()

    guard = strategy.execution_guard_report()
    assert engine.orders_sent == 0
    assert not guard["guard_passed"].any()
    assert set(guard["guard_reason"]) == {"stale_leg_book"}
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
        call_timestamps=[0],
        put_timestamps=[0, 100],
        future_timestamps=[0, 100],
    )

    engine.run()

    guard = strategy.execution_guard_report()
    assert engine.orders_sent == 0
    assert set(guard["guard_reason"]) == {"leg_book_skew_exceeded"}
    assert set(guard["leg_book_skew_ns"]) == {100}


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
):
    return MultiInstrumentEngine(
        instruments={
            "CALL1000": InstrumentConfig(
                Instrument("CALL1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
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
                    [
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
                    [
                        (
                            ts,
                            1008.0,
                            1009.0,
                            75,
                            75,
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
        venues={"NSE": venue()},
        strategy=strategy,
    )
