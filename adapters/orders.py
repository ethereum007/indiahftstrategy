from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.broker import get_adapter
from reports.manifest import write_experiment_manifest
from reports.quote_risk import (
    quote_risk_review_check,
    quote_risk_review_parameters,
    read_quote_risk_summary,
)
from reports.surface_quality import (
    read_surface_quality_summary,
    surface_quality_review_check,
    surface_quality_review_parameters,
)


@dataclass(frozen=True)
class OrderStagingLimits:
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    max_orders: int | None = None
    contract_multiplier: float = 1.0
    require_nonmarketable: bool = True
    allowed_sides: tuple[int, ...] = (-1, 1)
    default_order_type: str = "LIMIT"
    default_time_in_force: str = "DAY"


@dataclass(frozen=True)
class OrderStagingReport:
    accepted: pd.DataFrame
    rejected: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if not self.summary.empty and "all_passed" in self.summary.columns:
            return bool(self.summary.iloc[0]["all_passed"])
        return self.rejected.empty


ORDER_COLUMNS = [
    "client_order_id",
    "source",
    "source_row",
    "strategy",
    "instrument_id",
    "side",
    "side_text",
    "qty",
    "price",
    "order_type",
    "time_in_force",
    "ts_signal_ns",
    "notional",
    "market_bid",
    "market_ask",
    "marketable",
    "quote_edge",
    "theo",
    "expiry",
    "strike",
    "option_type",
    "market_spread_ticks",
    "forward",
    "futures_ts",
    "lifecycle_action",
    "lifecycle_action_id",
    "lifecycle_reason",
    "lifecycle_message_count",
    "quote_age_ns",
    "replaces_order_id",
]


def stage_surface_quote_orders(
    quotes: pd.DataFrame,
    *,
    limits: OrderStagingLimits | None = None,
) -> OrderStagingReport:
    return stage_orders(quotes, source="surface_quotes", limits=limits)


def stage_orders(
    orders: pd.DataFrame,
    *,
    source: str = "orders",
    limits: OrderStagingLimits | None = None,
) -> OrderStagingReport:
    limits = limits or OrderStagingLimits()
    _validate_limits(limits)
    frame = _normalize_order_candidates(orders, source=source, limits=limits)
    rejected_reasons = _rejection_reasons(frame, limits)
    accepted_count = 0
    for index, reasons in rejected_reasons.items():
        if reasons:
            continue
        if limits.max_orders is not None and accepted_count >= limits.max_orders:
            reasons.append("max_orders_exceeded")
        else:
            accepted_count += 1

    staged = frame.copy()
    staged["rejection_reason"] = [";".join(rejected_reasons[index]) for index in staged.index]
    accepted = staged.loc[staged["rejection_reason"] == "", ORDER_COLUMNS].reset_index(drop=True)
    rejected = staged.loc[staged["rejection_reason"] != "", [*ORDER_COLUMNS, "rejection_reason"]].reset_index(
        drop=True
    )
    summary = _summary(accepted, rejected, len(staged))
    return OrderStagingReport(accepted=accepted, rejected=rejected, summary=summary)


