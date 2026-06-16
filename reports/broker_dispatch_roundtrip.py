from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
)


@dataclass(frozen=True)
class BrokerDispatchRoundTripThresholds:
    target_mode: str = "live_dryrun"
    require_dispatch_ready: bool = True
    require_send_ready: bool = True
    require_ack_passed: bool = True
    require_identity_match: bool = True
    require_submission_disabled: bool = True
    require_all_requests_acked: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0
    max_missing_request_acks: int = 0
    max_total_failed_component_checks: int = 0


@dataclass(frozen=True)
class BrokerDispatchRoundTripReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_broker_dispatch_roundtrip(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    send_summary: pd.DataFrame,
    send_requests: pd.DataFrame,
    ack_summary: pd.DataFrame,
    acknowledgements: pd.DataFrame,
    dispatch_config: dict[str, Any] | None = None,
    send_config: dict[str, Any] | None = None,
    ack_config: dict[str, Any] | None = None,
    thresholds: BrokerDispatchRoundTripThresholds | None = None,
) -> BrokerDispatchRoundTripReport:
    thresholds = thresholds or BrokerDispatchRoundTripThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    send_summary = _require_nonempty(send_summary, "send_summary")
    send_requests = _require_nonempty(send_requests, "send_requests")
    ack_summary = _require_nonempty(ack_summary, "ack_summary")
    acknowledgements = _require_nonempty(acknowledgements, "acknowledgements")
    dispatch_row = _component_summary_state(dispatch_summary.iloc[0], dispatch_config or {})
    send_row = _component_summary_state(send_summary.iloc[0], send_config or {})
    ack_row = _component_summary_state(ack_summary.iloc[0], ack_config or {})

    orders = _roundtrip_orders(dispatch_orders, send_requests, acknowledgements)
    checks = _checks(
        dispatch_row,
        send_row,
        ack_row,
        dispatch_orders,
        send_requests,
        orders,
        thresholds,
    )
    summary = _summary(
        dispatch_row,
        send_row,
        ack_row,
        orders,
        checks,
        thresholds,
    )
    config = _config(summary.iloc[0], thresholds, checks)
    return BrokerDispatchRoundTripReport(orders=orders, checks=checks, summary=summary, config=config)


def write_broker_dispatch_roundtrip(
    *,
    dispatch_dir: str | Path,
    send_dir: str | Path,
    ack_dir: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchRoundTripThresholds | None = None,
) -> BrokerDispatchRoundTripReport:
    dispatch = Path(dispatch_dir)
    send = Path(send_dir)
    ack = Path(ack_dir)
    dispatch_summary_path = dispatch / "broker_dispatch_summary.csv"
    dispatch_orders_path = dispatch / "broker_dispatch_orders.csv"
    dispatch_config_path = dispatch / "broker_dispatch_config.json"
    dispatch_manifest_path = dispatch / "manifest.json"
    send_summary_path = send / "broker_dispatch_send_summary.csv"
    send_requests_path = send / "broker_dispatch_send_requests.csv"
    send_config_path = send / "broker_dispatch_send_config.json"
    send_manifest_path = send / "manifest.json"
    ack_summary_path = ack / "broker_dispatch_ack_summary.csv"
    acknowledgements_path = ack / "broker_dispatch_acknowledgements.csv"
    ack_config_path = ack / "broker_dispatch_ack_config.json"
    ack_manifest_path = ack / "manifest.json"
    dispatch_config = _read_optional_json(dispatch_config_path)
    send_config = _read_optional_json(send_config_path)
    ack_config = _read_optional_json(ack_config_path)
    send_dispatch_manifest_path = _manifest_input_path(send_manifest_path, "dispatch_manifest")
    ack_dispatch_manifest_path = _manifest_input_path(ack_manifest_path, "dispatch_manifest")
    broker_readiness_config_path = (
        _broker_readiness_config_from_dispatch_manifest(dispatch_manifest_path)
        or _broker_readiness_config_from_dispatch_manifest(send_dispatch_manifest_path)
        or _broker_readiness_config_from_dispatch_manifest(ack_dispatch_manifest_path)
    )
    if broker_readiness_config_path is not None:
        broker_readiness_config = json.loads(broker_readiness_config_path.read_text(encoding="utf-8"))
        dispatch_config = _with_broker_readiness_config_vendor_market_data_batch(
            dispatch_config,
            broker_readiness_config,
            target_key="route_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="route_broker_vendor_data_readiness",
        )
        send_config = _with_broker_readiness_config_vendor_market_data_batch(
            send_config,
            broker_readiness_config,
            target_key="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="dispatch_broker_vendor_data_readiness",
        )
        ack_config = _with_broker_readiness_config_vendor_market_data_batch(
            ack_config,
            broker_readiness_config,
            target_key="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="ack_broker_vendor_data_readiness",
        )
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=_read_required(dispatch_summary_path, "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch_orders_path, "broker_dispatch_orders"),
        send_summary=_read_required(send_summary_path, "broker_dispatch_send_summary"),
        send_requests=_read_required(send_requests_path, "broker_dispatch_send_requests"),
        ack_summary=_read_required(ack_summary_path, "broker_dispatch_ack_summary"),
        acknowledgements=_read_required(
            acknowledgements_path,
            "broker_dispatch_acknowledgements",
        ),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "broker_dispatch_roundtrip_orders.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_roundtrip_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_roundtrip_summary.csv", index=False)
    (out / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_roundtrip",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchRoundTripThresholds())},
        inputs=_manifest_inputs(
            dispatch_summary=dispatch_summary_path,
            dispatch_orders=dispatch_orders_path,
            dispatch_config=dispatch_config_path,
            dispatch_manifest=dispatch_manifest_path,
            send_summary=send_summary_path,
            send_requests=send_requests_path,
            send_config=send_config_path,
            send_manifest=send_manifest_path,
            ack_summary=ack_summary_path,
            acknowledgements=acknowledgements_path,
            ack_config=ack_config_path,
            ack_manifest=ack_manifest_path,
        ),
    )
    return BrokerDispatchRoundTripReport(report.orders, report.checks, report.summary, report.config, out)


def _manifest_inputs(**paths: Path) -> dict[str, Path]:
    return {name: path for name, path in paths.items() if path.exists()}


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


def _broker_readiness_config_from_dispatch_manifest(dispatch_manifest_path: Path | None) -> Path | None:
    route_manifest_path = _manifest_input_path(dispatch_manifest_path, "route_enable_manifest")
    cutover_manifest_path = _manifest_input_path(route_manifest_path, "cutover_manifest")
    return _manifest_input_path(cutover_manifest_path, "broker_readiness_config")


