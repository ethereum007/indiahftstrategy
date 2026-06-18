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


ACCEPTED_ACK_STATUSES = {
    "accepted",
    "ack",
    "acked",
    "acknowledged",
    "queued",
    "submitted",
    "dry_run_accepted",
    "success",
    "ok",
}
REJECTED_ACK_STATUSES = {"reject", "rejected", "error", "failed", "denied", "blocked"}


@dataclass(frozen=True)
class BrokerDispatchAckThresholds:
    require_dispatch_ready: bool = True
    require_all_acked: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0


@dataclass(frozen=True)
class BrokerDispatchAckReport:
    acknowledgements: pd.DataFrame
    unmatched_acks: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_broker_dispatch_acknowledgements(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    broker_acks: pd.DataFrame,
    dispatch_config: dict[str, Any] | None = None,
    thresholds: BrokerDispatchAckThresholds | None = None,
) -> BrokerDispatchAckReport:
    thresholds = thresholds or BrokerDispatchAckThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    dispatch_config = dispatch_config or {}
    broker_acks = _normalize_acks(broker_acks)
    summary_row = _dispatch_summary_state(dispatch_summary.iloc[0], dispatch_config)
    acknowledgements = _acknowledgements(dispatch_orders, broker_acks)
    unmatched = _unmatched_acks(dispatch_orders, broker_acks)
    checks = _checks(summary_row, acknowledgements, unmatched, thresholds)
    summary = _summary(summary_row, acknowledgements, unmatched, checks, thresholds)
    config = _config(summary.iloc[0], thresholds, checks)
    return BrokerDispatchAckReport(
        acknowledgements=acknowledgements,
        unmatched_acks=unmatched,
        checks=checks,
        summary=summary,
        config=config,
    )


def write_broker_dispatch_acknowledgements(
    *,
    dispatch_dir: str | Path,
    acks_path: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchAckThresholds | None = None,
) -> BrokerDispatchAckReport:
    dispatch = Path(dispatch_dir)
    acks = Path(acks_path)
    if not acks.exists():
        raise FileNotFoundError(f"broker acknowledgement file not found: {acks}")
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
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=_read_required(dispatch_summary_path, "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch_orders_path, "broker_dispatch_orders"),
        broker_acks=pd.read_csv(acks),
        dispatch_config=dispatch_config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.acknowledgements.to_csv(out / "broker_dispatch_acknowledgements.csv", index=False)
    report.unmatched_acks.to_csv(out / "broker_dispatch_unmatched_acks.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_ack_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_ack_summary.csv", index=False)
    (out / "broker_dispatch_ack_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_ack_reconciliation",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchAckThresholds())},
        inputs=_manifest_inputs(
            dispatch_summary=dispatch_summary_path,
            dispatch_orders=dispatch_orders_path,
            dispatch_config=dispatch_config_path,
            dispatch_manifest=dispatch_manifest_path,
            broker_acks=acks,
        ),
    )
    return BrokerDispatchAckReport(
        report.acknowledgements,
        report.unmatched_acks,
        report.checks,
        report.summary,
        report.config,
        out,
    )


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


