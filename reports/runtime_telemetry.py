from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.leadlag_lineage import (
    LEADLAG_LINEAGE_FIELDS,
    leadlag_lineage_fields,
    leadlag_lineage_ready,
)
from reports.manifest import write_experiment_manifest
from reports.scaleup_runtime_provenance import (
    BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS,
    empty_scaleup_runtime_provenance,
    load_scaleup_runtime_provenance,
    scaleup_runtime_fields,
    scaleup_runtime_manifest_extra,
    scaleup_runtime_manifest_inputs,
)


GUARD_COLUMNS = [
    "scenario_key",
    "adapter",
    "orders_sent",
    "lifecycle_orders",
    "replace_orders",
    "session_notional",
    "realized_pnl",
    "total_failed_component_checks",
    "open_order_notional",
    "gross_position_notional",
    "abs_net_delta",
    "abs_net_vega",
    "unmatched_fills",
    "mismatched_orders",
    "overfilled_orders",
    "worst_adverse_slippage",
]

SCALEUP_PROVENANCE_COLUMNS = list(
    scaleup_runtime_fields(empty_scaleup_runtime_provenance()).keys()
)


@dataclass(frozen=True)
class RuntimeTelemetryReport:
    telemetry: pd.DataFrame
    sources: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_runtime_telemetry(
    scaleup_config: dict[str, Any],
    *,
    export_summary: pd.DataFrame | None = None,
    upload_summary: pd.DataFrame | None = None,
    reconciliation_summary: pd.DataFrame | None = None,
    reconciliation_checks: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    pnl_snapshot: pd.DataFrame | None = None,
    open_orders: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    snapshot_ts_ns: int | float | None = None,
    source_paths: dict[str, str | Path | None] | None = None,
) -> RuntimeTelemetryReport:
    return _evaluate_runtime_telemetry(
        scaleup_config,
        export_summary=export_summary,
        upload_summary=upload_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
        snapshot_ts_ns=snapshot_ts_ns,
        source_paths=source_paths,
        scaleup_provenance=empty_scaleup_runtime_provenance(),
    )


def _evaluate_runtime_telemetry(
    scaleup_config: dict[str, Any],
    *,
    export_summary: pd.DataFrame | None = None,
    upload_summary: pd.DataFrame | None = None,
    reconciliation_summary: pd.DataFrame | None = None,
    reconciliation_checks: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    pnl_snapshot: pd.DataFrame | None = None,
    open_orders: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    snapshot_ts_ns: int | float | None = None,
    source_paths: dict[str, str | Path | None] | None = None,
    scaleup_provenance: dict[str, Any],
) -> RuntimeTelemetryReport:
    export_summary = _optional_frame(export_summary)
    upload_summary = _optional_frame(upload_summary)
    reconciliation_summary = _optional_frame(reconciliation_summary)
    reconciliation_checks = _optional_frame(reconciliation_checks)
    instrument_metadata_summary = _optional_frame(instrument_metadata_summary)
    pnl_snapshot = _optional_frame(pnl_snapshot)
    open_orders = _optional_frame(open_orders)
    positions = _optional_frame(positions)

    telemetry = _telemetry(
        scaleup_config,
        export_summary=export_summary,
        upload_summary=upload_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
        snapshot_ts_ns=snapshot_ts_ns,
        scaleup_provenance=scaleup_provenance,
    )
    sources = _sources(
        source_paths=source_paths,
        export_summary=export_summary,
        upload_summary=upload_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
    )
    checks = _checks(telemetry.iloc[0])
    summary = _summary(telemetry.iloc[0], checks)
    return RuntimeTelemetryReport(telemetry=telemetry, sources=sources, checks=checks, summary=summary)


def write_runtime_telemetry_snapshot(
    *,
    scaleup_dir: str | Path,
    output_dir: str | Path,
    export_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    pnl_path: str | Path | None = None,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    snapshot_ts_ns: int | float | None = None,
) -> RuntimeTelemetryReport:
    scaleup_file = _scaleup_config_path(scaleup_dir)
    scaleup_config = json.loads(scaleup_file.read_text(encoding="utf-8"))
    scaleup_provenance = load_scaleup_runtime_provenance(
        scaleup_file,
        scaleup_config=scaleup_config,
    )
    out = Path(output_dir)
    if out.resolve() == scaleup_file.parent.resolve():
        raise ValueError("runtime telemetry output must not overwrite the scale-up bundle")
    export_summary, export_summary_path = _read_optional_summary_with_path(
        export_dir,
        "broker_order_summary.csv",
        fallback_dirs=("04_export", "03_export"),
    )
    upload_summary, upload_summary_path = _read_optional_summary_with_path(
        upload_pack_dir,
        "broker_upload_summary.csv",
        fallback_dirs=("05_upload_pack", "04_upload_pack"),
    )
    reconciliation_summary, reconciliation_summary_path = _read_optional_summary_with_path(
        reconciliation_dir,
        "reconciliation_summary.csv",
    )
    reconciliation_checks, reconciliation_checks_path = _read_optional_summary_with_path(
        reconciliation_dir,
        "reconciliation_checks.csv",
    )
    instrument_metadata_summary, instrument_metadata_summary_path = _read_optional_summary_with_path(
        instrument_metadata_dir,
        "instrument_metadata_summary.csv",
    )
    pnl_snapshot = _read_optional_csv(pnl_path)
    open_orders = _read_optional_csv(open_orders_path)
    positions = _read_optional_csv(positions_path)
    source_paths = {
        "export_summary": export_summary_path,
        "upload_summary": upload_summary_path,
        "reconciliation_summary": reconciliation_summary_path,
        "reconciliation_checks": reconciliation_checks_path,
        "instrument_metadata_summary": instrument_metadata_summary_path,
        "pnl_snapshot": Path(pnl_path) if pnl_path is not None else None,
        "open_orders": Path(open_orders_path) if open_orders_path is not None else None,
        "positions": Path(positions_path) if positions_path is not None else None,
    }

    report = _evaluate_runtime_telemetry(
        scaleup_config,
        export_summary=export_summary,
        upload_summary=upload_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
        snapshot_ts_ns=snapshot_ts_ns,
        source_paths=source_paths,
        scaleup_provenance=scaleup_provenance,
    )
    out.mkdir(parents=True, exist_ok=True)
    report.telemetry.to_csv(out / "runtime_telemetry.csv", index=False)
    report.sources.to_csv(out / "runtime_telemetry_sources.csv", index=False)
    report.checks.to_csv(out / "runtime_telemetry_checks.csv", index=False)
    report.summary.to_csv(out / "runtime_telemetry_summary.csv", index=False)
    manifest_inputs: dict[str, Any] = {"scaleup": scaleup_file}
    manifest_inputs.update(scaleup_runtime_manifest_inputs(scaleup_provenance))
    for name, value in {
        "export": export_summary_path,
        "upload_pack": upload_summary_path,
        "reconciliation_summary": reconciliation_summary_path,
        "reconciliation_checks": reconciliation_checks_path,
        "instrument_metadata": instrument_metadata_summary_path,
        "pnl": pnl_path,
        "open_orders": open_orders_path,
        "positions": positions_path,
    }.items():
        if value is not None:
            manifest_inputs[name] = value
    write_experiment_manifest(
        out,
        run_type="runtime_telemetry_snapshot",
        parameters={"snapshot_ts_ns": snapshot_ts_ns},
        inputs=manifest_inputs,
        extra={
            "ready": bool(report.ready),
            **scaleup_runtime_manifest_extra(scaleup_provenance),
            "strategy_portfolio_leadlag_edge_lineage_required": _to_bool(
                report.summary.iloc[0].get(
                    "strategy_portfolio_leadlag_edge_lineage_required",
                    False,
                )
            ),
            "strategy_portfolio_leadlag_edge_lineage_ready": leadlag_lineage_ready(
                report.summary.iloc[0],
                prefix="strategy_portfolio_",
            ),
            "authorizes_submission": False,
        },
    )
    return RuntimeTelemetryReport(report.telemetry, report.sources, report.checks, report.summary, out)