def _roundtrip_orders(
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    acknowledgements: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, dispatch in dispatch_orders.reset_index(drop=True).iterrows():
        dispatch_order_id = _text(dispatch, "dispatch_order_id")
        source_order_id = _text(dispatch, "source_order_id")
        send_matches = _matches(send_requests, "dispatch_order_id", dispatch_order_id)
        ack_matches = _matches(acknowledgements, "dispatch_order_id", dispatch_order_id)
        ack = ack_matches.iloc[-1] if not ack_matches.empty else pd.Series(dtype=object)
        request = send_matches.iloc[-1] if not send_matches.empty else pd.Series(dtype=object)
        rows.append(
            {
                "dispatch_batch_id": _text(dispatch, "dispatch_batch_id"),
                "dispatch_order_id": dispatch_order_id,
                "dispatch_route_roundtrip_batch_id": _text(dispatch, "route_dispatch_roundtrip_batch_id"),
                "source_order_id": source_order_id,
                "target_mode": _text(dispatch, "target_mode"),
                "strategy": _text(dispatch, "strategy"),
                "market": _text(dispatch, "market"),
                "scenario_key": _text(dispatch, "scenario_key"),
                "adapter": _text(dispatch, "adapter"),
                "request_count": int(len(send_matches)),
                "request_id": _text(request, "request_id"),
                "request_route_roundtrip_batch_id": _text(request, "route_dispatch_roundtrip_batch_id"),
                "idempotency_key": _text(request, "idempotency_key"),
                "request_payload_hash": _text(request, "request_payload_hash"),
                "request_payload_valid": _to_bool(request.get("payload_valid", False)) if not request.empty else False,
                "request_submission_enabled": _to_bool(request.get("submission_enabled", False))
                if not request.empty
                else False,
                "request_dry_run_only": _to_bool(request.get("dry_run_only", False)) if not request.empty else False,
                "ack_row_present": not ack.empty,
                "ack_route_roundtrip_batch_id": _text(ack, "route_dispatch_roundtrip_batch_id"),
                "ack_dispatch_order_route_roundtrip_batch_id": _text(
                    ack,
                    "dispatch_order_route_roundtrip_batch_id",
                ),
                "ack_raw_route_roundtrip_batch_ids": _text(ack, "ack_route_dispatch_roundtrip_batch_ids"),
                "ack_count": int(_number(ack, "ack_count", 0.0)) if not ack.empty else 0,
                "ack_status": _text(ack, "ack_status"),
                "broker_order_id": _text(ack, "broker_order_id"),
                "acked": _to_bool(ack.get("acked", False)) if not ack.empty else False,
                "rejected": _to_bool(ack.get("rejected", False)) if not ack.empty else False,
                "duplicate_ack": _to_bool(ack.get("duplicate_ack", False)) if not ack.empty else False,
                "missing_ack": _to_bool(ack.get("missing_ack", True)) if not ack.empty else True,
            }
        )
    return pd.DataFrame(rows)


def _component_summary_state(row: pd.Series, config: dict[str, Any]) -> pd.Series:
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
    broker_vendor_data_readiness, _broker_vendor_readiness_source_prefix = (
        _broker_vendor_data_readiness_source(config)
    )
    if broker_vendor_data_readiness:
        _apply_broker_vendor_data_readiness_config(state, broker_vendor_data_readiness)
    else:
        _copy_broker_vendor_data_readiness_fields(state)
    broker_vendor_market_data_batch, _broker_vendor_source_prefix = _broker_vendor_market_data_batch_source(
        state,
        config,
    )
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            broker_vendor_market_data_batch,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefixes=(
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
                "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            ),
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    vendor_market_data_batch = (
        config.get("ack_vendor_market_data_batch", {})
        or config.get("dispatch_vendor_market_data_batch", {})
        or config.get("route_vendor_market_data_batch", {})
        or {}
    )
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(state, vendor_market_data_batch)
    else:
        _copy_vendor_market_data_batch_fields(state)
    return state


def _broker_vendor_market_data_batch_source(
    state: pd.Series,
    config: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    candidates = (
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch",
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    )
    vendor, field_prefix = select_vendor_market_data_batch_source(
        config,
        candidates,
        default_source="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    if vendor:
        return vendor, field_prefix
    for field_prefix in candidates:
        if any(
            f"{field_prefix}_{suffix}" in state
            for suffix in ("provided", "dataset_count", "datasets_json")
        ):
            return {}, field_prefix
    return {}, "ack_broker_dispatch_roundtrip_vendor_market_data_batch"


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
        (config.get("roundtrip_broker_vendor_data_readiness"), "roundtrip_broker_vendor_data_readiness"),
        (config.get("ack_broker_vendor_data_readiness"), "ack_broker_vendor_data_readiness"),
        (config.get("dispatch_broker_vendor_data_readiness"), "dispatch_broker_vendor_data_readiness"),
        (config.get("route_broker_vendor_data_readiness"), "route_broker_vendor_data_readiness"),
        (config.get("cutover_broker_vendor_data_readiness"), "cutover_broker_vendor_data_readiness"),
        (config.get("scaleup_broker_vendor_data_readiness"), "scaleup_broker_vendor_data_readiness"),
        (config.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness"),
    ]
    broker_readiness = config.get("broker_readiness", {}) or {}
    if isinstance(broker_readiness, dict):
        candidates.append(
            (broker_readiness.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
        broker_dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
        if isinstance(broker_dispatch, dict):
            candidates.append(
                (broker_dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
            )
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(
            (dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
    for candidate, source in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_source_active(candidate):
            return candidate, source
    return {}, "ack_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    component_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
    *,
    target_key: str,
    target_readiness_key: str,
) -> dict[str, Any]:
    vendor, _source = select_vendor_market_data_batch_source(
        component_config,
        (
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        sidecar_vendor, _source = select_vendor_market_data_batch_source(
            dispatch,
            (
                "broker_dispatch_roundtrip_vendor_market_data_batch",
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "vendor_market_data_batch",
                "roundtrip_vendor_market_data_batch",
            ),
            default_source="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        sidecar_vendor = {}
    should_hydrate_vendor = (
        not vendor_market_data_batch_source_active(vendor)
        and vendor_market_data_batch_source_active(sidecar_vendor)
    )
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(component_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(broker_readiness_config)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    if not should_hydrate_vendor and not should_hydrate_readiness:
        return component_config

    out = dict(component_config)
    if should_hydrate_vendor:
        out[target_key] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out[target_readiness_key] = dict(sidecar_readiness)
    return out


def _apply_vendor_market_data_batch_config(
    state: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str = "vendor_market_data_batch",
) -> None:
    comparison = vendor.get("comparison", {}) or {}
    state[f"{field_prefix}_provided"] = _to_bool(
        vendor.get("provided", state.get(f"{field_prefix}_provided", False))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        vendor.get("ready", state.get(f"{field_prefix}_ready", False))
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        vendor.get("adapter", state.get(f"{field_prefix}_adapter", ""))
    )
    state[f"{field_prefix}_kind"] = _object_text(
        vendor.get("kind", state.get(f"{field_prefix}_kind", ""))
    )
    state[f"{field_prefix}_manifest_run_type"] = _identity_key(
        vendor.get("manifest_run_type", state.get(f"{field_prefix}_manifest_run_type", ""))
    )
    state[f"{field_prefix}_market"] = _object_text(
        vendor.get("market", state.get(f"{field_prefix}_market", ""))
    )
    state[f"{field_prefix}_dataset_count"] = int(
        _number_value(vendor.get("dataset_count"), _number(state, f"{field_prefix}_dataset_count", 0.0))
    )
    state[f"{field_prefix}_ready_datasets"] = int(
        _number_value(vendor.get("ready_datasets"), _number(state, f"{field_prefix}_ready_datasets", 0.0))
    )
    state[f"{field_prefix}_failed_datasets"] = int(
        _number_value(vendor.get("failed_datasets"), _number(state, f"{field_prefix}_failed_datasets", 0.0))
    )
    state[f"{field_prefix}_ready_rate"] = _number_value(
        vendor.get("ready_rate"),
        _number(state, f"{field_prefix}_ready_rate", 0.0),
    )
    state[f"{field_prefix}_unique_source_files"] = int(
        _number_value(
            vendor.get("unique_source_files"),
            _number(state, f"{field_prefix}_unique_source_files", 0.0),
        )
    )
    state[f"{field_prefix}_unique_header_fingerprints"] = int(
        _number_value(
            vendor.get("unique_header_fingerprints"),
            _number(state, f"{field_prefix}_unique_header_fingerprints", 0.0),
        )
    )
    state[f"{field_prefix}_source_file_fingerprint_coverage"] = _number_value(
        vendor.get("source_file_fingerprint_coverage"),
        _number(state, f"{field_prefix}_source_file_fingerprint_coverage", 0.0),
    )
    state[f"{field_prefix}_min_mapping_coverage"] = _number_value(
        vendor.get("min_mapping_coverage"),
        _number(state, f"{field_prefix}_min_mapping_coverage", 0.0),
    )
    state[f"{field_prefix}_unique_mapping_drafts"] = int(
        _number_value(
            vendor.get("unique_mapping_drafts"),
            _number(state, f"{field_prefix}_unique_mapping_drafts", 0.0),
        )
    )
    state[f"{field_prefix}_mapping_sources"] = _object_text(
        vendor.get("mapping_sources", state.get(f"{field_prefix}_mapping_sources", ""))
    )
    state[f"{field_prefix}_comparison_accepted"] = _to_bool(
        comparison.get("accepted", state.get(f"{field_prefix}_comparison_accepted", False))
    )
    state[f"{field_prefix}_comparison_failed_checks"] = int(
        _number_value(
            comparison.get("failed_checks"),
            _number(state, f"{field_prefix}_comparison_failed_checks", 0.0),
        )
    )
    datasets = vendor.get("datasets")
    state[f"{field_prefix}_datasets_json"] = (
        json.dumps(_vendor_market_data_batch_datasets(datasets), sort_keys=True)
        if isinstance(datasets, list)
        else _text(state, f"{field_prefix}_datasets_json")
    )


def _copy_vendor_market_data_batch_fields(
    state: pd.Series,
    *,
    source_prefixes: tuple[str, ...] = (
        "ack_vendor_market_data_batch",
        "dispatch_vendor_market_data_batch",
        "route_vendor_market_data_batch",
    ),
    field_prefix: str = "vendor_market_data_batch",
) -> None:
    source_prefix = next(
        (
            prefix
            for prefix in source_prefixes
            if _to_bool(state.get(f"{prefix}_provided", False))
            or int(_number(state, f"{prefix}_dataset_count", 0.0)) > 0
        ),
        "",
    )
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
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_mapping_drafts",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        state[f"{field_prefix}_{suffix}"] = (
            state.get(f"{source_prefix}_{suffix}", "") if source_prefix else ""
        )


def _apply_broker_vendor_data_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str = "broker_vendor_data_readiness",
) -> None:
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    state[f"{field_prefix}_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{field_prefix}_provided", active_config))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        readiness.get("ready", state.get(f"{field_prefix}_ready", False))
    )
    state[f"{field_prefix}_failed_checks"] = _broker_vendor_data_readiness_failed_checks(
        readiness,
        fallback=_number(state, f"{field_prefix}_failed_checks", 0.0),
    )


def _copy_broker_vendor_data_readiness_fields(
    state: pd.Series,
    *,
    source_prefixes: tuple[str, ...] = (
        "roundtrip_broker_vendor_data_readiness",
        "ack_broker_vendor_data_readiness",
        "dispatch_broker_vendor_data_readiness",
        "route_broker_vendor_data_readiness",
    ),
    field_prefix: str = "broker_vendor_data_readiness",
) -> None:
    source_prefix = next(
        (
            prefix
            for prefix in source_prefixes
            if _to_bool(state.get(f"{prefix}_provided", False))
            or _to_bool(state.get(f"{prefix}_ready", False))
            or int(_number(state, f"{prefix}_failed_checks", 0.0)) > 0
        ),
        "",
    )
    for suffix in ("provided", "ready", "failed_checks"):
        state[f"{field_prefix}_{suffix}"] = (
            state.get(f"{source_prefix}_{suffix}", 0 if suffix == "failed_checks" else False)
            if source_prefix
            else 0 if suffix == "failed_checks" else False
        )


def _broker_vendor_data_readiness_failed_checks(
    readiness: dict[str, Any],
    *,
    fallback: float = 0.0,
) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_value(failed_checks, fallback))
    return int(_number_value(readiness.get("failed_check_count", fallback), fallback))


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
    send_summary: pd.Series,
    ack_summary: pd.Series,
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    roundtrip_orders: pd.DataFrame,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> pd.DataFrame:
    component_failed = _component_failed_checks(dispatch_summary, send_summary, ack_summary)
    request_count = int(len(send_requests))
    dispatch_count = int(len(dispatch_orders))
    acked_requests = int(roundtrip_orders["acked"].map(_to_bool).sum()) if not roundtrip_orders.empty else 0
    missing_request_acks = _missing_request_acks(roundtrip_orders)
    rejected = int(_number(ack_summary, "rejected_orders", 0.0))
    duplicate_acks = int(_number(ack_summary, "duplicate_ack_orders", 0.0))
    unmatched_acks = int(_number(ack_summary, "unmatched_acks", 0.0))
    identity_mismatches = _identity_mismatches(dispatch_summary, send_summary, ack_summary)
    route_readiness_required = _route_readiness_required(dispatch_summary, send_summary, ack_summary, thresholds)
    route_readiness_provided = _route_readiness_provided(dispatch_summary, send_summary, ack_summary)
    route_roundtrip_required = _dispatch_roundtrip_required(dispatch_summary, thresholds)
    route_roundtrip_provided = _route_roundtrip_provided(dispatch_summary, send_summary, ack_summary)
    route_enable_failed_checks = _route_enable_failed_checks(dispatch_summary, send_summary, ack_summary)
    submission_enabled = _submission_enabled(send_summary, send_requests)
    dry_run_only = _all_dry_run(dispatch_orders, send_requests, roundtrip_orders)
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                _to_bool(dispatch_summary.get("ready", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("ready", False)) or not thresholds.require_dispatch_ready,
                "dispatch plan is not ready",
            ),
            _check(
                "send_ready",
                _to_bool(send_summary.get("ready", False)),
                "is",
                True,
                _to_bool(send_summary.get("ready", False)) or not thresholds.require_send_ready,
                "broker dispatch send packet is not ready",
            ),
            _check(
                "ack_passed",
                _to_bool(ack_summary.get("passed", False)),
                "is",
                True,
                _to_bool(ack_summary.get("passed", False)) or not thresholds.require_ack_passed,
                "broker dispatch acknowledgements did not pass",
            ),
            _check(
                "target_mode_matches",
                _identity_key(dispatch_summary.get("target_mode", "")),
                "==",
                thresholds.target_mode,
                _identity_key(dispatch_summary.get("target_mode", "")) == thresholds.target_mode,
                "round-trip target mode does not match threshold",
            ),
            _check(
                "identity_match",
                identity_mismatches,
                "==",
                0,
                identity_mismatches == 0 or not thresholds.require_identity_match,
                "dispatch, send, and ack identities do not match",
            ),
            _check(
                "route_dispatch_roundtrip_provided",
                route_roundtrip_provided,
                "is",
                True,
                route_roundtrip_provided or not route_roundtrip_required,
                "round-trip proof requires route dispatch round-trip evidence from dispatch, send, and ack artifacts",
            ),
            _check(
                "route_readiness_provided",
                route_readiness_provided,
                "is",
                True,
                route_readiness_provided or not route_readiness_required,
                "round-trip proof requires route-readiness evidence from dispatch, send, and ack artifacts",
            ),
            _check(
                "request_count_matches_dispatch",
                request_count,
                "==",
                dispatch_count,
                request_count == dispatch_count,
                "send request count does not match dispatch order count",
            ),
            _check(
                "unique_request_per_dispatch_order",
                int(roundtrip_orders["request_count"].eq(1).sum()) if not roundtrip_orders.empty else 0,
                "==",
                dispatch_count,
                bool(roundtrip_orders["request_count"].eq(1).all()) if not roundtrip_orders.empty else False,
                "each dispatch order must have exactly one send request",
            ),
            _check(
                "submission_disabled",
                submission_enabled,
                "is",
                False,
                (not submission_enabled) or not thresholds.require_submission_disabled,
                "round-trip evidence includes live submission enabled",
            ),
            _check("dry_run_only", dry_run_only, "is", True, dry_run_only, "round-trip evidence is not dry-run-only"),
            _check(
                "all_requests_acked",
                acked_requests,
                "==",
                request_count,
                (acked_requests == request_count and missing_request_acks == 0)
                or not thresholds.require_all_requests_acked,
                "not every send request has an accepted acknowledgement",
            ),
            _check(
                "missing_request_acks",
                missing_request_acks,
                "<=",
                thresholds.max_missing_request_acks,
                missing_request_acks <= thresholds.max_missing_request_acks,
                "missing request acknowledgements exceeded threshold",
            ),
            _check(
                "rejected_orders",
                rejected,
                "==",
                0,
                rejected == 0 or thresholds.allow_rejections,
                "acknowledgements include rejected orders",
            ),
            _check(
                "duplicate_ack_orders",
                duplicate_acks,
                "<=",
                thresholds.max_duplicate_ack_orders,
                duplicate_acks <= thresholds.max_duplicate_ack_orders,
                "duplicate acknowledgement rows exceeded threshold",
            ),
            _check(
                "unmatched_acks",
                unmatched_acks,
                "<=",
                thresholds.max_unmatched_acks,
                unmatched_acks <= thresholds.max_unmatched_acks,
                "acknowledgement reconciliation has unmatched rows",
            ),
            _check(
                "component_failed_checks",
                component_failed,
                "<=",
                thresholds.max_total_failed_component_checks,
                component_failed <= thresholds.max_total_failed_component_checks,
                "component reports contain failed checks",
            ),
            _check(
                "route_enable_dispatch_roundtrip_failed_checks",
                route_enable_failed_checks,
                "<=",
                0,
                route_enable_failed_checks <= 0,
                "route-enable dispatch round-trip has failed component checks",
            ),
        ]
    )
    if route_readiness_required or route_readiness_provided:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _shadow_broker_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_shadow_broker_readiness_checks(dispatch_summary, send_summary, ack_summary)),
            ],
            ignore_index=True,
        )
    if _route_broker_shadow_broker_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_broker_shadow_broker_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _broker_vendor_data_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _broker_vendor_data_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _vendor_market_data_batch_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _vendor_market_data_batch_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _broker_vendor_market_data_batch_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _broker_vendor_market_data_batch_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if route_roundtrip_required or route_roundtrip_provided:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_roundtrip_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                        roundtrip_orders,
                    )
                ),
            ],
            ignore_index=True,
        )
    return checks


