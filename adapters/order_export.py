from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from reports.manifest import write_experiment_manifest


EXPORT_COLUMNS = [
    "broker_order_id",
    "client_order_id",
    "launch_order_id",
    "instrument_id",
    "side",
    "side_text",
    "qty",
    "price",
    "order_type",
    "time_in_force",
    "ts_signal_ns",
    "scenario_key",
    "launch_mode",
    "route_tag",
    "adapter",
    "adapter_schema_status",
]


@dataclass(frozen=True)
class OrderExportConfig:
    adapter: str = "normalized"
    route_tag: str | None = None
    require_launch_ready: bool = True
    require_limit_orders: bool = True
    max_orders: int | None = None


@dataclass(frozen=True)
class OrderExportReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_order_export(
    launch_orders: pd.DataFrame,
    launch_summary: pd.DataFrame,
    launch_config: dict[str, Any],
    *,
    config: OrderExportConfig | None = None,
) -> OrderExportReport:
    config = config or OrderExportConfig()
    _validate_config(config)
    adapter = get_adapter(config.adapter)
    _require(launch_orders, ["client_order_id", "instrument_id", "side", "qty", "price"], "launch_orders")
    _require(launch_summary, ["ready", "mode", "scenario_key"], "launch_summary")
    schema_status = adapter_schema_status(adapter.name)
    orders = _export_orders(
        launch_orders,
        adapter_name=adapter.name,
        schema_status=schema_status,
        route_tag=config.route_tag,
    )
    checks = _checks(orders, launch_summary, launch_config, config)
    summary = _summary(orders, launch_summary, checks, adapter.name, schema_status)
    schema = _schema_frame(orders, adapter.name, schema_status)
    return OrderExportReport(orders=orders, checks=checks, summary=summary, schema=schema)


def write_order_export(
    launch_dir: str | Path,
    *,
    output_dir: str | Path,
    config: OrderExportConfig | None = None,
) -> OrderExportReport:
    launch = Path(launch_dir)
    launch_orders_path = launch / "launch_orders.csv"
    launch_summary_path = launch / "launch_summary.csv"
    launch_config_path = launch / "launch_config.json"
    launch_orders = _read_required(launch_orders_path)
    launch_summary = _read_required(launch_summary_path)
    if not launch_config_path.exists():
        raise FileNotFoundError(f"launch_config.json not found: {launch_config_path}")
    launch_config = json.loads(launch_config_path.read_text(encoding="utf-8"))

    config = config or OrderExportConfig()
    report = evaluate_order_export(launch_orders, launch_summary, launch_config, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "broker_orders.csv", index=False)
    report.checks.to_csv(out / "broker_order_checks.csv", index=False)
    report.summary.to_csv(out / "broker_order_summary.csv", index=False)
    report.schema.to_csv(out / "broker_order_schema.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="order_export",
        parameters={"config": asdict(config)},
        inputs={"launch": launch},
    )
    return OrderExportReport(report.orders, report.checks, report.summary, report.schema, out)


def _export_orders(
    launch_orders: pd.DataFrame,
    *,
    adapter_name: str,
    schema_status: str,
    route_tag: str | None,
) -> pd.DataFrame:
    frame = launch_orders.copy().reset_index(drop=True)
    frame["side"] = frame["side"].map(_normalize_side)
    frame["side_text"] = frame["side"].map({1: "BUY", -1: "SELL"}).fillna("UNKNOWN")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    if "order_type" not in frame.columns:
        frame["order_type"] = "LIMIT"
    if "time_in_force" not in frame.columns:
        frame["time_in_force"] = "DAY"
    if "ts_signal_ns" not in frame.columns:
        frame["ts_signal_ns"] = np.nan
    if "launch_order_id" not in frame.columns:
        frame["launch_order_id"] = [f"LCH-{idx:06d}-{row.client_order_id}" for idx, row in frame.iterrows()]
    if "launch_mode" not in frame.columns:
        frame["launch_mode"] = "paper"
    if "scenario_key" not in frame.columns:
        frame["scenario_key"] = ""
    frame["route_tag"] = route_tag or frame["launch_mode"].astype(str)
    frame["adapter"] = adapter_name
    frame["adapter_schema_status"] = schema_status
    frame["broker_order_id"] = [
        f"{adapter_name.upper()}-{idx:06d}-{str(order_id)}" for idx, order_id in enumerate(frame["client_order_id"])
    ]
    for col in EXPORT_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame[EXPORT_COLUMNS]


