from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.loaders import trading_session_mask
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES


TICK_REQUIRED = ["ts", "bid", "ask", "bid_qty", "ask_qty"]
CHAIN_REQUIRED = [
    "ts",
    "expiry",
    "strike",
    "call_bid",
    "call_ask",
    "call_bid_qty",
    "call_ask_qty",
    "put_bid",
    "put_ask",
    "put_bid_qty",
    "put_ask_qty",
]


@dataclass(frozen=True)
class DiagnosticResult:
    summary: pd.DataFrame
    issues: pd.DataFrame
    output_dir: Path | None = None


def tick_diagnostics(
    ticks: pd.DataFrame,
    *,
    tick_size: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> DiagnosticResult:
    _require(ticks, TICK_REQUIRED, "ticks")
    frame = ticks.copy()
    frame["spread"] = frame["ask"] - frame["bid"]
    frame["mid"] = 0.5 * (frame["bid"] + frame["ask"])
    frame["depth"] = frame["bid_qty"] + frame["ask_qty"]
    if tick_size:
        frame["spread_ticks"] = frame["spread"] / tick_size
    else:
        frame["spread_ticks"] = np.nan
    gaps = frame["ts"].sort_values().diff().dropna()
    summary = pd.DataFrame(
        [
            {
                "rows": int(len(frame)),
                "start_ts": int(frame["ts"].min()) if len(frame) else np.nan,
                "end_ts": int(frame["ts"].max()) if len(frame) else np.nan,
                "nonmonotonic_rows": int((ticks["ts"].diff().fillna(0) < 0).sum()),
                "crossed_quote_rows": int((frame["ask"] < frame["bid"]).sum()),
                "nonpositive_quote_rows": int(((frame["bid"] <= 0) | (frame["ask"] <= 0)).sum()),
                "nonpositive_depth_rows": int(((frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0)).sum()),
                "out_of_session_rows": int((~trading_session_mask(frame["ts"], market=market)).sum()) if len(frame) else 0,
                "median_gap_ns": float(gaps.median()) if len(gaps) else 0.0,
                "p99_gap_ns": float(gaps.quantile(0.99)) if len(gaps) else 0.0,
                "median_spread": float(frame["spread"].median()) if len(frame) else 0.0,
                "median_spread_ticks": float(frame["spread_ticks"].median()) if tick_size and len(frame) else np.nan,
                "median_depth": float(frame["depth"].median()) if len(frame) else 0.0,
            }
        ]
    )
    return DiagnosticResult(summary=summary, issues=_tick_issues(frame, market=market))


def chain_diagnostics(
    chain: pd.DataFrame,
    *,
    tick_size: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> DiagnosticResult:
    _require(chain, CHAIN_REQUIRED, "chain")
    frame = chain.copy()
    frame["call_spread"] = frame["call_ask"] - frame["call_bid"]
    frame["put_spread"] = frame["put_ask"] - frame["put_bid"]
    if tick_size:
        frame["call_spread_ticks"] = frame["call_spread"] / tick_size
        frame["put_spread_ticks"] = frame["put_spread"] / tick_size
    else:
        frame["call_spread_ticks"] = np.nan
        frame["put_spread_ticks"] = np.nan
    by_expiry = (
        frame.groupby("expiry", dropna=False)
        .agg(
            rows=("strike", "size"),
            strikes=("strike", "nunique"),
            min_strike=("strike", "min"),
            max_strike=("strike", "max"),
            median_call_spread=("call_spread", "median"),
            median_put_spread=("put_spread", "median"),
            median_call_spread_ticks=("call_spread_ticks", "median"),
            median_put_spread_ticks=("put_spread_ticks", "median"),
        )
        .reset_index()
    )
    overall = pd.DataFrame(
        [
            {
                "rows": int(len(frame)),
                "expiries": int(frame["expiry"].nunique()),
                "strikes": int(frame["strike"].nunique()),
                "start_ts": int(frame["ts"].min()) if len(frame) else np.nan,
                "end_ts": int(frame["ts"].max()) if len(frame) else np.nan,
                "crossed_quote_rows": int(((frame["call_ask"] < frame["call_bid"]) | (frame["put_ask"] < frame["put_bid"])).sum()),
                "nonpositive_quote_rows": int(
                    (
                        (frame["call_bid"] <= 0)
                        | (frame["call_ask"] <= 0)
                        | (frame["put_bid"] <= 0)
                        | (frame["put_ask"] <= 0)
                    ).sum()
                ),
                "nonpositive_depth_rows": int(
                    (
                        (frame["call_bid_qty"] <= 0)
                        | (frame["call_ask_qty"] <= 0)
                        | (frame["put_bid_qty"] <= 0)
                        | (frame["put_ask_qty"] <= 0)
                    ).sum()
                ),
                "out_of_session_rows": int((~trading_session_mask(frame["ts"], market=market)).sum()) if len(frame) else 0,
            }
        ]
    )
    summary = pd.concat([overall.assign(scope="overall"), by_expiry.assign(scope="expiry")], ignore_index=True, sort=False)
    return DiagnosticResult(summary=summary, issues=_chain_issues(frame, market=market))


def write_diagnostics(result: DiagnosticResult, output_dir: str | Path) -> DiagnosticResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.summary.to_csv(out / "diagnostic_summary.csv", index=False)
    result.issues.to_csv(out / "diagnostic_issues.csv", index=False)
    return DiagnosticResult(result.summary, result.issues, out)


def _tick_issues(frame: pd.DataFrame, *, market: str) -> pd.DataFrame:
    rows = []
    checks = {
        "nonmonotonic_ts": frame["ts"].diff().fillna(0) < 0,
        "crossed_quote": frame["ask"] < frame["bid"],
        "nonpositive_quote": (frame["bid"] <= 0) | (frame["ask"] <= 0),
        "nonpositive_depth": (frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0),
        "out_of_session": ~trading_session_mask(frame["ts"], market=market),
    }
    for issue, mask in checks.items():
        for idx in frame.index[mask]:
            rows.append({"row_index": int(idx), "ts": int(frame.loc[idx, "ts"]), "issue": issue})
    return pd.DataFrame(rows, columns=["row_index", "ts", "issue"])


def _chain_issues(frame: pd.DataFrame, *, market: str) -> pd.DataFrame:
    rows = []
    checks = {
        "crossed_quote": (frame["call_ask"] < frame["call_bid"]) | (frame["put_ask"] < frame["put_bid"]),
        "nonpositive_quote": (frame["call_bid"] <= 0)
        | (frame["call_ask"] <= 0)
        | (frame["put_bid"] <= 0)
        | (frame["put_ask"] <= 0),
        "nonpositive_depth": (frame["call_bid_qty"] <= 0)
        | (frame["call_ask_qty"] <= 0)
        | (frame["put_bid_qty"] <= 0)
        | (frame["put_ask_qty"] <= 0),
        "out_of_session": ~trading_session_mask(frame["ts"], market=market),
    }
    for issue, mask in checks.items():
        for idx in frame.index[mask]:
            rows.append(
                {
                    "row_index": int(idx),
                    "ts": int(frame.loc[idx, "ts"]),
                    "expiry": frame.loc[idx, "expiry"],
                    "strike": float(frame.loc[idx, "strike"]),
                    "issue": issue,
                }
            )
    return pd.DataFrame(rows, columns=["row_index", "ts", "expiry", "strike", "issue"])


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