def _route_readiness_checks(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
) -> list[dict[str, object]]:
    rows = (dispatch_summary, send_summary, ack_summary)
    ready = all(_to_bool(row.get("route_readiness_ready", False)) for row in rows)
    identity_mismatches = _route_readiness_identity_mismatches(rows)
    gap_pairs = _route_readiness_counter_max(rows, "route_readiness_gap_pairs")
    return [
        _check(
            "route_readiness_ready",
            ready,
            "is",
            True,
            ready,
            "route-readiness proof is not ready in all component artifacts",
        ),
        _check(
            "route_readiness_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "route-readiness proof identity does not match component identity",
        ),
        _check(
            "route_readiness_gap_pairs",
            gap_pairs,
            "==",
            0,
            gap_pairs == 0,
            "route-readiness proof still reports market/strategy gaps",
        ),
    ]


def _route_roundtrip_checks(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    roundtrip_orders: pd.DataFrame,
) -> list[dict[str, object]]:
    rows = (dispatch_summary, send_summary, ack_summary)
    ready = all(_to_bool(row.get("route_dispatch_roundtrip_ready", False)) for row in rows)
    identity_mismatches = _route_roundtrip_identity_mismatches(rows)
    batch_ids = _route_roundtrip_batch_ids(rows, roundtrip_orders)
    batch_consistent = bool(batch_ids) and len(batch_ids) == 1
    request_counts_match = _route_roundtrip_request_counts_match(rows)
    missing = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_missing_request_acks")
    rejected = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_rejected_orders")
    unmatched = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_unmatched_acks")
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            ready,
            "is",
            True,
            ready,
            "route dispatch round-trip proof is not ready in all component artifacts",
        ),
        _check(
            "route_dispatch_roundtrip_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "route dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "route_dispatch_roundtrip_batch_consistent",
            ",".join(sorted(batch_ids)),
            "has_unique_nonempty",
            True,
            batch_consistent,
            "route dispatch round-trip proof batch is missing or inconsistent across artifacts",
        ),
        _check(
            "route_dispatch_roundtrip_request_counts_match",
            request_counts_match,
            "is",
            True,
            request_counts_match,
            "route dispatch round-trip request and ack counts are inconsistent",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            missing,
            "<=",
            0,
            missing <= 0,
            "route dispatch round-trip proof has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            rejected,
            "<=",
            0,
            rejected <= 0,
            "route dispatch round-trip proof has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            unmatched,
            "<=",
            0,
            unmatched <= 0,
            "route dispatch round-trip proof has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(*rows: pd.Series) -> bool:
    session_columns = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_route_readiness_sessions",
        "shadow_broker_dispatch_roundtrip_sessions",
        "shadow_broker_route_dispatch_roundtrip_sessions",
    )
    return any(_shadow_counter_max(rows, column) > 0 for column in session_columns)