def _telemetry(
    scaleup_config: dict[str, Any],
    *,
    export_summary: pd.DataFrame,
    upload_summary: pd.DataFrame,
    reconciliation_summary: pd.DataFrame,
    reconciliation_checks: pd.DataFrame,
    instrument_metadata_summary: pd.DataFrame,
    pnl_snapshot: pd.DataFrame,
    open_orders: pd.DataFrame,
    positions: pd.DataFrame,
    snapshot_ts_ns: int | float | None,
    scaleup_provenance: dict[str, Any],
) -> pd.DataFrame:
    export = _first_row(export_summary)
    upload = _first_row(upload_summary)
    recon = _first_row(reconciliation_summary)
    metadata = _first_row(instrument_metadata_summary)
    scaleup_metadata = scaleup_config.get("instrument_metadata", {}) or {}
    proof_freshness = scaleup_config.get("proof_freshness", {}) or {}
    if not isinstance(proof_freshness, dict):
        proof_freshness = {}
    broker_readiness = scaleup_config.get("broker_readiness", {}) or {}
    if not isinstance(broker_readiness, dict):
        broker_readiness = {}
    strategy_portfolio = scaleup_config.get("strategy_portfolio", {}) or {}
    if not isinstance(strategy_portfolio, dict):
        strategy_portfolio = {}
    strategy_portfolio_leadlag_required = bool(
        _to_bool(
            strategy_portfolio.get("leadlag_edge_lineage_required", False)
        )
        or _identity_key(strategy_portfolio.get("selected_profile", ""))
        == "leadlag"
    )
    strategy_portfolio_leadlag_lineage = leadlag_lineage_fields(
        strategy_portfolio,
        target_prefix="strategy_portfolio_",
    )
    broker_resume_gate = broker_readiness.get("resume_gate", {}) or {}
    if not isinstance(broker_resume_gate, dict):
        broker_resume_gate = {}
    broker_route_readiness = broker_readiness.get("route_readiness", {}) or {}
    if not isinstance(broker_route_readiness, dict):
        broker_route_readiness = {}
    pnl = _last_row(pnl_snapshot)
    orders_sent = _first_number(
        _number(export, "orders"),
        _number(recon, "orders"),
        float(len(open_orders)) if not open_orders.empty else np.nan,
        0.0,
    )
    session_notional = _first_number(
        _number(export, "total_notional"),
        _number(pnl, "session_notional"),
        _number(pnl, "total_notional"),
        0.0,
    )
    upload_failed = _first_number(_number(upload, "failed_checks"), 0.0)
    total_failed = _first_number(_number(export, "failed_checks"), 0.0) + upload_failed + _failed_checks(reconciliation_checks)
    row = {
        **scaleup_runtime_fields(scaleup_provenance),
        "snapshot_ts_ns": _first_number(snapshot_ts_ns, _number(pnl, "ts_ns"), _number(pnl, "timestamp_ns"), np.nan),
        "target_mode": str(scaleup_config.get("target_mode", "")),
        "strategy": _strategy_key(_scaleup_identity(scaleup_config, "strategy")),
        "market": _identity_key(_scaleup_identity(scaleup_config, "market")),
        "scenario_key": str(_first_value(export.get("scenario_key", np.nan), scaleup_config.get("scenario_key", ""))),
        "adapter": str(_first_value(export.get("adapter", np.nan), scaleup_config.get("adapter", ""))),
        "orders_sent": int(orders_sent),
        "lifecycle_orders": int(_first_number(_number(upload, "lifecycle_orders"), 0.0)),
        "replace_orders": int(_first_number(_number(upload, "replace_orders"), 0.0)),
        "session_notional": float(session_notional),
        "strategy_portfolio_required": _to_bool(strategy_portfolio.get("required", False)),
        "strategy_portfolio_provided": _to_bool(strategy_portfolio.get("provided", False)),
        "strategy_portfolio_ready": _to_bool(strategy_portfolio.get("ready", False)),
        "strategy_portfolio_leadlag_edge_lineage_required": strategy_portfolio_leadlag_required,
        **strategy_portfolio_leadlag_lineage,
        "strategy_portfolio_deployment_mode": str(strategy_portfolio.get("deployment_mode", "")),
        "strategy_portfolio_allocation_mode": str(strategy_portfolio.get("allocation_mode", "")),
        "strategy_portfolio_capital_currency": str(strategy_portfolio.get("capital_currency", "")),
        "strategy_portfolio_selected_profile": str(strategy_portfolio.get("selected_profile", "")),
        "strategy_portfolio_selected_strategy": _strategy_key(strategy_portfolio.get("selected_strategy", "")),
        "strategy_portfolio_selected_market": _identity_key(strategy_portfolio.get("selected_market", "")),
        "strategy_portfolio_selected_eligible": _to_bool(strategy_portfolio.get("selected_eligible", False)),
        "strategy_portfolio_selected_allocation_weight": float(
            _first_number(strategy_portfolio.get("selected_allocation_weight"), 0.0)
        ),
        "strategy_portfolio_selected_allocation_notional": float(
            _first_number(strategy_portfolio.get("selected_allocation_notional"), 0.0)
        ),
        "strategy_portfolio_notional_cap_applied": _to_bool(strategy_portfolio.get("notional_cap_applied", False)),
        "strategy_portfolio_min_strategy_count": int(
            _first_number(strategy_portfolio.get("min_strategy_count"), 0.0)
        ),
        "strategy_portfolio_min_market_count": int(_first_number(strategy_portfolio.get("min_market_count"), 0.0)),
        "strategy_portfolio_max_strategy_weight": float(
            _first_number(strategy_portfolio.get("max_strategy_weight"), 0.0)
        ),
        "strategy_portfolio_max_market_weight": float(
            _first_number(strategy_portfolio.get("max_market_weight"), 0.0)
        ),
        "strategy_portfolio_allocated_strategy_count": int(
            _first_number(strategy_portfolio.get("allocated_strategy_count"), 0.0)
        ),
        "strategy_portfolio_allocated_market_count": int(
            _first_number(strategy_portfolio.get("allocated_market_count"), 0.0)
        ),
        "strategy_portfolio_top_strategy_by_weight": _strategy_key(
            strategy_portfolio.get("top_strategy_by_weight", "")
        ),
        "strategy_portfolio_top_market_by_weight": _identity_key(
            strategy_portfolio.get("top_market_by_weight", "")
        ),
        "strategy_portfolio_max_strategy_allocation_weight": float(
            _first_number(strategy_portfolio.get("max_strategy_allocation_weight"), 0.0)
        ),
        "strategy_portfolio_max_market_allocation_weight": float(
            _first_number(strategy_portfolio.get("max_market_allocation_weight"), 0.0)
        ),
        "pre_portfolio_max_notional_per_session": float(
            _first_number(
                (scaleup_config.get("limits", {}) or {}).get("pre_portfolio_max_notional_per_session")
                if isinstance(scaleup_config.get("limits", {}), dict)
                else np.nan,
                np.nan,
            )
        ),
        "realized_pnl": float(_first_number(_number(pnl, "realized_pnl"), _number(pnl, "net_pnl"), _number(pnl, "pnl"), 0.0)),
        "total_failed_component_checks": int(total_failed),
        "broker_upload_pack_provided": not upload_summary.empty,
        "broker_upload_pack_ready": _to_bool(upload.get("ready", False)) if not upload.empty else False,
        "broker_upload_failed_checks": int(upload_failed),
        "unmatched_fills": int(_first_number(_number(recon, "unmatched_fills"), 0.0)),
        "mismatched_orders": int(_first_number(_number(recon, "mismatched_orders"), 0.0)),
        "overfilled_orders": int(_first_number(_number(recon, "overfilled_orders"), 0.0)),
        "worst_adverse_slippage": float(_first_number(_number(recon, "max_adverse_slippage"), 0.0)),
        "instrument_metadata_required": _to_bool(scaleup_metadata.get("required", False)),
        "instrument_metadata_provided": not instrument_metadata_summary.empty,
        "instrument_metadata_passed": _to_bool(metadata.get("passed", False)) if not metadata.empty else False,
        "instrument_parse_coverage": float(_first_number(_number(metadata, "parse_coverage"), np.nan)),
        "min_instrument_parse_coverage": float(
            _first_number(
                _number(metadata, "min_parse_coverage"),
                scaleup_metadata.get("min_parse_coverage", np.nan),
                np.nan,
            )
        ),
        "unparsed_instruments": float(_first_number(_number(metadata, "unparsed_instruments"), np.nan)),
        "proof_refresh_required": _to_bool(proof_freshness.get("required", False)),
        "proof_refresh_provided": _to_bool(proof_freshness.get("provided", False)),
        "proof_refresh_ready": _to_bool(proof_freshness.get("ready", False)),
        "proof_refresh_strategy": _strategy_key(proof_freshness.get("strategy", "")),
        "proof_refresh_market": _identity_key(proof_freshness.get("market", "")),
        "proof_refresh_mixed_identity": _to_bool(proof_freshness.get("mixed_identity", False)),
        "proof_source": str(proof_freshness.get("proof_source", "")),
        "fresh_proof_required": _to_bool(proof_freshness.get("fresh_proof_required", False)),
        "broker_resume_gate_required": _to_bool(broker_resume_gate.get("required", False)),
        "broker_resume_gate_provided": _to_bool(broker_resume_gate.get("provided", False)),
        "broker_resume_gate_ready": _to_bool(broker_resume_gate.get("ready", False)),
        "broker_resume_strategy": _strategy_key(broker_resume_gate.get("strategy", "")),
        "broker_resume_market": _identity_key(broker_resume_gate.get("market", "")),
        "broker_resume_incident_strategy": _strategy_key(broker_resume_gate.get("incident_strategy", "")),
        "broker_resume_incident_market": _identity_key(broker_resume_gate.get("incident_market", "")),
        "broker_resume_proof_refresh_ready": _to_bool(broker_resume_gate.get("proof_refresh_ready", False)),
        "broker_resume_proof_refresh_strategy": _strategy_key(
            broker_resume_gate.get("proof_refresh_strategy", "")
        ),
        "broker_resume_proof_refresh_market": _identity_key(broker_resume_gate.get("proof_refresh_market", "")),
        "broker_route_readiness_required": _to_bool(broker_route_readiness.get("required", False)),
        "broker_route_readiness_provided": _to_bool(broker_route_readiness.get("provided", False)),
        "broker_route_readiness_ready": _to_bool(broker_route_readiness.get("ready", False)),
        "broker_route_readiness_strategy": _strategy_key(broker_route_readiness.get("strategy", "")),
        "broker_route_readiness_market": _identity_key(broker_route_readiness.get("market", "")),
        "broker_route_readiness_route_ready_pairs": int(
            _first_number(broker_route_readiness.get("route_ready_pairs"), 0.0)
        ),
        "broker_route_readiness_gap_pairs": int(_first_number(broker_route_readiness.get("gap_pairs"), 0.0)),
        "broker_route_readiness_recommendation": str(broker_route_readiness.get("recommendation", "")),
        "broker_route_readiness_ops_launch_controls_ready": _to_bool(
            broker_route_readiness.get("ops_launch_controls_ready", False)
        ),
        "broker_route_readiness_ops_launch_control_failures": str(
            broker_route_readiness.get("ops_launch_control_failures", "")
        ).strip(),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _first_number(broker_route_readiness.get("ops_broker_roundtrip_portfolio_safe_runs"), 0.0)
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _first_number(broker_route_readiness.get("ops_broker_roundtrip_portfolio_breach_runs"), 0.0)
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _first_number(
                broker_route_readiness.get("ops_broker_roundtrip_portfolio_concentration_ok_runs"),
                0.0,
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _first_number(
                broker_route_readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_runs"),
                0.0,
            )
        ),
        "open_order_count": int(_active_open_orders(open_orders)),
        "open_order_qty": float(_open_order_qty(open_orders)),
        "open_order_notional": float(_open_order_notional(open_orders)),
        "oldest_open_order_age_ns": float(
            _oldest_open_order_age_ns(
                open_orders,
                _first_number(snapshot_ts_ns, _number(pnl, "ts_ns"), _number(pnl, "timestamp_ns"), np.nan),
            )
        ),
        "gross_position_qty": float(_gross_position_qty(positions)),
        "abs_net_position_qty": float(_abs_net_position_qty(positions)),
        "gross_position_notional": float(_gross_position_notional(positions)),
        "net_position_notional": float(_net_position_notional(positions)),
        "abs_net_position_notional": float(abs(_net_position_notional(positions))),
        "net_delta": float(_net_greek_exposure(positions, "delta")),
        "abs_net_delta": float(abs(_net_greek_exposure(positions, "delta"))),
        "net_vega": float(_net_greek_exposure(positions, "vega")),
        "abs_net_vega": float(abs(_net_greek_exposure(positions, "vega"))),
    }
    return pd.DataFrame([row])


