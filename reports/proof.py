from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    MANIFEST_NAME,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


PROOF_REPORT_RUN_TYPE = "proof_report"
PROOF_METRICS_FILE = "proof_metrics.csv"
PROOF_CHECKS_FILE = "proof_checks.csv"
PROOF_SUMMARY_FILE = "proof_summary.csv"
PROOF_REPORT_REQUIRED_ARTIFACTS = (
    PROOF_METRICS_FILE,
    PROOF_CHECKS_FILE,
    PROOF_SUMMARY_FILE,
)


@dataclass(frozen=True)
class ProofThresholds:
    min_net_pnl: float = 0.0
    min_fills: int = 1
    max_drawdown: float | None = None
    max_otr: float | None = None
    min_maker_share: float | None = None
    min_worst_regime_equity_change: float | None = None
    min_markout_mean: float | None = None
    min_spread_net: float | None = None


@dataclass(frozen=True)
class ProofReport:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["all_passed"]) if not self.summary.empty else False


@dataclass(frozen=True)
class ProofReportVerification:
    verified: bool
    passed: bool
    manifest_current: bool
    inputs_current: bool
    replay_manifests_current: bool
    artifacts_consistent: bool
    non_authorizing: bool
    output_dir: Path
    manifest_path: Path
    manifest_artifact_count: int = 0
    manifest_artifact_match_count: int = 0
    manifest_input_fingerprint_count: int = 0
    manifest_input_fingerprint_match_count: int = 0
    replay_manifest_count: int = 0
    replay_manifest_current_count: int = 0
    error: str = ""


def evaluate_replay_dir(
    run_dir: str | Path,
    *,
    thresholds: ProofThresholds | None = None,
    run_name: str | None = None,
) -> ProofReport:
    return evaluate_replay_dirs(
        [run_dir],
        thresholds=thresholds,
        run_names=[run_name] if run_name is not None else None,
    )


def evaluate_replay_dirs(
    run_dirs: list[str | Path],
    *,
    thresholds: ProofThresholds | None = None,
    run_names: list[str] | None = None,
) -> ProofReport:
    if not run_dirs:
        raise ValueError("at least one replay run directory is required")
    thresholds = thresholds or ProofThresholds()
    if run_names is not None and len(run_names) != len(run_dirs):
        raise ValueError("run_names must match run_dirs length")

    metric_rows = []
    check_frames = []
    for idx, run_dir in enumerate(run_dirs):
        path = Path(run_dir)
        name = run_names[idx] if run_names is not None else path.name
        metrics = _run_metrics(path, name)
        metric_rows.append(metrics)
        check_frames.append(_run_checks(metrics, thresholds))

    metrics_df = pd.DataFrame(metric_rows)
    checks_df = pd.concat([*check_frames, _identity_checks(metrics_df)], ignore_index=True, sort=False)
    summary_df = _proof_summary(metrics_df, checks_df)
    return ProofReport(metrics=metrics_df, checks=checks_df, summary=summary_df)


def write_proof_report(
    run_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    thresholds: ProofThresholds | None = None,
    run_names: list[str] | None = None,
) -> ProofReport:
    thresholds = thresholds or ProofThresholds()
    canonical_run_names = list(run_names) if run_names is not None else None
    report = evaluate_replay_dirs(
        run_dirs,
        thresholds=thresholds,
        run_names=canonical_run_names,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / PROOF_METRICS_FILE, index=False)
    report.checks.to_csv(out / PROOF_CHECKS_FILE, index=False)
    report.summary.to_csv(out / PROOF_SUMMARY_FILE, index=False)
    write_experiment_manifest(
        out,
        run_type=PROOF_REPORT_RUN_TYPE,
        parameters={
            "run_names": canonical_run_names,
            "thresholds": asdict(thresholds),
        },
        inputs=_proof_manifest_inputs(run_dirs),
        extra=_proof_manifest_extra(report),
    )
    return ProofReport(report.metrics, report.checks, report.summary, out)


