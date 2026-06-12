from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


BOOK_REQUIRED = ["ts", "bid", "ask", "bid_qty", "ask_qty"]


def l1_features(book: pd.DataFrame, *, tick_size: float) -> pd.DataFrame:
    _require(book, BOOK_REQUIRED, "book")
    out = book.sort_values("ts").copy().reset_index(drop=True)
    out["mid"] = 0.5 * (out["bid"] + out["ask"])
    out["spread"] = out["ask"] - out["bid"]
    out["spread_ticks"] = out["spread"] / tick_size
    depth = out["bid_qty"] + out["ask_qty"]
    out["obi_l1"] = np.where(depth > 0, (out["bid_qty"] - out["ask_qty"]) / depth, 0.0)
    out["microprice"] = np.where(
        depth > 0,
        (out["bid"] * out["ask_qty"] + out["ask"] * out["bid_qty"]) / depth,
        out["mid"],
    )
    out["mid_change"] = out["mid"].diff().fillna(0.0)
    out["microprice_change"] = out["microprice"].diff().fillna(0.0)
    out["bid_qty_change"] = out["bid_qty"].diff().fillna(0)
    out["ask_qty_change"] = out["ask_qty"].diff().fillna(0)
    return out


def forward_mid_labels(
    book: pd.DataFrame,
    *,
    horizons_ns: Iterable[int],
) -> pd.DataFrame:
    features = l1_features(book, tick_size=1.0)[["ts", "mid"]]
    rows = []
    for horizon_ns in horizons_ns:
        target = features.copy()
        target["target_ts"] = target["ts"] + int(horizon_ns)
        joined = pd.merge_asof(
            target.sort_values("target_ts"),
            features.rename(columns={"ts": "future_ts", "mid": "future_mid"}).sort_values("future_ts"),
            left_on="target_ts",
            right_on="future_ts",
            direction="forward",
        )
        joined["horizon_ns"] = int(horizon_ns)
        joined["forward_mid_change"] = joined["future_mid"] - joined["mid"]
        rows.append(joined[["ts", "horizon_ns", "future_ts", "mid", "future_mid", "forward_mid_change"]])
    return pd.concat(rows, ignore_index=True, sort=False).sort_values(["ts", "horizon_ns"]).reset_index(drop=True)


def triple_barrier_labels(
    book: pd.DataFrame,
    *,
    tick_size: float,
    profit_ticks: float,
    stop_ticks: float,
    timeout_ns: int,
) -> pd.DataFrame:
    state = l1_features(book, tick_size=tick_size)[["ts", "mid"]]
    rows = []
    profit = profit_ticks * tick_size
    stop = stop_ticks * tick_size
    for row in state.itertuples(index=False):
        window = state.loc[(state["ts"] > row.ts) & (state["ts"] <= row.ts + timeout_ns)]
        label = 0
        hit_ts = np.nan
        hit_mid = np.nan
        for future in window.itertuples(index=False):
            move = future.mid - row.mid
            if move >= profit:
                label = 1
                hit_ts = future.ts
                hit_mid = future.mid
                break
            if move <= -stop:
                label = -1
                hit_ts = future.ts
                hit_mid = future.mid
                break
        rows.append(
            {
                "ts": int(row.ts),
                "entry_mid": float(row.mid),
                "label": int(label),
                "hit_ts": hit_ts,
                "hit_mid": hit_mid,
                "timeout_ts": int(row.ts + timeout_ns),
            }
        )
    return pd.DataFrame(rows)


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
