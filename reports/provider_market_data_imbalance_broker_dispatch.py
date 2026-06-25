from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.broker_dispatch import (
    BrokerDispatchReport,
    BrokerDispatchThresholds,
    write_broker_dispatch_plan,
)
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_dispatch"

ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "action",
    "reason",
    "recommendation",
    "next_gate",
    "next_gate_help_command",
]

VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES = (
    "dispatch_roundtrip_vendor_market_data_batch",
    "broker_dispatch_roundtrip_vendor_market_data_batch",
)
UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES = (
    "upstream_dispatch_roundtrip_vendor_market_data_batch",
    "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
)
VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES = (
    "provided",
    "ready",
    "comparison_accepted",
)
VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES = (
    "dataset_count",
    "ready_datasets",
    "failed_datasets",
    "unique_source_files",
    "unique_header_fingerprints",
    "unique_mapping_drafts",
    "comparison_failed_checks",
)
VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES = (
    "ready_rate",
    "source_file_fingerprint_coverage",
    "min_mapping_coverage",
)
VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES = (
    "adapter",
    "kind",
    "manifest_run_type",
    "market",
    "mapping_sources",
    "datasets_json",
)


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchConfig:
    require_provider_route_enable_ready: bool = True
    require_broker_dispatch_ready: bool = True
    use_provider_route_enable_inputs: bool = True
    target_mode: str = ""
    require_route_enabled: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1
    max_orders: int | None = None


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchReport:
    broker_dispatch: BrokerDispatchReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_imbalance_broker_dispatch(
    provider_route_enable_dir: str | Path,
    output_dir: str | Path,
    *,
    route_enable_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    upload_orders_path: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerDispatchConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerDispatchReport:
    config = config or ProviderMarketDataImbalanceBrokerDispatchConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    provider_root = Path(provider_route_enable_dir)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_route_enable_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_route_enable_config.json"
    )

    resolved_route_enable_dir = _explicit_or_inferred(
        route_enable_dir,
        _inferred_route_enable_dir(provider_summary, provider_config),
        config,
    )
    resolved_upload_pack_dir = _explicit_or_inferred(
        upload_pack_dir,
        _inferred_upload_pack_dir(provider_summary, provider_config),
        config,
    )
    resolved_upload_orders_path = None if upload_orders_path is None else Path(upload_orders_path)
    inferred_provider_dispatch_roundtrip_dir, inferred_dispatch_roundtrip_dir = _inferred_dispatch_roundtrip_dirs(
        provider_summary,
        provider_config,
    )
    inferred_upstream_provider_dispatch_roundtrip_dir, inferred_upstream_dispatch_roundtrip_dir = (
        _inferred_upstream_dispatch_roundtrip_dirs(provider_summary, provider_config)
    )

    prechecks = _prechecks(
        provider_root,
        provider_summary,
        provider_summary_error,
        provider_config_error,
        resolved_route_enable_dir,
        resolved_upload_pack_dir,
        resolved_upload_orders_path,
        config,
    )

    broker_dispatch: BrokerDispatchReport | None = None
    broker_dispatch_error = ""
    broker_dispatch_dir = out / "broker_dispatch"
    if bool(prechecks["passed"].all()):
        try:
            broker_dispatch = write_broker_dispatch_plan(
                route_enable_dir=_path_or_empty(resolved_route_enable_dir),
                upload_pack_dir=_path_or_empty(resolved_upload_pack_dir),
                upload_orders_path=resolved_upload_orders_path,
                output_dir=broker_dispatch_dir,
                thresholds=_thresholds(config, provider_summary),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError, json.JSONDecodeError) as exc:
            broker_dispatch_error = str(exc)
    else:
        broker_dispatch_error = "provider imbalance broker-dispatch prerequisites are not ready"

    checks = _checks(prechecks, broker_dispatch, broker_dispatch_error, provider_summary, config)
    summary = _summary(
        provider_root,
        resolved_route_enable_dir,
        resolved_upload_pack_dir,
        resolved_upload_orders_path,
        inferred_provider_dispatch_roundtrip_dir,
        inferred_dispatch_roundtrip_dir,
        inferred_upstream_provider_dispatch_roundtrip_dir,
        inferred_upstream_dispatch_roundtrip_dir,
        broker_dispatch,
        checks,
        out,
        broker_dispatch_dir,
        provider_summary,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker_dispatch)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        broker_dispatch,
        checks,
        action_queue,
        config,
        {
            "provider_route_enable_dir": provider_root,
            "route_enable_dir": resolved_route_enable_dir,
            "upload_pack_dir": resolved_upload_pack_dir,
            "upload_orders_path": resolved_upload_orders_path,
            "provider_dispatch_roundtrip_dir": inferred_provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": inferred_dispatch_roundtrip_dir,
            "upstream_provider_dispatch_roundtrip_dir": inferred_upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": inferred_upstream_dispatch_roundtrip_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_dispatch_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_dispatch_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_broker_dispatch_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_broker_dispatch_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_dispatch_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_route_enable_dir": provider_root}
    for name, value in {
        "route_enable": resolved_route_enable_dir,
        "upload_pack": resolved_upload_pack_dir,
        "upload_orders": resolved_upload_orders_path,
        "provider_dispatch_roundtrip": inferred_provider_dispatch_roundtrip_dir,
        "dispatch_roundtrip": inferred_dispatch_roundtrip_dir,
        "upstream_provider_dispatch_roundtrip": inferred_upstream_provider_dispatch_roundtrip_dir,
        "upstream_dispatch_roundtrip": inferred_upstream_dispatch_roundtrip_dir,
    }.items():
        if value is not None:
            inputs[name] = Path(value)
    if broker_dispatch is not None and broker_dispatch.output_dir is not None:
        inputs["broker_dispatch"] = broker_dispatch.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "broker_dispatch_inputs": _jsonable(payload["broker_dispatch_inputs"]),
        },
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "broker_dispatch_ready": bool(summary.iloc[0]["broker_dispatch_ready"]),
            "profile": PROFILE,
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
            "dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary.iloc[0]["dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary.iloc[0]["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary.iloc[0]["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary.iloc[0]["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
        },
    )
    return ProviderMarketDataImbalanceBrokerDispatchReport(
        broker_dispatch,
        checks,
        summary,
        action_queue,
        payload,
        out,
    )


