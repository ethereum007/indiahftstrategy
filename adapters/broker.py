from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data.chains import NormalizedOptionChain, load_option_chain_csv
from data.loaders import NormalizedTicks, load_tick_csv
from research.calibration import calibration_summary, compare_simulated_to_live


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    tick_column_map: dict[str, str]
    chain_column_map: dict[str, str]
    simulated_order_column_map: dict[str, str]
    live_fill_column_map: dict[str, str]
    timestamp_unit: str = "ns"
    timestamp_tz: str | None = None


NORMALIZED_TICK_COLUMNS = {
    "ts": "ts",
    "bid": "bid",
    "ask": "ask",
    "bid_qty": "bid_qty",
    "ask_qty": "ask_qty",
    "last": "last",
    "last_qty": "last_qty",
}

NORMALIZED_CHAIN_COLUMNS = {
    "ts": "ts",
    "expiry": "expiry",
    "strike": "strike",
    "call_bid": "call_bid",
    "call_ask": "call_ask",
    "call_bid_qty": "call_bid_qty",
    "call_ask_qty": "call_ask_qty",
    "put_bid": "put_bid",
    "put_ask": "put_ask",
    "put_bid_qty": "put_bid_qty",
    "put_ask_qty": "put_ask_qty",
}

NORMALIZED_ORDER_COLUMNS = {
    "client_order_id": "client_order_id",
    "instrument_id": "instrument_id",
    "ts_sent_ns": "ts_sent_ns",
    "side": "side",
    "qty": "qty",
    "price": "price",
}

NORMALIZED_FILL_COLUMNS = {
    "client_order_id": "client_order_id",
    "instrument_id": "instrument_id",
    "ts_fill_ns": "ts_fill_ns",
    "side": "side",
    "qty": "qty",
    "price": "price",
}


ADAPTERS: dict[str, AdapterSpec] = {
    "normalized": AdapterSpec(
        name="normalized",
        tick_column_map=NORMALIZED_TICK_COLUMNS,
        chain_column_map=NORMALIZED_CHAIN_COLUMNS,
        simulated_order_column_map=NORMALIZED_ORDER_COLUMNS,
        live_fill_column_map=NORMALIZED_FILL_COLUMNS,
    ),
    "arrow_money": AdapterSpec(
        name="arrow_money",
        tick_column_map=NORMALIZED_TICK_COLUMNS,
        chain_column_map=NORMALIZED_CHAIN_COLUMNS,
        simulated_order_column_map=NORMALIZED_ORDER_COLUMNS,
        live_fill_column_map=NORMALIZED_FILL_COLUMNS,
    ),
    "irage": AdapterSpec(
        name="irage",
        tick_column_map=NORMALIZED_TICK_COLUMNS,
        chain_column_map=NORMALIZED_CHAIN_COLUMNS,
        simulated_order_column_map=NORMALIZED_ORDER_COLUMNS,
        live_fill_column_map=NORMALIZED_FILL_COLUMNS,
    ),
}


def get_adapter(name: str) -> AdapterSpec:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        raise ValueError(f"unknown adapter {name!r}; known adapters: {sorted(ADAPTERS)}") from exc


def load_adapter_ticks(
    path: str | Path,
    *,
    adapter: str = "normalized",
    filter_session: bool = True,
) -> NormalizedTicks:
    spec = get_adapter(adapter)
    return load_tick_csv(
        path,
        column_map=spec.tick_column_map,
        timestamp_unit=spec.timestamp_unit,
        timestamp_tz=spec.timestamp_tz,
        filter_session=filter_session,
    )


def load_adapter_chain(
    path: str | Path,
    *,
    adapter: str = "normalized",
    filter_session: bool = True,
) -> NormalizedOptionChain:
    spec = get_adapter(adapter)
    return load_option_chain_csv(
        path,
        column_map=spec.chain_column_map,
        timestamp_unit=spec.timestamp_unit,
        timestamp_tz=spec.timestamp_tz,
        filter_session=filter_session,
    )


def normalize_orders(path: str | Path, *, adapter: str = "normalized") -> pd.DataFrame:
    spec = get_adapter(adapter)
    return _rename_required(pd.read_csv(path), spec.simulated_order_column_map)


def normalize_live_fills(path: str | Path, *, adapter: str = "normalized") -> pd.DataFrame:
    spec = get_adapter(adapter)
    return _rename_required(pd.read_csv(path), spec.live_fill_column_map)


def run_calibration_report(
    *,
    simulated_orders_path: str | Path,
    live_fills_path: str | Path,
    output_dir: str | Path | None = None,
    adapter: str = "normalized",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    simulated = normalize_orders(simulated_orders_path, adapter=adapter)
    live = normalize_live_fills(live_fills_path, adapter=adapter)
    comparison = compare_simulated_to_live(simulated, live)
    summary = calibration_summary(comparison)
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(out / "calibration_comparison.csv", index=False)
        summary.to_csv(out / "calibration_summary.csv", index=False)
    return comparison, summary


def _rename_required(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    missing = [src for src in column_map.values() if src not in df.columns]
    if missing:
        raise ValueError(f"source columns missing from adapter data: {missing}")
    return df.rename(columns={src: dst for dst, src in column_map.items()})