def _shadow_broker_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    sessions = [int(_number(row, "shadow_broker_readiness_sessions", 0.0)) for row in rows]
    ready_sessions = [int(_number(row, "shadow_broker_readiness_ready_sessions", 0.0)) for row in rows]
    provided = all(value > 0 for value in sessions)
    ready = provided and all(ready == session for ready, session in zip(ready_sessions, sessions))
    adapter_match = _shadow_adapter_matches(rows)
    adapter_consistent = _shadow_adapter_consistent(rows)
    route_sessions = [int(_number(row, "shadow_broker_route_readiness_sessions", 0.0)) for row in rows]
    route_ready_sessions = [
        int(_number(row, "shadow_broker_route_readiness_ready_sessions", 0.0)) for row in rows
    ]
    dispatch_sessions = [
        int(_number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0)) for row in rows
    ]
    dispatch_ready_sessions = [
        int(_number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)) for row in rows
    ]
    route_dispatch_sessions = [
        int(_number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)) for row in rows
    ]
    route_dispatch_ready_sessions = [
        int(_number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)) for row in rows
    ]
    return [
        _check(
            "shadow_broker_readiness_provided",
            min(sessions) if sessions else 0,
            ">",
            0,
            provided,
            "shadow broker-readiness proof is not present in every component artifact",
        ),
        _check(
            "shadow_broker_readiness_ready",
            "|".join(str(value) for value in ready_sessions),
            "==",
            "|".join(str(value) for value in sessions),
            ready,
            "shadow broker-readiness proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_adapter_match",
            _shadow_adapter_value(rows),
            "matches",
            _identity_key(rows[0].get("adapter", "")) if rows else "",
            adapter_match,
            "shadow broker adapter proof does not match component adapter identity",
        ),
        _check(
            "shadow_broker_adapter_consistent",
            _shadow_counter_max(rows, "shadow_broker_adapter_count"),
            "==",
            1,
            adapter_consistent,
            "shadow broker adapter proof is missing or mixed across component artifacts",
        ),
        _check(
            "shadow_broker_route_readiness_ready",
            "|".join(str(value) for value in route_ready_sessions),
            "==",
            "|".join(str(value) for value in route_sessions),
            all(session > 0 for session in route_sessions)
            and all(ready == session for ready, session in zip(route_ready_sessions, route_sessions)),
            "shadow broker route-readiness proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_route_readiness_identity_match",
            _shadow_identity_mismatches(rows, "route_readiness"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "route_readiness") == 0,
            "shadow broker route-readiness proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_route_readiness_gap_pairs",
            _shadow_counter_max(rows, "shadow_broker_route_readiness_gap_pairs"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_route_readiness_gap_pairs") <= 0,
            "shadow broker route-readiness proof reports route gaps",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_ready",
            "|".join(str(value) for value in dispatch_ready_sessions),
            "==",
            "|".join(str(value) for value in dispatch_sessions),
            all(session > 0 for session in dispatch_sessions)
            and all(ready == session for ready, session in zip(dispatch_ready_sessions, dispatch_sessions)),
            "shadow broker dispatch round-trip proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_identity_match",
            _shadow_identity_mismatches(rows, "dispatch_roundtrip"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "dispatch_roundtrip") == 0,
            "shadow broker dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_scenario_consistent",
            "|".join(str(int(_number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0))) for row in rows),
            "==",
            1,
            all(int(_number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)) == 1 for row in rows),
            "shadow broker dispatch round-trip scenario is missing or mixed",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_missing_request_acks",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_missing_request_acks"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_missing_request_acks") <= 0,
            "shadow broker dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_rejected_orders",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_rejected_orders"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_rejected_orders") <= 0,
            "shadow broker dispatch round-trip has rejected orders",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_unmatched_acks",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_unmatched_acks"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_unmatched_acks") <= 0,
            "shadow broker dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_ready",
            "|".join(str(value) for value in route_dispatch_ready_sessions),
            "==",
            "|".join(str(value) for value in route_dispatch_sessions),
            all(session > 0 for session in route_dispatch_sessions)
            and all(
                ready == session
                for ready, session in zip(route_dispatch_ready_sessions, route_dispatch_sessions)
            ),
            "shadow broker route dispatch round-trip proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_identity_match",
            _shadow_identity_mismatches(rows, "route_dispatch_roundtrip"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "route_dispatch_roundtrip") == 0,
            "shadow broker route dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
            "|".join(
                str(int(_number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)))
                for row in rows
            ),
            "==",
            1,
            all(
                int(_number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)) == 1
                for row in rows
            ),
            "shadow broker route dispatch round-trip scenario is missing or mixed",
        ),
    ]


