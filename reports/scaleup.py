from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


LAUNCH_PIPELINE_SUMMARIES: tuple[tuple[str, str], ...] = (
    ("leadlag", "leadlag_launch_pipeline_summary.csv"),
    ("imbalance", "imbalance_launch_pipeline_summary.csv"),
    ("parity", "parity_launch_pipeline_summary.csv"),
    ("settlement", "settlement_launch_pipeline_summary.csv"),
    ("surface_mm", "surface_mm_launch_pipeline_summary.csv"),
)


@dataclass(frozen=True)
class ScaleUpThresholds:
    target_mode: str = "shadow"
    max_scale_multiplier: float = 1.0
    min_shadow_sessions: int = 1
    min_shadow_acceptance_rate: float = 1.0
    min_median_order_fill_rate: float = 0.0
    min_worst_order_fill_rate: float | None = None
    max_worst_adverse_slippage: float | None = None
    max_total_failed_component_checks: int = 0
    max_total_unmatched_fills: int = 0
    max_total_mismatched_orders: int = 0
    max_total_overfilled_orders: int = 0
    max_telemetry_age_ns: float | None = None
    max_lifecycle_orders: int | None = None
    max_replace_orders: int | None = None
    max_open_order_count: int | None = None
    max_open_order_qty: float | None = None
    max_open_order_notional: float | None = None
    max_open_order_age_ns: float | None = None
    max_gross_position_qty: float | None = None
    max_abs_net_position_qty: float | None = None
    max_orders_per_session: int | None = None
    max_session_notional: float | None = None
    max_gross_notional: float | None = None
    max_abs_net_delta: float | None = None
    max_abs_net_vega: float | None = None
    stop_loss: float | None = None
    allowed_adapters: tuple[str, ...] = ()
    require_proof_refresh: bool = False
    require_instrument_metadata: bool = False
    require_data_readiness: bool = False
    require_data_readiness_comparison: bool = False
    require_broker_readiness: bool = False
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    min_instrument_parse_coverage: float = 1.0
    expected_strategy: str | None = None
    expected_market: str | None = None


