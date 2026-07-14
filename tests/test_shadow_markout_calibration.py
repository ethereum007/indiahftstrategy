from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from shadow_markout_calibration import (
    DEFAULT_COST_SCENARIOS,
    ShadowMarkoutCalibrationConfig,
    ShadowMarkoutCalibrationError,
    evaluate_shadow_markout_calibration,
    statutory_fill_cost,
)


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sequence": 1,
                "ts_ns": 0,
                "symbol": "NIFTY-SIM",
                "bid_price": 100.0,
                "ask_price": 100.05,
                "bid_qty": 900,
                "ask_qty": 100,
                "microprice": 100.045,
            },
            {
                "sequence": 2,
                "ts_ns": 100,
                "symbol": "NIFTY-SIM",
                "bid_price": 100.05,
                "ask_price": 100.10,
                "bid_qty": 900,
                "ask_qty": 100,
                "microprice": 100.095,
            },
            {
                "sequence": 3,
                "ts_ns": 200,
                "symbol": "NIFTY-SIM",
                "bid_price": 99.95,
                "ask_price": 100.0,
                "bid_qty": 100,
                "ask_qty": 900,
                "microprice": 99.955,
            },
        ]
    )


def _intents() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "intent_sequence": 1,
                "source_sequence": 1,
                "ts_ns": 0,
                "symbol": "NIFTY-SIM",
                "action": "entry",
                "side": 1,
                "quantity_lots": 1,
                "quantity_units": 10,
                "limit_price": 100.05,
                "within_limits": True,
                "intent_status": "shadow_observed",
                "routing_status": "not_routable",
                "submission_status": "not_submitted",
            },
            {
                "intent_sequence": 2,
                "source_sequence": 3,
                "ts_ns": 200,
                "symbol": "NIFTY-SIM",
                "action": "exit_decay",
                "side": -1,
                "quantity_lots": 1,
                "quantity_units": 10,
                "limit_price": 99.95,
                "within_limits": True,
                "intent_status": "shadow_observed",
                "routing_status": "not_routable",
                "submission_status": "not_submitted",
            },
        ]
    )


def _config(**changes) -> ShadowMarkoutCalibrationConfig:
    return replace(
        ShadowMarkoutCalibrationConfig(
            horizons_ns=(0, 100, 200),
            max_horizon_overshoot_ns=0,
            min_covered_observations_per_horizon=1,
            min_coverage_ratio=0.5,
        ),
        **changes,
    )


def test_shadow_markout_calibration_separates_response_and_touch_markout():
    result = evaluate_shadow_markout_calibration(
        _features(),
        _intents(),
        tick_size=0.05,
        source_lot_size=10,
        config=_config(),
    )

    assert result.completed
    assert result.accepted_intent_count == 2
    assert result.observation_count == 6
    entry_100 = result.observations.loc[
        result.observations["observation_id"].eq("intent-1-horizon-100")
    ].iloc[0]
    assert entry_100["directional_mid_move_ticks"] == pytest.approx(1.0)
    assert entry_100["mid_markout_ticks"] == pytest.approx(0.5)
    assert entry_100["touch_markout_ticks"] == pytest.approx(0.0)
    assert entry_100["gross_touch_pnl"] == pytest.approx(0.0)
    assert not bool(entry_100["adverse_selection"])
    entry_200 = result.observations.loc[
        result.observations["observation_id"].eq("intent-1-horizon-200")
    ].iloc[0]
    assert entry_200["directional_mid_move_ticks"] == pytest.approx(-1.0)
    assert bool(entry_200["adverse_selection"])


def test_shadow_markout_calibration_applies_both_reference_cost_hurdles():
    result = evaluate_shadow_markout_calibration(
        _features(),
        _intents(),
        tick_size=0.05,
        source_lot_size=10,
        config=_config(),
    )

    assert set(result.cost_sensitivity["cost_scenario"]) == {
        "nse_index_futures_reference",
        "nse_index_options_reference",
    }
    covered = result.cost_sensitivity.loc[
        result.cost_sensitivity["covered"].astype(bool)
    ]
    assert (covered["round_trip_cost"] > 0).all()
    assert (covered["round_trip_cost_ticks"] > 0).all()
    assert set(covered["reference_status"]) == {
        "repository_reference_requires_external_validation"
    }
    assert not covered.loc[
        covered["observation_id"].eq("intent-1-horizon-100"),
        "cost_break_even_met",
    ].astype(bool).any()


def test_statutory_fill_cost_matches_repository_option_reference():
    options = next(
        scenario
        for scenario in DEFAULT_COST_SCENARIOS
        if scenario.name == "nse_index_options_reference"
    )

    buy = statutory_fill_cost(
        side=1,
        price=150.0,
        quantity_units=75,
        source_lot_size=75,
        scenario=options,
    )
    sell = statutory_fill_cost(
        side=-1,
        price=150.0,
        quantity_units=75,
        source_lot_size=75,
        scenario=options,
    )

    assert buy == pytest.approx(5.0010075)
    assert sell == pytest.approx(21.5385075)


def test_shadow_markout_calibration_marks_sparse_horizon_incomplete():
    result = evaluate_shadow_markout_calibration(
        _features(),
        _intents(),
        tick_size=0.05,
        source_lot_size=10,
        config=_config(horizons_ns=(300,)),
    )

    assert not result.completed
    assert result.covered_observation_count == 0
    assert result.incomplete_reason == "horizon_300_insufficient_count"


def test_shadow_markout_calibration_excludes_rejected_limit_intents():
    intents = _intents()
    intents.loc[1, "within_limits"] = False
    intents.loc[1, "intent_status"] = "rejected_limit"

    result = evaluate_shadow_markout_calibration(
        _features(),
        intents,
        tick_size=0.05,
        source_lot_size=10,
        config=_config(),
    )

    assert result.accepted_intent_count == 1
    assert set(result.observations["intent_sequence"]) == {1}


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("routing_status", "routable", "not_routable"),
        ("submission_status", "submitted", "not_submitted"),
        ("limit_price", 99.0, "source touch"),
        ("side", 0, "side must"),
        ("quantity_units", 11, "source_lot_size"),
        ("ts_ns", 0.5, "non-negative integer"),
    ],
)
def test_shadow_markout_calibration_rejects_unsafe_or_drifted_intents(
    column,
    value,
    message,
):
    intents = _intents()
    intents[column] = intents[column].astype(object)
    intents.loc[0, column] = value

    with pytest.raises(ShadowMarkoutCalibrationError, match=message):
        evaluate_shadow_markout_calibration(
            _features(),
            intents,
            tick_size=0.05,
            source_lot_size=10,
            config=_config(),
        )


@pytest.mark.parametrize(
    "config",
    [
        _config(horizons_ns=(100, 100)),
        _config(min_coverage_ratio=0.0),
        _config(max_horizon_overshoot_ns=-1),
        _config(cost_scenarios=()),
    ],
)
def test_shadow_markout_calibration_rejects_invalid_config(config):
    with pytest.raises(ShadowMarkoutCalibrationError):
        evaluate_shadow_markout_calibration(
            _features(),
            _intents(),
            tick_size=0.05,
            source_lot_size=10,
            config=config,
        )
