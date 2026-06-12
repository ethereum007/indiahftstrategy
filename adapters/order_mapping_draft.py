from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from adapters.mapped_order_export import MAPPING_COLUMNS
from reports.manifest import write_experiment_manifest


DRAFT_COLUMNS = [
    *MAPPING_COLUMNS,
    "confidence",
    "status",
    "notes",
]


@dataclass(frozen=True)
class OrderMappingDraftConfig:
    adapter: str = "normalized"
    output_filename: str = "order_mapping_draft.csv"
    required_columns: tuple[str, ...] = ()
    optional_columns: tuple[str, ...] = ()
    default_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderMappingDraftReport:
    mapping: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def draft_order_mapping(
    broker_orders: pd.DataFrame,
    sample_columns: list[str],
    *,
    config: OrderMappingDraftConfig | None = None,
) -> OrderMappingDraftReport:
    config = config or OrderMappingDraftConfig()
    _validate_config(config)
    targets = [str(column) for column in sample_columns]
    if not targets:
        raise ValueError("vendor order sample has no columns")
    _validate_requested_columns(targets, config)

    source_columns = [str(column) for column in broker_orders.columns]
    source_lookup = _key_lookup(source_columns)
    defaults = {_key(column): str(value) for column, value in config.default_values.items()}
    required_keys = {_key(column) for column in config.required_columns}
    optional_keys = {_key(column) for column in config.optional_columns}

    mapping_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    for target in targets:
        required = _is_required(target, required_keys, optional_keys)
        suggestion = _suggest_mapping(target, source_lookup, defaults)
        source_column = suggestion["source_column"]
        default_value = suggestion["default_value"]
        source_present = bool(source_column and source_column in source_columns)
        default_present = bool(default_value)
        mapped = source_present or default_present
        passed = mapped or not required
        status = _status(required, source_present, default_present)
        notes = _notes(required, passed, suggestion["confidence"], source_column, default_value)
        mapping_rows.append(
            {
                "target_column": target,
                "source_column": source_column,
                "default_value": default_value,
                "required": bool(required),
                "transform": suggestion["transform"],
                "confidence": suggestion["confidence"],
                "status": status,
                "notes": notes,
            }
        )
        check_rows.append(
            {
                "target_column": target,
                "required": bool(required),
                "source_column": source_column,
                "source_present": source_present,
                "default_present": default_present,
                "mapped": mapped,
                "passed": passed,
                "reason": "" if passed else "required vendor column is not mapped to a source or default",
            }
        )

    mapping = pd.DataFrame(mapping_rows, columns=DRAFT_COLUMNS)
    checks = pd.DataFrame(check_rows)
    summary = _summary(mapping, checks, config)
    return OrderMappingDraftReport(mapping=mapping, checks=checks, summary=summary)


def write_order_mapping_draft(
    export_path: str | Path,
    sample_path: str | Path,
    *,
    output_dir: str | Path,
    config: OrderMappingDraftConfig | None = None,
) -> OrderMappingDraftReport:
    config = config or OrderMappingDraftConfig()
    _validate_config(config)
    orders_file = _broker_orders_path(export_path)
    sample_file = Path(sample_path)
    if not sample_file.exists():
        raise FileNotFoundError(f"vendor order sample not found: {sample_file}")

    broker_orders = pd.read_csv(orders_file)
    sample = pd.read_csv(sample_file, nrows=0)
    report = draft_order_mapping(broker_orders, list(sample.columns), config=config)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.mapping.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "order_mapping_draft_checks.csv", index=False)
    report.summary.to_csv(out / "order_mapping_draft_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="order_mapping_draft",
        parameters={"config": asdict(config)},
        inputs={"broker_orders": orders_file, "sample": sample_file},
    )
    return OrderMappingDraftReport(report.mapping, report.checks, report.summary, out)


def _suggest_mapping(target: str, source_lookup: dict[str, str], defaults: dict[str, str]) -> dict[str, str]:
    target_key = _key(target)
    default_value = defaults.get(target_key, "")
    if default_value:
        return {
            "source_column": "",
            "default_value": default_value,
            "transform": "identity",
            "confidence": "manual_default",
        }

    alias = _alias_suggestion(target_key, source_lookup)
    if alias is not None:
        return alias

    source_column = source_lookup.get(target_key, "")
    if source_column:
        return {
            "source_column": source_column,
            "default_value": "",
            "transform": _transform_for_source(source_column, target_key),
            "confidence": "exact",
        }

    return {
        "source_column": "",
        "default_value": "",
        "transform": "identity",
        "confidence": "none",
    }


