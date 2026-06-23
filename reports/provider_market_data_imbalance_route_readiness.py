from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.market_portability import (
    MarketPortabilityReport,
    MarketPortabilityReportConfig,
    write_market_portability_report,
)
from reports.route_readiness import RouteReadinessReview, write_route_readiness_review


PROFILE = "imbalance"
DEFAULT_MARKET = "india_nse_index_derivatives"
DEFAULT_PORTABILITY_STRATEGY = "microprice_imbalance"
RUN_TYPE = "provider_market_data_imbalance_route_readiness"


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRouteReadinessConfig:
    require_provider_launch_evidence_ready: bool = True
    require_route_readiness_ready: bool = True
    use_provider_launch_evidence_inputs: bool = True
    market: str = DEFAULT_MARKET
    strategy: str = DEFAULT_PORTABILITY_STRATEGY
    require_ops_file_inputs: bool = True
    build_market_portability: bool = True


@dataclass(frozen=True)
class ProviderMarketDataImbalanceRouteReadinessReport:
    market_portability: MarketPortabilityReport | None
    route_readiness: RouteReadinessReview | None
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


def write_provider_market_data_imbalance_route_readiness(
    provider_launch_evidence_dir: str | Path,
    output_dir: str | Path,
    *,
    market_portability_dir: str | Path | None = None,
    strategy_evidence_dir: str | Path | None = None,
    ops_evidence_dirs: tuple[str | Path, ...] = (),
    config: ProviderMarketDataImbalanceRouteReadinessConfig | None = None,
) -> ProviderMarketDataImbalanceRouteReadinessReport:
    config = config or ProviderMarketDataImbalanceRouteReadinessConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    launch_evidence_dir = Path(provider_launch_evidence_dir)
    launch_evidence_summary, launch_evidence_summary_error = _read_csv(
        launch_evidence_dir / "provider_market_data_imbalance_launch_evidence_summary.csv"
    )
    explicit_strategy_evidence_dir = Path(strategy_evidence_dir) if strategy_evidence_dir is not None else None
    inferred_strategy_evidence_dir = _first_existing_path(
        explicit_strategy_evidence_dir,
        _path_from_text(_first_text(launch_evidence_summary, "strategy_evidence_dir"))
        if config.use_provider_launch_evidence_inputs
        else None,
        _path_or_none(launch_evidence_dir / "strategy_evidence")
        if config.use_provider_launch_evidence_inputs
        else None,
    )
    market = (
        _first_text(launch_evidence_summary, "market")
        or config.market
        or DEFAULT_MARKET
    )
    strategy = config.strategy or DEFAULT_PORTABILITY_STRATEGY

    market_portability: MarketPortabilityReport | None = None
    market_portability_error = ""
    market_portability_config_path: Path | None = None
    resolved_market_portability_dir: Path | None = None
    if market_portability_dir is not None:
        resolved_market_portability_dir = Path(market_portability_dir)
        market_portability_config_path = _market_portability_config_path(resolved_market_portability_dir)
        if not market_portability_config_path.exists():
            market_portability_error = f"market portability config not found: {market_portability_config_path}"
    elif config.build_market_portability:
        resolved_market_portability_dir = out / "market_portability"
        try:
            market_portability = write_market_portability_report(
                resolved_market_portability_dir,
                config=MarketPortabilityReportConfig(
                    markets=(market,),
                    strategies=(strategy,),
                    explicit_fee_model=False,
                ),
            )
            market_portability_config_path = resolved_market_portability_dir / "market_portability_config.json"
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            market_portability_error = str(exc)
    else:
        market_portability_error = "market portability input is required when auto-build is disabled"

    strategy_summary_path = _strategy_evidence_summary_path(inferred_strategy_evidence_dir)
    route_readiness: RouteReadinessReview | None = None
    route_readiness_error = ""
    route_readiness_dir = out / "route_readiness"
    prechecks = _prechecks(
        launch_evidence_dir,
        launch_evidence_summary,
        launch_evidence_summary_error,
        inferred_strategy_evidence_dir,
        strategy_summary_path,
        market_portability_config_path,
        market_portability_error,
        market,
        strategy,
        config,
    )
    if bool(prechecks["passed"].all()):
        try:
            route_readiness = write_route_readiness_review(
                route_readiness_dir,
                market_portability=_path_or_empty(market_portability_config_path),
                strategy_evidence=(_path_or_empty(inferred_strategy_evidence_dir),),
                ops_evidence=tuple(Path(path) for path in ops_evidence_dirs),
                require_ops_file_inputs=config.require_ops_file_inputs,
            )
        except (OSError, ValueError, FileNotFoundError, pd.errors.ParserError) as exc:
            route_readiness_error = str(exc)
    else:
        route_readiness_error = "provider imbalance route-readiness prerequisites are not ready"

    checks = _checks(prechecks, route_readiness, route_readiness_error, launch_evidence_summary, config)
    summary = _summary(
        launch_evidence_dir,
        resolved_market_portability_dir,
        market_portability_config_path,
        inferred_strategy_evidence_dir,
        tuple(Path(path) for path in ops_evidence_dirs),
        route_readiness,
        checks,
        out,
        launch_evidence_summary,
        market,
        strategy,
    )
    action_queue = _action_queue(summary.iloc[0], checks, route_readiness)
    payload = _config(
        summary.iloc[0],
        launch_evidence_summary,
        market_portability,
        route_readiness,
        checks,
        action_queue,
        config,
    )

    checks.to_csv(out / "provider_market_data_imbalance_route_readiness_checks.csv", index=False)
    summary.to_csv(out / "provider_market_data_imbalance_route_readiness_summary.csv", index=False)
    action_queue.to_csv(out / "provider_market_data_imbalance_route_readiness_action_queue.csv", index=False)
    (out / "provider_market_data_imbalance_route_readiness_config.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "provider_market_data_imbalance_route_readiness_runbook.md").write_text(
        _runbook_markdown(summary.iloc[0], checks, action_queue),
        encoding="utf-8",
    )

    inputs: dict[str, Any] = {"provider_launch_evidence_dir": launch_evidence_dir}
    if resolved_market_portability_dir is not None:
        inputs["market_portability"] = resolved_market_portability_dir
    if market_portability_config_path is not None:
        inputs["market_portability_config"] = market_portability_config_path
    if inferred_strategy_evidence_dir is not None:
        inputs["strategy_evidence"] = inferred_strategy_evidence_dir
    for index, path in enumerate(ops_evidence_dirs, start=1):
        inputs[f"ops_evidence_{index}"] = Path(path)
    if route_readiness is not None and route_readiness.output_dir is not None:
        inputs["route_readiness"] = route_readiness.output_dir

    write_experiment_manifest(
        out,
        run_type=RUN_TYPE,
        parameters={"config": asdict(config)},
        inputs=inputs,
        extra={
            "ready": bool(summary.iloc[0]["ready"]),
            "route_readiness_ready": bool(summary.iloc[0]["route_readiness_ready"]),
            "profile": PROFILE,
            "strategy": str(summary.iloc[0]["strategy"]),
            "market": str(summary.iloc[0]["market"]),
        },
    )
    return ProviderMarketDataImbalanceRouteReadinessReport(
        market_portability,
        route_readiness,
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


def _prechecks(
    launch_evidence_dir: Path,
    launch_evidence_summary: pd.DataFrame,
    launch_evidence_summary_error: str,
    strategy_evidence_dir: Path | None,
    strategy_summary_path: Path | None,
    market_portability_config_path: Path | None,
    market_portability_error: str,
    market: str,
    strategy: str,
    config: ProviderMarketDataImbalanceRouteReadinessConfig,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _check(
                "provider_launch_evidence_dir_exists",
                str(launch_evidence_dir),
                "exists",
                True,
                launch_evidence_dir.exists(),
                "provider imbalance launch-evidence directory is required",
            ),
            _check(
                "provider_launch_evidence_summary_readable",
                launch_evidence_summary_error or "ok",
                "is",
                "ok",
                not launch_evidence_summary_error,
                launch_evidence_summary_error or "provider imbalance launch-evidence summary could not be read",
            ),
            _check(
                "provider_imbalance_launch_evidence_ready",
                _first_bool(launch_evidence_summary, "ready"),
                "is",
                True,
                _first_bool(launch_evidence_summary, "ready")
                or not config.require_provider_launch_evidence_ready,
                "provider imbalance launch evidence is not ready",
            ),
            _check(
                "strategy_evidence_dir_exists",
                _path_text(strategy_evidence_dir),
                "exists",
                True,
                bool(strategy_evidence_dir and strategy_evidence_dir.exists()),
                "strategy evidence directory from provider launch evidence is required",
            ),
            _check(
                "strategy_evidence_summary_exists",
                _path_text(strategy_summary_path),
                "exists",
                True,
                bool(strategy_summary_path and strategy_summary_path.exists()),
                "strategy evidence summary is required for route readiness",
            ),
            _check(
                "market_portability_config_exists",
                market_portability_error or _path_text(market_portability_config_path),
                "exists",
                True,
                bool(market_portability_config_path and market_portability_config_path.exists())
                and not market_portability_error,
                market_portability_error or "market portability config is required for route readiness",
            ),
            _check(
                "market_identity_present",
                market,
                "is_not",
                "",
                bool(market),
                "provider market identity is required for route readiness",
            ),
            _check(
                "portability_strategy_present",
                strategy,
                "is_not",
                "",
                bool(strategy),
                "market portability strategy is required for route readiness",
            ),
        ]
    )


