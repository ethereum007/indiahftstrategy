from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.provider_market_data_live_ingest import (
    ProviderMarketDataLiveIngestConfig,
    ProviderMarketDataLiveIngestReport,
    write_provider_market_data_live_session_ingest,
)


CAPTURE_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]


@dataclass(frozen=True)
class ProviderMarketDataLiveRehearsalConfig:
    rows_per_window: int = 5
    base_price: float = 100.0
    tick_size: float = 0.05
    overwrite_captures: bool = False
    run_ingest: bool = True
    ingest_output_dir: str = ""
    ingest_min_capture_rows: int = 1
    ingest_pipeline_min_rows: int = 1


@dataclass(frozen=True)
class ProviderMarketDataLiveRehearsalReport:
    captures: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    ingest: ProviderMarketDataLiveIngestReport | None
    action_queue: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def write_provider_market_data_live_rehearsal(
    capture_bundle_path: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataLiveRehearsalConfig | None = None,
) -> ProviderMarketDataLiveRehearsalReport:
    report = evaluate_provider_market_data_live_rehearsal(capture_bundle_path, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.captures.to_csv(out / "provider_market_data_live_rehearsal_captures.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_live_rehearsal_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_live_rehearsal_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_live_rehearsal_action_queue.csv", index=False)
    (out / "provider_market_data_live_rehearsal_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_live_rehearsal_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.captures, report.action_queue),
        encoding="utf-8",
    )
    bundle_path = Path(capture_bundle_path)
    inputs: dict[str, Any] = {"capture_bundle": bundle_path} if bundle_path.exists() else {}
    env_template_text = str(report.summary.iloc[0]["env_template_path"])
    env_template_path = Path(env_template_text) if env_template_text else None
    if env_template_path is not None and env_template_path.exists():
        inputs["capture_env_template"] = env_template_path
    adapter_handoff_text = str(report.summary.iloc[0]["adapter_handoff_path"])
    adapter_handoff_path = Path(adapter_handoff_text) if adapter_handoff_text else None
    if adapter_handoff_path is not None and adapter_handoff_path.exists():
        inputs["adapter_handoff"] = adapter_handoff_path
    source_env_template_text = str(report.summary.iloc[0]["source_credential_env_template_path"])
    source_env_template_path = Path(source_env_template_text) if source_env_template_text else None
    if source_env_template_path is not None and source_env_template_path.exists():
        inputs["source_credential_env_template"] = source_env_template_path
    live_session_packet = Path(str(report.summary.iloc[0]["live_session_packet_path"]))
    if live_session_packet.exists():
        inputs["live_session_packet"] = live_session_packet
    captures = [Path(str(path)) for path in report.captures["capture_path"].astype(str).tolist()] if not report.captures.empty else []
    existing_captures = [path for path in captures if path.exists()]
    if existing_captures:
        inputs["synthetic_captures"] = existing_captures
    ingest_manifest = Path(str(report.summary.iloc[0]["ingest_output_dir"])) / "manifest.json"
    if ingest_manifest.exists():
        inputs["ingest_manifest"] = ingest_manifest
    write_experiment_manifest(
        out,
        run_type="provider_market_data_live_rehearsal",
        parameters={"config": asdict(config or ProviderMarketDataLiveRehearsalConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "synthetic_only": True,
            "capture_count": int(report.summary.iloc[0]["capture_count"]),
            "ingest_ready": bool(report.summary.iloc[0]["ingest_ready"]),
            "blocked_action_count": int(report.summary.iloc[0]["blocked_action_count"]),
            "source_credential_env_template": {
                "path": source_env_template_text,
                "exists": bool(report.summary.iloc[0]["source_credential_env_template_exists"]),
                "sha256": str(report.summary.iloc[0]["source_credential_env_template_sha256"]),
            },
            "live_fetch_contract": _mapping(report.config.get("live_fetch_contract")),
        },
    )
    return ProviderMarketDataLiveRehearsalReport(
        report.captures,
        report.checks,
        report.summary,
        report.ingest,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_live_rehearsal(
    capture_bundle_path: str | Path,
    *,
    config: ProviderMarketDataLiveRehearsalConfig | None = None,
) -> ProviderMarketDataLiveRehearsalReport:
    config = _normalize_config(config or ProviderMarketDataLiveRehearsalConfig())
    bundle_path = Path(capture_bundle_path)
    bundle, bundle_error = _read_bundle(bundle_path)
    captures = _captures_from_bundle(bundle)
    pre_checks = pd.DataFrame(_pre_checks(bundle_path, bundle, bundle_error, captures, config))
    pre_ready = bool(not pre_checks.empty and pre_checks["passed"].astype(bool).all())
    if pre_ready:
        captures = _write_synthetic_captures(captures, config)
    ingest = _run_ingest(bundle, captures, config) if pre_ready and config.run_ingest else None
    checks = pd.DataFrame(_checks(pre_checks, ingest, config))
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    action_queue = _action_queue(checks, ready, config)
    summary = _summary(bundle_path, bundle, captures, checks, ingest, action_queue, config, ready)
    rehearsal_config = _config(summary.iloc[0], bundle_path, bundle, captures, checks, ingest, action_queue, config)
    return ProviderMarketDataLiveRehearsalReport(captures, checks, summary, ingest, action_queue, rehearsal_config)


def _read_bundle(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "capture bundle does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"capture bundle is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"capture bundle JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "capture bundle JSON must be an object"
    return payload, ""


def _captures_from_bundle(bundle: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for index, item in enumerate(_list(bundle.get("commands")), start=1):
        command = _mapping(item)
        capture_path = _text(command.get("capture_path"))
        exists = bool(capture_path and Path(capture_path).exists() and Path(capture_path).is_file())
        rows.append(
            {
                "priority": index,
                "label": _text(command.get("label"), f"window_{index}"),
                "pipeline_label": _text(command.get("pipeline_label"), _text(command.get("label"), f"window_{index}")),
                "start_local": _text(command.get("start_local")),
                "end_local": _text(command.get("end_local")),
                "capture_path": capture_path,
                "preexisting_capture": exists,
                "synthetic_rows_written": 0,
                "synthetic_capture_sha256": "",
                "sidecar_path": "",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "label",
            "pipeline_label",
            "start_local",
            "end_local",
            "capture_path",
            "preexisting_capture",
            "synthetic_rows_written",
            "synthetic_capture_sha256",
            "sidecar_path",
        ],
    )


def _pre_checks(
    bundle_path: Path,
    bundle: dict[str, Any],
    bundle_error: str,
    captures: pd.DataFrame,
    config: ProviderMarketDataLiveRehearsalConfig,
) -> list[dict[str, Any]]:
    capture_count = int(len(captures))
    existing = int(captures["preexisting_capture"].astype(bool).sum()) if not captures.empty else 0
    unique_paths = bool(captures["capture_path"].astype(str).nunique() == len(captures)) if not captures.empty else False
    paths_present = bool(captures["capture_path"].astype(str).str.len().gt(0).all()) if not captures.empty else False
    times_present = bool(
        captures["start_local"].astype(str).str.len().gt(0).all()
        and captures["end_local"].astype(str).str.len().gt(0).all()
    ) if not captures.empty else False
    source_env_template = _source_credential_env_template(bundle_path, bundle)
    live_fetch_contract = _live_fetch_contract(bundle)
    return [
        _check("capture_bundle_path_exists", str(bundle_path), "exists", True, bundle_path.exists(), "capture bundle is required"),
        _check("capture_bundle_json_readable", bundle_error or "ok", "is", "ok", not bundle_error, bundle_error or "capture bundle could not be read"),
        _check("capture_bundle_ready", bool(bundle.get("ready")), "is", True, bool(bundle.get("ready")), "capture bundle must be ready before rehearsal"),
        _check("bundle_source_credential_env_template_carried", _text(source_env_template.get("path")), "exists", True, bool(source_env_template.get("exists")) and bool(_text(source_env_template.get("sha256"))), "capture bundle must carry source credential env-template proof"),
        _check("bundle_live_fetch_contract_carried", bool(live_fetch_contract.get("available")), "is", True, bool(live_fetch_contract.get("available")) and _text(live_fetch_contract.get("next_gate")) == "provider_fetcher", "capture bundle must carry the upstream live fetch-contract handoff"),
        _check("synthetic_only_marker", True, "is", True, True, ""),
        _check("rows_per_window_positive", config.rows_per_window, ">", 0, config.rows_per_window > 0, "rows per window must be positive"),
        _check("tick_size_positive", config.tick_size, ">", 0, config.tick_size > 0, "tick size must be positive"),
        _check("capture_commands_present", capture_count, ">=", 1, capture_count >= 1, "capture bundle must include at least one command"),
        _check("capture_paths_present", paths_present, "is", True, paths_present, "all capture commands must include capture paths"),
        _check("capture_paths_unique", capture_count, "unique", capture_count, unique_paths, "capture paths must be unique"),
        _check("capture_times_present", times_present, "is", True, times_present, "all capture commands must include start/end times"),
        _check("capture_files_do_not_already_exist", existing, "==", 0 if not config.overwrite_captures else "allowed", config.overwrite_captures or existing == 0, "capture files already exist; pass overwrite only for rehearsal sandboxes"),
    ]


def _write_synthetic_captures(
    captures: pd.DataFrame,
    config: ProviderMarketDataLiveRehearsalConfig,
) -> pd.DataFrame:
    out = captures.copy()
    for index, row in out.iterrows():
        capture_path = Path(str(row["capture_path"]))
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        frame = _synthetic_frame(row, index, config)
        frame.to_csv(capture_path, index=False)
        sidecar = capture_path.with_suffix(capture_path.suffix + ".rehearsal.json")
        sidecar.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "synthetic_only": True,
                    "source": "provider_market_data_live_rehearsal",
                    "rows": int(len(frame)),
                    "capture_path": str(capture_path),
                    "label": str(row["label"]),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        out.at[index, "synthetic_rows_written"] = int(len(frame))
        out.at[index, "synthetic_capture_sha256"] = _file_sha256(capture_path)
        out.at[index, "sidecar_path"] = str(sidecar)
    return out


def _synthetic_frame(row: pd.Series, window_index: int, config: ProviderMarketDataLiveRehearsalConfig) -> pd.DataFrame:
    start = _parse_datetime(str(row["start_local"]))
    records = []
    base = config.base_price + float(window_index)
    for offset in range(config.rows_per_window):
        ts = start + timedelta(seconds=offset)
        bid = base + offset * config.tick_size
        ask = bid + config.tick_size
        records.append(
            {
                "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "bid": round(bid, 6),
                "ask": round(ask, 6),
                "bid_qty": 75 + offset,
                "ask_qty": 150 + offset,
                "last": round(ask, 6),
                "last_qty": 50 + offset,
            }
        )
    return pd.DataFrame(records, columns=CAPTURE_COLUMNS)


def _run_ingest(
    bundle: dict[str, Any],
    captures: pd.DataFrame,
    config: ProviderMarketDataLiveRehearsalConfig,
) -> ProviderMarketDataLiveIngestReport | None:
    packet_path = _text(bundle.get("live_session_packet_path"))
    if not packet_path:
        return None
    ingest_out = config.ingest_output_dir or _default_ingest_output(bundle, captures)
    return write_provider_market_data_live_session_ingest(
        packet_path,
        ingest_out,
        config=ProviderMarketDataLiveIngestConfig(
            min_capture_rows=config.ingest_min_capture_rows,
            pipeline_min_rows=config.ingest_pipeline_min_rows,
        ),
    )


def _checks(
    pre_checks: pd.DataFrame,
    ingest: ProviderMarketDataLiveIngestReport | None,
    config: ProviderMarketDataLiveRehearsalConfig,
) -> list[dict[str, Any]]:
    rows = pre_checks.to_dict(orient="records") if not pre_checks.empty else []
    if config.run_ingest:
        rows.append(
            _check(
                "ingest_ran",
                ingest is not None,
                "is",
                True,
                ingest is not None,
                "live ingest rehearsal must run after synthetic captures are written",
            )
        )
        rows.append(
            _check(
                "ingest_ready",
                bool(ingest.ready) if ingest is not None else False,
                "is",
                True,
                bool(ingest.ready) if ingest is not None else False,
                "synthetic captures did not pass live ingest pipeline",
            )
        )
    else:
        rows.append(_check("ingest_skipped", True, "is", True, True, ""))
    return rows


def _summary(
    bundle_path: Path,
    bundle: dict[str, Any],
    captures: pd.DataFrame,
    checks: pd.DataFrame,
    ingest: ProviderMarketDataLiveIngestReport | None,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveRehearsalConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    ingest_ready = bool(ingest.ready) if ingest is not None else False
    ingest_output_dir = "" if ingest is None or ingest.output_dir is None else str(ingest.output_dir)
    env_template_path = _env_template_path(bundle_path, bundle)
    adapter_handoff_path = _adapter_handoff_path(bundle_path, bundle)
    source_env_template = _source_credential_env_template(bundle_path, bundle)
    live_fetch_contract = _live_fetch_contract(bundle)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "synthetic_only": True,
                "capture_bundle_path": str(bundle_path),
                "env_template_path": _path_text(env_template_path),
                "env_template_provided": bool(env_template_path),
                "env_template_exists": bool(env_template_path is not None and env_template_path.exists()),
                "adapter_handoff_path": _path_text(adapter_handoff_path),
                "adapter_handoff_provided": bool(adapter_handoff_path),
                "adapter_handoff_exists": bool(
                    adapter_handoff_path is not None and adapter_handoff_path.exists()
                ),
                "source_credential_env_template_path": _text(source_env_template.get("path")),
                "source_credential_env_template_exists": bool(source_env_template.get("exists")),
                "source_credential_env_template_sha256": _text(source_env_template.get("sha256")),
                "source_live_fetch_contract_available": bool(live_fetch_contract.get("available")),
                "source_live_fetch_contract_next_gate": _text(live_fetch_contract.get("next_gate")),
                "source_live_fetch_contract_command_template": _text(live_fetch_contract.get("command_template")),
                "live_session_packet_path": _text(bundle.get("live_session_packet_path")),
                "provider": _text(bundle.get("provider")),
                "transport": _text(bundle.get("transport")),
                "market": _text(bundle.get("market")),
                "kind": _text(bundle.get("kind")),
                "capture_count": int(len(captures)),
                "rows_per_window": int(config.rows_per_window),
                "synthetic_rows_written": int(pd.to_numeric(captures["synthetic_rows_written"], errors="coerce").sum()) if not captures.empty else 0,
                "overwrite_captures": bool(config.overwrite_captures),
                "run_ingest": bool(config.run_ingest),
                "ingest_ready": ingest_ready,
                "ingest_output_dir": ingest_output_dir,
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0,
                "blocked_action_count": blocked,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "provider_live_rehearsal_passed" if ready else "fix_provider_live_rehearsal",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, ready: bool, config: ProviderMarketDataLiveRehearsalConfig) -> pd.DataFrame:
    rows = []
    failed = checks.loc[~checks["passed"].astype(bool)] if not checks.empty else pd.DataFrame()
    for _, row in failed.iterrows():
        check = str(row["check"])
        next_gate = _next_gate_for_check(check)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check),
                "reason": str(row["reason"]),
                "next_gate": next_gate,
                "next_gate_help_command": _next_gate_help_command(next_gate),
            }
        )
    if not rows and ready:
        rows.append(
            {
                "priority": 1,
                "queue_status": "ready",
                "action": "replace_synthetic_captures_with_provider_live_captures",
                "reason": "synthetic rehearsal passed; do not use rehearsal captures as market-data evidence",
                "next_gate": "provider_fetcher_live_run" if config.run_ingest else "ingest-provider-market-data-live-session",
                "next_gate_help_command": "run the provider adapter bundle against Arrow.money/iRage credentials, then ingest real captures",
            }
        )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _config(
    summary: pd.Series,
    bundle_path: Path,
    bundle: dict[str, Any],
    captures: pd.DataFrame,
    checks: pd.DataFrame,
    ingest: ProviderMarketDataLiveIngestReport | None,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataLiveRehearsalConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "synthetic_only": True,
        "parameters": asdict(config),
        "capture_bundle_path": str(bundle_path),
        "env_template_path": str(summary["env_template_path"]),
        "env_template_provided": bool(summary["env_template_provided"]),
        "env_template_exists": bool(summary["env_template_exists"]),
        "adapter_handoff_path": str(summary["adapter_handoff_path"]),
        "adapter_handoff_provided": bool(summary["adapter_handoff_provided"]),
        "adapter_handoff_exists": bool(summary["adapter_handoff_exists"]),
        "source_credential_env_template": _source_credential_env_template_contract(summary),
        "live_fetch_contract": _live_fetch_contract(bundle),
        "live_session_packet_path": _text(bundle.get("live_session_packet_path")),
        "captures": _records(captures),
        "checks": _records(checks),
        "ingest": _ingest_config(ingest),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": actions[0] if actions else {},
    }


def _ingest_config(ingest: ProviderMarketDataLiveIngestReport | None) -> dict[str, Any]:
    if ingest is None:
        return {"ready": False, "output_dir": ""}
    row = ingest.summary.iloc[0] if not ingest.summary.empty else pd.Series(dtype=object)
    return {
        "ready": bool(ingest.ready),
        "output_dir": "" if ingest.output_dir is None else str(ingest.output_dir),
        "summary": {str(key): _jsonable(value) for key, value in row.to_dict().items()},
    }


def _next_gate_for_check(check: str) -> str:
    if check.startswith("capture_bundle"):
        return "bundle-provider-market-data-live-capture"
    if check in {"bundle_source_credential_env_template_carried", "bundle_live_fetch_contract_carried"}:
        return "bundle-provider-market-data-live-capture"
    if check.startswith("capture_") or check in {"rows_per_window_positive", "tick_size_positive"}:
        return "rehearse-provider-market-data-live-capture"
    if check.startswith("ingest"):
        return "ingest-provider-market-data-live-session"
    return "provider_fetcher_live_run"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {
        "bundle-provider-market-data-live-capture",
        "rehearse-provider-market-data-live-capture",
        "ingest-provider-market-data-live-session",
    }:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_fetcher_live_run":
        return "run the provider adapter bundle against Arrow.money/iRage credentials"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("capture_bundle"):
        return "repair_provider_live_capture_bundle"
    if check == "bundle_source_credential_env_template_carried":
        return "regenerate_capture_bundle_with_source_env_template"
    if check == "bundle_live_fetch_contract_carried":
        return "regenerate_capture_bundle_with_live_fetch_contract"
    if check == "capture_files_do_not_already_exist":
        return "choose_rehearsal_sandbox_or_allow_overwrite"
    if check.startswith("capture_"):
        return "repair_rehearsal_capture_plan"
    if check.startswith("ingest"):
        return "repair_provider_live_ingest_rehearsal"
    return "repair_provider_live_rehearsal"


def _runbook_markdown(summary: pd.Series, captures: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Live Rehearsal Runbook",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        "- Synthetic only: yes",
        f"- Captures: {summary['capture_count']}",
        f"- Rows per window: {summary['rows_per_window']}",
        f"- Credential env template: {summary['env_template_path']}",
        f"- Source credential env template: {summary['source_credential_env_template_path'] or 'missing'}",
        f"- Adapter handoff: {summary['adapter_handoff_path']}",
        f"- Ingest ready: {'yes' if bool(summary['ingest_ready']) else 'no'}",
        "",
        "## Synthetic Captures",
        "",
        _captures_table(captures),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _captures_table(captures: pd.DataFrame) -> str:
    if captures.empty:
        return "_None_"
    rows = []
    for row in captures.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("label")),
                _text(row.get("capture_path")),
                str(row.get("synthetic_rows_written", "")),
                _text(row.get("synthetic_capture_sha256"))[:12],
            ]
        )
    return _markdown_table(["#", "Label", "Capture", "Rows", "SHA256"], rows)


