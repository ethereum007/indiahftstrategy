from __future__ import annotations

import pandas as pd
import pytest

from market_data_observation_simulator import (
    BoundedMarketDataSimulationConfig,
    simulate_bounded_market_data_session,
)
from shadow_microprice_evaluator import (
    ShadowKillSwitch,
    ShadowMicropriceConfig,
    ShadowMicropriceEvaluationError,
    ShadowRuntimeLimits,
    evaluate_shadow_microprice_session,
)


def _telemetry(event_count=6):
    return simulate_bounded_market_data_session(
        config=BoundedMarketDataSimulationConfig(event_count=event_count),
        provider="arrow_money",
        adapter="arrow_ws",
        transport="websocket",
        market="india_nse_index_derivatives",
        exchange="NSE",
        session_id="shadow-test",
        trading_date="2026-07-14",
        timezone_name="Asia/Kolkata",
        open_local="09:15",
        close_local="15:30",
        kill_switch_enabled=True,
    ).telemetry


def _limits(**overrides):
    values = {
        "max_orders_per_session": 100,
        "max_notional_per_session": 1_000_000.0,
        "max_open_orders": 10,
        "max_position_lots": 5,
    }
    values.update(overrides)
    return ShadowRuntimeLimits(**values)


def _kill_switch(**overrides):
    values = {
        "enabled": True,
        "trigger_on_limit_breach": True,
        "stop_new_orders": True,
        "cancel_open_orders": True,
    }
    values.update(overrides)
    return ShadowKillSwitch(**values)


def _evaluate(*, event_count=6, config=None, limits=None, kill_switch=None):
    return evaluate_shadow_microprice_session(
        _telemetry(event_count),
        config=config or ShadowMicropriceConfig(),
        limits=limits or _limits(),
        kill_switch=kill_switch or _kill_switch(),
    )


def test_shadow_evaluator_observes_deterministic_entry_exit_cycles():
    first = _evaluate()
    second = _evaluate()

    assert first.completed
    assert not first.halted
    assert first.processed_event_count == 6
    assert first.observed_intent_count == 4
    assert first.rejected_intent_count == 0
    assert first.ending_shadow_position_lots == 0
    assert first.max_shadow_open_orders == 0
    assert first.intents["action"].tolist() == [
        "entry",
        "exit_decay",
        "entry",
        "exit_decay",
    ]
    assert first.intents["side"].tolist() == [1, -1, -1, 1]
    assert first.intents["within_limits"].tolist() == [True] * 4
    assert set(first.intents["routing_status"]) == {"not_routable"}
    assert set(first.intents["submission_status"]) == {"not_submitted"}
    pd.testing.assert_frame_equal(first.features, second.features)
    pd.testing.assert_frame_equal(first.intents, second.intents)


@pytest.mark.parametrize(
    ("limits", "config", "reason"),
    [
        (_limits(max_orders_per_session=1), None, "max_orders_per_session"),
        (
            _limits(max_notional_per_session=10_000.0),
            None,
            "max_notional_per_session",
        ),
        (
            _limits(max_position_lots=1),
            ShadowMicropriceConfig(intent_quantity_lots=2),
            "max_position_lots",
        ),
    ],
)
def test_shadow_evaluator_kill_switches_on_retained_limit_breach(
    limits,
    config,
    reason,
):
    result = _evaluate(config=config, limits=limits)

    assert result.halted
    assert not result.completed
    assert result.halt_reason == reason
    assert result.rejected_intent_count == 1
    assert not bool(result.intents.iloc[-1]["within_limits"])
    assert result.intents.iloc[-1]["intent_status"] == "rejected_limit"
    assert result.intents.iloc[-1]["routing_status"] == "not_routable"
    assert result.intents.iloc[-1]["submission_status"] == "not_submitted"


def test_shadow_evaluator_terminally_flattens_hypothetical_position():
    result = _evaluate(event_count=2)

    assert result.completed
    assert result.ending_shadow_position_lots == 0
    assert result.intents["action"].tolist() == ["entry", "terminal_flatten"]
    assert result.intents["ts_ns"].nunique() == 2


def test_shadow_evaluator_completes_when_no_signal_qualifies():
    result = _evaluate(
        config=ShadowMicropriceConfig(entry_imbalance=0.9),
    )

    assert result.completed
    assert result.intents.empty
    assert result.observed_intent_count == 0


def test_shadow_evaluator_requires_complete_kill_switch_contract():
    with pytest.raises(ShadowMicropriceEvaluationError, match="kill-switch"):
        _evaluate(kill_switch=_kill_switch(stop_new_orders=False))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda frame: frame.drop(columns=["bid_qty"]),
        lambda frame: frame.assign(sequence=[2, 3, 4, 5, 6, 7]),
        lambda frame: frame.assign(ts_ns=list(reversed(frame["ts_ns"].tolist()))),
        lambda frame: frame.assign(accepted=False),
        lambda frame: frame.assign(source_mode="provider_network"),
    ],
)
def test_shadow_evaluator_rejects_invalid_launcher_telemetry(mutator):
    with pytest.raises(ShadowMicropriceEvaluationError):
        evaluate_shadow_microprice_session(
            mutator(_telemetry()),
            config=ShadowMicropriceConfig(),
            limits=_limits(),
            kill_switch=_kill_switch(),
        )


@pytest.mark.parametrize(
    "config",
    [
        ShadowMicropriceConfig(lot_size=0),
        ShadowMicropriceConfig(tick_size=0),
        ShadowMicropriceConfig(exit_imbalance=0.7),
        ShadowMicropriceConfig(terminal_flatten=False),
    ],
)
def test_shadow_evaluator_rejects_invalid_config(config):
    with pytest.raises(ShadowMicropriceEvaluationError):
        evaluate_shadow_microprice_session(
            _telemetry(),
            config=config,
            limits=_limits(),
            kill_switch=_kill_switch(),
        )
