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
    assert list(first.test_index) == [0, 1]
    assert list(first.train_index) == [4, 5]

    second = splits[1]
    assert list(second.test_index) == [2, 3]
    assert list(second.train_index) == [0]

    third = splits[2]
    assert list(third.test_index) == [4, 5]
    assert list(third.train_index) == [0, 1, 2]


def test_purged_walk_forward_splits_preserve_original_indices():
    labels = pd.DataFrame(
        {
            "ts": [200, 0, 100],
            "label_end_ts": [250, 50, 150],
        },
        index=[20, 0, 10],
    )

    splits = purged_walk_forward_splits(labels, n_splits=1)

    assert list(splits[0].test_index) == [0, 10, 20]
