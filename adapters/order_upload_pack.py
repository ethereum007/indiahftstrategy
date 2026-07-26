from __future__ import annotations

import json
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
from adapters.orders import read_order_csv
from reports.manifest import write_experiment_manifest


TEMPLATE_COLUMNS = [*MAPPING_COLUMNS, "template_status", "notes"]


@dataclass(frozen=True)
class OrderUploadPackConfig:
    adapter: str = "arrow_money"
    product: str = "MIS"
    exchange: str = "NFO"
    require_reviewed_schema: bool = True
    require_instrument_resolution: bool = False
    require_broker_instrument_token: bool = True
    output_filename: str = "broker_upload_orders.csv"
    mapping_filename: str = "broker_upload_mapping.csv"


@dataclass(frozen=True)
class OrderUploadPackReport:
    orders: pd.DataFrame
    mapping: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    schema: pd.DataFrame
    contract_identity: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

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
    contract_identity = _contract_identity(
        broker_orders,
        mapped.orders,
        config,
    )
    checks = _checks(
        broker_orders,
        mapped.summary,
        mapped.checks,
        contract_identity,
        config,
    )
    summary = _summary(
        mapped.orders,
        checks,
        contract_identity,
        config,
    )
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, action_queue)
    return OrderUploadPackReport(
        orders=mapped.orders,
        mapping=mapping,
        checks=checks,
        summary=summary,
        schema=mapped.schema,
        contract_identity=contract_identity,
        action_queue=action_queue,
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
    report = build_order_upload_pack(
        read_order_csv(orders_file),
        config=config,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.mapping.to_csv(out / config.mapping_filename, index=False)
    report.checks.to_csv(out / "broker_upload_checks.csv", index=False)
    report.summary.to_csv(out / "broker_upload_summary.csv", index=False)
    report.schema.to_csv(out / "broker_upload_schema.csv", index=False)
    report.contract_identity.to_csv(
        out / "broker_upload_contract_identity.csv",
        index=False,
    )
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.checks)
    )
    action_queue.to_csv(out / "broker_upload_action_queue.csv", index=False)
    (out / "broker_upload_config.json").write_text(
        json.dumps(
            _config(report.summary.iloc[0], action_queue, config, orders_file),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "broker_upload_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="order_upload_pack",
        parameters={"config": asdict(config)},
        inputs={"broker_orders": orders_file},
    )
    return OrderUploadPackReport(
        report.orders,
        report.mapping,
        report.checks,
        report.summary,
        report.schema,
        report.contract_identity,
        out,
        action_queue,
    )


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
    contract_identity: pd.DataFrame,
    config: OrderUploadPackConfig,
) -> pd.DataFrame:
    schema_status = adapter_schema_status(config.adapter)
    mapping_ready = bool(mapped_summary.iloc[0]["ready"]) if not mapped_summary.empty else False
    mapping_failures = int((~mapped_checks["passed"].astype(bool)).sum()) if not mapped_checks.empty else 0
    reviewed_schema = schema_status != "placeholder_normalized_pending_vendor_schema"
    mapping_failure_reason = _mapping_failure_reason(mapped_summary)
    checks = [
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
    resolution_provided = _instrument_resolution_provided(contract_identity)
    if config.require_instrument_resolution or resolution_provided:
        checks.extend(
            _instrument_resolution_checks(
                contract_identity,
                required=config.require_instrument_resolution,
                require_token=config.require_broker_instrument_token,
            )
        )
    return pd.DataFrame(checks)


def _summary(
    orders: pd.DataFrame,
    checks: pd.DataFrame,
    contract_identity: pd.DataFrame,
    config: OrderUploadPackConfig,
) -> pd.DataFrame:
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
                "instrument_resolution_required": bool(
                    config.require_instrument_resolution
                ),
                "instrument_resolution_provided": _instrument_resolution_provided(
                    contract_identity
                ),
                "instrument_resolution_ready": _instrument_resolution_checks_passed(
                    checks
                ),
                "instrument_resolution_orders": _nonblank_count(
                    contract_identity,
                    "instrument_resolution_status",
                ),
                "broker_instrument_token_orders": _nonblank_count(
                    contract_identity,
                    "broker_instrument_token",
                ),
                "upload_identity_match_orders": int(
                    contract_identity["upload_identity_matches"]
                    .map(_to_bool)
                    .sum()
                )
                if not contract_identity.empty
                else 0,
                "contract_identity_file": "broker_upload_contract_identity.csv",
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


def _contract_identity(
    broker_orders: pd.DataFrame,
    upload_orders: pd.DataFrame,
    config: OrderUploadPackConfig,
) -> pd.DataFrame:
    source = broker_orders.copy().reset_index(drop=True)
    upload = upload_orders.copy().reset_index(drop=True)
    upload_column = {
        "arrow_money": "tradingsymbol",
        "irage": "symbol",
        "normalized": "instrument_id",
    }[config.adapter]
    upload_ids = _text_column(upload, upload_column).reindex(
        source.index,
        fill_value="",
    )
    broker_ids = _text_column(source, "instrument_id")
    statuses = _text_column(
        source,
        "instrument_resolution_status",
    ).str.lower()
    methods = _text_column(source, "instrument_resolution_method")
    research_ids = _text_column(source, "research_instrument_id")
    tokens = _text_column(source, "broker_instrument_token")
    upload_matches = (
        broker_ids.ne("")
        & upload_ids.ne("")
        & broker_ids.eq(upload_ids)
    )
    row_ready = (
        statuses.eq("resolved")
        & methods.ne("")
        & research_ids.ne("")
        & upload_matches
    )
    if config.require_broker_instrument_token:
        row_ready &= tokens.ne("")
    return pd.DataFrame(
        {
            "row_number": source.index.astype(int),
            "broker_order_id": _text_column(
                source,
                "broker_order_id",
            ),
            "client_order_id": _text_column(
                source,
                "client_order_id",
            ),
            "leg_group_id": _text_column(source, "leg_group_id"),
            "leg_role": _text_column(source, "leg_role"),
            "leg_index": source.get(
                "leg_index",
                pd.Series(index=source.index, dtype=float),
            ),
            "leg_count": source.get(
                "leg_count",
                pd.Series(index=source.index, dtype=float),
            ),
            "research_instrument_id": research_ids,
            "broker_instrument_id": broker_ids,
            "broker_instrument_token": tokens,
            "instrument_resolution_method": methods,
            "instrument_resolution_status": statuses,
            "upload_instrument_column": upload_column,
            "upload_instrument_id": upload_ids,
            "upload_identity_matches": upload_matches.astype(bool),
            "resolution_row_ready": row_ready.astype(bool),
        }
    )


def _instrument_resolution_checks(
    contract_identity: pd.DataFrame,
    *,
    required: bool,
    require_token: bool,
) -> list[dict[str, Any]]:
    order_count = int(len(contract_identity))
    provided = _instrument_resolution_provided(contract_identity)
    statuses = _text_column(
        contract_identity,
        "instrument_resolution_status",
    ).str.lower()
    methods = _text_column(
        contract_identity,
        "instrument_resolution_method",
    )
    research_ids = _text_column(
        contract_identity,
        "research_instrument_id",
    )
    tokens = _text_column(
        contract_identity,
        "broker_instrument_token",
    )
    upload_matches = contract_identity.get(
        "upload_identity_matches",
        pd.Series(False, index=contract_identity.index),
    ).map(_to_bool)
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
            "one or more upload orders are not marked as broker-resolved",
        ),
        _check(
            "instrument_resolution_method_complete",
            int(methods.ne("").sum()),
            "==",
            order_count,
            bool(order_count > 0 and methods.ne("").all()),
            "one or more upload orders lost the instrument resolution method",
        ),
        _check(
            "research_instrument_id_complete",
            int(research_ids.ne("").sum()),
            "==",
            order_count,
            bool(order_count > 0 and research_ids.ne("").all()),
            "one or more upload orders lost the research instrument ID",
        ),
        _check(
            "upload_instrument_identity_matches",
            int(upload_matches.sum()),
            "==",
            order_count,
            bool(order_count > 0 and upload_matches.all()),
            "the broker upload symbol does not match the resolved broker order symbol",
        ),
    ]
    if require_token:
        checks.append(
            _check(
                "broker_instrument_token_complete",
                int(tokens.ne("").sum()),
                "==",
                order_count,
                bool(order_count > 0 and tokens.ne("").all()),
                "one or more upload orders lost the broker instrument token",
            )
        )
    return checks


