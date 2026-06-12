import pandas as pd

from research.settlement import (
    expiring_option_intrinsic,
    projected_settlement,
    running_settlement_average,
    settlement_convergence_value,
)


def test_running_settlement_average_uses_window_ticks_only():
    ticks = pd.DataFrame(
        [
            {"ts": 0, "bid": 99.0, "ask": 101.0},
            {"ts": 100, "bid": 100.0, "ask": 102.0},
            {"ts": 200, "bid": 102.0, "ask": 104.0},
            {"ts": 300, "bid": 110.0, "ask": 112.0},
        ]
    )

    avg = running_settlement_average(
        ticks,
        window_start_ns=100,
        window_end_ns=300,
    )

    assert list(avg["ts"]) == [100, 200, 300]
    assert list(avg["settlement_price"]) == [101.0, 103.0, 111.0]
    assert list(avg["running_average"]) == [101.0, 102.0, 105.0]
    assert list(avg["known_fraction"]) == [0.0, 0.5, 1.0]


def test_projected_settlement_and_expiring_intrinsic():
    projected = projected_settlement(
        running_average=102.0,
        known_fraction=0.5,
        current_index=106.0,
    )

    assert projected == 104.0
    assert expiring_option_intrinsic(option_type="C", strike=100.0, projected_settlement_value=104.0) == 4.0
    assert expiring_option_intrinsic(option_type="P", strike=105.0, projected_settlement_value=104.0) == 1.0
    assert (
        settlement_convergence_value(
            option_type="C",
            strike=103.0,
            running_average=102.0,
            known_fraction=0.5,
            current_index=106.0,
        )
        == 1.0
    )