def _alias_suggestion(target_key: str, source_lookup: dict[str, str]) -> dict[str, str] | None:
    aliases = {
        "symbol": [("instrument_id", "string")],
        "tradingsymbol": [("instrument_id", "string")],
        "tradingsymbolname": [("instrument_id", "string")],
        "instrument": [("instrument_id", "string")],
        "instrumentid": [("instrument_id", "string")],
        "security": [("instrument_id", "string")],
        "securityid": [("instrument_id", "string")],
        "contract": [("instrument_id", "string")],
        "transactiontype": [("side", "side_text")],
        "orderside": [("side", "side_text")],
        "buysell": [("side", "side_text")],
        "buysellindicator": [("side", "side_text")],
        "action": [("side", "side_text")],
        "side": [("side", "side_text")],
        "quantity": [("qty", "int")],
        "orderquantity": [("qty", "int")],
        "orderqty": [("qty", "int")],
        "qty": [("qty", "int")],
        "limitprice": [("price", "float")],
        "orderprice": [("price", "float")],
        "price": [("price", "float")],
        "validity": [("time_in_force", "uppercase")],
        "timeinforce": [("time_in_force", "uppercase")],
        "tif": [("time_in_force", "uppercase")],
        "ordertype": [("order_type", "uppercase")],
        "type": [("order_type", "uppercase")],
        "clientorderid": [("client_order_id", "string")],
        "clientid": [("client_order_id", "string")],
        "clordid": [("client_order_id", "string")],
        "tag": [("client_order_id", "string")],
        "remarks": [("client_order_id", "string")],
    }
    for source_name, transform in aliases.get(target_key, []):
        source_column = source_lookup.get(_key(source_name), "")
        if source_column:
            return {
                "source_column": source_column,
                "default_value": "",
                "transform": transform,
                "confidence": "alias",
            }
    return None


def _transform_for_source(source_column: str, target_key: str) -> str:
    source_key = _key(source_column)
    if source_key in {"qty", "quantity", "orderqty", "orderquantity"}:
        return "int"
    if source_key in {"price", "limitprice", "orderprice"}:
        return "float"
    if source_key == "side":
        return "side_text" if target_key != "sidesigned" else "side_signed"
    if source_key == "sidetext":
        return "uppercase"
    if source_key in {"ordertype", "timeinforce", "validity", "tif"}:
        return "uppercase"
    if source_key in {"instrumentid", "clientorderid", "brokerorderid", "launchorderid"}:
        return "string"
    return "identity"


def _summary(
    mapping: pd.DataFrame,
    checks: pd.DataFrame,
    config: OrderMappingDraftConfig,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    required = int(checks["required"].astype(bool).sum()) if not checks.empty else 0
    mapped_required = int((checks["required"].astype(bool) & checks["mapped"].astype(bool)).sum())
    defaulted = int((checks["default_present"].astype(bool)).sum()) if not checks.empty else 0
    mapped = int((checks["mapped"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": bool(len(mapping) > 0 and failed == 0),
                "adapter": config.adapter,
                "adapter_schema_status": adapter_schema_status(config.adapter),
                "vendor_columns": int(len(mapping)),
                "required_columns": required,
                "mapped_columns": mapped,
                "mapped_required_columns": mapped_required,
                "defaulted_columns": defaulted,
                "unmapped_required_columns": failed,
                "output_file": config.output_filename,
            }
        ]
    )


def _is_required(target: str, required_keys: set[str], optional_keys: set[str]) -> bool:
    target_key = _key(target)
    if target_key in optional_keys:
        return False
    if required_keys:
        return target_key in required_keys
    return True


def _status(required: bool, source_present: bool, default_present: bool) -> str:
    if source_present:
        return "mapped"
    if default_present:
        return "defaulted"
    return "unmapped_required" if required else "unmapped_optional"


def _notes(
    required: bool,
    passed: bool,
    confidence: str,
    source_column: str,
    default_value: str,
) -> str:
    if not passed:
        return "review vendor schema and supply source_column or default_value before mapping export"
    if default_value:
        return "manual default supplied; verify against vendor order-entry semantics"
    if source_column and confidence in {"alias", "exact"}:
        return "suggested mapping; review before submitting to a broker or paper adapter"
    if not required:
        return "optional vendor column left blank"
    return ""


def _validate_config(config: OrderMappingDraftConfig) -> None:
    get_adapter(config.adapter)
    output_name = Path(config.output_filename)
    if not config.output_filename or output_name.name != config.output_filename:
        raise ValueError("output_filename must be a file name without directories")
    overlap = {_key(column) for column in config.required_columns} & {
        _key(column) for column in config.optional_columns
    }
    if overlap:
        raise ValueError(f"columns cannot be both required and optional: {sorted(overlap)}")
    for target in config.default_values:
        if not str(target).strip():
            raise ValueError("default_values contains a blank target column")


def _validate_requested_columns(targets: list[str], config: OrderMappingDraftConfig) -> None:
    target_keys = {_key(column) for column in targets}
    requested = {
        *_requested_column_rows(config.required_columns, "required"),
        *_requested_column_rows(config.optional_columns, "optional"),
        *_requested_column_rows(config.default_values.keys(), "default"),
    }
    missing = [f"{kind}:{column}" for kind, column in requested if _key(column) not in target_keys]
    if missing:
        raise ValueError(f"requested mapping columns are not in vendor sample: {missing}")


def _requested_column_rows(columns: Any, kind: str) -> list[tuple[str, str]]:
    return [(kind, str(column)) for column in columns]


def _broker_orders_path(export_path: str | Path) -> Path:
    path = Path(export_path)
    if path.is_dir():
        path = path / "broker_orders.csv"
    if not path.exists():
        raise FileNotFoundError(f"broker order export not found: {path}")
    return path


def _key_lookup(columns: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for column in columns:
        lookup.setdefault(_key(column), column)
    return lookup


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())