def _acknowledgements(dispatch_orders: pd.DataFrame, acks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, order in dispatch_orders.reset_index(drop=True).iterrows():
        matches, match_key = _matching_acks(order, acks)
        status = _latest_text(matches, "ack_status")
        broker_order_id = _latest_text(matches, "broker_order_id")
        ack_ts_ns = _latest_number(matches, "ack_ts_ns")
        dispatch_route_batch_id = _text(order, "route_dispatch_roundtrip_batch_id")
        ack_route_batch_ids = _unique_text_values(matches, "route_dispatch_roundtrip_batch_id")
        ack_count = int(len(matches))
        rows.append(
            {
                "dispatch_batch_id": _text(order, "dispatch_batch_id"),
                "dispatch_order_id": _text(order, "dispatch_order_id"),
                "route_dispatch_roundtrip_batch_id": (
                    ack_route_batch_ids[0] if len(ack_route_batch_ids) == 1 else dispatch_route_batch_id
                ),
                "dispatch_order_route_roundtrip_batch_id": dispatch_route_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": "|".join(ack_route_batch_ids),
                "source_order_id": _text(order, "source_order_id"),
                "target_mode": _text(order, "target_mode"),
                "strategy": _text(order, "strategy"),
                "market": _text(order, "market"),
                "adapter": _text(order, "adapter"),
                "ack_count": ack_count,
                "ack_status": status,
                "broker_order_id": broker_order_id,
                "ack_ts_ns": ack_ts_ns,
                "match_key": match_key,
                "acked": status in ACCEPTED_ACK_STATUSES,
                "rejected": status in REJECTED_ACK_STATUSES,
                "duplicate_ack": ack_count > 1,
                "missing_ack": ack_count == 0,
            }
        )
    return pd.DataFrame(rows)


def _unmatched_acks(dispatch_orders: pd.DataFrame, acks: pd.DataFrame) -> pd.DataFrame:
    if acks.empty:
        return acks
    dispatch_ids = set(dispatch_orders.get("dispatch_order_id", pd.Series(dtype=object)).dropna().astype(str))
    source_ids = set(dispatch_orders.get("source_order_id", pd.Series(dtype=object)).dropna().astype(str))
    matched = pd.Series(False, index=acks.index)
    if "dispatch_order_id" in acks.columns:
        matched = matched | acks["dispatch_order_id"].astype(str).isin(dispatch_ids)
    if "source_order_id" in acks.columns:
        matched = matched | acks["source_order_id"].astype(str).isin(source_ids)
    return acks.loc[~matched].reset_index(drop=True)


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
        _apply_shadow_broker_readiness_config(
            state,
            shadow_broker,
            field_prefix="shadow_broker",
        )
    route_broker_shadow = config.get("route_broker_shadow_broker_readiness", {}) or {}
    if route_broker_shadow:
        _apply_shadow_broker_readiness_config(
            state,
            route_broker_shadow,
            field_prefix="route_broker_shadow_broker",
        )
    broker_vendor_market_data_batch, broker_vendor_source_prefix = _broker_vendor_market_data_batch_source(
        state,
        config,
    )
    broker_vendor_data_readiness, broker_vendor_readiness_source_prefix = _broker_vendor_data_readiness_source(
        config,
    )
    if broker_vendor_data_readiness:
        _apply_broker_vendor_data_readiness_config(
            state,
            broker_vendor_data_readiness,
            field_prefix="ack_broker_vendor_data_readiness",
            fallback_prefix=broker_vendor_readiness_source_prefix,
        )
    else:
        _copy_broker_vendor_data_readiness_fields(
            state,
            source_prefix=broker_vendor_readiness_source_prefix,
            field_prefix="ack_broker_vendor_data_readiness",
        )
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            broker_vendor_market_data_batch,
            field_prefix="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            fallback_prefix=broker_vendor_source_prefix,
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix=broker_vendor_source_prefix,
            field_prefix="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    vendor_market_data_batch = (
        config.get("dispatch_vendor_market_data_batch", {})
        or config.get("route_vendor_market_data_batch", {})
        or {}
    )
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            vendor_market_data_batch,
            field_prefix="ack_vendor_market_data_batch",
            fallback_prefix="route_vendor_market_data_batch",
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix="route_vendor_market_data_batch",
            field_prefix="ack_vendor_market_data_batch",
        )
    return state