def _route_broker_shadow_broker_readiness_active(*rows: pd.Series) -> bool:
    prefix = "route_broker_shadow_broker"
    session_columns = (
        f"{prefix}_readiness_sessions",
        f"{prefix}_route_readiness_sessions",
        f"{prefix}_dispatch_roundtrip_sessions",
        f"{prefix}_route_dispatch_roundtrip_sessions",
    )
    return bool(
        any(_to_bool(row.get(f"{prefix}_readiness_provided", False)) for row in rows)
        or any(_shadow_counter_max(rows, column) > 0 for column in session_columns)
    )


def _route_broker_shadow_broker_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    source_prefix = "route_broker_shadow_broker"
    provided = bool(
        rows
        and all(
            _to_bool(row.get(f"{source_prefix}_readiness_provided", False))
            and int(_number(row, f"{source_prefix}_readiness_sessions", 0.0)) > 0
            for row in rows
        )
    )
    checks = [
        _check(
            "broker_shadow_broker_readiness_provided",
            provided,
            "is",
            True,
            provided,
            "broker-readiness shadow broker proof is not provided by every component",
        )
    ]
    projected_rows = tuple(_shadow_broker_projection(row, source_prefix=source_prefix) for row in rows)
    for check in _shadow_broker_readiness_checks(*projected_rows):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "shadow_broker",
            "broker_shadow_broker",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "shadow broker",
                "broker-readiness shadow broker",
            )
        checks.append(renamed)
    return checks


def _vendor_market_data_batch_active(*rows: pd.Series) -> bool:
    return bool(
        any(_to_bool(row.get("vendor_market_data_batch_provided", False)) for row in rows)
        or any(_identity_key(row.get("vendor_market_data_batch_manifest_run_type", "")) for row in rows)
        or any(int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0 for row in rows)
    )


def _broker_vendor_data_readiness_active(*rows: pd.Series) -> bool:
    return bool(
        any(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
        or any(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
        or any(int(_number(row, "broker_vendor_data_readiness_failed_checks", 0.0)) > 0 for row in rows)
    )


def _broker_vendor_data_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    provided = bool(
        rows and all(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
    )
    ready = bool(
        rows and all(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
    )
    failed_checks = _broker_vendor_data_readiness_counter_max(
        rows,
        "broker_vendor_data_readiness_failed_checks",
    )
    return [
        _check(
            "broker_vendor_data_readiness_provided",
            provided,
            "is",
            True,
            provided,
            "broker-vendor readiness wrapper proof is not provided by every component",
        ),
        _check(
            "broker_vendor_data_readiness_ready",
            ready,
            "is",
            True,
            ready,
            "broker-vendor readiness wrapper proof is not ready in every component",
        ),
        _check(
            "broker_vendor_data_readiness_failed_checks",
            failed_checks,
            "==",
            0,
            failed_checks == 0,
            "broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _vendor_market_data_batch_checks(*rows: pd.Series) -> list[dict[str, object]]:
    provided = bool(
        rows
        and all(
            _to_bool(row.get("vendor_market_data_batch_provided", False))
            and int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0
            for row in rows
        )
    )
    ready = bool(rows and all(_to_bool(row.get("vendor_market_data_batch_ready", False)) for row in rows))
    identity_mismatches = _vendor_market_data_batch_identity_mismatches(rows)
    manifest_run_type_valid = _vendor_market_data_batch_manifest_run_type_valid(rows)
    counts_consistent = _vendor_market_data_batch_counts_consistent(rows)
    failed_datasets = _vendor_market_data_batch_counter_max(rows, "vendor_market_data_batch_failed_datasets")
    comparison_failed = _vendor_market_data_batch_counter_max(
        rows,
        "vendor_market_data_batch_comparison_failed_checks",
    )
    source_file_fingerprint_coverage = _vendor_market_data_batch_number_min(
        rows,
        "vendor_market_data_batch_source_file_fingerprint_coverage",
    )
    min_mapping_coverage = _vendor_market_data_batch_number_min(
        rows,
        "vendor_market_data_batch_min_mapping_coverage",
    )
    unique_mapping_drafts = _vendor_market_data_batch_counter_min(
        rows,
        "vendor_market_data_batch_unique_mapping_drafts",
    )
    comparison_accepted = bool(
        rows and all(_to_bool(row.get("vendor_market_data_batch_comparison_accepted", False)) for row in rows)
    )
    return [
        _check(
            "vendor_market_data_batch_provided",
            provided,
            "is",
            True,
            provided,
            "vendor market-data batch proof is not provided by every component",
        ),
        _check(
            "vendor_market_data_batch_ready",
            ready,
            "is",
            True,
            ready,
            "vendor market-data batch proof is not ready in every component",
        ),
        _check(
            "vendor_market_data_batch_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "vendor market-data batch adapter/market identity is inconsistent",
        ),
        _check(
            "vendor_market_data_batch_manifest_run_type",
            _vendor_market_data_batch_text_value(rows, "manifest_run_type"),
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type_valid,
            "vendor market-data batch manifest is not a vendor batch pipeline proof",
        ),
        _check(
            "vendor_market_data_batch_dataset_count_consistent",
            counts_consistent,
            "is",
            True,
            counts_consistent,
            "vendor market-data batch dataset counts differ across components",
        ),
        _check(
            "vendor_market_data_batch_failed_datasets",
            failed_datasets,
            "==",
            0,
            failed_datasets == 0,
            "vendor market-data batch still has failed datasets",
        ),
        _check(
            "vendor_market_data_batch_source_file_fingerprint_coverage",
            source_file_fingerprint_coverage,
            ">=",
            1.0,
            source_file_fingerprint_coverage >= 1.0,
            "vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            "vendor_market_data_batch_min_mapping_coverage",
            min_mapping_coverage,
            ">=",
            1.0,
            min_mapping_coverage >= 1.0,
            "vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            "vendor_market_data_batch_mapping_drafts",
            unique_mapping_drafts,
            ">",
            0,
            unique_mapping_drafts > 0,
            "vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            "vendor_market_data_batch_comparison_accepted",
            comparison_accepted,
            "is",
            True,
            comparison_accepted,
            "vendor market-data batch comparison is not accepted by every component",
        ),
        _check(
            "vendor_market_data_batch_comparison_failed_checks",
            comparison_failed,
            "==",
            0,
            comparison_failed == 0,
            "vendor market-data batch comparison has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_active(*rows: pd.Series) -> bool:
    return _vendor_market_data_batch_active(*_broker_vendor_market_data_batch_rows(rows))


def _broker_vendor_market_data_batch_checks(*rows: pd.Series) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for check in _vendor_market_data_batch_checks(*_broker_vendor_market_data_batch_rows(rows)):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "vendor market-data batch",
                "broker-readiness vendor market-data batch",
            )
        checks.append(renamed)
    return checks


def _broker_vendor_market_data_batch_rows(rows: tuple[pd.Series, ...]) -> tuple[pd.Series, ...]:
    return tuple(
        _vendor_market_data_batch_projection(
            row,
            source_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
        for row in rows
    )


def _vendor_market_data_batch_projection(row: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = row.copy()
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
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_mapping_drafts",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        mapped[f"vendor_market_data_batch_{suffix}"] = row.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _shadow_broker_projection(row: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = row.copy()
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
        mapped[f"shadow_broker_{suffix}"] = row.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _prefixed_shadow_broker_summary_fields(
    rows: tuple[pd.Series, ...],
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, object]:
    return {
        f"{output_prefix}_readiness_provided": _prefixed_shadow_broker_readiness_provided(
            rows,
            source_prefix=source_prefix,
        ),
        f"{output_prefix}_readiness_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_readiness_sessions",
        ),
        f"{output_prefix}_readiness_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_readiness_ready_sessions",
        ),
        f"{output_prefix}_adapter": _prefixed_shadow_adapter_value(rows, source_prefix=source_prefix),
        f"{output_prefix}_adapter_count": _shadow_counter_max(rows, f"{source_prefix}_adapter_count"),
        f"{output_prefix}_route_readiness_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_sessions",
        ),
        f"{output_prefix}_route_readiness_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_ready_sessions",
        ),
        f"{output_prefix}_route_readiness_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_readiness",
            column="strategy",
        ),
        f"{output_prefix}_route_readiness_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_readiness",
            column="market",
        ),
        f"{output_prefix}_route_readiness_gap_pairs": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_gap_pairs",
        ),
        f"{output_prefix}_dispatch_roundtrip_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_sessions",
        ),
        f"{output_prefix}_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_ready_sessions",
        ),
        f"{output_prefix}_dispatch_roundtrip_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="dispatch_roundtrip",
            column="strategy",
        ),
        f"{output_prefix}_dispatch_roundtrip_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="dispatch_roundtrip",
            column="market",
        ),
        f"{output_prefix}_dispatch_roundtrip_scenario_count": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_scenario_count",
        ),
        f"{output_prefix}_dispatch_roundtrip_missing_request_acks": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_missing_request_acks",
        ),
        f"{output_prefix}_dispatch_roundtrip_rejected_orders": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_rejected_orders",
        ),
        f"{output_prefix}_dispatch_roundtrip_unmatched_acks": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_unmatched_acks",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_sessions",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_ready_sessions",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_dispatch_roundtrip",
            column="strategy",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_dispatch_roundtrip",
            column="market",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_scenario_count": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_scenario_count",
        ),
    }


