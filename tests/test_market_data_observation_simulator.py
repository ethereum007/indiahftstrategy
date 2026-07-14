from __future__ import annotations

import pandas as pd
import pytest

from market_data_observation_simulator import (
    BoundedMarketDataSimulationConfig,
    MarketDataObservationSimulationError,
    simulate_bounded_market_data_session,
)


def _simulate(**config_overrides):
    config = BoundedMarketDataSimulationConfig(**config_overrides)
    return simulate_bounded_market_data_session(
        config=config,
        provider="arrow_money",
        adapter="arrow_ws",
        transport="websocket",
        market="india_nse_index_derivatives",
        exchange="NSE",
        session_id="nse-live-dryrun-20260714",
        trading_date="2026-07-14",
        timezone_name="Asia/Kolkata",
        open_local="09:15",
        close_local="15:30",
        kill_switch_enabled=True,
    )


def test_bounded_market_data_simulation_is_complete_and_deterministic():
    first = _simulate(event_count=5, interval_ms=250)
    second = _simulate(event_count=5, interval_ms=250)

    assert first.completed
    assert not first.halted
    assert first.accepted_event_count == 5
    assert first.attempted_event_count == 5
    assert first.telemetry["accepted"].tolist() == [True] * 5
    assert first.telemetry["ts_ns"].is_monotonic_increasing
    assert (first.telemetry["ask_price"] > first.telemetry["bid_price"]).all()
    pd.testing.assert_frame_equal(first.telemetry, second.telemetry)


def test_bounded_market_data_simulation_halts_at_session_boundary():
    result = _simulate(
        event_count=3,
        interval_ms=1000,
        start_offset_seconds=(6 * 60 * 60) + (15 * 60) - 1,
    )

    assert result.halted
    assert not result.completed
    assert result.halt_reason == "outside_session_window"
    assert result.attempted_event_count == 2
    assert result.accepted_event_count == 1
    assert not bool(result.telemetry.iloc[-1]["accepted"])


@pytest.mark.parametrize(
    ("fault_mode", "expected_reason"),
    [
        ("invalid_quote", "invalid_quote"),
        ("non_monotonic_timestamp", "non_monotonic_timestamp"),
    ],
)
def test_bounded_market_data_simulation_kill_switches_on_fault(
    fault_mode,
    expected_reason,
):
    result = _simulate(
        event_count=5,
        fault_mode=fault_mode,
        fault_at_event=3,
    )

    assert result.halted
    assert result.halt_reason == expected_reason
    assert result.attempted_event_count == 3
    assert result.accepted_event_count == 2
    assert result.telemetry.iloc[-1]["breach_code"] == expected_reason


def test_bounded_market_data_simulation_requires_armed_kill_switch():
    with pytest.raises(
        MarketDataObservationSimulationError,
        match="armed kill switch",
    ):
        simulate_bounded_market_data_session(
            config=BoundedMarketDataSimulationConfig(event_count=1),
            provider="arrow_money",
            adapter="arrow_ws",
            transport="websocket",
            market="india_nse_index_derivatives",
            exchange="NSE",
            session_id="session",
            trading_date="2026-07-14",
            timezone_name="Asia/Kolkata",
            open_local="09:15",
            close_local="15:30",
            kill_switch_enabled=False,
        )


@pytest.mark.parametrize(
    "config",
    [
        BoundedMarketDataSimulationConfig(event_count=0),
        BoundedMarketDataSimulationConfig(interval_ms=0),
        BoundedMarketDataSimulationConfig(spread=0),
        BoundedMarketDataSimulationConfig(fault_mode="unknown"),
        BoundedMarketDataSimulationConfig(
            event_count=2,
            fault_mode="invalid_quote",
            fault_at_event=1,
        ),
    ],
)
def test_bounded_market_data_simulation_rejects_invalid_config(config):
    with pytest.raises(MarketDataObservationSimulationError):
        simulate_bounded_market_data_session(
            config=config,
            provider="arrow_money",
            adapter="arrow_ws",
            transport="websocket",
            market="india_nse_index_derivatives",
            exchange="NSE",
            session_id="session",
            trading_date="2026-07-14",
            timezone_name="Asia/Kolkata",
            open_local="09:15",
            close_local="15:30",
            kill_switch_enabled=True,
        )