def _checks(
    prechecks: pd.DataFrame,
    route_readiness: RouteReadinessReview | None,
    route_readiness_error: str,
    launch_evidence_summary: pd.DataFrame,
    config: ProviderMarketDataImbalanceRouteReadinessConfig,
) -> pd.DataFrame:
    rows = prechecks.to_dict(orient="records")
    route_summary = route_readiness.summary if route_readiness is not None else pd.DataFrame()
    route_ready = bool(route_readiness.ready) if route_readiness is not None else False
    rows.extend(
        [
            _check(
                "route_readiness_review_runnable",
                route_readiness_error or "ok",
                "is",
                "ok",
                not route_readiness_error and route_readiness is not None,
                route_readiness_error or "route readiness review could not be generated",
            ),
            _check(
                "route_readiness_ready",
                route_ready,
                "is",
                True,
                route_ready or not config.require_route_readiness_ready,
                _route_failure_reason(route_readiness) or "route readiness is not ready",
            ),
            _check(
                "strategy_identity_imbalance",
                _first_text(route_summary, "strategy") or _first_text(launch_evidence_summary, "strategy"),
                "is",
                DEFAULT_PORTABILITY_STRATEGY,
                _identity_key(_first_text(route_summary, "strategy") or _first_text(launch_evidence_summary, "strategy"))
                in {"imbalance", "microprice_imbalance"},
                "route readiness strategy did not resolve to imbalance",
            ),
            _check(
                "market_identity_consistent",
                _first_text(route_summary, "market") or _first_text(launch_evidence_summary, "market"),
                "is",
                _first_text(launch_evidence_summary, "market") or "present",
                bool(_first_text(route_summary, "market"))
                and (
                    not _first_text(launch_evidence_summary, "market")
                    or _identity_key(_first_text(route_summary, "market"))
                    == _identity_key(_first_text(launch_evidence_summary, "market"))
                ),
                "route readiness market identity does not match provider launch evidence",
            ),
        ]
    )
    return pd.DataFrame(rows)