def _instrument_resolution_provided(
    contract_identity: pd.DataFrame,
) -> bool:
    return any(
        _text_column(contract_identity, column).ne("").any()
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
        (
            "instrument_resolution_",
            "research_instrument_",
            "broker_instrument_",
            "upload_instrument_",
        )
    )
    return bool(
        mask.any()
        and checks.loc[mask, "passed"].map(_to_bool).all()
    )


def _nonblank_count(frame: pd.DataFrame, column: str) -> int:
    return int(_text_column(frame, column).ne("").sum())


def _text_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            [""] * len(frame),
            index=frame.index,
            dtype="object",
        )
    return (
        frame[column]
        .astype("string")
        .fillna("")
        .str.strip()
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "adapter",
    "check",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    blocked = int((statuses == "blocked").sum()) if not statuses.empty else 0
    ready = int((statuses == "ready").sum()) if not statuses.empty else 0
    review = int((statuses == "review").sum()) if not statuses.empty else 0
    next_gate = _first_action_value(action_queue, "next_gate")
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = ready
    out["blocked_action_count"] = blocked
    out["review_action_count"] = review
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(summary_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed_rows = _failed_check_rows(checks)
    for _, row in failed_rows.iterrows():
        check = _check_name(row)
        rows.append(
            _action_row(
                source="broker_upload_checks",
                component=_component(check),
                adapter=_text(summary_row.get("adapter")),
                check=check,
                actual=_check_value(row, "value"),
                operator=_check_value(row, "operator"),
                expected=_check_value(row, "threshold"),
                next_gate=_next_gate(check),
                reason=_check_reason(row),
                recommendation=_recommendation(check),
            )
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    source: str,
    component: str,
    adapter: str,
    check: str,
    actual: object,
    operator: str,
    expected: object,
    next_gate: str,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    return {
        "queue_status": "blocked",
        "source": source,
        "component": component,
        "adapter": adapter,
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _config(
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    config: OrderUploadPackConfig,
    orders_file: Path,
) -> dict[str, Any]:
    primary_action = _first_action_record(action_queue)
    return {
        "schema_version": 1,
        "ready": _to_bool(summary_row.get("ready")),
        "adapter": _text(summary_row.get("adapter")),
        "adapter_schema_status": _text(summary_row.get("adapter_schema_status")),
        "inputs": {"broker_orders": str(orders_file)},
        "upload": {
            "output_file": _text(summary_row.get("output_file")),
            "mapping_file": _text(summary_row.get("mapping_file")),
            "orders": _int(summary_row.get("orders")),
            "target_columns": _int(summary_row.get("target_columns")),
            "lifecycle_orders": _int(summary_row.get("lifecycle_orders")),
            "replace_orders": _int(summary_row.get("replace_orders")),
            "instrument_resolution_required": bool(
                config.require_instrument_resolution
            ),
            "require_broker_instrument_token": bool(
                config.require_broker_instrument_token
            ),
            "instrument_resolution_provided": _to_bool(
                summary_row.get("instrument_resolution_provided")
            ),
            "instrument_resolution_ready": _to_bool(
                summary_row.get("instrument_resolution_ready")
            ),
            "instrument_resolution_orders": _int(
                summary_row.get("instrument_resolution_orders")
            ),
            "broker_instrument_token_orders": _int(
                summary_row.get("broker_instrument_token_orders")
            ),
            "upload_identity_match_orders": _int(
                summary_row.get("upload_identity_match_orders")
            ),
            "contract_identity_file": _text(
                summary_row.get("contract_identity_file")
            ),
            "product": config.product,
            "exchange": config.exchange,
            "require_reviewed_schema": bool(config.require_reviewed_schema),
        },
        "failed_check_count": _int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _text(summary_row.get("primary_blocker_check")),
            "value": _text(summary_row.get("primary_blocker_value")),
            "operator": _text(summary_row.get("primary_blocker_operator")),
            "threshold": _text(summary_row.get("primary_blocker_threshold")),
            "reason": _text(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int(summary_row.get("action_queue_count")),
        "ready_action_count": _int(summary_row.get("ready_action_count")),
        "blocked_action_count": _int(summary_row.get("blocked_action_count")),
        "review_action_count": _int(summary_row.get("review_action_count")),
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(summary_row.get("primary_action_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "recommendation": _text(summary_row.get("recommendation")),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready")) else "no"
    lines = [
        "# Broker Upload Pack Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Adapter: {_text(summary_row.get('adapter'))}",
        f"- Schema status: {_text(summary_row.get('adapter_schema_status'))}",
        f"- Orders: {_int(summary_row.get('orders'))}",
        f"- Target columns: {_int(summary_row.get('target_columns'))}",
        f"- Lifecycle orders: {_int(summary_row.get('lifecycle_orders'))}",
        f"- Replace orders: {_int(summary_row.get('replace_orders'))}",
        f"- Instrument resolution required: {'yes' if _to_bool(summary_row.get('instrument_resolution_required')) else 'no'}",
        f"- Instrument resolution provided: {'yes' if _to_bool(summary_row.get('instrument_resolution_provided')) else 'no'}",
        f"- Instrument resolution ready: {'yes' if _to_bool(summary_row.get('instrument_resolution_ready')) else 'no'}",
        f"- Broker token orders: {_int(summary_row.get('broker_instrument_token_orders'))}",
        f"- Upload identity matches: {_int(summary_row.get('upload_identity_match_orders'))}/{_int(summary_row.get('orders'))}",
        f"- Contract identity sidecar: {_code(summary_row.get('contract_identity_file'))}",
        f"- Failed checks: {_int(summary_row.get('failed_check_count'))}",
        f"- Blocked actions: {_int(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No broker-upload actions."
    rows = [
        "| priority | status | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _text(item.get("priority")),
                    _text(item.get("queue_status")),
                    _text(item.get("check")),
                    _text(item.get("actual")),
                    _text(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _component(check: str) -> str:
    if check.startswith(
        (
            "instrument_resolution_",
            "research_instrument_",
            "broker_instrument_",
            "upload_instrument_",
        )
    ):
        return "instrument_resolution"
    if check == "schema_reviewed":
        return "schema_review"
    if check == "mapping_ready":
        return "mapping"
    if check == "broker_orders_nonempty":
        return "broker_orders"
    return "upload_pack"


def _recommendation(check: str) -> str:
    if _component(check) == "instrument_resolution":
        return "rerun_broker_instrument_resolution_and_order_export"
    if check == "schema_reviewed":
        return "review_real_broker_upload_schema_or_allow_placeholder_for_dry_run"
    if check == "mapping_ready":
        return "fix_built_in_upload_mapping_or_broker_order_export"
    if check == "broker_orders_nonempty":
        return "rerun_broker_order_export_with_accepted_orders"
    return "repair_broker_upload_pack"


def _next_gate(check: str) -> str:
    if _component(check) == "instrument_resolution":
        return "resolve-broker-instruments"
    return "pack-broker-upload"


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


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _text(action_queue.iloc[0].get(column))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _split_items(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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