def _summary(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    roundtrip_orders: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    proof_rows = (dispatch_summary, send_summary, ack_summary)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "target_mode": _text(dispatch_summary, "target_mode"),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "broker_schema_status": _broker_schema_text(proof_rows, "broker_schema_status"),
                "broker_schema_reviewed": _broker_schema_reviewed(proof_rows),
                "broker_schema_review_mode": _broker_schema_text(proof_rows, "broker_schema_review_mode"),
                "dispatch_batch_id": _text(dispatch_summary, "dispatch_batch_id")
                or _text(send_summary, "dispatch_batch_id"),
                "dispatch_orders": int(_number(dispatch_summary, "dispatch_orders", len(roundtrip_orders))),
                "send_requests": int(_number(send_summary, "requests", 0.0)),
                "acked_orders": int(_number(ack_summary, "acked_orders", 0.0)),
                "missing_request_acks": _missing_request_acks(roundtrip_orders),
                "rejected_orders": int(_number(ack_summary, "rejected_orders", 0.0)),
                "duplicate_ack_orders": int(_number(ack_summary, "duplicate_ack_orders", 0.0)),
                "unmatched_acks": int(_number(ack_summary, "unmatched_acks", 0.0)),
                "route_readiness_required": _route_readiness_required(
                    dispatch_summary,
                    send_summary,
                    ack_summary,
                    thresholds,
                ),
                "route_readiness_provided": _route_readiness_provided(*proof_rows),
                "route_readiness_ready": all(
                    _to_bool(row.get("route_readiness_ready", False)) for row in proof_rows
                ),
                "route_readiness_strategy": _route_readiness_identity_value(dispatch_summary, "strategy")
                or _route_readiness_identity_value(send_summary, "strategy")
                or _route_readiness_identity_value(ack_summary, "strategy"),
                "route_readiness_market": _route_readiness_identity_value(dispatch_summary, "market")
                or _route_readiness_identity_value(send_summary, "market")
                or _route_readiness_identity_value(ack_summary, "market"),
                "route_readiness_route_ready_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_route_ready_pairs",
                ),
                "route_readiness_gap_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_gap_pairs",
                ),
                "route_readiness_recommendation": _route_readiness_recommendation(*proof_rows),
                "shadow_broker_readiness_provided": _shadow_broker_readiness_provided(*proof_rows),
                "shadow_broker_readiness_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_readiness_sessions",
                ),
                "shadow_broker_readiness_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_readiness_ready_sessions",
                ),
                "shadow_broker_adapter": _shadow_adapter_value(proof_rows),
                "shadow_broker_adapter_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_adapter_count",
                ),
                "shadow_broker_route_readiness_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_sessions",
                ),
                "shadow_broker_route_readiness_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_ready_sessions",
                ),
                "shadow_broker_route_readiness_strategy": _shadow_identity_value(
                    proof_rows,
                    "route_readiness",
                    "strategy",
                ),
                "shadow_broker_route_readiness_market": _shadow_identity_value(
                    proof_rows,
                    "route_readiness",
                    "market",
                ),
                "shadow_broker_route_readiness_gap_pairs": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_gap_pairs",
                ),
                "shadow_broker_dispatch_roundtrip_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_sessions",
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_ready_sessions",
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _shadow_identity_value(
                    proof_rows,
                    "dispatch_roundtrip",
                    "strategy",
                ),
                "shadow_broker_dispatch_roundtrip_market": _shadow_identity_value(
                    proof_rows,
                    "dispatch_roundtrip",
                    "market",
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_scenario_count",
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_missing_request_acks",
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_rejected_orders",
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_unmatched_acks",
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_sessions",
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions",
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _shadow_identity_value(
                    proof_rows,
                    "route_dispatch_roundtrip",
                    "strategy",
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _shadow_identity_value(
                    proof_rows,
                    "route_dispatch_roundtrip",
                    "market",
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_scenario_count",
                ),
                **_prefixed_shadow_broker_summary_fields(
                    proof_rows,
                    source_prefix="route_broker_shadow_broker",
                    output_prefix="broker_shadow_broker",
                ),
                **_broker_vendor_data_readiness_summary_fields(proof_rows),
                **_vendor_market_data_batch_summary_fields(proof_rows),
                **_broker_vendor_market_data_batch_summary_fields(proof_rows),
                "route_dispatch_roundtrip_required": _dispatch_roundtrip_required(dispatch_summary, thresholds),
                "route_dispatch_roundtrip_provided": _route_roundtrip_provided(*proof_rows),
                "route_dispatch_roundtrip_ready": all(
                    _to_bool(row.get("route_dispatch_roundtrip_ready", False)) for row in proof_rows
                ),
                "route_dispatch_roundtrip_target_mode": _route_identity_value(dispatch_summary, "target_mode")
                or _route_identity_value(send_summary, "target_mode")
                or _route_identity_value(ack_summary, "target_mode"),
                "route_dispatch_roundtrip_strategy": _route_identity_value(dispatch_summary, "strategy")
                or _route_identity_value(send_summary, "strategy")
                or _route_identity_value(ack_summary, "strategy"),
                "route_dispatch_roundtrip_market": _route_identity_value(dispatch_summary, "market")
                or _route_identity_value(send_summary, "market")
                or _route_identity_value(ack_summary, "market"),
                "route_dispatch_roundtrip_scenario_key": _route_identity_value(dispatch_summary, "scenario_key")
                or _route_identity_value(send_summary, "scenario_key")
                or _route_identity_value(ack_summary, "scenario_key"),
                "route_dispatch_roundtrip_batch_id": _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
                or _text(send_summary, "route_dispatch_roundtrip_batch_id")
                or _text(ack_summary, "route_dispatch_roundtrip_batch_id"),
                "route_dispatch_roundtrip_requests": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_requests",
                ),
                "route_dispatch_roundtrip_acked_orders": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_acked_orders",
                ),
                "route_dispatch_roundtrip_missing_request_acks": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_missing_request_acks",
                ),
                "route_dispatch_roundtrip_rejected_orders": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_rejected_orders",
                ),
                "route_dispatch_roundtrip_unmatched_acks": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_unmatched_acks",
                ),
                "route_enable_dispatch_roundtrip_failed_checks": _route_enable_failed_checks(*proof_rows),
                "total_failed_component_checks": _component_failed_checks(
                    dispatch_summary,
                    send_summary,
                    ack_summary,
                ),
                "failed_checks": failed,
                "recommendation": "broker_dry_run_roundtrip_proved"
                if passed
                else "investigate_broker_dry_run_roundtrip",
            }
        ]
    )