def write_staged_orders(
    orders_path: str | Path,
    *,
    output_dir: str | Path,
    source: str = "orders",
    limits: OrderStagingLimits | None = None,
    adapter: str = "normalized",
    quote_risk_review_dir: str | Path | None = None,
    require_quote_risk_review: bool = False,
    surface_quality_review_dir: str | Path | None = None,
    require_surface_quality: bool = False,
) -> OrderStagingReport:
    get_adapter(adapter)
    orders_file = Path(orders_path)
    if not orders_file.exists():
        raise FileNotFoundError(f"orders file not found: {orders_file}")
    limits = limits or OrderStagingLimits()
    report = stage_orders(pd.read_csv(orders_file), source=source, limits=limits)
    quote_risk_summary = read_quote_risk_summary(quote_risk_review_dir)
    quote_risk_check = quote_risk_review_check(
        quote_risk_summary,
        required=require_quote_risk_review,
        input_dir=quote_risk_review_dir,
    )
    if quote_risk_check is not None and not bool(quote_risk_check["passed"]):
        report = _block_staged_orders(report, str(quote_risk_check["reason"]))
    surface_quality_summary = read_surface_quality_summary(surface_quality_review_dir)
    surface_quality_check = surface_quality_review_check(
        surface_quality_summary,
        required=require_surface_quality,
        input_dir=surface_quality_review_dir,
    )
    if surface_quality_check is not None and not bool(surface_quality_check["passed"]):
        report = _block_staged_orders(report, str(surface_quality_check["reason"]))
    report = _attach_quote_risk_summary(
        report,
        quote_risk_check=quote_risk_check,
        required=require_quote_risk_review,
    )
    report = _attach_surface_quality_summary(
        report,
        surface_quality_check=surface_quality_check,
        required=require_surface_quality,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.accepted.to_csv(out / "staged_orders.csv", index=False)
    report.rejected.to_csv(out / "staged_order_rejections.csv", index=False)
    report.summary.to_csv(out / "staged_order_summary.csv", index=False)
    inputs: dict[str, Any] = {"orders": orders_file}
    if quote_risk_review_dir is not None:
        inputs["quote_risk_review"] = Path(quote_risk_review_dir)
    if surface_quality_review_dir is not None:
        inputs["surface_quality"] = Path(surface_quality_review_dir)
    write_experiment_manifest(
        out,
        run_type="order_staging",
        parameters={
            "adapter": adapter,
            "source": source,
            "limits": asdict(limits),
            "require_quote_risk_review": bool(require_quote_risk_review),
            "quote_risk_review": quote_risk_review_parameters(quote_risk_summary, quote_risk_review_dir),
            "require_surface_quality": bool(require_surface_quality),
            "surface_quality": surface_quality_review_parameters(
                surface_quality_summary,
                surface_quality_review_dir,
            ),
        },
        inputs=inputs,
    )
    return OrderStagingReport(report.accepted, report.rejected, report.summary, out)


def _normalize_order_candidates(
    orders: pd.DataFrame,
    *,
    source: str,
    limits: OrderStagingLimits,
) -> pd.DataFrame:
    source = _normalize_source(source)
    _require_columns(orders, ["instrument_id", "side", "qty", "price"])
    frame = orders.copy().reset_index(drop=True)
    frame["source"] = source
    frame["source_row"] = np.arange(len(frame), dtype=int)
    frame["strategy"] = frame["strategy"] if "strategy" in frame.columns else _default_strategy(source)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side)
    frame["side_text"] = frame["side"].map({1: "BUY", -1: "SELL"}).fillna("UNKNOWN")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["notional"] = frame["qty"] * frame["price"] * float(limits.contract_multiplier)
    frame["order_type"] = _column_or_default(frame, "order_type", limits.default_order_type)
    frame["time_in_force"] = _column_or_default(frame, "time_in_force", limits.default_time_in_force)
    frame["ts_signal_ns"] = _timestamp_column(frame)
    frame["market_bid"] = _numeric_optional(frame, "market_bid")
    frame["market_ask"] = _numeric_optional(frame, "market_ask")
    frame["marketable"] = _marketable_column(frame)
    if "marketable" not in orders.columns:
        frame["marketable"] = _derive_marketable(frame)
    frame["client_order_id"] = _client_order_ids(frame)

    for col in ORDER_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame[ORDER_COLUMNS]


def _rejection_reasons(frame: pd.DataFrame, limits: OrderStagingLimits) -> dict[int, list[str]]:
    reasons: dict[int, list[str]] = {int(index): [] for index in frame.index}
    for row in frame.itertuples():
        row_reasons = reasons[int(row.Index)]
        if int(row.side) not in limits.allowed_sides:
            row_reasons.append("invalid_side")
        if _missing_or_nonpositive(row.qty):
            row_reasons.append("nonpositive_qty")
        if _missing_or_nonpositive(row.price):
            row_reasons.append("nonpositive_price")
        if limits.max_order_qty is not None and not pd.isna(row.qty) and float(row.qty) > limits.max_order_qty:
            row_reasons.append("qty_limit")
        if limits.max_notional is not None and not pd.isna(row.notional) and float(row.notional) > limits.max_notional:
            row_reasons.append("notional_limit")
        if limits.require_nonmarketable and bool(row.marketable):
            row_reasons.append("marketable_order")
        if _outside_price_band(row, limits.price_band_pct):
            row_reasons.append("price_band")
    return reasons