def _summary(
    launch_evidence_dir: Path,
    market_portability_dir: Path | None,
    market_portability_config_path: Path | None,
    strategy_evidence_dir: Path | None,
    ops_evidence_dirs: tuple[Path, ...],
    route_readiness: RouteReadinessReview | None,
    checks: pd.DataFrame,
    output_dir: Path,
    launch_evidence_summary: pd.DataFrame,
    market: str,
    strategy: str,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    ready = failed == 0
    route_summary = route_readiness.summary if route_readiness is not None else pd.DataFrame()
    next_gate = "plan-provider-market-data-imbalance-scaleup" if ready else _blocked_next_gate(checks, route_readiness)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "provider_launch_evidence_ready": _first_bool(launch_evidence_summary, "ready"),
                "route_readiness_ready": bool(route_readiness.ready) if route_readiness is not None else False,
                "provider_launch_evidence_dir": str(launch_evidence_dir),
                "provider_launch_dir": _first_text(launch_evidence_summary, "provider_launch_dir"),
                "market_portability_dir": _path_text(market_portability_dir),
                "market_portability_config": _path_text(market_portability_config_path),
                "strategy_evidence_dir": _path_text(strategy_evidence_dir),
                "ops_evidence_dirs": ";".join(str(path) for path in ops_evidence_dirs),
                "route_readiness_dir": "" if route_readiness is None else str(route_readiness.output_dir or ""),
                "output_dir": str(output_dir),
                "profile": PROFILE,
                "provider": _first_text(launch_evidence_summary, "provider"),
                "transport": _first_text(launch_evidence_summary, "transport"),
                "market": _first_text(route_summary, "market") or market,
                "strategy": _first_text(route_summary, "strategy") or strategy,
                "target_mode": _first_text(launch_evidence_summary, "target_mode"),
                "adapter": _first_text(launch_evidence_summary, "adapter"),
                "route_ready_pairs": int(_first_number(route_summary, "route_ready_pairs")),
                "gap_pairs": int(_first_number(route_summary, "gap_pairs")),
                "strategy_evidence_ready_pairs": int(_first_number(route_summary, "strategy_evidence_ready_pairs")),
                "ops_evidence_ready_pairs": int(_first_number(route_summary, "ops_evidence_ready_pairs")),
                "ops_launch_controls_blocked_pairs": int(
                    _first_number(route_summary, "ops_launch_controls_blocked_pairs")
                ),
                "require_ops_file_inputs": _first_bool(route_summary, "require_ops_file_inputs"),
                "failed_checks": failed,
                "failed_check_names": ";".join(
                    checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
                ),
                "recommendation": "feed_provider_route_readiness_into_scaleup"
                if ready
                else "repair_provider_imbalance_route_readiness",
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate, route_readiness),
                "primary_action_status": "ready" if ready else "blocked",
            }
        ]
    )


