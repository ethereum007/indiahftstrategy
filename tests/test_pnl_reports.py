import pandas as pd

from reports.pnl import pnl_decomposition, pnl_totals


def fills():
    return pd.DataFrame(
        [
            {
                "instrument_id": "OPT",
                "oid": 1,
                "side": 1,
                "qty": 75,
                "price": 100.0,
                "cost": 1.0,
                "maker": False,
            },
            {
                "instrument_id": "OPT",
                "oid": 2,
                "side": -1,
                "qty": 75,
                "price": 101.0,
                "cost": 2.0,
                "maker": True,
            },
            {
                "instrument_id": "OPT",
                "oid": 3,
                "side": -1,
                "qty": 75,
                "price": 99.0,
                "cost": 3.0,
                "maker": False,
            },
        ]
    )


def test_pnl_decomposition_labels_strategy_and_terminal_flatten():
    report = pnl_decomposition(
        fills(),
        strategy_order_ids=[1, 2],
        group_cols=["instrument_id"],
    )

    strategy = report.loc[report["source"] == "strategy"].iloc[0]
    terminal = report.loc[report["source"] == "terminal_flatten"].iloc[0]

    assert strategy["gross_cash_flow"] == 75.0
    assert strategy["costs"] == 3.0
    assert strategy["net_cash_flow"] == 72.0
    assert strategy["maker_share"] == 0.5
    assert terminal["gross_cash_flow"] == 7425.0
    assert terminal["net_cash_flow"] == 7422.0


def test_pnl_totals_without_strategy_ids_groups_all_fills():
    report = pnl_totals(fills())

    assert len(report) == 1
    row = report.iloc[0]
    assert row["source"] == "all"
    assert row["fills"] == 3
    assert row["costs"] == 6.0
    assert row["net_cash_flow"] == 7494.0