def _actions_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = []
    for row in action_queue.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("queue_status")),
                _text(row.get("action")),
                _text(row.get("next_gate")),
                _text(row.get("reason")),
            ]
        )
    return _markdown_table(["#", "Status", "Action", "Next gate", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _default_ingest_output(bundle: dict[str, Any], captures: pd.DataFrame) -> str:
    provider = _safe_label(_text(bundle.get("provider"), "provider"))
    market = _safe_label(_text(bundle.get("market"), "market"))
    day = "session"
    if not captures.empty:
        start = _text(captures.iloc[0].get("start_local"))
        if len(start) >= 10:
            day = start[:10].replace("-", "_")
    return f"runs/provider_market_data_live_rehearsal_ingest/{provider}_{market}_{day}"


def _env_template_path(bundle_path: Path, bundle: dict[str, Any]) -> Path | None:
    template = _text(_mapping(bundle.get("authentication")).get("env_template"))
    if not template:
        return None
    path = Path(template)
    if path.is_absolute():
        return path
    return bundle_path.parent / path


def _adapter_handoff_path(bundle_path: Path, bundle: dict[str, Any]) -> Path | None:
    handoff = _text(bundle.get("adapter_handoff")) or "provider_market_data_adapter_handoff.json"
    path = Path(handoff)
    if path.is_absolute():
        return path
    return bundle_path.parent / path


def _source_credential_env_template(bundle_path: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    env_template = _mapping(bundle.get("source_credential_env_template"))
    if not env_template:
        env_template = _mapping(_mapping(bundle.get("authentication")).get("source_env_template"))
    path = _path_from_text(_text(env_template.get("path")), bundle_path.parent)
    return {
        "path": _path_text(path),
        "exists": bool(path is not None and path.exists()),
        "sha256": _text(env_template.get("sha256")),
    }


def _live_fetch_contract(bundle: dict[str, Any]) -> dict[str, Any]:
    contract = _mapping(bundle.get("live_fetch_contract"))
    if not contract:
        contract = _mapping(_mapping(bundle.get("preflight")).get("live_fetch_contract"))
    return contract.copy()


def _source_credential_env_template_contract(summary: pd.Series) -> dict[str, Any]:
    return {
        "path": str(summary["source_credential_env_template_path"]),
        "exists": bool(summary["source_credential_env_template_exists"]),
        "sha256": str(summary["source_credential_env_template_sha256"]),
    }


def _path_from_text(value: str, base_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromisoformat("2026-01-01T09:15:00+05:30")
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _normalize_config(config: ProviderMarketDataLiveRehearsalConfig) -> ProviderMarketDataLiveRehearsalConfig:
    return ProviderMarketDataLiveRehearsalConfig(
        rows_per_window=int(config.rows_per_window),
        base_price=float(config.base_price),
        tick_size=float(config.tick_size),
        overwrite_captures=bool(config.overwrite_captures),
        run_ingest=bool(config.run_ingest),
        ingest_output_dir=str(config.ingest_output_dir or "").strip(),
        ingest_min_capture_rows=int(config.ingest_min_capture_rows),
        ingest_pipeline_min_rows=int(config.ingest_pipeline_min_rows),
    )


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _text(value: object, fallback: str = "") -> str:
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else fallback


def _safe_label(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value).strip())
    return safe.strip("._-") or "session"


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