def _action_queue(
    summary: pd.Series,
    checks: pd.DataFrame,
    route_readiness: RouteReadinessReview | None,
) -> pd.DataFrame:
    if bool(summary["ready"]):
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "queue_status": "ready",
                    "action": "plan_provider_imbalance_scaleup_with_route_readiness",
                    "reason": "provider imbalance route readiness is ready for provider scale-up planning",
                    "next_gate": "plan-provider-market-data-imbalance-scaleup",
                    "next_gate_help_command": _help_command_for_gate(
                        "plan-provider-market-data-imbalance-scaleup",
                        route_readiness,
                    ),
                }
            ]
        )
    rows: list[dict[str, Any]] = []
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    for check in failed:
        next_gate = _next_gate_for_check(check, route_readiness)
        rows.append(
            {
                "priority": len(rows) + 1,
                "queue_status": "blocked",
                "action": _repair_action(check, route_readiness),
                "reason": _reason_for_check(check, route_readiness),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command_for_gate(next_gate, route_readiness),
            }
        )
    if not rows:
        route_gate = _route_next_gate(route_readiness)
        rows.append(
            {
                "priority": 1,
                "queue_status": "blocked",
                "action": "repair_provider_imbalance_route_readiness",
                "reason": "provider imbalance route readiness is not ready",
                "next_gate": route_gate,
                "next_gate_help_command": _help_command_for_gate(route_gate, route_readiness),
            }
        )
    return pd.DataFrame(rows)


