import pandas as pd

from research.validation import purged_walk_forward_splits


def test_purged_walk_forward_splits_remove_overlap_and_embargo():
    labels = pd.DataFrame(
        {
            "ts": [0, 100, 200, 300, 400, 500],
            "label_end_ts": [150, 250, 350, 450, 550, 650],
        }
    )

    splits = purged_walk_forward_splits(labels, n_splits=3, embargo_ns=50)

    first = splits[0]
    assert list(first.test_index) == [3]
    assert list(first.train_index) == [0, 1]
    assert list(first.purged_index) == [2]
    assert list(first.embargoed_index) == []

    second = splits[1]
    assert list(second.test_index) == [4]
    assert list(second.train_index) == [0, 1, 2]
    assert list(second.purged_index) == [3]

    third = splits[2]
    assert list(third.test_index) == [5]
    assert list(third.train_index) == [0, 1, 2, 3]
    assert list(third.purged_index) == [4]


def test_purged_walk_forward_splits_never_train_on_future_rows():
    labels = pd.DataFrame(
        {
            "ts": [0, 100, 200, 300, 400, 500],
            "label_end_ts": [20, 120, 220, 320, 420, 520],
        }
    )

    splits = purged_walk_forward_splits(labels, n_splits=2, test_size=2)

    assert list(splits[0].train_index) == [0, 1]
    assert list(splits[0].test_index) == [2, 3]
    assert list(splits[1].train_index) == [0, 1, 2, 3]
    assert list(splits[1].test_index) == [4, 5]


def test_purged_walk_forward_splits_applies_duration_gap_before_test():
    labels = pd.DataFrame(
        {
            "ts": [0, 100, 200, 300],
            "label_end_ts": [50, 190, 290, 350],
        }
    )

    split = purged_walk_forward_splits(labels, n_splits=1, embargo_ns=75)[0]

    assert list(split.test_index) == [2, 3]
    assert list(split.train_index) == [0]
    assert list(split.embargoed_index) == [1]
    assert list(split.purged_index) == []


def test_purged_walk_forward_splits_preserve_original_indices():
    labels = pd.DataFrame(
        {
            "ts": [200, 0, 100],
            "label_end_ts": [250, 50, 150],
        },
        index=[20, 0, 10],
    )

    splits = purged_walk_forward_splits(labels, n_splits=1)

    assert list(splits[0].train_index) == [0, 10]
    assert list(splits[0].test_index) == [20]


def test_purged_walk_forward_splits_rejects_invalid_temporal_contracts():
    labels = pd.DataFrame(
        {
            "ts": [0, 100, 200],
            "label_end_ts": [50, 150, 250],
        }
    )

    for kwargs, message in (
        ({"n_splits": 3}, "initial training row"),
        ({"n_splits": 1, "embargo_ns": -1}, "non-negative integer"),
        ({"n_splits": 1, "test_size": 3}, "initial training window"),
    ):
        try:
            purged_walk_forward_splits(labels, **kwargs)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"expected invalid split contract for {kwargs}")

    invalid_interval = labels.copy()
    invalid_interval.loc[1, "label_end_ts"] = 99
    try:
        purged_walk_forward_splits(invalid_interval, n_splits=1)
    except ValueError as exc:
        assert "greater than or equal" in str(exc)
    else:
        raise AssertionError("expected invalid label interval to fail")

    overflow = labels.astype("object")
    overflow.loc[2, "label_end_ts"] = 2**63
    try:
        purged_walk_forward_splits(overflow, n_splits=1)
    except ValueError as exc:
        assert "signed 64-bit" in str(exc)
    else:
        raise AssertionError("expected timestamp overflow to fail")