@dataclass(frozen=True)
class ScaleUpPlanReport:
    plan: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_scaleup_plan(
    *,
    evidence_summary: pd.DataFrame,
    shadow_comparison_summary: pd.DataFrame,
    launch_summary: pd.DataFrame,
    order_exposure_summary: pd.DataFrame | None = None,
    proof_refresh_summary: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    data_readiness_summary: pd.DataFrame | None = None,
    data_readiness_comparison_summary: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    thresholds = thresholds or ScaleUpThresholds()
    _validate_thresholds(thresholds)
    _require(evidence_summary, ["ready"], "strategy_evidence_summary")
    _require(shadow_comparison_summary, ["accepted", "session_count", "acceptance_rate"], "shadow_comparison_summary")
    _require(launch_summary, ["ready", "mode", "adapter", "scenario_key", "accepted_orders"], "launch_summary")
    exposure = order_exposure_summary if order_exposure_summary is not None else pd.DataFrame()
    proof_refresh = proof_refresh_summary if proof_refresh_summary is not None else pd.DataFrame()
    instrument_metadata = instrument_metadata_summary if instrument_metadata_summary is not None else pd.DataFrame()
    data_readiness = data_readiness_summary if data_readiness_summary is not None else pd.DataFrame()
    data_readiness_comparison = (
        data_readiness_comparison_summary if data_readiness_comparison_summary is not None else pd.DataFrame()
    )
    broker_readiness = broker_readiness_summary if broker_readiness_summary is not None else pd.DataFrame()

    rows = {
        "evidence": evidence_summary.iloc[0],
        "shadow": shadow_comparison_summary.iloc[0],
        "launch": launch_summary.iloc[0],
        "exposure": exposure.iloc[0] if not exposure.empty else pd.Series(dtype=object),
        "proof_refresh": proof_refresh.iloc[0] if not proof_refresh.empty else pd.Series(dtype=object),
        "instrument_metadata": instrument_metadata.iloc[0] if not instrument_metadata.empty else pd.Series(dtype=object),
        "data_readiness": data_readiness.iloc[0] if not data_readiness.empty else pd.Series(dtype=object),
        "data_readiness_comparison": data_readiness_comparison.iloc[0]
        if not data_readiness_comparison.empty
        else pd.Series(dtype=object),
        "broker_readiness": broker_readiness.iloc[0] if not broker_readiness.empty else pd.Series(dtype=object),
    }
    checks = _checks(rows, thresholds)
    ready = bool(checks["passed"].all()) if not checks.empty else False
    plan = _plan(rows, thresholds, ready)
    summary = _summary(plan.iloc[0], checks)
    config = _config(plan.iloc[0], checks, thresholds)
    return ScaleUpPlanReport(plan=plan, checks=checks, summary=summary, config=config)


def write_scaleup_plan(
    *,
    evidence_dir: str | Path,
    shadow_comparison_dir: str | Path,
    launch_dir: str | Path,
    output_dir: str | Path,
    order_exposure_dir: str | Path | None = None,
    proof_refresh_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    data_readiness_dir: str | Path | None = None,
    data_readiness_comparison_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    evidence_path = _summary_path(evidence_dir, "strategy_evidence_summary.csv")
    shadow_path = _summary_path(shadow_comparison_dir, "shadow_session_comparison_summary.csv")
    launch_path = _summary_path(launch_dir, "launch_summary.csv", fallback_dirs=("03_launch", "02_launch"))
    launch_pipeline_path = _launch_pipeline_summary_path(launch_dir)
    exposure_path = _optional_summary_input(order_exposure_dir, "order_exposure_summary.csv")
    proof_refresh_path = _optional_summary_input(proof_refresh_dir, "proof_refresh_summary.csv")
    instrument_metadata_path = _optional_summary_input(instrument_metadata_dir, "instrument_metadata_summary.csv")
    data_readiness_path = _optional_summary_input(data_readiness_dir, "data_readiness_summary.csv")
    data_readiness_comparison_path = _optional_summary_input(
        data_readiness_comparison_dir,
        "data_readiness_comparison_summary.csv",
    )

    evidence = _read_summary(evidence_path, "strategy_evidence_summary.csv")
    shadow = _read_summary(shadow_path, "shadow_session_comparison_summary.csv")
    launch = _read_summary(launch_path, "launch_summary.csv")
    launch = _with_launch_pipeline_identity(
        launch,
        _read_launch_pipeline_summary(launch_pipeline_path) if launch_pipeline_path is not None else None,
    )
    exposure = _read_optional_summary(exposure_path, "order_exposure_summary.csv") if exposure_path else None
    proof_refresh = (
        _read_optional_summary(proof_refresh_path, "proof_refresh_summary.csv") if proof_refresh_path else None
    )
    instrument_metadata = (
        _read_optional_summary(instrument_metadata_path, "instrument_metadata_summary.csv")
        if instrument_metadata_path
        else None
    )
    resolved_broker_readiness_dir = broker_readiness_dir or _auto_broker_readiness_dir(launch_dir)
    broker_readiness_path = _optional_summary_input(
        resolved_broker_readiness_dir,
        "broker_readiness_summary.csv",
    )
    broker_readiness = (
        _read_optional_summary(broker_readiness_path, "broker_readiness_summary.csv")
        if broker_readiness_path
        else None
    )
    data_readiness = (
        _read_optional_summary(data_readiness_path, "data_readiness_summary.csv")
        if data_readiness_path
        else None
    )
    data_readiness_comparison = (
        _read_optional_summary(data_readiness_comparison_path, "data_readiness_comparison_summary.csv")
        if data_readiness_comparison_path
        else None
    )
    thresholds = thresholds or ScaleUpThresholds()
    report = evaluate_scaleup_plan(
        evidence_summary=evidence,
        shadow_comparison_summary=shadow,
        launch_summary=launch,
        order_exposure_summary=exposure,
        proof_refresh_summary=proof_refresh,
        instrument_metadata_summary=instrument_metadata,
        data_readiness_summary=data_readiness,
        data_readiness_comparison_summary=data_readiness_comparison,
        broker_readiness_summary=broker_readiness,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.plan.to_csv(out / "scaleup_plan.csv", index=False)
    report.checks.to_csv(out / "scaleup_checks.csv", index=False)
    report.summary.to_csv(out / "scaleup_summary.csv", index=False)
    (out / "scaleup_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs: dict[str, Any] = {
        "evidence": evidence_path,
        "shadow_comparison": shadow_path,
        "launch": launch_path,
    }
    if launch_pipeline_path is not None:
        inputs["launch_pipeline"] = launch_pipeline_path
    if exposure_path is not None:
        inputs["order_exposure"] = exposure_path
    if proof_refresh_path is not None:
        inputs["proof_refresh"] = proof_refresh_path
    if instrument_metadata_path is not None:
        inputs["instrument_metadata"] = instrument_metadata_path
    if data_readiness_path is not None:
        inputs["data_readiness"] = data_readiness_path
    if data_readiness_comparison_path is not None:
        inputs["data_readiness_comparison"] = data_readiness_comparison_path
    if broker_readiness_path is not None:
        inputs["broker_readiness"] = broker_readiness_path
    write_experiment_manifest(
        out,
        run_type="scaleup_plan",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
    )
    return ScaleUpPlanReport(report.plan, report.checks, report.summary, report.config, out)


def _checks(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds) -> pd.DataFrame:
    evidence = rows["evidence"]
    shadow = rows["shadow"]
    launch = rows["launch"]
    exposure = rows["exposure"]
    proof_refresh = rows["proof_refresh"]
    instrument_metadata = rows["instrument_metadata"]
    data_readiness = rows["data_readiness"]
    data_readiness_comparison = rows["data_readiness_comparison"]
    broker_readiness = rows["broker_readiness"]
    adapter = str(launch.get("adapter", ""))
    scenario_match = str(launch.get("scenario_key", "")) == str(shadow.get("scenario_key", launch.get("scenario_key", "")))
    evidence_strategy = _strategy_key(evidence.get("strategy", ""))
    evidence_market = _identity_key(evidence.get("market", ""))
    expected_proof_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
    expected_proof_market = _identity_key(thresholds.expected_market) or evidence_market
    checks = [
        _check("evidence_ready", _to_bool(evidence.get("ready", False)), "is", True, _to_bool(evidence.get("ready", False)), "strategy evidence review is not ready"),
        _check("shadow_comparison_accepted", _to_bool(shadow.get("accepted", False)), "is", True, _to_bool(shadow.get("accepted", False)), "shadow comparison is not accepted"),
        _check("launch_ready", _to_bool(launch.get("ready", False)), "is", True, _to_bool(launch.get("ready", False)), "launch bundle is not ready"),
        _check("scenario_match", scenario_match, "is", True, scenario_match, "launch and shadow scenario keys differ"),
        _threshold_check("session_count", _number(shadow, "session_count"), ">=", thresholds.min_shadow_sessions),
        _threshold_check("acceptance_rate", _number(shadow, "acceptance_rate"), ">=", thresholds.min_shadow_acceptance_rate),
        _threshold_check("median_order_fill_rate", _number(shadow, "median_order_fill_rate"), ">=", thresholds.min_median_order_fill_rate),
        _threshold_check("total_failed_component_checks", _number(shadow, "total_failed_component_checks"), "<=", thresholds.max_total_failed_component_checks),
        _threshold_check("total_unmatched_fills", _number(shadow, "total_unmatched_fills"), "<=", thresholds.max_total_unmatched_fills),
        _threshold_check("total_mismatched_orders", _number(shadow, "total_mismatched_orders"), "<=", thresholds.max_total_mismatched_orders),
        _threshold_check("total_overfilled_orders", _number(shadow, "total_overfilled_orders"), "<=", thresholds.max_total_overfilled_orders),
    ]
    if thresholds.expected_strategy is not None:
        expected_strategy = _strategy_key(thresholds.expected_strategy)
        checks.append(
            _check(
                "evidence_strategy_matches",
                evidence_strategy,
                "==",
                expected_strategy,
                bool(evidence_strategy and evidence_strategy == expected_strategy),
                "strategy evidence identity does not match expected strategy",
            )
        )
    if thresholds.expected_market is not None:
        expected_market = _identity_key(thresholds.expected_market)
        checks.append(
            _check(
                "evidence_market_matches",
                evidence_market,
                "==",
                expected_market,
                bool(evidence_market and evidence_market == expected_market),
                "strategy evidence identity does not match expected market",
            )
        )
    if _to_bool(launch.get("launch_pipeline_provided", False)) and not _to_bool(
        launch.get("surface_launch_pipeline_provided", False)
    ):
        launch_pipeline_ready = _to_bool(launch.get("launch_pipeline_ready", False))
        launch_pipeline_strategy = _strategy_key(launch.get("launch_pipeline_strategy", ""))
        launch_pipeline_market = _identity_key(launch.get("launch_pipeline_market", ""))
        checks.append(
            _check(
                "launch_pipeline_ready",
                launch_pipeline_ready,
                "is",
                True,
                launch_pipeline_ready,
                "launch pipeline root summary is not ready",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "launch_pipeline_strategy_matches",
                    launch_pipeline_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(launch_pipeline_strategy and launch_pipeline_strategy == expected_proof_strategy),
                    "launch pipeline strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "launch_pipeline_market_matches",
                    launch_pipeline_market,
                    "==",
                    expected_proof_market,
                    bool(launch_pipeline_market and launch_pipeline_market == expected_proof_market),
                    "launch pipeline market does not match scale-up market",
                )
            )
    if _to_bool(launch.get("surface_launch_pipeline_provided", False)):
        surface_launch_ready = _to_bool(launch.get("surface_launch_pipeline_ready", False))
        surface_launch_strategy = _strategy_key(launch.get("surface_launch_strategy", ""))
        surface_launch_market = _identity_key(launch.get("surface_launch_market", ""))
        checks.append(
            _check(
                "surface_launch_pipeline_ready",
                surface_launch_ready,
                "is",
                True,
                surface_launch_ready,
                "surface launch pipeline root summary is not ready",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "surface_launch_strategy_matches",
                    surface_launch_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(surface_launch_strategy and surface_launch_strategy == expected_proof_strategy),
                    "surface launch pipeline strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "surface_launch_market_matches",
                    surface_launch_market,
                    "==",
                    expected_proof_market,
                    bool(surface_launch_market and surface_launch_market == expected_proof_market),
                    "surface launch pipeline market does not match scale-up market",
                )
            )
    if thresholds.allowed_adapters:
        checks.append(
            _check(
                "adapter_allowed",
                adapter,
                "in",
                ";".join(thresholds.allowed_adapters),
                adapter in thresholds.allowed_adapters,
                "launch adapter is not in allowed adapter list",
            )
        )
    if thresholds.min_worst_order_fill_rate is not None:
        checks.append(_threshold_check("worst_order_fill_rate", _number(shadow, "worst_order_fill_rate"), ">=", thresholds.min_worst_order_fill_rate))
    if thresholds.max_worst_adverse_slippage is not None:
        checks.append(_threshold_check("worst_adverse_slippage", _number(shadow, "worst_adverse_slippage"), "<=", thresholds.max_worst_adverse_slippage))
    if thresholds.max_orders_per_session is not None:
        checks.append(_threshold_check("accepted_orders", _number(launch, "accepted_orders"), "<=", thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        checks.append(_threshold_check("launch_total_notional", _number(launch, "total_notional"), "<=", thresholds.max_session_notional))
    shadow_proof_sessions = int(_number(shadow, "runtime_proof_refresh_sessions", fallback=0.0))
    if shadow_proof_sessions > 0:
        shadow_proof_strategy = _strategy_key(shadow.get("proof_refresh_strategy", ""))
        shadow_proof_market = _identity_key(shadow.get("proof_refresh_market", ""))
        checks.extend(
            [
                _check(
                    "shadow_proof_refresh_ready",
                    int(_number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_proof_sessions,
                    int(_number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0))
                    == shadow_proof_sessions,
                    "not every accepted shadow runtime proof-refresh evidence item is ready",
                ),
                _check(
                    "shadow_proof_refresh_identity_consistent",
                    int(_number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)),
                    "==",
                    0,
                    int(_number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)) == 0,
                    "shadow comparison reported mixed proof-refresh identity",
                ),
            ]
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "shadow_proof_refresh_strategy_matches",
                    shadow_proof_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(shadow_proof_strategy and shadow_proof_strategy == expected_proof_strategy),
                    "shadow proof-refresh strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "shadow_proof_refresh_market_matches",
                    shadow_proof_market,
                    "==",
                    expected_proof_market,
                    bool(shadow_proof_market and shadow_proof_market == expected_proof_market),
                    "shadow proof-refresh market does not match scale-up market",
                )
            )
    if not exposure.empty:
        checks.append(_check("order_exposure_passed", _to_bool(exposure.get("passed", False)), "is", True, _to_bool(exposure.get("passed", False)), "order exposure report did not pass"))
        if thresholds.max_gross_notional is not None:
            checks.append(_threshold_check("gross_notional", _number(exposure, "gross_notional"), "<=", thresholds.max_gross_notional))
        if thresholds.max_abs_net_delta is not None:
            checks.append(_threshold_check("abs_net_delta", abs(_number(exposure, "net_delta")), "<=", thresholds.max_abs_net_delta))
        if thresholds.max_abs_net_vega is not None:
            checks.append(_threshold_check("abs_net_vega", abs(_number(exposure, "net_vega")), "<=", thresholds.max_abs_net_vega))
    if thresholds.require_proof_refresh:
        checks.append(
            _check(
                "proof_refresh_available",
                not proof_refresh.empty,
                "is",
                True,
                not proof_refresh.empty,
                "proof refresh gate is required but no proof refresh summary was supplied",
            )
        )
    if not proof_refresh.empty:
        proof_refresh_ready = _to_bool(proof_refresh.get("ready", False))
        proof_refresh_strategy = _strategy_key(proof_refresh.get("strategy", ""))
        proof_refresh_market = _identity_key(proof_refresh.get("market", ""))
        proof_refresh_mixed_identity = _to_bool(proof_refresh.get("mixed_identity", False))
        checks.append(
            _check(
                "proof_refresh_ready",
                proof_refresh_ready,
                "is",
                True,
                proof_refresh_ready,
                "proof refresh gate is not ready",
            )
        )
        checks.append(
            _check(
                "proof_refresh_identity_consistent",
                proof_refresh_mixed_identity,
                "is",
                False,
                not proof_refresh_mixed_identity,
                "proof refresh gate reported mixed strategy or market identity",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "proof_refresh_strategy_matches",
                    proof_refresh_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(proof_refresh_strategy and proof_refresh_strategy == expected_proof_strategy),
                    "proof refresh strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "proof_refresh_market_matches",
                    proof_refresh_market,
                    "==",
                    expected_proof_market,
                    bool(proof_refresh_market and proof_refresh_market == expected_proof_market),
                    "proof refresh market does not match scale-up market",
                )
            )
    if thresholds.require_instrument_metadata:
        checks.append(
            _check(
                "instrument_metadata_available",
                not instrument_metadata.empty,
                "is",
                True,
                not instrument_metadata.empty,
                "instrument metadata report is required but no summary was supplied",
            )
        )
    if not instrument_metadata.empty:
        metadata_passed = _to_bool(instrument_metadata.get("passed", False))
        parse_coverage = _number(instrument_metadata, "parse_coverage", fallback=0.0)
        checks.append(
            _check(
                "instrument_metadata_passed",
                metadata_passed,
                "is",
                True,
                metadata_passed,
                "instrument metadata report did not pass",
            )
        )
        checks.append(
            _threshold_check(
                "instrument_parse_coverage",
                parse_coverage,
                ">=",
                thresholds.min_instrument_parse_coverage,
            )
        )
    if thresholds.require_data_readiness:
        checks.append(
            _check(
                "data_readiness_available",
                not data_readiness.empty,
                "is",
                True,
                not data_readiness.empty,
                "data readiness review is required but no summary was supplied",
            )
        )
    if not data_readiness.empty:
        data_ready = _to_bool(data_readiness.get("ready", False))
        checks.append(
            _check(
                "data_readiness_ready",
                data_ready,
                "is",
                True,
                data_ready,
                "data readiness review is not ready",
            )
        )
    if thresholds.require_data_readiness_comparison:
        checks.append(
            _check(
                "data_readiness_comparison_available",
                not data_readiness_comparison.empty,
                "is",
                True,
                not data_readiness_comparison.empty,
                "data readiness comparison is required but no summary was supplied",
            )
        )
    if not data_readiness_comparison.empty:
        data_comparison_accepted = _to_bool(data_readiness_comparison.get("accepted", False))
        checks.append(
            _check(
                "data_readiness_comparison_accepted",
                data_comparison_accepted,
                "is",
                True,
                data_comparison_accepted,
                "data readiness comparison is not accepted",
            )
        )
    broker_readiness_required = _broker_readiness_required(thresholds)
    if broker_readiness_required:
        checks.append(
            _check(
                "broker_readiness_available",
                not broker_readiness.empty,
                "is",
                True,
                not broker_readiness.empty,
                "broker readiness review is required but no summary was supplied",
            )
        )
    if not broker_readiness.empty:
        broker_ready = _to_bool(broker_readiness.get("ready", False))
        checks.append(
            _check(
                "broker_readiness_ready",
                broker_ready,
                "is",
                True,
                broker_ready,
                "broker readiness review is not ready",
            )
        )
    resume_gate_provided = _to_bool(broker_readiness.get("resume_gate_provided", False))
    if thresholds.require_resume_gate:
        checks.append(
            _check(
                "broker_resume_gate_provided",
                resume_gate_provided,
                "is",
                True,
                resume_gate_provided,
                "scale-up requires broker readiness with resume-gate authorization",
            )
        )
    if not broker_readiness.empty and (thresholds.require_resume_gate or resume_gate_provided):
        resume_gate_ready = _to_bool(broker_readiness.get("resume_gate_ready", False))
        resume_strategy = _strategy_key(broker_readiness.get("resume_strategy", ""))
        resume_market = _identity_key(broker_readiness.get("resume_market", ""))
        resume_proof_ready = _to_bool(broker_readiness.get("resume_proof_refresh_ready", False))
        resume_proof_strategy = _strategy_key(broker_readiness.get("resume_proof_refresh_strategy", ""))
        resume_proof_market = _identity_key(broker_readiness.get("resume_proof_refresh_market", ""))
        expected_resume_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_resume_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.extend(
            [
                _check(
                    "broker_resume_gate_ready",
                    resume_gate_ready,
                    "is",
                    True,
                    resume_gate_ready,
                    "broker resume gate is not ready",
                ),
                _check(
                    "broker_resume_strategy_matches",
                    resume_strategy,
                    "==",
                    expected_resume_strategy,
                    bool(resume_strategy and expected_resume_strategy and resume_strategy == expected_resume_strategy),
                    "broker resume-gate strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_resume_market_matches",
                    resume_market,
                    "==",
                    expected_resume_market,
                    bool(resume_market and expected_resume_market and resume_market == expected_resume_market),
                    "broker resume-gate market does not match scale-up market",
                ),
                _check(
                    "broker_resume_proof_refresh_ready",
                    resume_proof_ready,
                    "is",
                    True,
                    resume_proof_ready,
                    "broker resume-gate proof freshness is not ready",
                ),
                _check(
                    "broker_resume_proof_refresh_strategy_matches",
                    resume_proof_strategy,
                    "==",
                    expected_resume_strategy,
                    bool(
                        resume_proof_strategy
                        and expected_resume_strategy
                        and resume_proof_strategy == expected_resume_strategy
                    ),
                    "broker resume-gate proof strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_resume_proof_refresh_market_matches",
                    resume_proof_market,
                    "==",
                    expected_resume_market,
                    bool(resume_proof_market and expected_resume_market and resume_proof_market == expected_resume_market),
                    "broker resume-gate proof market does not match scale-up market",
                ),
            ]
        )
    dispatch_roundtrip_required = _dispatch_roundtrip_required(thresholds)
    dispatch_roundtrip_provided = _to_bool(broker_readiness.get("dispatch_roundtrip_provided", False))
    route_dispatch_roundtrip_required = _route_dispatch_roundtrip_required(thresholds, broker_readiness)
    route_dispatch_roundtrip_provided = _to_bool(
        broker_readiness.get("route_dispatch_roundtrip_provided", False)
    )
    if dispatch_roundtrip_required:
        checks.append(
            _check(
                "broker_dispatch_roundtrip_provided",
                dispatch_roundtrip_provided,
                "is",
                True,
                dispatch_roundtrip_provided,
                "scale-up requires broker readiness with dry-run dispatch round-trip proof",
            )
        )
    if route_dispatch_roundtrip_required:
        checks.append(
            _check(
                "broker_route_dispatch_roundtrip_provided",
                route_dispatch_roundtrip_provided,
                "is",
                True,
                route_dispatch_roundtrip_provided,
                "scale-up requires broker readiness with dispatch route proof",
            )
        )
    if not broker_readiness.empty and (dispatch_roundtrip_required or dispatch_roundtrip_provided):
        dispatch_roundtrip_ready = _to_bool(broker_readiness.get("dispatch_roundtrip_ready", False))
        dispatch_roundtrip_target_mode = _identity_key(broker_readiness.get("dispatch_roundtrip_target_mode", ""))
        dispatch_roundtrip_strategy = _strategy_key(broker_readiness.get("dispatch_roundtrip_strategy", ""))
        dispatch_roundtrip_market = _identity_key(broker_readiness.get("dispatch_roundtrip_market", ""))
        dispatch_roundtrip_scenario = str(broker_readiness.get("dispatch_roundtrip_scenario_key", "")).strip()
        expected_dispatch_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_dispatch_market = _identity_key(thresholds.expected_market) or evidence_market
        launch_scenario = str(launch.get("scenario_key", "")).strip()
        checks.extend(
            [
                _check(
                    "broker_dispatch_roundtrip_ready",
                    dispatch_roundtrip_ready,
                    "is",
                    True,
                    dispatch_roundtrip_ready,
                    "broker dry-run dispatch round-trip proof is not ready",
                ),
                _check(
                    "broker_dispatch_roundtrip_target_mode_matches",
                    dispatch_roundtrip_target_mode,
                    "==",
                    thresholds.target_mode,
                    bool(dispatch_roundtrip_target_mode and dispatch_roundtrip_target_mode == thresholds.target_mode),
                    "broker dispatch round-trip target mode does not match scale-up target",
                ),
                _check(
                    "broker_dispatch_roundtrip_strategy_matches",
                    dispatch_roundtrip_strategy,
                    "==",
                    expected_dispatch_strategy,
                    bool(
                        dispatch_roundtrip_strategy
                        and expected_dispatch_strategy
                        and dispatch_roundtrip_strategy == expected_dispatch_strategy
                    ),
                    "broker dispatch round-trip strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_dispatch_roundtrip_market_matches",
                    dispatch_roundtrip_market,
                    "==",
                    expected_dispatch_market,
                    bool(
                        dispatch_roundtrip_market
                        and expected_dispatch_market
                        and dispatch_roundtrip_market == expected_dispatch_market
                    ),
                    "broker dispatch round-trip market does not match scale-up market",
                ),
                _check(
                    "broker_dispatch_roundtrip_scenario_matches",
                    dispatch_roundtrip_scenario,
                    "==",
                    launch_scenario,
                    bool(dispatch_roundtrip_scenario and launch_scenario and dispatch_roundtrip_scenario == launch_scenario),
                    "broker dispatch round-trip scenario does not match launch scenario",
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_missing_request_acks",
                    _number(broker_readiness, "dispatch_roundtrip_missing_request_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_rejected_orders",
                    _number(broker_readiness, "dispatch_roundtrip_rejected_orders", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_unmatched_acks",
                    _number(broker_readiness, "dispatch_roundtrip_unmatched_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_failed_checks",
                    _number(broker_readiness, "dispatch_roundtrip_failed_checks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_enable_dispatch_roundtrip_failed_checks",
                    _number(broker_readiness, "route_enable_dispatch_roundtrip_failed_checks", 0.0),
                    "<=",
                    0,
                ),
            ]
        )
    if not broker_readiness.empty and (
        dispatch_roundtrip_required or dispatch_roundtrip_provided or route_dispatch_roundtrip_provided
    ):
        route_dispatch_roundtrip_ready = _to_bool(broker_readiness.get("route_dispatch_roundtrip_ready", False))
        route_dispatch_roundtrip_target_mode = _identity_key(
            broker_readiness.get("route_dispatch_roundtrip_target_mode", "")
        )
        route_dispatch_roundtrip_strategy = _strategy_key(
            broker_readiness.get("route_dispatch_roundtrip_strategy", "")
        )
        route_dispatch_roundtrip_market = _identity_key(
            broker_readiness.get("route_dispatch_roundtrip_market", "")
        )
        route_dispatch_roundtrip_scenario = str(
            broker_readiness.get("route_dispatch_roundtrip_scenario_key", "")
        ).strip()
        route_dispatch_roundtrip_batch_id = str(
            broker_readiness.get("route_dispatch_roundtrip_batch_id", "")
        ).strip()
        route_dispatch_roundtrip_requests = int(
            _number(broker_readiness, "route_dispatch_roundtrip_requests", 0.0)
        )
        route_dispatch_roundtrip_acked_orders = int(
            _number(broker_readiness, "route_dispatch_roundtrip_acked_orders", 0.0)
        )
        dispatch_roundtrip_requests = int(_number(broker_readiness, "dispatch_roundtrip_requests", 0.0))
        dispatch_roundtrip_acked_orders = int(
            _number(broker_readiness, "dispatch_roundtrip_acked_orders", 0.0)
        )
        expected_dispatch_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_dispatch_market = _identity_key(thresholds.expected_market) or evidence_market
        launch_scenario = str(launch.get("scenario_key", "")).strip()
        checks.extend(
            [
                _check(
                    "broker_route_dispatch_roundtrip_ready",
                    route_dispatch_roundtrip_ready,
                    "is",
                    True,
                    route_dispatch_roundtrip_ready,
                    "broker dispatch route proof is not ready",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_target_mode_matches",
                    route_dispatch_roundtrip_target_mode,
                    "==",
                    thresholds.target_mode,
                    bool(
                        route_dispatch_roundtrip_target_mode
                        and route_dispatch_roundtrip_target_mode == thresholds.target_mode
                    ),
                    "broker dispatch route proof target mode does not match scale-up target",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_strategy_matches",
                    route_dispatch_roundtrip_strategy,
                    "==",
                    expected_dispatch_strategy,
                    bool(
                        route_dispatch_roundtrip_strategy
                        and expected_dispatch_strategy
                        and route_dispatch_roundtrip_strategy == expected_dispatch_strategy
                    ),
                    "broker dispatch route proof strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_market_matches",
                    route_dispatch_roundtrip_market,
                    "==",
                    expected_dispatch_market,
                    bool(
                        route_dispatch_roundtrip_market
                        and expected_dispatch_market
                        and route_dispatch_roundtrip_market == expected_dispatch_market
                    ),
                    "broker dispatch route proof market does not match scale-up market",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_scenario_matches",
                    route_dispatch_roundtrip_scenario,
                    "==",
                    launch_scenario,
                    bool(
                        route_dispatch_roundtrip_scenario
                        and launch_scenario
                        and route_dispatch_roundtrip_scenario == launch_scenario
                    ),
                    "broker dispatch route proof scenario does not match launch scenario",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_batch_id_provided",
                    route_dispatch_roundtrip_batch_id,
                    "is not",
                    "",
                    bool(route_dispatch_roundtrip_batch_id),
                    "broker dispatch route proof batch id is missing",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_request_count_matches",
                    f"{route_dispatch_roundtrip_requests}/{route_dispatch_roundtrip_acked_orders}",
                    "==",
                    f"{dispatch_roundtrip_requests}/{dispatch_roundtrip_acked_orders}",
                    (
                        route_dispatch_roundtrip_requests == dispatch_roundtrip_requests
                        and route_dispatch_roundtrip_acked_orders == dispatch_roundtrip_acked_orders
                    ),
                    "broker dispatch route proof request/ack counts do not match dispatch round-trip counts",
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_missing_request_acks",
                    _number(broker_readiness, "route_dispatch_roundtrip_missing_request_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_rejected_orders",
                    _number(broker_readiness, "route_dispatch_roundtrip_rejected_orders", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_unmatched_acks",
                    _number(broker_readiness, "route_dispatch_roundtrip_unmatched_acks", 0.0),
                    "<=",
                    0,
                ),
            ]
        )
    if thresholds.target_mode == "live_dryrun":
        runtime_session_provided = _to_bool(broker_readiness.get("runtime_session_provided", False))
        runtime_session_ready = _to_bool(broker_readiness.get("runtime_session_ready", False))
        runtime_guard_action = str(broker_readiness.get("runtime_guard_action", "")).strip().lower()
        runtime_guard_halted = _to_bool(broker_readiness.get("runtime_guard_halted", False))
        runtime_strategy = _strategy_key(broker_readiness.get("runtime_strategy", ""))
        runtime_market = _identity_key(broker_readiness.get("runtime_market", ""))
        expected_runtime_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_runtime_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.extend(
            [
                _check(
                    "broker_runtime_session_provided",
                    runtime_session_provided,
                    "is",
                    True,
                    runtime_session_provided,
                    "live_dryrun scale-up requires broker readiness with runtime-session evidence",
                ),
                _check(
                    "broker_runtime_session_ready",
                    runtime_session_ready,
                    "is",
                    True,
                    runtime_session_ready,
                    "broker runtime session is not ready",
                ),
                _check(
                    "broker_runtime_guard_continue",
                    runtime_guard_action or ("halt" if runtime_guard_halted else ""),
                    "==",
                    "continue",
                    runtime_guard_action == "continue" and not runtime_guard_halted,
                    "broker runtime session guard is not continuing",
                ),
                _check(
                    "broker_runtime_strategy_matches",
                    runtime_strategy,
                    "==",
                    expected_runtime_strategy,
                    bool(runtime_strategy and expected_runtime_strategy and runtime_strategy == expected_runtime_strategy),
                    "broker runtime-session strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_runtime_market_matches",
                    runtime_market,
                    "==",
                    expected_runtime_market,
                    bool(runtime_market and expected_runtime_market and runtime_market == expected_runtime_market),
                    "broker runtime-session market does not match scale-up market",
                ),
            ]
        )
    return pd.DataFrame(checks)


def _plan(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds, ready: bool) -> pd.DataFrame:
    evidence = rows["evidence"]
    launch = rows["launch"]
    shadow = rows["shadow"]
    proof_refresh = rows["proof_refresh"]
    instrument_metadata = rows["instrument_metadata"]
    data_readiness = rows["data_readiness"]
    data_readiness_comparison = rows["data_readiness_comparison"]
    broker_readiness = rows["broker_readiness"]
    accepted_orders = int(_number(launch, "accepted_orders", fallback=0.0))
    launch_notional = _number(launch, "total_notional", fallback=0.0)
    scaled_orders = int(np.floor(accepted_orders * thresholds.max_scale_multiplier))
    scaled_notional = float(launch_notional * thresholds.max_scale_multiplier)
    if thresholds.max_orders_per_session is not None:
        scaled_orders = min(scaled_orders, int(thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        scaled_notional = min(scaled_notional, float(thresholds.max_session_notional))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": thresholds.target_mode,
                "strategy": _strategy_key(evidence.get("strategy", "")),
                "market": _identity_key(evidence.get("market", "")),
                "expected_strategy": _strategy_key(thresholds.expected_strategy),
                "expected_market": _identity_key(thresholds.expected_market),
                "scenario_key": str(launch.get("scenario_key", "")),
                "adapter": str(launch.get("adapter", "")),
                "source_launch_mode": str(launch.get("mode", "")),
                "launch_pipeline_provided": _to_bool(launch.get("launch_pipeline_provided", False)),
                "launch_pipeline_family": str(launch.get("launch_pipeline_family", "")),
                "launch_pipeline_summary_file": str(launch.get("launch_pipeline_summary_file", "")),
                "launch_pipeline_ready": _to_bool(launch.get("launch_pipeline_ready", False)),
                "launch_pipeline_strategy": _strategy_key(launch.get("launch_pipeline_strategy", "")),
                "launch_pipeline_market": _identity_key(launch.get("launch_pipeline_market", "")),
                "launch_pipeline_expected_strategy": _strategy_key(
                    launch.get("launch_pipeline_expected_strategy", "")
                ),
                "launch_pipeline_expected_market": _identity_key(
                    launch.get("launch_pipeline_expected_market", "")
                ),
                "launch_pipeline_failed_components": int(
                    _number(launch, "launch_pipeline_failed_components", fallback=0.0)
                ),
                "launch_pipeline_skipped_components": int(
                    _number(launch, "launch_pipeline_skipped_components", fallback=0.0)
                ),
                "surface_launch_pipeline_provided": _to_bool(
                    launch.get("surface_launch_pipeline_provided", False)
                ),
                "surface_launch_pipeline_ready": _to_bool(launch.get("surface_launch_pipeline_ready", False)),
                "surface_launch_strategy": _strategy_key(launch.get("surface_launch_strategy", "")),
                "surface_launch_market": _identity_key(launch.get("surface_launch_market", "")),
                "surface_launch_expected_strategy": _strategy_key(
                    launch.get("surface_launch_expected_strategy", "")
                ),
                "surface_launch_expected_market": _identity_key(launch.get("surface_launch_expected_market", "")),
                "surface_launch_failed_components": int(
                    _number(launch, "surface_launch_failed_components", fallback=0.0)
                ),
                "surface_launch_skipped_components": int(
                    _number(launch, "surface_launch_skipped_components", fallback=0.0)
                ),
                "max_scale_multiplier": float(thresholds.max_scale_multiplier),
                "max_orders_per_session": scaled_orders,
                "max_notional_per_session": scaled_notional,
                "stop_loss": _jsonable(thresholds.stop_loss),
                "min_required_shadow_sessions": int(thresholds.min_shadow_sessions),
                "observed_shadow_sessions": int(_number(shadow, "session_count", fallback=0.0)),
                "observed_acceptance_rate": _number(shadow, "acceptance_rate"),
                "observed_median_fill_rate": _number(shadow, "median_order_fill_rate"),
                "observed_worst_fill_rate": _number(shadow, "worst_order_fill_rate"),
                "observed_worst_adverse_slippage": _number(shadow, "worst_adverse_slippage"),
                "shadow_proof_refresh_sessions": int(
                    _number(shadow, "runtime_proof_refresh_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_ready_sessions": int(
                    _number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_mixed_identity_sessions": int(
                    _number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_strategy": _strategy_key(shadow.get("proof_refresh_strategy", "")),
                "shadow_proof_refresh_market": _identity_key(shadow.get("proof_refresh_market", "")),
                "proof_refresh_provided": not proof_refresh.empty,
                "proof_refresh_ready": _to_bool(proof_refresh.get("ready", False)) if not proof_refresh.empty else False,
                "proof_refresh_strategy": _strategy_key(proof_refresh.get("strategy", ""))
                if not proof_refresh.empty
                else "",
                "proof_refresh_market": _identity_key(proof_refresh.get("market", ""))
                if not proof_refresh.empty
                else "",
                "proof_refresh_mixed_identity": _to_bool(proof_refresh.get("mixed_identity", False))
                if not proof_refresh.empty
                else False,
                "proof_source": str(proof_refresh.get("proof_source", "")) if not proof_refresh.empty else "",
                "fresh_proof_required": _to_bool(proof_refresh.get("fresh_proof_required", False))
                if not proof_refresh.empty
                else False,
                "proof_refresh_recommendation": str(proof_refresh.get("recommendation", ""))
                if not proof_refresh.empty
                else "",
                "instrument_metadata_provided": not instrument_metadata.empty,
                "instrument_metadata_passed": _to_bool(instrument_metadata.get("passed", False))
                if not instrument_metadata.empty
                else False,
                "instrument_parse_coverage": _number(instrument_metadata, "parse_coverage", fallback=np.nan)
                if not instrument_metadata.empty
                else np.nan,
                "unparsed_instruments": int(_number(instrument_metadata, "unparsed_instruments", fallback=0.0))
                if not instrument_metadata.empty
                else 0,
                "data_readiness_provided": not data_readiness.empty,
                "data_readiness_ready": _to_bool(data_readiness.get("ready", False))
                if not data_readiness.empty
                else False,
                "data_readiness_failed_checks": int(_number(data_readiness, "failed_checks", fallback=0.0))
                if not data_readiness.empty
                else 0,
                "data_readiness_recommendation": str(data_readiness.get("recommendation", ""))
                if not data_readiness.empty
                else "",
                "data_readiness_comparison_provided": not data_readiness_comparison.empty,
                "data_readiness_comparison_accepted": _to_bool(data_readiness_comparison.get("accepted", False))
                if not data_readiness_comparison.empty
                else False,
                "data_readiness_comparison_dataset_count": int(
                    _number(data_readiness_comparison, "dataset_count", fallback=0.0)
                )
                if not data_readiness_comparison.empty
                else 0,
                "data_readiness_comparison_ready_rate": _number(
                    data_readiness_comparison,
                    "ready_rate",
                    fallback=np.nan,
                )
                if not data_readiness_comparison.empty
                else np.nan,
                "data_readiness_comparison_failed_checks": int(
                    _number(
                        data_readiness_comparison,
                        "total_failed_checks",
                        fallback=_number(data_readiness_comparison, "failed_checks", fallback=0.0),
                    )
                )
                if not data_readiness_comparison.empty
                else 0,
                "data_readiness_comparison_recommendation": str(
                    data_readiness_comparison.get("recommendation", "")
                )
                if not data_readiness_comparison.empty
                else "",
                "broker_readiness_provided": not broker_readiness.empty,
                "broker_readiness_ready": _to_bool(broker_readiness.get("ready", False))
                if not broker_readiness.empty
                else False,
                "broker_schema_status": str(broker_readiness.get("adapter_schema_status", ""))
                if not broker_readiness.empty
                else "",
                "broker_schema_reviewed": _to_bool(broker_readiness.get("schema_reviewed", False))
                if not broker_readiness.empty
                else False,
                "broker_schema_review_mode": str(broker_readiness.get("schema_review_mode", ""))
                if not broker_readiness.empty
                else "",
                "broker_readiness_recommendation": str(broker_readiness.get("recommendation", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_session_required": thresholds.target_mode == "live_dryrun",
                "broker_runtime_session_provided": _to_bool(broker_readiness.get("runtime_session_provided", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_session_ready": _to_bool(broker_readiness.get("runtime_session_ready", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_guard_action": str(broker_readiness.get("runtime_guard_action", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_guard_halted": _to_bool(broker_readiness.get("runtime_guard_halted", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_target_mode": str(broker_readiness.get("runtime_target_mode", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_strategy": _strategy_key(broker_readiness.get("runtime_strategy", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_market": _identity_key(broker_readiness.get("runtime_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_gate_required": thresholds.require_resume_gate,
                "broker_resume_gate_provided": _to_bool(broker_readiness.get("resume_gate_provided", False))
                if not broker_readiness.empty
                else False,
                "broker_resume_gate_ready": _to_bool(broker_readiness.get("resume_gate_ready", False))
                if not broker_readiness.empty
                else False,
                "broker_resume_strategy": _strategy_key(broker_readiness.get("resume_strategy", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_market": _identity_key(broker_readiness.get("resume_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_incident_strategy": _strategy_key(
                    broker_readiness.get("resume_incident_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_resume_incident_market": _identity_key(broker_readiness.get("resume_incident_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_proof_refresh_ready": _to_bool(
                    broker_readiness.get("resume_proof_refresh_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_resume_proof_refresh_strategy": _strategy_key(
                    broker_readiness.get("resume_proof_refresh_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_resume_proof_refresh_market": _identity_key(
                    broker_readiness.get("resume_proof_refresh_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    broker_readiness.get("dispatch_roundtrip_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_dispatch_roundtrip_ready": _to_bool(
                    broker_readiness.get("dispatch_roundtrip_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_dispatch_roundtrip_target_mode": str(
                    broker_readiness.get("dispatch_roundtrip_target_mode", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_strategy": _strategy_key(
                    broker_readiness.get("dispatch_roundtrip_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_market": _identity_key(
                    broker_readiness.get("dispatch_roundtrip_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_scenario_key": str(
                    broker_readiness.get("dispatch_roundtrip_scenario_key", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_batch_id": str(
                    broker_readiness.get("dispatch_roundtrip_batch_id", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_requests": int(
                    _number(broker_readiness, "dispatch_roundtrip_requests", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_acked_orders": int(
                    _number(broker_readiness, "dispatch_roundtrip_acked_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(broker_readiness, "dispatch_roundtrip_missing_request_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_rejected_orders": int(
                    _number(broker_readiness, "dispatch_roundtrip_rejected_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(broker_readiness, "dispatch_roundtrip_unmatched_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_failed_checks": int(
                    _number(broker_readiness, "dispatch_roundtrip_failed_checks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(broker_readiness, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_required(
                    thresholds,
                    broker_readiness,
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    broker_readiness.get("route_dispatch_roundtrip_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    broker_readiness.get("route_dispatch_roundtrip_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_dispatch_roundtrip_target_mode": str(
                    broker_readiness.get("route_dispatch_roundtrip_target_mode", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_strategy": _strategy_key(
                    broker_readiness.get("route_dispatch_roundtrip_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_market": _identity_key(
                    broker_readiness.get("route_dispatch_roundtrip_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_scenario_key": str(
                    broker_readiness.get("route_dispatch_roundtrip_scenario_key", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_batch_id": str(
                    broker_readiness.get("route_dispatch_roundtrip_batch_id", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_requests": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_requests", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_acked_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_rejected_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
            }
        ]
    )


def _summary(plan_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(plan_row["ready"])
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(plan_row["target_mode"]),
                "strategy": str(plan_row["strategy"]),
                "market": str(plan_row["market"]),
                "expected_strategy": str(plan_row["expected_strategy"]),
                "expected_market": str(plan_row["expected_market"]),
                "scenario_key": str(plan_row["scenario_key"]),
                "adapter": str(plan_row["adapter"]),
                "launch_pipeline_provided": _to_bool(plan_row["launch_pipeline_provided"]),
                "launch_pipeline_family": str(plan_row["launch_pipeline_family"]),
                "launch_pipeline_ready": _to_bool(plan_row["launch_pipeline_ready"]),
                "launch_pipeline_strategy": str(plan_row["launch_pipeline_strategy"]),
                "launch_pipeline_market": str(plan_row["launch_pipeline_market"]),
                "surface_launch_pipeline_ready": _to_bool(plan_row["surface_launch_pipeline_ready"]),
                "surface_launch_strategy": str(plan_row["surface_launch_strategy"]),
                "surface_launch_market": str(plan_row["surface_launch_market"]),
                "max_orders_per_session": int(plan_row["max_orders_per_session"]),
                "max_notional_per_session": float(plan_row["max_notional_per_session"]),
                "proof_refresh_ready": _to_bool(plan_row["proof_refresh_ready"]),
                "proof_refresh_strategy": str(plan_row["proof_refresh_strategy"]),
                "proof_refresh_market": str(plan_row["proof_refresh_market"]),
                "proof_refresh_mixed_identity": _to_bool(plan_row["proof_refresh_mixed_identity"]),
                "shadow_proof_refresh_sessions": int(plan_row["shadow_proof_refresh_sessions"]),
                "shadow_proof_refresh_ready_sessions": int(plan_row["shadow_proof_refresh_ready_sessions"]),
                "shadow_proof_refresh_mixed_identity_sessions": int(
                    plan_row["shadow_proof_refresh_mixed_identity_sessions"]
                ),
                "shadow_proof_refresh_strategy": str(plan_row["shadow_proof_refresh_strategy"]),
                "shadow_proof_refresh_market": str(plan_row["shadow_proof_refresh_market"]),
                "proof_source": str(plan_row["proof_source"]),
                "instrument_metadata_passed": _to_bool(plan_row["instrument_metadata_passed"]),
                "instrument_parse_coverage": _jsonable(plan_row["instrument_parse_coverage"]),
                "data_readiness_ready": _to_bool(plan_row["data_readiness_ready"]),
                "data_readiness_comparison_accepted": _to_bool(
                    plan_row["data_readiness_comparison_accepted"]
                ),
                "data_readiness_comparison_dataset_count": int(
                    plan_row["data_readiness_comparison_dataset_count"]
                ),
                "data_readiness_comparison_ready_rate": _jsonable(
                    plan_row["data_readiness_comparison_ready_rate"]
                ),
                "broker_readiness_ready": _to_bool(plan_row["broker_readiness_ready"]),
                "broker_schema_status": str(plan_row["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(plan_row["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(plan_row["broker_schema_review_mode"]),
                "broker_runtime_session_required": _to_bool(plan_row["broker_runtime_session_required"]),
                "broker_runtime_session_provided": _to_bool(plan_row["broker_runtime_session_provided"]),
                "broker_runtime_session_ready": _to_bool(plan_row["broker_runtime_session_ready"]),
                "broker_runtime_guard_action": str(plan_row["broker_runtime_guard_action"]),
                "broker_runtime_guard_halted": _to_bool(plan_row["broker_runtime_guard_halted"]),
                "broker_runtime_target_mode": str(plan_row["broker_runtime_target_mode"]),
                "broker_runtime_strategy": str(plan_row["broker_runtime_strategy"]),
                "broker_runtime_market": str(plan_row["broker_runtime_market"]),
                "broker_resume_gate_required": _to_bool(plan_row["broker_resume_gate_required"]),
                "broker_resume_gate_provided": _to_bool(plan_row["broker_resume_gate_provided"]),
                "broker_resume_gate_ready": _to_bool(plan_row["broker_resume_gate_ready"]),
                "broker_resume_strategy": str(plan_row["broker_resume_strategy"]),
                "broker_resume_market": str(plan_row["broker_resume_market"]),
                "broker_resume_proof_refresh_ready": _to_bool(
                    plan_row["broker_resume_proof_refresh_ready"]
                ),
                "broker_resume_proof_refresh_strategy": str(
                    plan_row["broker_resume_proof_refresh_strategy"]
                ),
                "broker_resume_proof_refresh_market": str(plan_row["broker_resume_proof_refresh_market"]),
                "broker_dispatch_roundtrip_required": _to_bool(
                    plan_row["broker_dispatch_roundtrip_required"]
                ),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    plan_row["broker_dispatch_roundtrip_provided"]
                ),
                "broker_dispatch_roundtrip_ready": _to_bool(plan_row["broker_dispatch_roundtrip_ready"]),
                "broker_dispatch_roundtrip_target_mode": str(
                    plan_row["broker_dispatch_roundtrip_target_mode"]
                ),
                "broker_dispatch_roundtrip_strategy": str(plan_row["broker_dispatch_roundtrip_strategy"]),
                "broker_dispatch_roundtrip_market": str(plan_row["broker_dispatch_roundtrip_market"]),
                "broker_dispatch_roundtrip_scenario_key": str(
                    plan_row["broker_dispatch_roundtrip_scenario_key"]
                ),
                "broker_dispatch_roundtrip_batch_id": str(plan_row["broker_dispatch_roundtrip_batch_id"]),
                "broker_dispatch_roundtrip_requests": int(plan_row["broker_dispatch_roundtrip_requests"]),
                "broker_dispatch_roundtrip_acked_orders": int(
                    plan_row["broker_dispatch_roundtrip_acked_orders"]
                ),
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    plan_row["broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_dispatch_roundtrip_rejected_orders": int(
                    plan_row["broker_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    plan_row["broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "broker_dispatch_roundtrip_failed_checks": int(
                    plan_row["broker_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    plan_row["broker_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_dispatch_roundtrip_required": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_required"]
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_provided"]
                ),
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_ready"]
                ),
                "broker_route_dispatch_roundtrip_target_mode": str(
                    plan_row["broker_route_dispatch_roundtrip_target_mode"]
                ),
                "broker_route_dispatch_roundtrip_strategy": str(
                    plan_row["broker_route_dispatch_roundtrip_strategy"]
                ),
                "broker_route_dispatch_roundtrip_market": str(
                    plan_row["broker_route_dispatch_roundtrip_market"]
                ),
                "broker_route_dispatch_roundtrip_scenario_key": str(
                    plan_row["broker_route_dispatch_roundtrip_scenario_key"]
                ),
                "broker_route_dispatch_roundtrip_batch_id": str(
                    plan_row["broker_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_requests": int(
                    plan_row["broker_route_dispatch_roundtrip_requests"]
                ),
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    plan_row["broker_route_dispatch_roundtrip_acked_orders"]
                ),
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    plan_row["broker_route_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    plan_row["broker_route_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    plan_row["broker_route_dispatch_roundtrip_unmatched_acks"]
                ),
                "failed_checks": failed,
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def _config(plan_row: pd.Series, checks: pd.DataFrame, thresholds: ScaleUpThresholds) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ready": bool(plan_row["ready"]),
        "target_mode": str(plan_row["target_mode"]),
        "strategy": str(plan_row["strategy"]),
        "market": str(plan_row["market"]),
        "scenario_key": str(plan_row["scenario_key"]),
        "adapter": str(plan_row["adapter"]),
        "identity": {
            "strategy": str(plan_row["strategy"]),
            "market": str(plan_row["market"]),
            "expected_strategy": str(plan_row["expected_strategy"]),
            "expected_market": str(plan_row["expected_market"]),
        },
        "launch_pipeline": {
            "provided": _to_bool(plan_row["launch_pipeline_provided"]),
            "family": str(plan_row["launch_pipeline_family"]),
            "summary_file": str(plan_row["launch_pipeline_summary_file"]),
            "ready": _to_bool(plan_row["launch_pipeline_ready"]),
            "strategy": str(plan_row["launch_pipeline_strategy"]),
            "market": str(plan_row["launch_pipeline_market"]),
            "expected_strategy": str(plan_row["launch_pipeline_expected_strategy"]),
            "expected_market": str(plan_row["launch_pipeline_expected_market"]),
            "failed_components": int(plan_row["launch_pipeline_failed_components"]),
            "skipped_components": int(plan_row["launch_pipeline_skipped_components"]),
        },
        "surface_launch_pipeline": {
            "provided": _to_bool(plan_row["surface_launch_pipeline_provided"]),
            "ready": _to_bool(plan_row["surface_launch_pipeline_ready"]),
            "strategy": str(plan_row["surface_launch_strategy"]),
            "market": str(plan_row["surface_launch_market"]),
            "expected_strategy": str(plan_row["surface_launch_expected_strategy"]),
            "expected_market": str(plan_row["surface_launch_expected_market"]),
            "failed_components": int(plan_row["surface_launch_failed_components"]),
            "skipped_components": int(plan_row["surface_launch_skipped_components"]),
        },
        "limits": {
            "max_orders_per_session": int(plan_row["max_orders_per_session"]),
            "max_notional_per_session": float(plan_row["max_notional_per_session"]),
            "max_scale_multiplier": float(plan_row["max_scale_multiplier"]),
            "stop_loss": _jsonable(plan_row["stop_loss"]),
        },
        "kill_switches": {
            "max_total_failed_component_checks": thresholds.max_total_failed_component_checks,
            "max_total_unmatched_fills": thresholds.max_total_unmatched_fills,
            "max_total_mismatched_orders": thresholds.max_total_mismatched_orders,
            "max_total_overfilled_orders": thresholds.max_total_overfilled_orders,
            "max_telemetry_age_ns": _jsonable(thresholds.max_telemetry_age_ns),
            "max_lifecycle_orders": _jsonable(thresholds.max_lifecycle_orders),
            "max_replace_orders": _jsonable(thresholds.max_replace_orders),
            "max_open_order_count": _jsonable(thresholds.max_open_order_count),
            "max_open_order_qty": _jsonable(thresholds.max_open_order_qty),
            "max_open_order_notional": _jsonable(thresholds.max_open_order_notional),
            "max_open_order_age_ns": _jsonable(thresholds.max_open_order_age_ns),
            "max_gross_position_qty": _jsonable(thresholds.max_gross_position_qty),
            "max_abs_net_position_qty": _jsonable(thresholds.max_abs_net_position_qty),
            "max_gross_notional": _jsonable(thresholds.max_gross_notional),
            "max_abs_net_delta": _jsonable(thresholds.max_abs_net_delta),
            "max_abs_net_vega": _jsonable(thresholds.max_abs_net_vega),
            "max_worst_adverse_slippage": _jsonable(thresholds.max_worst_adverse_slippage),
        },
        "proof_freshness": {
            "required": bool(thresholds.require_proof_refresh),
            "provided": _to_bool(plan_row["proof_refresh_provided"]),
            "ready": _to_bool(plan_row["proof_refresh_ready"]),
            "strategy": str(plan_row["proof_refresh_strategy"]),
            "market": str(plan_row["proof_refresh_market"]),
            "mixed_identity": _to_bool(plan_row["proof_refresh_mixed_identity"]),
            "proof_source": str(plan_row["proof_source"]),
            "fresh_proof_required": _to_bool(plan_row["fresh_proof_required"]),
            "recommendation": str(plan_row["proof_refresh_recommendation"]),
        },
        "shadow_proof_freshness": {
            "sessions": int(plan_row["shadow_proof_refresh_sessions"]),
            "ready_sessions": int(plan_row["shadow_proof_refresh_ready_sessions"]),
            "mixed_identity_sessions": int(plan_row["shadow_proof_refresh_mixed_identity_sessions"]),
            "strategy": str(plan_row["shadow_proof_refresh_strategy"]),
            "market": str(plan_row["shadow_proof_refresh_market"]),
        },
        "instrument_metadata": {
            "required": bool(thresholds.require_instrument_metadata),
            "provided": _to_bool(plan_row["instrument_metadata_provided"]),
            "passed": _to_bool(plan_row["instrument_metadata_passed"]),
            "parse_coverage": _jsonable(plan_row["instrument_parse_coverage"]),
            "min_parse_coverage": float(thresholds.min_instrument_parse_coverage),
            "unparsed_instruments": int(plan_row["unparsed_instruments"]),
        },
        "data_readiness": {
            "required": bool(thresholds.require_data_readiness),
            "provided": _to_bool(plan_row["data_readiness_provided"]),
            "ready": _to_bool(plan_row["data_readiness_ready"]),
            "failed_checks": int(plan_row["data_readiness_failed_checks"]),
            "recommendation": str(plan_row["data_readiness_recommendation"]),
        },
        "data_readiness_comparison": {
            "required": bool(thresholds.require_data_readiness_comparison),
            "provided": _to_bool(plan_row["data_readiness_comparison_provided"]),
            "accepted": _to_bool(plan_row["data_readiness_comparison_accepted"]),
            "dataset_count": int(plan_row["data_readiness_comparison_dataset_count"]),
            "ready_rate": _jsonable(plan_row["data_readiness_comparison_ready_rate"]),
            "failed_checks": int(plan_row["data_readiness_comparison_failed_checks"]),
            "recommendation": str(plan_row["data_readiness_comparison_recommendation"]),
        },
        "broker_readiness": {
            "required": _broker_readiness_required(thresholds),
            "provided": _to_bool(plan_row["broker_readiness_provided"]),
            "ready": _to_bool(plan_row["broker_readiness_ready"]),
            "adapter_schema_status": str(plan_row["broker_schema_status"]),
            "schema_reviewed": _to_bool(plan_row["broker_schema_reviewed"]),
            "schema_review_mode": str(plan_row["broker_schema_review_mode"]),
            "recommendation": str(plan_row["broker_readiness_recommendation"]),
            "runtime_session": {
                "required": _to_bool(plan_row["broker_runtime_session_required"]),
                "provided": _to_bool(plan_row["broker_runtime_session_provided"]),
                "ready": _to_bool(plan_row["broker_runtime_session_ready"]),
                "guard_action": str(plan_row["broker_runtime_guard_action"]),
                "guard_halted": _to_bool(plan_row["broker_runtime_guard_halted"]),
                "target_mode": str(plan_row["broker_runtime_target_mode"]),
                "strategy": str(plan_row["broker_runtime_strategy"]),
                "market": str(plan_row["broker_runtime_market"]),
            },
            "resume_gate": {
                "required": _to_bool(plan_row["broker_resume_gate_required"]),
                "provided": _to_bool(plan_row["broker_resume_gate_provided"]),
                "ready": _to_bool(plan_row["broker_resume_gate_ready"]),
                "strategy": str(plan_row["broker_resume_strategy"]),
                "market": str(plan_row["broker_resume_market"]),
                "incident_strategy": str(plan_row["broker_resume_incident_strategy"]),
                "incident_market": str(plan_row["broker_resume_incident_market"]),
                "proof_refresh_ready": _to_bool(plan_row["broker_resume_proof_refresh_ready"]),
                "proof_refresh_strategy": str(plan_row["broker_resume_proof_refresh_strategy"]),
                "proof_refresh_market": str(plan_row["broker_resume_proof_refresh_market"]),
            },
            "dispatch_roundtrip": {
                "required": _to_bool(plan_row["broker_dispatch_roundtrip_required"]),
                "provided": _to_bool(plan_row["broker_dispatch_roundtrip_provided"]),
                "ready": _to_bool(plan_row["broker_dispatch_roundtrip_ready"]),
                "target_mode": str(plan_row["broker_dispatch_roundtrip_target_mode"]),
                "strategy": str(plan_row["broker_dispatch_roundtrip_strategy"]),
                "market": str(plan_row["broker_dispatch_roundtrip_market"]),
                "scenario_key": str(plan_row["broker_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(plan_row["broker_dispatch_roundtrip_batch_id"]),
                "requests": int(plan_row["broker_dispatch_roundtrip_requests"]),
                "acked_orders": int(plan_row["broker_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(plan_row["broker_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(plan_row["broker_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(plan_row["broker_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": int(plan_row["broker_dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip": {
                    "failed_checks": int(plan_row["broker_route_enable_dispatch_roundtrip_failed_checks"]),
                },
                "route_proof": {
                    "required": _to_bool(plan_row["broker_route_dispatch_roundtrip_required"]),
                    "provided": _to_bool(plan_row["broker_route_dispatch_roundtrip_provided"]),
                    "ready": _to_bool(plan_row["broker_route_dispatch_roundtrip_ready"]),
                    "target_mode": str(plan_row["broker_route_dispatch_roundtrip_target_mode"]),
                    "strategy": str(plan_row["broker_route_dispatch_roundtrip_strategy"]),
                    "market": str(plan_row["broker_route_dispatch_roundtrip_market"]),
                    "scenario_key": str(plan_row["broker_route_dispatch_roundtrip_scenario_key"]),
                    "dispatch_batch_id": str(plan_row["broker_route_dispatch_roundtrip_batch_id"]),
                    "requests": int(plan_row["broker_route_dispatch_roundtrip_requests"]),
                    "acked_orders": int(plan_row["broker_route_dispatch_roundtrip_acked_orders"]),
                    "missing_request_acks": int(
                        plan_row["broker_route_dispatch_roundtrip_missing_request_acks"]
                    ),
                    "rejected_orders": int(plan_row["broker_route_dispatch_roundtrip_rejected_orders"]),
                    "unmatched_acks": int(plan_row["broker_route_dispatch_roundtrip_unmatched_acks"]),
                },
            },
        },
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
        "thresholds": asdict(thresholds),
    }


def _broker_readiness_required(thresholds: ScaleUpThresholds) -> bool:
    return bool(
        thresholds.require_broker_readiness
        or thresholds.require_resume_gate
        or thresholds.require_dispatch_roundtrip
        or thresholds.target_mode == "live_dryrun"
    )


def _dispatch_roundtrip_required(thresholds: ScaleUpThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_dispatch_roundtrip_required(thresholds: ScaleUpThresholds, broker_readiness: pd.Series) -> bool:
    return bool(
        _dispatch_roundtrip_required(thresholds)
        or _to_bool(broker_readiness.get("route_dispatch_roundtrip_required", False))
    )


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
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _read_summary(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> pd.DataFrame:
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    if not file_path.exists():
        raise FileNotFoundError(f"required scale-up input missing: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required scale-up input is empty: {file_path}")
    return frame


def _read_optional_summary(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> pd.DataFrame:
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    if not file_path.exists():
        return pd.DataFrame()
    return _read_summary(file_path, filename)


def _optional_summary_input(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> Path | None:
    if path is None:
        return None
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    return file_path if file_path.exists() else Path(path)


def _launch_pipeline_summary_path(path: str | Path) -> Path | None:
    candidate = Path(path)
    if candidate.is_file():
        return candidate if candidate.name in {filename for _, filename in LAUNCH_PIPELINE_SUMMARIES} else None

    found: list[Path] = []
    for _, filename in LAUNCH_PIPELINE_SUMMARIES:
        file_path = _summary_path(path, filename)
        if file_path.exists():
            found.append(file_path)
    if len(found) > 1:
        files = ", ".join(file.name for file in found)
        raise ValueError(f"multiple launch pipeline summaries found: {files}")
    return found[0] if found else None


def _read_launch_pipeline_summary(path: str | Path) -> tuple[str, str, pd.DataFrame] | None:
    candidate = Path(path)
    if candidate.is_file():
        for family, filename in LAUNCH_PIPELINE_SUMMARIES:
            if candidate.name == filename:
                return family, filename, _read_summary(candidate, filename)
        return None

    found: list[tuple[str, str, pd.DataFrame]] = []
    for family, filename in LAUNCH_PIPELINE_SUMMARIES:
        file_path = _summary_path(path, filename)
        if file_path.exists():
            found.append((family, filename, _read_summary(file_path, filename)))
    if len(found) > 1:
        files = ", ".join(filename for _, filename, _ in found)
        raise ValueError(f"multiple launch pipeline summaries found: {files}")
    return found[0] if found else None


def _with_launch_pipeline_identity(
    launch: pd.DataFrame,
    launch_pipeline: tuple[str, str, pd.DataFrame] | None,
) -> pd.DataFrame:
    out = launch.copy()
    out["launch_pipeline_provided"] = False
    out["launch_pipeline_family"] = ""
    out["launch_pipeline_summary_file"] = ""
    out["launch_pipeline_ready"] = False
    out["launch_pipeline_strategy"] = ""
    out["launch_pipeline_market"] = ""
    out["launch_pipeline_expected_strategy"] = ""
    out["launch_pipeline_expected_market"] = ""
    out["launch_pipeline_failed_components"] = 0
    out["launch_pipeline_skipped_components"] = 0
    if launch_pipeline is None:
        out["surface_launch_pipeline_provided"] = False
        out["surface_launch_pipeline_ready"] = False
        out["surface_launch_strategy"] = ""
        out["surface_launch_market"] = ""
        out["surface_launch_expected_strategy"] = ""
        out["surface_launch_expected_market"] = ""
        out["surface_launch_failed_components"] = 0
        out["surface_launch_skipped_components"] = 0
        return out
    family, filename, summary = launch_pipeline
    row = summary.iloc[0]
    out["launch_pipeline_provided"] = True
    out["launch_pipeline_family"] = family
    out["launch_pipeline_summary_file"] = filename
    out["launch_pipeline_ready"] = _to_bool(row.get("ready", False))
    out["launch_pipeline_strategy"] = _strategy_key(row.get("strategy", ""))
    out["launch_pipeline_market"] = _identity_key(row.get("market", ""))
    out["launch_pipeline_expected_strategy"] = _strategy_key(row.get("expected_strategy", ""))
    out["launch_pipeline_expected_market"] = _identity_key(row.get("expected_market", ""))
    out["launch_pipeline_failed_components"] = int(_number(row, "failed_components", fallback=0.0))
    out["launch_pipeline_skipped_components"] = int(_number(row, "skipped_components", fallback=0.0))
    out["surface_launch_pipeline_provided"] = family == "surface_mm"
    out["surface_launch_pipeline_ready"] = _to_bool(row.get("ready", False)) if family == "surface_mm" else False
    out["surface_launch_strategy"] = _strategy_key(row.get("strategy", "")) if family == "surface_mm" else ""
    out["surface_launch_market"] = _identity_key(row.get("market", "")) if family == "surface_mm" else ""
    out["surface_launch_expected_strategy"] = (
        _strategy_key(row.get("expected_strategy", "")) if family == "surface_mm" else ""
    )
    out["surface_launch_expected_market"] = (
        _identity_key(row.get("expected_market", "")) if family == "surface_mm" else ""
    )
    out["surface_launch_failed_components"] = (
        int(_number(row, "failed_components", fallback=0.0)) if family == "surface_mm" else 0
    )
    out["surface_launch_skipped_components"] = (
        int(_number(row, "skipped_components", fallback=0.0)) if family == "surface_mm" else 0
    )
    return out


def _summary_path(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        direct = candidate / filename
        if direct.exists():
            return direct
        for folder in fallback_dirs:
            nested = candidate / folder / filename
            if nested.exists():
                return nested
        return direct
    return candidate


def _auto_broker_readiness_dir(launch_dir: str | Path) -> Path | None:
    candidate = Path(launch_dir)
    if not candidate.is_dir():
        return None
    for folder in ("06_broker_readiness", "05_broker_readiness"):
        broker_dir = candidate / folder
        if (broker_dir / "broker_readiness_summary.csv").exists():
            return broker_dir
    return None


def _validate_thresholds(thresholds: ScaleUpThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_scale_multiplier <= 0:
        raise ValueError("max_scale_multiplier must be positive")
    if thresholds.min_shadow_sessions <= 0:
        raise ValueError("min_shadow_sessions must be positive")
    for name in ("min_shadow_acceptance_rate", "min_median_order_fill_rate"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if thresholds.min_worst_order_fill_rate is not None and not 0 <= thresholds.min_worst_order_fill_rate <= 1:
        raise ValueError("min_worst_order_fill_rate must be between 0 and 1")
    if not 0 <= thresholds.min_instrument_parse_coverage <= 1:
        raise ValueError("min_instrument_parse_coverage must be between 0 and 1")
    for name in (
        "max_total_failed_component_checks",
        "max_total_unmatched_fills",
        "max_total_mismatched_orders",
        "max_total_overfilled_orders",
        "max_lifecycle_orders",
        "max_replace_orders",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in (
        "max_telemetry_age_ns",
        "max_open_order_count",
        "max_open_order_qty",
        "max_open_order_notional",
        "max_open_order_age_ns",
        "max_gross_position_qty",
        "max_abs_net_position_qty",
        "max_orders_per_session",
        "max_session_notional",
        "max_gross_notional",
        "max_abs_net_delta",
        "max_abs_net_vega",
        "stop_loss",
    ):
        value = getattr(thresholds, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


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


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
