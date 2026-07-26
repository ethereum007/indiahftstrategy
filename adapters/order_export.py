from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.orders import read_order_csv
from reports.manifest import write_experiment_manifest


EXPORT_COLUMNS = [
    "broker_order_id",
    "client_order_id",
    "launch_order_id",
    "instrument_id",
    "research_instrument_id",
    "broker_instrument_token",
    "instrument_resolution_method",
    "instrument_resolution_status",
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
    "leg_group_id",
    "leg_role",
    "leg_index",
    "leg_count",
    "lifecycle_action",
    "lifecycle_action_id",
    "lifecycle_reason",
    "lifecycle_message_count",
    "quote_age_ns",
    "replaces_order_id",
]

INSTRUMENT_RESOLUTION_COLUMNS = {
    "research_instrument_id",
    "broker_instrument_token",
    "instrument_resolution_method",
    "instrument_resolution_status",
}
MULTI_LEG_IDENTITY_COLUMNS = {
    "leg_group_id",
    "leg_role",
    "leg_index",
    "leg_count",
}


@dataclass(frozen=True)
class OrderExportConfig:
    adapter: str = "normalized"
    route_tag: str | None = None
    require_launch_ready: bool = True
    require_limit_orders: bool = True
    require_instrument_resolution: bool = False
    require_broker_instrument_token: bool = True
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
    summary = _summary(
        orders,
        launch_summary,
        checks,
        adapter.name,
        schema_status,
        config,
    )
    schema = _schema_frame(
        orders,
        adapter.name,
        schema_status,
        config,
    )
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
    launch_orders = _read_required(
        launch_orders_path,
        preserve_order_identity=True,
    )
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
    resolution_provided = _instrument_resolution_provided(orders)
    if config.require_instrument_resolution or resolution_provided:
        checks.extend(
            _instrument_resolution_checks(
                orders,
                required=config.require_instrument_resolution,
                require_token=config.require_broker_instrument_token,
            )
        )
    return pd.DataFrame(checks)


def _summary(
    orders: pd.DataFrame,
    launch_summary: pd.DataFrame,
    checks: pd.DataFrame,
    adapter: str,
    schema_status: str,
    config: OrderExportConfig,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    total_notional = float((orders["qty"] * orders["price"]).sum()) if not orders.empty else 0.0
    resolution_provided = _instrument_resolution_provided(orders)
    resolution_ready = _instrument_resolution_checks_passed(checks)
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
                "instrument_resolution_required": bool(
                    config.require_instrument_resolution
                ),
                "broker_instrument_token_required": bool(
                    config.require_broker_instrument_token
                ),
                "instrument_resolution_provided": resolution_provided,
                "instrument_resolution_ready": resolution_ready,
                "instrument_resolution_orders": _nonblank_count(
                    orders,
                    "instrument_resolution_status",
                ),
                "broker_instrument_token_orders": _nonblank_count(
                    orders,
                    "broker_instrument_token",
                ),
                "multi_leg_groups": _multi_leg_group_count(orders),
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0,
            }
        ]
    )


def _instrument_resolution_checks(
    orders: pd.DataFrame,
    *,
    required: bool,
    require_token: bool,
) -> list[dict[str, Any]]:
    order_count = int(len(orders))
    provided = _instrument_resolution_provided(orders)
    statuses = _text_column(orders, "instrument_resolution_status").str.lower()
    methods = _text_column(orders, "instrument_resolution_method")
    research_ids = _text_column(orders, "research_instrument_id")
    broker_symbols = _text_column(orders, "instrument_id")
    broker_tokens = _text_column(orders, "broker_instrument_token")
    checks = [
        _check(
            "instrument_resolution_metadata_present",
            provided,
            "is",
            True,
            provided or not required,
            "broker instrument resolution metadata is required but missing",
        ),
        _check(
            "instrument_resolution_status_complete",
            int(statuses.eq("resolved").sum()),
            "==",
            order_count,
            bool(order_count > 0 and statuses.eq("resolved").all()),
            "one or more launch orders are not marked as broker-resolved",
        ),
        _check(
            "research_instrument_id_complete",
            int(research_ids.ne("").sum()),
            "==",
            order_count,
            bool(order_count > 0 and research_ids.ne("").all()),
            "one or more resolved launch orders lost the research instrument ID",
        ),
        _check(
            "instrument_resolution_method_complete",
            int(methods.ne("").sum()),
            "==",
            order_count,
            bool(order_count > 0 and methods.ne("").all()),
            "one or more resolved launch orders lost the instrument resolution method",
        ),
        _check(
            "broker_instrument_id_complete",
            int(broker_symbols.ne("").sum()),
            "==",
            order_count,
            bool(order_count > 0 and broker_symbols.ne("").all()),
            "one or more resolved launch orders have a blank broker trading symbol",
        ),
    ]
    if require_token:
        checks.append(
            _check(
                "broker_instrument_token_complete",
                int(broker_tokens.ne("").sum()),
                "==",
                order_count,
                bool(order_count > 0 and broker_tokens.ne("").all()),
                "one or more resolved launch orders lost the broker instrument token",
            )
        )
    checks.extend(
        _multi_leg_identity_checks(
            orders,
            require_token=require_token,
        )
    )
    return checks


