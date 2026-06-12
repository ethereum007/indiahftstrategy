import pandas as pd

from data.chains import normalize_option_chain
from scanners.run_parity_box import run_scan


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def chain_rows():
    return pd.DataFrame(
        [
            {
                "time": ns_ist("2026-06-10 09:15:00"),
                "expiry_date": "2026-06-30",
                "k": 1000.0,
                "cb": 54.0,
                "ca": 55.0,
                "cbq": 300,
                "caq": 300,
                "pb": 60.0,
                "pa": 61.0,
                "pbq": 300,
                "paq": 300,
            },
            {
                "time": ns_ist("2026-06-10 15:30:01"),
                "expiry_date": "2026-06-30",
                "k": 1010.0,
                "cb": 44.0,
                "ca": 45.0,
                "cbq": 300,
                "caq": 300,
                "pb": 60.0,
                "pa": 61.0,
                "pbq": 300,
                "paq": 300,
            },
        ]
    )


def chain_map():
    return {
        "ts": "time",
        "expiry": "expiry_date",
        "strike": "k",
        "call_bid": "cb",
        "call_ask": "ca",
        "call_bid_qty": "cbq",
        "call_ask_qty": "caq",
        "put_bid": "pb",
        "put_ask": "pa",
        "put_bid_qty": "pbq",
        "put_ask_qty": "paq",
    }


def test_option_chain_normalizer_maps_vendor_columns_and_filters_session():
    normalized = normalize_option_chain(chain_rows(), column_map=chain_map())

    assert len(normalized.data) == 1
    assert normalized.data.iloc[0]["strike"] == 1000.0
    assert normalized.data.iloc[0]["regime"] == "post_stt_hike"
    assert normalized.quarantine.total_rows == 2
    assert normalized.quarantine.dropped_out_of_session_rows == 1


def test_parity_box_runner_writes_outputs(tmp_path):
    chain = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 1200,
                "call_ask_qty": 1200,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 1200,
                "put_ask_qty": 1200,
            },
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "expiry": "2026-06-30",
                "strike": 1010.0,
                "call_bid": 45.0,
                "call_ask": 46.0,
                "call_bid_qty": 1200,
                "call_ask_qty": 1200,
                "put_bid": 45.0,
                "put_ask": 46.0,
                "put_bid_qty": 1200,
                "put_ask_qty": 1200,
            },
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 1008.0,
                "ask": 1009.0,
                "bid_qty": 1200,
                "ask_qty": 1200,
            }
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "reports"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    result = run_scan(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        asof_latency_ns=0,
        depth_fraction=1.0,
    )

    assert not result.parity.empty
    assert (out_dir / "parity_opportunities.csv").exists()
    assert (out_dir / "box_opportunities.csv").exists()
    assert (out_dir / "opportunity_report.csv").exists()
    assert "post_stt_hike" in set(result.report["regime"])