def verify_proof_report(report_dir: str | Path) -> ProofReportVerification:
    requested = Path(report_dir)
    root = requested.parent if requested.is_file() else requested
    root = root.resolve()
    manifest_path = root / MANIFEST_NAME
    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=PROOF_REPORT_RUN_TYPE,
        required_artifacts=PROOF_REPORT_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    inputs_current = False
    replay_manifests_current = False
    artifacts_consistent = False
    non_authorizing = False
    replay_manifest_count = 0
    replay_manifest_current_count = 0
    try:
        manifest = _read_json_object(manifest_path, "proof manifest")
        parameters = _mapping(manifest.get("parameters"))
        run_names, thresholds = _proof_parameters_from_manifest(parameters)
        inputs = _mapping(manifest.get("inputs"))
        run_dirs = _proof_run_paths_from_manifest(inputs)
        if run_names is not None and len(run_names) != len(run_dirs):
            raise ValueError("proof run names do not match replay inputs")
        expected_report = evaluate_replay_dirs(
            run_dirs,
            thresholds=thresholds,
            run_names=run_names,
        )
        expected_parameters = {
            "run_names": run_names,
            "thresholds": asdict(thresholds),
        }
        expected_extra = _proof_manifest_extra(expected_report)
        inputs_current = bool(
            _proof_input_contract_current(inputs, run_dirs)
            and integrity.input_fingerprint_count
            == integrity.input_fingerprint_match_count
            and integrity.input_fingerprint_count > 0
        )
        (
            replay_manifests_current,
            replay_manifest_count,
            replay_manifest_current_count,
        ) = _proof_replay_manifests_current(run_dirs)
        artifacts_consistent = bool(
            _proof_artifacts_consistent(root, expected_report, manifest)
            and dict(parameters) == expected_parameters
            and _mapping(manifest.get("extra")) == expected_extra
        )
        non_authorizing = _proof_authority_consistent(
            root,
            _mapping(manifest.get("extra")),
            expected_report.passed,
        )
        verified = bool(
            integrity.passed
            and inputs_current
            and replay_manifests_current
            and artifacts_consistent
            and non_authorizing
        )
        error = ""
        if not verified:
            error = (
                integrity.error
                or (
                    "input contract is invalid"
                    if not inputs_current
                    else ""
                )
                or (
                    "replay manifests are missing, stale, or unfingerprinted"
                    if not replay_manifests_current
                    else ""
                )
                or (
                    "artifacts do not reconstruct from replay inputs"
                    if not artifacts_consistent
                    else ""
                )
                or "report widens authority"
            )
        return ProofReportVerification(
            verified=verified,
            passed=bool(verified and expected_report.passed),
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            replay_manifests_current=replay_manifests_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=integrity.artifact_match_count,
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            replay_manifest_count=replay_manifest_count,
            replay_manifest_current_count=replay_manifest_current_count,
            error=error,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return ProofReportVerification(
            verified=False,
            passed=False,
            manifest_current=integrity.passed,
            inputs_current=inputs_current,
            replay_manifests_current=replay_manifests_current,
            artifacts_consistent=artifacts_consistent,
            non_authorizing=non_authorizing,
            output_dir=root,
            manifest_path=manifest_path,
            manifest_artifact_count=integrity.artifact_count,
            manifest_artifact_match_count=integrity.artifact_match_count,
            manifest_input_fingerprint_count=(
                integrity.input_fingerprint_count
            ),
            manifest_input_fingerprint_match_count=(
                integrity.input_fingerprint_match_count
            ),
            replay_manifest_count=replay_manifest_count,
            replay_manifest_current_count=replay_manifest_current_count,
            error=integrity.error or str(exc),
        )


def _proof_manifest_extra(report: ProofReport) -> dict[str, object]:
    return {
        "all_passed": report.passed,
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }


def _proof_parameters_from_manifest(
    parameters: Mapping[str, Any],
) -> tuple[list[str] | None, ProofThresholds]:
    if set(parameters) != {"run_names", "thresholds"}:
        raise ValueError(
            "proof manifest parameters must contain run_names and thresholds"
        )
    raw_run_names = parameters.get("run_names")
    if raw_run_names is None:
        run_names = None
    elif isinstance(raw_run_names, list) and all(
        isinstance(value, str) for value in raw_run_names
    ):
        run_names = list(raw_run_names)
    else:
        raise ValueError("proof manifest run_names must be a string list")
    values = _mapping(parameters.get("thresholds"))
    expected_fields = {field.name for field in fields(ProofThresholds)}
    if set(values) != expected_fields:
        raise ValueError("proof manifest threshold contract is incomplete")
    thresholds = ProofThresholds(**dict(values))
    expected = {
        "run_names": run_names,
        "thresholds": asdict(thresholds),
    }
    if dict(parameters) != expected:
        raise ValueError("proof manifest parameters are not canonical")
    return run_names, thresholds


def _proof_manifest_inputs(
    run_dirs: list[str | Path],
) -> dict[str, object]:
    canonical_dirs = [Path(path).resolve() for path in run_dirs]
    manifest_paths: dict[str, Path] = {}
    dependency_paths: dict[str, Path] = {}
    for root in canonical_dirs:
        manifest_path = (root / MANIFEST_NAME).resolve()
        if not manifest_path.is_file():
            continue
        manifest_paths[str(manifest_path)] = manifest_path
        for dependency in manifest_dependency_paths(manifest_path):
            resolved = dependency.resolve()
            dependency_paths[str(resolved)] = resolved
    inputs: dict[str, object] = {"run_dirs": canonical_dirs}
    if manifest_paths:
        inputs["run_manifests"] = [
            manifest_paths[key] for key in sorted(manifest_paths)
        ]
    if dependency_paths:
        inputs["run_dependencies"] = [
            dependency_paths[key] for key in sorted(dependency_paths)
        ]
    return inputs


def _proof_run_paths_from_manifest(
    inputs: Mapping[str, Any],
) -> list[Path]:
    value = inputs.get("run_dirs")
    if not isinstance(value, list) or not value:
        raise ValueError("proof manifest lacks replay directory fingerprints")
    return [
        _manifest_path_fingerprint(item, "run_dirs")
        for item in value
    ]


def _manifest_path_fingerprint(value: Any, label: str) -> Path:
    fingerprint = _mapping(value)
    if fingerprint.get("kind") != "directory":
        raise ValueError(
            f"proof manifest {label} input is not a directory fingerprint"
        )
    raw_path = str(fingerprint.get("path", "")).strip()
    if not raw_path:
        raise ValueError(f"proof manifest {label} input path is missing")
    return Path(raw_path).resolve()


def _proof_input_contract_current(
    inputs: Mapping[str, Any],
    run_dirs: list[Path],
) -> bool:
    expected = _proof_manifest_inputs(run_dirs)
    if set(inputs) != set(expected):
        return False
    return all(
        _manifest_input_path_contract(inputs.get(name))
        == _expected_input_path_contract(value)
        for name, value in expected.items()
    )


def _manifest_input_path_contract(value: Any) -> Any:
    if isinstance(value, list):
        return [
            _manifest_input_path_contract(item)
            for item in value
        ]
    fingerprint = _mapping(value)
    kind = str(fingerprint.get("kind", ""))
    raw_path = str(fingerprint.get("path", "")).strip()
    if kind not in {"file", "directory"} or not raw_path:
        return None
    return kind, str(Path(raw_path).resolve())


def _expected_input_path_contract(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [
            _expected_input_path_contract(item)
            for item in value
        ]
    if not isinstance(value, (str, Path)):
        return None
    path = Path(value).resolve()
    kind = (
        "file"
        if path.is_file()
        else "directory"
        if path.is_dir()
        else ""
    )
    return (kind, str(path)) if kind else None


def _proof_replay_manifests_current(
    run_dirs: list[Path],
) -> tuple[bool, int, int]:
    manifest_paths = [
        (root / MANIFEST_NAME).resolve()
        for root in run_dirs
    ]
    current_count = sum(
        verify_experiment_manifest(
            path,
            require_input_fingerprints=True,
        ).passed
        for path in manifest_paths
    )
    return (
        bool(manifest_paths and current_count == len(manifest_paths)),
        len(manifest_paths),
        int(current_count),
    )


def _proof_artifacts_consistent(
    root: Path,
    expected: ProofReport,
    manifest: Mapping[str, Any],
) -> bool:
    return bool(
        _proof_manifest_artifacts_exact(manifest)
        and _csv_frame_matches(root / PROOF_METRICS_FILE, expected.metrics)
        and _csv_frame_matches(root / PROOF_CHECKS_FILE, expected.checks)
        and _csv_frame_matches(root / PROOF_SUMMARY_FILE, expected.summary)
    )


def _proof_manifest_artifacts_exact(
    manifest: Mapping[str, Any],
) -> bool:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    names = [
        str(item.get("path", "")).replace("\\", "/")
        for item in artifacts
        if isinstance(item, Mapping)
    ]
    return bool(
        len(names) == len(PROOF_REPORT_REQUIRED_ARTIFACTS)
        and len(names) == len(artifacts)
        and set(names) == set(PROOF_REPORT_REQUIRED_ARTIFACTS)
    )


def _proof_authority_consistent(
    root: Path,
    manifest_extra: Mapping[str, Any],
    passed: bool,
) -> bool:
    summary = _read_csv_frame(root / PROOF_SUMMARY_FILE, "proof summary")
    if len(summary.index) != 1:
        return False
    row = summary.iloc[0]
    return bool(
        _bool(row.get("non_authorizing", False))
        and not _bool(row.get("authorizes_routing", True))
        and not _bool(row.get("authorizes_submission", True))
        and dict(manifest_extra)
        == {
            "all_passed": bool(passed),
            "non_authorizing": True,
            "authorizes_routing": False,
            "authorizes_submission": False,
        }
    )


def _csv_frame_matches(path: Path, expected: pd.DataFrame) -> bool:
    actual = _read_csv_frame(path, path.name)
    expected_roundtrip = pd.read_csv(
        StringIO(expected.to_csv(index=False)),
        keep_default_na=False,
    )
    return bool(
        list(actual.columns) == list(expected_roundtrip.columns)
        and actual.to_dict(orient="records")
        == expected_roundtrip.to_dict(orient="records")
    )


def _read_csv_frame(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, keep_default_na=False)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        raise ValueError(f"{label} is unreadable") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _run_metrics(run_dir: Path, run_name: str) -> dict[str, float | int | str | bool]:
    summary = _read_required(run_dir / "summary.csv")
    row = summary.iloc[0]
    manifest = _read_manifest(run_dir)
    equity = _read_optional(run_dir / "equity.csv")
    equity_by_regime = _read_optional(run_dir / "equity_by_regime.csv")
    spread_summary = _read_optional(run_dir / "spread_summary.csv")
    markouts = _read_optional(run_dir / "markouts.csv")
    strategy = _strategy_key(_first_identity(row, manifest, ("strategy", "strategy_name", "strategy_id")))
    market = _identity_key(_first_identity(row, manifest, ("market", "market_profile", "market_name", "market_id")))

    net_pnl = _float(row, "net_pnl")
    fills = _int(row, "fills")
    turnover = _float(row, "turnover")
    total_costs = _float(row, "total_costs")
    maker_share = _float(row, "maker_share")
    otr = _float(row, "order_to_trade_ratio")
    pending_order_risk_reservation_enabled = _bool(
        row.get("pending_order_risk_reservation_enabled", False)
    )
    aggressive_self_cross_prevention_enabled = _bool(
        row.get("aggressive_self_cross_prevention_enabled", False)
    )
    venue_order_validation_enabled = _bool(
        row.get("venue_order_validation_enabled", False)
    )
    shared_event_liquidity_enabled = _bool(
        row.get("shared_event_liquidity_enabled", False)
    )
    persistent_displayed_liquidity_enabled = _bool(
        row.get("persistent_displayed_liquidity_enabled", False)
    )
    arrival_queue_initialization_enabled = _bool(
        row.get("arrival_queue_initialization_enabled", False)
    )
    limit_orders_sent = _int(row, "limit_orders_sent")
    queue_initialization_events = _int(row, "queue_initialization_events")
    deferred_queue_initialization_events = _int(
        row,
        "deferred_queue_initialization_events",
    )
    uninitialized_limit_orders = _int(row, "uninitialized_limit_orders")
    max_queue_initialization_lag_ns = _int(
        row,
        "max_queue_initialization_lag_ns",
    )
    residual_resting_transition_events = _int(
        row,
        "residual_resting_transition_events",
    )
    residual_resting_transition_qty = _int(
        row,
        "residual_resting_transition_qty",
    )
    deferred_residual_queue_events = _int(
        row,
        "deferred_residual_queue_events",
    )
    unresolved_residual_queue_events = _int(
        row,
        "unresolved_residual_queue_events",
    )
    max_residual_queue_initialization_lag_ns = _int(
        row,
        "max_residual_queue_initialization_lag_ns",
    )
    passive_price_through_depth_constrained_enabled = _bool(
        row.get(
            "passive_price_through_depth_constrained_enabled",
            False,
        )
    )
    passive_price_through_events = _int(
        row,
        "passive_price_through_events",
    )
    passive_price_through_requested_qty = _int(
        row,
        "passive_price_through_requested_qty",
    )
    passive_price_through_filled_qty = _int(
        row,
        "passive_price_through_filled_qty",
    )
    passive_price_through_shortfall_qty = _int(
        row,
        "passive_price_through_shortfall_qty",
    )
    passive_price_through_incomplete_events = _int(
        row,
        "passive_price_through_incomplete_events",
    )
    terminal_liquidation_depth_constrained_enabled = _bool(
        row.get(
            "terminal_liquidation_depth_constrained_enabled",
            False,
        )
    )
    terminal_liquidation_events = _int(
        row,
        "terminal_liquidation_events",
    )
    terminal_liquidation_requested_qty = _int(
        row,
        "terminal_liquidation_requested_qty",
    )
    terminal_liquidation_filled_qty = _int(
        row,
        "terminal_liquidation_filled_qty",
    )
    terminal_liquidation_shortfall_qty = _int(
        row,
        "terminal_liquidation_shortfall_qty",
    )
    terminal_liquidation_incomplete_events = _int(
        row,
        "terminal_liquidation_incomplete_events",
    )
    terminal_residual_position_qty = _int(
        row,
        "terminal_residual_position_qty",
    )
    terminal_residual_instruments = _int(
        row,
        "terminal_residual_instruments",
    )
    terminal_liquidation_complete = _bool(
        row.get("terminal_liquidation_complete", False)
    )
    liquidity_shortfall_events = _int(row, "liquidity_shortfall_events")
    liquidity_shortfall_qty = _int(row, "liquidity_shortfall_qty")
    displayed_liquidity_shortfall_events = _int(
        row,
        "displayed_liquidity_shortfall_events",
    )
    displayed_liquidity_shortfall_qty = _int(
        row,
        "displayed_liquidity_shortfall_qty",
    )
    trade_print_shortfall_events = _int(
        row,
        "trade_print_shortfall_events",
    )
    trade_print_shortfall_qty = _int(row, "trade_print_shortfall_qty")
    carried_depletion_shortfall_events = _int(
        row,
        "carried_depletion_shortfall_events",
    )
    carried_depletion_shortfall_qty = _int(
        row,
        "carried_depletion_shortfall_qty",
    )
    pretrade_rejections = _int(row, "pretrade_rejections")
    venue_rule_rejections = _int(row, "venue_rule_rejections")
    position_risk_rejections = _int(row, "position_risk_rejections")
    self_cross_rejections = _int(row, "self_cross_rejections")
    max_drawdown = _max_drawdown(equity)
    worst_regime = _worst_regime_equity_change(equity_by_regime)
    markout_mean, markout_win_rate = _markout_quality(markouts)
    spread_net = _spread_net(spread_summary)

    return {
        "run": run_name,
        "strategy": strategy,
        "market": market,
        "net_pnl": net_pnl,
        "fills": fills,
        "turnover": turnover,
        "total_costs": total_costs,
        "cost_bps": 1e4 * total_costs / turnover if turnover > 0 else np.nan,
        "pnl_per_fill": net_pnl / fills if fills > 0 else np.nan,
        "maker_share": maker_share,
        "order_to_trade_ratio": otr,
        "otr_breached": _bool(row.get("otr_breached", False)),
        "pending_order_risk_reservation_enabled": (
            pending_order_risk_reservation_enabled
        ),
        "aggressive_self_cross_prevention_enabled": (
            aggressive_self_cross_prevention_enabled
        ),
        "venue_order_validation_enabled": venue_order_validation_enabled,
        "shared_event_liquidity_enabled": shared_event_liquidity_enabled,
        "persistent_displayed_liquidity_enabled": (
            persistent_displayed_liquidity_enabled
        ),
        "arrival_queue_initialization_enabled": (
            arrival_queue_initialization_enabled
        ),
        "limit_orders_sent": limit_orders_sent,
        "queue_initialization_events": queue_initialization_events,
        "deferred_queue_initialization_events": (
            deferred_queue_initialization_events
        ),
        "uninitialized_limit_orders": uninitialized_limit_orders,
        "max_queue_initialization_lag_ns": max_queue_initialization_lag_ns,
        "residual_resting_transition_events": (
            residual_resting_transition_events
        ),
        "residual_resting_transition_qty": residual_resting_transition_qty,
        "deferred_residual_queue_events": deferred_residual_queue_events,
        "unresolved_residual_queue_events": unresolved_residual_queue_events,
        "max_residual_queue_initialization_lag_ns": (
            max_residual_queue_initialization_lag_ns
        ),
        "passive_price_through_depth_constrained_enabled": (
            passive_price_through_depth_constrained_enabled
        ),
        "passive_price_through_events": passive_price_through_events,
        "passive_price_through_requested_qty": (
            passive_price_through_requested_qty
        ),
        "passive_price_through_filled_qty": passive_price_through_filled_qty,
        "passive_price_through_shortfall_qty": (
            passive_price_through_shortfall_qty
        ),
        "passive_price_through_incomplete_events": (
            passive_price_through_incomplete_events
        ),
        "terminal_liquidation_depth_constrained_enabled": (
            terminal_liquidation_depth_constrained_enabled
        ),
        "terminal_liquidation_events": terminal_liquidation_events,
        "terminal_liquidation_requested_qty": (
            terminal_liquidation_requested_qty
        ),
        "terminal_liquidation_filled_qty": terminal_liquidation_filled_qty,
        "terminal_liquidation_shortfall_qty": (
            terminal_liquidation_shortfall_qty
        ),
        "terminal_liquidation_incomplete_events": (
            terminal_liquidation_incomplete_events
        ),
        "terminal_residual_position_qty": terminal_residual_position_qty,
        "terminal_residual_instruments": terminal_residual_instruments,
        "terminal_liquidation_complete": terminal_liquidation_complete,
        "liquidity_shortfall_events": liquidity_shortfall_events,
        "liquidity_shortfall_qty": liquidity_shortfall_qty,
        "displayed_liquidity_shortfall_events": (
            displayed_liquidity_shortfall_events
        ),
        "displayed_liquidity_shortfall_qty": displayed_liquidity_shortfall_qty,
        "trade_print_shortfall_events": trade_print_shortfall_events,
        "trade_print_shortfall_qty": trade_print_shortfall_qty,
        "carried_depletion_shortfall_events": (
            carried_depletion_shortfall_events
        ),
        "carried_depletion_shortfall_qty": carried_depletion_shortfall_qty,
        "pretrade_rejections": pretrade_rejections,
        "venue_rule_rejections": venue_rule_rejections,
        "position_risk_rejections": position_risk_rejections,
        "self_cross_rejections": self_cross_rejections,
        "max_drawdown": max_drawdown,
        "regime_count": int(len(equity_by_regime)) if not equity_by_regime.empty else 0,
        "losing_regimes": _losing_regimes(equity_by_regime),
        "worst_regime_equity_change": worst_regime,
        "spread_net": spread_net,
        "markout_mean": markout_mean,
        "markout_win_rate": markout_win_rate,
    }


def _run_checks(metrics: dict[str, float | int | str | bool], thresholds: ProofThresholds) -> pd.DataFrame:
    rows = [
        _check(metrics, "net_pnl", metrics["net_pnl"], ">=", thresholds.min_net_pnl),
        _check(metrics, "fills", metrics["fills"], ">=", thresholds.min_fills),
        {
            "run": metrics["run"],
            "check": "otr_not_breached",
            "value": metrics["otr_breached"],
            "operator": "is",
            "threshold": False,
            "passed": not bool(metrics["otr_breached"]),
            "reason": "summary.csv reported an OTR breach" if bool(metrics["otr_breached"]) else "",
        },
    ]
    if bool(metrics["terminal_liquidation_depth_constrained_enabled"]):
        complete = bool(metrics["terminal_liquidation_complete"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "terminal_liquidation_complete",
                "value": complete,
                "operator": "is",
                "threshold": True,
                "passed": complete,
                "reason": (
                    ""
                    if complete
                    else "terminal liquidation left residual inventory"
                ),
            }
        )
    if thresholds.max_drawdown is not None:
        rows.append(_check(metrics, "max_drawdown", metrics["max_drawdown"], "<=", thresholds.max_drawdown))
    if thresholds.max_otr is not None:
        rows.append(_check(metrics, "order_to_trade_ratio", metrics["order_to_trade_ratio"], "<=", thresholds.max_otr))
    if thresholds.min_maker_share is not None:
        rows.append(_check(metrics, "maker_share", metrics["maker_share"], ">=", thresholds.min_maker_share))
    if thresholds.min_worst_regime_equity_change is not None:
        rows.append(
            _check(
                metrics,
                "worst_regime_equity_change",
                metrics["worst_regime_equity_change"],
                ">=",
                thresholds.min_worst_regime_equity_change,
            )
        )
    if thresholds.min_markout_mean is not None:
        rows.append(_check(metrics, "markout_mean", metrics["markout_mean"], ">=", thresholds.min_markout_mean))
    if thresholds.min_spread_net is not None:
        rows.append(_check(metrics, "spread_net", metrics["spread_net"], ">=", thresholds.min_spread_net))
    return pd.DataFrame(rows)


def _check(
    metrics: dict[str, float | int | str | bool],
    name: str,
    value: float | int | str | bool,
    operator: str,
    threshold: float | int | bool,
) -> dict[str, float | int | str | bool]:
    value_float = float(value)
    threshold_float = float(threshold)
    is_missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not is_missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not is_missing) and value_float <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if is_missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "run": metrics["run"],
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _proof_summary(metrics: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    metric_runs = set(metrics["run"].astype(str))
    failed_runs = checks.loc[
        (~checks["passed"]) & checks["run"].astype(str).isin(metric_runs),
        "run",
    ].drop_duplicates()
    strategies = _identity_values(metrics, "strategy", normalizer=_strategy_key)
    markets = _identity_values(metrics, "market", normalizer=_identity_key)
    missing_strategies = _missing_identity_count(metrics, "strategy")
    missing_markets = _missing_identity_count(metrics, "market")
    mixed_identity = bool((len(strategies) > 1) or (len(markets) > 1))
    all_checks_passed = bool(checks["passed"].all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "run_count": int(len(metrics)),
                "passed_runs": int(len(metrics) - len(failed_runs)),
                "failed_runs": int(len(failed_runs)),
                "all_passed": bool(all_checks_passed and not mixed_identity),
                "strategy": next(iter(strategies)) if len(strategies) == 1 else "",
                "strategy_count": int(len(strategies)),
                "missing_strategy_runs": missing_strategies,
                "market": next(iter(markets)) if len(markets) == 1 else "",
                "market_count": int(len(markets)),
                "missing_market_runs": missing_markets,
                "mixed_identity": mixed_identity,
                "total_net_pnl": float(metrics["net_pnl"].sum()),
                "total_fills": int(metrics["fills"].sum()),
                "worst_drawdown": float(metrics["max_drawdown"].max(skipna=True)),
                "worst_regime_equity_change": float(metrics["worst_regime_equity_change"].min(skipna=True)),
                "non_authorizing": True,
                "authorizes_routing": False,
                "authorizes_submission": False,
            }
        ]
    )