def _sources(
    source_paths: dict[str, str | Path | None] | None = None,
    **frames: pd.DataFrame,
) -> pd.DataFrame:
    source_paths = source_paths or {}
    return pd.DataFrame(
        [
            {
                "source": name,
                "provided": not frame.empty,
                "path": _source_path(source_paths.get(name)),
                "rows": int(len(frame)),
                "columns": ";".join(frame.columns.astype(str).tolist()) if not frame.empty else "",
            }
            for name, frame in frames.items()
        ]
    )


def _checks(row: pd.Series) -> pd.DataFrame:
    checks = [
        _check("strategy_present", row["strategy"], "not_empty", True, bool(str(row["strategy"]).strip()), "strategy identity is missing"),
        _check("market_present", row["market"], "not_empty", True, bool(str(row["market"]).strip()), "market identity is missing"),
        _check("scenario_key_present", row["scenario_key"], "not_empty", True, bool(str(row["scenario_key"]).strip()), "scenario_key is missing"),
        _check("adapter_present", row["adapter"], "not_empty", True, bool(str(row["adapter"]).strip()), "adapter is missing"),
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
        if _to_bool(row.get("scaleup_proof_refresh_active", False)):
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
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(
                    _check(name, passed, "is", True, passed, reason)
                )
        portfolio_active = _to_bool(
            row.get("scaleup_strategy_portfolio_required", False)
        ) or _to_bool(row.get("scaleup_strategy_portfolio_provided", False))
        if portfolio_active:
            for name, reason in (
                (
                    "scaleup_strategy_portfolio_manifest_current",
                    "scale-up portfolio manifest is not current",
                ),
                (
                    "scaleup_strategy_portfolio_provenance_gate_passed",
                    "scale-up portfolio provenance gate did not pass",
                ),
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(_check(name, passed, "is", True, passed, reason))
        if _to_bool(row.get("scaleup_scorecard_manifest_required", False)):
            for name, reason in (
                (
                    "scaleup_scorecard_manifest_current",
                    "scale-up scorecard manifest is not current",
                ),
                (
                    "scaleup_scorecard_provenance_gate_passed",
                    "scale-up scorecard provenance gate did not pass",
                ),
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(_check(name, passed, "is", True, passed, reason))
        if _to_bool(row.get("scaleup_research_family_bound", False)):
            family_current = _to_bool(
                row.get("scaleup_research_family_provenance_current", False)
            )
            checks.extend(
                [
                    _check(
                        "scaleup_research_family_provenance_current",
                        family_current,
                        "is",
                        True,
                        family_current,
                        "registered research-family proof is not current",
                    ),
                    _check(
                        "scaleup_research_family_identity_present",
                        _family_identity(row),
                        "complete",
                        True,
                        bool(_family_identity(row)),
                        "registered research-family identity or manifest hash is missing",
                    ),
                ]
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
            ):
                passed = _to_bool(row.get(name, False))
                checks.append(_check(name, passed, "is", True, passed, reason))
            contract_identity_active = _to_bool(
                row.get(
                    (
                        "scaleup_broker_readiness_roundtrip_"
                        "contract_identity_active"
                    ),
                    False,
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
                identity_sha = str(
                    row.get(
                        (
                            "scaleup_broker_readiness_roundtrip_"
                            "contract_identity_sha256"
                        ),
                        "",
                    )
                ).strip()
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
                            _to_bool(
                                row.get(
                                    (
                                        "scaleup_broker_readiness_roundtrip_"
                                        "contract_identity_matches_current"
                                    ),
                                    False,
                                )
                            ),
                            "is",
                            True,
                            _to_bool(
                                row.get(
                                    (
                                        "scaleup_broker_readiness_roundtrip_"
                                        "contract_identity_matches_current"
                                    ),
                                    False,
                                )
                            ),
                            (
                                "terminal round-trip contract identity "
                                "differs from current broker readiness"
                            ),
                        ),
                    ]
                )
    for column in GUARD_COLUMNS:
        value = row[column]
        present = not pd.isna(value) and (not isinstance(value, str) or bool(value.strip()))
        checks.append(_check(f"{column}_available", value, "present", True, present, f"{column} is unavailable"))
    upload_provided = _to_bool(row.get("broker_upload_pack_provided", False))
    if upload_provided:
        upload_ready = _to_bool(row.get("broker_upload_pack_ready", False))
        checks.append(
            _check(
                "broker_upload_pack_ready",
                upload_ready,
                "is",
                True,
                upload_ready,
                "broker upload pack is not ready",
            )
        )
    metadata_required = _to_bool(row.get("instrument_metadata_required", False))
    metadata_provided = _to_bool(row.get("instrument_metadata_provided", False))
    if metadata_required:
        checks.append(
            _check(
                "instrument_metadata_provided",
                metadata_provided,
                "is",
                True,
                metadata_provided,
                "instrument metadata summary is required but was not supplied",
            )
        )
    if metadata_required or metadata_provided:
        metadata_passed = _to_bool(row.get("instrument_metadata_passed", False))
        parse_coverage = _number(row, "instrument_parse_coverage")
        min_coverage = _number(row, "min_instrument_parse_coverage")
        unparsed = _number(row, "unparsed_instruments")
        coverage_ready = not np.isnan(parse_coverage) and not np.isnan(min_coverage) and parse_coverage + 1e-12 >= min_coverage
        unparsed_ready = not np.isnan(unparsed) and unparsed <= 0
        checks.extend(
            [
                _check(
                    "instrument_metadata_passed",
                    metadata_passed,
                    "is",
                    True,
                    metadata_passed,
                    "instrument metadata summary did not pass",
                ),
                _check(
                    "instrument_parse_coverage",
                    parse_coverage,
                    ">=",
                    min_coverage,
                    coverage_ready,
                    "instrument parse coverage is below the required threshold",
                ),
                _check(
                    "unparsed_instruments",
                    unparsed,
                    "<=",
                    0,
                    unparsed_ready,
                    "instrument metadata contains unparsed instruments",
                ),
            ]
        )
    portfolio_required = _to_bool(row.get("strategy_portfolio_required", False))
    portfolio_provided = _to_bool(row.get("strategy_portfolio_provided", False))
    if portfolio_required:
        checks.append(
            _check(
                "strategy_portfolio_provided",
                portfolio_provided,
                "is",
                True,
                portfolio_provided,
                "strategy portfolio allocation is required but missing from scale-up config",
            )
        )
    if portfolio_required or portfolio_provided:
        portfolio_ready = _to_bool(row.get("strategy_portfolio_ready", False))
        portfolio_eligible = _to_bool(row.get("strategy_portfolio_selected_eligible", False))
        portfolio_strategy = _strategy_key(row.get("strategy_portfolio_selected_strategy", ""))
        portfolio_market = _identity_key(row.get("strategy_portfolio_selected_market", ""))
        allocation_notional = _number(row, "strategy_portfolio_selected_allocation_notional")
        strategy = _strategy_key(row.get("strategy", ""))
        market = _identity_key(row.get("market", ""))
        checks.extend(
            [
                _check(
                    "strategy_portfolio_ready",
                    portfolio_ready,
                    "is",
                    True,
                    portfolio_ready,
                    "strategy portfolio allocation is not ready",
                ),
                _check(
                    "strategy_portfolio_allocation_eligible",
                    portfolio_eligible,
                    "is",
                    True,
                    portfolio_eligible,
                    "strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "strategy_portfolio_strategy_matches",
                    portfolio_strategy,
                    "==",
                    strategy,
                    bool(portfolio_strategy and strategy and portfolio_strategy == strategy),
                    "strategy portfolio allocation strategy does not match runtime telemetry strategy",
                ),
                _check(
                    "strategy_portfolio_market_matches",
                    portfolio_market,
                    "==",
                    market,
                    bool(portfolio_market and market and portfolio_market == market),
                    "strategy portfolio allocation market does not match runtime telemetry market",
                ),
                _check(
                    "strategy_portfolio_allocation_positive",
                    allocation_notional,
                    ">",
                    0.0,
                    not np.isnan(allocation_notional) and allocation_notional > 0.0,
                    "strategy portfolio allocation notional must be positive",
                ),
            ]
        )
        leadlag_lineage_required = _to_bool(
            row.get("strategy_portfolio_leadlag_edge_lineage_required", False)
        )
        if leadlag_lineage_required:
            lineage_ready = leadlag_lineage_ready(
                row,
                prefix="strategy_portfolio_",
            )
            checks.append(
                _check(
                    "strategy_portfolio_leadlag_edge_lineage_ready",
                    lineage_ready,
                    "is",
                    True,
                    lineage_ready,
                    "lead-lag strategy portfolio allocation is missing its complete measured-edge lineage",
                )
            )
    proof_refresh_required = _to_bool(row.get("proof_refresh_required", False))
    proof_refresh_provided = _to_bool(row.get("proof_refresh_provided", False))
    if proof_refresh_required:
        checks.append(
            _check(
                "proof_refresh_provided",
                proof_refresh_provided,
                "is",
                True,
                proof_refresh_provided,
                "proof refresh evidence is required but missing from scale-up config",
            )
        )
    if proof_refresh_required or proof_refresh_provided:
        proof_refresh_ready = _to_bool(row.get("proof_refresh_ready", False))
        proof_refresh_mixed = _to_bool(row.get("proof_refresh_mixed_identity", False))
        proof_refresh_strategy = _strategy_key(row.get("proof_refresh_strategy", ""))
        proof_refresh_market = _identity_key(row.get("proof_refresh_market", ""))
        strategy = _strategy_key(row.get("strategy", ""))
        market = _identity_key(row.get("market", ""))
        checks.extend(
            [
                _check(
                    "proof_refresh_ready",
                    proof_refresh_ready,
                    "is",
                    True,
                    proof_refresh_ready,
                    "proof refresh evidence is not ready",
                ),
                _check(
                    "proof_refresh_identity_consistent",
                    proof_refresh_mixed,
                    "is",
                    False,
                    not proof_refresh_mixed,
                    "proof refresh evidence reports mixed strategy or market identity",
                ),
                _check(
                    "proof_refresh_strategy_matches",
                    proof_refresh_strategy,
                    "==",
                    strategy,
                    bool(proof_refresh_strategy and strategy and proof_refresh_strategy == strategy),
                    "proof refresh strategy does not match runtime telemetry strategy",
                ),
                _check(
                    "proof_refresh_market_matches",
                    proof_refresh_market,
                    "==",
                    market,
                    bool(proof_refresh_market and market and proof_refresh_market == market),
                    "proof refresh market does not match runtime telemetry market",
                ),
            ]
        )
    broker_resume_required = _to_bool(row.get("broker_resume_gate_required", False))
    broker_resume_provided = _to_bool(row.get("broker_resume_gate_provided", False))
    if broker_resume_required:
        checks.append(
            _check(
                "broker_resume_gate_provided",
                broker_resume_provided,
                "is",
                True,
                broker_resume_provided,
                "broker resume gate is required but missing from scale-up config",
            )
        )
    if broker_resume_required or broker_resume_provided:
        broker_resume_ready = _to_bool(row.get("broker_resume_gate_ready", False))
        broker_resume_strategy = _strategy_key(row.get("broker_resume_strategy", ""))
        broker_resume_market = _identity_key(row.get("broker_resume_market", ""))
        broker_resume_proof_ready = _to_bool(row.get("broker_resume_proof_refresh_ready", False))
        broker_resume_proof_strategy = _strategy_key(row.get("broker_resume_proof_refresh_strategy", ""))
        broker_resume_proof_market = _identity_key(row.get("broker_resume_proof_refresh_market", ""))
        strategy = _strategy_key(row.get("strategy", ""))
        market = _identity_key(row.get("market", ""))
        checks.extend(
            [
                _check(
                    "broker_resume_gate_ready",
                    broker_resume_ready,
                    "is",
                    True,
                    broker_resume_ready,
                    "broker resume gate is not ready",
                ),
                _check(
                    "broker_resume_strategy_matches",
                    broker_resume_strategy,
                    "==",
                    strategy,
                    bool(broker_resume_strategy and strategy and broker_resume_strategy == strategy),
                    "broker resume-gate strategy does not match runtime telemetry strategy",
                ),
                _check(
                    "broker_resume_market_matches",
                    broker_resume_market,
                    "==",
                    market,
                    bool(broker_resume_market and market and broker_resume_market == market),
                    "broker resume-gate market does not match runtime telemetry market",
                ),
                _check(
                    "broker_resume_proof_refresh_ready",
                    broker_resume_proof_ready,
                    "is",
                    True,
                    broker_resume_proof_ready,
                    "broker resume-gate proof freshness is not ready",
                ),
                _check(
                    "broker_resume_proof_refresh_strategy_matches",
                    broker_resume_proof_strategy,
                    "==",
                    strategy,
                    bool(
                        broker_resume_proof_strategy
                        and strategy
                        and broker_resume_proof_strategy == strategy
                    ),
                    "broker resume-gate proof strategy does not match runtime telemetry strategy",
                ),
                _check(
                    "broker_resume_proof_refresh_market_matches",
                    broker_resume_proof_market,
                    "==",
                    market,
                    bool(broker_resume_proof_market and market and broker_resume_proof_market == market),
                    "broker resume-gate proof market does not match runtime telemetry market",
                ),
            ]
        )
    broker_route_required = _to_bool(row.get("broker_route_readiness_required", False))
    broker_route_provided = _to_bool(row.get("broker_route_readiness_provided", False))
    if broker_route_required:
        checks.append(
            _check(
                "broker_route_readiness_provided",
                broker_route_provided,
                "is",
                True,
                broker_route_provided,
                "broker route readiness is required but missing from scale-up config",
            )
        )
    if broker_route_required or broker_route_provided:
        broker_route_ready = _to_bool(row.get("broker_route_readiness_ready", False))
        broker_route_strategy = _strategy_key(row.get("broker_route_readiness_strategy", ""))
        broker_route_market = _identity_key(row.get("broker_route_readiness_market", ""))
        broker_route_ready_pairs = _number(row, "broker_route_readiness_route_ready_pairs")
        broker_route_gap_pairs = _number(row, "broker_route_readiness_gap_pairs")
        broker_route_ops_ready = _to_bool(row.get("broker_route_readiness_ops_launch_controls_ready", False))
        broker_route_safe_runs = _number(row, "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs")
        broker_route_breach_runs = _number(row, "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs")
        broker_route_concentration_ok_runs = _number(
            row,
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        )
        broker_route_concentration_breach_runs = _number(
            row,
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        )
        strategy = _strategy_key(row.get("strategy", ""))
        market = _identity_key(row.get("market", ""))
        checks.extend(
            [
                _check(
                    "broker_route_readiness_ready",
                    broker_route_ready,
                    "is",
                    True,
                    broker_route_ready,
                    "broker route readiness is not ready",
                ),
                _check(
                    "broker_route_readiness_strategy_matches",
                    broker_route_strategy,
                    "==",
                    strategy,
                    bool(broker_route_strategy and strategy and broker_route_strategy == strategy),
                    "broker route readiness strategy does not match runtime telemetry strategy",
                ),
                _check(
                    "broker_route_readiness_market_matches",
                    broker_route_market,
                    "==",
                    market,
                    bool(broker_route_market and market and broker_route_market == market),
                    "broker route readiness market does not match runtime telemetry market",
                ),
                _check(
                    "broker_route_readiness_route_ready_pairs",
                    broker_route_ready_pairs,
                    ">",
                    0.0,
                    not np.isnan(broker_route_ready_pairs) and broker_route_ready_pairs > 0.0,
                    "broker route readiness has no ready route pairs",
                ),
                _check(
                    "broker_route_readiness_gap_pairs",
                    broker_route_gap_pairs,
                    "<=",
                    0,
                    not np.isnan(broker_route_gap_pairs) and broker_route_gap_pairs <= 0,
                    "broker route readiness has route gap pairs",
                ),
                _check(
                    "broker_route_readiness_ops_launch_controls_ready",
                    broker_route_ops_ready,
                    "is",
                    True,
                    broker_route_ops_ready,
                    "broker route readiness ops launch controls are not ready",
                ),
                _check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    broker_route_safe_runs,
                    ">",
                    0.0,
                    not np.isnan(broker_route_safe_runs) and broker_route_safe_runs > 0.0,
                    "broker route readiness has no safe broker round-trip portfolio run",
                ),
                _check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    broker_route_breach_runs,
                    "<=",
                    0,
                    not np.isnan(broker_route_breach_runs) and broker_route_breach_runs <= 0,
                    "broker route readiness has broker round-trip portfolio breach runs",
                ),
                _check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    broker_route_concentration_ok_runs,
                    ">",
                    0.0,
                    not np.isnan(broker_route_concentration_ok_runs)
                    and broker_route_concentration_ok_runs > 0.0,
                    "broker route readiness has no concentration-safe broker round-trip portfolio run",
                ),
                _check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    broker_route_concentration_breach_runs,
                    "<=",
                    0,
                    not np.isnan(broker_route_concentration_breach_runs)
                    and broker_route_concentration_breach_runs <= 0,
                    "broker route readiness has concentration breach runs",
                ),
            ]
        )
    return pd.DataFrame(checks)


