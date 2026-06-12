import pandas as pd

from reports.regime import attach_regime, equity_change_by_regime, fill_summary_by_regime


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_attach_regime_uses_structural_breaks():
    frame = pd.DataFrame(
        {
            "ts": [
                ns_ist("2024-11-19 10:00:00"),
                ns_ist("2025-09-01 10:00:00"),
                ns_ist("2026-04-01 10:00:00"),
            ]
        }
    )

    tagged = attach_regime(frame, ts_col="ts")

    assert list(tagged["regime"]) == [
        "pre_weekly_consolidation",
        "expiry_swap",
        "post_stt_hike",
    ]


def test_fill_summary_by_regime_groups_costs_turnover_and_maker_share():
    fills = pd.DataFrame(
        [
            {
                "ts_ns": ns_ist("2026-03-31 10:00:00"),
                "qty": 75,
                "price": 100.0,
                "cost": 1.0,
                "maker": True,
            },
            {
                "ts_ns": ns_ist("2026-04-01 10:00:00"),
                "qty": 150,
                "price": 101.0,
                "cost": 2.0,
                "maker": False,
            },
        ]
    )

    summary = fill_summary_by_regime(fills)

    assert set(summary["regime"]) == {"expiry_swap", "post_stt_hike"}
    post = summary.loc[summary["regime"] == "post_stt_hike"].iloc[0]
    assert post["turnover"] == 15150.0
    assert post["costs"] == 2.0
    assert post["maker_share"] == 0.0


def test_equity_change_by_regime_uses_first_and_last_equity_per_regime():
    equity = pd.DataFrame(
        [
            {"ts": ns_ist("2026-03-31 10:00:00"), "equity": 10.0},
            {"ts": ns_ist("2026-03-31 10:00:01"), "equity": 15.0},
            {"ts": ns_ist("2026-04-01 10:00:00"), "equity": 20.0},
            {"ts": ns_ist("2026-04-01 10:00:01"), "equity": 5.0},
        ]
    )

    summary = equity_change_by_regime(equity)

    assert summary.loc[summary["regime"] == "expiry_swap", "equity_change"].iloc[0] == 5.0
    assert summary.loc[summary["regime"] == "post_stt_hike", "equity_change"].iloc[0] == -15.0