def _identity_checks(metrics: pd.DataFrame) -> pd.DataFrame:
    strategies = _identity_values(metrics, "strategy", normalizer=_strategy_key)
    markets = _identity_values(metrics, "market", normalizer=_identity_key)
    strategy_passed = len(strategies) <= 1
    market_passed = len(markets) <= 1
    return pd.DataFrame(
        [
            {
                "run": "__proof__",
                "check": "same_strategy",
                "value": ";".join(sorted(strategies)) if strategies else "",
                "operator": "count<=",
                "threshold": 1,
                "passed": strategy_passed,
                "reason": "" if strategy_passed else "proof bundle mixes strategy identities",
            },
            {
                "run": "__proof__",
                "check": "same_market",
                "value": ";".join(sorted(markets)) if markets else "",
                "operator": "count<=",
                "threshold": 1,
                "passed": market_passed,
                "reason": "" if market_passed else "proof bundle mixes market identities",
            },
        ]
    )


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required replay artifact missing: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required replay artifact is empty: {path}")
    return frame


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _read_manifest(run_dir: Path) -> dict:
    path = run_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row else np.nan


def _int(row: pd.Series, column: str) -> int:
    return int(row[column]) if column in row and not pd.isna(row[column]) else 0


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _max_drawdown(equity: pd.DataFrame) -> float:
    if equity.empty or "equity" not in equity.columns:
        return np.nan
    values = pd.Series([0.0] + equity["equity"].astype(float).tolist())
    return float((values.cummax() - values).max())


