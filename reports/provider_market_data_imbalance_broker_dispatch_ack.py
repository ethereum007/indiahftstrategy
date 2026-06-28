from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.broker_dispatch_ack import (
    BrokerDispatchAckReport,
    BrokerDispatchAckThresholds,
    write_broker_dispatch_acknowledgements,
)
from reports.manifest import write_experiment_manifest


PROFILE = "imbalance"
RUN_TYPE = "provider_market_data_imbalance_broker_dispatch_ack"

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
class ProviderMarketDataImbalanceBrokerDispatchAckConfig:
    require_provider_broker_dispatch_send_ready: bool = True
    require_broker_dispatch_ack_passed: bool = True
    use_provider_broker_dispatch_send_inputs: bool = True
    require_dispatch_ready: bool = True
    require_all_acked: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0


@dataclass(frozen=True)
class ProviderMarketDataImbalanceBrokerDispatchAckReport:
    broker_dispatch_ack: BrokerDispatchAckReport | None
    checks: pd.DataFrame
    summary: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def write_provider_market_data_imbalance_broker_dispatch_ack(
    provider_broker_dispatch_send_dir: str | Path,
    acks_path: str | Path,
    output_dir: str | Path,
    *,
    broker_dispatch_dir: str | Path | None = None,
    config: ProviderMarketDataImbalanceBrokerDispatchAckConfig | None = None,
) -> ProviderMarketDataImbalanceBrokerDispatchAckReport:
    config = config or ProviderMarketDataImbalanceBrokerDispatchAckConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    provider_root = Path(provider_broker_dispatch_send_dir)
    acks = Path(acks_path)
    provider_summary, provider_summary_error = _read_csv(
        provider_root / "provider_market_data_imbalance_broker_dispatch_send_summary.csv"
    )
    provider_config, provider_config_error = _read_json(
        provider_root / "provider_market_data_imbalance_broker_dispatch_send_config.json"
    )
    resolved_broker_dispatch_dir = _explicit_or_inferred(
        broker_dispatch_dir,
        _inferred_broker_dispatch_dir(provider_summary, provider_config),
        config,
    )
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
        resolved_broker_dispatch_dir,
        acks,
        config,
    )

    broker_dispatch_ack: BrokerDispatchAckReport | None = None
    broker_dispatch_ack_error = ""
    broker_dispatch_ack_dir = out / "broker_dispatch_ack"
    if bool(prechecks["passed"].all()):
        try:
            broker_dispatch_ack = write_broker_dispatch_acknowledgements(
                dispatch_dir=_path_or_empty(resolved_broker_dispatch_dir),
                acks_path=acks,
                output_dir=broker_dispatch_ack_dir,
                thresholds=_thresholds(config),
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError, json.JSONDecodeError) as exc:
            broker_dispatch_ack_error = str(exc)
    else:
        broker_dispatch_ack_error = "provider imbalance broker-dispatch-ack prerequisites are not ready"

    checks = _checks(prechecks, broker_dispatch_ack, broker_dispatch_ack_error, provider_summary, config)
    summary = _summary(
        provider_root,
        resolved_broker_dispatch_dir,
        acks,
        inferred_provider_dispatch_roundtrip_dir,
        inferred_dispatch_roundtrip_dir,
        inferred_upstream_provider_dispatch_roundtrip_dir,
        inferred_upstream_dispatch_roundtrip_dir,
        broker_dispatch_ack,
        checks,
        out,
        broker_dispatch_ack_dir,
        provider_summary,
    )
    action_queue = _action_queue(summary.iloc[0], checks, broker_dispatch_ack)
    summary = _summary_with_actions(summary, action_queue)
    payload = _config(
        summary.iloc[0],
        provider_summary,
        provider_config,
        broker_dispatch_ack,
        checks,
        action_queue,
        config,
        {
            "provider_broker_dispatch_send_dir": provider_root,
            "broker_dispatch_dir": resolved_broker_dispatch_dir,
            "acks_path": acks,
            "provider_dispatch_roundtrip_dir": inferred_provider_dispatch_roundtrip_dir,
            "dispatch_roundtrip_dir": inferred_dispatch_roundtrip_dir,
            "upstream_provider_dispatch_roundtrip_dir": inferred_upstream_provider_dispatch_roundtrip_dir,
            "upstream_dispatch_roundtrip_dir": inferred_upstream_dispatch_roundtrip_dir,
        },
    )

    checks.to_csv(out / "provider_market_data_imbalance_broker_dispatch_ack_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_broker_dispatch_ack_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_broker_dispatch_ack_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_broker_dispatch_ack_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_broker_dispatch_ack_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {
        "provider_broker_dispatch_send_dir": provider_root,
        "broker_acks": acks,
    }
    if resolved_broker_dispatch_dir is not None:
        inputs["broker_dispatch"] = Path(resolved_broker_dispatch_dir)
    if inferred_provider_dispatch_roundtrip_dir is not None:
        inputs["provider_dispatch_roundtrip"] = Path(inferred_provider_dispatch_roundtrip_dir)
    if inferred_dispatch_roundtrip_dir is not None:
        inputs["dispatch_roundtrip"] = Path(inferred_dispatch_roundtrip_dir)
    if inferred_upstream_provider_dispatch_roundtrip_dir is not None:
        inputs["upstream_provider_dispatch_roundtrip"] = Path(inferred_upstream_provider_dispatch_roundtrip_dir)
    if inferred_upstream_dispatch_roundtrip_dir is not None:
        inputs["upstream_dispatch_roundtrip"] = Path(inferred_upstream_dispatch_roundtrip_dir)
    if broker_dispatch_ack is not None and broker_dispatch_ack.output_dir is not None:
        inputs["broker_dispatch_ack"] = broker_dispatch_ack.output_dir
    summary_row = summary.iloc[0]
    for name, value in {
        "capture_bundle": _path_from_text(summary_row["capture_bundle_path"]),
        "capture_env_template": _path_from_text(summary_row["capture_env_template_path"]),
        "adapter_handoff": _path_from_text(summary_row["adapter_handoff_path"]),
        "dispatch_roundtrip_capture_bundle": _path_from_text(
            summary_row["dispatch_roundtrip_capture_bundle_path"]
        ),
        "dispatch_roundtrip_capture_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_capture_env_template_path"]
        ),
        "dispatch_roundtrip_adapter_handoff": _path_from_text(
            summary_row["dispatch_roundtrip_adapter_handoff_path"]
        ),
        "dispatch_roundtrip_source_credential_env_template": _path_from_text(
            summary_row["dispatch_roundtrip_source_credential_env_template_path"]
        ),
        "source_credential_env_template": _path_from_text(summary_row["source_credential_env_template_path"]),
    }.items():
        if value is not None:
            inputs[name] = value

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={
            "config": asdict(config),
            "broker_dispatch_ack_inputs": _jsonable(payload["broker_dispatch_ack_inputs"]),
        },
        inputs=inputs,
        extra={
            "passed": bool(summary_row["passed"]),
            "broker_dispatch_ack_passed": bool(summary_row["broker_dispatch_ack_passed"]),
            "profile": PROFILE,
            "strategy": str(summary_row["strategy"]),
            "market": str(summary_row["market"]),
            "exchange": str(summary_row["exchange"]),
            "source_session": _source_session_contract_from_summary(summary_row),
            "market_session": _market_session_contract_from_summary(summary_row),
            "capture_bundle_provided": bool(summary_row["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary_row["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary_row["capture_bundle_ready"]),
            "capture_env_template_exists": bool(summary_row["capture_env_template_exists"]),
            "adapter_handoff_provided": bool(summary_row["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary_row["adapter_handoff_exists"]),
            "capture_bundle_metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_bundle": {
                "exchange": str(summary_row["capture_bundle_exchange"]),
                "source_session": _capture_bundle_source_session_contract_from_summary(summary_row),
                "market_session": _capture_bundle_market_session_contract_from_summary(summary_row),
                "metadata_matches_session": bool(summary_row["capture_bundle_metadata_matches_session"]),
                "live_fetch_contract_metadata_matches_session": bool(
                    summary_row["capture_bundle_live_fetch_contract_metadata_matches_session"]
                ),
            },
            "source_credential_env_template": {
                "path": str(summary_row["source_credential_env_template_path"]),
                "exists": bool(summary_row["source_credential_env_template_exists"]),
                "sha256": str(summary_row["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": {
                "available": bool(summary_row["source_live_fetch_contract_available"]),
                "next_gate": str(summary_row["source_live_fetch_contract_next_gate"]),
                "command_template": str(summary_row["source_live_fetch_contract_command_template"]),
                "exchange": str(summary_row["source_live_fetch_contract_exchange"]),
                "market": str(summary_row["source_live_fetch_contract_market"]),
                "session": _source_live_fetch_contract_session_from_summary(summary_row),
            },
            "dispatch_roundtrip_capture_provenance_consistent": bool(
                summary_row["dispatch_roundtrip_capture_provenance_consistent"]
            ),
            "dispatch_roundtrip_capture_bundle_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_bundle_matches_session"]
            ),
            "dispatch_roundtrip_capture_env_template_matches_session": bool(
                summary_row["dispatch_roundtrip_capture_env_template_matches_session"]
            ),
            "dispatch_roundtrip_adapter_handoff_matches_session": bool(
                summary_row["dispatch_roundtrip_adapter_handoff_matches_session"]
            ),
            "dispatch_roundtrip_source_provenance_consistent": bool(
                summary_row["dispatch_roundtrip_source_provenance_consistent"]
            ),
            "dispatch_roundtrip_source_credential_env_template_matches_session": bool(
                summary_row["dispatch_roundtrip_source_credential_env_template_matches_session"]
            ),
            "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": bool(
                summary_row["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"]
            ),
            "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": bool(
                summary_row["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"]
            ),
            "dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready": bool(
                summary_row["upstream_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
            ),
        },
    )
    return ProviderMarketDataImbalanceBrokerDispatchAckReport(
        broker_dispatch_ack,
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
    broker_dispatch_dir: Path | None,
    acks_path: Path,
    config: ProviderMarketDataImbalanceBrokerDispatchAckConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_broker_dispatch_send_dir_exists",
                str(provider_root),
                "exists",
                True,
                provider_root.exists(),
                "provider imbalance broker-dispatch-send directory is required",
            ),
            _check(
                "provider_broker_dispatch_send_summary_readable",
                provider_summary_error or "ok",
                "is",
                "ok",
                not provider_summary_error,
                provider_summary_error or "provider broker-dispatch-send summary could not be read",
            ),
            _check(
                "provider_broker_dispatch_send_config_readable",
                provider_config_error or "ok",
                "is",
                "ok",
                not provider_config_error,
                provider_config_error or "provider broker-dispatch-send config could not be read",
            ),
            _check(
                "provider_broker_dispatch_send_ready",
                _first_bool(provider_summary, "ready"),
                "is",
                True,
                _first_bool(provider_summary, "ready") or not config.require_provider_broker_dispatch_send_ready,
                "provider broker-dispatch-send wrapper is not ready",
            ),
            _check(
                "provider_nested_broker_dispatch_send_ready",
                _first_bool(provider_summary, "broker_dispatch_send_ready"),
                "is",
                True,
                _first_bool(provider_summary, "broker_dispatch_send_ready")
                or not config.require_provider_broker_dispatch_send_ready,
                "nested broker dispatch send packet is not ready",
            ),
            _check(
                "generic_broker_dispatch_input_resolved",
                _path_text(broker_dispatch_dir),
                "present",
                True,
                bool(broker_dispatch_dir),
                "nested generic broker dispatch input is required for ack reconciliation",
            ),
            _check(
                "nested_broker_dispatch_config_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_config.json").exists()),
                "nested broker_dispatch_config.json is required for ack reconciliation",
            ),
            _check(
                "nested_broker_dispatch_summary_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_summary.csv").exists()),
                "nested broker_dispatch_summary.csv is required for ack reconciliation",
            ),
            _check(
                "nested_broker_dispatch_orders_exists",
                _path_text(broker_dispatch_dir),
                "exists",
                True,
                bool(broker_dispatch_dir and (broker_dispatch_dir / "broker_dispatch_orders.csv").exists()),
                "nested broker_dispatch_orders.csv is required for ack reconciliation",
            ),
            _check(
                "broker_acks_path_exists",
                str(acks_path),
                "exists",
                True,
                acks_path.exists(),
                "broker acknowledgement CSV is required for provider ack reconciliation",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    broker_dispatch_ack: BrokerDispatchAckReport | None,
    broker_dispatch_ack_error: str,
    provider_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchAckConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    ack_summary = broker_dispatch_ack.summary if broker_dispatch_ack is not None else pd.DataFrame()
    rows.append(
        _check(
            "broker_dispatch_ack_runnable",
            broker_dispatch_ack_error or ("ran" if broker_dispatch_ack is not None else "not_run"),
            "is",
            "ran",
            broker_dispatch_ack is not None and not broker_dispatch_ack_error,
            broker_dispatch_ack_error or "generic broker dispatch ack reconciliation was not run",
        )
    )
    rows.append(
        _check(
            "broker_dispatch_ack_passed",
            bool(broker_dispatch_ack is not None and broker_dispatch_ack.passed),
            "is",
            True,
            bool(
                broker_dispatch_ack is not None
                and (broker_dispatch_ack.passed or not config.require_broker_dispatch_ack_passed)
            ),
            _broker_dispatch_ack_failure_reason(broker_dispatch_ack) or "broker dispatch ack reconciliation did not pass",
        )
    )
    strategy = _first_text(ack_summary, "strategy") or _first_text(provider_summary, "strategy")
    rows.append(
        _check(
            "strategy_identity_imbalance",
            strategy,
            "is",
            PROFILE,
            bool(broker_dispatch_ack is not None) and _identity_key(strategy) == PROFILE,
            "broker dispatch ack reconciliation did not resolve to imbalance strategy",
        )
    )
    expected_market = _first_text(provider_summary, "market")
    ack_market = _first_text(ack_summary, "market")
    rows.append(
        _check(
            "market_identity_consistent",
            ack_market or expected_market,
            "is",
            expected_market or "present",
            bool(broker_dispatch_ack is not None)
            and (not expected_market or _identity_key(ack_market) == _identity_key(expected_market)),
            "broker dispatch ack market identity does not match provider send",
        )
    )
    expected_adapter = _first_text(provider_summary, "adapter")
    ack_adapter = _first_text(ack_summary, "adapter")
    rows.append(
        _check(
            "adapter_identity_consistent",
            ack_adapter or expected_adapter,
            "is",
            expected_adapter or "present",
            bool(broker_dispatch_ack is not None)
            and (not expected_adapter or _identity_key(ack_adapter) == _identity_key(expected_adapter)),
            "broker dispatch ack adapter identity does not match provider send",
        )
    )
    return pd.DataFrame(rows)


def _summary(
    provider_root: Path,
    broker_dispatch_dir: Path | None,
    acks_path: Path,
    provider_dispatch_roundtrip_dir: Path | None,
    dispatch_roundtrip_dir: Path | None,
    upstream_provider_dispatch_roundtrip_dir: Path | None,
    upstream_dispatch_roundtrip_dir: Path | None,
    broker_dispatch_ack: BrokerDispatchAckReport | None,
    checks: pd.DataFrame,
    output_dir: Path,
    broker_dispatch_ack_dir: Path,
    provider_summary: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    passed = failed == 0
    ack_summary = broker_dispatch_ack.summary if broker_dispatch_ack is not None else pd.DataFrame()
    ack_dir = (
        broker_dispatch_ack_dir
        if broker_dispatch_ack is None
        else Path(broker_dispatch_ack.output_dir or broker_dispatch_ack_dir)
    )
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "ready": passed,
                "provider_broker_dispatch_send_ready": _first_bool(provider_summary, "ready"),
                "broker_dispatch_ack_passed": bool(broker_dispatch_ack is not None and broker_dispatch_ack.passed),
                "provider_broker_dispatch_send_dir": str(provider_root),
                "broker_dispatch_dir": _path_text(broker_dispatch_dir),
                "acks_path": str(acks_path),
                "exchange": _first_text(provider_summary, "exchange"),
                "source_session_timezone": _first_text(provider_summary, "source_session_timezone"),
                "source_session_open_local": _first_text(provider_summary, "source_session_open_local"),
                "source_session_close_local": _first_text(provider_summary, "source_session_close_local"),
                "market_session_timezone": _first_text(provider_summary, "market_session_timezone"),
                "market_session_open_local": _first_text(provider_summary, "market_session_open_local"),
                "market_session_close_local": _first_text(provider_summary, "market_session_close_local"),
                "capture_bundle_path": _first_text(provider_summary, "capture_bundle_path"),
                "capture_bundle_provided": _first_bool(provider_summary, "capture_bundle_provided"),
                "capture_bundle_exists": _first_bool(provider_summary, "capture_bundle_exists"),
                "capture_bundle_ready": _first_bool(provider_summary, "capture_bundle_ready"),
                "capture_bundle_exchange": _first_text(provider_summary, "capture_bundle_exchange"),
                "capture_bundle_source_session_timezone": _first_text(
                    provider_summary, "capture_bundle_source_session_timezone"
                ),
                "capture_bundle_source_session_open_local": _first_text(
                    provider_summary, "capture_bundle_source_session_open_local"
                ),
                "capture_bundle_source_session_close_local": _first_text(
                    provider_summary, "capture_bundle_source_session_close_local"
                ),
                "capture_bundle_market_session_timezone": _first_text(
                    provider_summary, "capture_bundle_market_session_timezone"
                ),
                "capture_bundle_market_session_open_local": _first_text(
                    provider_summary, "capture_bundle_market_session_open_local"
                ),
                "capture_bundle_market_session_close_local": _first_text(
                    provider_summary, "capture_bundle_market_session_close_local"
                ),
                "capture_bundle_metadata_matches_session": _first_bool(
                    provider_summary, "capture_bundle_metadata_matches_session"
                ),
                "capture_bundle_live_fetch_contract_metadata_matches_session": _first_bool(
                    provider_summary,
                    "capture_bundle_live_fetch_contract_metadata_matches_session",
                ),
                "capture_env_template_path": _first_text(provider_summary, "capture_env_template_path"),
                "capture_env_template_provided": _first_bool(provider_summary, "capture_env_template_provided"),
                "capture_env_template_exists": _first_bool(provider_summary, "capture_env_template_exists"),
                "adapter_handoff_path": _first_text(provider_summary, "adapter_handoff_path"),
                "adapter_handoff_provided": _first_bool(provider_summary, "adapter_handoff_provided"),
                "adapter_handoff_exists": _first_bool(provider_summary, "adapter_handoff_exists"),
                "source_credential_env_template_path": _first_text(
                    provider_summary,
                    "source_credential_env_template_path",
                ),
                "source_credential_env_template_exists": _first_bool(
                    provider_summary,
                    "source_credential_env_template_exists",
                ),
                "source_credential_env_template_sha256": _first_text(
                    provider_summary,
                    "source_credential_env_template_sha256",
                ),
                "source_live_fetch_contract_available": _first_bool(
                    provider_summary,
                    "source_live_fetch_contract_available",
                ),
                "source_live_fetch_contract_next_gate": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_next_gate",
                ),
                "source_live_fetch_contract_command_template": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_command_template",
                ),
                "source_live_fetch_contract_exchange": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_exchange",
                ),
                "source_live_fetch_contract_market": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_market",
                ),
                "source_live_fetch_contract_session_timezone": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_timezone",
                ),
                "source_live_fetch_contract_session_open_local": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_open_local",
                ),
                "source_live_fetch_contract_session_close_local": _first_text(
                    provider_summary,
                    "source_live_fetch_contract_session_close_local",
                ),
                "dispatch_roundtrip_source_credential_env_template_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_path",
                ),
                "dispatch_roundtrip_source_credential_env_template_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_exists",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_sha256",
                ),
                "dispatch_roundtrip_source_credential_env_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_matches_session",
                ),
                "dispatch_roundtrip_source_credential_env_template_sha256_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_credential_env_template_sha256_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_available": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_available",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session",
                ),
                "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session",
                ),
                "dispatch_roundtrip_source_provenance_consistent": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_source_provenance_consistent",
                ),
                "dispatch_roundtrip_capture_bundle_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_path",
                ),
                "dispatch_roundtrip_capture_bundle_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_provided",
                ),
                "dispatch_roundtrip_capture_bundle_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_exists",
                ),
                "dispatch_roundtrip_capture_bundle_ready": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_ready",
                ),
                "dispatch_roundtrip_capture_bundle_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_bundle_matches_session",
                ),
                "dispatch_roundtrip_capture_env_template_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_path",
                ),
                "dispatch_roundtrip_capture_env_template_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_provided",
                ),
                "dispatch_roundtrip_capture_env_template_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_exists",
                ),
                "dispatch_roundtrip_capture_env_template_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_env_template_matches_session",
                ),
                "dispatch_roundtrip_adapter_handoff_path": _first_text(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_path",
                ),
                "dispatch_roundtrip_adapter_handoff_provided": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_provided",
                ),
                "dispatch_roundtrip_adapter_handoff_exists": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_exists",
                ),
                "dispatch_roundtrip_adapter_handoff_matches_session": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_adapter_handoff_matches_session",
                ),
                "dispatch_roundtrip_capture_provenance_consistent": _first_bool(
                    provider_summary,
                    "dispatch_roundtrip_capture_provenance_consistent",
                ),
                "provider_dispatch_roundtrip_dir": _path_text(provider_dispatch_roundtrip_dir),
                "dispatch_roundtrip_dir": _path_text(dispatch_roundtrip_dir),
                "dispatch_roundtrip_provided": _first_bool(provider_summary, "dispatch_roundtrip_provided"),
                "dispatch_roundtrip_ready": _first_bool(provider_summary, "dispatch_roundtrip_ready"),
                "dispatch_roundtrip_failed_checks": int(
                    _first_number(provider_summary, "dispatch_roundtrip_failed_checks")
                ),
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
                **_vendor_market_data_batch_summary_fields(provider_summary),
                "broker_dispatch_ack_dir": str(ack_dir),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(provider_summary, "provider"),
                "transport": _first_text(provider_summary, "transport"),
                "market": _first_text(ack_summary, "market") or _first_text(provider_summary, "market"),
                "strategy": _first_text(ack_summary, "strategy")
                or _first_text(provider_summary, "strategy")
                or PROFILE,
                "target_mode": _first_text(ack_summary, "target_mode")
                or _first_text(provider_summary, "target_mode"),
                "adapter": _first_text(ack_summary, "adapter") or _first_text(provider_summary, "adapter"),
                "scenario_key": _first_text(ack_summary, "scenario_key")
                or _first_text(provider_summary, "scenario_key"),
                "dispatch_orders": int(
                    _first_number(ack_summary, "dispatch_orders")
                    or _first_number(provider_summary, "dispatch_orders")
                ),
                "acked_orders": int(_first_number(ack_summary, "acked_orders")),
                "missing_acks": int(_first_number(ack_summary, "missing_acks")),
                "rejected_orders": int(_first_number(ack_summary, "rejected_orders")),
                "duplicate_ack_orders": int(_first_number(ack_summary, "duplicate_ack_orders")),
                "unmatched_acks": int(_first_number(ack_summary, "unmatched_acks")),
                "ack_rate": float(_first_number(ack_summary, "ack_rate")),
                "dispatch_total_notional": float(
                    _first_number(ack_summary, "dispatch_total_notional")
                    or _first_number(provider_summary, "dispatch_total_notional")
                ),
                "route_readiness_required": _first_bool(ack_summary, "route_readiness_required")
                or _first_bool(provider_summary, "route_readiness_required"),
                "route_readiness_ready": _first_bool(ack_summary, "route_readiness_ready")
                or _first_bool(provider_summary, "route_readiness_ready"),
                "route_readiness_gap_pairs": int(
                    _first_number(ack_summary, "route_readiness_gap_pairs")
                    or _first_number(provider_summary, "route_readiness_gap_pairs")
                ),
                "provider_broker_dispatch_send_recommendation": _first_text(
                    provider_summary, "broker_dispatch_send_recommendation"
                )
                or _first_text(provider_summary, "recommendation"),
                "broker_dispatch_ack_recommendation": _first_text(ack_summary, "recommendation"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "review_provider_imbalance_broker_dispatch_roundtrip"
                if passed
                else "repair_provider_imbalance_broker_dispatch_ack",
                "next_gate": "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
                if passed
                else _blocked_next_gate(checks, broker_dispatch_ack),
                "next_gate_help_command": _help_command_for_gate(
                    "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
                    if passed
                    else _blocked_next_gate(checks, broker_dispatch_ack)
                ),
                "primary_action_status": "ready" if passed else "blocked",
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
    broker_dispatch_ack: BrokerDispatchAckReport | None,
) -> pd.DataFrame:
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    if failed.empty:
        return _action_frame(
            [
                {
                    "queue_status": "ready",
                    "source": "provider_market_data_imbalance_broker_dispatch_ack_summary",
                    "component": "broker_dispatch_ack",
                    "check": "broker_dispatch_ack_passed",
                    "actual": True,
                    "operator": "is",
                    "expected": True,
                    "action": "review_provider_imbalance_broker_dispatch_roundtrip",
                    "reason": "provider imbalance broker dispatch acknowledgements passed reconciliation",
                    "recommendation": "review_dispatch_send_ack_roundtrip_before_broker_promotion",
                    "next_gate": "review-provider-market-data-imbalance-broker-dispatch-roundtrip",
                    "next_gate_help_command": _help_command_for_gate(
                        "review-provider-market-data-imbalance-broker-dispatch-roundtrip"
                    ),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, check in failed.iterrows():
        name = str(check.get("check", ""))
        next_gate = _next_gate_for_check(name, broker_dispatch_ack)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "provider_market_data_imbalance_broker_dispatch_ack_checks",
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
    return _action_frame(rows)


def _config(
    summary: pd.Series,
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
    broker_dispatch_ack: BrokerDispatchAckReport | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceBrokerDispatchAckConfig,
    broker_dispatch_ack_inputs: dict[str, Any],
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "passed": bool(summary["passed"]),
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "broker_dispatch_ack_inputs": _jsonable(broker_dispatch_ack_inputs),
        "summary": _series_record(summary),
        "exchange": str(summary["exchange"]),
        "source_session": _source_session_contract_from_summary(summary),
        "market_session": _market_session_contract_from_summary(summary),
        "capture_bundle": {
            "capture_bundle_path": str(summary["capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["capture_bundle_ready"]),
            "exchange": str(summary["capture_bundle_exchange"]),
            "source_session": _capture_bundle_source_session_contract_from_summary(summary),
            "market_session": _capture_bundle_market_session_contract_from_summary(summary),
            "capture_bundle_metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "capture_bundle_live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "metadata_matches_session": bool(summary["capture_bundle_metadata_matches_session"]),
            "live_fetch_contract_metadata_matches_session": bool(
                summary["capture_bundle_live_fetch_contract_metadata_matches_session"]
            ),
            "capture_env_template_path": str(summary["capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["capture_env_template_exists"]),
            "adapter_handoff_path": str(summary["adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
            "source_credential_env_template_path": str(summary["source_credential_env_template_path"]),
            "source_credential_env_template_exists": bool(summary["source_credential_env_template_exists"]),
            "source_credential_env_template_sha256": str(summary["source_credential_env_template_sha256"]),
            "source_live_fetch_contract_available": bool(summary["source_live_fetch_contract_available"]),
            "source_live_fetch_contract_next_gate": str(summary["source_live_fetch_contract_next_gate"]),
            "source_live_fetch_contract_command_template": str(
                summary["source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_exchange": str(summary["source_live_fetch_contract_exchange"]),
            "source_live_fetch_contract_market": str(summary["source_live_fetch_contract_market"]),
            "source_live_fetch_contract_session_timezone": str(
                summary["source_live_fetch_contract_session_timezone"]
            ),
            "source_live_fetch_contract_session_open_local": str(
                summary["source_live_fetch_contract_session_open_local"]
            ),
            "source_live_fetch_contract_session_close_local": str(
                summary["source_live_fetch_contract_session_close_local"]
            ),
        },
        "dispatch_roundtrip_provenance": {
            "capture_bundle_path": str(summary["dispatch_roundtrip_capture_bundle_path"]),
            "capture_bundle_provided": bool(summary["dispatch_roundtrip_capture_bundle_provided"]),
            "capture_bundle_exists": bool(summary["dispatch_roundtrip_capture_bundle_exists"]),
            "capture_bundle_ready": bool(summary["dispatch_roundtrip_capture_bundle_ready"]),
            "capture_bundle_matches_session": bool(summary["dispatch_roundtrip_capture_bundle_matches_session"]),
            "capture_env_template_path": str(summary["dispatch_roundtrip_capture_env_template_path"]),
            "capture_env_template_provided": bool(summary["dispatch_roundtrip_capture_env_template_provided"]),
            "capture_env_template_exists": bool(summary["dispatch_roundtrip_capture_env_template_exists"]),
            "capture_env_template_matches_session": bool(
                summary["dispatch_roundtrip_capture_env_template_matches_session"]
            ),
            "adapter_handoff_path": str(summary["dispatch_roundtrip_adapter_handoff_path"]),
            "adapter_handoff_provided": bool(summary["dispatch_roundtrip_adapter_handoff_provided"]),
            "adapter_handoff_exists": bool(summary["dispatch_roundtrip_adapter_handoff_exists"]),
            "adapter_handoff_matches_session": bool(summary["dispatch_roundtrip_adapter_handoff_matches_session"]),
            "consistent_with_runtime_session": bool(summary["dispatch_roundtrip_capture_provenance_consistent"]),
            "source_credential_env_template_path": str(
                summary["dispatch_roundtrip_source_credential_env_template_path"]
            ),
            "source_credential_env_template_exists": bool(
                summary["dispatch_roundtrip_source_credential_env_template_exists"]
            ),
            "source_credential_env_template_sha256": str(
                summary["dispatch_roundtrip_source_credential_env_template_sha256"]
            ),
            "source_credential_env_template_matches_session": bool(
                summary["dispatch_roundtrip_source_credential_env_template_matches_session"]
            ),
            "source_credential_env_template_sha256_matches_session": bool(
                summary["dispatch_roundtrip_source_credential_env_template_sha256_matches_session"]
            ),
            "source_live_fetch_contract_available": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_available"]
            ),
            "source_live_fetch_contract_next_gate": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_next_gate"]
            ),
            "source_live_fetch_contract_command_template": str(
                summary["dispatch_roundtrip_source_live_fetch_contract_command_template"]
            ),
            "source_live_fetch_contract_next_gate_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_next_gate_matches_session"]
            ),
            "source_live_fetch_contract_command_template_matches_session": bool(
                summary["dispatch_roundtrip_source_live_fetch_contract_command_template_matches_session"]
            ),
            "source_provenance_consistent_with_runtime_session": bool(
                summary["dispatch_roundtrip_source_provenance_consistent"]
            ),
        },
        "provider_broker_dispatch_send": _first_record(provider_summary),
        "provider_broker_dispatch_send_config": provider_config,
        "dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "upstream_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "upstream_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "upstream_broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            provider_config,
            "upstream_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "broker_dispatch_ack": {
            "evaluated": broker_dispatch_ack is not None,
            "passed": False if broker_dispatch_ack is None else bool(broker_dispatch_ack.passed),
            "output_dir": "" if broker_dispatch_ack is None else str(broker_dispatch_ack.output_dir or ""),
            "acknowledgements": _records(None if broker_dispatch_ack is None else broker_dispatch_ack.acknowledgements),
            "unmatched_acks": _records(None if broker_dispatch_ack is None else broker_dispatch_ack.unmatched_acks),
            "summary": _first_record(None if broker_dispatch_ack is None else broker_dispatch_ack.summary),
            "checks": _records(None if broker_dispatch_ack is None else broker_dispatch_ack.checks),
            "action_queue": _records(None if broker_dispatch_ack is None else broker_dispatch_ack.action_queue),
            "config": {}
            if broker_dispatch_ack is None or broker_dispatch_ack.config is None
            else broker_dispatch_ack.config,
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
        "# Provider Market Data Imbalance Broker Dispatch Acknowledgements",
        "",
        f"- Passed: {'yes' if bool(summary['passed']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Exchange: {summary['exchange'] or 'unspecified'}",
        f"- Source session: {summary['source_session_open_local'] or '?'} - {summary['source_session_close_local'] or '?'} {summary['source_session_timezone'] or ''}",
        f"- Target mode: {summary['target_mode']}",
        f"- Ack rate: {summary['ack_rate']}",
        f"- Missing acks: {summary['missing_acks']}",
        f"- Rejected orders: {summary['rejected_orders']}",
        f"- Broker dispatch ack dir: {summary['broker_dispatch_ack_dir']}",
        f"- Capture bundle: {summary['capture_bundle_path'] or 'not provided'}",
        f"- Capture env template: {summary['capture_env_template_path'] or 'not provided'}",
        f"- Adapter handoff: {summary['adapter_handoff_path'] or 'not provided'}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'not provided'}",
        "- Live fetch contract: "
        f"{'available' if bool(summary['source_live_fetch_contract_available']) else 'missing'}",
        f"- Dispatch round-trip capture bundle: {summary['dispatch_roundtrip_capture_bundle_path'] or 'not provided'}",
        "- Dispatch round-trip capture env template: "
        f"{summary['dispatch_roundtrip_capture_env_template_path'] or 'not provided'}",
        f"- Dispatch round-trip adapter handoff: {summary['dispatch_roundtrip_adapter_handoff_path'] or 'not provided'}",
        "- Dispatch round-trip provenance consistent: "
        f"{'yes' if bool(summary['dispatch_roundtrip_capture_provenance_consistent']) else 'no'}",
        "- Dispatch round-trip source credential env template: "
        f"{summary['dispatch_roundtrip_source_credential_env_template_path'] or 'not provided'}",
        "- Dispatch round-trip source provenance consistent: "
        f"{'yes' if bool(summary['dispatch_roundtrip_source_provenance_consistent']) else 'no'}",
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


def _thresholds(config: ProviderMarketDataImbalanceBrokerDispatchAckConfig) -> BrokerDispatchAckThresholds:
    return BrokerDispatchAckThresholds(
        require_dispatch_ready=config.require_dispatch_ready,
        require_all_acked=config.require_all_acked,
        require_route_readiness=config.require_route_readiness,
        require_dispatch_roundtrip=config.require_dispatch_roundtrip,
        allow_rejections=config.allow_rejections,
        max_duplicate_ack_orders=config.max_duplicate_ack_orders,
        max_unmatched_acks=config.max_unmatched_acks,
    )


def _broker_dispatch_ack_failure_reason(broker_dispatch_ack: BrokerDispatchAckReport | None) -> str:
    if broker_dispatch_ack is None or broker_dispatch_ack.checks.empty:
        return ""
    failed = broker_dispatch_ack.checks.loc[~broker_dispatch_ack.checks["passed"].astype(bool)]
    if failed.empty:
        return ""
    row = failed.iloc[0]
    return f"{row.get('check', '')}: {row.get('reason', '')}".strip(": ")


def _blocked_next_gate(checks: pd.DataFrame, broker_dispatch_ack: BrokerDispatchAckReport | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    return _next_gate_for_check(failed[0], broker_dispatch_ack)


def _next_gate_for_check(check: str, broker_dispatch_ack: BrokerDispatchAckReport | None) -> str:
    if check.startswith("provider_broker_dispatch_send"):
        return "prepare-provider-market-data-imbalance-broker-dispatch-send"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "plan-provider-market-data-imbalance-broker-dispatch"
    if check.startswith("broker_acks"):
        return "reconcile-provider-market-data-imbalance-broker-dispatch"
    if check == "broker_dispatch_ack_passed" and broker_dispatch_ack is not None:
        next_gate = _first_action_value(broker_dispatch_ack.action_queue, "next_gate")
        return next_gate or "reconcile-broker-dispatch"
    if check.startswith("broker_dispatch_ack"):
        return "reconcile-broker-dispatch"
    if check in {"strategy_identity_imbalance", "market_identity_consistent", "adapter_identity_consistent"}:
        return "prepare-provider-market-data-imbalance-broker-dispatch-send"
    return "reconcile-provider-market-data-imbalance-broker-dispatch"


def _help_command_for_gate(next_gate: str) -> str:
    if next_gate == "review-provider-market-data-imbalance-broker-dispatch-roundtrip":
        return "python -m hft_cli review-provider-market-data-imbalance-broker-dispatch-roundtrip --help"
    if next_gate == "prepare-provider-market-data-imbalance-broker-dispatch-send":
        return "python -m hft_cli prepare-provider-market-data-imbalance-broker-dispatch-send --help"
    if next_gate == "plan-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli plan-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "reconcile-provider-market-data-imbalance-broker-dispatch":
        return "python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch --help"
    if next_gate == "reconcile-broker-dispatch":
        return "python -m hft_cli reconcile-broker-dispatch --help"
    if next_gate == "review-broker-dispatch-roundtrip":
        return "python -m hft_cli review-broker-dispatch-roundtrip --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-cutover-gate":
        return "python -m hft_cli review-cutover-gate --help"
    if next_gate == "pipeline-vendor-market-data-batch":
        return "python -m hft_cli pipeline-vendor-market-data-batch --help"
    if next_gate == "pipeline-broker-vendor-readiness":
        return "python -m hft_cli pipeline-broker-vendor-readiness --help"
    if next_gate == "review-resume-gate":
        return "python -m hft_cli review-resume-gate --help"
    if next_gate == "review-broker-readiness":
        return "python -m hft_cli review-broker-readiness --help"
    return "python -m hft_cli reconcile-provider-market-data-imbalance-broker-dispatch --help"


def _component_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_send"):
        return "provider_broker_dispatch_send"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "broker_dispatch"
    if check.startswith("broker_acks") or check.startswith("broker_dispatch_ack"):
        return "broker_dispatch_ack"
    if check.endswith("identity_imbalance") or check.endswith("identity_consistent"):
        return "runtime_identity"
    return "provider_broker_dispatch_ack"


def _action_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_send"):
        return "repair_provider_imbalance_broker_dispatch_send"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "repair_provider_imbalance_broker_dispatch_inputs"
    if check.startswith("broker_acks") or check.startswith("broker_dispatch_ack"):
        return "repair_broker_dispatch_acknowledgements"
    return "repair_provider_imbalance_broker_dispatch_ack"


def _recommendation_for_check(check: str) -> str:
    if check.startswith("provider_broker_dispatch_send"):
        return "rerun_provider_broker_dispatch_send_before_ack_reconciliation"
    if check.startswith("generic_broker_dispatch") or check.startswith("nested_broker_dispatch"):
        return "rerun_provider_broker_dispatch_to_refresh_nested_dispatch_artifacts"
    if check.startswith("broker_acks"):
        return "capture_or_supply_broker_dry_run_ack_file"
    if check.startswith("broker_dispatch_ack"):
        return "rerun_generic_broker_ack_reconciliation_with_clean_ack_file"
    return "repair_provider_broker_dispatch_ack_inputs"


def _inferred_broker_dispatch_dir(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> Path | None:
    send_inputs = provider_config.get("broker_dispatch_send_inputs", {}) or {}
    nested_send_config = provider_config.get("broker_dispatch_send", {}) or {}
    nested_inputs = nested_send_config.get("config", {}).get("inputs", {}) if isinstance(nested_send_config, dict) else {}
    return _first_existing_path(
        _path_from_text(_first_text(provider_summary, "broker_dispatch_dir")),
        _path_from_text(send_inputs.get("broker_dispatch_dir")),
        _path_from_text(nested_inputs.get("dispatch_dir")),
    )


def _inferred_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    send_inputs = provider_config.get("broker_dispatch_send_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "provider_dispatch_roundtrip_dir")),
        _path_from_text(send_inputs.get("provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "dispatch_roundtrip_dir")),
        _path_from_text(send_inputs.get("dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _inferred_upstream_dispatch_roundtrip_dirs(
    provider_summary: pd.DataFrame,
    provider_config: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    send_inputs = provider_config.get("broker_dispatch_send_inputs", {}) or {}
    provider_dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_provider_dispatch_roundtrip_dir")),
        _path_from_text(send_inputs.get("upstream_provider_dispatch_roundtrip_dir")),
    )
    dispatch_roundtrip_dir = _first_existing_path(
        _path_from_text(_first_text(provider_summary, "upstream_dispatch_roundtrip_dir")),
        _path_from_text(send_inputs.get("upstream_dispatch_roundtrip_dir")),
    )
    return provider_dispatch_roundtrip_dir, dispatch_roundtrip_dir


def _explicit_or_inferred(
    explicit: str | Path | None,
    inferred: Path | None,
    config: ProviderMarketDataImbalanceBrokerDispatchAckConfig,
) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    if not config.use_provider_broker_dispatch_send_inputs:
        return None
    return inferred


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


def _source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_session_timezone"]),
        "open_local": str(summary["source_session_open_local"]),
        "close_local": str(summary["source_session_close_local"]),
    }


def _market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["market_session_timezone"]),
        "open_local": str(summary["market_session_open_local"]),
        "close_local": str(summary["market_session_close_local"]),
    }


def _capture_bundle_source_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_source_session_timezone"]),
        "open_local": str(summary["capture_bundle_source_session_open_local"]),
        "close_local": str(summary["capture_bundle_source_session_close_local"]),
    }


def _capture_bundle_market_session_contract_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["capture_bundle_market_session_timezone"]),
        "open_local": str(summary["capture_bundle_market_session_open_local"]),
        "close_local": str(summary["capture_bundle_market_session_close_local"]),
    }


def _source_live_fetch_contract_session_from_summary(summary: pd.Series) -> dict[str, str]:
    return {
        "timezone": str(summary["source_live_fetch_contract_session_timezone"]),
        "open_local": str(summary["source_live_fetch_contract_session_open_local"]),
        "close_local": str(summary["source_live_fetch_contract_session_close_local"]),
    }


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
