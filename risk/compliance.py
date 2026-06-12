from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OTRCheck:
    orders_sent: int
    fills: int
    ratio: float
    limit: float
    breached: bool


@dataclass(frozen=True)
class CrossSegmentGuardResult:
    flagged: bool
    driver_segment: str
    beneficiary_segment: str
    driver_pnl: float
    beneficiary_pnl: float
    reason: str


def check_order_to_trade_ratio(
    *,
    orders_sent: int,
    fills: int,
    limit: float,
) -> OTRCheck:
    if orders_sent < 0 or fills < 0:
        raise ValueError("orders_sent and fills must be non-negative")
    if limit <= 0:
        raise ValueError("limit must be positive")
    ratio = orders_sent / max(fills, 1)
    return OTRCheck(
        orders_sent=orders_sent,
        fills=fills,
        ratio=ratio,
        limit=limit,
        breached=ratio > limit,
    )


def cross_segment_loss_guard(
    segment_pnl: pd.DataFrame,
    *,
    driver_segment: str,
    beneficiary_segment: str,
    loss_threshold: float,
    profit_threshold: float,
    segment_col: str = "segment",
    pnl_col: str = "pnl",
) -> CrossSegmentGuardResult:
    """Flag persistent loss in one segment paired with gains in another."""

    for col in (segment_col, pnl_col):
        if col not in segment_pnl.columns:
            raise ValueError(f"segment_pnl missing required column {col}")
    driver_pnl = float(segment_pnl.loc[segment_pnl[segment_col] == driver_segment, pnl_col].sum())
    beneficiary_pnl = float(
        segment_pnl.loc[segment_pnl[segment_col] == beneficiary_segment, pnl_col].sum()
    )
    flagged = driver_pnl <= -abs(loss_threshold) and beneficiary_pnl >= abs(profit_threshold)
    reason = (
        "driver segment loses while beneficiary segment profits"
        if flagged
        else "no cross-segment loss/profit red flag"
    )
    return CrossSegmentGuardResult(
        flagged=flagged,
        driver_segment=driver_segment,
        beneficiary_segment=beneficiary_segment,
        driver_pnl=driver_pnl,
        beneficiary_pnl=beneficiary_pnl,
        reason=reason,
    )
