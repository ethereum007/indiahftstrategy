from __future__ import annotations

import pandas as pd


def running_settlement_average(
    index_ticks: pd.DataFrame,
    *,
    window_start_ns: int,
    window_end_ns: int,
    price_col: str | None = None,
) -> pd.DataFrame:
    """Compute the running average inside an expiry settlement window.

    If `price_col` is omitted, the function uses mid from bid/ask columns.
    The average is an observation average over supplied ticks; callers should
    feed the same sampling convention they intend to test.
    """

    if window_end_ns <= window_start_ns:
        raise ValueError("window_end_ns must be greater than window_start_ns")
    frame = index_ticks.sort_values("ts").copy()
    if price_col is None:
        _require(frame, ["ts", "bid", "ask"], "index_ticks")
        frame["settlement_price"] = 0.5 * (frame["bid"] + frame["ask"])
    else:
        _require(frame, ["ts", price_col], "index_ticks")
        frame["settlement_price"] = frame[price_col]

    frame = frame.loc[
        (frame["ts"] >= window_start_ns) & (frame["ts"] <= window_end_ns)
    ].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=["ts", "settlement_price", "running_average", "known_fraction"]
        )
    frame["running_average"] = frame["settlement_price"].expanding().mean()
    frame["known_fraction"] = (frame["ts"] - window_start_ns) / (
        window_end_ns - window_start_ns
    )
    frame["known_fraction"] = frame["known_fraction"].clip(0.0, 1.0)
    return frame[["ts", "settlement_price", "running_average", "known_fraction"]].reset_index(drop=True)


def projected_settlement(
    *,
    running_average: float,
    known_fraction: float,
    current_index: float,
) -> float:
    if not 0 <= known_fraction <= 1:
        raise ValueError("known_fraction must be between 0 and 1")
    return known_fraction * running_average + (1 - known_fraction) * current_index


def expiring_option_intrinsic(
    *,
    option_type: str,
    strike: float,
    projected_settlement_value: float,
) -> float:
    option = option_type.upper()
    if option == "C":
        return max(projected_settlement_value - strike, 0.0)
    if option == "P":
        return max(strike - projected_settlement_value, 0.0)
    raise ValueError("option_type must be 'C' or 'P'")


def settlement_convergence_value(
    *,
    option_type: str,
    strike: float,
    running_average: float,
    known_fraction: float,
    current_index: float,
) -> float:
    projected = projected_settlement(
        running_average=running_average,
        known_fraction=known_fraction,
        current_index=current_index,
    )
    return expiring_option_intrinsic(
        option_type=option_type,
        strike=strike,
        projected_settlement_value=projected,
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
