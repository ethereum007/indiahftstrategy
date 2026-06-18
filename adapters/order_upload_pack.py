from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.mapped_order_export import (
    MAPPING_COLUMNS,
    MappedOrderExportConfig,
    map_broker_orders,
)
from reports.manifest import write_experiment_manifest


TEMPLATE_COLUMNS = [*MAPPING_COLUMNS, "template_status", "notes"]


@dataclass(frozen=True)
class OrderUploadPackConfig:
    adapter: str = "arrow_money"
    product: str = "MIS"
    exchange: str = "NFO"
    require_reviewed_schema: bool = True
    output_filename: str = "broker_upload_orders.csv"
    mapping_filename: str = "broker_upload_mapping.csv"


@dataclass(frozen=True)
class OrderUploadPackReport:
    orders: pd.DataFrame
    mapping: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def build_order_upload_pack(
    broker_orders: pd.DataFrame,
    *,
    config: OrderUploadPackConfig | None = None,
) -> OrderUploadPackReport:
    config = config or OrderUploadPackConfig()
    _validate_config(config)
    mapping = broker_order_upload_mapping(config)
    mapped = map_broker_orders(
        broker_orders,
        mapping,
        config=MappedOrderExportConfig(
            adapter=config.adapter,
            output_filename=config.output_filename,
            require_all_mapped=True,
        ),
    )
    checks = _checks(broker_orders, mapped.summary, mapped.checks, config)
    summary = _summary(mapped.orders, checks, config)
    return OrderUploadPackReport(
        orders=mapped.orders,
        mapping=mapping,
        checks=checks,
        summary=summary,
        schema=mapped.schema,
    )


def write_order_upload_pack(
    export_path: str | Path,
    *,
    output_dir: str | Path,
    config: OrderUploadPackConfig | None = None,
) -> OrderUploadPackReport:
    config = config or OrderUploadPackConfig()
    _validate_config(config)
    orders_file = _broker_orders_path(export_path)
    report = build_order_upload_pack(pd.read_csv(orders_file), config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.mapping.to_csv(out / config.mapping_filename, index=False)
    report.checks.to_csv(out / "broker_upload_checks.csv", index=False)
    report.summary.to_csv(out / "broker_upload_summary.csv", index=False)
    report.schema.to_csv(out / "broker_upload_schema.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="order_upload_pack",
        parameters={"config": asdict(config)},
        inputs={"broker_orders": orders_file},
    )
    return OrderUploadPackReport(report.orders, report.mapping, report.checks, report.summary, report.schema, out)


def broker_order_upload_mapping(config: OrderUploadPackConfig) -> pd.DataFrame:
    _validate_config(config)
    if config.adapter == "normalized":
        return _mapping_frame(_normalized_rows())
    if config.adapter == "arrow_money":
        return _mapping_frame(_arrow_money_rows(config))
    if config.adapter == "irage":
        return _mapping_frame(_irage_rows(config))
    raise ValueError(f"no built-in broker upload template for adapter {config.adapter!r}")


def _arrow_money_rows(config: OrderUploadPackConfig) -> list[dict[str, Any]]:
    return [
        _row("exchange", default=config.exchange, notes="review against Arrow.money upload schema"),
        _row("tradingsymbol", source="instrument_id", transform="string"),
        _row("transaction_type", source="side", transform="side_text"),
        _row("quantity", source="qty", transform="int"),
        _row("order_type", source="order_type", transform="uppercase"),
        _row("product", default=config.product, transform="uppercase"),
        _row("price", source="price", transform="float"),
        _row("validity", source="time_in_force", transform="uppercase"),
        _row("client_order_id", source="client_order_id", transform="string"),
        _row("tag", source="route_tag", transform="string", required=False),
        *_lifecycle_rows(),
    ]


def _irage_rows(config: OrderUploadPackConfig) -> list[dict[str, Any]]:
    return [
        _row("exchange", default=config.exchange, notes="review against iRage upload schema"),
        _row("symbol", source="instrument_id", transform="string"),
        _row("side", source="side", transform="side_text"),
        _row("qty", source="qty", transform="int"),
        _row("ord_type", source="order_type", transform="uppercase"),
        _row("product", default=config.product, transform="uppercase"),
        _row("limit_price", source="price", transform="float"),
        _row("validity", source="time_in_force", transform="uppercase"),
        _row("client_tag", source="client_order_id", transform="string"),
        _row("strategy_tag", source="route_tag", transform="string", required=False),
        *_lifecycle_rows(),
    ]


def _normalized_rows() -> list[dict[str, Any]]:
    return [
        _row("broker_order_id", source="broker_order_id", transform="string"),
        _row("client_order_id", source="client_order_id", transform="string"),
        _row("instrument_id", source="instrument_id", transform="string"),
        _row("side", source="side", transform="side_signed"),
        _row("qty", source="qty", transform="int"),
        _row("price", source="price", transform="float"),
        _row("order_type", source="order_type", transform="uppercase"),
        _row("time_in_force", source="time_in_force", transform="uppercase"),
        *_lifecycle_rows(),
    ]


def _lifecycle_rows() -> list[dict[str, Any]]:
    return [
        _row("lifecycle_action", source="lifecycle_action", transform="lowercase", required=False),
        _row("lifecycle_action_id", source="lifecycle_action_id", transform="string", required=False),
        _row("lifecycle_reason", source="lifecycle_reason", transform="string", required=False),
        _row("lifecycle_message_count", source="lifecycle_message_count", transform="int", required=False),
        _row("quote_age_ns", source="quote_age_ns", transform="int", required=False),
        _row("replaces_order_id", source="replaces_order_id", transform="string", required=False),
    ]


def _mapping_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=TEMPLATE_COLUMNS)


