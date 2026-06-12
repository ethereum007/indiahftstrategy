import pandas as pd

from research.features import forward_mid_labels, l1_features, triple_barrier_labels


def book():
    return pd.DataFrame(
        [
            {"ts": 0, "bid": 99.0, "ask": 101.0, "bid_qty": 300, "ask_qty": 100},
            {"ts": 100, "bid": 100.0, "ask": 102.0, "bid_qty": 100, "ask_qty": 300},
            {"ts": 200, "bid": 102.0, "ask": 104.0, "bid_qty": 200, "ask_qty": 200},
            {"ts": 300, "bid": 98.0, "ask": 100.0, "bid_qty": 200, "ask_qty": 200},
        ]
    )


def test_l1_features_compute_imbalance_microprice_and_changes():
    features = l1_features(book(), tick_size=0.05)

    assert features.iloc[0]["mid"] == 100.0
    assert features.iloc[0]["spread_ticks"] == 40.0
    assert features.iloc[0]["obi_l1"] == 0.5
    assert features.iloc[0]["microprice"] == 100.5
    assert features.iloc[1]["mid_change"] == 1.0
    assert features.iloc[1]["bid_qty_change"] == -200


def test_forward_mid_labels_use_explicit_future_horizon():
    labels = forward_mid_labels(book(), horizons_ns=[100, 200])

    row = labels.loc[(labels["ts"] == 0) & (labels["horizon_ns"] == 100)].iloc[0]
    assert row["future_ts"] == 100
    assert row["forward_mid_change"] == 1.0

    row = labels.loc[(labels["ts"] == 0) & (labels["horizon_ns"] == 200)].iloc[0]
    assert row["future_ts"] == 200
    assert row["forward_mid_change"] == 3.0


def test_triple_barrier_labels_first_barrier_hit_wins():
    labels = triple_barrier_labels(
        book(),
        tick_size=1.0,
        profit_ticks=2.0,
        stop_ticks=1.0,
        timeout_ns=250,
    )

    assert labels.loc[labels["ts"] == 0, "label"].iloc[0] == 1
    assert labels.loc[labels["ts"] == 100, "label"].iloc[0] == 1
    assert labels.loc[labels["ts"] == 200, "label"].iloc[0] == -1
    assert labels.loc[labels["ts"] == 300, "label"].iloc[0] == 0