def _vendor_market_data_batch_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    return {
        "roundtrip_vendor_market_data_batch_provided": bool(
            rows and all(_to_bool(row.get("vendor_market_data_batch_provided", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_ready": bool(
            rows and all(_to_bool(row.get("vendor_market_data_batch_ready", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_adapter": _vendor_market_data_batch_identity_value(rows, "adapter"),
        "roundtrip_vendor_market_data_batch_kind": _vendor_market_data_batch_text_value(rows, "kind"),
        "roundtrip_vendor_market_data_batch_manifest_run_type": _vendor_market_data_batch_identity_value(
            rows,
            "manifest_run_type",
        ),
        "roundtrip_vendor_market_data_batch_market": _vendor_market_data_batch_identity_value(rows, "market"),
        "roundtrip_vendor_market_data_batch_dataset_count": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_dataset_count",
        ),
        "roundtrip_vendor_market_data_batch_ready_datasets": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_ready_datasets",
        ),
        "roundtrip_vendor_market_data_batch_failed_datasets": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_failed_datasets",
        ),
        "roundtrip_vendor_market_data_batch_ready_rate": _vendor_market_data_batch_number_min(
            rows,
            "vendor_market_data_batch_ready_rate",
        ),
        "roundtrip_vendor_market_data_batch_unique_source_files": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_source_files",
        ),
        "roundtrip_vendor_market_data_batch_unique_header_fingerprints": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_header_fingerprints",
        ),
        "roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage": (
            _vendor_market_data_batch_number_min(
                rows,
                "vendor_market_data_batch_source_file_fingerprint_coverage",
            )
        ),
        "roundtrip_vendor_market_data_batch_min_mapping_coverage": _vendor_market_data_batch_number_min(
            rows,
            "vendor_market_data_batch_min_mapping_coverage",
        ),
        "roundtrip_vendor_market_data_batch_unique_mapping_drafts": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_mapping_drafts",
        ),
        "roundtrip_vendor_market_data_batch_mapping_sources": _vendor_market_data_batch_text_value(
            rows,
            "mapping_sources",
        ),
        "roundtrip_vendor_market_data_batch_comparison_accepted": bool(
            rows
            and all(_to_bool(row.get("vendor_market_data_batch_comparison_accepted", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_comparison_failed_checks": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_comparison_failed_checks",
        ),
        "roundtrip_vendor_market_data_batch_datasets_json": _vendor_market_data_batch_datasets_json(rows),
    }


def _broker_vendor_market_data_batch_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    fields = _vendor_market_data_batch_summary_fields(
        _broker_vendor_market_data_batch_rows(rows)
    )
    return {
        key.replace(
            "roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        ): value
        for key, value in fields.items()
    }


def _broker_vendor_data_readiness_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    return {
        "roundtrip_broker_vendor_data_readiness_provided": bool(
            rows and all(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
        ),
        "roundtrip_broker_vendor_data_readiness_ready": bool(
            rows and all(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
        ),
        "roundtrip_broker_vendor_data_readiness_failed_checks": _broker_vendor_data_readiness_counter_max(
            rows,
            "broker_vendor_data_readiness_failed_checks",
        ),
    }


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


def _vendor_market_data_batch_config(
    summary: pd.Series,
    *,
    field_prefix: str = "roundtrip_vendor_market_data_batch",
) -> dict[str, object]:
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
        "unique_header_fingerprints": int(
            summary[f"{field_prefix}_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            summary[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(summary[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(summary[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": _text(summary, f"{field_prefix}_mapping_sources"),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_data_readiness_config(summary: pd.Series) -> dict[str, object]:
    return {
        "provided": _to_bool(summary["roundtrip_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(summary["roundtrip_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(summary["roundtrip_broker_vendor_data_readiness_failed_checks"]),
    }


def _config(
    summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": _to_bool(summary["passed"]),
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
        "dispatch_orders": int(summary["dispatch_orders"]),
        "send_requests": int(summary["send_requests"]),
        "acked_orders": int(summary["acked_orders"]),
        "missing_request_acks": int(summary["missing_request_acks"]),
        "rejected_orders": int(summary["rejected_orders"]),
        "duplicate_ack_orders": int(summary["duplicate_ack_orders"]),
        "unmatched_acks": int(summary["unmatched_acks"]),
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
            "provided": _to_bool(summary["shadow_broker_readiness_provided"]),
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
        "broker_shadow_broker_readiness": _prefixed_shadow_broker_config(
            summary,
            field_prefix="broker_shadow_broker",
        ),
        "roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(summary),
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _vendor_market_data_batch_config(
                summary,
                field_prefix="roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "roundtrip_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(summary),
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


def _matches(frame: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    if frame.empty or not value or column not in frame.columns:
        return frame.iloc[:0]
    return frame.loc[frame[column].astype(str).str.strip() == value].reset_index(drop=True)


def _missing_request_acks(roundtrip_orders: pd.DataFrame) -> int:
    if roundtrip_orders.empty:
        return 0
    requested = roundtrip_orders["request_count"].astype(int) > 0
    acked = roundtrip_orders["acked"].map(_to_bool)
    return int((requested & ~acked).sum())


def _submission_enabled(send_summary: pd.Series, send_requests: pd.DataFrame) -> bool:
    summary_enabled = _to_bool(send_summary.get("submission_enabled", False))
    request_enabled = (
        bool(send_requests["submission_enabled"].map(_to_bool).any())
        if "submission_enabled" in send_requests.columns and not send_requests.empty
        else False
    )
    return summary_enabled or request_enabled


def _all_dry_run(
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    roundtrip_orders: pd.DataFrame,
) -> bool:
    dispatch_dry_run = (
        bool(dispatch_orders["dry_run_only"].map(_to_bool).all())
        if "dry_run_only" in dispatch_orders.columns and not dispatch_orders.empty
        else False
    )
    send_dry_run = (
        bool(send_requests["dry_run_only"].map(_to_bool).all())
        if "dry_run_only" in send_requests.columns and not send_requests.empty
        else False
    )
    linked_dry_run = (
        bool(roundtrip_orders["request_dry_run_only"].map(_to_bool).all()) if not roundtrip_orders.empty else False
    )
    return dispatch_dry_run and send_dry_run and linked_dry_run


def _dispatch_roundtrip_required(
    dispatch_summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> bool:
    return bool(
        thresholds.require_dispatch_roundtrip
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
    )


def _route_readiness_required(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> bool:
    return bool(
        thresholds.require_route_readiness
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
        or any(
            _to_bool(row.get("route_readiness_required", False))
            for row in (dispatch_summary, send_summary, ack_summary)
        )
    )


def _route_readiness_provided(*rows: pd.Series) -> bool:
    return all(_to_bool(row.get("route_readiness_provided", False)) for row in rows)


def _route_roundtrip_provided(*rows: pd.Series) -> bool:
    return all(_to_bool(row.get("route_dispatch_roundtrip_provided", False)) for row in rows)


def _route_readiness_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _route_readiness_identity_value(row, column)
            for row in rows
            if not row.empty and _route_readiness_identity_value(row, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_roundtrip_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("target_mode", "strategy", "market", "scenario_key"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _route_identity_value(row, column)
            for row in rows
            if not row.empty and _route_identity_value(row, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_roundtrip_batch_ids(rows: tuple[pd.Series, ...], roundtrip_orders: pd.DataFrame) -> set[str]:
    batch_ids = {
        _text(row, "route_dispatch_roundtrip_batch_id")
        for row in rows
        if _text(row, "route_dispatch_roundtrip_batch_id")
    }
    for column in (
        "dispatch_route_roundtrip_batch_id",
        "request_route_roundtrip_batch_id",
        "ack_route_roundtrip_batch_id",
        "ack_dispatch_order_route_roundtrip_batch_id",
        "ack_raw_route_roundtrip_batch_ids",
    ):
        if column in roundtrip_orders.columns:
            for value in roundtrip_orders[column].dropna().astype(str):
                batch_ids.update(_split_batch_ids(value))
    return batch_ids


def _split_batch_ids(value: object) -> set[str]:
    if pd.isna(value):
        return set()
    return {item.strip() for item in str(value).split("|") if item.strip()}


def _route_roundtrip_request_counts_match(rows: tuple[pd.Series, ...]) -> bool:
    request_counts = [
        int(_number(row, "route_dispatch_roundtrip_requests", 0.0))
        for row in rows
    ]
    acked_counts = [
        int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        for row in rows
    ]
    counts = set(request_counts + acked_counts)
    return bool(counts and 0 not in counts and len(counts) == 1)


def _route_roundtrip_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows)


def _route_readiness_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows)


def _shadow_broker_readiness_provided(*rows: pd.Series) -> bool:
    return bool(rows and all(int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0 for row in rows))


def _prefixed_shadow_broker_readiness_provided(rows: tuple[pd.Series, ...], *, source_prefix: str) -> bool:
    return bool(
        rows
        and all(
            _to_bool(row.get(f"{source_prefix}_readiness_provided", False))
            and int(_number(row, f"{source_prefix}_readiness_sessions", 0.0)) > 0
            for row in rows
        )
    )


def _shadow_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_counter_min(rows: tuple[pd.Series, ...], column: str) -> int:
    values = [int(_number(row, column, 0.0)) for row in rows]
    return min(values) if values else 0


def _broker_vendor_data_readiness_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_number_min(rows: tuple[pd.Series, ...], column: str) -> float:
    values = [float(_number(row, column, 0.0)) for row in rows]
    return min(values) if values else 0.0


def _vendor_market_data_batch_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("adapter", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _identity_key(row.get(f"vendor_market_data_batch_{column}", ""))
            for row in rows
            if not row.empty and _identity_key(row.get(f"vendor_market_data_batch_{column}", ""))
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _vendor_market_data_batch_manifest_run_type_valid(rows: tuple[pd.Series, ...]) -> bool:
    values = {
        _identity_key(row.get("vendor_market_data_batch_manifest_run_type", ""))
        for row in rows
        if not row.empty and _identity_key(row.get("vendor_market_data_batch_manifest_run_type", ""))
    }
    return values == {"vendor_market_data_batch_pipeline"}


def _vendor_market_data_batch_counts_consistent(rows: tuple[pd.Series, ...]) -> bool:
    counts = {
        int(_number(row, "vendor_market_data_batch_dataset_count", 0.0))
        for row in rows
        if not row.empty and int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0
    }
    return bool(counts and len(counts) == 1)


def _vendor_market_data_batch_text_value(rows: tuple[pd.Series, ...], column: str) -> str:
    for row in rows:
        value = _text(row, f"vendor_market_data_batch_{column}")
        if value:
            return value
    return ""


def _vendor_market_data_batch_identity_value(rows: tuple[pd.Series, ...], column: str) -> str:
    return _identity_key(_vendor_market_data_batch_text_value(rows, column))


def _vendor_market_data_batch_datasets_json(rows: tuple[pd.Series, ...]) -> str:
    for row in rows:
        value = _text(row, "vendor_market_data_batch_datasets_json")
        if value:
            return value
    return ""


def _shadow_adapter_matches(rows: tuple[pd.Series, ...]) -> bool:
    adapters = {
        _identity_key(row.get("adapter", ""))
        for row in rows
        if not row.empty and _identity_key(row.get("adapter", ""))
    }
    shadow_adapters = {
        _identity_key(row.get("shadow_broker_adapter", ""))
        for row in rows
        if int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0
        and _identity_key(row.get("shadow_broker_adapter", ""))
    }
    return bool(adapters and shadow_adapters and len(adapters | shadow_adapters) == 1)


def _shadow_adapter_consistent(rows: tuple[pd.Series, ...]) -> bool:
    adapters = {
        _identity_key(row.get("shadow_broker_adapter", ""))
        for row in rows
        if int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0
        and _identity_key(row.get("shadow_broker_adapter", ""))
    }
    return bool(
        adapters
        and len(adapters) == 1
        and _shadow_counter_max(rows, "shadow_broker_adapter_count") == 1
    )


def _shadow_adapter_value(rows: tuple[pd.Series, ...]) -> str:
    for row in rows:
        adapter = _identity_key(row.get("shadow_broker_adapter", ""))
        if adapter:
            return adapter
    return ""


def _prefixed_shadow_adapter_value(rows: tuple[pd.Series, ...], *, source_prefix: str) -> str:
    for row in rows:
        adapter = _identity_key(row.get(f"{source_prefix}_adapter", ""))
        if adapter:
            return adapter
    return ""


def _shadow_identity_value(rows: tuple[pd.Series, ...], proof_name: str, column: str) -> str:
    proof_column = f"shadow_broker_{proof_name}_{column}"
    for row in rows:
        value = _identity_key(row.get(proof_column, ""))
        if value:
            return value
    return ""


def _prefixed_shadow_identity_value(
    rows: tuple[pd.Series, ...],
    *,
    source_prefix: str,
    proof_name: str,
    column: str,
) -> str:
    proof_column = f"{source_prefix}_{proof_name}_{column}"
    for row in rows:
        value = _identity_key(row.get(proof_column, ""))
        if value:
            return value
    return ""


def _shadow_identity_mismatches(rows: tuple[pd.Series, ...], proof_name: str) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _identity_key(row.get(f"shadow_broker_{proof_name}_{column}", ""))
            for row in rows
            if int(_number(row, f"shadow_broker_{proof_name}_sessions", 0.0)) > 0
            and _identity_key(row.get(f"shadow_broker_{proof_name}_{column}", ""))
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_enable_failed_checks(*rows: pd.Series) -> int:
    return max(int(_number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)) for row in rows)


def _route_readiness_recommendation(*rows: pd.Series) -> str:
    for row in rows:
        text = _text(row, "route_readiness_recommendation")
        if text:
            return text
    return ""


def _broker_schema_text(rows: tuple[pd.Series, ...], column: str) -> str:
    for row in rows:
        text = _text(row, column)
        if text:
            return text
    return ""


def _broker_schema_reviewed(rows: tuple[pd.Series, ...]) -> bool:
    values = [_to_bool(row.get("broker_schema_reviewed", False)) for row in rows if not row.empty]
    return bool(values and all(values))


def _route_identity_value(row: pd.Series, column: str) -> str:
    proof_column = f"route_dispatch_roundtrip_{column}"
    if column == "scenario_key":
        return _text(row, proof_column)
    return _identity_key(row.get(proof_column, ""))


def _route_readiness_identity_value(row: pd.Series, column: str) -> str:
    return _identity_key(row.get(f"route_readiness_{column}", ""))


def _identity_mismatches(*rows: pd.Series) -> int:
    mismatches = 0
    for column in ("target_mode", "strategy", "market", "scenario_key", "adapter"):
        values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        if len(values) > 1:
            mismatches += 1
    return mismatches


def _identity_value(row: pd.Series, column: str) -> str:
    if column == "scenario_key":
        return _text(row, column)
    return _identity_key(row.get(column, ""))


def _component_failed_checks(*rows: pd.Series) -> int:
    return int(sum(int(_number(row, "failed_checks", 0.0)) for row in rows))


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch round-trip input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch round-trip input is empty: {name}")
    return frame


def _read_optional_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _validate_thresholds(thresholds: BrokerDispatchRoundTripThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    for name in (
        "max_duplicate_ack_orders",
        "max_unmatched_acks",
        "max_missing_request_acks",
        "max_total_failed_component_checks",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _object_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
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
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready", "accepted"}
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
