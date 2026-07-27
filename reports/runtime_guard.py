from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.leadlag_lineage import (
    LEADLAG_LINEAGE_FIELDS,
    leadlag_lineage_field_matches,
    leadlag_lineage_fields,
    leadlag_lineage_ready,
)
from reports.manifest import write_experiment_manifest
from reports.scaleup_runtime_provenance import (
    BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS,
    BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS,
    BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS,
    BROKER_READINESS_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS,
    empty_scaleup_runtime_provenance,
    load_scaleup_runtime_provenance,
    scaleup_runtime_fields,
    scaleup_runtime_manifest_extra,
    scaleup_runtime_manifest_inputs,
)


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]

SCALEUP_PROVENANCE_COLUMNS = tuple(
    scaleup_runtime_fields(empty_scaleup_runtime_provenance()).keys()
)
RUNTIME_LINEAGE_COLUMNS = (
    "runtime_telemetry_scaleup_provenance_carried",
    "runtime_telemetry_scaleup_provenance_gate_passed",
    "runtime_telemetry_scaleup_manifest_sha256",
    "runtime_telemetry_scaleup_manifest_matches_current",
    "runtime_telemetry_proof_refresh_manifest_sha256",
    "runtime_telemetry_proof_refresh_provenance_gate_passed",
    "runtime_telemetry_proof_refresh_matches_current",
    "runtime_telemetry_strategy_portfolio_manifest_sha256",
    "runtime_telemetry_strategy_portfolio_matches_current",
    "runtime_telemetry_scorecard_manifest_sha256",
    "runtime_telemetry_scorecard_matches_current",
    "runtime_telemetry_research_family_bound",
    "runtime_telemetry_research_family_provenance_current",
    "runtime_telemetry_research_family_id",
    "runtime_telemetry_research_family_registration_id",
    "runtime_telemetry_research_family_manifest_sha256",
    "runtime_telemetry_research_family_matches_current",
    "runtime_telemetry_broker_readiness_manifest_sha256",
    "runtime_telemetry_broker_readiness_lineage_gate_passed",
    "runtime_telemetry_broker_readiness_roundtrip_contract_identity_active",
    "runtime_telemetry_broker_readiness_roundtrip_contract_identity_sha256",
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_lineage_verified"
    ),
    (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_matches_current"
    ),
    "runtime_telemetry_broker_readiness_route_contract_identity_active",
    "runtime_telemetry_broker_readiness_route_contract_identity_sha256",
    (
        "runtime_telemetry_current_broker_readiness_"
        "route_contract_identity_sha256"
    ),
    (
        "runtime_telemetry_broker_readiness_"
        "route_contract_identity_matches_current"
    ),
    (
        "runtime_telemetry_broker_readiness_route_enable_"
        "route_contract_identity_active"
    ),
    (
        "runtime_telemetry_broker_readiness_route_enable_"
        "route_contract_identity_sha256"
    ),
    (
        "runtime_telemetry_current_broker_readiness_route_enable_"
        "route_contract_identity_sha256"
    ),
    (
        "runtime_telemetry_broker_readiness_route_enable_"
        "route_contract_identity_matches_current"
    ),
    "runtime_telemetry_broker_readiness_matches_current",
    "runtime_telemetry_lineage_matches_current",
)


@dataclass(frozen=True)
class RuntimeGuardReport:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def halted(self) -> bool:
        if self.summary.empty:
            return True
        return str(self.summary.iloc[0]["guard_action"]) == "halt"


def evaluate_runtime_guard(
    scaleup_config: dict[str, Any],
    telemetry: pd.DataFrame,
    *,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
) -> RuntimeGuardReport:
    return _evaluate_runtime_guard(
        scaleup_config,
        telemetry,
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
        scaleup_provenance=empty_scaleup_runtime_provenance(),
    )


def _evaluate_runtime_guard(
    scaleup_config: dict[str, Any],
    telemetry: pd.DataFrame,
    *,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
    scaleup_provenance: dict[str, Any],
) -> RuntimeGuardReport:
    if telemetry.empty:
        raise ValueError("runtime telemetry is empty")
    metrics = _metrics(
        scaleup_config,
        telemetry,
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
        scaleup_provenance=scaleup_provenance,
    )
    checks = _checks(metrics.iloc[0], scaleup_config)
    action_queue = _action_queue(metrics.iloc[0], checks)
    summary = _summary_with_actions(_summary(metrics.iloc[0], checks), checks, action_queue)
    guard_config = _config(summary.iloc[0], action_queue)
    return RuntimeGuardReport(metrics=metrics, checks=checks, summary=summary, config=guard_config, action_queue=action_queue)


