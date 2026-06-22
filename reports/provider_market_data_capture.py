from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import file_sha256, write_experiment_manifest


SUPPORTED_PROVIDERS = {"arrow_money", "irage"}
LIVE_TRANSPORTS = {"rest", "websocket"}


@dataclass(frozen=True)
class ProviderMarketDataCaptureConfig:
    min_rows: int = 1
    max_missing_required_columns: int = 0
    max_null_required_cells: int = 0
    require_monotonic_ts: bool = True
    expected_market: str = ""
    expected_kind: str = ""
    pipeline_output_dir: str = ""


@dataclass(frozen=True)
class ProviderMarketDataCaptureReport:
    checks: pd.DataFrame
    summary: pd.DataFrame
    columns: pd.DataFrame
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_provider_market_data_capture(
    client_packet_path: str | Path,
    capture_path: str | Path,
    *,
    config: ProviderMarketDataCaptureConfig | None = None,
) -> ProviderMarketDataCaptureReport:
    config = _normalize_config(config or ProviderMarketDataCaptureConfig())
    packet_path = Path(client_packet_path)
    data_path = Path(capture_path)
    packet, packet_error = _read_packet(packet_path)
    frame, capture_error = _read_capture(data_path)
    columns = _columns(frame, packet)
    checks = pd.DataFrame(_checks(packet_path, data_path, packet, packet_error, frame, capture_error, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    summary = _summary(packet_path, data_path, packet, frame, checks, ready, config)
    action_queue = _action_queue(summary.iloc[0], checks, config)
    summary = _summary_with_actions(summary, action_queue)
    capture_config = _config(summary.iloc[0], columns, checks, action_queue, packet, config)
    return ProviderMarketDataCaptureReport(checks, summary, columns, action_queue, capture_config)


def write_provider_market_data_capture_review(
    client_packet_path: str | Path,
    capture_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataCaptureConfig | None = None,
) -> ProviderMarketDataCaptureReport:
    report = evaluate_provider_market_data_capture(client_packet_path, capture_path, config=config)
    normalized = _normalize_config(config or ProviderMarketDataCaptureConfig())
    packet_path = Path(client_packet_path)
    data_path = Path(capture_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.checks.to_csv(out / "provider_market_data_capture_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_capture_summary.csv", index=False)
    report.columns.to_csv(out / "provider_market_data_capture_columns.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_capture_action_queue.csv", index=False)
    (out / "provider_market_data_capture_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_capture_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {}
    if packet_path.exists():
        inputs["client_packet"] = packet_path
    if data_path.exists():
        inputs["capture"] = data_path
    write_experiment_manifest(
        out,
        run_type="provider_market_data_capture_review",
        parameters={
            "client_packet_path": str(packet_path),
            "capture_path": str(data_path),
            "config": asdict(normalized),
        },
        inputs=inputs,
        extra={
            "capture": report.config["capture"],
            "normalized_pipeline": report.config["normalized_pipeline"],
        },
    )
    return ProviderMarketDataCaptureReport(
        report.checks,
        report.summary,
        report.columns,
        report.action_queue,
        report.config,
        out,
    )


def _normalize_config(config: ProviderMarketDataCaptureConfig) -> ProviderMarketDataCaptureConfig:
    return ProviderMarketDataCaptureConfig(
        min_rows=int(config.min_rows),
        max_missing_required_columns=int(config.max_missing_required_columns),
        max_null_required_cells=int(config.max_null_required_cells),
        require_monotonic_ts=bool(config.require_monotonic_ts),
        expected_market=_identity_key(config.expected_market),
        expected_kind=_identity_key(config.expected_kind),
        pipeline_output_dir=str(config.pipeline_output_dir or "").strip(),
    )


def _read_packet(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "client packet file does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"client packet file is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"client packet JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "client packet JSON must be an object"
    return payload, ""


def _read_capture(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), "capture CSV file does not exist"
    try:
        frame = pd.read_csv(path)
    except OSError as exc:
        return pd.DataFrame(), f"capture CSV file is not readable: {exc}"
    except pd.errors.EmptyDataError:
        return pd.DataFrame(), "capture CSV file is empty"
    except pd.errors.ParserError as exc:
        return pd.DataFrame(), f"capture CSV parse failed: {exc}"
    return frame, ""


def _checks(
    packet_path: Path,
    capture_path: Path,
    packet: dict[str, Any],
    packet_error: str,
    frame: pd.DataFrame,
    capture_error: str,
    config: ProviderMarketDataCaptureConfig,
) -> list[dict[str, Any]]:
    required_columns = _required_columns(packet)
    missing_columns = [column for column in required_columns if column not in frame.columns]
    null_required_cells = _null_required_cells(frame, required_columns)
    parsed_ts = _parsed_ts(frame)
    return [
        _check(
            "client_packet_path_exists",
            str(packet_path),
            "exists",
            True,
            packet_path.exists(),
            "provider client packet is required",
        ),
        _check(
            "client_packet_json_readable",
            packet_error or "ok",
            "is",
            "ok",
            not packet_error,
            packet_error or "provider client packet JSON could not be read",
        ),
        _check(
            "client_packet_ready",
            bool(packet.get("ready")),
            "is",
            True,
            bool(packet.get("ready")),
            "provider client packet must be ready before capture review",
        ),
        _check(
            "client_execution_mode_dry_run",
            _text(packet.get("execution_mode")),
            "==",
            "dry_run",
            _text(packet.get("execution_mode")) == "dry_run",
            "capture review expects the dry-run client packet contract",
        ),
        _check(
            "provider_supported",
            _text(packet.get("provider")),
            "in",
            sorted(SUPPORTED_PROVIDERS),
            _text(packet.get("provider")) in SUPPORTED_PROVIDERS,
            "provider capture review supports Arrow.money and iRage packet contracts",
        ),
        _check(
            "transport_is_live",
            _text(packet.get("transport")),
            "in",
            sorted(LIVE_TRANSPORTS),
            _text(packet.get("transport")) in LIVE_TRANSPORTS,
            "capture review expects REST or websocket provider captures",
        ),
        _check(
            "credential_values_not_stored",
            bool(_mapping(packet.get("authentication")).get("values_stored", True)),
            "is",
            False,
            bool(_mapping(packet.get("authentication")).get("values_stored", True)) is False,
            "client packet must not store credential values",
        ),
        _check(
            "capture_path_exists",
            str(capture_path),
            "exists",
            True,
            capture_path.exists(),
            "provider capture CSV is required",
        ),
        _check(
            "capture_csv_readable",
            capture_error or "ok",
            "is",
            "ok",
            not capture_error,
            capture_error or "provider capture CSV could not be read",
        ),
        _check(
            "capture_min_rows",
            int(len(frame)),
            ">=",
            config.min_rows,
            int(len(frame)) >= config.min_rows,
            "provider capture does not meet the minimum row threshold",
        ),
        _check(
            "output_schema_present",
            len(required_columns),
            ">=",
            1,
            len(required_columns) >= 1,
            "client packet must carry normalized output schema columns",
        ),
        _check(
            "required_columns_present",
            len(missing_columns),
            "<=",
            config.max_missing_required_columns,
            len(missing_columns) <= config.max_missing_required_columns,
            "provider capture is missing required normalized columns",
        ),
        _check(
            "required_columns_not_null",
            null_required_cells,
            "<=",
            config.max_null_required_cells,
            null_required_cells <= config.max_null_required_cells,
            "provider capture has nulls in required normalized columns",
        ),
        _check(
            "timestamp_column_present",
            "ts" in frame.columns,
            "is",
            True,
            "ts" in frame.columns,
            "provider capture must include normalized ts column",
        ),
        _check(
            "timestamp_parseable",
            int(parsed_ts.notna().sum()) if not parsed_ts.empty else 0,
            "==",
            int(len(frame)),
            bool("ts" in frame.columns and len(frame) == int(parsed_ts.notna().sum())),
            "provider capture ts column must be parseable for every row",
        ),
        _check(
            "timestamp_monotonic",
            bool(parsed_ts.is_monotonic_increasing) if not parsed_ts.empty else False,
            "is",
            True if config.require_monotonic_ts else "optional",
            bool(parsed_ts.is_monotonic_increasing) if config.require_monotonic_ts and not parsed_ts.empty else True,
            "provider capture timestamps must be monotonic increasing",
        ),
        _check(
            "market_matches_expected",
            _text(packet.get("market")),
            "==",
            config.expected_market or _text(packet.get("market")),
            (not config.expected_market) or _identity_key(packet.get("market")) == config.expected_market,
            "provider capture packet market does not match expected market",
        ),
        _check(
            "kind_matches_expected",
            _text(packet.get("kind")),
            "==",
            config.expected_kind or _text(packet.get("kind")),
            (not config.expected_kind) or _identity_key(packet.get("kind")) == config.expected_kind,
            "provider capture packet kind does not match expected data kind",
        ),
    ]


def _summary(
    packet_path: Path,
    capture_path: Path,
    packet: dict[str, Any],
    frame: pd.DataFrame,
    checks: pd.DataFrame,
    ready: bool,
    config: ProviderMarketDataCaptureConfig,
) -> pd.DataFrame:
    required_columns = _required_columns(packet)
    missing_columns = [column for column in required_columns if column not in frame.columns]
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    capture_exists = capture_path.exists()
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "client_packet_path": str(packet_path),
                "capture_path": str(capture_path),
                "capture_file_sha256": file_sha256(capture_path) if capture_exists and capture_path.is_file() else "",
                "provider": _text(packet.get("provider")),
                "adapter": _text(packet.get("adapter")),
                "market": _text(packet.get("market")),
                "kind": _text(packet.get("kind")),
                "transport": _text(packet.get("transport")),
                "template_kind": _text(packet.get("template_kind")),
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "required_columns": ";".join(required_columns),
                "missing_required_columns": ";".join(missing_columns),
                "missing_required_column_count": int(len(missing_columns)),
                "null_required_cells": int(_null_required_cells(frame, required_columns)),
                "extra_columns": ";".join([column for column in frame.columns if column not in required_columns]),
                "min_rows": int(config.min_rows),
                "pipeline_output_dir": _pipeline_output_dir(packet, capture_path, config),
                "failed_checks": failed_checks,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                )
                if not checks.empty
                else "",
                "recommendation": "provider_market_data_capture_ready"
                if ready
                else "fix_provider_market_data_capture",
            }
        ]
    )


def _summary_with_actions(summary: pd.DataFrame, action_queue: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    ready_actions = int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0
    blocked_actions = (
        int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    )
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    out["ready_action_count"] = ready_actions
    out["blocked_action_count"] = blocked_actions
    out["next_gate"] = "" if next_action is None else str(next_action["next_gate"])
    out["next_gate_help_command"] = "" if next_action is None else str(next_action["next_gate_help_command"])
    out["primary_action_status"] = "" if next_action is None else str(next_action["queue_status"])
    return out


def _columns(frame: pd.DataFrame, packet: dict[str, Any]) -> pd.DataFrame:
    required_columns = _required_columns(packet)
    rows = []
    for position, column in enumerate(frame.columns, start=1):
        series = frame[column]
        rows.append(
            {
                "position": position,
                "column": str(column),
                "required": str(column) in required_columns,
                "null_count": int(series.isna().sum()),
                "non_null_count": int(series.notna().sum()),
                "dtype": str(series.dtype),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["position", "column", "required", "null_count", "non_null_count", "dtype"],
    )


def _action_queue(summary: pd.Series, checks: pd.DataFrame, config: ProviderMarketDataCaptureConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        next_gate = _blocked_next_gate(str(row["check"]))
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(str(row["check"])),
                "reason": str(row["reason"]),
                "provider": str(summary["provider"]),
                "kind": str(summary["kind"]),
                "transport": str(summary["transport"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and bool(summary["ready"]):
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "run_provider_capture_market_data_pipeline",
                "reason": "provider capture matches the client packet and normalized schema",
                "provider": str(summary["provider"]),
                "kind": str(summary["kind"]),
                "transport": str(summary["transport"]),
                "next_gate": "pipeline-vendor-market-data",
                "next_gate_help_command": _pipeline_command(summary, config),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "action",
            "reason",
            "provider",
            "kind",
            "transport",
            "next_gate",
            "next_gate_help_command",
        ],
    )


def _config(
    summary: pd.Series,
    columns: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    packet: dict[str, Any],
    config: ProviderMarketDataCaptureConfig,
) -> dict[str, Any]:
    failed_checks = _failed_checks(checks)
    ready_actions = _queue_records(action_queue, "ready")
    blocked_actions = _queue_records(action_queue, "blocked")
    next_action = _first_record(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "client_packet": {
            "path": str(summary["client_packet_path"]),
            "ready": bool(packet.get("ready")),
            "provider": str(summary["provider"]),
            "adapter": str(summary["adapter"]),
            "market": str(summary["market"]),
            "kind": str(summary["kind"]),
            "transport": str(summary["transport"]),
            "template_kind": str(summary["template_kind"]),
            "credential_values_stored": bool(_mapping(packet.get("authentication")).get("values_stored", True)),
        },
        "capture": {
            "path": str(summary["capture_path"]),
            "file_sha256": str(summary["capture_file_sha256"]),
            "rows": int(summary["rows"]),
            "columns": _records(columns),
            "required_columns": _split_items(summary["required_columns"]),
            "missing_required_columns": _split_items(summary["missing_required_columns"]),
            "null_required_cells": int(summary["null_required_cells"]),
        },
        "normalized_pipeline": {
            "available": bool(summary["ready"]),
            "next_gate": "pipeline-vendor-market-data" if bool(summary["ready"]) else "",
            "command": _pipeline_command(summary, config) if bool(summary["ready"]) else "",
            "output_dir": str(summary["pipeline_output_dir"]),
        },
        "failed_check_count": len(failed_checks),
        "failed_checks": failed_checks,
        "ready_action_count": len(ready_actions),
        "blocked_action_count": len(blocked_actions),
        "next_gate": "" if next_action is None else str(next_action["next_gate"]),
        "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
        "next_actions": _records(action_queue),
        "ready_actions": ready_actions,
        "blocked_actions": blocked_actions,
        "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
        "primary_action": {} if next_action is None else next_action,
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Capture Review Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Kind: {summary['kind']}",
        f"- Transport: {summary['transport']}",
        f"- Rows: {summary['rows']}",
        f"- Missing required columns: {summary['missing_required_columns'] or 'none'}",
        f"- Null required cells: {summary['null_required_cells']}",
        f"- Pipeline output: {summary['pipeline_output_dir']}",
        "",
        "## Actions",
    ]
    if action_queue.empty:
        lines.append("- None")
    else:
        for _, row in action_queue.iterrows():
            lines.append(
                f"- [{row['queue_status']}] {row['action']}: {row['reason']} "
                f"(`{row['next_gate_help_command']}`)"
            )
    return "\n".join(lines) + "\n"


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
        "value": _jsonable(value),
        "operator": operator,
        "threshold": _jsonable(threshold),
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _required_columns(packet: dict[str, Any]) -> list[str]:
    output = _mapping(packet.get("output"))
    return [str(column) for column in _list(output.get("schema_columns")) if str(column)]


def _null_required_cells(frame: pd.DataFrame, required_columns: list[str]) -> int:
    present = [column for column in required_columns if column in frame.columns]
    if not present:
        return 0
    return int(frame[present].isna().sum().sum())


def _parsed_ts(frame: pd.DataFrame) -> pd.Series:
    if "ts" not in frame.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(frame["ts"], errors="coerce")


def _pipeline_output_dir(packet: dict[str, Any], capture_path: Path, config: ProviderMarketDataCaptureConfig) -> str:
    if config.pipeline_output_dir:
        return config.pipeline_output_dir
    provider = _identity_key(packet.get("provider")) or "provider"
    kind = _identity_key(packet.get("kind")) or "ticks"
    stem = _safe_stem(capture_path.stem or "capture")
    return f"runs/provider_market_data_pipeline/{provider}_{kind}_{stem}"


def _pipeline_command(summary: pd.Series, config: ProviderMarketDataCaptureConfig) -> str:
    return (
        "python -m hft_cli pipeline-vendor-market-data "
        f"--input {_shell_quote(summary['capture_path'])} "
        f"--out {_shell_quote(_pipeline_output_dir_from_summary(summary, config))} "
        "--adapter normalized "
        f"--kind {summary['kind']} "
        f"--market {summary['market']} "
        "--fail-on-blocked-actions --fail-on-breach"
    )


def _pipeline_output_dir_from_summary(summary: pd.Series, config: ProviderMarketDataCaptureConfig) -> str:
    if config.pipeline_output_dir:
        return config.pipeline_output_dir
    value = str(summary.get("pipeline_output_dir", ""))
    return value or "runs/provider_market_data_pipeline/provider_capture"


def _blocked_next_gate(check: str) -> str:
    if check.startswith("client") or check in {
        "provider_supported",
        "transport_is_live",
        "credential_values_not_stored",
        "output_schema_present",
    }:
        return "prepare-provider-market-data-client"
    return "review-provider-market-data-capture"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate == "prepare-provider-market-data-client":
        return "python -m hft_cli prepare-provider-market-data-client --help"
    if next_gate == "review-provider-market-data-capture":
        return "python -m hft_cli review-provider-market-data-capture --help"
    if next_gate == "pipeline-vendor-market-data":
        return "python -m hft_cli pipeline-vendor-market-data --help"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("client"):
        return "repair_or_regenerate_provider_market_data_client_packet"
    if check in {"provider_supported", "transport_is_live", "credential_values_not_stored", "output_schema_present"}:
        return "repair_provider_client_contract"
    if check.startswith("capture"):
        return "provide_readable_provider_capture_csv"
    if check.startswith("required_columns") or check.startswith("timestamp"):
        return "repair_provider_capture_normalized_schema"
    if check.endswith("matches_expected"):
        return "select_matching_provider_capture_packet"
    return "repair_provider_market_data_capture"


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _split_items(value: object) -> list[str]:
    text = str(value or "")
    if not text:
        return []
    return [item for item in text.split(";") if item]


def _identity_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def _safe_stem(value: str) -> str:
    text = _identity_key(value)
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_") or "capture"


def _shell_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"' if re.search(r"\s", escaped) else escaped


def _failed_checks(checks: pd.DataFrame) -> list[dict[str, Any]]:
    if checks.empty:
        return []
    return _records(checks.loc[~checks["passed"].astype(bool)])


def _queue_records(action_queue: pd.DataFrame, status: str) -> list[dict[str, Any]]:
    if action_queue.empty:
        return []
    return _records(action_queue.loc[action_queue["queue_status"].astype(str) == status])


def _first_record(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame.empty:
        return None
    return _records(frame.iloc[[0]])[0]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        rows.append({str(key): _jsonable(value) for key, value in record.items()})
    return rows


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, tuple):
        return list(value)
    return value
