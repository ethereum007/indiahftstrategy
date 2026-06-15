from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
)


def test_vendor_market_data_batch_source_active_accepts_provenance_signals():
    assert vendor_market_data_batch_source_active({"provided": "ready"})
    assert vendor_market_data_batch_source_active({"dataset_count": "2"})
    assert vendor_market_data_batch_source_active({"adapter": "arrow-money"})
    assert vendor_market_data_batch_source_active({"market": "india.nse.index.derivatives"})


def test_vendor_market_data_batch_source_active_rejects_empty_proof():
    assert not vendor_market_data_batch_source_active({})
    assert not vendor_market_data_batch_source_active(
        {
            "provided": False,
            "dataset_count": 0,
            "adapter": "",
            "market": "",
        }
    )
    assert not vendor_market_data_batch_source_active(None)


def test_select_vendor_market_data_batch_source_prefers_first_active_candidate():
    config = {
        "older": {"provided": True, "adapter": "irage"},
        "preferred": {"provided": True, "adapter": "arrow_money"},
    }

    vendor, source = select_vendor_market_data_batch_source(
        config,
        ("preferred", "older"),
        default_source="older",
    )

    assert source == "preferred"
    assert vendor["adapter"] == "arrow_money"


def test_select_vendor_market_data_batch_source_skips_inactive_candidate():
    config = {
        "preferred": {"provided": False, "dataset_count": 0},
        "older": {"dataset_count": 2, "adapter": "arrow_money"},
    }

    vendor, source = select_vendor_market_data_batch_source(
        config,
        ("preferred", "older"),
        default_source="older",
    )

    assert source == "older"
    assert vendor["adapter"] == "arrow_money"


def test_select_vendor_market_data_batch_source_returns_default_when_no_active_proof():
    vendor, source = select_vendor_market_data_batch_source(
        {"ignored": ["not", "a", "proof"]},
        ("preferred", "older"),
        default_source="older",
    )

    assert vendor == {}
    assert source == "older"