def _broker_vendor_market_data_batch_source(
    state: pd.Series,
    config: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    candidates = (
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    )
    vendor, field_prefix = select_vendor_market_data_batch_source(
        config,
        candidates,
        default_source="route_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    if vendor:
        return vendor, field_prefix
    if any(
        f"dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_{suffix}" in state
        for suffix in ("provided", "dataset_count", "datasets_json")
    ):
        return {}, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {}, "route_broker_dispatch_roundtrip_vendor_market_data_batch"


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
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
    return {}, "dispatch_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    dispatch_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = select_vendor_market_data_batch_source(
        dispatch_config,
        (
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="route_broker_dispatch_roundtrip_vendor_market_data_batch",
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
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(dispatch_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(broker_readiness_config)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    if not should_hydrate_vendor and not should_hydrate_readiness:
        return dispatch_config

    out = dict(dispatch_config)
    if should_hydrate_vendor:
        out["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out["route_broker_vendor_data_readiness"] = dict(sidecar_readiness)
    return out


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
    state[f"{field_prefix}_source_file_fingerprint_coverage"] = _number_value(
        vendor.get("source_file_fingerprint_coverage"),
        _number(state, f"{fallback_prefix}_source_file_fingerprint_coverage", 0.0),
    )
    state[f"{field_prefix}_min_mapping_coverage"] = _number_value(
        vendor.get("min_mapping_coverage"),
        _number(state, f"{fallback_prefix}_min_mapping_coverage", 0.0),
    )
    state[f"{field_prefix}_unique_mapping_drafts"] = int(
        _number_value(
            vendor.get("unique_mapping_drafts"),
            _number(state, f"{fallback_prefix}_unique_mapping_drafts", 0.0),
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
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_mapping_drafts",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        state[f"{field_prefix}_{suffix}"] = state.get(f"{source_prefix}_{suffix}", "")


def _apply_broker_vendor_data_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
    fallback_prefix: str,
) -> None:
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    state[f"{field_prefix}_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{fallback_prefix}_provided", active_config))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        readiness.get("ready", state.get(f"{fallback_prefix}_ready", False))
    )
    state[f"{field_prefix}_failed_checks"] = _broker_vendor_data_readiness_failed_checks(
        readiness,
        fallback=_number(state, f"{fallback_prefix}_failed_checks", 0.0),
    )


def _copy_broker_vendor_data_readiness_fields(
    state: pd.Series,
    *,
    source_prefix: str,
    field_prefix: str,
) -> None:
    state[f"{field_prefix}_provided"] = state.get(f"{source_prefix}_provided", False)
    state[f"{field_prefix}_ready"] = state.get(f"{source_prefix}_ready", False)
    state[f"{field_prefix}_failed_checks"] = state.get(f"{source_prefix}_failed_checks", 0)


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
    vendor_readiness = readiness.get("broker_vendor_data_readiness", {}) or {}
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
    state[f"{field_prefix}_vendor_data_readiness_sessions"] = int(
        _number_value(
            vendor_readiness.get("sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_provided_sessions"] = int(
        _number_value(
            vendor_readiness.get("provided_sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_ready_sessions"] = int(
        _number_value(
            vendor_readiness.get("ready_sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_failed_checks"] = int(
        _number_value(
            vendor_readiness.get("failed_checks"),
            _number(state, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0),
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
    acknowledgements: pd.DataFrame,
    unmatched_acks: pd.DataFrame,
    thresholds: BrokerDispatchAckThresholds,
) -> pd.DataFrame:
    dispatch_ready = _to_bool(dispatch_summary.get("ready", False))
    orders = int(len(acknowledgements))
    acked = int(acknowledgements["acked"].astype(bool).sum()) if orders else 0
    rejected = int(acknowledgements["rejected"].astype(bool).sum()) if orders else 0
    missing = int(acknowledgements["missing_ack"].astype(bool).sum()) if orders else 0
    duplicates = int(acknowledgements["duplicate_ack"].astype(bool).sum()) if orders else 0
    route_readiness_required = _route_readiness_required(dispatch_summary, thresholds)
    route_readiness_active = bool(
        route_readiness_required or _to_bool(dispatch_summary.get("route_readiness_provided", False))
    )
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                dispatch_ready,
                "is",
                True,
                dispatch_ready or not thresholds.require_dispatch_ready,
                "broker dispatch plan is not ready",
            ),
            _check(
                "all_dispatch_orders_acked",
                acked,
                "==",
                orders,
                (acked == orders and missing == 0) or not thresholds.require_all_acked,
                "not every dispatch order has an accepted acknowledgement",
            ),
            _check(
                "rejected_orders",
                rejected,
                "==",
                0,
                rejected == 0 or thresholds.allow_rejections,
                "broker acknowledgements include rejected orders",
            ),
            _check(
                "duplicate_ack_orders",
                duplicates,
                "<=",
                thresholds.max_duplicate_ack_orders,
                duplicates <= thresholds.max_duplicate_ack_orders,
                "duplicate acknowledgements exceeded threshold",
            ),
            _check(
                "unmatched_acks",
                int(len(unmatched_acks)),
                "<=",
                thresholds.max_unmatched_acks,
                int(len(unmatched_acks)) <= thresholds.max_unmatched_acks,
                "broker acknowledgement file contains unmatched rows",
            ),
            _check(
                "route_readiness_provided",
                _to_bool(dispatch_summary.get("route_readiness_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_readiness_provided", False)) or not route_readiness_required,
                "ack reconciliation requires dispatch plan with route-readiness proof",
            ),
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
    if _dispatch_roundtrip_required(dispatch_summary, thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    ):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_dispatch_roundtrip_checks(dispatch_summary)),
                pd.DataFrame(_route_batch_continuity_checks(dispatch_summary, acknowledgements)),
            ],
            ignore_index=True,
        )
    if _broker_vendor_data_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_broker_vendor_data_readiness_checks(dispatch_summary)),
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
            "dispatch route-readiness strategy does not match acknowledgement strategy",
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
            "dispatch route-readiness market does not match acknowledgement market",
        ),
    ]


def _dispatch_roundtrip_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    target_mode = _identity_key(dispatch_summary.get("target_mode", ""))
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    scenario = _text(dispatch_summary, "scenario_key")
    route_enable_failed_checks = int(
        _number(dispatch_summary, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
    )
    return [
        _check(
            "route_dispatch_roundtrip_provided",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
            "ack reconciliation requires dispatch plan with route round-trip proof",
        ),
        _check(
            "route_dispatch_roundtrip_ready",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "dispatch route round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_batch_id_provided",
            _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "nonempty",
            True,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_batch_id")),
            "dispatch route round-trip proof batch id is missing",
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
            "dispatch route round-trip target mode does not match acknowledgement target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")) == strategy
            ),
            "dispatch route round-trip strategy does not match acknowledgement strategy",
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
            "dispatch route round-trip market does not match acknowledgement market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key"),
            "==",
            scenario,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") and scenario)
            and _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") == scenario,
            "dispatch route round-trip scenario does not match acknowledgement scenario",
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
        _check(
            "route_enable_dispatch_roundtrip_failed_checks",
            route_enable_failed_checks,
            "<=",
            0,
            route_enable_failed_checks <= 0,
            "route-enable dispatch round-trip has failed component checks",
        ),
    ]


def _route_batch_continuity_checks(
    dispatch_summary: pd.Series,
    acknowledgements: pd.DataFrame,
) -> list[dict[str, object]]:
    route_batch_id = _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
    dispatch_order_batches = _unique_text_values(acknowledgements, "dispatch_order_route_roundtrip_batch_id")
    ack_route_batches = _unique_pipe_text_values(acknowledgements, "ack_route_dispatch_roundtrip_batch_ids")
    matched = acknowledgements.loc[acknowledgements["ack_count"].astype(int) > 0] if not acknowledgements.empty else acknowledgements
    missing_ack_route_batches = (
        int((matched["ack_route_dispatch_roundtrip_batch_ids"].astype(str).str.strip() == "").sum())
        if not matched.empty and "ack_route_dispatch_roundtrip_batch_ids" in matched.columns
        else 0
    )
    return [
        _check(
            "dispatch_order_route_roundtrip_batch_matches",
            "|".join(dispatch_order_batches),
            "==",
            route_batch_id,
            bool(route_batch_id and len(dispatch_order_batches) == 1 and dispatch_order_batches[0] == route_batch_id),
            "dispatch order route proof batch ids do not match dispatch summary",
        ),
        _check(
            "ack_route_roundtrip_batch_matches",
            f"{'|'.join(ack_route_batches)}; missing={missing_ack_route_batches}",
            "==",
            route_batch_id,
            bool(
                route_batch_id
                and missing_ack_route_batches == 0
                and len(ack_route_batches) == 1
                and ack_route_batches[0] == route_batch_id
            ),
            "broker acknowledgement route proof batch ids do not match dispatch summary",
        ),
    ]


def _shadow_broker_readiness_active(dispatch_summary: pd.Series) -> bool:
    session_columns = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_vendor_data_readiness_sessions",
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
                    "send_shadow_broker_readiness_ready",
                    ready_sessions,
                    "==",
                    sessions,
                    ready_sessions == sessions,
                    "sender shadow broker-readiness evidence is not ready for every carried session",
                ),
                _check(
                    "send_shadow_broker_adapter_matches",
                    shadow_adapter,
                    "==",
                    adapter,
                    bool(shadow_adapter and adapter and shadow_adapter == adapter),
                    "sender shadow broker adapter does not match acknowledgement adapter",
                ),
                _check(
                    "send_shadow_broker_adapter_consistent",
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)) == 1,
                    "sender shadow broker adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_sessions", 0.0))
    if vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    "send_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
                    vendor_sessions,
                    "==",
                    sessions,
                    vendor_sessions == sessions,
                    "sender shadow broker vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    "send_shadow_broker_vendor_data_readiness_provided",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)),
                    "==",
                    sessions,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0))
                    == sessions,
                    "sender shadow broker vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    "send_shadow_broker_vendor_data_readiness_ready",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)),
                    "==",
                    sessions,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0))
                    == sessions,
                    "sender shadow broker vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    "send_shadow_broker_vendor_data_readiness_failed_checks",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)) <= 0,
                    "sender shadow broker vendor-data wrapper proof has failed checks",
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
                    "send_shadow_broker_route_readiness_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0)),
                    "==",
                    route_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0))
                    == route_sessions,
                    "sender shadow broker route-readiness proof is not ready for every carried session",
                ),
                _check(
                    "send_shadow_broker_route_readiness_strategy_matches",
                    route_strategy,
                    "==",
                    strategy,
                    bool(route_strategy and strategy and route_strategy == strategy),
                    "sender shadow broker route-readiness strategy does not match acknowledgement strategy",
                ),
                _check(
                    "send_shadow_broker_route_readiness_market_matches",
                    route_market,
                    "==",
                    market,
                    bool(route_market and market and route_market == market),
                    "sender shadow broker route-readiness market does not match acknowledgement market",
                ),
                _check(
                    "send_shadow_broker_route_readiness_gap_pairs",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)) <= 0,
                    "sender shadow broker route-readiness proof has route gaps",
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
                    "send_shadow_broker_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0))
                    == dispatch_sessions,
                    "sender shadow broker dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_strategy_matches",
                    dispatch_strategy,
                    "==",
                    strategy,
                    bool(dispatch_strategy and strategy and dispatch_strategy == strategy),
                    "sender shadow broker dispatch round-trip strategy does not match acknowledgement strategy",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_market_matches",
                    dispatch_market,
                    "==",
                    market,
                    bool(dispatch_market and market and dispatch_market == market),
                    "sender shadow broker dispatch round-trip market does not match acknowledgement market",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "sender shadow broker dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_missing_request_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0))
                    <= 0,
                    "sender shadow broker dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_rejected_orders",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
                    "sender shadow broker dispatch round-trip has rejected orders",
                ),
                _check(
                    "send_shadow_broker_dispatch_roundtrip_unmatched_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
                    "sender shadow broker dispatch round-trip has unmatched acknowledgements",
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
                    "send_shadow_broker_route_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    route_dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0))
                    == route_dispatch_sessions,
                    "sender shadow broker route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "send_shadow_broker_route_dispatch_roundtrip_strategy_matches",
                    route_dispatch_strategy,
                    "==",
                    strategy,
                    bool(route_dispatch_strategy and strategy and route_dispatch_strategy == strategy),
                    "sender shadow broker route dispatch round-trip strategy does not match acknowledgement strategy",
                ),
                _check(
                    "send_shadow_broker_route_dispatch_roundtrip_market_matches",
                    route_dispatch_market,
                    "==",
                    market,
                    bool(route_dispatch_market and market and route_dispatch_market == market),
                    "sender shadow broker route dispatch round-trip market does not match acknowledgement market",
                ),
                _check(
                    "send_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "sender shadow broker route dispatch round-trip scenario is missing or mixed",
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
            "send_broker_shadow_broker_readiness_provided",
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "sender broker-readiness shadow broker proof is active but not marked provided",
        )
    ]
    mapped = _shadow_broker_projection(dispatch_summary, source_prefix=source_prefix)
    for check in _shadow_broker_readiness_checks(mapped):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "send_shadow_broker",
            "send_broker_shadow_broker",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "sender shadow broker",
                "sender broker-readiness shadow broker",
            )
        checks.append(renamed)
    return checks