def _config(
    summary: pd.Series,
    launch_evidence_summary: pd.DataFrame,
    market_portability: MarketPortabilityReport | None,
    route_readiness: RouteReadinessReview | None,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
    config: ProviderMarketDataImbalanceRouteReadinessConfig,
) -> dict[str, Any]:
    actions = _records(action_queue)
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "parameters": asdict(config),
        "summary": _series_record(summary),
        "provider_launch_evidence": _first_record(launch_evidence_summary),
        "market_portability": {
            "ready": False if market_portability is None else bool(market_portability.ready),
            "output_dir": "" if market_portability is None else str(market_portability.output_dir or ""),
            "summary": _first_record(None if market_portability is None else market_portability.summary),
            "config": {} if market_portability is None else market_portability.config,
        },
        "route_readiness": {
            "ready": False if route_readiness is None else bool(route_readiness.ready),
            "output_dir": "" if route_readiness is None else str(route_readiness.output_dir or ""),
            "summary": _first_record(None if route_readiness is None else route_readiness.summary),
            "pairs": _records(None if route_readiness is None else route_readiness.pairs),
            "gaps": _records(None if route_readiness is None else route_readiness.gaps),
            "config": {} if route_readiness is None else route_readiness.config,
        },
        "checks": _records(checks),
        "next_gate": str(summary["next_gate"]),
        "next_gate_help_command": str(summary["next_gate_help_command"]),
        "next_actions": actions,
        "ready_actions": [row for row in actions if row.get("queue_status") == "ready"],
        "blocked_actions": [row for row in actions if row.get("queue_status") == "blocked"],
        "primary_action": actions[0] if actions else {},
    }


def _blocked_next_gate(checks: pd.DataFrame, route_readiness: RouteReadinessReview | None) -> str:
    failed = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if not failed:
        return _route_next_gate(route_readiness)
    return _next_gate_for_check(failed[0], route_readiness)


def _next_gate_for_check(check: str, route_readiness: RouteReadinessReview | None) -> str:
    if check.startswith("provider_launch_evidence") or check.startswith("provider_imbalance_launch_evidence"):
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("strategy_evidence") or check == "strategy_identity_imbalance":
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("market_portability") or check == "portability_strategy_present":
        return "market-portability-report"
    if check == "market_identity_present" or check == "market_identity_consistent":
        return "review-provider-market-data-imbalance-launch-evidence"
    if check.startswith("route_readiness"):
        return _route_next_gate(route_readiness)
    return "review-provider-market-data-imbalance-route-readiness"


def _route_next_gate(route_readiness: RouteReadinessReview | None) -> str:
    route_summary = route_readiness.summary if route_readiness is not None else pd.DataFrame()
    route_gate = _first_text(route_summary, "next_gate")
    if route_gate and route_gate != "live_dryrun_route_review":
        return route_gate
    return "review-route-readiness"


def _help_command_for_gate(next_gate: str, route_readiness: RouteReadinessReview | None = None) -> str:
    if next_gate == "plan-provider-market-data-imbalance-scaleup":
        return "python -m hft_cli plan-provider-market-data-imbalance-scaleup --help"
    if next_gate == "review-provider-market-data-imbalance-launch-evidence":
        return "python -m hft_cli review-provider-market-data-imbalance-launch-evidence --help"
    if next_gate == "market-portability-report":
        return "python -m hft_cli market-portability-report --help"
    if next_gate == "review-route-readiness":
        return "python -m hft_cli review-route-readiness --help"
    if next_gate == "review-provider-market-data-imbalance-route-readiness":
        return "python -m hft_cli review-provider-market-data-imbalance-route-readiness --help"
    route_summary = route_readiness.summary if route_readiness is not None else pd.DataFrame()
    route_help = _first_text(route_summary, "next_gate_help_command")
    if route_help and next_gate == _first_text(route_summary, "next_gate"):
        return route_help
    if next_gate.startswith("review-strategy-evidence"):
        return f"python -m hft_cli {next_gate} --help"
    return ""


