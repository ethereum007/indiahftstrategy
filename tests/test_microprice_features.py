from __future__ import annotations

import math

import pytest

from strategies.microprice_features import (
    microprice_entry_side,
    microprice_exit_action,
    microprice_features,
)


def test_microprice_features_and_entry_side_match_depth_pressure():
    positive = microprice_features(
        {"bid": 100.0, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
        0.05,
    )
    negative = microprice_features(
        {"bid": 100.0, "ask": 100.05, "bid_qty": 100, "ask_qty": 900},
        0.05,
    )

    assert positive is not None
    assert negative is not None
    assert positive["imbalance"] == pytest.approx(0.8)
    assert positive["microprice_edge_ticks"] == pytest.approx(0.4)
    assert negative["imbalance"] == pytest.approx(-0.8)
    assert negative["microprice_edge_ticks"] == pytest.approx(-0.4)
    assert microprice_entry_side(
        positive,
        entry_imbalance=0.6,
        min_microprice_edge_ticks=0.25,
    ) == 1
    assert microprice_entry_side(
        negative,
        entry_imbalance=0.6,
        min_microprice_edge_ticks=0.25,
    ) == -1


def test_microprice_exit_action_preserves_hold_precedence():
    decayed = {"imbalance": 0.1}
    assert microprice_exit_action(
        decayed,
        position_lots=1,
        entry_ts_ns=100,
        now_ns=200,
        hold_ns=1_000,
        exit_imbalance=0.15,
    ) == "exit_decay"
    assert microprice_exit_action(
        decayed,
        position_lots=1,
        entry_ts_ns=100,
        now_ns=1_100,
        hold_ns=1_000,
        exit_imbalance=0.15,
    ) == "exit_hold"


@pytest.mark.parametrize(
    "tick",
    [
        {"bid": 0, "ask": 1, "bid_qty": 1, "ask_qty": 1},
        {"bid": 2, "ask": 1, "bid_qty": 1, "ask_qty": 1},
        {"bid": 1, "ask": 2, "bid_qty": 0, "ask_qty": 1},
        {"bid": math.nan, "ask": 2, "bid_qty": 1, "ask_qty": 1},
    ],
)
def test_microprice_features_reject_invalid_books(tick):
    assert microprice_features(tick, 0.05) is None


def test_microprice_features_requires_positive_finite_tick_size():
    tick = {"bid": 1, "ask": 2, "bid_qty": 1, "ask_qty": 1}
    with pytest.raises(ValueError, match="tick_size"):
        microprice_features(tick, 0)