def _vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "ack_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _broker_vendor_data_readiness_active(dispatch_summary: pd.Series) -> bool:
    prefix = "ack_broker_vendor_data_readiness"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)) > 0
    )


def _broker_vendor_data_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "ack_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
            "ack broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            "ack broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)) <= 0,
            "ack broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "ack_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    return [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "ack vendor market-data manifest is not a vendor batch pipeline proof",
        )
    ]


def _broker_vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _broker_vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    return [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "ack broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            _number(dispatch_summary, f"{prefix}_source_file_fingerprint_coverage", 0.0),
            ">=",
            1.0,
            _number(dispatch_summary, f"{prefix}_source_file_fingerprint_coverage", 0.0) >= 1.0,
            "ack broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            _number(dispatch_summary, f"{prefix}_min_mapping_coverage", 0.0),
            ">=",
            1.0,
            _number(dispatch_summary, f"{prefix}_min_mapping_coverage", 0.0) >= 1.0,
            "ack broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(_number(dispatch_summary, f"{prefix}_unique_mapping_drafts", 0.0)),
            ">",
            0,
            int(_number(dispatch_summary, f"{prefix}_unique_mapping_drafts", 0.0)) > 0,
            "ack broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
    ]


def _shadow_broker_projection(dispatch_summary: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = dispatch_summary.copy()
    for suffix in (
        "readiness_sessions",
        "readiness_ready_sessions",
        "vendor_data_readiness_sessions",
        "vendor_data_readiness_provided_sessions",
        "vendor_data_readiness_ready_sessions",
        "vendor_data_readiness_failed_checks",
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
        f"{field_prefix}_vendor_data_readiness_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_provided_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0)
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
    acknowledgements: pd.DataFrame,
    unmatched_acks: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerDispatchAckThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    orders = int(len(acknowledgements))
    acked = int(acknowledgements["acked"].astype(bool).sum()) if orders else 0
    rejected = int(acknowledgements["rejected"].astype(bool).sum()) if orders else 0
    missing = int(acknowledgements["missing_ack"].astype(bool).sum()) if orders else 0
    duplicates = int(acknowledgements["duplicate_ack"].astype(bool).sum()) if orders else 0
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "target_mode": _text(dispatch_summary, "target_mode"),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "broker_schema_status": _text(dispatch_summary, "broker_schema_status"),
                "broker_schema_reviewed": _to_bool(dispatch_summary.get("broker_schema_reviewed", False)),
                "broker_schema_review_mode": _text(dispatch_summary, "broker_schema_review_mode"),
                "dispatch_orders": orders,
                "acked_orders": acked,
                "missing_acks": missing,
                "rejected_orders": rejected,
                "duplicate_ack_orders": duplicates,
                "unmatched_acks": int(len(unmatched_acks)),
                "route_readiness_required": _route_readiness_required(dispatch_summary, thresholds),
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
                "shadow_broker_vendor_data_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)
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
                **_broker_vendor_data_readiness_summary_fields(
                    dispatch_summary,
                    field_prefix="ack_broker_vendor_data_readiness",
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="ack_vendor_market_data_batch",
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
                "ack_rate": acked / orders if orders else 0.0,
                "failed_checks": failed,
                "recommendation": "broker_dispatch_acknowledged" if passed else "investigate_broker_dispatch_acks",
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
        "broker_vendor_data_readiness": {
            "sessions": int(summary[f"{field_prefix}_vendor_data_readiness_sessions"]),
            "provided_sessions": int(summary[f"{field_prefix}_vendor_data_readiness_provided_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(summary[f"{field_prefix}_vendor_data_readiness_failed_checks"]),
        },
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
        f"{field_prefix}_source_file_fingerprint_coverage": _number(
            dispatch_summary, f"{field_prefix}_source_file_fingerprint_coverage", 0.0
        ),
        f"{field_prefix}_min_mapping_coverage": _number(
            dispatch_summary, f"{field_prefix}_min_mapping_coverage", 0.0
        ),
        f"{field_prefix}_unique_mapping_drafts": int(
            _number(dispatch_summary, f"{field_prefix}_unique_mapping_drafts", 0.0)
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


def _broker_vendor_data_readiness_summary_fields(
    dispatch_summary: pd.Series,
    *,
    field_prefix: str,
) -> dict[str, object]:
    return {
        f"{field_prefix}_provided": _to_bool(dispatch_summary.get(f"{field_prefix}_provided", False)),
        f"{field_prefix}_ready": _to_bool(dispatch_summary.get(f"{field_prefix}_ready", False)),
        f"{field_prefix}_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_failed_checks", 0.0)
        ),
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


def _broker_vendor_data_readiness_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "failed_checks": int(summary[f"{field_prefix}_failed_checks"]),
    }


def _config(summary: pd.Series, thresholds: BrokerDispatchAckThresholds, checks: pd.DataFrame) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    return {
        "schema_version": 1,
        "passed": _to_bool(summary["passed"]),
        "failed_check_count": len(failed_check_records),
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
        "dispatch_orders": int(summary["dispatch_orders"]),
        "acked_orders": int(summary["acked_orders"]),
        "missing_acks": int(summary["missing_acks"]),
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
            "provided": int(summary["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(summary["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(summary["shadow_broker_readiness_ready_sessions"]),
            "adapter": _text(summary, "shadow_broker_adapter"),
            "adapter_count": int(summary["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(summary["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(summary["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(summary["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
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
        "ack_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(
            summary,
            field_prefix="ack_broker_vendor_data_readiness",
        ),
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "ack_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="ack_vendor_market_data_batch",
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
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
    }


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [_jsonable_check_record(row) for row in failed.to_dict(orient="records")]


def _jsonable_check_record(row: dict[str, Any]) -> dict[str, object]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _matching_acks(order: pd.Series, acks: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if acks.empty:
        return acks, ""
    dispatch_order_id = _text(order, "dispatch_order_id")
    if dispatch_order_id and "dispatch_order_id" in acks.columns:
        matches = acks.loc[acks["dispatch_order_id"].astype(str).str.strip() == dispatch_order_id]
        if not matches.empty:
            return matches, "dispatch_order_id"
    source_order_id = _text(order, "source_order_id")
    if source_order_id and "source_order_id" in acks.columns:
        matches = acks.loc[acks["source_order_id"].astype(str).str.strip() == source_order_id]
        if not matches.empty:
            return matches, "source_order_id"
    return acks.iloc[:0], ""


def _normalize_acks(acks: pd.DataFrame) -> pd.DataFrame:
    frame = acks.copy().reset_index(drop=True)
    if frame.empty:
        return frame
    status_column = _first_column(frame, ("ack_status", "status", "order_status", "broker_status"))
    if status_column:
        frame["ack_status"] = frame[status_column].map(_status_key)
    else:
        frame["ack_status"] = ""
    if "broker_order_id" not in frame.columns:
        frame["broker_order_id"] = ""
    if "ack_ts_ns" not in frame.columns:
        frame["ack_ts_ns"] = pd.NA
    return frame


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    for column in candidates:
        if column in frame.columns:
            return column
    return ""


def _latest_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return str(values.iloc[-1]) if not values.empty else ""


def _latest_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return float("nan")
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else float("nan")


def _number_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _unique_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(set(values.loc[values != ""]))


def _unique_pipe_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    values: set[str] = set()
    if frame.empty or column not in frame.columns:
        return []
    for raw in frame[column].dropna().astype(str):
        for value in raw.split("|"):
            cleaned = value.strip()
            if cleaned:
                values.add(cleaned)
    return sorted(values)


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch acknowledgement input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch acknowledgement input is empty: {name}")
    return frame


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(dispatch_summary: pd.Series, thresholds: BrokerDispatchAckThresholds) -> bool:
    return bool(
        thresholds.require_dispatch_roundtrip
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
    )


def _route_readiness_required(dispatch_summary: pd.Series, thresholds: BrokerDispatchAckThresholds) -> bool:
    return bool(
        thresholds.require_route_readiness
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
        or _to_bool(dispatch_summary.get("route_readiness_required", False))
    )


def _validate_thresholds(thresholds: BrokerDispatchAckThresholds) -> None:
    if thresholds.max_duplicate_ack_orders < 0:
        raise ValueError("max_duplicate_ack_orders must be non-negative")
    if thresholds.max_unmatched_acks < 0:
        raise ValueError("max_unmatched_acks must be non-negative")


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


def _status_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


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