def _summary(accepted: pd.DataFrame, rejected: pd.DataFrame, total_orders: int) -> pd.DataFrame:
    accepted_notional = float(pd.to_numeric(accepted["notional"], errors="coerce").sum()) if not accepted.empty else 0.0
    rejected_notional = float(pd.to_numeric(rejected["notional"], errors="coerce").sum()) if not rejected.empty else 0.0
    all_orders = pd.concat([accepted, rejected], ignore_index=True, sort=False)
    max_order_notional = (
        float(pd.to_numeric(all_orders["notional"], errors="coerce").max()) if not all_orders.empty else 0.0
    )
    buy_orders = int((accepted["side"] == 1).sum()) if not accepted.empty else 0
    sell_orders = int((accepted["side"] == -1).sum()) if not accepted.empty else 0
    return pd.DataFrame(
        [
            {
                "total_orders": int(total_orders),
                "accepted_orders": int(len(accepted)),
                "rejected_orders": int(len(rejected)),
                "acceptance_rate": len(accepted) / total_orders if total_orders else 1.0,
                "buy_orders": buy_orders,
                "sell_orders": sell_orders,
                "accepted_notional": accepted_notional,
                "rejected_notional": rejected_notional,
                "total_notional": accepted_notional + rejected_notional,
                "max_order_notional": max_order_notional,
                "all_passed": bool(rejected.empty),
            }
        ]
    )


def _block_staged_orders(report: OrderStagingReport, reason: str) -> OrderStagingReport:
    accepted = report.accepted.iloc[0:0].copy()
    rejected = report.rejected.copy()
    if not report.accepted.empty:
        blocked = report.accepted.copy()
        blocked["rejection_reason"] = reason
        rejected = pd.concat(
            [rejected, blocked[[*ORDER_COLUMNS, "rejection_reason"]]],
            ignore_index=True,
            sort=False,
        )
    total_orders = int(report.summary.iloc[0]["total_orders"]) if not report.summary.empty else len(rejected)
    return OrderStagingReport(
        accepted=accepted,
        rejected=rejected.reset_index(drop=True),
        summary=_summary(accepted, rejected, total_orders),
    )


def _attach_quote_risk_summary(
    report: OrderStagingReport,
    *,
    quote_risk_check: dict[str, Any] | None,
    required: bool,
) -> OrderStagingReport:
    summary = report.summary.copy()
    passed = True if quote_risk_check is None else bool(quote_risk_check["passed"])
    summary["quote_risk_review_required"] = bool(required)
    summary["quote_risk_review_provided"] = bool(quote_risk_check is not None and quote_risk_check["input_dir"])
    summary["quote_risk_review_passed"] = bool(passed)
    summary["quote_risk_review_reason"] = "" if quote_risk_check is None else str(quote_risk_check["reason"])
    summary["all_passed"] = summary["all_passed"].astype(bool) & bool(passed)
    return OrderStagingReport(
        accepted=report.accepted,
        rejected=report.rejected,
        summary=summary,
        output_dir=report.output_dir,
    )


def _attach_surface_quality_summary(
    report: OrderStagingReport,
    *,
    surface_quality_check: dict[str, Any] | None,
    required: bool,
) -> OrderStagingReport:
    summary = report.summary.copy()
    passed = True if surface_quality_check is None else bool(surface_quality_check["passed"])
    summary["surface_quality_required"] = bool(required)
    summary["surface_quality_provided"] = bool(surface_quality_check is not None and surface_quality_check["input_dir"])
    summary["surface_quality_passed"] = bool(passed)
    summary["surface_quality_reason"] = "" if surface_quality_check is None else str(surface_quality_check["reason"])
    summary["all_passed"] = summary["all_passed"].astype(bool) & bool(passed)
    return OrderStagingReport(
        accepted=report.accepted,
        rejected=report.rejected,
        summary=summary,
        output_dir=report.output_dir,
    )


