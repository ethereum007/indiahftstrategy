from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import get_adapter
from reports.manifest import write_experiment_manifest
from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
)


@dataclass(frozen=True)
class BrokerDispatchSendThresholds:
    target_mode: str = "live_dryrun"
    require_dispatch_ready: bool = True
    require_armed_dispatch: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    max_requests: int | None = None


@dataclass(frozen=True)
class BrokerDispatchSendReport:
    requests: pd.DataFrame
    expected_acks: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_dispatch_send_packet(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    dispatch_config: dict[str, Any] | None = None,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    thresholds = thresholds or BrokerDispatchSendThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    dispatch_config = dispatch_config or {}

    summary_row = _dispatch_summary_state(dispatch_summary.iloc[0], dispatch_config)
    requests = _request_rows(summary_row, dispatch_orders)
    expected_acks = _expected_ack_template(requests)
    checks = _checks(summary_row, dispatch_orders, requests, thresholds)
    summary = _summary(summary_row, requests, checks, thresholds)
    config = _config(summary.iloc[0], requests, thresholds, checks)
    return BrokerDispatchSendReport(
        requests=requests,
        expected_acks=expected_acks,
        checks=checks,
        summary=summary,
        config=config,
    )


def write_broker_dispatch_send_packet(
    *,
    dispatch_dir: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    dispatch = Path(dispatch_dir)
    dispatch_config_path = dispatch / "broker_dispatch_config.json"
    dispatch_summary_path = dispatch / "broker_dispatch_summary.csv"
    dispatch_orders_path = dispatch / "broker_dispatch_orders.csv"
    dispatch_manifest_path = dispatch / "manifest.json"
    dispatch_config = (
        json.loads(dispatch_config_path.read_text(encoding="utf-8"))
        if dispatch_config_path.exists()
        else {}
    )
    route_manifest_path = _manifest_input_path(dispatch_manifest_path, "route_enable_manifest")
    cutover_manifest_path = _manifest_input_path(route_manifest_path, "cutover_manifest")
    broker_readiness_config_path = _manifest_input_path(cutover_manifest_path, "broker_readiness_config")
    if broker_readiness_config_path is not None:
        dispatch_config = _with_broker_readiness_config_vendor_market_data_batch(
            dispatch_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=_read_required(dispatch_summary_path, "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch_orders_path, "broker_dispatch_orders"),
        dispatch_config=dispatch_config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.requests.to_csv(out / "broker_dispatch_send_requests.csv", index=False)
    report.expected_acks.to_csv(out / "broker_dispatch_expected_acks.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_send_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_send_summary.csv", index=False)
    (out / "broker_dispatch_send_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_send_packet",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchSendThresholds())},
        inputs=_manifest_inputs(
            dispatch_summary=dispatch_summary_path,
            dispatch_orders=dispatch_orders_path,
            dispatch_config=dispatch_config_path,
            dispatch_manifest=dispatch_manifest_path,
        ),
    )
    return BrokerDispatchSendReport(
        report.requests,
        report.expected_acks,
        report.checks,
        report.summary,
        report.config,
        out,
    )


def _manifest_inputs(**paths: Path) -> dict[str, Path]:
    return {name: path for name, path in paths.items() if path.exists()}


def _request_rows(dispatch_summary: pd.Series, dispatch_orders: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    target_mode = _identity_key(_text(dispatch_summary, "target_mode") or _first_order_text(dispatch_orders, "target_mode"))
    for index, order in dispatch_orders.reset_index(drop=True).iterrows():
        payload, payload_error = _order_payload(order)
        envelope = {
            "adapter": adapter,
            "target_mode": target_mode,
            "dry_run_only": True,
            "submission_enabled": False,
            "dispatch_batch_id": _text(order, "dispatch_batch_id"),
            "dispatch_order_id": _text(order, "dispatch_order_id"),
            "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
            or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "source_order_id": _text(order, "source_order_id"),
            "source_payload_hash": _text(order, "source_payload_hash"),
            "order": payload,
        }
        request_hash = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode("utf-8")).hexdigest()
        rows.append(
            {
                "request_id": f"BDR-{index + 1:06d}-{request_hash[:12]}",
                "dispatch_batch_id": _text(order, "dispatch_batch_id"),
                "dispatch_order_id": _text(order, "dispatch_order_id"),
                "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
                or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
                "source_order_id": _text(order, "source_order_id"),
                "target_mode": target_mode,
                "strategy": _text(order, "strategy") or _text(dispatch_summary, "strategy"),
                "market": _text(order, "market") or _text(dispatch_summary, "market"),
                "scenario_key": _text(order, "scenario_key") or _text(dispatch_summary, "scenario_key"),
                "adapter": adapter,
                "request_action": _text(order, "dispatch_action") or "dry_run_submit",
                "transport": "file_packet",
                "endpoint": f"{adapter}.orders.dry_run_submit",
                "http_method": "POST",
                "submission_enabled": False,
                "dry_run_only": _to_bool(order.get("dry_run_only", False)),
                "idempotency_key": f"IDEMP-{request_hash[:24]}",
                "source_payload_hash": _text(order, "source_payload_hash"),
                "request_payload_hash": request_hash,
                "payload_valid": payload_error == "",
                "payload_error": payload_error,
                "request_payload_json": json.dumps(envelope, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _expected_ack_template(requests: pd.DataFrame) -> pd.DataFrame:
    if requests.empty:
        return pd.DataFrame(
            columns=[
                "dispatch_order_id",
                "source_order_id",
                "request_id",
                "idempotency_key",
                "route_dispatch_roundtrip_batch_id",
                "adapter",
                "target_mode",
                "broker_order_id",
                "ack_status",
                "ack_ts_ns",
                "notes",
            ]
        )
    return pd.DataFrame(
        [
            {
                "dispatch_order_id": row.dispatch_order_id,
                "source_order_id": row.source_order_id,
                "request_id": row.request_id,
                "idempotency_key": row.idempotency_key,
                "route_dispatch_roundtrip_batch_id": row.route_dispatch_roundtrip_batch_id,
                "adapter": row.adapter,
                "target_mode": row.target_mode,
                "broker_order_id": "",
                "ack_status": "",
                "ack_ts_ns": "",
                "notes": "fill from Arrow.money/iRage dry-run acknowledgement log",
            }
            for row in requests.itertuples(index=False)
        ]
    )


def _dispatch_summary_state(row: pd.Series, config: dict[str, Any]) -> pd.Series:
    state = row.copy()
    broker_readiness = config.get("broker_readiness", {}) or {}
    if "adapter_schema_status" in broker_readiness:
        state["broker_schema_status"] = _object_text(
            broker_readiness.get("adapter_schema_status", _text(state, "broker_schema_status"))
        )
    if "schema_reviewed" in broker_readiness:
        state["broker_schema_reviewed"] = _to_bool(
            broker_readiness.get("schema_reviewed", state.get("broker_schema_reviewed", False))
        )
    if "schema_review_mode" in broker_readiness:
        state["broker_schema_review_mode"] = _object_text(
            broker_readiness.get("schema_review_mode", _text(state, "broker_schema_review_mode"))
        )
    route_enable = config.get("route_enable_dispatch_roundtrip", {}) or {}
    if "failed_checks" in route_enable:
        state["route_enable_dispatch_roundtrip_failed_checks"] = int(
            _number_value(
                route_enable.get("failed_checks"),
                _number(state, "route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
        )
    route_readiness = config.get("route_readiness", {}) or {}
    if route_readiness:
        state["route_readiness_required"] = _to_bool(
            route_readiness.get("required", state.get("route_readiness_required", False))
        )
        state["route_readiness_provided"] = _to_bool(
            route_readiness.get("provided", state.get("route_readiness_provided", False))
        )
        state["route_readiness_ready"] = _to_bool(
            route_readiness.get("ready", state.get("route_readiness_ready", False))
        )
        state["route_readiness_strategy"] = _object_text(
            route_readiness.get("strategy", _text(state, "route_readiness_strategy"))
        )
        state["route_readiness_market"] = _object_text(
            route_readiness.get("market", _text(state, "route_readiness_market"))
        )
        state["route_readiness_route_ready_pairs"] = int(
            _number_value(
                route_readiness.get("route_ready_pairs"),
                _number(state, "route_readiness_route_ready_pairs", 0.0),
            )
        )
        state["route_readiness_gap_pairs"] = int(
            _number_value(route_readiness.get("gap_pairs"), _number(state, "route_readiness_gap_pairs", 0.0))
        )
        state["route_readiness_recommendation"] = _object_text(
            route_readiness.get("recommendation", _text(state, "route_readiness_recommendation"))
        )
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    if shadow_broker:
        state["shadow_broker_readiness_sessions"] = int(
            _number_value(
                shadow_broker.get("sessions"),
                _number(state, "shadow_broker_readiness_sessions", 0.0),
            )
        )
        state["shadow_broker_readiness_ready_sessions"] = int(
            _number_value(
                shadow_broker.get("ready_sessions"),
                _number(state, "shadow_broker_readiness_ready_sessions", 0.0),
            )
        )
        state["shadow_broker_adapter"] = _object_text(
            shadow_broker.get("adapter", _text(state, "shadow_broker_adapter"))
        )
        state["shadow_broker_adapter_count"] = int(
            _number_value(
                shadow_broker.get("adapter_count"),
                _number(state, "shadow_broker_adapter_count", 0.0),
            )
        )
        shadow_route = shadow_broker.get("route_readiness", {}) or {}
        state["shadow_broker_route_readiness_sessions"] = int(
            _number_value(
                shadow_route.get("sessions"),
                _number(state, "shadow_broker_route_readiness_sessions", 0.0),
            )
        )
        state["shadow_broker_route_readiness_ready_sessions"] = int(
            _number_value(
                shadow_route.get("ready_sessions"),
                _number(state, "shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        )
        state["shadow_broker_route_readiness_strategy"] = _object_text(
            shadow_route.get("strategy", _text(state, "shadow_broker_route_readiness_strategy"))
        )
        state["shadow_broker_route_readiness_market"] = _object_text(
            shadow_route.get("market", _text(state, "shadow_broker_route_readiness_market"))
        )
        state["shadow_broker_route_readiness_gap_pairs"] = int(
            _number_value(
                shadow_route.get("max_gap_pairs"),
                _number(state, "shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        )
        shadow_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
        state["shadow_broker_dispatch_roundtrip_sessions"] = int(
            _number_value(
                shadow_dispatch.get("sessions"),
                _number(state, "shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        )
        state["shadow_broker_dispatch_roundtrip_ready_sessions"] = int(
            _number_value(
                shadow_dispatch.get("ready_sessions"),
                _number(state, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        )
        state["shadow_broker_dispatch_roundtrip_strategy"] = _object_text(
            shadow_dispatch.get("strategy", _text(state, "shadow_broker_dispatch_roundtrip_strategy"))
        )
        state["shadow_broker_dispatch_roundtrip_market"] = _object_text(
            shadow_dispatch.get("market", _text(state, "shadow_broker_dispatch_roundtrip_market"))
        )
        state["shadow_broker_dispatch_roundtrip_scenario_count"] = int(
            _number_value(
                shadow_dispatch.get("scenario_count"),
                _number(state, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        )
        state["shadow_broker_dispatch_roundtrip_missing_request_acks"] = int(
            _number_value(
                shadow_dispatch.get("max_missing_request_acks"),
                _number(state, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        )
        state["shadow_broker_dispatch_roundtrip_rejected_orders"] = int(
            _number_value(
                shadow_dispatch.get("max_rejected_orders"),
                _number(state, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        )
        state["shadow_broker_dispatch_roundtrip_unmatched_acks"] = int(
            _number_value(
                shadow_dispatch.get("max_unmatched_acks"),
                _number(state, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        )
        shadow_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
        state["shadow_broker_route_dispatch_roundtrip_sessions"] = int(
            _number_value(
                shadow_route_dispatch.get("sessions"),
                _number(state, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        )
        state["shadow_broker_route_dispatch_roundtrip_ready_sessions"] = int(
            _number_value(
                shadow_route_dispatch.get("ready_sessions"),
                _number(state, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        )
        state["shadow_broker_route_dispatch_roundtrip_strategy"] = _object_text(
            shadow_route_dispatch.get("strategy", _text(state, "shadow_broker_route_dispatch_roundtrip_strategy"))
        )
        state["shadow_broker_route_dispatch_roundtrip_market"] = _object_text(
            shadow_route_dispatch.get("market", _text(state, "shadow_broker_route_dispatch_roundtrip_market"))
        )
        state["shadow_broker_route_dispatch_roundtrip_scenario_count"] = int(
            _number_value(
                shadow_route_dispatch.get("scenario_count"),
                _number(state, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        )
    route_broker_shadow = config.get("route_broker_shadow_broker_readiness", {}) or {}
    if route_broker_shadow:
        _apply_shadow_broker_readiness_config(
            state,
            route_broker_shadow,
            field_prefix="route_broker_shadow_broker",
        )
    (
        broker_vendor_market_data_batch,
        broker_vendor_market_data_batch_prefix,
    ) = _broker_vendor_market_data_batch_source(config)
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            broker_vendor_market_data_batch,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            fallback_prefix=broker_vendor_market_data_batch_prefix,
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix=broker_vendor_market_data_batch_prefix,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    vendor_market_data_batch = config.get("route_vendor_market_data_batch", {}) or {}
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            vendor_market_data_batch,
            field_prefix="dispatch_vendor_market_data_batch",
            fallback_prefix="route_vendor_market_data_batch",
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix="route_vendor_market_data_batch",
            field_prefix="dispatch_vendor_market_data_batch",
        )
    return state


def _broker_vendor_market_data_batch_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        default_source="route_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    dispatch_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = _broker_vendor_market_data_batch_source(dispatch_config)
    if vendor_market_data_batch_source_active(vendor):
        return dispatch_config
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return dispatch_config
    vendor, _source = select_vendor_market_data_batch_source(
        dispatch,
        (
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    if not vendor_market_data_batch_source_active(vendor):
        return dispatch_config
    out = dict(dispatch_config)
    out["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(vendor)
    return out


def _manifest_input_path(manifest_path: Path | None, input_name: str) -> Path | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path if path.exists() else None


def _apply_vendor_market_data_batch_config(
    state: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str,
    fallback_prefix: str,
) -> None:
    comparison = vendor.get("comparison", {}) or {}
    state[f"{field_prefix}_provided"] = _to_bool(
        vendor.get("provided", state.get(f"{fallback_prefix}_provided", False))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        vendor.get("ready", state.get(f"{fallback_prefix}_ready", False))
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        vendor.get("adapter", state.get(f"{fallback_prefix}_adapter", ""))
    )
    state[f"{field_prefix}_kind"] = _object_text(vendor.get("kind", state.get(f"{fallback_prefix}_kind", "")))
    state[f"{field_prefix}_manifest_run_type"] = _identity_key(
        vendor.get("manifest_run_type", state.get(f"{fallback_prefix}_manifest_run_type", ""))
    )
    state[f"{field_prefix}_market"] = _object_text(
        vendor.get("market", state.get(f"{fallback_prefix}_market", ""))
    )
    state[f"{field_prefix}_dataset_count"] = int(
        _number_value(
            vendor.get("dataset_count"),
            _number(state, f"{fallback_prefix}_dataset_count", 0.0),
        )
    )
    state[f"{field_prefix}_ready_datasets"] = int(
        _number_value(
            vendor.get("ready_datasets"),
            _number(state, f"{fallback_prefix}_ready_datasets", 0.0),
        )
    )
    state[f"{field_prefix}_failed_datasets"] = int(
        _number_value(
            vendor.get("failed_datasets"),
            _number(state, f"{fallback_prefix}_failed_datasets", 0.0),
        )
    )
    state[f"{field_prefix}_ready_rate"] = _number_value(
        vendor.get("ready_rate"),
        _number(state, f"{fallback_prefix}_ready_rate", 0.0),
    )
    state[f"{field_prefix}_unique_source_files"] = int(
        _number_value(
            vendor.get("unique_source_files"),
            _number(state, f"{fallback_prefix}_unique_source_files", 0.0),
        )
    )
    state[f"{field_prefix}_unique_header_fingerprints"] = int(
        _number_value(
            vendor.get("unique_header_fingerprints"),
            _number(state, f"{fallback_prefix}_unique_header_fingerprints", 0.0),
        )
    )
    state[f"{field_prefix}_mapping_sources"] = _object_text(
        vendor.get("mapping_sources", state.get(f"{fallback_prefix}_mapping_sources", ""))
    )
    state[f"{field_prefix}_comparison_accepted"] = _to_bool(
        comparison.get("accepted", state.get(f"{fallback_prefix}_comparison_accepted", False))
    )
    state[f"{field_prefix}_comparison_failed_checks"] = int(
        _number_value(
            comparison.get("failed_checks"),
            _number(state, f"{fallback_prefix}_comparison_failed_checks", 0.0),
        )
    )
    datasets = vendor.get("datasets")
    state[f"{field_prefix}_datasets_json"] = (
        json.dumps(_vendor_market_data_batch_datasets(datasets), sort_keys=True)
        if isinstance(datasets, list)
        else _text(state, f"{fallback_prefix}_datasets_json")
    )


def _copy_vendor_market_data_batch_fields(
    state: pd.Series,
    *,
    source_prefix: str,
    field_prefix: str,
) -> None:
    for suffix in (
        "provided",
        "ready",
        "adapter",
        "kind",
        "manifest_run_type",
        "market",
        "dataset_count",
        "ready_datasets",
        "failed_datasets",
        "ready_rate",
        "unique_source_files",
        "unique_header_fingerprints",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        state[f"{field_prefix}_{suffix}"] = state.get(f"{source_prefix}_{suffix}", "")


def _apply_shadow_broker_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
) -> None:
    route = readiness.get("route_readiness", {}) or {}
    dispatch = readiness.get("dispatch_roundtrip", {}) or {}
    route_dispatch = readiness.get("route_dispatch_roundtrip", {}) or {}
    state[f"{field_prefix}_readiness_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{field_prefix}_readiness_provided", False))
    )
    state[f"{field_prefix}_readiness_sessions"] = int(
        _number_value(readiness.get("sessions"), _number(state, f"{field_prefix}_readiness_sessions", 0.0))
    )
    state[f"{field_prefix}_readiness_ready_sessions"] = int(
        _number_value(
            readiness.get("ready_sessions"),
            _number(state, f"{field_prefix}_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        readiness.get("adapter", _text(state, f"{field_prefix}_adapter"))
    )
    state[f"{field_prefix}_adapter_count"] = int(
        _number_value(readiness.get("adapter_count"), _number(state, f"{field_prefix}_adapter_count", 0.0))
    )
    state[f"{field_prefix}_route_readiness_sessions"] = int(
        _number_value(route.get("sessions"), _number(state, f"{field_prefix}_route_readiness_sessions", 0.0))
    )
    state[f"{field_prefix}_route_readiness_ready_sessions"] = int(
        _number_value(
            route.get("ready_sessions"),
            _number(state, f"{field_prefix}_route_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_readiness_strategy"] = _object_text(
        route.get("strategy", _text(state, f"{field_prefix}_route_readiness_strategy"))
    )
    state[f"{field_prefix}_route_readiness_market"] = _object_text(
        route.get("market", _text(state, f"{field_prefix}_route_readiness_market"))
    )
    state[f"{field_prefix}_route_readiness_gap_pairs"] = int(
        _number_value(route.get("max_gap_pairs"), _number(state, f"{field_prefix}_route_readiness_gap_pairs", 0.0))
    )
    state[f"{field_prefix}_dispatch_roundtrip_sessions"] = int(
        _number_value(dispatch.get("sessions"), _number(state, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0))
    )
    state[f"{field_prefix}_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            dispatch.get("ready_sessions"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_strategy"] = _object_text(
        dispatch.get("strategy", _text(state, f"{field_prefix}_dispatch_roundtrip_strategy"))
    )
    state[f"{field_prefix}_dispatch_roundtrip_market"] = _object_text(
        dispatch.get("market", _text(state, f"{field_prefix}_dispatch_roundtrip_market"))
    )
    state[f"{field_prefix}_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            dispatch.get("scenario_count"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_missing_request_acks"] = int(
        _number_value(
            dispatch.get("max_missing_request_acks"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_rejected_orders"] = int(
        _number_value(
            dispatch.get("max_rejected_orders"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_unmatched_acks"] = int(
        _number_value(
            dispatch.get("max_unmatched_acks"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_sessions"] = int(
        _number_value(
            route_dispatch.get("sessions"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            route_dispatch.get("ready_sessions"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_strategy"] = _object_text(
        route_dispatch.get("strategy", _text(state, f"{field_prefix}_route_dispatch_roundtrip_strategy"))
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_market"] = _object_text(
        route_dispatch.get("market", _text(state, f"{field_prefix}_route_dispatch_roundtrip_market"))
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            route_dispatch.get("scenario_count"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0),
        )
    )


def _checks(
    dispatch_summary: pd.Series,
    dispatch_orders: pd.DataFrame,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    request_count = int(len(requests))
    max_requests = thresholds.max_requests if thresholds.max_requests is not None else orders
    summary_ready = _to_bool(dispatch_summary.get("ready", False))
    dispatch_state = _identity_key(dispatch_summary.get("dispatch_state", ""))
    target_mode = _identity_key(dispatch_summary.get("target_mode", ""))
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    adapter_known = _adapter_known(adapter)
    dry_run_only = bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False
    submission_disabled = bool((~requests["submission_enabled"].astype(bool)).all()) if not requests.empty else False
    unique_idempotency = int(requests["idempotency_key"].nunique()) if not requests.empty else 0
    payloads_valid = bool(requests["payload_valid"].astype(bool).all()) if not requests.empty else False
    route_roundtrip_active = _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    )
    route_readiness_required = _route_readiness_required(thresholds, dispatch_summary)
    route_readiness_active = bool(
        route_readiness_required or _to_bool(dispatch_summary.get("route_readiness_provided", False))
    )
    route_enable_failed_checks = int(
        _number(dispatch_summary, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
    )
    route_batch_id = _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
    order_route_batches = _unique_text_values(dispatch_orders, "route_dispatch_roundtrip_batch_id")
    request_route_batches = _unique_text_values(requests, "route_dispatch_roundtrip_batch_id")
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                summary_ready,
                "is",
                True,
                summary_ready or not thresholds.require_dispatch_ready,
                "broker dispatch plan is not ready",
            ),
            _check(
                "dispatch_armed_dry_run",
                dispatch_state,
                "==",
                "armed_dry_run",
                dispatch_state == "armed_dry_run" or not thresholds.require_armed_dispatch,
                "dispatch state is not armed for dry-run sending",
            ),
            _check(
                "target_mode_matches",
                target_mode,
                "==",
                thresholds.target_mode,
                target_mode == thresholds.target_mode,
                "sender packet target mode does not match dispatch target",
            ),
            _check(
                "route_dispatch_roundtrip_provided",
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False))
                or not _dispatch_roundtrip_required(thresholds),
                "sender packet requires dispatch plan with route round-trip proof",
            ),
            _check(
                "route_readiness_provided",
                _to_bool(dispatch_summary.get("route_readiness_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_readiness_provided", False)) or not route_readiness_required,
                "sender packet requires dispatch plan with route-readiness proof",
            ),
            _check("adapter_known", adapter, "in", "known adapters", adapter_known, "dispatch adapter is unknown"),
            _check(
                "request_count_matches_dispatch",
                request_count,
                "==",
                orders,
                request_count == orders,
                "sender packet request count does not match dispatch order count",
            ),
            _check(
                "request_count_within_limit",
                request_count,
                "<=",
                max_requests,
                request_count <= max_requests,
                "sender packet request count exceeds limit",
            ),
            _check(
                "dry_run_only",
                dry_run_only,
                "is",
                True,
                dry_run_only or not thresholds.require_dry_run,
                "sender packet contains non-dry-run requests",
            ),
            _check(
                "submission_disabled",
                submission_disabled,
                "is",
                True,
                submission_disabled,
                "sender packet would enable live submission",
            ),
            _check(
                "unique_idempotency_key",
                unique_idempotency,
                "==",
                request_count,
                unique_idempotency == request_count,
                "sender packet idempotency keys are not unique",
            ),
            _check("payloads_valid", payloads_valid, "is", True, payloads_valid, "dispatch payload JSON is invalid"),
        ]
    )
    if route_readiness_active:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_route_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    ):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_dispatch_roundtrip_checks(dispatch_summary, target_mode)),
                pd.DataFrame(
                    [
                        _check(
                            "route_enable_dispatch_roundtrip_failed_checks",
                            route_enable_failed_checks,
                            "<=",
                            0,
                            route_enable_failed_checks <= 0,
                            "route-enable dispatch round-trip has failed component checks",
                        ),
                        _check(
                            "dispatch_order_route_roundtrip_batch_matches",
                            "|".join(order_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(order_route_batches) == 1
                                and order_route_batches[0] == route_batch_id
                            ),
                            "dispatch order route proof batch ids do not match dispatch summary",
                        ),
                        _check(
                            "request_route_roundtrip_batch_matches",
                            "|".join(request_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(request_route_batches) == 1
                                and request_route_batches[0] == route_batch_id
                            ),
                            "sender request route proof batch ids do not match dispatch summary",
                        ),
                    ]
                )
                if route_roundtrip_active
                else pd.DataFrame(),
            ],
            ignore_index=True,
        )
    if _shadow_broker_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_shadow_broker_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _route_broker_shadow_broker_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_route_broker_shadow_broker_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _vendor_market_data_batch_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_vendor_market_data_batch_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _broker_vendor_market_data_batch_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_broker_vendor_market_data_batch_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    return checks


def _route_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    return [
        _check(
            "route_readiness_ready",
            _to_bool(dispatch_summary.get("route_readiness_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_readiness_ready", False)),
            "dispatch route-readiness proof is not ready",
        ),
        _check(
            "route_readiness_strategy_matches",
            _identity_key(dispatch_summary.get("route_readiness_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get("route_readiness_strategy", ""))
                and strategy
                and _identity_key(dispatch_summary.get("route_readiness_strategy", "")) == strategy
            ),
            "dispatch route-readiness strategy does not match sender strategy",
        ),
        _check(
            "route_readiness_market_matches",
            _identity_key(dispatch_summary.get("route_readiness_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_readiness_market", ""))
                and market
                and _identity_key(dispatch_summary.get("route_readiness_market", "")) == market
            ),
            "dispatch route-readiness market does not match sender market",
        ),
    ]


def _dispatch_roundtrip_checks(dispatch_summary: pd.Series, target_mode: str) -> list[dict[str, object]]:
    strategy = _text(dispatch_summary, "strategy")
    market = _identity_key(dispatch_summary.get("market", ""))
    scenario = _text(dispatch_summary, "scenario_key")
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "dispatch route round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")),
            "==",
            target_mode,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")) == target_mode
            ),
            "dispatch route round-trip target mode does not match sender target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")),
            "==",
            _identity_key(strategy),
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")) == _identity_key(strategy)
            ),
            "dispatch route round-trip strategy does not match sender strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")) == market
            ),
            "dispatch route round-trip market does not match sender market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key"),
            "==",
            scenario,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") and scenario)
            and _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") == scenario,
            "dispatch route round-trip scenario does not match sender scenario",
        ),
        _check(
            "route_dispatch_roundtrip_batch_id_provided",
            _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "is not",
            "",
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_batch_id")),
            "dispatch route round-trip proof batch id is missing",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)) <= 0,
            "dispatch route round-trip has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
            "dispatch route round-trip has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
            "dispatch route round-trip has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(dispatch_summary: pd.Series) -> bool:
    session_columns = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_route_readiness_sessions",
        "shadow_broker_dispatch_roundtrip_sessions",
        "shadow_broker_route_dispatch_roundtrip_sessions",
    )
    return any(int(_number(dispatch_summary, column, 0.0)) > 0 for column in session_columns)


def _shadow_broker_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    adapter = _identity_key(dispatch_summary.get("adapter", ""))
    sessions = int(_number(dispatch_summary, "shadow_broker_readiness_sessions", 0.0))
    if sessions > 0:
        ready_sessions = int(_number(dispatch_summary, "shadow_broker_readiness_ready_sessions", 0.0))
        shadow_adapter = _identity_key(dispatch_summary.get("shadow_broker_adapter", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_readiness_ready",
                    ready_sessions,
                    "==",
                    sessions,
                    ready_sessions == sessions,
                    "dispatch shadow broker-readiness evidence is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_adapter_matches",
                    shadow_adapter,
                    "==",
                    adapter,
                    bool(shadow_adapter and adapter and shadow_adapter == adapter),
                    "dispatch shadow broker adapter does not match sender adapter",
                ),
                _check(
                    "dispatch_shadow_broker_adapter_consistent",
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)) == 1,
                    "dispatch shadow broker adapter identity is missing or mixed",
                ),
            ]
        )
    route_sessions = int(_number(dispatch_summary, "shadow_broker_route_readiness_sessions", 0.0))
    if route_sessions > 0:
        route_strategy = _identity_key(dispatch_summary.get("shadow_broker_route_readiness_strategy", ""))
        route_market = _identity_key(dispatch_summary.get("shadow_broker_route_readiness_market", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_route_readiness_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0)),
                    "==",
                    route_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0))
                    == route_sessions,
                    "dispatch shadow broker route-readiness proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_strategy_matches",
                    route_strategy,
                    "==",
                    strategy,
                    bool(route_strategy and strategy and route_strategy == strategy),
                    "dispatch shadow broker route-readiness strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_market_matches",
                    route_market,
                    "==",
                    market,
                    bool(route_market and market and route_market == market),
                    "dispatch shadow broker route-readiness market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_gap_pairs",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)) <= 0,
                    "dispatch shadow broker route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_sessions", 0.0))
    if dispatch_sessions > 0:
        dispatch_strategy = _identity_key(dispatch_summary.get("shadow_broker_dispatch_roundtrip_strategy", ""))
        dispatch_market = _identity_key(dispatch_summary.get("shadow_broker_dispatch_roundtrip_market", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0))
                    == dispatch_sessions,
                    "dispatch shadow broker dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_strategy_matches",
                    dispatch_strategy,
                    "==",
                    strategy,
                    bool(dispatch_strategy and strategy and dispatch_strategy == strategy),
                    "dispatch shadow broker dispatch round-trip strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_market_matches",
                    dispatch_market,
                    "==",
                    market,
                    bool(dispatch_market and market and dispatch_market == market),
                    "dispatch shadow broker dispatch round-trip market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "dispatch shadow broker dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_missing_request_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0))
                    <= 0,
                    "dispatch shadow broker dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_rejected_orders",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
                    "dispatch shadow broker dispatch round-trip has rejected orders",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_unmatched_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
                    "dispatch shadow broker dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0))
    if route_dispatch_sessions > 0:
        route_dispatch_strategy = _identity_key(
            dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_strategy", "")
        )
        route_dispatch_market = _identity_key(
            dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_market", "")
        )
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    route_dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0))
                    == route_dispatch_sessions,
                    "dispatch shadow broker route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_strategy_matches",
                    route_dispatch_strategy,
                    "==",
                    strategy,
                    bool(route_dispatch_strategy and strategy and route_dispatch_strategy == strategy),
                    "dispatch shadow broker route dispatch round-trip strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_market_matches",
                    route_dispatch_market,
                    "==",
                    market,
                    bool(route_dispatch_market and market and route_dispatch_market == market),
                    "dispatch shadow broker route dispatch round-trip market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "dispatch shadow broker route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _route_broker_shadow_broker_readiness_active(dispatch_summary: pd.Series) -> bool:
    prefix = "route_broker_shadow_broker"
    session_columns = (
        f"{prefix}_readiness_sessions",
        f"{prefix}_route_readiness_sessions",
        f"{prefix}_dispatch_roundtrip_sessions",
        f"{prefix}_route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_readiness_provided", False))
        or any(int(_number(dispatch_summary, column, 0.0)) > 0 for column in session_columns)
    )


def _route_broker_shadow_broker_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    source_prefix = "route_broker_shadow_broker"
    checks = [
        _check(
            "dispatch_broker_shadow_broker_readiness_provided",
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "dispatch broker-readiness shadow broker proof is active but not marked provided",
        )
    ]
    mapped = _shadow_broker_projection(dispatch_summary, source_prefix=source_prefix)
    for check in _shadow_broker_readiness_checks(mapped):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "dispatch_shadow_broker",
            "dispatch_broker_shadow_broker",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "dispatch shadow broker",
                "dispatch broker-readiness shadow broker",
            )
        checks.append(renamed)
    return checks


def _vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "dispatch_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "dispatch_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    return [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "dispatch vendor market-data manifest is not a vendor batch pipeline proof",
        )
    ]


def _broker_vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _broker_vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    return [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "dispatch broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        )
    ]


def _shadow_broker_projection(dispatch_summary: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = dispatch_summary.copy()
    for suffix in (
        "readiness_sessions",
        "readiness_ready_sessions",
        "adapter",
        "adapter_count",
        "route_readiness_sessions",
        "route_readiness_ready_sessions",
        "route_readiness_strategy",
        "route_readiness_market",
        "route_readiness_gap_pairs",
        "dispatch_roundtrip_sessions",
        "dispatch_roundtrip_ready_sessions",
        "dispatch_roundtrip_strategy",
        "dispatch_roundtrip_market",
        "dispatch_roundtrip_scenario_count",
        "dispatch_roundtrip_missing_request_acks",
        "dispatch_roundtrip_rejected_orders",
        "dispatch_roundtrip_unmatched_acks",
        "route_dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_ready_sessions",
        "route_dispatch_roundtrip_strategy",
        "route_dispatch_roundtrip_market",
        "route_dispatch_roundtrip_scenario_count",
    ):
        mapped[f"shadow_broker_{suffix}"] = dispatch_summary.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _prefixed_shadow_broker_summary_fields(dispatch_summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        f"{field_prefix}_readiness_provided": _to_bool(
            dispatch_summary.get(f"{field_prefix}_readiness_provided", False)
        ),
        f"{field_prefix}_readiness_sessions": int(_number(dispatch_summary, f"{field_prefix}_readiness_sessions", 0.0)),
        f"{field_prefix}_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_adapter": _identity_key(dispatch_summary.get(f"{field_prefix}_adapter", "")),
        f"{field_prefix}_adapter_count": int(_number(dispatch_summary, f"{field_prefix}_adapter_count", 0.0)),
        f"{field_prefix}_route_readiness_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_readiness_strategy", "")
        ),
        f"{field_prefix}_route_readiness_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_readiness_market", "")
        ),
        f"{field_prefix}_route_readiness_gap_pairs": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_gap_pairs", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_dispatch_roundtrip_strategy", "")
        ),
        f"{field_prefix}_dispatch_roundtrip_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_dispatch_roundtrip_market", "")
        ),
        f"{field_prefix}_dispatch_roundtrip_scenario_count": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_missing_request_acks": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_rejected_orders": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_unmatched_acks": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_dispatch_roundtrip_strategy", "")
        ),
        f"{field_prefix}_route_dispatch_roundtrip_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_dispatch_roundtrip_market", "")
        ),
        f"{field_prefix}_route_dispatch_roundtrip_scenario_count": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0)
        ),
    }