def _summary(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "authorizes_submission": False,
                **{column: row[column] for column in SCALEUP_PROVENANCE_COLUMNS},
                "target_mode": row["target_mode"],
                "strategy": row["strategy"],
                "market": row["market"],
                "scenario_key": row["scenario_key"],
                "adapter": row["adapter"],
                "orders_sent": int(row["orders_sent"]),
                "lifecycle_orders": int(row["lifecycle_orders"]),
                "replace_orders": int(row["replace_orders"]),
                "session_notional": float(row["session_notional"]),
                "strategy_portfolio_required": _to_bool(row["strategy_portfolio_required"]),
                "strategy_portfolio_provided": _to_bool(row["strategy_portfolio_provided"]),
                "strategy_portfolio_ready": _to_bool(row["strategy_portfolio_ready"]),
                "strategy_portfolio_leadlag_edge_lineage_required": _to_bool(
                    row["strategy_portfolio_leadlag_edge_lineage_required"]
                ),
                **{
                    f"strategy_portfolio_{field}": row[
                        f"strategy_portfolio_{field}"
                    ]
                    for field in LEADLAG_LINEAGE_FIELDS
                },
                "strategy_portfolio_deployment_mode": row["strategy_portfolio_deployment_mode"],
                "strategy_portfolio_allocation_mode": row["strategy_portfolio_allocation_mode"],
                "strategy_portfolio_capital_currency": row["strategy_portfolio_capital_currency"],
                "strategy_portfolio_selected_profile": row["strategy_portfolio_selected_profile"],
                "strategy_portfolio_selected_strategy": row["strategy_portfolio_selected_strategy"],
                "strategy_portfolio_selected_market": row["strategy_portfolio_selected_market"],
                "strategy_portfolio_selected_eligible": _to_bool(row["strategy_portfolio_selected_eligible"]),
                "strategy_portfolio_selected_allocation_weight": float(
                    row["strategy_portfolio_selected_allocation_weight"]
                ),
                "strategy_portfolio_selected_allocation_notional": float(
                    row["strategy_portfolio_selected_allocation_notional"]
                ),
                "strategy_portfolio_notional_cap_applied": _to_bool(row["strategy_portfolio_notional_cap_applied"]),
                "strategy_portfolio_min_strategy_count": int(row["strategy_portfolio_min_strategy_count"]),
                "strategy_portfolio_min_market_count": int(row["strategy_portfolio_min_market_count"]),
                "strategy_portfolio_max_strategy_weight": float(row["strategy_portfolio_max_strategy_weight"]),
                "strategy_portfolio_max_market_weight": float(row["strategy_portfolio_max_market_weight"]),
                "strategy_portfolio_allocated_strategy_count": int(
                    row["strategy_portfolio_allocated_strategy_count"]
                ),
                "strategy_portfolio_allocated_market_count": int(
                    row["strategy_portfolio_allocated_market_count"]
                ),
                "strategy_portfolio_top_strategy_by_weight": row["strategy_portfolio_top_strategy_by_weight"],
                "strategy_portfolio_top_market_by_weight": row["strategy_portfolio_top_market_by_weight"],
                "strategy_portfolio_max_strategy_allocation_weight": float(
                    row["strategy_portfolio_max_strategy_allocation_weight"]
                ),
                "strategy_portfolio_max_market_allocation_weight": float(
                    row["strategy_portfolio_max_market_allocation_weight"]
                ),
                "pre_portfolio_max_notional_per_session": float(row["pre_portfolio_max_notional_per_session"]),
                "realized_pnl": float(row["realized_pnl"]),
                "open_order_notional": float(row["open_order_notional"]),
                "oldest_open_order_age_ns": float(row["oldest_open_order_age_ns"]),
                "gross_position_notional": float(row["gross_position_notional"]),
                "abs_net_delta": float(row["abs_net_delta"]),
                "abs_net_vega": float(row["abs_net_vega"]),
                "proof_refresh_required": _to_bool(row["proof_refresh_required"]),
                "proof_refresh_provided": _to_bool(row["proof_refresh_provided"]),
                "proof_refresh_ready": _to_bool(row["proof_refresh_ready"]),
                "proof_refresh_strategy": row["proof_refresh_strategy"],
                "proof_refresh_market": row["proof_refresh_market"],
                "proof_refresh_mixed_identity": _to_bool(row["proof_refresh_mixed_identity"]),
                "proof_source": row["proof_source"],
                "broker_resume_gate_required": _to_bool(row["broker_resume_gate_required"]),
                "broker_resume_gate_provided": _to_bool(row["broker_resume_gate_provided"]),
                "broker_resume_gate_ready": _to_bool(row["broker_resume_gate_ready"]),
                "broker_resume_strategy": row["broker_resume_strategy"],
                "broker_resume_market": row["broker_resume_market"],
                "broker_resume_incident_strategy": row["broker_resume_incident_strategy"],
                "broker_resume_incident_market": row["broker_resume_incident_market"],
                "broker_resume_proof_refresh_ready": _to_bool(row["broker_resume_proof_refresh_ready"]),
                "broker_resume_proof_refresh_strategy": row["broker_resume_proof_refresh_strategy"],
                "broker_resume_proof_refresh_market": row["broker_resume_proof_refresh_market"],
                "broker_route_readiness_required": _to_bool(row["broker_route_readiness_required"]),
                "broker_route_readiness_provided": _to_bool(row["broker_route_readiness_provided"]),
                "broker_route_readiness_ready": _to_bool(row["broker_route_readiness_ready"]),
                "broker_route_readiness_strategy": row["broker_route_readiness_strategy"],
                "broker_route_readiness_market": row["broker_route_readiness_market"],
                "broker_route_readiness_route_ready_pairs": int(row["broker_route_readiness_route_ready_pairs"]),
                "broker_route_readiness_gap_pairs": int(row["broker_route_readiness_gap_pairs"]),
                "broker_route_readiness_recommendation": row["broker_route_readiness_recommendation"],
                "broker_route_readiness_ops_launch_controls_ready": _to_bool(
                    row["broker_route_readiness_ops_launch_controls_ready"]
                ),
                "broker_route_readiness_ops_launch_control_failures": row[
                    "broker_route_readiness_ops_launch_control_failures"
                ],
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    row["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    row["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    row["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    row["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
                ),
                "failed_checks": failed,
                "recommendation": "feed_runtime_guard" if ready else "fix_telemetry_before_guard",
            }
        ]
    )