def _worst_regime_equity_change(equity_by_regime: pd.DataFrame) -> float:
    if equity_by_regime.empty or "equity_change" not in equity_by_regime.columns:
        return np.nan
    return float(equity_by_regime["equity_change"].min())


def _losing_regimes(equity_by_regime: pd.DataFrame) -> int:
    if equity_by_regime.empty or "equity_change" not in equity_by_regime.columns:
        return 0
    return int((equity_by_regime["equity_change"] < 0).sum())


def _spread_net(spread_summary: pd.DataFrame) -> float:
    if spread_summary.empty or "net_spread" not in spread_summary.columns:
        return np.nan
    return float(spread_summary["net_spread"].sum())


def _markout_quality(markouts: pd.DataFrame) -> tuple[float, float]:
    if markouts.empty:
        return np.nan, np.nan
    if "markout" in markouts.columns:
        values = markouts["markout"].astype(float)
    elif "surface_markout" in markouts.columns:
        values = markouts["surface_markout"].astype(float)
    else:
        return np.nan, np.nan
    return float(values.mean()), float((values > 0).mean())


def _first_identity(row: pd.Series, manifest: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    parsed = _parse_scenario_key(_text(row, "scenario_key"))
    for key in keys:
        if key in parsed:
            return parsed[key]
    for section in ("parameters", "extra", "inputs"):
        value = _find_json_key(manifest.get(section, {}), keys)
        if value:
            return value
    return ""


def _identity_values(frame: pd.DataFrame, column: str, *, normalizer) -> set[str]:
    if frame.empty or column not in frame.columns:
        return set()
    return {value for value in frame[column].map(normalizer) if value}


def _missing_identity_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty:
        return 0
    if column not in frame.columns:
        return int(len(frame))
    return int((frame[column].map(_identity_key) == "").sum())


def _parse_scenario_key(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in value.split("|"):
        if "=" not in part:
            continue
        key, item = part.split("=", 1)
        key = key.strip()
        item = item.strip()
        if key and item:
            parsed[key] = item
    return parsed


def _find_json_key(value: object, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, (str, int, float)) and str(item).strip():
                return str(item)
        for item in value.values():
            found = _find_json_key(item, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_json_key(item, keys)
            if found:
                return found
    return ""


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


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