def _summary(
    dispatch_summary: pd.Series,
    requests: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "request_state": "dry_run_send_packet_ready" if ready else "disabled",
                "target_mode": _identity_key(dispatch_summary.get("target_mode", "")),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "broker_schema_status": _text(dispatch_summary, "broker_schema_status"),
                "broker_schema_reviewed": _to_bool(dispatch_summary.get("broker_schema_reviewed", False)),
                "broker_schema_review_mode": _text(dispatch_summary, "broker_schema_review_mode"),
                "dispatch_batch_id": _text(dispatch_summary, "dispatch_batch_id"),
                "dispatch_orders": int(_number(dispatch_summary, "dispatch_orders", len(requests))),
                "requests": int(len(requests)),
                "route_readiness_required": _route_readiness_required(thresholds, dispatch_summary),
                "route_readiness_provided": _to_bool(dispatch_summary.get("route_readiness_provided", False)),
                "route_readiness_ready": _to_bool(dispatch_summary.get("route_readiness_ready", False)),
                "route_readiness_strategy": _identity_key(dispatch_summary.get("route_readiness_strategy", "")),
                "route_readiness_market": _identity_key(dispatch_summary.get("route_readiness_market", "")),
                "route_readiness_route_ready_pairs": int(
                    _number(dispatch_summary, "route_readiness_route_ready_pairs", 0.0)
                ),
                "route_readiness_gap_pairs": int(_number(dispatch_summary, "route_readiness_gap_pairs", 0.0)),
                "route_readiness_recommendation": _text(dispatch_summary, "route_readiness_recommendation"),
                "shadow_broker_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_readiness_sessions", 0.0)
                ),
                "shadow_broker_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_adapter": _identity_key(dispatch_summary.get("shadow_broker_adapter", "")),
                "shadow_broker_adapter_count": int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)),
                "shadow_broker_route_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_route_readiness_strategy", "")
                ),
                "shadow_broker_route_readiness_market": _identity_key(
                    dispatch_summary.get("shadow_broker_route_readiness_market", "")
                ),
                "shadow_broker_route_readiness_gap_pairs": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("shadow_broker_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)
                ),
                **_prefixed_shadow_broker_summary_fields(
                    dispatch_summary,
                    field_prefix="route_broker_shadow_broker",
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="dispatch_vendor_market_data_batch",
                ),
                "route_dispatch_roundtrip_required": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_required", False)
                ),
                "route_dispatch_roundtrip_provided": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_provided", False)
                ),
                "route_dispatch_roundtrip_ready": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_ready", False)
                ),
                "route_dispatch_roundtrip_target_mode": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")
                ),
                "route_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_strategy", "")
                ),
                "route_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_market", "")
                ),
                "route_dispatch_roundtrip_scenario_key": _text(
                    dispatch_summary, "route_dispatch_roundtrip_scenario_key"
                ),
                "route_dispatch_roundtrip_batch_id": _text(
                    dispatch_summary, "route_dispatch_roundtrip_batch_id"
                ),
                "route_dispatch_roundtrip_requests": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_requests", 0.0)
                ),
                "route_dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_acked_orders", 0.0)
                ),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "route_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "route_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_summary, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                ),
                "dry_run_only": bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False,
                "submission_enabled": False,
                "failed_checks": failed,
                "recommendation": "ready_for_non_submitting_broker_sender_review"
                if ready
                else "keep_broker_sender_disabled",
            }
        ]
    )


