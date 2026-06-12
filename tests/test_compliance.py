import pandas as pd

from risk.compliance import check_order_to_trade_ratio, cross_segment_loss_guard


def test_order_to_trade_ratio_flags_breach():
    ok = check_order_to_trade_ratio(orders_sent=100, fills=50, limit=5.0)
    breach = check_order_to_trade_ratio(orders_sent=100, fills=10, limit=5.0)

    assert ok.ratio == 2.0
    assert not ok.breached
    assert breach.ratio == 10.0
    assert breach.breached


def test_cross_segment_loss_guard_flags_loss_making_driver_segment():
    pnl = pd.DataFrame(
        [
            {"segment": "cash", "pnl": -700.0},
            {"segment": "cash", "pnl": -400.0},
            {"segment": "options", "pnl": 2_500.0},
        ]
    )

    result = cross_segment_loss_guard(
        pnl,
        driver_segment="cash",
        beneficiary_segment="options",
        loss_threshold=1_000.0,
        profit_threshold=2_000.0,
    )

    assert result.flagged
    assert result.driver_pnl == -1_100.0
    assert result.beneficiary_pnl == 2_500.0


def test_cross_segment_loss_guard_does_not_flag_ordinary_losses():
    pnl = pd.DataFrame(
        [
            {"segment": "futures", "pnl": -500.0},
            {"segment": "options", "pnl": 800.0},
        ]
    )

    result = cross_segment_loss_guard(
        pnl,
        driver_segment="futures",
        beneficiary_segment="options",
        loss_threshold=1_000.0,
        profit_threshold=2_000.0,
    )

    assert not result.flagged