def _row(
    target: str,
    *,
    source: str = "",
    default: str = "",
    required: bool = True,
    transform: str = "identity",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "target_column": target,
        "source_column": source,
        "default_value": default,
        "required": bool(required),
        "transform": transform,
        "template_status": "review_required",
        "notes": notes or "built-in template; review before broker submission",
    }


def _checks(
    broker_orders: pd.DataFrame,
    mapped_summary: pd.DataFrame,
    mapped_checks: pd.DataFrame,
    config: OrderUploadPackConfig,
) -> pd.DataFrame:
    schema_status = adapter_schema_status(config.adapter)
    mapping_ready = bool(mapped_summary.iloc[0]["ready"]) if not mapped_summary.empty else False
    mapping_failures = int((~mapped_checks["passed"].astype(bool)).sum()) if not mapped_checks.empty else 0
    reviewed_schema = schema_status != "placeholder_normalized_pending_vendor_schema"
    mapping_failure_reason = _mapping_failure_reason(mapped_summary)
    return pd.DataFrame(
        [
            _check(
                "broker_orders_nonempty",
                len(broker_orders),
                ">=",
                1,
                len(broker_orders) > 0,
                "broker_orders.csv is empty",
            ),
            _check("mapping_ready", mapping_failures, "==", 0, mapping_ready, mapping_failure_reason),
            _check(
                "schema_reviewed",
                schema_status,
                "!=",
                "placeholder",
                reviewed_schema or not config.require_reviewed_schema,
                "adapter schema is still a placeholder; review vendor sample before live upload",
            ),
        ]
    )


def _summary(orders: pd.DataFrame, checks: pd.DataFrame, config: OrderUploadPackConfig) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 0
    schema_status = adapter_schema_status(config.adapter)
    recommendation = "review_vendor_schema"
    if ready and schema_status == "native_normalized":
        recommendation = "internal_upload_ready"
    elif ready:
        recommendation = "dry_run_or_paper_review"
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": config.adapter,
                "adapter_schema_status": schema_status,
                "orders": int(len(orders)),
                "target_columns": int(len(orders.columns)),
                "lifecycle_orders": _lifecycle_order_count(orders),
                "replace_orders": _replace_order_count(orders),
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "output_file": config.output_filename,
                "mapping_file": config.mapping_filename,
                "recommendation": recommendation,
            }
        ]
    )


def _mapping_failure_reason(mapped_summary: pd.DataFrame) -> str:
    fallback = "built-in upload mapping has failures"
    if mapped_summary.empty:
        return fallback
    row = mapped_summary.iloc[0]
    blocker = _clean(row.get("primary_blocker_check", ""))
    reason = _clean(row.get("primary_blocker_reason", "")) or _clean(row.get("first_failed_reason", ""))
    if blocker and reason:
        return f"{blocker}: {reason}"
    return reason or fallback


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    failed_mask = ~checks["passed"].map(_to_bool)
    return checks.loc[failed_mask].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    return _check_value(row, "check")


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _broker_orders_path(export_path: str | Path) -> Path:
    path = Path(export_path)
    if path.is_dir():
        path = path / "broker_orders.csv"
    if not path.exists():
        raise FileNotFoundError(f"broker order export not found: {path}")
    return path


def _validate_config(config: OrderUploadPackConfig) -> None:
    get_adapter(config.adapter)
    if not str(config.product).strip():
        raise ValueError("product must not be blank")
    if not str(config.exchange).strip():
        raise ValueError("exchange must not be blank")
    for attr in ("output_filename", "mapping_filename"):
        value = str(getattr(config, attr))
        if not value or Path(value).name != value:
            raise ValueError(f"{attr} must be a file name without directories")


def _lifecycle_order_count(orders: pd.DataFrame) -> int:
    if "lifecycle_action" not in orders.columns:
        return 0
    values = orders["lifecycle_action"].astype("string").str.strip()
    return int(values.ne("").fillna(False).sum())


def _replace_order_count(orders: pd.DataFrame) -> int:
    if "lifecycle_action" not in orders.columns:
        return 0
    values = orders["lifecycle_action"].astype("string").str.strip().str.lower()
    return int(values.eq("replace").fillna(False).sum())


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


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