def _prefixed_shadow_broker_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_readiness_provided"]),
        "sessions": int(summary[f"{field_prefix}_readiness_sessions"]),
        "ready_sessions": int(summary[f"{field_prefix}_readiness_ready_sessions"]),
        "adapter": _text(summary, f"{field_prefix}_adapter"),
        "adapter_count": int(summary[f"{field_prefix}_adapter_count"]),
        "route_readiness": {
            "sessions": int(summary[f"{field_prefix}_route_readiness_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_route_readiness_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_route_readiness_strategy"),
            "market": _text(summary, f"{field_prefix}_route_readiness_market"),
            "max_gap_pairs": int(summary[f"{field_prefix}_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(summary[f"{field_prefix}_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_dispatch_roundtrip_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_dispatch_roundtrip_strategy"),
            "market": _text(summary, f"{field_prefix}_dispatch_roundtrip_market"),
            "scenario_count": int(summary[f"{field_prefix}_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(summary[f"{field_prefix}_dispatch_roundtrip_missing_request_acks"]),
            "max_rejected_orders": int(summary[f"{field_prefix}_dispatch_roundtrip_rejected_orders"]),
            "max_unmatched_acks": int(summary[f"{field_prefix}_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(summary[f"{field_prefix}_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_route_dispatch_roundtrip_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_route_dispatch_roundtrip_strategy"),
            "market": _text(summary, f"{field_prefix}_route_dispatch_roundtrip_market"),
            "scenario_count": int(summary[f"{field_prefix}_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_summary_fields(dispatch_summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        f"{field_prefix}_provided": _to_bool(dispatch_summary.get(f"{field_prefix}_provided", False)),
        f"{field_prefix}_ready": _to_bool(dispatch_summary.get(f"{field_prefix}_ready", False)),
        f"{field_prefix}_adapter": _identity_key(dispatch_summary.get(f"{field_prefix}_adapter", "")),
        f"{field_prefix}_kind": _text(dispatch_summary, f"{field_prefix}_kind"),
        f"{field_prefix}_manifest_run_type": _identity_key(
            dispatch_summary.get(f"{field_prefix}_manifest_run_type", "")
        ),
        f"{field_prefix}_market": _identity_key(dispatch_summary.get(f"{field_prefix}_market", "")),
        f"{field_prefix}_dataset_count": int(_number(dispatch_summary, f"{field_prefix}_dataset_count", 0.0)),
        f"{field_prefix}_ready_datasets": int(_number(dispatch_summary, f"{field_prefix}_ready_datasets", 0.0)),
        f"{field_prefix}_failed_datasets": int(_number(dispatch_summary, f"{field_prefix}_failed_datasets", 0.0)),
        f"{field_prefix}_ready_rate": _number(dispatch_summary, f"{field_prefix}_ready_rate", 0.0),
        f"{field_prefix}_unique_source_files": int(
            _number(dispatch_summary, f"{field_prefix}_unique_source_files", 0.0)
        ),
        f"{field_prefix}_unique_header_fingerprints": int(
            _number(dispatch_summary, f"{field_prefix}_unique_header_fingerprints", 0.0)
        ),
        f"{field_prefix}_mapping_sources": _text(dispatch_summary, f"{field_prefix}_mapping_sources"),
        f"{field_prefix}_comparison_accepted": _to_bool(
            dispatch_summary.get(f"{field_prefix}_comparison_accepted", False)
        ),
        f"{field_prefix}_comparison_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_comparison_failed_checks", 0.0)
        ),
        f"{field_prefix}_datasets_json": _text(dispatch_summary, f"{field_prefix}_datasets_json"),
    }


def _vendor_market_data_batch_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "adapter": _text(summary, f"{field_prefix}_adapter"),
        "kind": _text(summary, f"{field_prefix}_kind"),
        "manifest_run_type": _text(summary, f"{field_prefix}_manifest_run_type"),
        "market": _text(summary, f"{field_prefix}_market"),
        "dataset_count": int(summary[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(summary[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(summary[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(summary[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(summary[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(summary[f"{field_prefix}_unique_header_fingerprints"]),
        "mapping_sources": _text(summary, f"{field_prefix}_mapping_sources"),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _config(
    summary: pd.Series,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": _to_bool(summary["ready"]),
        "request_state": _text(summary, "request_state"),
        "submission_enabled": False,
        "transport": "file_packet",
        "target_mode": _text(summary, "target_mode"),
        "strategy": _text(summary, "strategy"),
        "market": _text(summary, "market"),
        "scenario_key": _text(summary, "scenario_key"),
        "adapter": _text(summary, "adapter"),
        "broker_readiness": {
            "adapter_schema_status": _text(summary, "broker_schema_status"),
            "schema_reviewed": _to_bool(summary["broker_schema_reviewed"]),
            "schema_review_mode": _text(summary, "broker_schema_review_mode"),
        },
        "dispatch_batch_id": _text(summary, "dispatch_batch_id"),
        "requests": int(summary["requests"]),
        "first_request_id": str(requests.iloc[0]["request_id"]) if not requests.empty else "",
        "last_request_id": str(requests.iloc[-1]["request_id"]) if not requests.empty else "",
        "route_readiness": {
            "required": _to_bool(summary["route_readiness_required"]),
            "provided": _to_bool(summary["route_readiness_provided"]),
            "ready": _to_bool(summary["route_readiness_ready"]),
            "strategy": _text(summary, "route_readiness_strategy"),
            "market": _text(summary, "route_readiness_market"),
            "route_ready_pairs": int(summary["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(summary["route_readiness_gap_pairs"]),
            "recommendation": _text(summary, "route_readiness_recommendation"),
        },
        "shadow_broker_readiness": {
            "provided": int(summary["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(summary["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(summary["shadow_broker_readiness_ready_sessions"]),
            "adapter": _text(summary, "shadow_broker_adapter"),
            "adapter_count": int(summary["shadow_broker_adapter_count"]),
            "route_readiness": {
                "sessions": int(summary["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_route_readiness_strategy"),
                "market": _text(summary, "shadow_broker_route_readiness_market"),
                "max_gap_pairs": int(summary["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_dispatch_roundtrip_strategy"),
                "market": _text(summary, "shadow_broker_dispatch_roundtrip_market"),
                "scenario_count": int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    summary["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(summary["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(summary["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_route_dispatch_roundtrip_strategy"),
                "market": _text(summary, "shadow_broker_route_dispatch_roundtrip_market"),
                "scenario_count": int(summary["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "route_broker_shadow_broker_readiness": _prefixed_shadow_broker_config(
            summary,
            field_prefix="route_broker_shadow_broker",
        ),
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "dispatch_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="dispatch_vendor_market_data_batch",
        ),
        "route_dispatch_roundtrip": {
            "required": _to_bool(summary["route_dispatch_roundtrip_required"]),
            "provided": _to_bool(summary["route_dispatch_roundtrip_provided"]),
            "ready": _to_bool(summary["route_dispatch_roundtrip_ready"]),
            "target_mode": _text(summary, "route_dispatch_roundtrip_target_mode"),
            "strategy": _text(summary, "route_dispatch_roundtrip_strategy"),
            "market": _text(summary, "route_dispatch_roundtrip_market"),
            "scenario_key": _text(summary, "route_dispatch_roundtrip_scenario_key"),
            "dispatch_batch_id": _text(summary, "route_dispatch_roundtrip_batch_id"),
            "requests": int(summary["route_dispatch_roundtrip_requests"]),
            "acked_orders": int(summary["route_dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(summary["route_dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(summary["route_dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(summary["route_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(summary["route_enable_dispatch_roundtrip_failed_checks"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _order_payload(order: pd.Series) -> tuple[dict[str, Any], str]:
    raw = _text(order, "order_payload_json")
    if not raw:
        return {}, "missing order_payload_json"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"invalid order_payload_json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "order_payload_json is not an object"
    return _jsonable_row(payload), ""


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch send input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch send input is empty: {name}")
    return frame


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: BrokerDispatchSendThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: BrokerDispatchSendThresholds, dispatch_summary: pd.Series | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (
            dispatch_summary is not None
            and _to_bool(dispatch_summary.get("route_readiness_required", False))
        )
    )


def _validate_thresholds(thresholds: BrokerDispatchSendThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_requests is not None and thresholds.max_requests <= 0:
        raise ValueError("max_requests must be positive")


def _adapter_known(adapter: str) -> bool:
    try:
        get_adapter(adapter)
    except ValueError:
        return False
    return True


def _first_order_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return str(values.iloc[0]) if not values.empty else ""


def _unique_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(set(values.loc[values != ""]))


def _object_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "armed", "accepted"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _vendor_market_data_batch_datasets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "dataset": _object_text(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": _object_text(item.get("source_file_sha256", "")),
                "source_header_sha256": _object_text(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": _object_text(item.get("mapping_draft_sha256", "")),
                "mapping_source": _object_text(item.get("mapping_source", "")),
            }
        )
    return rows


def _json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }
