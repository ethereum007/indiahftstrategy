from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


SUPPORTED_STRATEGIES = {"imbalance"}
DEFAULT_STRATEGIES = ("imbalance",)


@dataclass(frozen=True)
class ProviderMarketDataResearchHandoffConfig:
    strategies: tuple[str, ...] = field(default_factory=lambda: DEFAULT_STRATEGIES)
    require_research_ready: bool = True
    allow_synthetic_smoke: bool = False
    min_tick_folds: int = 2
    tick_size: float = 0.05
    market: str = ""
    instrument_id: str = "PROVIDER_BOOK"
    output_root: str = "runs/provider_market_data_research"


@dataclass(frozen=True)
class ProviderMarketDataResearchHandoffReport:
    datasets: pd.DataFrame
    commands: pd.DataFrame
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


def write_provider_market_data_research_handoff(
    live_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ProviderMarketDataResearchHandoffConfig | None = None,
) -> ProviderMarketDataResearchHandoffReport:
    report = evaluate_provider_market_data_research_handoff(live_evidence_dir, config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.datasets.to_csv(out / "provider_market_data_research_handoff_datasets.csv", index=False)
    report.commands.to_csv(out / "provider_market_data_research_handoff_commands.csv", index=False)
    report.checks.to_csv(out / "provider_market_data_research_handoff_checks.csv", index=False)
    report.summary.to_csv(out / "provider_market_data_research_handoff_summary.csv", index=False)
    report.action_queue.to_csv(out / "provider_market_data_research_handoff_action_queue.csv", index=False)
    (out / "provider_market_data_research_handoff_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_research_handoff_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], report.datasets, report.commands, report.action_queue),
        encoding="utf-8",
    )
    evidence_dir = Path(live_evidence_dir)
    inputs: dict[str, Any] = {"live_evidence_dir": evidence_dir} if evidence_dir.exists() else {}
    capture_paths = [Path(str(path)) for path in report.datasets["capture_path"].astype(str).tolist()] if not report.datasets.empty else []
    if capture_paths:
        inputs["captures"] = [path for path in capture_paths if path.exists()]
    write_experiment_manifest(
        out,
        run_type="provider_market_data_research_handoff",
        parameters={"config": asdict(config or ProviderMarketDataResearchHandoffConfig())},
        inputs=inputs,
        extra={
            "ready": bool(report.summary.iloc[0]["ready"]),
            "research_ready": bool(report.summary.iloc[0]["research_ready"]),
            "ready_command_count": int(report.summary.iloc[0]["ready_command_count"]),
            "blocked_action_count": int(report.summary.iloc[0]["blocked_action_count"]),
        },
    )
    return ProviderMarketDataResearchHandoffReport(
        report.datasets,
        report.commands,
        report.checks,
        report.summary,
        report.action_queue,
        report.config,
        out,
    )


def evaluate_provider_market_data_research_handoff(
    live_evidence_dir: str | Path,
    *,
    config: ProviderMarketDataResearchHandoffConfig | None = None,
) -> ProviderMarketDataResearchHandoffReport:
    config = _normalize_config(config or ProviderMarketDataResearchHandoffConfig())
    evidence_dir = Path(live_evidence_dir)
    evidence_summary, summary_error = _read_csv(evidence_dir / "provider_market_data_live_evidence_summary.csv")
    evidence_captures, captures_error = _read_csv(evidence_dir / "provider_market_data_live_evidence_captures.csv")
    evidence_config, config_error = _read_json(evidence_dir / "provider_market_data_live_evidence_config.json")
    manifest, manifest_error = _read_json(evidence_dir / "manifest.json")
    datasets = _datasets(evidence_captures)
    commands = _commands(evidence_summary, datasets, config)
    checks = pd.DataFrame(
        _checks(
            evidence_dir,
            evidence_summary,
            summary_error,
            evidence_captures,
            captures_error,
            evidence_config,
            config_error,
            manifest,
            manifest_error,
            datasets,
            commands,
            config,
        )
    )
    ready = bool(not checks.empty and checks["passed"].astype(bool).all())
    action_queue = _action_queue(checks, commands, ready)
    summary = _summary(evidence_dir, evidence_summary, datasets, commands, checks, action_queue, config, ready)
    handoff_config = _config(summary.iloc[0], evidence_dir, evidence_summary, evidence_config, manifest, datasets, commands, checks, action_queue, config)
    return ProviderMarketDataResearchHandoffReport(datasets, commands, checks, summary, action_queue, handoff_config)


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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"{path.name} is not readable: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"{path.name} JSON is invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{path.name} JSON must be an object"
    return payload, ""


def _datasets(captures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(captures.to_dict(orient="records") if not captures.empty else [], start=1):
        capture_path = Path(_text(row.get("capture_path")))
        rows.append(
            {
                "priority": index,
                "fold_label": _text(row.get("pipeline_label"), _text(row.get("label"), f"fold_{index}")),
                "capture_path": str(capture_path),
                "capture_exists": bool(capture_path.exists() and capture_path.is_file()),
                "capture_rows": int(_number(row.get("capture_rows"))),
                "synthetic_rehearsal": _truthy(row.get("synthetic_rehearsal")),
                "role": "tick_fold",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "fold_label",
            "capture_path",
            "capture_exists",
            "capture_rows",
            "synthetic_rehearsal",
            "role",
        ],
    )


def _commands(
    evidence_summary: pd.DataFrame,
    datasets: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    market = _effective_market(evidence_summary, config)
    output_root = Path(config.output_root)
    ticks = datasets["capture_path"].astype(str).tolist() if not datasets.empty else []
    labels = datasets["fold_label"].astype(str).tolist() if not datasets.empty else []
    requested = tuple(config.strategies)
    if "imbalance" in requested:
        edge_out = output_root / "imbalance_edge"
        replay_out = output_root / "imbalance_replay"
        rows.append(
            _command(
                "ready",
                "imbalance",
                "imbalance_edge_walkforward",
                "walkforward-imbalance-edge",
                _imbalance_edge_command(ticks, labels, edge_out, market, config),
                str(edge_out),
                "provider tick folds are ready for imbalance edge discovery",
            )
        )
        rows.append(
            _command(
                "ready",
                "imbalance",
                "imbalance_replay_walkforward",
                "walkforward-imbalance-replay",
                _imbalance_replay_command(ticks, labels, edge_out, replay_out, market, config),
                str(replay_out),
                "replay the selected imbalance candidate after edge discovery writes candidate_config.json",
            )
        )
    for strategy in requested:
        if strategy not in SUPPORTED_STRATEGIES:
            rows.append(
                _command(
                    "blocked",
                    strategy,
                    "unsupported_provider_research_handoff",
                    _unsupported_gate(strategy),
                    "",
                    "",
                    _unsupported_reason(strategy),
                )
            )
    for priority, row in enumerate(rows, start=1):
        row["priority"] = priority
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "strategy",
            "run_type",
            "next_gate",
            "command",
            "output_dir",
            "reason",
        ],
    )


def _command(status: str, strategy: str, run_type: str, next_gate: str, command: str, output_dir: str, reason: str) -> dict[str, Any]:
    return {
        "priority": 0,
        "queue_status": status,
        "strategy": strategy,
        "run_type": run_type,
        "next_gate": next_gate,
        "command": command,
        "output_dir": output_dir,
        "reason": reason,
    }


def _imbalance_edge_command(
    ticks: list[str],
    labels: list[str],
    output_dir: Path,
    market: str,
    config: ProviderMarketDataResearchHandoffConfig,
) -> str:
    parts = [
        "python",
        "-m",
        "hft_cli",
        "walkforward-imbalance-edge",
        "--ticks",
        *ticks,
        "--out",
        str(output_dir),
    ]
    for label in labels:
        parts.extend(["--label", label])
    parts.extend(
        [
            "--market",
            market,
            "--tick-size",
            str(config.tick_size),
            "--entry-imbalance",
            "0.55",
            "0.65",
            "0.75",
            "--min-microprice-edge-ticks",
            "0.25",
            "0.50",
            "1.00",
            "--forward-horizon-ns",
            "100000000",
            "500000000",
            "1000000000",
            "--min-signals",
            "1",
            "--min-passed-configs",
            "1",
            "--fail-on-breach",
        ]
    )
    return " ".join(_shell_quote(part) for part in parts)


def _imbalance_replay_command(
    ticks: list[str],
    labels: list[str],
    edge_out: Path,
    output_dir: Path,
    market: str,
    config: ProviderMarketDataResearchHandoffConfig,
) -> str:
    parts = [
        "python",
        "-m",
        "hft_cli",
        "walkforward-imbalance-replay",
        "--ticks",
        *ticks,
        "--out",
        str(output_dir),
        "--candidate-config",
        str(edge_out / "candidate_config.json"),
    ]
    for label in labels:
        parts.extend(["--label", label])
    parts.extend(
        [
            "--market",
            market,
            "--instrument-id",
            config.instrument_id,
            "--tick-size",
            str(config.tick_size),
            "--qty",
            "75",
            "--min-fills",
            "1",
            "--min-folds",
            str(config.min_tick_folds),
            "--fail-on-breach",
        ]
    )
    return " ".join(_shell_quote(part) for part in parts)


def _checks(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    summary_error: str,
    evidence_captures: pd.DataFrame,
    captures_error: str,
    evidence_config: dict[str, Any],
    config_error: str,
    manifest: dict[str, Any],
    manifest_error: str,
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
) -> list[dict[str, Any]]:
    dataset_count = int(len(datasets))
    synthetic_count = int(datasets["synthetic_rehearsal"].astype(bool).sum()) if not datasets.empty else 0
    ready_commands = int((commands["queue_status"].astype(str) == "ready").sum()) if not commands.empty else 0
    blocked_commands = int((commands["queue_status"].astype(str) == "blocked").sum()) if not commands.empty else 0
    unsupported = [strategy for strategy in config.strategies if strategy not in SUPPORTED_STRATEGIES]
    return [
        _check("live_evidence_dir_exists", str(evidence_dir), "exists", True, evidence_dir.exists(), "live evidence directory is required"),
        _check("live_evidence_summary_readable", summary_error or "ok", "is", "ok", not summary_error, summary_error or "live evidence summary could not be read"),
        _check("live_evidence_captures_readable", captures_error or "ok", "is", "ok", not captures_error, captures_error or "live evidence captures could not be read"),
        _check("live_evidence_config_readable", config_error or "ok", "is", "ok", not config_error, config_error or "live evidence config could not be read"),
        _check("live_evidence_manifest_readable", manifest_error or "ok", "is", "ok", not manifest_error, manifest_error or "live evidence manifest could not be read"),
        _check("live_evidence_manifest_type", _text(manifest.get("run_type")), "is", "provider_market_data_live_evidence_review", _text(manifest.get("run_type")) == "provider_market_data_live_evidence_review", "live evidence manifest run_type is not expected"),
        _check("live_evidence_ready", _first_bool(evidence_summary, "ready"), "is", True, _first_bool(evidence_summary, "ready"), "live evidence review is not ready"),
        _check("live_evidence_research_ready", _first_bool(evidence_summary, "research_ready"), "is", True, _first_bool(evidence_summary, "research_ready") or not config.require_research_ready, "live evidence is not research-ready"),
        _check("synthetic_rehearsal_absent", synthetic_count, "==", 0 if not config.allow_synthetic_smoke else "allowed", synthetic_count == 0 or config.allow_synthetic_smoke, "synthetic rehearsal captures cannot be handed to strategy research"),
        _check("tick_folds_present", dataset_count, ">=", config.min_tick_folds, dataset_count >= config.min_tick_folds, "not enough tick folds for walk-forward research"),
        _check("tick_fold_files_exist", int(datasets["capture_exists"].astype(bool).sum()) if not datasets.empty else 0, "==", dataset_count, bool(dataset_count and datasets["capture_exists"].astype(bool).all()), "all tick fold files must exist"),
        _check("tick_fold_rows_positive", int((datasets["capture_rows"].astype(int) > 0).sum()) if not datasets.empty else 0, "==", dataset_count, bool(dataset_count and (datasets["capture_rows"].astype(int) > 0).all()), "all tick folds must contain rows"),
        _check("requested_strategies_supported", ";".join(unsupported), "is", "", not unsupported, "some requested strategies need extra inputs before provider tick handoff"),
        _check("ready_research_commands_present", ready_commands, ">=", 1, ready_commands >= 1, "at least one ready research command is required"),
        _check("blocked_research_commands_absent", blocked_commands, "==", 0, blocked_commands == 0, "blocked research commands remain"),
        _check("tick_size_positive", config.tick_size, ">", 0, config.tick_size > 0, "tick size must be positive"),
    ]


def _summary(
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
    ready: bool,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    blocked = int((action_queue["queue_status"].astype(str) == "blocked").sum()) if not action_queue.empty else 0
    ready_actions = int((action_queue["queue_status"].astype(str) == "ready").sum()) if not action_queue.empty else 0
    next_action = action_queue.iloc[0] if not action_queue.empty else None
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "research_ready": bool(ready and _first_bool(evidence_summary, "research_ready")),
                "live_evidence_dir": str(evidence_dir),
                "provider": _first_text(evidence_summary, "provider"),
                "transport": _first_text(evidence_summary, "transport"),
                "market": _effective_market(evidence_summary, config),
                "kind": _first_text(evidence_summary, "kind"),
                "strategy": ";".join(config.strategies),
                "strategy_profiles": ";".join(config.strategies),
                "dataset_count": int(len(datasets)),
                "ready_command_count": int((commands["queue_status"].astype(str) == "ready").sum()) if not commands.empty else 0,
                "blocked_command_count": int((commands["queue_status"].astype(str) == "blocked").sum()) if not commands.empty else 0,
                "synthetic_dataset_count": int(datasets["synthetic_rehearsal"].astype(bool).sum()) if not datasets.empty else 0,
                "failed_checks": failed,
                "failed_check_names": ";".join(checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()) if not checks.empty else "",
                "ready_action_count": ready_actions,
                "blocked_action_count": blocked,
                "next_gate": "" if next_action is None else str(next_action["next_gate"]),
                "next_gate_help_command": "" if next_action is None else str(next_action["next_gate_help_command"]),
                "primary_action_status": "" if next_action is None else str(next_action["queue_status"]),
                "recommendation": "run_provider_market_data_strategy_research" if ready else "fix_provider_market_data_research_handoff",
            }
        ]
    )


def _action_queue(checks: pd.DataFrame, commands: pd.DataFrame, ready: bool) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
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
        for _, command in commands.loc[commands["queue_status"].astype(str) == "ready"].iterrows():
            rows.append(
                {
                    "priority": len(rows) + 1,
                    "queue_status": "ready",
                    "action": f"run_{command['run_type']}",
                    "reason": str(command["reason"]),
                    "next_gate": str(command["next_gate"]),
                    "next_gate_help_command": str(command["command"]),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["priority", "queue_status", "action", "reason", "next_gate", "next_gate_help_command"],
    )


def _config(
    summary: pd.Series,
    evidence_dir: Path,
    evidence_summary: pd.DataFrame,
    evidence_config: dict[str, Any],
    manifest: dict[str, Any],
    datasets: pd.DataFrame,
    commands: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataResearchHandoffConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "research_ready": bool(summary["research_ready"]),
        "parameters": asdict(config),
        "live_evidence_dir": str(evidence_dir),
        "evidence_summary": _first_record(evidence_summary),
        "evidence_manifest_run_type": _text(manifest.get("run_type")),
        "evidence_config_ready": bool(evidence_config.get("ready", False)),
        "datasets": _records(datasets),
        "commands": _records(commands),
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action_status": str(summary["primary_action_status"]),
        "primary_action": actions[0] if actions else {},
    }


def _next_gate_for_check(check: str) -> str:
    if check.startswith("live_evidence"):
        return "review-provider-market-data-live-evidence"
    if check.startswith("synthetic"):
        return "provider_fetcher_live_run"
    if check.startswith("tick_fold"):
        return "review-provider-market-data-live-evidence"
    if check.startswith("requested_strategies"):
        return "handoff-provider-market-data-research"
    if check.startswith("ready_research") or check.startswith("blocked_research"):
        return "handoff-provider-market-data-research"
    return "handoff-provider-market-data-research"


def _next_gate_help_command(next_gate: str) -> str:
    if next_gate in {"review-provider-market-data-live-evidence", "handoff-provider-market-data-research"}:
        return f"python -m hft_cli {next_gate} --help"
    if next_gate == "provider_fetcher_live_run":
        return "replace synthetic captures with real Arrow.money/iRage provider captures"
    return ""


def _repair_action(check: str) -> str:
    if check.startswith("live_evidence"):
        return "repair_live_evidence_review"
    if check.startswith("synthetic"):
        return "replace_synthetic_captures_with_real_provider_data"
    if check.startswith("tick_fold"):
        return "collect_more_provider_tick_folds"
    if check.startswith("requested_strategies"):
        return "provide_extra_strategy_inputs_or_select_imbalance"
    return "repair_provider_market_data_research_handoff"


def _unsupported_gate(strategy: str) -> str:
    if strategy == "leadlag":
        return "walkforward-leadlag-replay"
    if strategy == "settlement":
        return "walkforward-settlement-convergence"
    if strategy == "surface_mm":
        return "pipeline-surface-mm-research"
    if strategy == "parity":
        return "audit-parity-edge"
    return "handoff-provider-market-data-research"


def _unsupported_reason(strategy: str) -> str:
    if strategy == "leadlag":
        return "lead-lag needs explicit leader/laggard capture groups"
    if strategy in {"settlement", "parity", "surface_mm"}:
        return "this strategy needs option-chain or surface inputs in addition to top-of-book ticks"
    return "strategy is not supported by provider tick research handoff"


def _effective_market(evidence_summary: pd.DataFrame, config: ProviderMarketDataResearchHandoffConfig) -> str:
    return config.market or _first_text(evidence_summary, "market") or "india_nse_index_derivatives"


def _runbook_markdown(summary: pd.Series, datasets: pd.DataFrame, commands: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Research Handoff",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Market: {summary['market']}",
        f"- Strategies: {summary['strategy_profiles']}",
        f"- Tick folds: {summary['dataset_count']}",
        f"- Ready commands: {summary['ready_command_count']}",
        "",
        "## Datasets",
        "",
        _datasets_table(datasets),
        "",
        "## Research Commands",
        "",
        _commands_table(commands),
        "",
        "## Actions",
        "",
        _actions_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _datasets_table(datasets: pd.DataFrame) -> str:
    if datasets.empty:
        return "_None_"
    rows = []
    for row in datasets.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("fold_label")),
                _text(row.get("capture_path")),
                str(row.get("capture_rows", "")),
                "yes" if _truthy(row.get("synthetic_rehearsal")) else "no",
            ]
        )
    return _markdown_table(["#", "Fold", "Capture", "Rows", "Synthetic"], rows)


def _commands_table(commands: pd.DataFrame) -> str:
    if commands.empty:
        return "_None_"
    rows = []
    for row in commands.to_dict(orient="records"):
        rows.append(
            [
                str(row.get("priority", "")),
                _text(row.get("queue_status")),
                _text(row.get("strategy")),
                _text(row.get("run_type")),
                _text(row.get("command")),
            ]
        )
    return _markdown_table(["#", "Status", "Strategy", "Run type", "Command"], rows)


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


def _check(check: str, value: object, operator: str, threshold: object, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _normalize_config(config: ProviderMarketDataResearchHandoffConfig) -> ProviderMarketDataResearchHandoffConfig:
    strategies = tuple(_normalize_strategy(item) for item in config.strategies if _normalize_strategy(item))
    return ProviderMarketDataResearchHandoffConfig(
        strategies=strategies or DEFAULT_STRATEGIES,
        require_research_ready=bool(config.require_research_ready),
        allow_synthetic_smoke=bool(config.allow_synthetic_smoke),
        min_tick_folds=int(config.min_tick_folds),
        tick_size=float(config.tick_size),
        market=str(config.market or "").strip(),
        instrument_id=str(config.instrument_id or "PROVIDER_BOOK").strip(),
        output_root=str(config.output_root or "runs/provider_market_data_research").strip(),
    )


def _normalize_strategy(value: object) -> str:
    text = _text(value).lower().replace("-", "_")
    aliases = {
        "microprice_imbalance": "imbalance",
        "lead_lag": "leadlag",
        "lead_lag_taker": "leadlag",
        "settlement_convergence": "settlement",
        "parity_box": "parity",
        "surface_market_making": "surface_mm",
    }
    return aliases.get(text, text)


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _first_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame, column: str) -> bool:
    if frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


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


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(value)
    return _text(value).lower() in {"1", "true", "yes", "ready"}


def _number(value: object) -> float:
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _shell_quote(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() or ch in "'\"`" for ch in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