def _read_csv(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), f"{path.name} does not exist"
    try:
        return pd.read_csv(path), ""
    except (OSError, pd.errors.ParserError) as exc:
        return pd.DataFrame(), f"{path.name} is not readable: {exc}"


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"{path.name} does not exist"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not readable: {exc}"
    return value if isinstance(value, dict) else {}, ""


def _prechecks(
    provider_root: Path,
    provider_summary: pd.DataFrame,
    provider_summary_error: str,
    provider_config_error: str,
    route_enable_dir: Path | None,
    upload_pack_dir: Path | None,
    upload_orders_path: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchConfig,
) -> pd.DataFrame:
    upload_summary = _summary_path(
        upload_pack_dir,
        "broker_upload_summary.csv",
        fallback_dirs=("05_upload_pack", "04_upload_pack"),
    )
    return pd.DataFrame(
        [
            _check(
                "provider_route_enable_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance route-enable directory is required",
            ),
            _check(
                "provider_route_enable_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider imbalance route-enable summary could not be read",
            ),
            _check(
                "provider_route_enable_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider imbalance route-enable config could not be read",
            ),
            _check(
                "provider_route_enable_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_route_enable_ready,
                "provider imbalance route-enable wrapper is not ready",
            ),
            _check(
                "provider_route_enabled",
                _first_bool(provider_summary, "route_enabled"),
                "is",
                True,
                _first_bool(provider_summary, "route_enabled") or not config.require_route_enabled,
                "provider imbalance route is not enabled for broker dispatch",
            ),
            _check(
                "generic_route_enable_input_resolved",
                _path_text(route_enable_dir),
                "present",
                True,
                bool(route_enable_dir),
                "nested generic route-enable input is required for broker dispatch",
            ),
            _check(
                "nested_route_enable_config_exists",
                _path_text(route_enable_dir),
                "exists",
                True,
                bool(route_enable_dir and (route_enable_dir / "route_enable_config.json").exists()),
                "nested route_enable_config.json is required for broker dispatch",
            ),
            _check(
                "nested_route_enable_summary_exists",
                _path_text(route_enable_dir),
                "exists",
                True,
                bool(route_enable_dir and (route_enable_dir / "route_enable_summary.csv").exists()),
                "nested route_enable_summary.csv is required for broker dispatch",
            ),
            _check(
                "upload_pack_input_resolved",
                _path_text(upload_pack_dir),
                "present",
                True,
                bool(upload_pack_dir),
                "broker upload pack input is required for broker dispatch",
            ),
            _check(
                "upload_pack_summary_exists",
                _path_text(upload_summary),
                "exists",
                True,
                bool(upload_summary and upload_summary.exists()),
                "broker_upload_summary.csv is required for broker dispatch",
            ),
            _check(
                "upload_orders_path_exists",
                _path_text(upload_orders_path),
                "exists",
                True,
                upload_orders_path is None or upload_orders_path.exists(),
                "explicit upload-orders CSV does not exist",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker_dispatch: BrokerDispatchReport | None,
    broker_dispatch_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    broker_summary = broker_dispatch.summary if broker_dispatch is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_dispatch_runnable",
            broker_dispatch_error or ("ran" if broker_dispatch is not None else "not_run"),
            "is",
            "ran",
            broker_dispatch is not None and not broker_dispatch_error,
            broker_dispatch_error or "generic broker dispatch planner was not run",
        )
    )
    rows.append(
        _check(
            "broker_dispatch_ready",
            bool(broker_dispatch is not None and broker_dispatch.ready),
            "is",
            True,
            bool(broker_dispatch is not None and (broker_dispatch.ready or not config.require_broker_dispatch_ready)),
            _broker_dispatch_failure_reason(broker_dispatch) or "broker dispatch plan is not ready",
        )
    )
    strategy = _first_text(broker_summary, "strategy") or _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            bool(broker_dispatch is not None) and _identity_key(strategy) == PROFILE,
            "broker dispatch plan did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    dispatch_market = _first_text(broker_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            dispatch_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker_dispatch is not None)
            and (not expected_market or _identity_key(dispatch_market) == _identity_key(expected_market)),
            "broker dispatch market identity does not match provider route-enable",
        )
    )
    expected_adapter = _first_text(provider_summary, "adapter")
    dispatch_adapter = _first_text(broker_summary, "adapter")
    rows.append(
        _check(
            "adapter_identity_consistent",
            dispatch_adapter or expected_adapter,
            "is",
            expected_adapter or "present",
            bool(broker_dispatch is not None)
            and (not expected_adapter or _identity_key(dispatch_adapter) == _identity_key(expected_adapter)),
            "broker dispatch adapter identity does not match provider route-enable",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    provider_root: Path,
    route_enable_dir: Path | None,
    upload_pack_dir: Path | None,
    upload_orders_path: Path | None,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
    broker_dispatch: BrokerDispatchReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    broker_dispatch_dir: Path,
    provider_summary: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    dispatch_summary = broker_dispatch.summary if broker_dispatch is not None else pd.DataFrame()
    dispatch_dir = broker_dispatch_dir if broker_dispatch is None else Path(broker_dispatch.output_dir or broker_dispatch_dir)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_route_enable_ready": _first_bool(provider_summary, "ready"),
                "broker_dispatch_ready": bool(broker_dispatch is not None and broker_dispatch.ready),
                "provider_route_enable_dir": str(provider_root),
                "route_enable_dir": _path_text(route_enable_dir),
                "upload_pack_dir": _path_text(upload_pack_dir),
                "upload_orders_path": _path_text(upload_orders_path),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "upstream_provider_dispatch_roundtrip_dir": _path_text(upstream_provider_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_dir": _path_text(upstream_dispatch_roundtrip_dir),
                "upstream_dispatch_roundtrip_provided": bool(upstream_dispatch_roundtrip_dir)
                or _first_bool(provider_summary, "upstream_dispatch_roundtrip_provided"),
                "upstream_dispatch_roundtrip_ready": _first_bool(
                    provider_summary,
                    "upstream_dispatch_roundtrip_ready",
                ),
                "upstream_dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "upstream_dispatch_roundtrip_failed_checks")
                ),
                "dispatch_roundtrip_provided": _first_bool(provider_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(provider_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "dispatch_roundtrip_failed_checks")
                ),
                **_vendor_market_data_batch_summary_fields(provider_summary),
                "broker_dispatch_dir": str(dispatch_dir),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(dispatch_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(dispatch_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(dispatch_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(dispatch_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(dispatch_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "route_state": _first_text(provider_summary, "route_state") or "disabled",
                "route_enabled": _first_bool(provider_summary, "route_enabled"),
                "dispatch_state": _first_text(dispatch_summary, "dispatch_state") or "disabled",
                "dispatch_orders": int(_first_number(dispatch_summary, "dispatch_orders")),
                "route_upload_orders": int(_first_number(dispatch_summary, "route_upload_orders")),
                "max_orders_per_session": int(_first_number(dispatch_summary, "max_orders_per_session")),
                "max_notional_per_session": float(_first_number(dispatch_summary, "max_notional_per_session")),
                "dispatch_total_notional": float(_first_number(dispatch_summary, "dispatch_total_notional")),
                "dry_run_only": _first_bool(dispatch_summary, "dry_run_only"),
                "upload_file_hash": _first_text(dispatch_summary, "upload_file_hash"),
                "dispatch_batch_id": _first_text(dispatch_summary, "dispatch_batch_id"),
                "route_readiness_required": _first_bool(dispatch_summary, "route_readiness_required")
                or _first_bool(provider_summary, "route_readiness_required"),
                "route_readiness_ready": _first_bool(dispatch_summary, "route_readiness_ready")
                or _first_bool(provider_summary, "route_readiness_ready"),
                "route_readiness_gap_pairs": int(
                    _first_number(dispatch_summary, "route_readiness_gap_pairs")
                    or _first_number(provider_summary, "route_readiness_gap_pairs")
                ),
                "provider_route_enable_recommendation": _first_text(provider_summary, "route_enable_recommendation")
                or _first_text(provider_summary, "recommendation"),
                "broker_dispatch_recommendation": _first_text(dispatch_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "prepare_provider_imbalance_broker_dispatch_send"
                if ready
                else "repair_provider_imbalance_broker_dispatch",
                "next_gate": "prepare-broker-dispatch-send"
                if ready
                else _blocked_next_gate(checks, broker_dispatch),
                "next_gate_help_command": _help_command_for_gate(
                    "prepare-broker-dispatch-send" if ready else _blocked_next_gate(checks, broker_dispatch)
                ),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _vendor_market_data_batch_summary_fields(provider_summary: pd.DataFrame) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for prefix in (
        *VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES,
        *UPSTREAM_VENDOR_MARKET_DATA_BATCH_SUMMARY_PREFIXES,
    ):
        for suffix in VENDOR_MARKET_DATA_BATCH_BOOL_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_bool(provider_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_INT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = int(_first_number(provider_summary, f"{prefix}_{suffix}"))
        for suffix in VENDOR_MARKET_DATA_BATCH_FLOAT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_number(provider_summary, f"{prefix}_{suffix}")
        for suffix in VENDOR_MARKET_DATA_BATCH_TEXT_SUFFIXES:
            fields[f"{prefix}_{suffix}"] = _first_text(provider_summary, f"{prefix}_{suffix}")
    return fields


def _vendor_market_data_batch_config(provider_config: dict[str, Any], key: str) -> dict[str, Any]:
    vendor = provider_config.get(key, {})
    return dict(vendor) if isinstance(vendor, dict) else {}


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    if not action_queue.empty:
        out["primary_action_status"] = str(action_queue.iloc[0].get("queue_status", ""))
        out["next_gate"] = str(action_queue.iloc[0].get("next_gate", out.iloc[0].get("next_gate", "")))
        out["next_gate_help_command"] = str(
            action_queue.iloc[0].get("next_gate_help_command", out.iloc[0].get("next_gate_help_command", ""))
        )
    return out


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    broker_dispatch: BrokerDispatchReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_dispatch_summary",
                    "component": "broker_dispatch",
                    "check": "broker_dispatch_ready",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "prepare_provider_imbalance_broker_dispatch_send",
                    "reason": "provider imbalance broker dispatch plan is ready for dry-run send preparation",
                    "recommendation": "prepare_non_submitting_broker_dispatch_send_packet",
                    "next_gate": "prepare-broker-dispatch-send",
                    "next_gate_help_command": _help_command_for_gate("prepare-broker-dispatch-send"),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker_dispatch)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_checks",
                "component": _component_for_check(name),
                "check": name,
                "actual": check.get("value"),
                "operator": check.get("operator"),
                "expected": check.get("threshold"),
                "action": _action_for_check(name),
                "reason": str(check.get("reason", "")) or name.replace("_", " "),
                "recommendation": _recommendation_for_check(name),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate),
            }
        )
    if not rows:
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_checks",
                "component": "broker_dispatch",
                "check": "provider_broker_dispatch_ready",
                "actual": bool(summary.get("ready", False)),
                "operator": "is",
                "expected": True,
                "action": "repair_provider_imbalance_broker_dispatch",
                "reason": "provider imbalance broker dispatch wrapper is not ready",
                "recommendation": "rerun_provider_imbalance_broker_dispatch",
                "next_gate": "plan-provider-market-data-imbalance-broker-dispatch",
                "next_gate_help_command": _help_command_for_gate(
                    "plan-provider-market-data-imbalance-broker-dispatch"
                ),
            }
        )
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    broker_dispatch: BrokerDispatchReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchConfig,
    broker_dispatch_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_dispatch_inputs": _jsonable(broker_dispatch_inputs),
        "summary": _series_record(summary),
        "provider_route_enable": _first_record(provider_summary),
        "provider_route_enable_config": provider_config,
        "upstream_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "upstream_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_dispatch": {
            "evaluated": broker_dispatch is not None,
            "ready": False if broker_dispatch is None else bool(broker_dispatch.ready),
            "output_dir": "" if broker_dispatch is None else str(broker_dispatch.output_dir or ""),
            "orders": _records(None if broker_dispatch is None else broker_dispatch.dispatch_orders),
            "summary": _first_record(None if broker_dispatch is None else broker_dispatch.summary),
            "checks": _records(None if broker_dispatch is None else broker_dispatch.checks),
            "action_queue": _records(None if broker_dispatch is None else broker_dispatch.action_queue),
            "config": {} if broker_dispatch is None or broker_dispatch.config is None else broker_dispatch.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Broker Dispatch",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Target mode: {summary['target_mode']}",
        f"- Dispatch state: {summary['dispatch_state']}",
        f"- Broker dispatch dir: {summary['broker_dispatch_dir']}",
        f"- Dispatch round-trip ready: {'yes' if bool(summary['dispatch_roundtrip_ready']) else 'no'}",
        f"- Dispatch round-trip dir: {summary['dispatch_roundtrip_dir']}",
        "- Dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Upstream dispatch round-trip ready: {'yes' if bool(summary['upstream_dispatch_roundtrip_ready']) else 'no'}",
        f"- Upstream dispatch round-trip dir: {summary['upstream_dispatch_roundtrip_dir']}",
        "- Upstream dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        "- Upstream broker dispatch round-trip vendor batch ready: "
        f"{'yes' if bool(summary['upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready']) else 'no'}",
        f"- Primary next gate: `{summary['next_gate']}`",
        f"- Primary next gate help: `{summary['next_gate_help_command']}`",
        "",
        "## Checks",
        "",
        _checks_table(checks),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _thresholds(
    config: ProviderMarketDataImbalanceBrokerDispatchConfig,
    provider_summary: pd.DataFrame,
) -> BrokerDispatchThresholds:
    return BrokerDispatchThresholds(
        target_mode=config.target_mode or _first_text(provider_summary, "target_mode") or "live_dryrun",
        require_route_enabled=config.require_route_enabled,
        require_dry_run=config.require_dry_run,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        min_orders=config.min_orders,
        max_orders=config.max_orders,
    )


def _broker_dispatch_failure_reason(broker_dispatch: BrokerDispatchReport | None) -> str:
    if broker_dispatch is None or broker_dispatch.checks.empty:
        return ""
    failed = broker_dispatch.checks.loc[~broker_dispatch.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame, broker_dispatch: BrokerDispatchReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "plan-provider-market-data-imbalance-broker-dispatch"
    return _next_gate_for_check(failed[0], broker_dispatch)


def _next_gate_for_check(check: str, broker_dispatch: BrokerDispatchReport | None) -> str:
    if check.startswith("provider_route_enable"):
        return "review-provider-market-data-imbalance-route-enable"
    if check.startswith("generic_route_enable") or check.startswith("nested_route_enable"):
        return "review-provider-market-data-imbalance-route-enable"
    if check.startswith("upload_pack") or check.startswith("upload_orders"):
        return "pack-broker-upload"
    if check == "broker_dispatch_ready" and broker_dispatch is not None:
        next_gate = _first_action_value(broker_dispatch.action_queue, "next_gate")
        return next_gate or "plan-broker-dispatch"
    if check.startswith("broker_dispatch"):
        return "plan-broker-dispatch"
    if check in {"strategy_identity_imbalance", "market_identity_consistent", "adapter_identity_consistent"}:
        return "review-provider-market-data-imbalance-route-enable"
    return "plan-provider-market-data-imbalance-broker-dispatch"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-route-enable":
        return "python -m hft_cli review-provider-market-data-imbalance-route-enable --help"
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "review-route-enable":
        return "python -m hft_cli review-route-enable --help"
    if next_gate == "pack-broker-upload":
        return "python -m hft_cli pack-broker-upload --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    if next_gate == "review-broker-dispatch-roundtrip":
        return "python -m hft_cli review-broker-dispatch-roundtrip --help"
    if next_gate == "pipeline-vendor-market-data-batch":
        return "python -m hft_cli pipeline-vendor-market-data-batch --help"
    if next_gate == "pipeline-broker-vendor-readiness":
        return "python -m hft_cli pipeline-broker-vendor-readiness --help"
    if next_gate == "review-resume-gate":
        return "python -m hft_cli review-resume-gate --help"
    if next_gate == "plan-broker-dispatch":
        return "python -m hft_cli plan-broker-dispatch --help"
    if next_gate == "prepare-broker-dispatch-send":
        return "python -m hft_cli prepare-broker-dispatch-send --help"
    return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_route_enable"):
        return "provider_route_enable"
    if check.startswith("generic_route_enable") or check.startswith("nested_route_enable"):
        return "route_enable"
    if check.startswith("upload_pack"):
        return "upload_pack"
    if check.startswith("upload_orders"):
        return "upload_orders"
    if check.startswith("broker_dispatch"):
        return "broker_dispatch"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_dispatch"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_route_enable"):
        return "repair_provider_imbalance_route_enable"
    if check.startswith("generic_route_enable") or check.startswith("nested_route_enable"):
        return "repair_provider_imbalance_route_enable_inputs"
    if check.startswith("upload_pack") or check.startswith("upload_orders"):
        return "repair_broker_upload_pack"
    if check.startswith("broker_dispatch"):
        return "repair_broker_dispatch_plan"
    return "repair_provider_imbalance_broker_dispatch"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_route_enable"):
        return "rerun_provider_route_enable_before_broker_dispatch"
    if check.startswith("generic_route_enable") or check.startswith("nested_route_enable"):
        return "rerun_provider_route_enable_to_refresh_nested_route_artifacts"
    if check.startswith("upload_pack") or check.startswith("upload_orders"):
        return "rerun_broker_upload_pack_before_broker_dispatch"
    if check.startswith("broker_dispatch"):
        return "rerun_generic_broker_dispatch_with_required_artifacts"
    return "repair_provider_broker_dispatch_inputs"


def _inferred_route_enable_dir(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> Path | None:
    route_enable_config = provider_config.get("route_enable", {}) or {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "route_enable_dir")),
        _path_from_text(route_enable_config.get("output_dir")),
    )


def _inferred_upload_pack_dir(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> Path | None:
    route_enable_inputs = provider_config.get("route_enable_inputs", {}) or {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upload_pack_dir")),
        _path_from_text(route_enable_inputs.get("upload_pack_dir")),
    )


def _inferred_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    route_enable_inputs = provider_config.get("route_enable_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_dispatch_roundtrip_dir")),
        _path_from_text(route_enable_inputs.get("provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "dispatch_roundtrip_dir")),
        _path_from_text(route_enable_inputs.get("dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    route_enable_inputs = provider_config.get("route_enable_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_provider_dispatch_roundtrip_dir")),
        _path_from_text(route_enable_inputs.get("upstream_provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_dispatch_roundtrip_dir")),
        _path_from_text(route_enable_inputs.get("upstream_dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchConfig,
) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not config.use_provider_route_enable_inputs:
        return None
    return inferred


def _summary_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    for folder in fallback_dirs:
        nested = candidate / folder / filename
        if nested.exists():
            return nested
    return direct


def _first_action_value(action_queue: pd.DataFrame | None, column: str) -> str:
    if action_queue is None or action_queue.empty or column not in action_queue.columns:
        return ""
    for value in action_queue[column].tolist():
        text = _clean(value)
        if text:
            return text
    return ""


def _checks_table(checks: pd.DataFrame) -> str:
    if checks.empty:
        return "_None_"
    rows = [
        [
            str(row.get("check", "")),
            "pass" if _truthy(row.get("passed")) else "fail",
            str(row.get("value", "")),
            str(row.get("threshold", "")),
            str(row.get("reason", "")),
        ]
        for row in checks.to_dict(orient="records")
    ]
    return _markdown_table(["Check", "Status", "Value", "Threshold", "Reason"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(row.get("priority", "")),
            str(row.get("queue_status", "")),
            str(row.get("action", "")),
            str(row.get("next_gate", "")),
            str(row.get("reason", "")),
        ]
        for row in action_queue.to_dict(orient="records")
    ]
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _action_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: object) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    return Path(text)


def _path_or_empty(path: str | Path | None) -> Path:
    if path is None:
        return Path()
    return Path(path)


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _clean(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str, fallback: float = 0.0) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return float(fallback)
    value = pd.to_numeric(frame.iloc[0][column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _identity_key(value: object) -> str:
    return _clean(value).lower().replace("-", "_").replace(" ", "_")


def _truthy(value: object) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "ready", "pass", "passed", "continue", "enabled"}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_jsonable(row) for row in frame.to_dict(orient="records")]


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    records = _records(frame)
    return records[0] if records else {}


def _series_record(series: pd.Series) -> dict[str, Any]:
    return _jsonable(series.to_dict())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _records(value)
    if isinstance(value, pd.Series):
        return _series_record(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return str(value)
    return value