def _checks(
    orders: pd.DataFrame,
    launch_summary: pd.DataFrame,
    launch_config: dict[str, Any],
    config: OrderExportConfig,
) -> pd.DataFrame:
    launch_ready = _to_bool(launch_summary.iloc[0]["ready"]) and _to_bool(launch_config.get("ready", False))
    checks = [
        _check(
            "launch_ready",
            launch_ready,
            "is",
            True,
            (not config.require_launch_ready) or launch_ready,
            "launch bundle is not ready",
        ),
        _check("orders_nonempty", len(orders), ">=", 1, len(orders) > 0, "no launch orders available"),
        _check(
            "valid_sides",
            int(orders["side"].isin([-1, 1]).sum()),
            "==",
            len(orders),
            bool(orders["side"].isin([-1, 1]).all()),
            "orders contain invalid side values",
        ),
        _check(
            "positive_qty",
            int((orders["qty"] > 0).sum()),
            "==",
            len(orders),
            bool((orders["qty"] > 0).all()),
            "orders contain non-positive quantities",
        ),
        _check(
            "positive_price",
            int((orders["price"] > 0).sum()),
            "==",
            len(orders),
            bool((orders["price"] > 0).all()),
            "orders contain non-positive prices",
        ),
        _check(
            "unique_client_order_id",
            int(orders["client_order_id"].nunique()),
            "==",
            len(orders),
            int(orders["client_order_id"].nunique()) == len(orders),
            "client_order_id values are not unique",
        ),
    ]
    if config.require_limit_orders:
        limit_mask = orders["order_type"].astype(str).str.upper() == "LIMIT"
        checks.append(
            _check(
                "limit_orders_only",
                int(limit_mask.sum()),
                "==",
                len(orders),
                bool(limit_mask.all()),
                "non-LIMIT order types are present",
            )
        )
    if config.max_orders is not None:
        checks.append(
            _check(
                "max_orders",
                len(orders),
                "<=",
                config.max_orders,
                len(orders) <= config.max_orders,
                "order count exceeds export cap",
            )
        )
    return pd.DataFrame(checks)


def _summary(
    orders: pd.DataFrame,
    launch_summary: pd.DataFrame,
    checks: pd.DataFrame,
    adapter: str,
    schema_status: str,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    total_notional = float((orders["qty"] * orders["price"]).sum()) if not orders.empty else 0.0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": schema_status,
                "launch_mode": str(launch_summary.iloc[0]["mode"]),
                "scenario_key": str(launch_summary.iloc[0]["scenario_key"]),
                "orders": int(len(orders)),
                "buy_orders": int((orders["side"] == 1).sum()),
                "sell_orders": int((orders["side"] == -1).sum()),
                "total_qty": int(pd.to_numeric(orders["qty"], errors="coerce").sum()) if not orders.empty else 0,
                "total_notional": total_notional,
                "max_order_notional": float((orders["qty"] * orders["price"]).max()) if not orders.empty else 0.0,
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0,
            }
        ]
    )


def _schema_frame(orders: pd.DataFrame, adapter: str, schema_status: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "adapter_schema_status": schema_status,
                "column": col,
                "dtype": str(orders[col].dtype),
                "required": True,
            }
            for col in orders.columns
        ]
    )


def _validate_config(config: OrderExportConfig) -> None:
    if config.max_orders is not None and config.max_orders <= 0:
        raise ValueError("max_orders must be positive")
    get_adapter(config.adapter)


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required order export input missing: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required order export input is empty: {path}")
    return frame


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


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


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
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


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