def _multi_leg_identity_checks(
    orders: pd.DataFrame,
    *,
    require_token: bool,
) -> list[dict[str, Any]]:
    group_ids = _text_column(orders, "leg_group_id")
    roles = _text_column(orders, "leg_role")
    leg_counts = pd.to_numeric(
        orders.get("leg_count", pd.Series(index=orders.index, dtype=float)),
        errors="coerce",
    )
    metadata_provided = bool(
        group_ids.ne("").any()
        or roles.ne("").any()
        or leg_counts.notna().any()
    )
    if not metadata_provided:
        return []

    complete_rows = group_ids.ne("") & roles.ne("") & leg_counts.gt(0)
    group_failures = 0
    duplicate_role_groups = 0
    duplicate_symbol_groups = 0
    duplicate_token_groups = 0
    for group_id in group_ids[group_ids.ne("")].drop_duplicates().tolist():
        mask = group_ids.eq(group_id)
        expected_values = sorted(
            set(int(value) for value in leg_counts.loc[mask].dropna())
        )
        expected = expected_values[0] if len(expected_values) == 1 else 0
        actual = int(mask.sum())
        if expected <= 0 or actual != expected:
            group_failures += 1
        if int(roles.loc[mask].nunique()) != actual:
            duplicate_role_groups += 1
        if int(_text_column(orders.loc[mask], "instrument_id").nunique()) != actual:
            duplicate_symbol_groups += 1
        if require_token and int(
            _text_column(orders.loc[mask], "broker_instrument_token").nunique()
        ) != actual:
            duplicate_token_groups += 1

    group_count = int(group_ids[group_ids.ne("")].nunique())
    checks = [
        _check(
            "multi_leg_identity_complete",
            int(complete_rows.sum()),
            "==",
            len(orders),
            bool(len(orders) > 0 and complete_rows.all()),
            "multi-leg contract identity is missing a group, role, or declared leg count",
        ),
        _check(
            "multi_leg_group_cardinality",
            group_failures,
            "==",
            0,
            group_count > 0 and group_failures == 0,
            "one or more multi-leg groups do not match their declared leg count",
        ),
        _check(
            "multi_leg_roles_unique",
            duplicate_role_groups,
            "==",
            0,
            group_count > 0 and duplicate_role_groups == 0,
            "one or more multi-leg groups reuse a leg role",
        ),
        _check(
            "multi_leg_broker_symbols_unique",
            duplicate_symbol_groups,
            "==",
            0,
            group_count > 0 and duplicate_symbol_groups == 0,
            "one or more multi-leg groups reuse a broker trading symbol",
        ),
    ]
    if require_token:
        checks.append(
            _check(
                "multi_leg_broker_tokens_unique",
                duplicate_token_groups,
                "==",
                0,
                group_count > 0 and duplicate_token_groups == 0,
                "one or more multi-leg groups reuse a broker instrument token",
            )
        )
    return checks


def _instrument_resolution_provided(orders: pd.DataFrame) -> bool:
    return any(
        _text_column(orders, column).ne("").any()
        for column in (
            "research_instrument_id",
            "broker_instrument_token",
            "instrument_resolution_method",
            "instrument_resolution_status",
        )
    )


def _instrument_resolution_checks_passed(checks: pd.DataFrame) -> bool:
    if checks.empty:
        return False
    mask = checks["check"].astype(str).str.startswith(
        ("instrument_resolution_", "research_instrument_", "broker_instrument_", "multi_leg_")
    )
    return bool(mask.any() and checks.loc[mask, "passed"].astype(bool).all())


def _nonblank_count(frame: pd.DataFrame, column: str) -> int:
    return int(_text_column(frame, column).ne("").sum())


def _multi_leg_group_count(frame: pd.DataFrame) -> int:
    values = _text_column(frame, "leg_group_id")
    return int(values.loc[values.ne("")].nunique())


def _text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([""] * len(frame), index=frame.index, dtype="object")
    return (
        frame[column]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def _schema_frame(
    orders: pd.DataFrame,
    adapter: str,
    schema_status: str,
    config: OrderExportConfig,
) -> pd.DataFrame:
    resolution_required = bool(
        config.require_instrument_resolution
        or _instrument_resolution_provided(orders)
    )
    multi_leg_required = _multi_leg_group_count(orders) > 0
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "adapter_schema_status": schema_status,
                "column": col,
                "dtype": str(orders[col].dtype),
                "required": _schema_column_required(
                    col,
                    resolution_required=resolution_required,
                    multi_leg_required=multi_leg_required,
                    require_token=config.require_broker_instrument_token,
                ),
            }
            for col in orders.columns
        ]
    )


def _schema_column_required(
    column: str,
    *,
    resolution_required: bool,
    multi_leg_required: bool,
    require_token: bool,
) -> bool:
    if column == "broker_instrument_token":
        return bool(resolution_required and require_token)
    if column in INSTRUMENT_RESOLUTION_COLUMNS:
        return resolution_required
    if column in MULTI_LEG_IDENTITY_COLUMNS:
        return multi_leg_required
    return True


def _validate_config(config: OrderExportConfig) -> None:
    if config.max_orders is not None and config.max_orders <= 0:
        raise ValueError("max_orders must be positive")
    get_adapter(config.adapter)


def _read_required(
    path: Path,
    *,
    preserve_order_identity: bool = False,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required order export input missing: {path}")
    frame = (
        read_order_csv(path)
        if preserve_order_identity
        else pd.read_csv(path)
    )
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