def _scaleup_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "scaleup_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"scale-up config not found: {candidate}")
    return candidate


def _family_identity(row: pd.Series) -> str:
    values = (
        str(row.get("scaleup_research_family_id", "")).strip(),
        str(row.get("scaleup_research_family_registration_id", "")).strip(),
        str(row.get("scaleup_research_family_manifest_sha256", "")).strip(),
    )
    return ":".join(values) if all(values) else ""


def _read_optional_summary(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> pd.DataFrame | None:
    frame, _ = _read_optional_summary_with_path(path, filename, fallback_dirs=fallback_dirs)
    return frame


def _read_optional_summary_with_path(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> tuple[pd.DataFrame | None, Path | None]:
    if path is None:
        return None, None
    candidate = _optional_summary_path(path, filename, fallback_dirs=fallback_dirs)
    return _read_optional_csv(candidate), candidate


def _optional_summary_path(
    path: str | Path,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    return next(
        (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
        direct,
    )


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists():
        raise FileNotFoundError(f"optional runtime telemetry input not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"optional runtime telemetry input is empty: {candidate}")
    return frame


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _source_path(path: str | Path | None) -> str:
    if path is None:
        return ""
    return str(Path(path).resolve())


def _first_row(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[0] if not frame.empty else pd.Series(dtype=object)


def _last_row(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[-1] if not frame.empty else pd.Series(dtype=object)


def _number(row: pd.Series, column: str) -> float:
    if row.empty or column not in row.index:
        return np.nan
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else np.nan


def _first_number(*values: object) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(number):
            return number
    return np.nan


def _first_value(*values: object) -> object:
    for value in values:
        if not pd.isna(value) and str(value).strip():
            return value
    return ""


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


def _failed_checks(checks: pd.DataFrame) -> int:
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _active_open_orders(open_orders: pd.DataFrame) -> int:
    if open_orders.empty:
        return 0
    return int(_active_open_order_mask(open_orders).sum())


def _open_order_qty(open_orders: pd.DataFrame) -> float:
    if open_orders.empty:
        return 0.0
    return float(_open_quantities(open_orders).loc[_active_open_order_mask(open_orders)].sum())


def _open_order_notional(open_orders: pd.DataFrame) -> float:
    if open_orders.empty:
        return 0.0
    active = _active_open_order_mask(open_orders)
    for column in ("open_notional", "leaves_notional", "remaining_notional"):
        if column in open_orders.columns:
            return float(pd.to_numeric(open_orders.loc[active, column], errors="coerce").fillna(0.0).abs().sum())
    if "notional" in open_orders.columns:
        qty = _open_quantities(open_orders)
        total_qty = _order_quantities(open_orders).replace(0.0, np.nan)
        notional = pd.to_numeric(open_orders["notional"], errors="coerce").fillna(0.0).abs()
        return float((notional * (qty / total_qty).fillna(0.0)).loc[active].sum())
    return float((_open_quantities(open_orders).abs() * _open_order_prices(open_orders).abs()).loc[active].sum())


def _oldest_open_order_age_ns(open_orders: pd.DataFrame, snapshot_ts_ns: float) -> float:
    if open_orders.empty:
        return 0.0
    active = _active_open_order_mask(open_orders)
    if not active.any():
        return 0.0
    for column in ("open_order_age_ns", "order_age_ns", "age_ns"):
        if column in open_orders.columns:
            ages = pd.to_numeric(open_orders.loc[active, column], errors="coerce")
            return float(ages.max(skipna=True)) if ages.notna().any() else np.nan
    if np.isnan(snapshot_ts_ns):
        return np.nan
    for column in ("created_ts_ns", "order_ts_ns", "submitted_ts_ns", "ts_ns", "timestamp_ns"):
        if column in open_orders.columns:
            timestamps = pd.to_numeric(open_orders.loc[active, column], errors="coerce")
            if timestamps.notna().any():
                ages = (float(snapshot_ts_ns) - timestamps).clip(lower=0.0)
                return float(ages.max(skipna=True))
    return np.nan


def _active_open_order_mask(open_orders: pd.DataFrame) -> pd.Series:
    status = open_orders["status"].astype(str).str.lower() if "status" in open_orders.columns else pd.Series(["open"] * len(open_orders), index=open_orders.index)
    terminal = {"filled", "cancelled", "canceled", "rejected", "expired", "complete", "closed"}
    return (~status.isin(terminal)) & (_open_quantities(open_orders) > 0)


def _open_quantities(open_orders: pd.DataFrame) -> pd.Series:
    for column in ("open_qty", "leaves_qty", "remaining_qty"):
        if column in open_orders.columns:
            return pd.to_numeric(open_orders[column], errors="coerce").fillna(0.0)
    qty = _order_quantities(open_orders)
    filled = pd.to_numeric(open_orders["filled_qty"], errors="coerce").fillna(0.0) if "filled_qty" in open_orders.columns else pd.Series([0.0] * len(open_orders))
    return (qty - filled).clip(lower=0.0)


def _order_quantities(open_orders: pd.DataFrame) -> pd.Series:
    for column in ("qty", "order_qty", "quantity"):
        if column in open_orders.columns:
            return pd.to_numeric(open_orders[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(open_orders), index=open_orders.index)


def _open_order_prices(open_orders: pd.DataFrame) -> pd.Series:
    for column in ("limit_price", "order_price", "price", "last", "ltp"):
        if column in open_orders.columns:
            return pd.to_numeric(open_orders[column], errors="coerce").fillna(0.0)
    side = open_orders["side"].map(_side_sign) if "side" in open_orders.columns else pd.Series([0] * len(open_orders), index=open_orders.index)
    for bid_col, ask_col in (
        ("market_bid", "market_ask"),
        ("bid", "ask"),
        ("best_bid", "best_ask"),
    ):
        if bid_col in open_orders.columns and ask_col in open_orders.columns:
            bid = pd.to_numeric(open_orders[bid_col], errors="coerce")
            ask = pd.to_numeric(open_orders[ask_col], errors="coerce")
            mid = (bid + ask) / 2.0
            return pd.Series(np.where(side > 0, ask, np.where(side < 0, bid, mid)), index=open_orders.index).fillna(0.0)
    return pd.Series([0.0] * len(open_orders), index=open_orders.index)


def _side_sign(value: object) -> int:
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"buy", "b", "long", "1"}:
            return 1
        if text in {"sell", "s", "short", "-1"}:
            return -1
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number > 0:
        return 1
    if number < 0:
        return -1
    return 0


def _gross_position_qty(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    return float(_position_quantities(positions).abs().sum())


def _abs_net_position_qty(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    return float(abs(_position_quantities(positions).sum()))


def _gross_position_notional(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    for column in ("gross_notional", "gross_position_notional"):
        if column in positions.columns:
            return float(pd.to_numeric(positions[column], errors="coerce").fillna(0.0).abs().sum())
    for column in ("signed_notional", "net_notional", "position_notional", "notional"):
        if column in positions.columns:
            return float(pd.to_numeric(positions[column], errors="coerce").fillna(0.0).abs().sum())
    prices = _position_prices(positions)
    return float((_position_quantities(positions).abs() * prices.abs()).sum())


def _net_position_notional(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    for column in ("signed_notional", "net_notional", "position_notional"):
        if column in positions.columns:
            return float(pd.to_numeric(positions[column], errors="coerce").fillna(0.0).sum())
    prices = _position_prices(positions)
    return float((_position_quantities(positions) * prices).sum())


def _position_quantities(positions: pd.DataFrame) -> pd.Series:
    for column in ("net_qty", "position", "qty"):
        if column in positions.columns:
            return pd.to_numeric(positions[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(positions))


def _net_greek_exposure(positions: pd.DataFrame, greek: str) -> float:
    if positions.empty:
        return 0.0
    total_columns = (
        f"signed_{greek}",
        f"net_{greek}",
        f"position_{greek}",
        f"{greek}_exposure",
    )
    for column in total_columns:
        if column in positions.columns:
            return float(pd.to_numeric(positions[column], errors="coerce").fillna(0.0).sum())
    unit_column = _first_existing_column(positions, (f"unit_{greek}", greek))
    if unit_column is None:
        return 0.0
    return float((_position_quantities(positions) * pd.to_numeric(positions[unit_column], errors="coerce").fillna(0.0)).sum())


def _first_existing_column(frame: pd.DataFrame, columns: tuple[str, ...]) -> str | None:
    return next((column for column in columns if column in frame.columns), None)


def _position_prices(positions: pd.DataFrame) -> pd.Series:
    for column in ("mark_price", "mid_price", "mid", "last", "ltp", "price"):
        if column in positions.columns:
            return pd.to_numeric(positions[column], errors="coerce").fillna(0.0)
    for bid_col, ask_col in (
        ("market_bid", "market_ask"),
        ("bid", "ask"),
        ("best_bid", "best_ask"),
    ):
        if bid_col in positions.columns and ask_col in positions.columns:
            bid = pd.to_numeric(positions[bid_col], errors="coerce")
            ask = pd.to_numeric(positions[ask_col], errors="coerce")
            return ((bid + ask) / 2.0).fillna(0.0)
    return pd.Series([0.0] * len(positions))


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


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
