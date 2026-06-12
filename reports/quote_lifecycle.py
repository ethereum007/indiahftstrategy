from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.quote_risk import (
    quote_risk_review_check,
    quote_risk_review_parameters,
    read_quote_risk_summary,
)
from risk.compliance import check_order_to_trade_ratio


@dataclass(frozen=True)
class QuoteLifecycleThresholds:
    quote_ttl_ns: int | None = None
    max_order_messages: int | None = None
    max_active_quotes: int | None = None
    max_replaces: int | None = None
    max_cancels: int | None = None
    max_messages_per_snapshot: int | None = None
    expected_fills: int | None = None
    max_order_to_trade_ratio: float | None = None
    final_cancel: bool = True


@dataclass(frozen=True)
class QuoteLifecycleReport:
    actions: pd.DataFrame
    route_orders: pd.DataFrame
    snapshots: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_quote_lifecycle(
    quotes: pd.DataFrame,
    *,
    thresholds: QuoteLifecycleThresholds | None = None,
    quote_risk_summary: pd.DataFrame | None = None,
    quote_risk_review_dir: str | Path | None = None,
    require_quote_risk_review: bool = False,
) -> QuoteLifecycleReport:
    thresholds = thresholds or QuoteLifecycleThresholds()
    _validate_thresholds(thresholds)
    frame = _normalize_quotes(quotes)
    actions, snapshots = _lifecycle_actions(frame, thresholds)
    route_orders = _route_orders(actions)
    summary = _summary(frame, actions, route_orders, snapshots, thresholds)
    checks = _checks(summary.iloc[0], thresholds)
    quote_risk_summary = pd.DataFrame() if quote_risk_summary is None else quote_risk_summary
    quote_risk_check = quote_risk_review_check(
        quote_risk_summary,
        required=require_quote_risk_review,
        input_dir=quote_risk_review_dir,
    )
    if quote_risk_check is not None:
        checks = pd.concat([pd.DataFrame([quote_risk_check]), checks], ignore_index=True, sort=False)
    summary["quote_risk_review_required"] = bool(require_quote_risk_review)
    summary["quote_risk_review_provided"] = bool(quote_risk_check is not None and quote_risk_check["input_dir"])
    summary["quote_risk_review_passed"] = bool(True if quote_risk_check is None else quote_risk_check["passed"])
    summary["quote_risk_review_reason"] = "" if quote_risk_check is None else str(quote_risk_check["reason"])
    summary["failed_checks"] = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    summary["ready"] = bool(summary.iloc[0]["failed_checks"] == 0)
    summary["recommendation"] = _recommendation(summary.iloc[0])
    return QuoteLifecycleReport(actions=actions, route_orders=route_orders, snapshots=snapshots, checks=checks, summary=summary)