def write_runtime_guard_report(
    *,
    scaleup_dir: str | Path,
    telemetry_path: str | Path,
    output_dir: str | Path,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
) -> RuntimeGuardReport:
    scaleup_file = _scaleup_config_path(scaleup_dir)
    telemetry_file = _telemetry_path(telemetry_path)
    if not telemetry_file.exists():
        raise FileNotFoundError(f"runtime telemetry file not found: {telemetry_file}")
    scaleup_config = json.loads(scaleup_file.read_text(encoding="utf-8"))
    scaleup_provenance = load_scaleup_runtime_provenance(
        scaleup_file,
        scaleup_config=scaleup_config,
    )
    out = Path(output_dir)
    if out.resolve() == scaleup_file.parent.resolve():
        raise ValueError("runtime guard output must not overwrite the scale-up bundle")
    if out.resolve() == telemetry_file.parent.resolve():
        raise ValueError("runtime guard output must not overwrite runtime telemetry inputs")
    report = _evaluate_runtime_guard(
        scaleup_config,
        pd.read_csv(telemetry_file),
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
        scaleup_provenance=scaleup_provenance,
    )
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "runtime_guard_metrics.csv", index=False)
    report.checks.to_csv(out / "runtime_guard_checks.csv", index=False)
    report.summary.to_csv(out / "runtime_guard_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.metrics.iloc[0], report.checks)
    action_queue.to_csv(out / "runtime_guard_action_queue.csv", index=False)
    guard_config = report.config if report.config is not None else _config(report.summary.iloc[0], action_queue)
    (out / "runtime_guard_config.json").write_text(
        json.dumps(guard_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "runtime_guard_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="runtime_guard",
        parameters={
            "scaleup_ready": bool(scaleup_config.get("ready", False)),
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
        },
        inputs={
            "scaleup": scaleup_file,
            "telemetry": telemetry_file,
            **scaleup_runtime_manifest_inputs(scaleup_provenance),
            **_telemetry_manifest_inputs(telemetry_file),
        },
        extra={
            "guard_action": str(report.summary.iloc[0]["guard_action"]),
            "halted": bool(report.halted),
            **scaleup_runtime_manifest_extra(scaleup_provenance),
            "runtime_telemetry_lineage_matches_current": bool(
                report.summary.iloc[0]["runtime_telemetry_lineage_matches_current"]
            ),
            (
                "runtime_telemetry_broker_readiness_roundtrip_"
                "contract_identity_matches_current"
            ): bool(
                report.summary.iloc[0].get(
                    (
                        "runtime_telemetry_broker_readiness_roundtrip_"
                        "contract_identity_matches_current"
                    ),
                    False,
                )
            ),
            (
                "runtime_telemetry_broker_readiness_"
                "route_contract_identity_matches_current"
            ): bool(
                report.summary.iloc[0].get(
                    (
                        "runtime_telemetry_broker_readiness_"
                        "route_contract_identity_matches_current"
                    ),
                    False,
                )
            ),
            (
                "runtime_telemetry_broker_readiness_route_enable_"
                "route_contract_identity_matches_current"
            ): bool(
                report.summary.iloc[0].get(
                    (
                        "runtime_telemetry_broker_readiness_route_enable_"
                        "route_contract_identity_matches_current"
                    ),
                    False,
                )
            ),
            "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": bool(
                report.summary.iloc[0].get(
                    "strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
                    False,
                )
            ),
            "authorizes_submission": False,
        },
    )
    return RuntimeGuardReport(report.metrics, report.checks, report.summary, out, guard_config, action_queue)


def _metrics(
    scaleup_config: dict[str, Any],
    telemetry: pd.DataFrame,
    *,
    as_of_ts_ns: int | float | None,
    max_telemetry_age_ns: int | float | None,
    scaleup_provenance: dict[str, Any],
) -> pd.DataFrame:
    latest = telemetry.iloc[-1]
    limits = scaleup_config.get("limits", {}) or {}
    kill_switches = scaleup_config.get("kill_switches", {}) or {}
    instrument_metadata = scaleup_config.get("instrument_metadata", {}) or {}
    proof_freshness = scaleup_config.get("proof_freshness", {}) or {}
    if not isinstance(proof_freshness, dict):
        proof_freshness = {}
    broker_readiness = scaleup_config.get("broker_readiness", {}) or {}
    if not isinstance(broker_readiness, dict):
        broker_readiness = {}
    strategy_portfolio = scaleup_config.get("strategy_portfolio", {}) or {}
    if not isinstance(strategy_portfolio, dict):
        strategy_portfolio = {}
    scaleup_strategy_portfolio_profile = str(
        strategy_portfolio.get("selected_profile", "")
    )
    scaleup_strategy_portfolio_profile_key = _identity_key(
        scaleup_strategy_portfolio_profile
    )
    scaleup_strategy_portfolio_leadlag_required = bool(
        _bool_from(strategy_portfolio, "leadlag_edge_lineage_required")
        or scaleup_strategy_portfolio_profile_key == "leadlag"
    )
    scaleup_strategy_portfolio_leadlag_lineage = leadlag_lineage_fields(
        strategy_portfolio,
        target_prefix="scaleup_strategy_portfolio_",
    )
    runtime_strategy_portfolio_profile = str(
        _value(latest, "strategy_portfolio_selected_profile", "")
    )
    runtime_strategy_portfolio_profile_key = _identity_key(
        runtime_strategy_portfolio_profile
    )
    runtime_strategy_portfolio_leadlag_required = _bool_value(
        latest,
        "strategy_portfolio_leadlag_edge_lineage_required",
        fallback=False,
    )
    runtime_strategy_portfolio_leadlag_lineage = leadlag_lineage_fields(
        latest,
        source_prefix="strategy_portfolio_",
        target_prefix="runtime_strategy_portfolio_",
    )
    scaleup_strategy_portfolio_leadlag_ready = leadlag_lineage_ready(
        strategy_portfolio
    )
    runtime_strategy_portfolio_leadlag_ready = leadlag_lineage_ready(
        latest,
        prefix="strategy_portfolio_",
    )
    runtime_strategy_portfolio_leadlag_matches_scaleup = bool(
        not scaleup_strategy_portfolio_leadlag_required
        or (
            runtime_strategy_portfolio_leadlag_required
            and scaleup_strategy_portfolio_profile_key == "leadlag"
            and runtime_strategy_portfolio_profile_key
            == scaleup_strategy_portfolio_profile_key
            and scaleup_strategy_portfolio_leadlag_ready
            and runtime_strategy_portfolio_leadlag_ready
            and all(
                leadlag_lineage_field_matches(
                    field,
                    runtime_strategy_portfolio_leadlag_lineage[
                        f"runtime_strategy_portfolio_{field}"
                    ],
                    scaleup_strategy_portfolio_leadlag_lineage[
                        f"scaleup_strategy_portfolio_{field}"
                    ],
                )
                for field in LEADLAG_LINEAGE_FIELDS
            )
        )
    )
    broker_resume_gate = broker_readiness.get("resume_gate", {}) or {}
    if not isinstance(broker_resume_gate, dict):
        broker_resume_gate = {}
    broker_route_readiness = broker_readiness.get("route_readiness", {}) or {}
    if not isinstance(broker_route_readiness, dict):
        broker_route_readiness = {}
    metadata_min_coverage = _number_from(instrument_metadata, "min_parse_coverage")
    snapshot_ts_ns = _number(latest, "snapshot_ts_ns", fallback=_number(latest, "ts_ns"))
    guard_as_of_ts_ns = _first_number(as_of_ts_ns, _number(latest, "guard_as_of_ts_ns"), np.nan)
    telemetry_age_ns = guard_as_of_ts_ns - snapshot_ts_ns if not np.isnan(guard_as_of_ts_ns) and not np.isnan(snapshot_ts_ns) else np.nan
    max_age_ns = _first_number(max_telemetry_age_ns, _number_from(kill_switches, "max_telemetry_age_ns"), np.nan)
    return pd.DataFrame(
        [
            {
                **scaleup_runtime_fields(scaleup_provenance),
                **_runtime_lineage_fields(latest, scaleup_provenance),
                "scaleup_ready": bool(scaleup_config.get("ready", False)),
                "target_mode": str(scaleup_config.get("target_mode", "")),
                "strategy": _strategy_key(_value(latest, "strategy", "")),
                "expected_strategy": _strategy_key(_scaleup_identity(scaleup_config, "strategy")),
                "market": _identity_key(_value(latest, "market", "")),
                "expected_market": _identity_key(_scaleup_identity(scaleup_config, "market")),
                "scenario_key": str(_value(latest, "scenario_key", scaleup_config.get("scenario_key", ""))),
                "expected_scenario_key": str(scaleup_config.get("scenario_key", "")),
                "adapter": str(_value(latest, "adapter", scaleup_config.get("adapter", ""))),
                "expected_adapter": str(scaleup_config.get("adapter", "")),
                "snapshot_count": int(len(telemetry)),
                "snapshot_ts_ns": snapshot_ts_ns,
                "guard_as_of_ts_ns": guard_as_of_ts_ns,
                "runtime_telemetry_age_ns": telemetry_age_ns,
                "max_telemetry_age_ns": max_age_ns,
                "orders_sent": _number(latest, "orders_sent", fallback=_number(latest, "orders")),
                "lifecycle_orders": _number(latest, "lifecycle_orders"),
                "replace_orders": _number(latest, "replace_orders"),
                "session_notional": _number(latest, "session_notional", fallback=_number(latest, "total_notional")),
                "scaleup_strategy_portfolio_required": _bool_from(strategy_portfolio, "required"),
                "scaleup_strategy_portfolio_provided": _bool_from(strategy_portfolio, "provided"),
                "scaleup_strategy_portfolio_ready": _bool_from(strategy_portfolio, "ready"),
                "scaleup_strategy_portfolio_leadlag_edge_lineage_required": (
                    scaleup_strategy_portfolio_leadlag_required
                ),
                **scaleup_strategy_portfolio_leadlag_lineage,
                "scaleup_strategy_portfolio_deployment_mode": str(strategy_portfolio.get("deployment_mode", "")),
                "scaleup_strategy_portfolio_allocation_mode": str(strategy_portfolio.get("allocation_mode", "")),
                "scaleup_strategy_portfolio_capital_currency": str(strategy_portfolio.get("capital_currency", "")),
                "scaleup_strategy_portfolio_selected_profile": str(strategy_portfolio.get("selected_profile", "")),
                "scaleup_strategy_portfolio_selected_strategy": _strategy_key(
                    strategy_portfolio.get("selected_strategy", "")
                ),
                "scaleup_strategy_portfolio_selected_market": _identity_key(
                    strategy_portfolio.get("selected_market", "")
                ),
                "scaleup_strategy_portfolio_selected_eligible": _bool_from(
                    strategy_portfolio,
                    "selected_eligible",
                ),
                "scaleup_strategy_portfolio_selected_allocation_weight": _number_from(
                    strategy_portfolio,
                    "selected_allocation_weight",
                ),
                "scaleup_strategy_portfolio_selected_allocation_notional": _number_from(
                    strategy_portfolio,
                    "selected_allocation_notional",
                ),
                "scaleup_strategy_portfolio_notional_cap_applied": _bool_from(
                    strategy_portfolio,
                    "notional_cap_applied",
                ),
                "scaleup_strategy_portfolio_min_strategy_count": int(
                    _first_number(_number_from(strategy_portfolio, "min_strategy_count"), 0.0)
                ),
                "scaleup_strategy_portfolio_min_market_count": int(
                    _first_number(_number_from(strategy_portfolio, "min_market_count"), 0.0)
                ),
                "scaleup_strategy_portfolio_max_strategy_weight": _first_number(
                    _number_from(strategy_portfolio, "max_strategy_weight"),
                    0.0,
                ),
                "scaleup_strategy_portfolio_max_market_weight": _first_number(
                    _number_from(strategy_portfolio, "max_market_weight"),
                    0.0,
                ),
                "scaleup_strategy_portfolio_allocated_strategy_count": int(
                    _first_number(_number_from(strategy_portfolio, "allocated_strategy_count"), 0.0)
                ),
                "scaleup_strategy_portfolio_allocated_market_count": int(
                    _first_number(_number_from(strategy_portfolio, "allocated_market_count"), 0.0)
                ),
                "scaleup_strategy_portfolio_top_strategy_by_weight": _strategy_key(
                    strategy_portfolio.get("top_strategy_by_weight", "")
                ),
                "scaleup_strategy_portfolio_top_market_by_weight": _identity_key(
                    strategy_portfolio.get("top_market_by_weight", "")
                ),
                "scaleup_strategy_portfolio_max_strategy_allocation_weight": _first_number(
                    _number_from(strategy_portfolio, "max_strategy_allocation_weight"),
                    0.0,
                ),
                "scaleup_strategy_portfolio_max_market_allocation_weight": _first_number(
                    _number_from(strategy_portfolio, "max_market_allocation_weight"),
                    0.0,
                ),
                "runtime_strategy_portfolio_provided": _bool_value(
                    latest,
                    "strategy_portfolio_provided",
                    fallback=_bool_from(strategy_portfolio, "provided"),
                ),
                "runtime_strategy_portfolio_ready": _bool_value(
                    latest,
                    "strategy_portfolio_ready",
                    fallback=_bool_from(strategy_portfolio, "ready"),
                ),
                "runtime_strategy_portfolio_selected_profile": runtime_strategy_portfolio_profile,
                "runtime_strategy_portfolio_leadlag_edge_lineage_required": (
                    runtime_strategy_portfolio_leadlag_required
                ),
                **runtime_strategy_portfolio_leadlag_lineage,
                "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup": (
                    runtime_strategy_portfolio_leadlag_matches_scaleup
                ),
                "runtime_strategy_portfolio_selected_strategy": _strategy_key(
                    _value(
                        latest,
                        "strategy_portfolio_selected_strategy",
                        strategy_portfolio.get("selected_strategy", ""),
                    )
                ),
                "runtime_strategy_portfolio_selected_market": _identity_key(
                    _value(
                        latest,
                        "strategy_portfolio_selected_market",
                        strategy_portfolio.get("selected_market", ""),
                    )
                ),
                "runtime_strategy_portfolio_selected_eligible": _bool_value(
                    latest,
                    "strategy_portfolio_selected_eligible",
                    fallback=_bool_from(strategy_portfolio, "selected_eligible"),
                ),
                "runtime_strategy_portfolio_selected_allocation_notional": _number(
                    latest,
                    "strategy_portfolio_selected_allocation_notional",
                    fallback=_number_from(strategy_portfolio, "selected_allocation_notional"),
                ),
                "runtime_strategy_portfolio_notional_cap_applied": _bool_value(
                    latest,
                    "strategy_portfolio_notional_cap_applied",
                    fallback=_bool_from(strategy_portfolio, "notional_cap_applied"),
                ),
                "runtime_strategy_portfolio_min_strategy_count": int(
                    _first_number(
                        _number(latest, "strategy_portfolio_min_strategy_count"),
                        _number_from(strategy_portfolio, "min_strategy_count"),
                        0.0,
                    )
                ),
                "runtime_strategy_portfolio_min_market_count": int(
                    _first_number(
                        _number(latest, "strategy_portfolio_min_market_count"),
                        _number_from(strategy_portfolio, "min_market_count"),
                        0.0,
                    )
                ),
                "runtime_strategy_portfolio_max_strategy_weight": _first_number(
                    _number(latest, "strategy_portfolio_max_strategy_weight"),
                    _number_from(strategy_portfolio, "max_strategy_weight"),
                    0.0,
                ),
                "runtime_strategy_portfolio_max_market_weight": _first_number(
                    _number(latest, "strategy_portfolio_max_market_weight"),
                    _number_from(strategy_portfolio, "max_market_weight"),
                    0.0,
                ),
                "runtime_strategy_portfolio_allocated_strategy_count": int(
                    _first_number(
                        _number(latest, "strategy_portfolio_allocated_strategy_count"),
                        _number_from(strategy_portfolio, "allocated_strategy_count"),
                        0.0,
                    )
                ),
                "runtime_strategy_portfolio_allocated_market_count": int(
                    _first_number(
                        _number(latest, "strategy_portfolio_allocated_market_count"),
                        _number_from(strategy_portfolio, "allocated_market_count"),
                        0.0,
                    )
                ),
                "runtime_strategy_portfolio_top_strategy_by_weight": _strategy_key(
                    _value(
                        latest,
                        "strategy_portfolio_top_strategy_by_weight",
                        strategy_portfolio.get("top_strategy_by_weight", ""),
                    )
                ),
                "runtime_strategy_portfolio_top_market_by_weight": _identity_key(
                    _value(
                        latest,
                        "strategy_portfolio_top_market_by_weight",
                        strategy_portfolio.get("top_market_by_weight", ""),
                    )
                ),
                "runtime_strategy_portfolio_max_strategy_allocation_weight": _first_number(
                    _number(latest, "strategy_portfolio_max_strategy_allocation_weight"),
                    _number_from(strategy_portfolio, "max_strategy_allocation_weight"),
                    0.0,
                ),
                "runtime_strategy_portfolio_max_market_allocation_weight": _first_number(
                    _number(latest, "strategy_portfolio_max_market_allocation_weight"),
                    _number_from(strategy_portfolio, "max_market_allocation_weight"),
                    0.0,
                ),
                "realized_pnl": _number(latest, "realized_pnl", fallback=_number(latest, "net_pnl")),
                "open_order_count": _number(latest, "open_order_count"),
                "open_order_qty": _number(latest, "open_order_qty"),
                "open_order_notional": _number(latest, "open_order_notional"),
                "oldest_open_order_age_ns": _number(latest, "oldest_open_order_age_ns"),
                "gross_position_qty": _number(latest, "gross_position_qty"),
                "abs_net_position_qty": _number(latest, "abs_net_position_qty"),
                "gross_position_notional": _number(latest, "gross_position_notional"),
                "net_position_notional": _number(latest, "net_position_notional"),
                "abs_net_position_notional": _number(latest, "abs_net_position_notional"),
                "net_delta": _number(latest, "net_delta"),
                "abs_net_delta": _number(latest, "abs_net_delta"),
                "net_vega": _number(latest, "net_vega"),
                "abs_net_vega": _number(latest, "abs_net_vega"),
                "total_failed_component_checks": _number(latest, "total_failed_component_checks"),
                "unmatched_fills": _number(latest, "unmatched_fills"),
                "mismatched_orders": _number(latest, "mismatched_orders"),
                "overfilled_orders": _number(latest, "overfilled_orders"),
                "worst_adverse_slippage": _number(
                    latest,
                    "worst_adverse_slippage",
                    fallback=_number(latest, "max_adverse_slippage"),
                ),
                "instrument_metadata_required": _bool_from(instrument_metadata, "required"),
                "scaleup_instrument_metadata_provided": _bool_from(instrument_metadata, "provided"),
                "scaleup_instrument_metadata_passed": _bool_from(instrument_metadata, "passed"),
                "scaleup_instrument_parse_coverage": _number_from(instrument_metadata, "parse_coverage"),
                "scaleup_unparsed_instruments": _number_from(instrument_metadata, "unparsed_instruments"),
                "runtime_instrument_metadata_provided": _bool_value(latest, "instrument_metadata_provided", fallback=False),
                "runtime_instrument_metadata_passed": _bool_value(latest, "instrument_metadata_passed", fallback=False),
                "runtime_instrument_parse_coverage": _number(latest, "instrument_parse_coverage"),
                "runtime_unparsed_instruments": _number(latest, "unparsed_instruments"),
                "min_instrument_parse_coverage": _number(
                    latest,
                    "min_instrument_parse_coverage",
                    fallback=metadata_min_coverage,
                ),
                "scaleup_proof_refresh_required": _bool_from(proof_freshness, "required"),
                "scaleup_proof_refresh_provided": _bool_from(proof_freshness, "provided"),
                "scaleup_proof_refresh_ready": _bool_from(proof_freshness, "ready"),
                "scaleup_proof_refresh_strategy": _strategy_key(proof_freshness.get("strategy", "")),
                "scaleup_proof_refresh_market": _identity_key(proof_freshness.get("market", "")),
                "scaleup_proof_refresh_mixed_identity": _bool_from(proof_freshness, "mixed_identity"),
                "runtime_proof_refresh_provided": _bool_value(latest, "proof_refresh_provided", fallback=False),
                "runtime_proof_refresh_ready": _bool_value(latest, "proof_refresh_ready", fallback=False),
                "runtime_proof_refresh_strategy": _strategy_key(_value(latest, "proof_refresh_strategy", "")),
                "runtime_proof_refresh_market": _identity_key(_value(latest, "proof_refresh_market", "")),
                "runtime_proof_refresh_mixed_identity": _bool_value(
                    latest,
                    "proof_refresh_mixed_identity",
                    fallback=False,
                ),
                "scaleup_broker_resume_gate_required": _bool_from(broker_resume_gate, "required"),
                "scaleup_broker_resume_gate_provided": _bool_from(broker_resume_gate, "provided"),
                "scaleup_broker_resume_gate_ready": _bool_from(broker_resume_gate, "ready"),
                "scaleup_broker_resume_strategy": _strategy_key(broker_resume_gate.get("strategy", "")),
                "scaleup_broker_resume_market": _identity_key(broker_resume_gate.get("market", "")),
                "scaleup_broker_resume_proof_refresh_ready": _bool_from(
                    broker_resume_gate,
                    "proof_refresh_ready",
                ),
                "scaleup_broker_resume_proof_refresh_strategy": _strategy_key(
                    broker_resume_gate.get("proof_refresh_strategy", "")
                ),
                "scaleup_broker_resume_proof_refresh_market": _identity_key(
                    broker_resume_gate.get("proof_refresh_market", "")
                ),
                "runtime_broker_resume_gate_provided": _bool_value(
                    latest,
                    "broker_resume_gate_provided",
                    fallback=False,
                ),
                "runtime_broker_resume_gate_ready": _bool_value(latest, "broker_resume_gate_ready", fallback=False),
                "runtime_broker_resume_strategy": _strategy_key(_value(latest, "broker_resume_strategy", "")),
                "runtime_broker_resume_market": _identity_key(_value(latest, "broker_resume_market", "")),
                "runtime_broker_resume_proof_refresh_ready": _bool_value(
                    latest,
                    "broker_resume_proof_refresh_ready",
                    fallback=False,
                ),
                "runtime_broker_resume_proof_refresh_strategy": _strategy_key(
                    _value(latest, "broker_resume_proof_refresh_strategy", "")
                ),
                "runtime_broker_resume_proof_refresh_market": _identity_key(
                    _value(latest, "broker_resume_proof_refresh_market", "")
                ),
                "scaleup_broker_route_readiness_required": _bool_from(
                    broker_route_readiness,
                    "required",
                ),
                "scaleup_broker_route_readiness_provided": _bool_from(
                    broker_route_readiness,
                    "provided",
                ),
                "scaleup_broker_route_readiness_ready": _bool_from(broker_route_readiness, "ready"),
                "scaleup_broker_route_readiness_strategy": _strategy_key(
                    broker_route_readiness.get("strategy", "")
                ),
                "scaleup_broker_route_readiness_market": _identity_key(
                    broker_route_readiness.get("market", "")
                ),
                "scaleup_broker_route_readiness_route_ready_pairs": _number_from(
                    broker_route_readiness,
                    "route_ready_pairs",
                ),
                "scaleup_broker_route_readiness_gap_pairs": _number_from(
                    broker_route_readiness,
                    "gap_pairs",
                ),
                "scaleup_broker_route_readiness_recommendation": str(
                    broker_route_readiness.get("recommendation", "")
                ),
                "scaleup_broker_route_readiness_ops_launch_controls_ready": _bool_from(
                    broker_route_readiness,
                    "ops_launch_controls_ready",
                ),
                "scaleup_broker_route_readiness_ops_launch_control_failures": str(
                    broker_route_readiness.get("ops_launch_control_failures", "")
                ).strip(),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _number_from(
                    broker_route_readiness,
                    "ops_broker_roundtrip_portfolio_safe_runs",
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _number_from(
                    broker_route_readiness,
                    "ops_broker_roundtrip_portfolio_breach_runs",
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    _number_from(
                        broker_route_readiness,
                        "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    )
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    _number_from(
                        broker_route_readiness,
                        "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    )
                ),
                "runtime_broker_route_readiness_provided": _bool_value(
                    latest,
                    "broker_route_readiness_provided",
                    fallback=False,
                ),
                "runtime_broker_route_readiness_ready": _bool_value(
                    latest,
                    "broker_route_readiness_ready",
                    fallback=False,
                ),
                "runtime_broker_route_readiness_strategy": _strategy_key(
                    _value(latest, "broker_route_readiness_strategy", "")
                ),
                "runtime_broker_route_readiness_market": _identity_key(
                    _value(latest, "broker_route_readiness_market", "")
                ),
                "runtime_broker_route_readiness_route_ready_pairs": _number(
                    latest,
                    "broker_route_readiness_route_ready_pairs",
                ),
                "runtime_broker_route_readiness_gap_pairs": _number(
                    latest,
                    "broker_route_readiness_gap_pairs",
                ),
                "runtime_broker_route_readiness_recommendation": str(
                    _value(latest, "broker_route_readiness_recommendation", "")
                ),
                "runtime_broker_route_readiness_ops_launch_controls_ready": _bool_value(
                    latest,
                    "broker_route_readiness_ops_launch_controls_ready",
                    fallback=False,
                ),
                "runtime_broker_route_readiness_ops_launch_control_failures": str(
                    _value(latest, "broker_route_readiness_ops_launch_control_failures", "")
                ).strip(),
                "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _number(
                    latest,
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                ),
                "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _number(
                    latest,
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                ),
                "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": _number(
                    latest,
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                ),
                "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": _number(
                    latest,
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                ),
                "max_orders_per_session": _number_from(limits, "max_orders_per_session"),
                "max_notional_per_session": _number_from(limits, "max_notional_per_session"),
                "stop_loss": _number_from(limits, "stop_loss"),
                "max_total_failed_component_checks": _number_from(kill_switches, "max_total_failed_component_checks"),
                "max_total_unmatched_fills": _number_from(kill_switches, "max_total_unmatched_fills"),
                "max_total_mismatched_orders": _number_from(kill_switches, "max_total_mismatched_orders"),
                "max_total_overfilled_orders": _number_from(kill_switches, "max_total_overfilled_orders"),
                "max_lifecycle_orders": _number_from(kill_switches, "max_lifecycle_orders"),
                "max_replace_orders": _number_from(kill_switches, "max_replace_orders"),
                "max_worst_adverse_slippage": _number_from(kill_switches, "max_worst_adverse_slippage"),
                "max_open_order_count": _number_from(kill_switches, "max_open_order_count"),
                "max_open_order_qty": _number_from(kill_switches, "max_open_order_qty"),
                "max_open_order_notional": _number_from(kill_switches, "max_open_order_notional"),
                "max_open_order_age_ns": _number_from(kill_switches, "max_open_order_age_ns"),
                "max_gross_position_qty": _number_from(kill_switches, "max_gross_position_qty"),
                "max_abs_net_position_qty": _number_from(kill_switches, "max_abs_net_position_qty"),
                "max_gross_notional": _first_number(
                    _number_from(kill_switches, "max_gross_notional"),
                    _number_from(limits, "max_gross_notional"),
                    np.nan,
                ),
                "max_abs_net_delta": _first_number(
                    _number_from(kill_switches, "max_abs_net_delta"),
                    _number_from(limits, "max_abs_net_delta"),
                    np.nan,
                ),
                "max_abs_net_vega": _first_number(
                    _number_from(kill_switches, "max_abs_net_vega"),
                    _number_from(limits, "max_abs_net_vega"),
                    np.nan,
                ),
            }
        ]
    )


def _checks(row: pd.Series, scaleup_config: dict[str, Any]) -> pd.DataFrame:
    checks = [
        _check(
            "scaleup_ready",
            bool(row["scaleup_ready"]),
            "is",
            True,
            bool(row["scaleup_ready"]),
            "scale-up config is not ready",
        ),
        _check(
            "strategy_match",
            row["strategy"],
            "==",
            row["expected_strategy"],
            bool(str(row["expected_strategy"]).strip()) and row["strategy"] == row["expected_strategy"],
            "telemetry strategy does not match scale-up config",
        ),
        _check(
            "market_match",
            row["market"],
            "==",
            row["expected_market"],
            bool(str(row["expected_market"]).strip()) and row["market"] == row["expected_market"],
            "telemetry market does not match scale-up config",
        ),
        _check(
            "scenario_match",
            row["scenario_key"],
            "==",
            row["expected_scenario_key"],
            str(row["scenario_key"]) == str(row["expected_scenario_key"]),
            "telemetry scenario does not match scale-up config",
        ),
        _check(
            "adapter_match",
            row["adapter"],
            "==",
            row["expected_adapter"],
            str(row["adapter"]) == str(row["expected_adapter"]),
            "telemetry adapter does not match scale-up config",
        ),
        _threshold_check("orders_sent", row["orders_sent"], "<=", row["max_orders_per_session"]),
        _threshold_check("session_notional", row["session_notional"], "<=", row["max_notional_per_session"]),
        _threshold_check(
            "total_failed_component_checks",
            row["total_failed_component_checks"],
            "<=",
            row["max_total_failed_component_checks"],
        ),
        _threshold_check("unmatched_fills", row["unmatched_fills"], "<=", row["max_total_unmatched_fills"]),
        _threshold_check("mismatched_orders", row["mismatched_orders"], "<=", row["max_total_mismatched_orders"]),
        _threshold_check("overfilled_orders", row["overfilled_orders"], "<=", row["max_total_overfilled_orders"]),
    ]
    if _to_bool(row.get("scaleup_manifest_required", False)):
        for name, reason in (
            ("scaleup_manifest_provided", "scale-up manifest is missing"),
            ("scaleup_manifest_current", "scale-up artifacts or recursive inputs have drifted"),
            ("scaleup_contract_consistent", "scale-up config, summary, checks, plan, and manifest disagree"),
            ("scaleup_non_authorizing", "scale-up proof contains a submission-authorizing claim"),
            ("scaleup_source_ready", "scale-up plan is not ready"),
            ("scaleup_provenance_gate_passed", "scale-up provenance gate did not pass"),
        ):
            passed = _to_bool(row.get(name, False))
            checks.append(_check(name, passed, "is", True, passed, reason))
        proof_refresh_active = _to_bool(
            row.get("scaleup_proof_refresh_active", False)
        )
        if proof_refresh_active:
            for name, reason in (
                (
                    "scaleup_proof_refresh_verified",
                    "scale-up proof-refresh evidence was not verified",
                ),
                (
                    "scaleup_proof_refresh_manifest_current",
                    "carried proof-refresh manifest is not current",
                ),
                (
                    "scaleup_proof_refresh_semantically_verified",
                    "carried proof-refresh evidence failed semantic verification",
                ),
                (
                    "scaleup_proof_refresh_source_manifest_current",
                    "current proof-refresh source manifest is not current",
                ),
                (
                    "scaleup_proof_refresh_source_semantically_verified",
                    "current proof-refresh source failed semantic verification",
                ),
                (
                    "scaleup_proof_refresh_source_provenance_gate_passed",
                    "current proof-refresh source provenance gate did not pass",
                ),
                (
                    "scaleup_proof_refresh_matches_current",
                    "scale-up proof-refresh lineage differs from its current source",
                ),
                (
                    "runtime_telemetry_proof_refresh_matches_current",
                    "runtime telemetry proof-refresh lineage differs from current scale-up",
                ),
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(
                    _check(name, passed, "is", True, passed, reason)
                )
        broker_readiness_active = bool(
            _to_bool(row.get("scaleup_broker_readiness_required", False))
            or _to_bool(row.get("scaleup_broker_readiness_provided", False))
            or _to_bool(
                row.get("scaleup_broker_readiness_lineage_required", False)
            )
            or _to_bool(
                row.get("scaleup_broker_readiness_lineage_provided", False)
            )
            or _to_bool(
                row.get(
                    (
                        "scaleup_broker_readiness_roundtrip_"
                        "contract_identity_active"
                    ),
                    False,
                )
            )
            or _to_bool(
                row.get(
                    (
                        "runtime_telemetry_broker_readiness_roundtrip_"
                        "contract_identity_active"
                    ),
                    False,
                )
            )
            or _to_bool(
                row.get(
                    (
                        "scaleup_broker_readiness_"
                        "route_contract_identity_active"
                    ),
                    False,
                )
            )
            or _to_bool(
                row.get(
                    (
                        "runtime_telemetry_broker_readiness_"
                        "route_contract_identity_active"
                    ),
                    False,
                )
            )
            or _to_bool(
                row.get(
                    (
                        "scaleup_broker_readiness_route_enable_"
                        "route_contract_identity_active"
                    ),
                    False,
                )
            )
            or _to_bool(
                row.get(
                    (
                        "runtime_telemetry_broker_readiness_route_enable_"
                        "route_contract_identity_active"
                    ),
                    False,
                )
            )
        )
        lineage_required = _to_bool(
            row.get("scaleup_strategy_portfolio_required", False)
        ) or _to_bool(
            row.get("scaleup_strategy_portfolio_provided", False)
        ) or _to_bool(
            row.get("scaleup_research_family_bound", False)
        ) or proof_refresh_active or broker_readiness_active
        lineage_carried = _to_bool(
            row.get("runtime_telemetry_scaleup_provenance_carried", False)
        )
        if lineage_required or lineage_carried:
            for name, reason in (
                (
                    "runtime_telemetry_scaleup_provenance_carried",
                    "runtime telemetry did not carry scale-up provenance",
                ),
                (
                    "runtime_telemetry_scaleup_provenance_gate_passed",
                    "runtime telemetry scale-up provenance gate did not pass",
                ),
                (
                    "runtime_telemetry_scaleup_manifest_matches_current",
                    "runtime telemetry was built from a different scale-up manifest",
                ),
                (
                    "runtime_telemetry_lineage_matches_current",
                    "runtime telemetry proof-refresh, portfolio, scorecard, family, or broker-readiness lineage differs from current scale-up",
                ),
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(_check(name, passed, "is", True, passed, reason))
        if _to_bool(row.get("scaleup_research_family_bound", False)):
            family_matches = _to_bool(
                row.get("runtime_telemetry_research_family_matches_current", False)
            )
            checks.append(
                _check(
                    "runtime_telemetry_research_family_matches_current",
                    family_matches,
                    "is",
                    True,
                    family_matches,
                    "runtime telemetry lost or changed registered research-family closure proof",
                )
            )
        if broker_readiness_active:
            for name, reason in (
                (
                    "scaleup_broker_readiness_manifest_current",
                    "scale-up broker-readiness manifest is not current",
                ),
                (
                    "scaleup_broker_readiness_lineage_contract_consistent",
                    "scale-up broker-readiness lineage contract is inconsistent",
                ),
                (
                    "scaleup_broker_readiness_lineage_gate_passed",
                    "scale-up broker-readiness recursive lineage gate did not pass",
                ),
                (
                    "scaleup_broker_readiness_source_provenance_gate_passed",
                    "current broker-readiness source provenance gate did not pass",
                ),
                (
                    "scaleup_broker_readiness_matches_current",
                    "scale-up broker-readiness lineage differs from its current source",
                ),
                (
                    "runtime_telemetry_broker_readiness_matches_current",
                    "runtime telemetry broker-readiness lineage differs from current scale-up",
                ),
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(_check(name, passed, "is", True, passed, reason))
            contract_identity_active = bool(
                _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_roundtrip_"
                            "contract_identity_active"
                        ),
                        False,
                    )
                )
                or _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_roundtrip_"
                            "contract_identity_active"
                        ),
                        False,
                    )
                )
            )
            if contract_identity_active:
                for suffix, reason in (
                    BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS
                ):
                    name = (
                        "scaleup_broker_readiness_roundtrip_"
                        f"contract_identity_{suffix}"
                    )
                    passed = _to_bool(row.get(name, False))
                    checks.append(
                        _check(name, passed, "is", True, passed, reason)
                    )
                identity_sha = _clean(
                    row.get(
                        (
                            "scaleup_broker_readiness_roundtrip_"
                            "contract_identity_sha256"
                        ),
                        "",
                    )
                )
                scaleup_identity_matches = _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_roundtrip_"
                            "contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                telemetry_identity_matches = _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_roundtrip_"
                            "contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                checks.extend(
                    [
                        _check(
                            (
                                "scaleup_broker_readiness_roundtrip_"
                                "contract_identity_sha256_present"
                            ),
                            identity_sha,
                            "present",
                            True,
                            bool(identity_sha),
                            (
                                "terminal round-trip contract identity "
                                "digest is missing"
                            ),
                        ),
                        _check(
                            (
                                "scaleup_broker_readiness_roundtrip_"
                                "contract_identity_matches_current"
                            ),
                            scaleup_identity_matches,
                            "is",
                            True,
                            scaleup_identity_matches,
                            (
                                "scale-up contract identity differs from "
                                "current broker readiness"
                            ),
                        ),
                        _check(
                            (
                                "runtime_telemetry_broker_readiness_roundtrip_"
                                "contract_identity_matches_current"
                            ),
                            telemetry_identity_matches,
                            "is",
                            True,
                            telemetry_identity_matches,
                            (
                                "runtime telemetry contract identity differs "
                                "from current scale-up"
                            ),
                        ),
                    ]
                )
            route_identity_active = bool(
                _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_"
                            "route_contract_identity_active"
                        ),
                        False,
                    )
                )
                or _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_"
                            "route_contract_identity_active"
                        ),
                        False,
                    )
                )
            )
            if route_identity_active:
                route_identity_sha = _clean(
                    row.get(
                        (
                            "scaleup_broker_readiness_"
                            "route_contract_identity_sha256"
                        ),
                        "",
                    )
                )
                current_route_identity_sha = _clean(
                    row.get(
                        (
                            "scaleup_broker_readiness_current_"
                            "route_contract_identity_sha256"
                        ),
                        "",
                    )
                )
                scaleup_route_identity_matches = _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_"
                            "route_contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                telemetry_route_identity_matches = _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_"
                            "route_contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                checks.extend(
                    [
                        _check(
                            (
                                "scaleup_broker_readiness_"
                                "route_contract_identity_sha256_present"
                            ),
                            route_identity_sha,
                            "present",
                            True,
                            bool(route_identity_sha),
                            (
                                "scale-up broker-readiness route contract "
                                "identity digest is missing"
                            ),
                        ),
                        _check(
                            (
                                "scaleup_broker_readiness_route_contract_"
                                "identity_sha256_matches_current"
                            ),
                            bool(
                                route_identity_sha
                                and current_route_identity_sha
                                and (
                                    route_identity_sha
                                    == current_route_identity_sha
                                )
                            ),
                            "is",
                            True,
                            bool(
                                route_identity_sha
                                and current_route_identity_sha
                                and (
                                    route_identity_sha
                                    == current_route_identity_sha
                                )
                            ),
                            (
                                "scale-up broker-readiness route contract "
                                "identity differs from the current source"
                            ),
                        ),
                        _check(
                            (
                                "scaleup_broker_readiness_"
                                "route_contract_identity_matches_current"
                            ),
                            scaleup_route_identity_matches,
                            "is",
                            True,
                            scaleup_route_identity_matches,
                            (
                                "scale-up broker-readiness route contract "
                                "identity current-source verdict failed"
                            ),
                        ),
                        _check(
                            (
                                "runtime_telemetry_broker_readiness_"
                                "route_contract_identity_matches_current"
                            ),
                            telemetry_route_identity_matches,
                            "is",
                            True,
                            telemetry_route_identity_matches,
                            (
                                "runtime telemetry route contract identity "
                                "differs from the current scale-up"
                            ),
                        ),
                    ]
                )
            route_enable_identity_active = bool(
                _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_route_enable_"
                            "route_contract_identity_active"
                        ),
                        False,
                    )
                )
                or _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_route_enable_"
                            "route_contract_identity_active"
                        ),
                        False,
                    )
                )
            )
            if route_enable_identity_active:
                route_enable_identity_sha = _clean(
                    row.get(
                        (
                            "scaleup_broker_readiness_route_enable_"
                            "route_contract_identity_sha256"
                        ),
                        "",
                    )
                )
                current_route_enable_identity_sha = _clean(
                    row.get(
                        (
                            "scaleup_broker_readiness_current_route_enable_"
                            "route_contract_identity_sha256"
                        ),
                        "",
                    )
                )
                scaleup_route_enable_identity_matches = _to_bool(
                    row.get(
                        (
                            "scaleup_broker_readiness_route_enable_"
                            "route_contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                telemetry_route_enable_identity_matches = _to_bool(
                    row.get(
                        (
                            "runtime_telemetry_broker_readiness_route_enable_"
                            "route_contract_identity_matches_current"
                        ),
                        False,
                    )
                )
                checks.extend(
                    [
                        _check(
                            (
                                "scaleup_broker_readiness_route_enable_"
                                "route_contract_identity_sha256_present"
                            ),
                            route_enable_identity_sha,
                            "present",
                            True,
                            bool(route_enable_identity_sha),
                            (
                                "scale-up broker-readiness route-enable "
                                "route contract identity digest is missing"
                            ),
                        ),
                        _check(
                            (
                                "scaleup_broker_readiness_route_enable_"
                                "route_contract_identity_sha256_matches_current"
                            ),
                            bool(
                                route_enable_identity_sha
                                and current_route_enable_identity_sha
                                and (
                                    route_enable_identity_sha
                                    == current_route_enable_identity_sha
                                )
                            ),
                            "is",
                            True,
                            bool(
                                route_enable_identity_sha
                                and current_route_enable_identity_sha
                                and (
                                    route_enable_identity_sha
                                    == current_route_enable_identity_sha
                                )
                            ),
                            (
                                "scale-up broker-readiness route-enable "
                                "route contract identity differs from the "
                                "current source"
                            ),
                        ),
                        _check(
                            (
                                "scaleup_broker_readiness_route_enable_"
                                "route_contract_identity_matches_current"
                            ),
                            scaleup_route_enable_identity_matches,
                            "is",
                            True,
                            scaleup_route_enable_identity_matches,
                            (
                                "scale-up broker-readiness route-enable "
                                "route contract identity current-source "
                                "verdict failed"
                            ),
                        ),
                        _check(
                            (
                                "runtime_telemetry_broker_readiness_"
                                "route_enable_route_contract_identity_"
                                "matches_current"
                            ),
                            telemetry_route_enable_identity_matches,
                            "is",
                            True,
                            telemetry_route_enable_identity_matches,
                            (
                                "runtime telemetry route-enable route "
                                "contract identity differs from the current "
                                "scale-up"
                            ),
                        ),
                    ]
                )
    scaleup_portfolio_active = bool(row["scaleup_strategy_portfolio_required"]) or bool(
        row["scaleup_strategy_portfolio_provided"]
    )
    runtime_portfolio_active = bool(row["runtime_strategy_portfolio_provided"])
    if bool(row["scaleup_strategy_portfolio_required"]):
        checks.append(
            _check(
                "scaleup_strategy_portfolio_provided",
                bool(row["scaleup_strategy_portfolio_provided"]),
                "is",
                True,
                bool(row["scaleup_strategy_portfolio_provided"]),
                "scale-up config requires strategy portfolio allocation but does not record supplied evidence",
            )
        )
    if scaleup_portfolio_active or runtime_portfolio_active:
        checks.extend(
            [
                _check(
                    "scaleup_strategy_portfolio_ready",
                    bool(row["scaleup_strategy_portfolio_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_strategy_portfolio_ready"]),
                    "scale-up strategy portfolio allocation is not ready",
                ),
                _check(
                    "scaleup_strategy_portfolio_allocation_eligible",
                    bool(row["scaleup_strategy_portfolio_selected_eligible"]),
                    "is",
                    True,
                    bool(row["scaleup_strategy_portfolio_selected_eligible"]),
                    "scale-up strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "scaleup_strategy_portfolio_strategy_matches",
                    row["scaleup_strategy_portfolio_selected_strategy"],
                    "==",
                    row["expected_strategy"],
                    bool(
                        row["scaleup_strategy_portfolio_selected_strategy"]
                        and row["expected_strategy"]
                        and row["scaleup_strategy_portfolio_selected_strategy"] == row["expected_strategy"]
                    ),
                    "scale-up strategy portfolio strategy does not match scale-up identity",
                ),
                _check(
                    "scaleup_strategy_portfolio_market_matches",
                    row["scaleup_strategy_portfolio_selected_market"],
                    "==",
                    row["expected_market"],
                    bool(
                        row["scaleup_strategy_portfolio_selected_market"]
                        and row["expected_market"]
                        and row["scaleup_strategy_portfolio_selected_market"] == row["expected_market"]
                    ),
                    "scale-up strategy portfolio market does not match scale-up identity",
                ),
                _check(
                    "scaleup_strategy_portfolio_allocation_notional",
                    row["scaleup_strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    not pd.isna(row["scaleup_strategy_portfolio_selected_allocation_notional"])
                    and float(row["scaleup_strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "scale-up strategy portfolio allocation notional must be positive",
                ),
                _check(
                    "runtime_strategy_portfolio_ready",
                    bool(row["runtime_strategy_portfolio_ready"]),
                    "is",
                    True,
                    bool(row["runtime_strategy_portfolio_ready"]),
                    "runtime telemetry strategy portfolio allocation is not ready",
                ),
                _check(
                    "runtime_strategy_portfolio_allocation_eligible",
                    bool(row["runtime_strategy_portfolio_selected_eligible"]),
                    "is",
                    True,
                    bool(row["runtime_strategy_portfolio_selected_eligible"]),
                    "runtime telemetry strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "runtime_strategy_portfolio_strategy_matches",
                    row["runtime_strategy_portfolio_selected_strategy"],
                    "==",
                    row["expected_strategy"],
                    bool(
                        row["runtime_strategy_portfolio_selected_strategy"]
                        and row["expected_strategy"]
                        and row["runtime_strategy_portfolio_selected_strategy"] == row["expected_strategy"]
                    ),
                    "runtime telemetry strategy portfolio strategy does not match scale-up identity",
                ),
                _check(
                    "runtime_strategy_portfolio_market_matches",
                    row["runtime_strategy_portfolio_selected_market"],
                    "==",
                    row["expected_market"],
                    bool(
                        row["runtime_strategy_portfolio_selected_market"]
                        and row["expected_market"]
                        and row["runtime_strategy_portfolio_selected_market"] == row["expected_market"]
                    ),
                    "runtime telemetry strategy portfolio market does not match scale-up identity",
                ),
                _check(
                    "runtime_strategy_portfolio_allocation_notional",
                    row["runtime_strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    not pd.isna(row["runtime_strategy_portfolio_selected_allocation_notional"])
                    and float(row["runtime_strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "runtime telemetry strategy portfolio allocation notional must be positive",
                ),
                _threshold_check(
                    "strategy_portfolio_session_notional",
                    row["session_notional"],
                    "<=",
                    row["scaleup_strategy_portfolio_selected_allocation_notional"],
                ),
            ]
        )
        if bool(
            row["scaleup_strategy_portfolio_leadlag_edge_lineage_required"]
        ):
            scaleup_lineage_ready = leadlag_lineage_ready(
                row,
                prefix="scaleup_strategy_portfolio_",
            )
            runtime_lineage_required = bool(
                row["runtime_strategy_portfolio_leadlag_edge_lineage_required"]
            )
            runtime_lineage_ready = leadlag_lineage_ready(
                row,
                prefix="runtime_strategy_portfolio_",
            )
            profile_matches = bool(
                row["runtime_strategy_portfolio_selected_profile"]
                and _identity_key(
                    row["runtime_strategy_portfolio_selected_profile"]
                )
                == _identity_key(
                    row["scaleup_strategy_portfolio_selected_profile"]
                )
            )
            checks.extend(
                [
                    _check(
                        "scaleup_strategy_portfolio_leadlag_edge_lineage_ready",
                        scaleup_lineage_ready,
                        "is",
                        True,
                        scaleup_lineage_ready,
                        "scale-up lead-lag allocation is missing its complete measured-edge lineage",
                    ),
                    _check(
                        "runtime_strategy_portfolio_leadlag_edge_lineage_required",
                        runtime_lineage_required,
                        "is",
                        True,
                        runtime_lineage_required,
                        "runtime telemetry did not carry the required lead-lag lineage marker",
                    ),
                    _check(
                        "runtime_strategy_portfolio_selected_profile_matches_scaleup",
                        row["runtime_strategy_portfolio_selected_profile"],
                        "==",
                        row["scaleup_strategy_portfolio_selected_profile"],
                        profile_matches,
                        "runtime telemetry lead-lag profile differs from current scale-up",
                    ),
                    _check(
                        "runtime_strategy_portfolio_leadlag_edge_lineage_ready",
                        runtime_lineage_ready,
                        "is",
                        True,
                        runtime_lineage_ready,
                        "runtime telemetry lost or malformed the lead-lag measured-edge lineage",
                    ),
                ]
            )
            for field in LEADLAG_LINEAGE_FIELDS:
                actual = row[f"runtime_strategy_portfolio_{field}"]
                expected = row[f"scaleup_strategy_portfolio_{field}"]
                field_matches = leadlag_lineage_field_matches(
                    field,
                    actual,
                    expected,
                )
                checks.append(
                    _check(
                        f"runtime_strategy_portfolio_{field}_matches_scaleup",
                        actual,
                        "==",
                        expected,
                        field_matches,
                        f"runtime telemetry {field} differs from current scale-up",
                    )
                )
    for value_column, threshold_column in (
        ("lifecycle_orders", "max_lifecycle_orders"),
        ("replace_orders", "max_replace_orders"),
    ):
        if not pd.isna(row[threshold_column]):
            checks.append(_threshold_check(value_column, row[value_column], "<=", row[threshold_column]))
    if not pd.isna(row["stop_loss"]):
        checks.append(_threshold_check("realized_pnl", row["realized_pnl"], ">=", -abs(float(row["stop_loss"]))))
    if not pd.isna(row["max_worst_adverse_slippage"]):
        checks.append(
            _threshold_check(
                "worst_adverse_slippage",
                row["worst_adverse_slippage"],
                "<=",
                row["max_worst_adverse_slippage"],
            )
        )
    for value_column, threshold_column in (
        ("open_order_count", "max_open_order_count"),
        ("open_order_qty", "max_open_order_qty"),
        ("open_order_notional", "max_open_order_notional"),
        ("oldest_open_order_age_ns", "max_open_order_age_ns"),
        ("gross_position_qty", "max_gross_position_qty"),
        ("abs_net_position_qty", "max_abs_net_position_qty"),
        ("gross_position_notional", "max_gross_notional"),
        ("abs_net_delta", "max_abs_net_delta"),
        ("abs_net_vega", "max_abs_net_vega"),
    ):
        if not pd.isna(row[threshold_column]):
            checks.append(_threshold_check(value_column, row[value_column], "<=", row[threshold_column]))
    if not pd.isna(row["max_telemetry_age_ns"]):
        checks.extend(
            [
                _threshold_check(
                    "runtime_telemetry_age_nonnegative",
                    row["runtime_telemetry_age_ns"],
                    ">=",
                    0,
                ),
                _threshold_check(
                    "runtime_telemetry_age_ns",
                    row["runtime_telemetry_age_ns"],
                    "<=",
                    row["max_telemetry_age_ns"],
                ),
            ]
        )
    metadata_required = bool(row["instrument_metadata_required"])
    metadata_provided = bool(row["runtime_instrument_metadata_provided"])
    if metadata_required:
        checks.extend(
            [
                _check(
                    "scaleup_instrument_metadata_provided",
                    bool(row["scaleup_instrument_metadata_provided"]),
                    "is",
                    True,
                    bool(row["scaleup_instrument_metadata_provided"]),
                    "scale-up config requires instrument metadata but does not record supplied evidence",
                ),
                _check(
                    "scaleup_instrument_metadata_passed",
                    bool(row["scaleup_instrument_metadata_passed"]),
                    "is",
                    True,
                    bool(row["scaleup_instrument_metadata_passed"]),
                    "scale-up config requires instrument metadata but the gate did not pass",
                ),
                _check(
                    "runtime_instrument_metadata_provided",
                    metadata_provided,
                    "is",
                    True,
                    metadata_provided,
                    "runtime telemetry is missing required instrument metadata evidence",
                ),
            ]
        )
    if metadata_required or metadata_provided:
        checks.extend(
            [
                _check(
                    "runtime_instrument_metadata_passed",
                    bool(row["runtime_instrument_metadata_passed"]),
                    "is",
                    True,
                    bool(row["runtime_instrument_metadata_passed"]),
                    "runtime instrument metadata did not pass",
                ),
                _threshold_check(
                    "runtime_instrument_parse_coverage",
                    row["runtime_instrument_parse_coverage"],
                    ">=",
                    row["min_instrument_parse_coverage"],
                ),
                _threshold_check(
                    "runtime_unparsed_instruments",
                    row["runtime_unparsed_instruments"],
                    "<=",
                    0,
                ),
            ]
        )
    scaleup_proof_active = bool(row["scaleup_proof_refresh_required"]) or bool(row["scaleup_proof_refresh_provided"])
    runtime_proof_active = bool(row["runtime_proof_refresh_provided"])
    if scaleup_proof_active:
        checks.extend(
            [
                _check(
                    "scaleup_proof_refresh_provided",
                    bool(row["scaleup_proof_refresh_provided"]),
                    "is",
                    True,
                    bool(row["scaleup_proof_refresh_provided"]),
                    "scale-up config requires proof refresh but does not record supplied evidence",
                ),
                _check(
                    "scaleup_proof_refresh_ready",
                    bool(row["scaleup_proof_refresh_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_proof_refresh_ready"]),
                    "scale-up config proof refresh evidence is not ready",
                ),
                _check(
                    "scaleup_proof_refresh_identity_consistent",
                    bool(row["scaleup_proof_refresh_mixed_identity"]),
                    "is",
                    False,
                    not bool(row["scaleup_proof_refresh_mixed_identity"]),
                    "scale-up config proof refresh evidence reports mixed identity",
                ),
                _check(
                    "runtime_proof_refresh_provided",
                    bool(row["runtime_proof_refresh_provided"]),
                    "is",
                    True,
                    bool(row["runtime_proof_refresh_provided"]),
                    "runtime telemetry is missing required proof refresh evidence",
                ),
            ]
        )
    if scaleup_proof_active or runtime_proof_active:
        expected_proof_strategy = row["scaleup_proof_refresh_strategy"] or row["expected_strategy"]
        expected_proof_market = row["scaleup_proof_refresh_market"] or row["expected_market"]
        checks.extend(
            [
                _check(
                    "runtime_proof_refresh_ready",
                    bool(row["runtime_proof_refresh_ready"]),
                    "is",
                    True,
                    bool(row["runtime_proof_refresh_ready"]),
                    "runtime proof refresh evidence is not ready",
                ),
                _check(
                    "runtime_proof_refresh_identity_consistent",
                    bool(row["runtime_proof_refresh_mixed_identity"]),
                    "is",
                    False,
                    not bool(row["runtime_proof_refresh_mixed_identity"]),
                    "runtime proof refresh evidence reports mixed identity",
                ),
                _check(
                    "runtime_proof_refresh_strategy_matches",
                    row["runtime_proof_refresh_strategy"],
                    "==",
                    expected_proof_strategy,
                    bool(
                        row["runtime_proof_refresh_strategy"]
                        and expected_proof_strategy
                        and row["runtime_proof_refresh_strategy"] == expected_proof_strategy
                    ),
                    "runtime proof refresh strategy does not match scale-up proof identity",
                ),
                _check(
                    "runtime_proof_refresh_market_matches",
                    row["runtime_proof_refresh_market"],
                    "==",
                    expected_proof_market,
                    bool(
                        row["runtime_proof_refresh_market"]
                        and expected_proof_market
                        and row["runtime_proof_refresh_market"] == expected_proof_market
                    ),
                    "runtime proof refresh market does not match scale-up proof identity",
                ),
            ]
        )
    scaleup_broker_resume_active = bool(row["scaleup_broker_resume_gate_required"]) or bool(
        row["scaleup_broker_resume_gate_provided"]
    )
    runtime_broker_resume_active = bool(row["runtime_broker_resume_gate_provided"])
    if scaleup_broker_resume_active:
        checks.extend(
            [
                _check(
                    "scaleup_broker_resume_gate_provided",
                    bool(row["scaleup_broker_resume_gate_provided"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_resume_gate_provided"]),
                    "scale-up config requires broker resume gate but does not record supplied evidence",
                ),
                _check(
                    "scaleup_broker_resume_gate_ready",
                    bool(row["scaleup_broker_resume_gate_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_resume_gate_ready"]),
                    "scale-up config broker resume gate is not ready",
                ),
                _check(
                    "scaleup_broker_resume_proof_refresh_ready",
                    bool(row["scaleup_broker_resume_proof_refresh_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_resume_proof_refresh_ready"]),
                    "scale-up config broker resume proof freshness is not ready",
                ),
                _check(
                    "runtime_broker_resume_gate_provided",
                    bool(row["runtime_broker_resume_gate_provided"]),
                    "is",
                    True,
                    bool(row["runtime_broker_resume_gate_provided"]),
                    "runtime telemetry is missing required broker resume-gate evidence",
                ),
            ]
        )
    if scaleup_broker_resume_active or runtime_broker_resume_active:
        expected_resume_strategy = row["scaleup_broker_resume_strategy"] or row["expected_strategy"]
        expected_resume_market = row["scaleup_broker_resume_market"] or row["expected_market"]
        expected_resume_proof_strategy = row["scaleup_broker_resume_proof_refresh_strategy"] or expected_resume_strategy
        expected_resume_proof_market = row["scaleup_broker_resume_proof_refresh_market"] or expected_resume_market
        checks.extend(
            [
                _check(
                    "runtime_broker_resume_gate_ready",
                    bool(row["runtime_broker_resume_gate_ready"]),
                    "is",
                    True,
                    bool(row["runtime_broker_resume_gate_ready"]),
                    "runtime broker resume gate is not ready",
                ),
                _check(
                    "runtime_broker_resume_strategy_matches",
                    row["runtime_broker_resume_strategy"],
                    "==",
                    expected_resume_strategy,
                    bool(
                        row["runtime_broker_resume_strategy"]
                        and expected_resume_strategy
                        and row["runtime_broker_resume_strategy"] == expected_resume_strategy
                    ),
                    "runtime broker resume strategy does not match scale-up broker resume identity",
                ),
                _check(
                    "runtime_broker_resume_market_matches",
                    row["runtime_broker_resume_market"],
                    "==",
                    expected_resume_market,
                    bool(
                        row["runtime_broker_resume_market"]
                        and expected_resume_market
                        and row["runtime_broker_resume_market"] == expected_resume_market
                    ),
                    "runtime broker resume market does not match scale-up broker resume identity",
                ),
                _check(
                    "runtime_broker_resume_proof_refresh_ready",
                    bool(row["runtime_broker_resume_proof_refresh_ready"]),
                    "is",
                    True,
                    bool(row["runtime_broker_resume_proof_refresh_ready"]),
                    "runtime broker resume proof freshness is not ready",
                ),
                _check(
                    "runtime_broker_resume_proof_refresh_strategy_matches",
                    row["runtime_broker_resume_proof_refresh_strategy"],
                    "==",
                    expected_resume_proof_strategy,
                    bool(
                        row["runtime_broker_resume_proof_refresh_strategy"]
                        and expected_resume_proof_strategy
                        and row["runtime_broker_resume_proof_refresh_strategy"] == expected_resume_proof_strategy
                    ),
                    "runtime broker resume proof strategy does not match scale-up broker resume proof identity",
                ),
                _check(
                    "runtime_broker_resume_proof_refresh_market_matches",
                    row["runtime_broker_resume_proof_refresh_market"],
                    "==",
                    expected_resume_proof_market,
                    bool(
                        row["runtime_broker_resume_proof_refresh_market"]
                        and expected_resume_proof_market
                        and row["runtime_broker_resume_proof_refresh_market"] == expected_resume_proof_market
                    ),
                    "runtime broker resume proof market does not match scale-up broker resume proof identity",
                ),
            ]
        )
    scaleup_broker_route_active = bool(row["scaleup_broker_route_readiness_required"]) or bool(
        row["scaleup_broker_route_readiness_provided"]
    )
    runtime_broker_route_active = bool(row["runtime_broker_route_readiness_provided"])
    if scaleup_broker_route_active:
        checks.extend(
            [
                _check(
                    "scaleup_broker_route_readiness_provided",
                    bool(row["scaleup_broker_route_readiness_provided"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_route_readiness_provided"]),
                    "scale-up config requires broker route readiness but does not record supplied evidence",
                ),
                _check(
                    "scaleup_broker_route_readiness_ready",
                    bool(row["scaleup_broker_route_readiness_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_route_readiness_ready"]),
                    "scale-up config broker route readiness is not ready",
                ),
                _check(
                    "scaleup_broker_route_readiness_route_ready_pairs",
                    row["scaleup_broker_route_readiness_route_ready_pairs"],
                    ">",
                    0.0,
                    not pd.isna(row["scaleup_broker_route_readiness_route_ready_pairs"])
                    and float(row["scaleup_broker_route_readiness_route_ready_pairs"]) > 0.0,
                    "scale-up config broker route readiness has no ready route pairs",
                ),
                _threshold_check(
                    "scaleup_broker_route_readiness_gap_pairs",
                    row["scaleup_broker_route_readiness_gap_pairs"],
                    "<=",
                    0,
                ),
                _check(
                    "scaleup_broker_route_readiness_ops_launch_controls_ready",
                    bool(row["scaleup_broker_route_readiness_ops_launch_controls_ready"]),
                    "is",
                    True,
                    bool(row["scaleup_broker_route_readiness_ops_launch_controls_ready"]),
                    "scale-up config broker route ops launch controls are not ready",
                ),
                _check(
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"],
                    ">",
                    0.0,
                    not pd.isna(row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"])
                    and float(row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0.0,
                    "scale-up config broker route readiness has no safe broker round-trip portfolio run",
                ),
                _threshold_check(
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"],
                    "<=",
                    0,
                ),
                _check(
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
                    ">",
                    0.0,
                    not pd.isna(
                        row[
                            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                        ]
                    )
                    and float(
                        row[
                            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                        ]
                    )
                    > 0.0,
                    "scale-up config broker route readiness has no concentration-safe broker round-trip portfolio run",
                ),
                _threshold_check(
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    row["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
                    "<=",
                    0,
                ),
                _check(
                    "runtime_broker_route_readiness_provided",
                    bool(row["runtime_broker_route_readiness_provided"]),
                    "is",
                    True,
                    bool(row["runtime_broker_route_readiness_provided"]),
                    "runtime telemetry is missing required broker route-readiness evidence",
                ),
            ]
        )
    if scaleup_broker_route_active or runtime_broker_route_active:
        expected_route_strategy = row["scaleup_broker_route_readiness_strategy"] or row["expected_strategy"]
        expected_route_market = row["scaleup_broker_route_readiness_market"] or row["expected_market"]
        checks.extend(
            [
                _check(
                    "runtime_broker_route_readiness_ready",
                    bool(row["runtime_broker_route_readiness_ready"]),
                    "is",
                    True,
                    bool(row["runtime_broker_route_readiness_ready"]),
                    "runtime broker route readiness is not ready",
                ),
                _check(
                    "runtime_broker_route_readiness_strategy_matches",
                    row["runtime_broker_route_readiness_strategy"],
                    "==",
                    expected_route_strategy,
                    bool(
                        row["runtime_broker_route_readiness_strategy"]
                        and expected_route_strategy
                        and row["runtime_broker_route_readiness_strategy"] == expected_route_strategy
                    ),
                    "runtime broker route readiness strategy does not match scale-up broker route identity",
                ),
                _check(
                    "runtime_broker_route_readiness_market_matches",
                    row["runtime_broker_route_readiness_market"],
                    "==",
                    expected_route_market,
                    bool(
                        row["runtime_broker_route_readiness_market"]
                        and expected_route_market
                        and row["runtime_broker_route_readiness_market"] == expected_route_market
                    ),
                    "runtime broker route readiness market does not match scale-up broker route identity",
                ),
                _check(
                    "runtime_broker_route_readiness_route_ready_pairs",
                    row["runtime_broker_route_readiness_route_ready_pairs"],
                    ">",
                    0.0,
                    not pd.isna(row["runtime_broker_route_readiness_route_ready_pairs"])
                    and float(row["runtime_broker_route_readiness_route_ready_pairs"]) > 0.0,
                    "runtime broker route readiness has no ready route pairs",
                ),
                _threshold_check(
                    "runtime_broker_route_readiness_gap_pairs",
                    row["runtime_broker_route_readiness_gap_pairs"],
                    "<=",
                    0,
                ),
                _check(
                    "runtime_broker_route_readiness_ops_launch_controls_ready",
                    bool(row["runtime_broker_route_readiness_ops_launch_controls_ready"]),
                    "is",
                    True,
                    bool(row["runtime_broker_route_readiness_ops_launch_controls_ready"]),
                    "runtime broker route ops launch controls are not ready",
                ),
                _check(
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"],
                    ">",
                    0.0,
                    not pd.isna(row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"])
                    and float(row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0.0,
                    "runtime broker route readiness has no safe broker round-trip portfolio run",
                ),
                _threshold_check(
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"],
                    "<=",
                    0,
                ),
                _check(
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
                    ">",
                    0.0,
                    not pd.isna(
                        row[
                            "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                        ]
                    )
                    and float(
                        row[
                            "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                        ]
                    )
                    > 0.0,
                    "runtime broker route readiness has no concentration-safe broker round-trip portfolio run",
                ),
                _threshold_check(
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    row["runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
                    "<=",
                    0,
                ),
            ]
        )
    manual_halt = _manual_halt(scaleup_config)
    if manual_halt:
        checks.append(_check("manual_halt", True, "is", False, False, "scale-up config contains a manual halt"))
    return pd.DataFrame(checks)


def _summary(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    halted = bool((~checks["passed"].astype(bool)).any()) if not checks.empty else True
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    failed_names = _failed_check_names(checks)
    failed_reasons = _failed_check_reasons(checks)
    primary_blocker = _first_failed_check(_failed_check_rows(checks))
    return pd.DataFrame(
        [
            {
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "authorizes_submission": False,
                **{
                    column: row[column]
                    for column in (*SCALEUP_PROVENANCE_COLUMNS, *RUNTIME_LINEAGE_COLUMNS)
                },
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": ";".join(failed_names),
                "first_failed_reason": failed_reasons[0] if failed_reasons else "",
                "failed_check_reasons": ";".join(failed_reasons),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "target_mode": row["target_mode"],
                "strategy": row["strategy"],
                "market": row["market"],
                "scenario_key": row["scenario_key"],
                "adapter": row["adapter"],
                "proof_refresh_required": bool(row["scaleup_proof_refresh_required"]),
                "proof_refresh_provided": bool(row["runtime_proof_refresh_provided"]),
                "proof_refresh_ready": bool(row["runtime_proof_refresh_ready"]),
                "proof_refresh_strategy": row["runtime_proof_refresh_strategy"],
                "proof_refresh_market": row["runtime_proof_refresh_market"],
                "proof_refresh_mixed_identity": bool(row["runtime_proof_refresh_mixed_identity"]),
                "broker_resume_gate_required": bool(row["scaleup_broker_resume_gate_required"]),
                "broker_resume_gate_provided": bool(row["runtime_broker_resume_gate_provided"]),
                "broker_resume_gate_ready": bool(row["runtime_broker_resume_gate_ready"]),
                "broker_resume_strategy": row["runtime_broker_resume_strategy"],
                "broker_resume_market": row["runtime_broker_resume_market"],
                "broker_resume_proof_refresh_ready": bool(row["runtime_broker_resume_proof_refresh_ready"]),
                "broker_resume_proof_refresh_strategy": row["runtime_broker_resume_proof_refresh_strategy"],
                "broker_resume_proof_refresh_market": row["runtime_broker_resume_proof_refresh_market"],
                "broker_route_readiness_required": bool(row["scaleup_broker_route_readiness_required"]),
                "broker_route_readiness_provided": bool(row["runtime_broker_route_readiness_provided"]),
                "broker_route_readiness_ready": bool(row["runtime_broker_route_readiness_ready"]),
                "broker_route_readiness_strategy": row["runtime_broker_route_readiness_strategy"],
                "broker_route_readiness_market": row["runtime_broker_route_readiness_market"],
                "broker_route_readiness_route_ready_pairs": row[
                    "runtime_broker_route_readiness_route_ready_pairs"
                ],
                "broker_route_readiness_gap_pairs": row["runtime_broker_route_readiness_gap_pairs"],
                "broker_route_readiness_recommendation": row["runtime_broker_route_readiness_recommendation"],
                "broker_route_readiness_ops_launch_controls_ready": bool(
                    row["runtime_broker_route_readiness_ops_launch_controls_ready"]
                ),
                "broker_route_readiness_ops_launch_control_failures": row[
                    "runtime_broker_route_readiness_ops_launch_control_failures"
                ],
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": row[
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"
                ],
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": row[
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"
                ],
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": row[
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                ],
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": row[
                    "runtime_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
                ],
                "orders_sent": row["orders_sent"],
                "lifecycle_orders": row["lifecycle_orders"],
                "replace_orders": row["replace_orders"],
                "open_order_notional": row["open_order_notional"],
                "oldest_open_order_age_ns": row["oldest_open_order_age_ns"],
                "gross_position_notional": row["gross_position_notional"],
                "abs_net_delta": row["abs_net_delta"],
                "abs_net_vega": row["abs_net_vega"],
                "session_notional": row["session_notional"],
                "strategy_portfolio_required": bool(row["scaleup_strategy_portfolio_required"]),
                "strategy_portfolio_provided": bool(row["runtime_strategy_portfolio_provided"]),
                "strategy_portfolio_ready": bool(row["runtime_strategy_portfolio_ready"]),
                "strategy_portfolio_selected_profile": row[
                    "runtime_strategy_portfolio_selected_profile"
                ],
                "strategy_portfolio_leadlag_edge_lineage_required": bool(
                    row[
                        "scaleup_strategy_portfolio_leadlag_edge_lineage_required"
                    ]
                ),
                "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": bool(
                    row[
                        "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                    ]
                ),
                **{
                    f"strategy_portfolio_{field}": row[
                        f"runtime_strategy_portfolio_{field}"
                    ]
                    for field in LEADLAG_LINEAGE_FIELDS
                },
                "strategy_portfolio_selected_strategy": row["runtime_strategy_portfolio_selected_strategy"],
                "strategy_portfolio_selected_market": row["runtime_strategy_portfolio_selected_market"],
                "strategy_portfolio_selected_eligible": bool(
                    row["runtime_strategy_portfolio_selected_eligible"]
                ),
                "strategy_portfolio_selected_allocation_notional": row[
                    "runtime_strategy_portfolio_selected_allocation_notional"
                ],
                "strategy_portfolio_notional_cap_applied": bool(
                    row["runtime_strategy_portfolio_notional_cap_applied"]
                ),
                "strategy_portfolio_min_strategy_count": int(
                    row["runtime_strategy_portfolio_min_strategy_count"]
                ),
                "strategy_portfolio_min_market_count": int(row["runtime_strategy_portfolio_min_market_count"]),
                "strategy_portfolio_max_strategy_weight": row["runtime_strategy_portfolio_max_strategy_weight"],
                "strategy_portfolio_max_market_weight": row["runtime_strategy_portfolio_max_market_weight"],
                "strategy_portfolio_allocated_strategy_count": int(
                    row["runtime_strategy_portfolio_allocated_strategy_count"]
                ),
                "strategy_portfolio_allocated_market_count": int(
                    row["runtime_strategy_portfolio_allocated_market_count"]
                ),
                "strategy_portfolio_top_strategy_by_weight": row[
                    "runtime_strategy_portfolio_top_strategy_by_weight"
                ],
                "strategy_portfolio_top_market_by_weight": row[
                    "runtime_strategy_portfolio_top_market_by_weight"
                ],
                "strategy_portfolio_max_strategy_allocation_weight": row[
                    "runtime_strategy_portfolio_max_strategy_allocation_weight"
                ],
                "strategy_portfolio_max_market_allocation_weight": row[
                    "runtime_strategy_portfolio_max_market_allocation_weight"
                ],
                "realized_pnl": row["realized_pnl"],
                "recommendation": "stop_routing_and_investigate" if halted else "continue_with_controls",
            }
        ]
    )


def _summary_with_actions(
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    out = summary.copy()
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    out["failed_check_count"] = int(len(failed_rows))
    out["failed_check_names"] = ";".join(_failed_check_names(checks))
    out["first_failed_reason"] = _prefixed_check_reason(primary_blocker)
    out["primary_blocker_check"] = _check_name(primary_blocker)
    out["primary_blocker_value"] = _check_value(primary_blocker, "value")
    out["primary_blocker_operator"] = _check_value(primary_blocker, "operator")
    out["primary_blocker_threshold"] = _check_value(primary_blocker, "threshold")
    out["primary_blocker_reason"] = _check_reason(primary_blocker)
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, check in _failed_check_rows(checks).iterrows():
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "ready",
                "source": "runtime_guard_checks",
                "component": _component(check),
                "check": _check_name(check),
                "actual": check.get("value"),
                "operator": _check_value(check, "operator"),
                "expected": check.get("threshold"),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "reason": _check_reason(check),
                "recommendation": _action_recommendation(check, row),
            }
        )
    ordered_rows = []
    for priority, action in enumerate(rows, start=1):
        item = {column: action.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _component(row: pd.Series) -> str:
    check = _check_name(row)
    if check.startswith("scaleup_manifest") or check.startswith("scaleup_contract") or check.startswith(
        "scaleup_non_authorizing"
    ) or check.startswith("scaleup_provenance") or check.startswith("scaleup_source") or check.startswith(
        "runtime_telemetry_scaleup"
    ) or check.startswith("runtime_telemetry_lineage"):
        return "scaleup_provenance"
    if check.startswith("runtime_telemetry_research_family"):
        return "research_family_provenance"
    if check in {"scaleup_ready", "manual_halt"}:
        return "scaleup_plan"
    if check in {"strategy_matches", "market_matches"}:
        return "runtime_identity"
    if check in {"runtime_telemetry_age_ns", "snapshot_ts_ns"}:
        return "runtime_telemetry"
    if check.startswith("runtime_proof_refresh"):
        return "proof_refresh"
    if check.startswith("runtime_broker_resume"):
        return "broker_resume_gate"
    if check.startswith("runtime_broker_route") or check.startswith("scaleup_broker_route"):
        return "broker_route_readiness"
    if check.startswith("runtime_strategy_portfolio") or check.startswith("scaleup_strategy_portfolio"):
        return "strategy_portfolio"
    if check in {
        "open_order_count",
        "open_order_qty",
        "open_order_notional",
        "oldest_open_order_age_ns",
    }:
        return "open_order_risk"
    if check in {
        "gross_position_qty",
        "abs_net_position_qty",
        "gross_position_notional",
        "net_position_notional",
        "abs_net_position_notional",
        "abs_net_delta",
        "abs_net_vega",
    }:
        return "position_risk"
    if check in {"orders_sent", "lifecycle_orders", "replace_orders", "session_notional", "realized_pnl"}:
        return "runtime_limits"
    return "runtime_guard"


def _next_gate(row: pd.Series) -> str:
    check = _check_name(row)
    if check.startswith("scaleup_manifest") or check.startswith("scaleup_contract") or check.startswith(
        "scaleup_non_authorizing"
    ) or check.startswith("scaleup_provenance") or check.startswith("scaleup_source") or check.startswith(
        "runtime_telemetry_scaleup"
    ) or check.startswith("runtime_telemetry_lineage"):
        return "plan-scaleup"
    if check == "scaleup_ready":
        return "plan-scaleup"
    if check.startswith("runtime_proof_refresh"):
        return "refresh-proof"
    if check.startswith("runtime_broker_resume"):
        return "review-resume-gate"
    if check.startswith("runtime_broker_route") or check.startswith("scaleup_broker_route"):
        return "review-route-readiness"
    return "plan-halt-response"


def _action_recommendation(row: pd.Series, metrics_row: pd.Series) -> str:
    check = _check_name(row)
    if check.startswith("scaleup_manifest") or check.startswith("scaleup_contract") or check.startswith(
        "scaleup_non_authorizing"
    ) or check.startswith("scaleup_provenance") or check.startswith("scaleup_source") or check.startswith(
        "runtime_telemetry_scaleup"
    ) or check.startswith("runtime_telemetry_lineage"):
        return "rebuild_current_non_authorizing_scaleup_provenance_before_routing"
    if check.startswith("runtime_telemetry_research_family"):
        return "rebuild_runtime_telemetry_from_current_registered_family_scaleup"
    if check == "scaleup_ready":
        return "repair_scaleup_plan_before_runtime_routing"
    if check == "manual_halt":
        return "clear_manual_halt_or_prepare_halt_response"
    if check.startswith("runtime_proof_refresh"):
        return "refresh_or_repair_runtime_proof_before_routing"
    if check.startswith("runtime_broker_resume"):
        return "repair_broker_resume_gate_before_routing"
    if check.startswith("runtime_broker_route") or check.startswith("scaleup_broker_route"):
        return "repair_broker_route_readiness_before_routing"
    if check.startswith("runtime_strategy_portfolio") or check.startswith("scaleup_strategy_portfolio"):
        return "repair_strategy_portfolio_allocation_before_routing"
    if _clean(metrics_row.get("target_mode")) in {"live", "paper", "shadow"}:
        return "stop_routing_and_prepare_halt_response"
    return "investigate_runtime_guard_halt"


def _config(summary_row: pd.Series, action_queue: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "guard_action": _clean(summary_row.get("guard_action")),
        "halted": _to_bool(summary_row.get("halted")),
        "strategy": _clean(summary_row.get("strategy")),
        "market": _clean(summary_row.get("market")),
        "scenario_key": _clean(summary_row.get("scenario_key")),
        "adapter": _clean(summary_row.get("adapter")),
        "failed_check_count": _int_value(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _clean(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _clean(summary_row.get("primary_blocker_check")),
            "value": _clean(summary_row.get("primary_blocker_value")),
            "operator": _clean(summary_row.get("primary_blocker_operator")),
            "threshold": _clean(summary_row.get("primary_blocker_threshold")),
            "reason": _clean(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int_value(summary_row.get("action_queue_count")),
        "ready_action_count": _int_value(summary_row.get("ready_action_count")),
        "blocked_action_count": _int_value(summary_row.get("blocked_action_count")),
        "review_action_count": _int_value(summary_row.get("review_action_count")),
        "next_gate": _clean(summary_row.get("next_gate")),
        "next_gate_help_command": _clean(summary_row.get("next_gate_help_command")),
        "primary_action_status": _clean(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "scaleup_provenance": {
            column: _jsonable_value(summary_row.get(column))
            for column in SCALEUP_PROVENANCE_COLUMNS
        },
        "runtime_telemetry_lineage": {
            column: _jsonable_value(summary_row.get(column))
            for column in RUNTIME_LINEAGE_COLUMNS
        },
        "broker_route_readiness": {
            "required": _to_bool(summary_row.get("broker_route_readiness_required")),
            "provided": _to_bool(summary_row.get("broker_route_readiness_provided")),
            "ready": _to_bool(summary_row.get("broker_route_readiness_ready")),
            "strategy": _clean(summary_row.get("broker_route_readiness_strategy")),
            "market": _clean(summary_row.get("broker_route_readiness_market")),
            "route_ready_pairs": _int_value(summary_row.get("broker_route_readiness_route_ready_pairs")),
            "gap_pairs": _int_value(summary_row.get("broker_route_readiness_gap_pairs")),
            "recommendation": _clean(summary_row.get("broker_route_readiness_recommendation")),
            "ops_launch_controls_ready": _to_bool(
                summary_row.get("broker_route_readiness_ops_launch_controls_ready")
            ),
            "ops_launch_control_failures": _clean(
                summary_row.get("broker_route_readiness_ops_launch_control_failures")
            ),
            "ops_broker_roundtrip_portfolio_safe_runs": _int_value(
                summary_row.get("broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs")
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": _int_value(
                summary_row.get("broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs")
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": _int_value(
                summary_row.get(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                )
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": _int_value(
                summary_row.get(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
                )
            ),
        },
        "strategy_portfolio": {
            "required": _to_bool(summary_row.get("strategy_portfolio_required")),
            "provided": _to_bool(summary_row.get("strategy_portfolio_provided")),
            "ready": _to_bool(summary_row.get("strategy_portfolio_ready")),
            "selected_profile": _clean(
                summary_row.get("strategy_portfolio_selected_profile")
            ),
            "leadlag_edge_lineage_required": _to_bool(
                summary_row.get(
                    "strategy_portfolio_leadlag_edge_lineage_required"
                )
            ),
            "leadlag_edge_lineage_matches_scaleup": _to_bool(
                summary_row.get(
                    "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                )
            ),
            **{
                field: _jsonable_value(
                    summary_row.get(f"strategy_portfolio_{field}")
                )
                for field in LEADLAG_LINEAGE_FIELDS
            },
            "selected_strategy": _clean(summary_row.get("strategy_portfolio_selected_strategy")),
            "selected_market": _clean(summary_row.get("strategy_portfolio_selected_market")),
            "selected_eligible": _to_bool(summary_row.get("strategy_portfolio_selected_eligible")),
            "selected_allocation_notional": _first_number(
                summary_row.get("strategy_portfolio_selected_allocation_notional"),
                0.0,
            ),
            "notional_cap_applied": _to_bool(summary_row.get("strategy_portfolio_notional_cap_applied")),
            "min_strategy_count": _int_value(summary_row.get("strategy_portfolio_min_strategy_count")),
            "min_market_count": _int_value(summary_row.get("strategy_portfolio_min_market_count")),
            "max_strategy_weight": _first_number(summary_row.get("strategy_portfolio_max_strategy_weight"), 0.0),
            "max_market_weight": _first_number(summary_row.get("strategy_portfolio_max_market_weight"), 0.0),
            "allocated_strategy_count": _int_value(
                summary_row.get("strategy_portfolio_allocated_strategy_count")
            ),
            "allocated_market_count": _int_value(summary_row.get("strategy_portfolio_allocated_market_count")),
            "top_strategy_by_weight": _clean(summary_row.get("strategy_portfolio_top_strategy_by_weight")),
            "top_market_by_weight": _clean(summary_row.get("strategy_portfolio_top_market_by_weight")),
            "max_strategy_allocation_weight": _first_number(
                summary_row.get("strategy_portfolio_max_strategy_allocation_weight"),
                0.0,
            ),
            "max_market_allocation_weight": _first_number(
                summary_row.get("strategy_portfolio_max_market_allocation_weight"),
                0.0,
            ),
        },
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    halted_label = "yes" if _to_bool(summary.get("halted")) else "no"
    lines = [
        "# Runtime Guard Runbook",
        "",
        f"- Halted: {halted_label}",
        f"- Guard action: {_clean(summary.get('guard_action'))}",
        f"- Strategy: {_clean(summary.get('strategy'))}",
        f"- Market: {_clean(summary.get('market'))}",
        f"- Scenario: {_clean(summary.get('scenario_key'))}",
        f"- Adapter: {_clean(summary.get('adapter'))}",
        f"- Failed checks: {_int_value(summary.get('failed_check_count'))}",
        f"- Ready actions: {_int_value(summary.get('ready_action_count'))}",
        f"- Blocked actions: {_int_value(summary.get('blocked_action_count'))}",
        f"- Recommendation: {_clean(summary.get('recommendation'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No runtime-guard actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _clean(item.get("priority")),
                    _clean(item.get("queue_status")),
                    _clean(item.get("component")),
                    _clean(item.get("check")),
                    _clean(item.get("actual")),
                    _clean(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _clean(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _scaleup_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "scaleup_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"scale-up config not found: {candidate}")
    return candidate


def _runtime_lineage_fields(
    latest: pd.Series,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    current_scaleup_sha = _clean(provenance.get("manifest_sha256"))
    telemetry_scaleup_sha = _clean(_value(latest, "scaleup_manifest_sha256", ""))
    carried = bool(
        "scaleup_manifest_required" in latest.index
        and _bool_value(latest, "scaleup_manifest_required")
        and telemetry_scaleup_sha
    )
    scaleup_matches = bool(
        carried
        and current_scaleup_sha
        and telemetry_scaleup_sha == current_scaleup_sha
    )

    proof_refresh_active = _to_bool(
        provenance.get("proof_refresh_active", False)
    )
    current_proof_refresh_source_sha = _clean(
        provenance.get("proof_refresh_source_manifest_sha256")
    )
    current_proof_refresh_source_gate = _to_bool(
        provenance.get(
            "proof_refresh_source_provenance_gate_passed",
            False,
        )
    )
    current_proof_refresh_source_match = _to_bool(
        provenance.get("proof_refresh_matches_current", False)
    )
    telemetry_proof_refresh_sha = _clean(
        _value(
            latest,
            "scaleup_proof_refresh_manifest_sha256",
            "",
        )
    )
    telemetry_proof_refresh_gate = _bool_value(
        latest,
        "scaleup_proof_refresh_source_provenance_gate_passed",
        fallback=False,
    )
    telemetry_proof_refresh_source_match = _bool_value(
        latest,
        "scaleup_proof_refresh_matches_current",
        fallback=False,
    )
    proof_refresh_matches = bool(
        not proof_refresh_active
        or (
            current_proof_refresh_source_sha
            and telemetry_proof_refresh_sha
            == current_proof_refresh_source_sha
            and current_proof_refresh_source_gate
            and current_proof_refresh_source_match
            and telemetry_proof_refresh_gate
            and telemetry_proof_refresh_source_match
        )
    )
    current_portfolio_sha = _clean(
        provenance.get("strategy_portfolio_manifest_sha256")
    )
    telemetry_portfolio_sha = _clean(
        _value(latest, "scaleup_strategy_portfolio_manifest_sha256", "")
    )
    portfolio_matches = bool(
        not current_portfolio_sha
        or telemetry_portfolio_sha == current_portfolio_sha
    )
    current_scorecard_sha = _clean(provenance.get("scorecard_manifest_sha256"))
    telemetry_scorecard_sha = _clean(
        _value(latest, "scaleup_scorecard_manifest_sha256", "")
    )
    scorecard_matches = bool(
        not current_scorecard_sha
        or telemetry_scorecard_sha == current_scorecard_sha
    )

    family_bound = _to_bool(provenance.get("research_family_bound", False))
    telemetry_family_bound = _bool_value(
        latest,
        "scaleup_research_family_bound",
        fallback=False,
    )
    telemetry_family_current = _bool_value(
        latest,
        "scaleup_research_family_provenance_current",
        fallback=False,
    )
    telemetry_family_id = _clean(
        _value(latest, "scaleup_research_family_id", "")
    )
    telemetry_registration_id = _clean(
        _value(latest, "scaleup_research_family_registration_id", "")
    )
    telemetry_family_sha = _clean(
        _value(latest, "scaleup_research_family_manifest_sha256", "")
    )
    family_matches = bool(
        not family_bound
        or (
            telemetry_family_bound
            and telemetry_family_current
            and telemetry_family_id == _clean(provenance.get("research_family_id"))
            and telemetry_registration_id
            == _clean(provenance.get("research_family_registration_id"))
            and telemetry_family_sha
            == _clean(provenance.get("research_family_manifest_sha256"))
        )
    )
    broker_readiness_active = bool(
        _to_bool(provenance.get("broker_readiness_required", False))
        or _to_bool(provenance.get("broker_readiness_provided", False))
        or _to_bool(provenance.get("broker_readiness_lineage_required", False))
        or _to_bool(provenance.get("broker_readiness_lineage_provided", False))
    )
    current_broker_readiness_sha = _clean(
        provenance.get("broker_readiness_manifest_sha256")
    )
    telemetry_broker_readiness_sha = _clean(
        _value(latest, "scaleup_broker_readiness_manifest_sha256", "")
    )
    telemetry_broker_readiness_gate = _bool_value(
        latest,
        "scaleup_broker_readiness_lineage_gate_passed",
        fallback=False,
    )
    telemetry_broker_readiness_source_match = _bool_value(
        latest,
        "scaleup_broker_readiness_matches_current",
        fallback=False,
    )
    current_contract_identity_active = _to_bool(
        provenance.get(
            "broker_readiness_roundtrip_contract_identity_active",
            False,
        )
    )
    telemetry_contract_identity_active = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_roundtrip_"
            "contract_identity_active"
        ),
        fallback=False,
    )
    broker_readiness_active = bool(
        broker_readiness_active or telemetry_contract_identity_active
    )
    current_contract_identity_sha = _clean(
        provenance.get(
            "broker_readiness_roundtrip_contract_identity_sha256",
            "",
        )
    )
    telemetry_contract_identity_sha = _clean(
        _value(
            latest,
            (
                "scaleup_broker_readiness_roundtrip_"
                "contract_identity_sha256"
            ),
            "",
        )
    )
    current_contract_identity_verified = _to_bool(
        provenance.get(
            (
                "broker_readiness_roundtrip_"
                "contract_identity_lineage_verified"
            ),
            False,
        )
    )
    telemetry_contract_identity_verified = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_roundtrip_"
            "contract_identity_lineage_verified"
        ),
        fallback=False,
    )
    current_contract_identity_source_match = _to_bool(
        provenance.get(
            "broker_readiness_contract_identity_matches_current",
            False,
        )
    )
    telemetry_contract_identity_source_match = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_roundtrip_"
            "contract_identity_matches_current"
        ),
        fallback=False,
    )
    contract_identity_fields_match = all(
        _broker_contract_identity_value_matches(
            _value(latest, f"scaleup_{report_field}", None),
            provenance.get(report_field),
            report_field,
        )
        for _config_field, report_field in (
            BROKER_READINESS_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
    )
    contract_identity_matches = bool(
        contract_identity_fields_match
        and (
            (
                not current_contract_identity_active
                and not telemetry_contract_identity_active
            )
            or (
                current_contract_identity_active
                and telemetry_contract_identity_active
                and current_contract_identity_sha
                and telemetry_contract_identity_sha
                == current_contract_identity_sha
                and current_contract_identity_verified
                and telemetry_contract_identity_verified
                and current_contract_identity_source_match
                and telemetry_contract_identity_source_match
            )
        )
    )
    current_route_identity_active = _to_bool(
        provenance.get(
            "broker_readiness_route_contract_identity_active",
            False,
        )
    )
    telemetry_route_identity_active = _bool_value(
        latest,
        "scaleup_broker_readiness_route_contract_identity_active",
        fallback=False,
    )
    broker_readiness_active = bool(
        broker_readiness_active
        or current_route_identity_active
        or telemetry_route_identity_active
    )
    current_route_identity_sha = _clean(
        provenance.get(
            "broker_readiness_route_contract_identity_sha256",
            "",
        )
    )
    telemetry_route_identity_sha = _clean(
        _value(
            latest,
            "scaleup_broker_readiness_route_contract_identity_sha256",
            "",
        )
    )
    current_route_identity_source_sha = _clean(
        provenance.get(
            "broker_readiness_current_route_contract_identity_sha256",
            "",
        )
    )
    telemetry_route_identity_source_sha = _clean(
        _value(
            latest,
            (
                "scaleup_broker_readiness_current_"
                "route_contract_identity_sha256"
            ),
            "",
        )
    )
    current_route_identity_source_match = _to_bool(
        provenance.get(
            "broker_readiness_route_contract_identity_matches_current",
            False,
        )
    )
    telemetry_route_identity_source_match = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_"
            "route_contract_identity_matches_current"
        ),
        fallback=False,
    )
    route_identity_fields_match = all(
        _broker_contract_identity_value_matches(
            _value(latest, f"scaleup_{report_field}", None),
            provenance.get(report_field),
            report_field,
        )
        for _config_field, report_field in (
            BROKER_READINESS_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
    )
    route_identity_matches = bool(
        route_identity_fields_match
        and (
            (
                not current_route_identity_active
                and not telemetry_route_identity_active
            )
            or (
                current_route_identity_active
                and telemetry_route_identity_active
                and current_route_identity_sha
                and telemetry_route_identity_sha == current_route_identity_sha
                and current_route_identity_source_sha
                and (
                    telemetry_route_identity_source_sha
                    == current_route_identity_source_sha
                )
                and (
                    current_route_identity_sha
                    == current_route_identity_source_sha
                )
                and current_route_identity_source_match
                and telemetry_route_identity_source_match
            )
        )
    )
    current_route_enable_identity_active = _to_bool(
        provenance.get(
            (
                "broker_readiness_route_enable_"
                "route_contract_identity_active"
            ),
            False,
        )
    )
    telemetry_route_enable_identity_active = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_route_enable_"
            "route_contract_identity_active"
        ),
        fallback=False,
    )
    broker_readiness_active = bool(
        broker_readiness_active
        or current_route_enable_identity_active
        or telemetry_route_enable_identity_active
    )
    current_route_enable_identity_sha = _clean(
        provenance.get(
            (
                "broker_readiness_route_enable_"
                "route_contract_identity_sha256"
            ),
            "",
        )
    )
    telemetry_route_enable_identity_sha = _clean(
        _value(
            latest,
            (
                "scaleup_broker_readiness_route_enable_"
                "route_contract_identity_sha256"
            ),
            "",
        )
    )
    current_route_enable_identity_source_sha = _clean(
        provenance.get(
            (
                "broker_readiness_current_route_enable_"
                "route_contract_identity_sha256"
            ),
            "",
        )
    )
    telemetry_route_enable_identity_source_sha = _clean(
        _value(
            latest,
            (
                "scaleup_broker_readiness_current_route_enable_"
                "route_contract_identity_sha256"
            ),
            "",
        )
    )
    current_route_enable_identity_source_match = _to_bool(
        provenance.get(
            (
                "broker_readiness_route_enable_"
                "route_contract_identity_matches_current"
            ),
            False,
        )
    )
    telemetry_route_enable_identity_source_match = _bool_value(
        latest,
        (
            "scaleup_broker_readiness_route_enable_"
            "route_contract_identity_matches_current"
        ),
        fallback=False,
    )
    route_enable_identity_fields_match = all(
        _broker_contract_identity_value_matches(
            _value(latest, f"scaleup_{report_field}", None),
            provenance.get(report_field),
            report_field,
        )
        for _config_field, report_field in (
            BROKER_READINESS_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_LINEAGE_FIELDS
        )
    )
    route_enable_identity_matches = bool(
        route_enable_identity_fields_match
        and (
            (
                not current_route_enable_identity_active
                and not telemetry_route_enable_identity_active
            )
            or (
                current_route_enable_identity_active
                and telemetry_route_enable_identity_active
                and current_route_enable_identity_sha
                and (
                    telemetry_route_enable_identity_sha
                    == current_route_enable_identity_sha
                )
                and current_route_enable_identity_source_sha
                and (
                    telemetry_route_enable_identity_source_sha
                    == current_route_enable_identity_source_sha
                )
                and (
                    current_route_enable_identity_sha
                    == current_route_enable_identity_source_sha
                )
                and current_route_enable_identity_source_match
                and telemetry_route_enable_identity_source_match
            )
        )
    )
    broker_readiness_matches = bool(
        not broker_readiness_active
        or (
            current_broker_readiness_sha
            and telemetry_broker_readiness_sha
            == current_broker_readiness_sha
            and telemetry_broker_readiness_gate
            and telemetry_broker_readiness_source_match
            and contract_identity_matches
            and route_identity_matches
            and route_enable_identity_matches
        )
    )
    telemetry_gate = _bool_value(
        latest,
        "scaleup_provenance_gate_passed",
        fallback=False,
    )
    lineage_matches = bool(
        scaleup_matches
        and proof_refresh_matches
        and portfolio_matches
        and scorecard_matches
        and family_matches
        and contract_identity_matches
        and route_identity_matches
        and route_enable_identity_matches
        and broker_readiness_matches
    )
    return {
        "runtime_telemetry_scaleup_provenance_carried": carried,
        "runtime_telemetry_scaleup_provenance_gate_passed": telemetry_gate,
        "runtime_telemetry_scaleup_manifest_sha256": telemetry_scaleup_sha,
        "runtime_telemetry_scaleup_manifest_matches_current": scaleup_matches,
        "runtime_telemetry_proof_refresh_manifest_sha256": (
            telemetry_proof_refresh_sha
        ),
        "runtime_telemetry_proof_refresh_provenance_gate_passed": (
            telemetry_proof_refresh_gate
        ),
        "runtime_telemetry_proof_refresh_matches_current": (
            proof_refresh_matches
        ),
        "runtime_telemetry_strategy_portfolio_manifest_sha256": telemetry_portfolio_sha,
        "runtime_telemetry_strategy_portfolio_matches_current": portfolio_matches,
        "runtime_telemetry_scorecard_manifest_sha256": telemetry_scorecard_sha,
        "runtime_telemetry_scorecard_matches_current": scorecard_matches,
        "runtime_telemetry_research_family_bound": telemetry_family_bound,
        "runtime_telemetry_research_family_provenance_current": telemetry_family_current,
        "runtime_telemetry_research_family_id": telemetry_family_id,
        "runtime_telemetry_research_family_registration_id": telemetry_registration_id,
        "runtime_telemetry_research_family_manifest_sha256": telemetry_family_sha,
        "runtime_telemetry_research_family_matches_current": family_matches,
        "runtime_telemetry_broker_readiness_manifest_sha256": (
            telemetry_broker_readiness_sha
        ),
        "runtime_telemetry_broker_readiness_lineage_gate_passed": (
            telemetry_broker_readiness_gate
        ),
        (
            "runtime_telemetry_broker_readiness_roundtrip_"
            "contract_identity_active"
        ): telemetry_contract_identity_active,
        (
            "runtime_telemetry_broker_readiness_roundtrip_"
            "contract_identity_sha256"
        ): telemetry_contract_identity_sha,
        (
            "runtime_telemetry_broker_readiness_roundtrip_"
            "contract_identity_lineage_verified"
        ): telemetry_contract_identity_verified,
        (
            "runtime_telemetry_broker_readiness_roundtrip_"
            "contract_identity_matches_current"
        ): contract_identity_matches,
        (
            "runtime_telemetry_broker_readiness_"
            "route_contract_identity_active"
        ): telemetry_route_identity_active,
        (
            "runtime_telemetry_broker_readiness_"
            "route_contract_identity_sha256"
        ): telemetry_route_identity_sha,
        (
            "runtime_telemetry_current_broker_readiness_"
            "route_contract_identity_sha256"
        ): telemetry_route_identity_source_sha,
        (
            "runtime_telemetry_broker_readiness_"
            "route_contract_identity_matches_current"
        ): route_identity_matches,
        (
            "runtime_telemetry_broker_readiness_route_enable_"
            "route_contract_identity_active"
        ): telemetry_route_enable_identity_active,
        (
            "runtime_telemetry_broker_readiness_route_enable_"
            "route_contract_identity_sha256"
        ): telemetry_route_enable_identity_sha,
        (
            "runtime_telemetry_current_broker_readiness_route_enable_"
            "route_contract_identity_sha256"
        ): telemetry_route_enable_identity_source_sha,
        (
            "runtime_telemetry_broker_readiness_route_enable_"
            "route_contract_identity_matches_current"
        ): route_enable_identity_matches,
        "runtime_telemetry_broker_readiness_matches_current": (
            broker_readiness_matches
        ),
        "runtime_telemetry_lineage_matches_current": lineage_matches,
    }


def _telemetry_manifest_inputs(telemetry_file: Path) -> dict[str, Any]:
    root = telemetry_file.parent
    manifest_path = root / "manifest.json"
    if telemetry_file.name != "runtime_telemetry.csv" or not manifest_path.is_file():
        return {}
    artifacts = [
        root / name
        for name in (
            "runtime_telemetry.csv",
            "runtime_telemetry_sources.csv",
            "runtime_telemetry_checks.csv",
            "runtime_telemetry_summary.csv",
        )
        if (root / name).is_file()
    ]
    inputs: dict[str, Any] = {"runtime_telemetry_manifest": manifest_path}
    if artifacts:
        inputs["runtime_telemetry_artifacts"] = artifacts
    return inputs


def _telemetry_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "runtime_telemetry.csv"
    return candidate


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float) or np.isnan(threshold_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} or threshold is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    return checks.loc[~checks["passed"].map(_to_bool)].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(checks: pd.DataFrame) -> list[str]:
    if checks.empty or "passed" not in checks.columns or "check" not in checks.columns:
        return []
    failed = _failed_check_rows(checks)["check"]
    return [str(value) for value in failed.tolist()]


def _failed_check_reasons(checks: pd.DataFrame) -> list[str]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = _failed_check_rows(checks)
    if failed.empty:
        return []
    names = failed["check"].astype(str) if "check" in failed.columns else pd.Series(["check"] * len(failed))
    reasons = failed["reason"].astype(str) if "reason" in failed.columns else pd.Series([""] * len(failed))
    out: list[str] = []
    for name, reason in zip(names.tolist(), reasons.tolist(), strict=False):
        clean_reason = reason.strip()
        out.append(f"{name}: {clean_reason}" if clean_reason else str(name))
    return out


def _check_name(row: pd.Series) -> str:
    if row.empty:
        return ""
    return _check_value(row, "check")


def _check_reason(row: pd.Series) -> str:
    if row.empty:
        return ""
    return _check_value(row, "reason")


def _prefixed_check_reason(row: pd.Series) -> str:
    if row.empty:
        return ""
    name = _check_name(row)
    reason = _check_reason(row)
    return f"{name}: {reason}" if name and reason else name or reason


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row.get(column))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _clean(action_queue.iloc[0].get(column))


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
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _split_items(value: object) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _clean(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _clean(value)
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _broker_contract_identity_value_matches(
    left: object,
    right: object,
    report_field: str,
) -> bool:
    if report_field.endswith("_orders"):
        return _int_value(left) == _int_value(right)
    if report_field.endswith(("_sha256", "_error")):
        return _clean(left) == _clean(right)
    return _to_bool(left) == _to_bool(right)


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


def _manual_halt(scaleup_config: dict[str, Any]) -> bool:
    value = scaleup_config.get("manual_halt", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _scaleup_identity(scaleup_config: dict[str, Any], key: str) -> object:
    identity = scaleup_config.get("identity", {}) or {}
    if not isinstance(identity, dict):
        identity = {}
    return _first_value(scaleup_config.get(key, ""), identity.get(key, ""))


def _strategy_key(value: object) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _first_value(*values: object) -> object:
    for value in values:
        try:
            missing = bool(pd.isna(value))
        except (TypeError, ValueError):
            missing = False
        if not missing and str(value).strip():
            return value
    return ""


def _value(row: pd.Series, column: str, fallback: object = "") -> object:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return value


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _number_from(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key, np.nan)
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return np.nan
    return float(parsed)


def _first_number(*values: object) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(number):
            return number
    return np.nan


def _bool_from(mapping: dict[str, Any], key: str) -> bool:
    return _to_bool(mapping.get(key, False))


def _bool_value(row: pd.Series, column: str, fallback: bool = False) -> bool:
    return _to_bool(row.get(column, fallback))


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)