def _repair_action(check: str, route_readiness: RouteReadinessReview | None) -> str:
    if check.startswith("provider_launch_evidence") or check.startswith("provider_imbalance_launch_evidence"):
        return "review_full_provider_imbalance_launch_evidence"
    if check.startswith("strategy_evidence") or check == "strategy_identity_imbalance":
        return "review_provider_strategy_evidence_before_route_readiness"
    if check.startswith("market_portability") or check == "portability_strategy_present":
        return "build_market_portability_for_provider_route"
    if check.startswith("route_readiness"):
        return _route_repair_action(route_readiness)
    return "repair_provider_imbalance_route_readiness"


def _route_repair_action(route_readiness: RouteReadinessReview | None) -> str:
    action_queue = route_readiness.action_queue if route_readiness is not None else pd.DataFrame()
    if action_queue is not None and not action_queue.empty:
        recommendation = _first_text(action_queue, "recommendation")
        if recommendation:
            return recommendation
    return "repair_provider_imbalance_route_readiness"


def _reason_for_check(check: str, route_readiness: RouteReadinessReview | None) -> str:
    if check == "route_readiness_ready":
        return _route_failure_reason(route_readiness) or "route readiness review is not ready"
    return check.replace("_", " ")


def _route_failure_reason(route_readiness: RouteReadinessReview | None) -> str:
    action_queue = route_readiness.action_queue if route_readiness is not None else pd.DataFrame()
    if action_queue is not None and not action_queue.empty:
        blocked = action_queue.loc[action_queue["queue_status"].astype(str) == "blocked"]
        if not blocked.empty:
            row = blocked.iloc[0]
            status = _text(row.get("status"))
            recommendation = _text(row.get("recommendation"))
            next_gate = _text(row.get("next_gate"))
            return ": ".join(item for item in [status, recommendation, next_gate] if item)
    route_summary = route_readiness.summary if route_readiness is not None else pd.DataFrame()
    return _first_text(route_summary, "recommendation")


def _runbook_markdown(summary: pd.Series, checks: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    lines = [
        "# Provider Market Data Imbalance Route Readiness",
        "",
        f"- Ready: {'yes' if bool(summary['ready']) else 'no'}",
        f"- Provider: {summary['provider']}",
        f"- Market: {summary['market']}",
        f"- Strategy: {summary['strategy']}",
        f"- Route readiness dir: {summary['route_readiness_dir']}",
        f"- Next gate: `{summary['next_gate']}`",
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


def _market_portability_config_path(path: Path) -> Path:
    return path / "market_portability_config.json" if path.is_dir() else path


def _strategy_evidence_summary_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path / "strategy_evidence_summary.csv" if path.is_dir() else path


def _first_existing_path(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.exists():
            return path
    for path in paths:
        if path is not None:
            return path
    return None


def _path_from_text(value: str) -> Path | None:
    return Path(value) if value else None


def _path_or_none(path: Path) -> Path | None:
    return path


def _path_or_empty(path: Path | None) -> Path:
    return path if path is not None else Path("__missing__")


def _path_text(path: Path | None) -> str:
    return "" if path is None else str(path)


def _identity_key(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _first_record(frame: pd.DataFrame | None) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    return {str(key): _jsonable(value) for key, value in frame.iloc[0].to_dict().items()}


def _series_record(row: pd.Series) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.to_dict().items()}


def _records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [{str(key): _jsonable(value) for key, value in row.items()} for row in frame.to_dict(orient="records")]


def _first_text(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    return _text(frame.iloc[0][column])


def _first_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    return _truthy(frame.iloc[0][column])


def _first_number(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return _number(frame.iloc[0][column])


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
    return _text(value).lower() in {"1", "true", "yes", "ready", "pass"}


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


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