def write_quote_lifecycle_plan(
    quotes_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: QuoteLifecycleThresholds | None = None,
    quote_risk_review_dir: str | Path | None = None,
    require_quote_risk_review: bool = False,
) -> QuoteLifecycleReport:
    quotes_file = Path(quotes_path)
    if quotes_file.is_dir():
        quotes_file = quotes_file / "surface_quotes.csv"
    if not quotes_file.exists():
        raise FileNotFoundError(f"surface quotes file not found: {quotes_file}")
    thresholds = thresholds or QuoteLifecycleThresholds()
    quote_risk_summary = read_quote_risk_summary(quote_risk_review_dir)
    report = evaluate_quote_lifecycle(
        pd.read_csv(quotes_file),
        thresholds=thresholds,
        quote_risk_summary=quote_risk_summary,
        quote_risk_review_dir=quote_risk_review_dir,
        require_quote_risk_review=require_quote_risk_review,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.actions.to_csv(out / "quote_lifecycle_actions.csv", index=False)
    report.route_orders.to_csv(out / "quote_lifecycle_route_orders.csv", index=False)
    report.snapshots.to_csv(out / "quote_lifecycle_snapshots.csv", index=False)
    report.checks.to_csv(out / "quote_lifecycle_checks.csv", index=False)
    report.summary.to_csv(out / "quote_lifecycle_summary.csv", index=False)
    inputs: dict[str, Any] = {"quotes": quotes_file}
    if quote_risk_review_dir is not None:
        inputs["quote_risk_review"] = Path(quote_risk_review_dir)
    write_experiment_manifest(
        out,
        run_type="quote_lifecycle_plan",
        parameters={
            "thresholds": asdict(thresholds),
            "require_quote_risk_review": bool(require_quote_risk_review),
            "quote_risk_review": quote_risk_review_parameters(quote_risk_summary, quote_risk_review_dir),
        },
        inputs=inputs,
    )
    return QuoteLifecycleReport(report.actions, report.route_orders, report.snapshots, report.checks, report.summary, out)


def _lifecycle_actions(
    quotes: pd.DataFrame,
    thresholds: QuoteLifecycleThresholds,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if quotes.empty:
        return _empty_actions(), _empty_snapshots()

    active: dict[tuple[str, int], dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    order_seq = 0
    action_seq = 0

    for snapshot_index, (ts_ns, snapshot) in enumerate(_snapshot_groups(quotes)):
        snapshot_messages_before = _message_count(actions)
        action_seq = _cancel_stale_quotes(
            active,
            actions,
            ts_ns=ts_ns,
            snapshot_index=snapshot_index,
            action_seq=action_seq,
            thresholds=thresholds,
        )
        desired = _desired_snapshot(snapshot)
        desired_keys = set(desired["quote_key"])
        for row in desired.itertuples(index=False):
            key = row.quote_key
            current = active.get(key)
            if current is None:
                order_seq += 1
                action_seq += 1
                order_id = _order_id(order_seq)
                actions.append(
                    _action_row(
                        action_seq,
                        ts_ns=ts_ns,
                        snapshot_index=snapshot_index,
                        action="submit",
                        order_id=order_id,
                        replaces_order_id="",
                        row=row,
                        message_count=1,
                        reason="new_quote",
                        quote_age_ns=0,
                        order_action="submit",
                    )
                )
                active[key] = _active_quote(row, order_id, ts_ns)
                continue
            if _quote_changed(current, row):
                old_order_id = str(current["client_order_id"])
                order_seq += 1
                action_seq += 1
                order_id = _order_id(order_seq)
                actions.append(
                    _action_row(
                        action_seq,
                        ts_ns=ts_ns,
                        snapshot_index=snapshot_index,
                        action="replace",
                        order_id=order_id,
                        replaces_order_id=old_order_id,
                        row=row,
                        message_count=2,
                        reason="price_or_qty_change",
                        quote_age_ns=_quote_age(ts_ns, current["ts_submit_ns"]),
                        order_action="replace",
                    )
                )
                active[key] = _active_quote(row, order_id, ts_ns)
        for key in sorted(set(active) - desired_keys):
            current = active.pop(key)
            action_seq += 1
            actions.append(
                _cancel_row(
                    action_seq,
                    ts_ns=ts_ns,
                    snapshot_index=snapshot_index,
                    current=current,
                    reason="quote_not_in_snapshot",
                )
            )
        snapshot_rows.append(
            {
                "snapshot_index": snapshot_index,
                "ts_ns": ts_ns,
                "desired_quotes": int(len(desired)),
                "active_quotes": int(len(active)),
                "messages": int(_message_count(actions) - snapshot_messages_before),
            }
        )

    if thresholds.final_cancel and active:
        final_ts = snapshot_rows[-1]["ts_ns"] if snapshot_rows else 0
        final_index = int(snapshot_rows[-1]["snapshot_index"]) + 1 if snapshot_rows else 0
        snapshot_messages_before = _message_count(actions)
        for key in sorted(active):
            current = active[key]
            action_seq += 1
            actions.append(
                _cancel_row(
                    action_seq,
                    ts_ns=final_ts,
                    snapshot_index=final_index,
                    current=current,
                    reason="end_of_plan",
                )
            )
        active.clear()
        snapshot_rows.append(
            {
                "snapshot_index": final_index,
                "ts_ns": final_ts,
                "desired_quotes": 0,
                "active_quotes": 0,
                "messages": int(_message_count(actions) - snapshot_messages_before),
            }
        )

    return pd.DataFrame(actions, columns=_action_columns()), pd.DataFrame(snapshot_rows, columns=_snapshot_columns())


def _cancel_stale_quotes(
    active: dict[tuple[str, int], dict[str, Any]],
    actions: list[dict[str, Any]],
    *,
    ts_ns: int,
    snapshot_index: int,
    action_seq: int,
    thresholds: QuoteLifecycleThresholds,
) -> int:
    if thresholds.quote_ttl_ns is None:
        return action_seq
    expired = [
        key
        for key, current in active.items()
        if _quote_age(ts_ns, current["ts_submit_ns"]) >= int(thresholds.quote_ttl_ns)
    ]
    for key in sorted(expired):
        current = active.pop(key)
        action_seq += 1
        actions.append(
            _cancel_row(
                action_seq,
                ts_ns=ts_ns,
                snapshot_index=snapshot_index,
                current=current,
                reason="quote_ttl_expired",
            )
        )
    return action_seq


def _normalize_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in ("instrument_id", "side", "price", "qty") if column not in quotes.columns]
    if missing:
        raise ValueError(f"quotes missing required columns: {missing}")
    frame = quotes.copy().reset_index(drop=False).rename(columns={"index": "source_row"})
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side)
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["ts_ns"] = pd.to_numeric(frame["ts"], errors="coerce") if "ts" in frame.columns else 0
    frame["ts_ns"] = frame["ts_ns"].fillna(0).astype(np.int64)
    frame["quote_key"] = list(zip(frame["instrument_id"], frame["side"]))
    return frame.sort_values(["ts_ns", "instrument_id", "side", "source_row"]).reset_index(drop=True)


def _snapshot_groups(frame: pd.DataFrame) -> list[tuple[int, pd.DataFrame]]:
    return [(int(ts_ns), group.copy()) for ts_ns, group in frame.groupby("ts_ns", sort=True)]


def _desired_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    return (
        snapshot.sort_values(["instrument_id", "side", "source_row"])
        .drop_duplicates(subset=["quote_key"], keep="last")
        .reset_index(drop=True)
    )


def _active_quote(row: Any, order_id: str, ts_ns: int) -> dict[str, Any]:
    return {
        "client_order_id": order_id,
        "instrument_id": str(row.instrument_id),
        "side": int(row.side),
        "side_text": _side_text(row.side),
        "qty": float(row.qty),
        "price": float(row.price),
        "ts_submit_ns": int(ts_ns),
        "source_row": int(row.source_row),
        "expiry": _optional(row, "expiry"),
        "strike": _optional(row, "strike"),
        "option_type": _optional(row, "option_type"),
        "market_bid": _optional(row, "market_bid"),
        "market_ask": _optional(row, "market_ask"),
        "marketable": _optional(row, "marketable", False),
        "quote_edge": _optional(row, "quote_edge"),
        "theo": _optional(row, "theo"),
        "market_spread_ticks": _optional(row, "market_spread_ticks"),
        "forward": _optional(row, "forward"),
        "futures_ts": _optional(row, "futures_ts"),
        "order_type": str(_optional(row, "order_type", "LIMIT")),
        "time_in_force": str(_optional(row, "time_in_force", "DAY")),
    }


def _action_row(
    action_seq: int,
    *,
    ts_ns: int,
    snapshot_index: int,
    action: str,
    order_id: str,
    replaces_order_id: str,
    row: Any,
    message_count: int,
    reason: str,
    quote_age_ns: int,
    order_action: str,
) -> dict[str, Any]:
    return {
        "action_id": _action_id(action_seq),
        "ts_ns": int(ts_ns),
        "snapshot_index": int(snapshot_index),
        "action": action,
        "client_order_id": order_id,
        "replaces_order_id": replaces_order_id,
        "instrument_id": str(row.instrument_id),
        "side": int(row.side),
        "side_text": _side_text(row.side),
        "qty": float(row.qty),
        "price": float(row.price),
        "message_count": int(message_count),
        "reason": reason,
        "quote_age_ns": int(quote_age_ns),
        "source_row": int(row.source_row),
        "expiry": _optional(row, "expiry"),
        "strike": _optional(row, "strike"),
        "option_type": _optional(row, "option_type"),
        "market_bid": _optional(row, "market_bid"),
        "market_ask": _optional(row, "market_ask"),
        "marketable": _optional(row, "marketable", False),
        "quote_edge": _optional(row, "quote_edge"),
        "theo": _optional(row, "theo"),
        "market_spread_ticks": _optional(row, "market_spread_ticks"),
        "forward": _optional(row, "forward"),
        "futures_ts": _optional(row, "futures_ts"),
        "order_type": str(_optional(row, "order_type", "LIMIT")),
        "time_in_force": str(_optional(row, "time_in_force", "DAY")),
        "lifecycle_action": order_action,
    }


def _cancel_row(
    action_seq: int,
    *,
    ts_ns: int,
    snapshot_index: int,
    current: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "action_id": _action_id(action_seq),
        "ts_ns": int(ts_ns),
        "snapshot_index": int(snapshot_index),
        "action": "cancel",
        "client_order_id": str(current["client_order_id"]),
        "replaces_order_id": "",
        "instrument_id": str(current["instrument_id"]),
        "side": int(current["side"]),
        "side_text": str(current["side_text"]),
        "qty": float(current["qty"]),
        "price": float(current["price"]),
        "message_count": 1,
        "reason": reason,
        "quote_age_ns": int(_quote_age(ts_ns, current["ts_submit_ns"])),
        "source_row": int(current["source_row"]),
        "expiry": current.get("expiry", np.nan),
        "strike": current.get("strike", np.nan),
        "option_type": current.get("option_type", np.nan),
        "market_bid": current.get("market_bid", np.nan),
        "market_ask": current.get("market_ask", np.nan),
        "marketable": current.get("marketable", False),
        "quote_edge": current.get("quote_edge", np.nan),
        "theo": current.get("theo", np.nan),
        "market_spread_ticks": current.get("market_spread_ticks", np.nan),
        "forward": current.get("forward", np.nan),
        "futures_ts": current.get("futures_ts", np.nan),
        "order_type": str(current.get("order_type", "LIMIT")),
        "time_in_force": str(current.get("time_in_force", "DAY")),
        "lifecycle_action": "cancel",
    }


def _route_orders(actions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "client_order_id",
        "source_row",
        "instrument_id",
        "side",
        "side_text",
        "qty",
        "price",
        "order_type",
        "time_in_force",
        "ts_signal_ns",
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
    if actions.empty:
        return pd.DataFrame(columns=columns)
    route = actions.loc[actions["action"].isin(["submit", "replace"])].copy().reset_index(drop=True)
    if route.empty:
        return pd.DataFrame(columns=columns)
    route["ts_signal_ns"] = route["ts_ns"]
    route["source_row"] = route.index
    route["lifecycle_action_id"] = route["action_id"]
    route["lifecycle_reason"] = route["reason"]
    route["lifecycle_message_count"] = route["message_count"]
    for column in columns:
        if column not in route.columns:
            route[column] = np.nan
    return route[columns]


def _summary(
    quotes: pd.DataFrame,
    actions: pd.DataFrame,
    route_orders: pd.DataFrame,
    snapshots: pd.DataFrame,
    thresholds: QuoteLifecycleThresholds,
) -> pd.DataFrame:
    action_counts = actions["action"].value_counts() if not actions.empty else pd.Series(dtype=int)
    order_messages = _message_count(actions.to_dict("records")) if not actions.empty else 0
    expected_fills = thresholds.expected_fills
    otr = np.nan
    if expected_fills is not None:
        otr = check_order_to_trade_ratio(
            orders_sent=order_messages,
            fills=int(expected_fills),
            limit=thresholds.max_order_to_trade_ratio or 1.0,
        ).ratio
    return pd.DataFrame(
        [
            {
                "ready": False,
                "snapshots": int(quotes["ts_ns"].nunique()) if not quotes.empty else 0,
                "input_quotes": int(len(quotes)),
                "instruments": int(quotes["instrument_id"].nunique()) if not quotes.empty else 0,
                "invalid_side_quotes": int((~quotes["side"].isin([-1, 1])).sum()) if not quotes.empty else 0,
                "nonpositive_qty_quotes": _invalid_positive_count(quotes, "qty"),
                "nonpositive_price_quotes": _invalid_positive_count(quotes, "price"),
                "lifecycle_actions": int(len(actions)),
                "route_orders": int(len(route_orders)),
                "submits": int(action_counts.get("submit", 0)),
                "replaces": int(action_counts.get("replace", 0)),
                "cancels": int(action_counts.get("cancel", 0)),
                "order_messages": int(order_messages),
                "max_messages_per_snapshot": int(snapshots["messages"].max()) if not snapshots.empty else 0,
                "max_active_quotes": int(snapshots["active_quotes"].max()) if not snapshots.empty else 0,
                "expected_fills": np.nan if expected_fills is None else int(expected_fills),
                "order_to_trade_ratio": float(otr) if not pd.isna(otr) else np.nan,
                "failed_checks": 0,
                "recommendation": "",
            }
        ]
    )


def _checks(row: pd.Series, thresholds: QuoteLifecycleThresholds) -> pd.DataFrame:
    checks = [
        _check("quotes_nonempty", row["input_quotes"], ">=", 1, int(row["input_quotes"]) >= 1, "quote input is empty"),
        _check(
            "valid_sides",
            row["invalid_side_quotes"],
            "==",
            0,
            int(row["invalid_side_quotes"]) == 0,
            "one or more quotes has an invalid side",
        ),
        _check(
            "positive_qty",
            row["nonpositive_qty_quotes"],
            "==",
            0,
            int(row["nonpositive_qty_quotes"]) == 0,
            "one or more quotes has nonpositive qty",
        ),
        _check(
            "positive_price",
            row["nonpositive_price_quotes"],
            "==",
            0,
            int(row["nonpositive_price_quotes"]) == 0,
            "one or more quotes has nonpositive price",
        ),
        _check(
            "route_orders_nonempty",
            row["route_orders"],
            ">=",
            1,
            int(row["route_orders"]) >= 1,
            "no submit or replace orders are available to route",
        ),
    ]
    optional_limits = (
        ("order_messages", thresholds.max_order_messages),
        ("max_active_quotes", thresholds.max_active_quotes),
        ("replaces", thresholds.max_replaces),
        ("cancels", thresholds.max_cancels),
        ("max_messages_per_snapshot", thresholds.max_messages_per_snapshot),
    )
    for column, threshold in optional_limits:
        if threshold is not None:
            checks.append(_threshold_check(column, row[column], "<=", threshold))
    if thresholds.max_order_to_trade_ratio is not None:
        if thresholds.expected_fills is None:
            checks.append(
                _check(
                    "expected_fills_available",
                    "missing",
                    "present",
                    True,
                    False,
                    "expected_fills is required when max_order_to_trade_ratio is set",
                )
            )
        else:
            checks.append(
                _threshold_check(
                    "order_to_trade_ratio",
                    row["order_to_trade_ratio"],
                    "<=",
                    thresholds.max_order_to_trade_ratio,
                )
            )
    return pd.DataFrame(checks)


def _recommendation(row: pd.Series) -> str:
    if not bool(row["ready"]):
        if not bool(row.get("quote_risk_review_passed", True)):
            return "fix_quote_risk_review_before_routing"
        return "reduce_quote_churn_or_limits_before_routing"
    if int(row.get("order_messages", 0)) == 0:
        return "no_quote_actions_to_route"
    return "route_with_lifecycle_controls"


def _threshold_check(name: str, value: Any, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = _number(value)
    threshold_float = float(threshold)
    if operator == "<=":
        passed = not np.isnan(value_float) and value_float <= threshold_float
    elif operator == ">=":
        passed = not np.isnan(value_float) and value_float >= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = "" if passed else f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: QuoteLifecycleThresholds) -> None:
    for name in (
        "quote_ttl_ns",
        "max_order_messages",
        "max_active_quotes",
        "max_replaces",
        "max_cancels",
        "max_messages_per_snapshot",
        "expected_fills",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    if thresholds.max_order_to_trade_ratio is not None and thresholds.max_order_to_trade_ratio <= 0:
        raise ValueError("max_order_to_trade_ratio must be positive")


def _quote_changed(current: dict[str, Any], row: Any) -> bool:
    return abs(float(current["price"]) - float(row.price)) > 1e-12 or abs(float(current["qty"]) - float(row.qty)) > 1e-12


def _quote_age(ts_ns: int, ts_submit_ns: int) -> int:
    return max(int(ts_ns) - int(ts_submit_ns), 0)


def _normalize_side(value: Any) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    numeric = float(value)
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0


def _side_text(side: Any) -> str:
    return "BUY" if int(side) > 0 else "SELL" if int(side) < 0 else "UNKNOWN"


def _optional(row: Any, name: str, default: Any = np.nan) -> Any:
    return getattr(row, name, default)


def _invalid_positive_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty:
        return 0
    values = pd.to_numeric(frame[column], errors="coerce")
    return int((values.isna() | (values <= 0)).sum())


def _order_id(order_seq: int) -> str:
    return f"QLF-{order_seq:06d}"


def _action_id(action_seq: int) -> str:
    return f"ACT-{action_seq:06d}"


def _message_count(actions: list[dict[str, Any]]) -> int:
    return int(sum(int(action.get("message_count", 0)) for action in actions))


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _action_columns() -> list[str]:
    return [
        "action_id",
        "ts_ns",
        "snapshot_index",
        "action",
        "client_order_id",
        "replaces_order_id",
        "instrument_id",
        "side",
        "side_text",
        "qty",
        "price",
        "message_count",
        "reason",
        "quote_age_ns",
        "source_row",
        "expiry",
        "strike",
        "option_type",
        "market_bid",
        "market_ask",
        "marketable",
        "quote_edge",
        "theo",
        "market_spread_ticks",
        "forward",
        "futures_ts",
        "order_type",
        "time_in_force",
        "lifecycle_action",
    ]


def _snapshot_columns() -> list[str]:
    return ["snapshot_index", "ts_ns", "desired_quotes", "active_quotes", "messages"]


def _empty_actions() -> pd.DataFrame:
    return pd.DataFrame(columns=_action_columns())


def _empty_snapshots() -> pd.DataFrame:
    return pd.DataFrame(columns=_snapshot_columns())