def _validate_limits(limits: OrderStagingLimits) -> None:
    if limits.max_order_qty is not None and limits.max_order_qty <= 0:
        raise ValueError("max_order_qty must be positive")
    if limits.max_notional is not None and limits.max_notional <= 0:
        raise ValueError("max_notional must be positive")
    if limits.price_band_pct is not None and limits.price_band_pct < 0:
        raise ValueError("price_band_pct must be non-negative")
    if limits.max_orders is not None and limits.max_orders < 0:
        raise ValueError("max_orders must be non-negative")
    if limits.contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive")
    if not limits.allowed_sides:
        raise ValueError("allowed_sides must not be empty")


def _normalize_source(source: str) -> str:
    normalized = source.strip().lower().replace("-", "_")
    if normalized in {"order", "orders", "generic"}:
        return "orders"
    if normalized in {"surface_quote", "surface_quotes"}:
        return "surface_quotes"
    raise ValueError("source must be 'orders' or 'surface_quotes'")


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"orders missing required columns: {missing}")


def _default_strategy(source: str) -> str:
    return "surface_mm" if source == "surface_quotes" else "manual"


def _normalize_side(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0


def _column_or_default(frame: pd.DataFrame, column: str, default: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index)
    return frame[column].fillna(default).astype(str).str.upper()


def _timestamp_column(frame: pd.DataFrame) -> pd.Series:
    for col in ("ts_signal_ns", "ts", "ts_sent_ns"):
        if col in frame.columns:
            return pd.to_numeric(frame[col], errors="coerce")
    return pd.Series([np.nan] * len(frame), index=frame.index)


def _numeric_optional(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([np.nan] * len(frame), index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _marketable_column(frame: pd.DataFrame) -> pd.Series:
    if "marketable" not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index)
    return frame["marketable"].map(_to_bool)


def _derive_marketable(frame: pd.DataFrame) -> pd.Series:
    bid = pd.to_numeric(frame["market_bid"], errors="coerce")
    ask = pd.to_numeric(frame["market_ask"], errors="coerce")
    price = pd.to_numeric(frame["price"], errors="coerce")
    side = pd.to_numeric(frame["side"], errors="coerce")
    return ((side > 0) & ask.notna() & (price >= ask)) | ((side < 0) & bid.notna() & (price <= bid))


def _client_order_ids(frame: pd.DataFrame) -> pd.Series:
    if "client_order_id" in frame.columns:
        ids = frame["client_order_id"].fillna("").astype(str)
    else:
        ids = pd.Series([""] * len(frame), index=frame.index)
    generated = []
    for row in frame.itertuples():
        existing = ids.iloc[int(row.Index)].strip()
        if existing:
            generated.append(existing)
            continue
        payload = "|".join(
            str(value)
            for value in (
                row.source,
                row.source_row,
                row.instrument_id,
                row.side,
                row.qty,
                row.price,
                row.ts_signal_ns,
            )
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
        generated.append(f"STG-{int(row.source_row):06d}-{digest}")
    return pd.Series(generated, index=frame.index)


def _missing_or_nonpositive(value: object) -> bool:
    return pd.isna(value) or float(value) <= 0


def _outside_price_band(row: object, price_band_pct: float | None) -> bool:
    if price_band_pct is None:
        return False
    if pd.isna(row.market_bid) or pd.isna(row.market_ask) or pd.isna(row.price):
        return False
    market_bid = float(row.market_bid)
    market_ask = float(row.market_ask)
    if market_bid <= 0 or market_ask <= 0:
        return False
    lower = market_bid * (1.0 - price_band_pct)
    upper = market_ask * (1.0 + price_band_pct)
    return float(row.price) < lower or float(row.price) > upper


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
