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
    manifest_parameters = _mapping(manifest.get("parameters"))
    equity = _read_optional(run_dir / "equity.csv")
    equity_by_regime = _read_optional(run_dir / "equity_by_regime.csv")
    spread_summary = _read_optional(run_dir / "spread_summary.csv")
    markouts = _read_optional(run_dir / "markouts.csv")
    parity_signals_path = run_dir / "signals.csv"
    parity_futures_join_audit_path = (
        run_dir / "parity_futures_join_audit.csv"
    )
    parity_signals = _read_optional(parity_signals_path)
    parity_futures_join_audit = _read_optional(
        parity_futures_join_audit_path
    )
    parity_execution_guard_path = (
        run_dir / "parity_execution_guard.csv"
    )
    parity_legging_path = run_dir / "legging.csv"
    fills_path = run_dir / "fills.csv"
    feed_deliveries_path = run_dir / "feed_deliveries.csv"
    order_submissions_path = run_dir / "order_submissions.csv"
    ioc_arrival_audit_path = run_dir / "ioc_arrival_audit.csv"
    parity_execution_guard = _read_optional(
        parity_execution_guard_path
    )
    parity_legging = _read_optional(parity_legging_path)
    replay_fills = _read_optional(fills_path)
    feed_deliveries = _read_optional(feed_deliveries_path)
    order_submissions = _read_optional(order_submissions_path)
    ioc_arrival_audit = _read_optional(ioc_arrival_audit_path)
    strategy = _strategy_key(_first_identity(row, manifest, ("strategy", "strategy_name", "strategy_id")))
    market = _identity_key(_first_identity(row, manifest, ("market", "market_profile", "market_name", "market_id")))

    net_pnl = _float(row, "net_pnl")
    fills = _int(row, "fills")
    turnover = _float(row, "turnover")
    total_costs = _float(row, "total_costs")
    maker_share = _float(row, "maker_share")
    otr = _float(row, "order_to_trade_ratio")
    input_quarantine_tracking_enabled = _bool(
        row.get("input_quarantine_tracking_enabled", False)
    )
    input_dataset_count = _int(row, "input_dataset_count")
    input_total_rows = _int(row, "input_total_rows")
    input_kept_rows = _int(row, "input_kept_rows")
    input_dropped_rows = _int(row, "input_dropped_rows")
    input_integrity_dropped_rows = _int(
        row,
        "input_integrity_dropped_rows",
    )
    input_session_filtered_rows = _int(
        row,
        "input_session_filtered_rows",
    )
    input_empty_datasets = _int(row, "input_empty_datasets")
    parity_futures_asof_freshness_enabled = _bool(
        row.get("parity_futures_asof_freshness_enabled", False)
    )
    parity_futures_max_quote_age_ns = _int(
        row,
        "parity_futures_max_quote_age_ns",
    )
    parity_futures_join_reasons = (
        parity_futures_join_audit["reason"].astype(str)
        if "reason" in parity_futures_join_audit.columns
        else pd.Series(dtype="object")
    )
    parity_futures_fresh_join_rows = int(
        (parity_futures_join_reasons == "fresh").sum()
    )
    parity_futures_stale_join_rows = int(
        parity_futures_join_reasons.isin(
            {
                "stale_future_quote",
                "negative_future_quote_age",
            }
        ).sum()
    )
    parity_futures_unmatched_join_rows = int(
        parity_futures_join_reasons.isin(
            {
                "no_prior_future_quote",
                "incomplete_future_quote",
            }
        ).sum()
    )
    parity_futures_unclassified_join_rows = max(
        int(len(parity_futures_join_audit))
        - parity_futures_fresh_join_rows
        - parity_futures_stale_join_rows
        - parity_futures_unmatched_join_rows,
        0,
    )
    parity_signal_ages = pd.to_numeric(
        parity_signals.get(
            "future_asof_age_ns",
            pd.Series(index=parity_signals.index, dtype="float64"),
        ),
        errors="coerce",
    )
    parity_observed_signal_ages = parity_signal_ages.dropna()
    parity_futures_signal_age_violations = int(
        (
            parity_signal_ages.lt(0)
            | parity_signal_ages.gt(parity_futures_max_quote_age_ns)
        ).sum()
    )
    parity_execution_guard_declared = _bool(
        row.get("parity_execution_guard_enabled", False)
    )
    parity_execution_run_detected = (
        str(manifest.get("run_type", "")).strip().lower()
        == "parity_replay"
    )
    parity_latency_sampling_declared = _bool(
        row.get("parity_latency_sampling_audit_enabled", False)
    )
    parity_latency_sampling_configured = (
        "latency_jitter_us" in manifest_parameters
        and "latency_seed" in manifest_parameters
    )
    parity_latency_sampling_enabled = bool(
        parity_execution_run_detected
        and (
            parity_latency_sampling_declared
            or parity_latency_sampling_configured
        )
    )
    parity_execution_guard_enabled = bool(
        parity_execution_guard_declared
        or parity_execution_run_detected
        or parity_execution_guard_path.exists()
        or parity_legging_path.exists()
    )
    parity_execution_ioc_batch_preflight_declared = _bool(
        row.get(
            "parity_execution_ioc_batch_preflight_enabled",
            False,
        )
    )
    parity_execution_edge_revalidation_declared = _bool(
        row.get(
            "parity_execution_edge_revalidation_enabled",
            False,
        )
    )
    parity_execution_signal_source_causality_declared = _bool(
        row.get(
            "parity_execution_signal_source_causality_enabled",
            False,
        )
    )
    parity_execution_realized_edge_declared = _bool(
        row.get(
            "parity_execution_realized_edge_enabled",
            False,
        )
    )
    parity_execution_order_timing_declared = _bool(
        row.get(
            "parity_execution_order_timing_enabled",
            False,
        )
    )
    parity_execution_ioc_arrival_audit_declared = _bool(
        row.get(
            "parity_execution_ioc_arrival_audit_enabled",
            False,
        )
    )
    parity_execution_ioc_arrival_event_lineage_declared = _bool(
        row.get(
            "parity_execution_ioc_arrival_event_lineage_enabled",
            False,
        )
    )
    parity_execution_ioc_batch_preflight_enabled = bool(
        parity_execution_guard_enabled
    )
    parity_execution_max_leg_book_age_ns = _int(
        row,
        "parity_execution_max_leg_book_age_ns",
    )
    parity_execution_max_leg_book_skew_ns = _int(
        row,
        "parity_execution_max_leg_book_skew_ns",
    )
    parity_guard_passed_raw = parity_execution_guard.get(
        "guard_passed",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_guard_passed = parity_guard_passed_raw.map(_bool)
    parity_guard_routing_complete_raw = parity_execution_guard.get(
        "routing_complete",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_guard_routing_complete = (
        parity_guard_routing_complete_raw.map(_bool)
    )
    parity_guard_reason_raw = parity_execution_guard.get(
        "guard_reason",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_guard_reasons = (
        parity_guard_reason_raw.astype("string").fillna("").str.strip()
    )
    parity_routing_status_raw = parity_execution_guard.get(
        "routing_status",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_routing_status = (
        parity_routing_status_raw.astype("string").fillna("").str.strip()
    )
    parity_guard_orders_requested = pd.to_numeric(
        parity_execution_guard.get(
            "orders_requested",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_guard_orders_accepted = pd.to_numeric(
        parity_execution_guard.get(
            "orders_accepted",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_preflight_enabled_raw = parity_execution_guard.get(
        "ioc_batch_preflight_enabled",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_preflight_enabled = parity_preflight_enabled_raw.map(_bool)
    parity_preflight_attempted_raw = parity_execution_guard.get(
        "ioc_batch_preflight_attempted",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_preflight_attempted = (
        parity_preflight_attempted_raw.map(_bool)
    )
    parity_preflight_passed_raw = parity_execution_guard.get(
        "ioc_batch_preflight_passed",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_preflight_passed = parity_preflight_passed_raw.map(_bool)
    parity_preflight_reason_raw = parity_execution_guard.get(
        "ioc_batch_preflight_reason",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_preflight_reasons = (
        parity_preflight_reason_raw.astype("string")
        .fillna("")
        .str.strip()
    )
    parity_capacity_checked_raw = parity_execution_guard.get(
        "ioc_batch_preflight_visible_capacity_checked",
        pd.Series(np.nan, index=parity_execution_guard.index),
    )
    parity_capacity_checked = parity_capacity_checked_raw.map(_bool)
    parity_capacity_ratio = pd.to_numeric(
        parity_execution_guard.get(
            "ioc_batch_preflight_min_visible_fill_ratio",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_capacity_instrument_raw = parity_execution_guard.get(
        "ioc_batch_preflight_limiting_instrument_id",
        pd.Series(
            np.nan,
            index=parity_execution_guard.index,
        ),
    )
    parity_capacity_instruments = (
        parity_capacity_instrument_raw.astype("string")
        .fillna("")
        .str.strip()
    )
    parity_capacity_requested = pd.to_numeric(
        parity_execution_guard.get(
            "ioc_batch_preflight_requested_qty",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_capacity_available = pd.to_numeric(
        parity_execution_guard.get(
            "ioc_batch_preflight_available_qty",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_capacity_touch_price = pd.to_numeric(
        parity_execution_guard.get(
            "ioc_batch_preflight_touch_price",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_capacity_limit_price = pd.to_numeric(
        parity_execution_guard.get(
            "ioc_batch_preflight_limit_price",
            pd.Series(np.nan, index=parity_execution_guard.index),
        ),
        errors="coerce",
    )
    parity_known_guard_reasons = {
        "signal_age_exceeded",
        "nonpositive_quantity",
        "unsupported_direction",
        "missing_leg_mapping",
        "unknown_leg_instrument",
        "missing_leg_book",
        "negative_leg_book_age",
        "stale_leg_book",
        "leg_book_skew_exceeded",
        "signal_source_books_pending",
        "execution_edge_below_threshold",
        "ioc_batch_preflight_rejected",
        "ready",
    }
    parity_known_routing_statuses = {
        "not_attempted",
        "complete",
        "partial",
        "rejected",
    }
    parity_execution_guard_unclassified_rows = int(
        (
            ~parity_guard_reasons.isin(parity_known_guard_reasons)
            | ~parity_routing_status.isin(
                parity_known_routing_statuses
            )
        ).sum()
    )
    parity_guard_missing_evidence = (
        _boolean_evidence_missing(parity_guard_passed_raw)
        | _boolean_evidence_missing(
            parity_guard_routing_complete_raw
        )
        | parity_guard_reason_raw.isna()
        | parity_guard_reasons.eq("")
        | parity_routing_status_raw.isna()
        | parity_routing_status.eq("")
        | parity_guard_orders_requested.isna()
        | parity_guard_orders_accepted.isna()
    )
    parity_preflight_missing_evidence = (
        _boolean_evidence_missing(parity_preflight_enabled_raw)
        | _boolean_evidence_missing(parity_preflight_attempted_raw)
        | _boolean_evidence_missing(parity_preflight_passed_raw)
        | parity_preflight_reason_raw.isna()
        | parity_preflight_reasons.eq("")
    )
    parity_preflight_consistency_violation = (
        ~parity_preflight_enabled
        | (
            parity_preflight_attempted
            & parity_preflight_passed
            & ~parity_preflight_reasons.eq("passed")
        )
        | (
            parity_preflight_attempted
            & ~parity_preflight_passed
            & parity_preflight_reasons.isin(
                {"passed", "not_attempted"}
            )
        )
        | (
            ~parity_preflight_attempted
            & (
                parity_preflight_passed
                | ~parity_preflight_reasons.eq("not_attempted")
            )
        )
        | (
            parity_guard_passed
            & (
                ~parity_preflight_attempted
                | ~parity_preflight_passed
                | ~parity_preflight_reasons.eq("passed")
            )
        )
        | (
            parity_guard_reasons.eq(
                "ioc_batch_preflight_rejected"
            )
            & (
                ~parity_preflight_attempted
                | parity_preflight_passed
                | parity_preflight_reasons.isin(
                    {"passed", "not_attempted"}
                )
            )
        )
        | (
            ~parity_guard_passed
            & ~parity_guard_reasons.eq(
                "ioc_batch_preflight_rejected"
            )
            & (
                parity_preflight_attempted
                | parity_preflight_passed
                | ~parity_preflight_reasons.eq("not_attempted")
            )
        )
    )
    parity_execution_ioc_batch_preflight_missing_evidence_rows = (
        int(parity_preflight_missing_evidence.sum())
    )
    parity_execution_ioc_batch_preflight_consistency_violations = (
        int(
            (
                parity_preflight_consistency_violation
                & ~parity_preflight_missing_evidence
            ).sum()
        )
    )
    parity_capacity_passed = (
        parity_preflight_attempted & parity_preflight_passed
    )
    parity_capacity_not_marketable = parity_preflight_reasons.eq(
        "visible_ioc_not_marketable"
    )
    parity_capacity_shortfall = parity_preflight_reasons.eq(
        "visible_ioc_capacity_shortfall"
    )
    parity_capacity_relevant = (
        parity_capacity_passed
        | parity_capacity_not_marketable
        | parity_capacity_shortfall
    )
    parity_capacity_missing_evidence = parity_capacity_relevant & (
        _boolean_evidence_missing(parity_capacity_checked_raw)
        | parity_capacity_ratio.isna()
        | parity_capacity_instrument_raw.isna()
        | parity_capacity_instruments.eq("")
        | parity_capacity_requested.isna()
        | parity_capacity_available.isna()
        | parity_capacity_touch_price.isna()
        | parity_capacity_limit_price.isna()
    )
    parity_directions = (
        parity_execution_guard.get(
            "direction",
            pd.Series(
                np.nan,
                index=parity_execution_guard.index,
            ),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )
    parity_call_ids = (
        parity_execution_guard.get(
            "call_instrument_id",
            pd.Series(
                np.nan,
                index=parity_execution_guard.index,
            ),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )
    parity_put_ids = (
        parity_execution_guard.get(
            "put_instrument_id",
            pd.Series(
                np.nan,
                index=parity_execution_guard.index,
            ),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )
    parity_future_ids = (
        parity_execution_guard.get(
            "future_instrument_id",
            pd.Series(
                np.nan,
                index=parity_execution_guard.index,
            ),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )
    parity_capacity_is_call = (
        parity_capacity_instruments.eq(parity_call_ids)
        & parity_capacity_instruments.ne("")
    )
    parity_capacity_is_put_or_future = (
        (
            parity_capacity_instruments.eq(parity_put_ids)
            | parity_capacity_instruments.eq(parity_future_ids)
        )
        & parity_capacity_instruments.ne("")
    )
    parity_capacity_side = pd.Series(
        0,
        index=parity_execution_guard.index,
        dtype="int64",
    )
    buy_synthetic = parity_directions.eq(
        "buy_synthetic_sell_future"
    )
    sell_synthetic = parity_directions.eq(
        "sell_synthetic_buy_future"
    )
    parity_capacity_side.loc[
        (buy_synthetic & parity_capacity_is_call)
        | (sell_synthetic & parity_capacity_is_put_or_future)
    ] = 1
    parity_capacity_side.loc[
        (sell_synthetic & parity_capacity_is_call)
        | (buy_synthetic & parity_capacity_is_put_or_future)
    ] = -1
    parity_capacity_marketable = (
        (
            parity_capacity_side.eq(1)
            & parity_capacity_limit_price.ge(
                parity_capacity_touch_price
            )
        )
        | (
            parity_capacity_side.eq(-1)
            & parity_capacity_limit_price.le(
                parity_capacity_touch_price
            )
        )
    )
    parity_capacity_expected_ratio = (
        parity_capacity_available
        / parity_capacity_requested.where(
            parity_capacity_requested.gt(0)
        )
    )
    parity_capacity_common_violation = (
        ~parity_capacity_checked
        | parity_capacity_side.eq(0)
        | parity_capacity_requested.le(0)
        | parity_capacity_requested.mod(1).ne(0)
        | parity_capacity_available.lt(0)
        | parity_capacity_ratio.lt(0)
        | ~np.isfinite(parity_capacity_ratio)
        | ~np.isfinite(parity_capacity_available)
        | ~np.isfinite(parity_capacity_touch_price)
        | ~np.isfinite(parity_capacity_limit_price)
        | (
            parity_capacity_ratio
            .sub(parity_capacity_expected_ratio)
            .abs()
            .gt(1e-9)
        )
    )
    parity_capacity_consistency_violation = (
        parity_capacity_common_violation
        | (
            parity_capacity_passed
            & (
                ~parity_capacity_marketable
                | parity_capacity_ratio.lt(1.0)
                | parity_capacity_available.lt(
                    parity_capacity_requested
                )
            )
        )
        | (
            parity_capacity_not_marketable
            & (
                parity_capacity_marketable
                | parity_capacity_ratio.ne(0.0)
            )
        )
        | (
            parity_capacity_shortfall
            & (
                ~parity_capacity_marketable
                | parity_capacity_ratio.ge(1.0)
                | parity_capacity_available.ge(
                    parity_capacity_requested
                )
            )
        )
    )
    parity_execution_ioc_visible_capacity_missing_evidence_rows = (
        int(parity_capacity_missing_evidence.sum())
    )
    parity_execution_ioc_visible_capacity_consistency_violations = (
        int(
            (
                parity_capacity_relevant
                & parity_capacity_consistency_violation
                & ~parity_capacity_missing_evidence
            ).sum()
        )
    )
    parity_edge_metrics = _parity_edge_revalidation_metrics(
        parity_execution_guard,
        enabled=parity_execution_guard_enabled,
    )
    parity_signal_source_metrics = _parity_signal_source_metrics(
        parity_execution_guard,
        enabled=parity_execution_guard_enabled,
    )
    parity_realized_edge_metrics = _parity_realized_edge_metrics(
        parity_legging,
        parity_execution_guard,
        replay_fills,
        enabled=parity_execution_realized_edge_declared,
        fills_present=fills_path.exists(),
    )
    parity_order_timing_metrics = _parity_order_timing_metrics(
        parity_legging,
        replay_fills,
        order_submissions,
        enabled=parity_execution_order_timing_declared,
        order_submissions_present=order_submissions_path.exists(),
    )
    parity_latency_sampling_metrics = (
        _parity_latency_sampling_metrics(
            feed_deliveries,
            order_submissions,
            parameters=manifest_parameters,
            enabled=parity_latency_sampling_enabled,
            feed_deliveries_present=feed_deliveries_path.exists(),
            order_submissions_present=(
                order_submissions_path.exists()
            ),
        )
    )
    parity_ioc_arrival_metrics = _parity_ioc_arrival_metrics(
        parity_legging,
        replay_fills,
        order_submissions,
        ioc_arrival_audit,
        enabled=parity_execution_ioc_arrival_audit_declared,
        event_lineage_enabled=(
            parity_execution_ioc_arrival_event_lineage_declared
        ),
        audit_present=ioc_arrival_audit_path.exists(),
    )
    parity_routed_capacity_ratios = parity_capacity_ratio.loc[
        parity_capacity_passed
    ].dropna()
    parity_expected_routing_status = pd.Series(
        "not_attempted",
        index=parity_execution_guard.index,
        dtype="object",
    )
    parity_expected_routing_status.loc[
        parity_guard_passed & parity_guard_orders_accepted.eq(0)
    ] = "rejected"
    parity_expected_routing_status.loc[
        parity_guard_passed
        & parity_guard_orders_accepted.gt(0)
        & parity_guard_orders_accepted.lt(3)
    ] = "partial"
    parity_expected_routing_status.loc[
        parity_guard_passed & parity_guard_orders_accepted.eq(3)
    ] = "complete"
    parity_guard_consistency_violation = (
        (parity_guard_passed & ~parity_guard_reasons.eq("ready"))
        | (
            parity_guard_passed
            & parity_guard_orders_requested.ne(3)
        )
        | (
            ~parity_guard_passed
            & (
                parity_guard_orders_requested.ne(0)
                | parity_guard_orders_accepted.ne(0)
                | parity_guard_routing_complete
            )
        )
        | parity_guard_orders_accepted.lt(0)
        | parity_guard_orders_accepted.gt(3)
        | parity_guard_orders_accepted.mod(1).ne(0)
        | parity_guard_routing_complete.ne(
            parity_guard_passed
            & parity_guard_orders_accepted.eq(3)
        )
        | parity_routing_status.ne(parity_expected_routing_status)
    )
    parity_execution_guard_missing_evidence_rows = int(
        parity_guard_missing_evidence.sum()
    )
    parity_execution_guard_consistency_violations = int(
        (
            parity_guard_consistency_violation
            & ~parity_guard_missing_evidence
        ).sum()
    )
    parity_passed_guard_rows = parity_execution_guard.loc[
        parity_guard_passed
    ]
    parity_guard_leg_ages = pd.DataFrame(
        {
            column: pd.to_numeric(
                parity_passed_guard_rows.get(
                    column,
                    pd.Series(
                        index=parity_passed_guard_rows.index,
                        dtype="float64",
                    ),
                ),
                errors="coerce",
            )
            for column in [
                "call_book_age_ns",
                "put_book_age_ns",
                "future_book_age_ns",
            ]
        },
        index=parity_passed_guard_rows.index,
    )
    parity_guard_skew = pd.to_numeric(
        parity_passed_guard_rows.get(
            "leg_book_skew_ns",
            pd.Series(
                index=parity_passed_guard_rows.index,
                dtype="float64",
            ),
        ),
        errors="coerce",
    )
    parity_execution_guard_passed_missing_age_rows = int(
        (
            parity_guard_leg_ages.isna().any(axis=1)
            | parity_guard_skew.isna()
        ).sum()
    )
    parity_execution_guard_age_violations = int(
        (
            parity_guard_leg_ages.lt(0)
            | parity_guard_leg_ages.gt(
                parity_execution_max_leg_book_age_ns
            )
        ).any(axis=1).sum()
    )
    parity_execution_guard_skew_violations = int(
        (
            parity_guard_skew.lt(0)
            | parity_guard_skew.gt(
                parity_execution_max_leg_book_skew_ns
            )
        ).sum()
    )
    parity_guard_max_ages = (
        parity_guard_leg_ages.max(axis=1).dropna()
        if not parity_guard_leg_ages.empty
        else pd.Series(dtype="float64")
    )
    parity_observed_guard_skew = parity_guard_skew.dropna()
    parity_expected_order_count = pd.to_numeric(
        parity_legging.get(
            "expected_order_count",
            pd.Series(np.nan, index=parity_legging.index),
        ),
        errors="coerce",
    )
    parity_order_count = pd.to_numeric(
        parity_legging.get(
            "order_count",
            pd.Series(np.nan, index=parity_legging.index),
        ),
        errors="coerce",
    )
    parity_route_rejected_legs = pd.to_numeric(
        parity_legging.get(
            "route_rejection_count",
            pd.Series(np.nan, index=parity_legging.index),
        ),
        errors="coerce",
    )
    parity_fully_filled_leg_count = pd.to_numeric(
        parity_legging.get(
            "fully_filled_leg_count",
            pd.Series(np.nan, index=parity_legging.index),
        ),
        errors="coerce",
    )
    parity_unfilled_legs = pd.to_numeric(
        parity_legging.get(
            "unfilled_leg_count",
            pd.Series(np.nan, index=parity_legging.index),
        ),
        errors="coerce",
    )
    parity_legging_routing_complete_raw = parity_legging.get(
        "routing_complete",
        pd.Series(np.nan, index=parity_legging.index),
    )
    parity_legging_routing_complete = (
        parity_legging_routing_complete_raw.map(_bool)
    )
    parity_legging_fills_complete_raw = parity_legging.get(
        "fills_complete",
        pd.Series(np.nan, index=parity_legging.index),
    )
    parity_legging_fills_complete = (
        parity_legging_fills_complete_raw.map(_bool)
    )
    parity_legging_partial_raw = parity_legging.get(
        "partial",
        pd.Series(np.nan, index=parity_legging.index),
    )
    parity_legging_partial = parity_legging_partial_raw.map(_bool)
    parity_legging_missing_evidence = (
        parity_expected_order_count.isna()
        | parity_order_count.isna()
        | parity_route_rejected_legs.isna()
        | parity_fully_filled_leg_count.isna()
        | parity_unfilled_legs.isna()
        | _boolean_evidence_missing(
            parity_legging_routing_complete_raw
        )
        | _boolean_evidence_missing(
            parity_legging_fills_complete_raw
        )
        | _boolean_evidence_missing(parity_legging_partial_raw)
    )
    parity_legging_consistency_violation = (
        parity_expected_order_count.ne(3)
        | parity_order_count.lt(0)
        | parity_order_count.gt(parity_expected_order_count)
        | parity_order_count.mod(1).ne(0)
        | parity_route_rejected_legs.ne(
            parity_expected_order_count - parity_order_count
        )
        | parity_fully_filled_leg_count.lt(0)
        | parity_fully_filled_leg_count.gt(parity_order_count)
        | parity_fully_filled_leg_count.mod(1).ne(0)
        | parity_unfilled_legs.ne(
            parity_expected_order_count
            - parity_fully_filled_leg_count
        )
        | parity_legging_routing_complete.ne(
            parity_order_count.eq(parity_expected_order_count)
        )
        | parity_legging_fills_complete.ne(
            parity_fully_filled_leg_count.eq(
                parity_expected_order_count
            )
        )
        | parity_legging_partial.ne(
            ~(
                parity_legging_routing_complete
                & parity_legging_fills_complete
            )
        )
    )
    parity_execution_legging_missing_evidence_rows = int(
        parity_legging_missing_evidence.sum()
    )
    parity_execution_legging_consistency_violations = int(
        (
            parity_legging_consistency_violation
            & ~parity_legging_missing_evidence
        ).sum()
    )
    parity_legging_complete = (
        ~parity_legging_missing_evidence
        & ~parity_legging_consistency_violation
        & parity_legging_routing_complete
        & parity_legging_fills_complete
    )
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
    lot_conserving_fills_enabled = _bool(
        row.get("lot_conserving_fills_enabled", False)
    )
    causal_event_ordering_enabled = _bool(
        row.get("causal_event_ordering_enabled", False)
    )
    cancel_lifecycle_tracking_enabled = _bool(
        row.get("cancel_lifecycle_tracking_enabled", False)
    )
    cancel_requests = _int(row, "cancel_requests")
    cancel_effective_events = _int(row, "cancel_effective_events")
    cancel_effective_after_partial_fill_events = _int(
        row,
        "cancel_effective_after_partial_fill_events",
    )
    cancel_filled_before_effective_events = _int(
        row,
        "cancel_filled_before_effective_events",
    )
    cancel_closed_before_effective_events = _int(
        row,
        "cancel_closed_before_effective_events",
    )
    cancel_pending_at_replay_end_events = _int(
        row,
        "cancel_pending_at_replay_end_events",
    )
    cancel_inflight_filled_qty = _int(
        row,
        "cancel_inflight_filled_qty",
    )
    order_horizon_tracking_enabled = _bool(
        row.get("order_horizon_tracking_enabled", False)
    )
    open_orders_at_replay_end = _int(
        row,
        "open_orders_at_replay_end",
    )
    open_order_qty_at_replay_end = _int(
        row,
        "open_order_qty_at_replay_end",
    )
    pending_activation_orders_at_replay_end = _int(
        row,
        "pending_activation_orders_at_replay_end",
    )
    active_ioc_orders_at_replay_end = _int(
        row,
        "active_ioc_orders_at_replay_end",
    )
    active_limit_orders_at_replay_end = _int(
        row,
        "active_limit_orders_at_replay_end",
    )
    cancel_pending_orders_at_replay_end = _int(
        row,
        "cancel_pending_orders_at_replay_end",
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
        "input_quarantine_tracking_enabled": (
            input_quarantine_tracking_enabled
        ),
        "input_dataset_count": input_dataset_count,
        "input_total_rows": input_total_rows,
        "input_kept_rows": input_kept_rows,
        "input_dropped_rows": input_dropped_rows,
        "input_integrity_dropped_rows": input_integrity_dropped_rows,
        "input_session_filtered_rows": input_session_filtered_rows,
        "input_empty_datasets": input_empty_datasets,
        "parity_futures_asof_freshness_enabled": (
            parity_futures_asof_freshness_enabled
        ),
        "parity_futures_max_quote_age_ns": (
            parity_futures_max_quote_age_ns
        ),
        "parity_futures_join_audit_present": (
            parity_futures_join_audit_path.exists()
        ),
        "parity_futures_signals_present": parity_signals_path.exists(),
        "parity_futures_join_rows": int(
            len(parity_futures_join_audit)
        ),
        "parity_futures_fresh_join_rows": (
            parity_futures_fresh_join_rows
        ),
        "parity_futures_stale_join_rows": (
            parity_futures_stale_join_rows
        ),
        "parity_futures_unmatched_join_rows": (
            parity_futures_unmatched_join_rows
        ),
        "parity_futures_unclassified_join_rows": (
            parity_futures_unclassified_join_rows
        ),
        "parity_futures_signal_count": int(len(parity_signals)),
        "parity_futures_signals_without_age": int(
            parity_signal_ages.isna().sum()
        ),
        "parity_futures_signal_age_violations": (
            parity_futures_signal_age_violations
        ),
        "parity_futures_max_signal_age_ns": int(
            parity_observed_signal_ages.max()
        )
        if not parity_observed_signal_ages.empty
        else 0,
        "parity_execution_guard_enabled": (
            parity_execution_guard_enabled
        ),
        "parity_execution_guard_declared": (
            parity_execution_guard_declared
        ),
        "parity_execution_run_detected": (
            parity_execution_run_detected
        ),
        "parity_latency_sampling_declared": (
            parity_latency_sampling_declared
        ),
        **parity_latency_sampling_metrics,
        "parity_execution_max_leg_book_age_ns": (
            parity_execution_max_leg_book_age_ns
        ),
        "parity_execution_max_leg_book_skew_ns": (
            parity_execution_max_leg_book_skew_ns
        ),
        "parity_execution_guard_present": (
            parity_execution_guard_path.exists()
        ),
        "parity_execution_legging_present": (
            parity_legging_path.exists()
        ),
        "parity_execution_guard_rows": int(
            len(parity_execution_guard)
        ),
        "parity_execution_guard_passed_attempts": int(
            parity_guard_passed.sum()
        ),
        "parity_execution_guard_deferred_attempts": int(
            (~parity_guard_passed).sum()
        ),
        "parity_execution_edge_revalidation_declared": (
            parity_execution_edge_revalidation_declared
        ),
        "parity_execution_signal_source_causality_declared": (
            parity_execution_signal_source_causality_declared
        ),
        **parity_signal_source_metrics,
        **parity_edge_metrics,
        "parity_execution_realized_edge_declared": (
            parity_execution_realized_edge_declared
        ),
        **parity_realized_edge_metrics,
        "parity_execution_order_timing_declared": (
            parity_execution_order_timing_declared
        ),
        **parity_order_timing_metrics,
        "parity_execution_ioc_arrival_audit_declared": (
            parity_execution_ioc_arrival_audit_declared
        ),
        "parity_execution_ioc_arrival_event_lineage_declared": (
            parity_execution_ioc_arrival_event_lineage_declared
        ),
        **parity_ioc_arrival_metrics,
        "parity_execution_ioc_batch_preflight_enabled": (
            parity_execution_ioc_batch_preflight_enabled
        ),
        "parity_execution_ioc_batch_preflight_declared": (
            parity_execution_ioc_batch_preflight_declared
        ),
        "parity_execution_ioc_batch_preflight_attempts": int(
            parity_preflight_attempted.sum()
        ),
        "parity_execution_ioc_batch_preflight_passed_attempts": int(
            (
                parity_preflight_attempted
                & parity_preflight_passed
            ).sum()
        ),
        "parity_execution_ioc_batch_preflight_rejected_attempts": (
            int(
                (
                    parity_preflight_attempted
                    & ~parity_preflight_passed
                ).sum()
            )
        ),
        "parity_execution_ioc_batch_preflight_missing_evidence_rows": (
            parity_execution_ioc_batch_preflight_missing_evidence_rows
        ),
        "parity_execution_ioc_batch_preflight_consistency_violations": (
            parity_execution_ioc_batch_preflight_consistency_violations
        ),
        "parity_execution_ioc_visible_not_marketable_attempts": int(
            parity_capacity_not_marketable.sum()
        ),
        "parity_execution_ioc_visible_capacity_shortfall_attempts": (
            int(parity_capacity_shortfall.sum())
        ),
        "parity_execution_ioc_visible_capacity_missing_evidence_rows": (
            parity_execution_ioc_visible_capacity_missing_evidence_rows
        ),
        "parity_execution_ioc_visible_capacity_consistency_violations": (
            parity_execution_ioc_visible_capacity_consistency_violations
        ),
        "parity_execution_min_routed_visible_fill_ratio": (
            float(parity_routed_capacity_ratios.min())
            if not parity_routed_capacity_ratios.empty
            else 0.0
        ),
        "parity_execution_guard_missing_evidence_rows": (
            parity_execution_guard_missing_evidence_rows
        ),
        "parity_execution_guard_unclassified_rows": (
            parity_execution_guard_unclassified_rows
        ),
        "parity_execution_guard_consistency_violations": (
            parity_execution_guard_consistency_violations
        ),
        "parity_execution_guard_passed_missing_age_rows": (
            parity_execution_guard_passed_missing_age_rows
        ),
        "parity_execution_guard_age_violations": (
            parity_execution_guard_age_violations
        ),
        "parity_execution_guard_skew_violations": (
            parity_execution_guard_skew_violations
        ),
        "parity_execution_routing_incomplete_attempts": int(
            (
                parity_guard_passed
                & ~parity_routing_status.eq("complete")
            ).sum()
        ),
        "parity_execution_routing_complete_attempts": int(
            (
                parity_guard_passed
                & parity_routing_status.eq("complete")
            ).sum()
        ),
        "parity_execution_signal_expiry_events": int(
            (parity_guard_reasons == "signal_age_exceeded").sum()
        ),
        "parity_execution_stale_book_attempts": int(
            (parity_guard_reasons == "stale_leg_book").sum()
        ),
        "parity_execution_negative_book_age_attempts": int(
            (
                parity_guard_reasons
                == "negative_leg_book_age"
            ).sum()
        ),
        "parity_execution_skew_attempts": int(
            (
                parity_guard_reasons
                == "leg_book_skew_exceeded"
            ).sum()
        ),
        "parity_execution_max_routed_book_age_ns": int(
            parity_guard_max_ages.max()
        )
        if not parity_guard_max_ages.empty
        else 0,
        "parity_execution_max_routed_book_skew_ns": int(
            parity_observed_guard_skew.max()
        )
        if not parity_observed_guard_skew.empty
        else 0,
        "parity_execution_count": int(len(parity_legging)),
        "parity_execution_legging_missing_evidence_rows": (
            parity_execution_legging_missing_evidence_rows
        ),
        "parity_execution_legging_consistency_violations": (
            parity_execution_legging_consistency_violations
        ),
        "parity_execution_complete_count": int(
            parity_legging_complete.sum()
        ),
        "parity_execution_incomplete_count": int(
            (~parity_legging_complete).sum()
        ),
        "parity_execution_route_rejected_legs": int(
            parity_route_rejected_legs.fillna(0).sum()
        ),
        "parity_execution_unfilled_legs": int(
            parity_unfilled_legs.fillna(0).sum()
        ),
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
        "lot_conserving_fills_enabled": lot_conserving_fills_enabled,
        "causal_event_ordering_enabled": causal_event_ordering_enabled,
        "cancel_lifecycle_tracking_enabled": (
            cancel_lifecycle_tracking_enabled
        ),
        "cancel_requests": cancel_requests,
        "cancel_effective_events": cancel_effective_events,
        "cancel_effective_after_partial_fill_events": (
            cancel_effective_after_partial_fill_events
        ),
        "cancel_filled_before_effective_events": (
            cancel_filled_before_effective_events
        ),
        "cancel_closed_before_effective_events": (
            cancel_closed_before_effective_events
        ),
        "cancel_pending_at_replay_end_events": (
            cancel_pending_at_replay_end_events
        ),
        "cancel_inflight_filled_qty": cancel_inflight_filled_qty,
        "order_horizon_tracking_enabled": (
            order_horizon_tracking_enabled
        ),
        "open_orders_at_replay_end": open_orders_at_replay_end,
        "open_order_qty_at_replay_end": open_order_qty_at_replay_end,
        "pending_activation_orders_at_replay_end": (
            pending_activation_orders_at_replay_end
        ),
        "active_ioc_orders_at_replay_end": (
            active_ioc_orders_at_replay_end
        ),
        "active_limit_orders_at_replay_end": (
            active_limit_orders_at_replay_end
        ),
        "cancel_pending_orders_at_replay_end": (
            cancel_pending_orders_at_replay_end
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


def _parity_signal_source_metrics(
    guard: pd.DataFrame,
    *,
    enabled: bool,
) -> dict[str, int | bool]:
    checks = 0
    ready_attempts = 0
    pending_attempts = 0
    missing_rows = 0
    consistency_violations = 0
    observed_lags: list[int] = []

    for _, row in guard.iterrows():
        enabled_raw = row.get(
            "signal_source_causality_enabled",
            np.nan,
        )
        checked_raw = row.get(
            "signal_source_books_checked",
            np.nan,
        )
        ready_raw = row.get(
            "signal_source_books_ready",
            np.nan,
        )
        checked = _bool(checked_raw)
        ready = _bool(ready_raw)
        edge_checked = _bool(
            row.get("edge_revalidation_checked", False)
        )
        preflight_attempted = _bool(
            row.get("ioc_batch_preflight_attempted", False)
        )
        guard_passed = _bool(row.get("guard_passed", False))
        reason = str(row.get("guard_reason", "")).strip()
        pending = reason == "signal_source_books_pending"
        relevant = (
            checked
            or edge_checked
            or preflight_attempted
            or guard_passed
            or pending
        )
        if not relevant:
            continue

        checks += int(checked)
        ready_attempts += int(checked and ready)
        pending_attempts += int(pending)
        bool_missing = bool(
            _boolean_evidence_missing(
                pd.Series(
                    [enabled_raw, checked_raw, ready_raw]
                )
            ).any()
        )
        signal_age = pd.to_numeric(
            row.get("signal_age_ns", np.nan),
            errors="coerce",
        )
        call_age = pd.to_numeric(
            row.get("call_book_age_ns", np.nan),
            errors="coerce",
        )
        put_age = pd.to_numeric(
            row.get("put_book_age_ns", np.nan),
            errors="coerce",
        )
        reported_lag = pd.to_numeric(
            row.get("signal_source_max_lag_ns", np.nan),
            errors="coerce",
        )
        if (
            bool_missing
            or pd.isna(signal_age)
            or pd.isna(call_age)
            or pd.isna(put_age)
            or pd.isna(reported_lag)
        ):
            missing_rows += 1
            continue

        signal_age_value = int(signal_age)
        call_age_value = int(call_age)
        put_age_value = int(put_age)
        lag_value = float(reported_lag)
        expected_lag = max(
            call_age_value - signal_age_value,
            put_age_value - signal_age_value,
            0,
        )
        expected_ready = expected_lag == 0
        violation = (
            not _bool(enabled_raw)
            or not checked
            or lag_value < 0
            or lag_value % 1 != 0
            or lag_value != expected_lag
            or ready != expected_ready
            or (pending and ready)
            or (not ready and not pending)
            or (
                (edge_checked or preflight_attempted or guard_passed)
                and not ready
            )
        )
        consistency_violations += int(violation)
        if checked:
            observed_lags.append(int(lag_value))

    return {
        "parity_execution_signal_source_causality_enabled": bool(
            enabled
        ),
        "parity_execution_signal_source_checks": checks,
        "parity_execution_signal_source_ready_attempts": (
            ready_attempts
        ),
        "parity_execution_signal_source_pending_attempts": (
            pending_attempts
        ),
        "parity_execution_signal_source_missing_evidence_rows": (
            missing_rows
        ),
        "parity_execution_signal_source_consistency_violations": (
            consistency_violations
        ),
        "parity_execution_max_signal_source_lag_ns": (
            max(observed_lags)
            if observed_lags
            else 0
        ),
    }


def _parity_edge_revalidation_metrics(
    guard: pd.DataFrame,
    *,
    enabled: bool,
) -> dict[str, int | float | bool]:
    attempts = 0
    passed_attempts = 0
    rejected_attempts = 0
    missing_rows = 0
    consistency_violations = 0
    routed_net_edges: list[float] = []
    observed_edge_decay: list[float] = []
    numeric_columns = [
        "strike",
        "edge_revalidation_qty",
        "signal_net_edge",
        "decision_call_side",
        "decision_call_price",
        "decision_put_side",
        "decision_put_price",
        "decision_future_side",
        "decision_future_price",
        "decision_contract_multiplier",
        "decision_edge_per_unit",
        "decision_gross_edge",
        "decision_call_cost",
        "decision_put_cost",
        "decision_future_cost",
        "decision_total_cost",
        "decision_net_edge",
        "decision_min_net_edge",
    ]

    for _, row in guard.iterrows():
        checked_raw = row.get(
            "edge_revalidation_checked",
            np.nan,
        )
        enabled_raw = row.get(
            "edge_revalidation_enabled",
            np.nan,
        )
        checked = _bool(checked_raw)
        preflight_attempted = _bool(
            row.get("ioc_batch_preflight_attempted", False)
        )
        guard_passed = _bool(row.get("guard_passed", False))
        reason = str(row.get("guard_reason", "")).strip()
        rejected = reason == "execution_edge_below_threshold"
        relevant = checked or preflight_attempted or rejected
        if not relevant:
            continue

        attempts += int(checked)
        passed_attempts += int(preflight_attempted)
        rejected_attempts += int(rejected)
        numbers = {
            column: pd.to_numeric(
                row.get(column, np.nan),
                errors="coerce",
            )
            for column in numeric_columns
        }
        direction = str(row.get("direction", "")).strip()
        boolean_missing = bool(
            _boolean_evidence_missing(
                pd.Series([enabled_raw, checked_raw])
            ).any()
        )
        if (
            boolean_missing
            or direction == ""
            or any(pd.isna(value) for value in numbers.values())
        ):
            missing_rows += 1
            continue

        values = {
            key: float(value)
            for key, value in numbers.items()
        }
        qty = values["edge_revalidation_qty"]
        strike = values["strike"]
        call_side = values["decision_call_side"]
        call_price = values["decision_call_price"]
        put_side = values["decision_put_side"]
        put_price = values["decision_put_price"]
        future_side = values["decision_future_side"]
        future_price = values["decision_future_price"]
        multiplier = values["decision_contract_multiplier"]
        signal_net_edge = values["signal_net_edge"]
        edge_per_unit = values["decision_edge_per_unit"]
        gross_edge = values["decision_gross_edge"]
        call_cost = values["decision_call_cost"]
        put_cost = values["decision_put_cost"]
        future_cost = values["decision_future_cost"]
        total_cost = values["decision_total_cost"]
        net_edge = values["decision_net_edge"]
        threshold = values["decision_min_net_edge"]

        if direction == "buy_synthetic_sell_future":
            expected_sides = (1.0, -1.0, -1.0)
            expected_edge_per_unit = (
                future_price
                - (call_price - put_price + strike)
            )
        elif direction == "sell_synthetic_buy_future":
            expected_sides = (-1.0, 1.0, 1.0)
            expected_edge_per_unit = (
                call_price - put_price + strike - future_price
            )
        else:
            expected_sides = (0.0, 0.0, 0.0)
            expected_edge_per_unit = float("nan")
        expected_gross_edge = (
            expected_edge_per_unit * qty * multiplier
        )
        expected_total_cost = call_cost + put_cost + future_cost
        expected_net_edge = expected_gross_edge - expected_total_cost
        finite = all(np.isfinite(value) for value in values.values())
        violation = (
            not _bool(enabled_raw)
            or not checked
            or direction not in {
                "buy_synthetic_sell_future",
                "sell_synthetic_buy_future",
            }
            or qty <= 0
            or qty % 1 != 0
            or strike <= 0
            or signal_net_edge <= 0
            or call_price <= 0
            or put_price <= 0
            or future_price <= 0
            or multiplier <= 0
            or call_cost < 0
            or put_cost < 0
            or future_cost < 0
            or total_cost < 0
            or threshold < 0
            or (call_side, put_side, future_side) != expected_sides
            or not finite
            or abs(edge_per_unit - expected_edge_per_unit) > 1e-9
            or abs(gross_edge - expected_gross_edge) > 1e-9
            or abs(total_cost - expected_total_cost) > 1e-9
            or abs(net_edge - expected_net_edge) > 1e-9
            or (
                checked
                and not preflight_attempted
                and not rejected
            )
            or (preflight_attempted and net_edge <= threshold)
            or (
                rejected
                and (
                    net_edge > threshold
                    or preflight_attempted
                    or guard_passed
                )
            )
        )
        consistency_violations += int(violation)
        if guard_passed:
            routed_net_edges.append(net_edge)
        if checked:
            observed_edge_decay.append(signal_net_edge - net_edge)

    return {
        "parity_execution_edge_revalidation_enabled": bool(enabled),
        "parity_execution_edge_revalidation_attempts": attempts,
        "parity_execution_edge_revalidation_passed_attempts": (
            passed_attempts
        ),
        "parity_execution_edge_revalidation_rejected_attempts": (
            rejected_attempts
        ),
        "parity_execution_edge_revalidation_missing_evidence_rows": (
            missing_rows
        ),
        "parity_execution_edge_revalidation_consistency_violations": (
            consistency_violations
        ),
        "parity_execution_min_routed_net_edge": (
            min(routed_net_edges)
            if routed_net_edges
            else 0.0
        ),
        "parity_execution_max_observed_edge_decay": (
            max(max(observed_edge_decay), 0.0)
            if observed_edge_decay
            else 0.0
        ),
    }


def _parity_realized_edge_metrics(
    legging: pd.DataFrame,
    guard: pd.DataFrame,
    fills: pd.DataFrame,
    *,
    enabled: bool,
    fills_present: bool,
) -> dict[str, int | float | bool]:
    evaluable_count = 0
    positive_count = 0
    nonpositive_count = 0
    missing_rows = 0
    consistency_violations = 0
    realized_net_edges: list[float] = []
    realized_edge_changes: list[float] = []
    fill_spans: list[int] = []
    first_fill_latencies: list[int] = []
    completion_latencies: list[int] = []
    fill_timing_evaluable_count = 0
    negative_fill_latency_count = 0
    seen_order_ids: set[int] = set()
    required_fill_columns = {
        "instrument_id",
        "ts_ns",
        "oid",
        "side",
        "qty",
        "price",
        "cost",
    }
    fill_columns_complete = required_fill_columns.issubset(
        fills.columns
    )
    fill_oids = (
        pd.to_numeric(fills["oid"], errors="coerce")
        if "oid" in fills.columns
        else pd.Series(np.nan, index=fills.index)
    )
    guard_signal_indices = pd.to_numeric(
        guard.get(
            "signal_index",
            pd.Series(np.nan, index=guard.index),
        ),
        errors="coerce",
    )
    guard_passed = guard.get(
        "guard_passed",
        pd.Series(False, index=guard.index),
    ).map(_bool)

    for _, row in legging.iterrows():
        row_missing = False
        violation = False
        bool_fields = {
            name: row.get(name, np.nan)
            for name in (
                "routing_complete",
                "fills_complete",
                "partial",
                "realized_edge_evidence_enabled",
                "realized_edge_evaluable",
                "realized_edge_positive",
            )
        }
        number_names = [
            "signal_index",
            "signal_ts_ns",
            "decision_ts_ns",
            "strike",
            "requested_qty",
            "fill_count",
            "filled_leg_count",
            "fully_filled_leg_count",
            "contract_multiplier",
            "decision_net_edge",
            "call_side",
            "call_limit_price",
            "call_filled_qty",
            "put_side",
            "put_limit_price",
            "put_filled_qty",
            "future_side",
            "future_limit_price",
            "future_filled_qty",
        ]
        numbers = {
            name: pd.to_numeric(
                row.get(name, np.nan),
                errors="coerce",
            )
            for name in number_names
        }
        direction = str(row.get("direction", "")).strip()
        instrument_ids = {
            leg: str(row.get(f"{leg}_instrument_id", "")).strip()
            for leg in ("call", "put", "future")
        }
        if (
            _boolean_evidence_missing(
                pd.Series(list(bool_fields.values()))
            ).any()
            or any(pd.isna(value) for value in numbers.values())
            or direction == ""
            or any(not value for value in instrument_ids.values())
        ):
            missing_rows += 1
            continue

        signal_index = float(numbers["signal_index"])
        signal_ts_ns = int(numbers["signal_ts_ns"])
        decision_ts_ns = int(numbers["decision_ts_ns"])
        requested_qty = float(numbers["requested_qty"])
        strike = float(numbers["strike"])
        multiplier = float(numbers["contract_multiplier"])
        decision_net_edge = float(numbers["decision_net_edge"])
        routing_complete = _bool(bool_fields["routing_complete"])
        fills_complete = _bool(bool_fields["fills_complete"])
        partial = _bool(bool_fields["partial"])
        outcome_enabled = _bool(
            bool_fields["realized_edge_evidence_enabled"]
        )
        evaluable = _bool(bool_fields["realized_edge_evaluable"])
        positive = _bool(bool_fields["realized_edge_positive"])
        if direction == "buy_synthetic_sell_future":
            expected_sides = {"call": 1, "put": -1, "future": -1}
        elif direction == "sell_synthetic_buy_future":
            expected_sides = {"call": -1, "put": 1, "future": 1}
        else:
            expected_sides = {"call": 0, "put": 0, "future": 0}
        violation = (
            not outcome_enabled
            or signal_index < 0
            or signal_index % 1 != 0
            or numbers["signal_ts_ns"] % 1 != 0
            or numbers["decision_ts_ns"] % 1 != 0
            or signal_ts_ns < 0
            or decision_ts_ns < signal_ts_ns
            or direction not in {
                "buy_synthetic_sell_future",
                "sell_synthetic_buy_future",
            }
            or strike <= 0
            or requested_qty <= 0
            or requested_qty % 1 != 0
            or multiplier <= 0
            or decision_net_edge <= 0
            or partial == (routing_complete and fills_complete)
            or evaluable != (routing_complete and fills_complete)
        )

        matching_signal_guards = guard.loc[
            guard_signal_indices.eq(int(signal_index))
        ]
        matching_passed_guards = matching_signal_guards.loc[
            guard_passed.loc[matching_signal_guards.index]
        ]
        matching_guard = (
            matching_passed_guards
            if len(matching_passed_guards) == 1
            else matching_signal_guards
            if len(matching_signal_guards) == 1
            else pd.DataFrame()
        )
        if len(matching_guard) != 1:
            violation = True
            row_missing = row_missing or matching_guard.empty
        else:
            guard_row = matching_guard.iloc[0]
            guard_number_names = [
                "signal_ts_ns",
                "decision_ts_ns",
                "strike",
                "edge_revalidation_qty",
                "decision_contract_multiplier",
                "decision_net_edge",
                "decision_call_side",
                "decision_call_price",
                "decision_put_side",
                "decision_put_price",
                "decision_future_side",
                "decision_future_price",
            ]
            guard_numbers = {
                name: pd.to_numeric(
                    guard_row.get(name, np.nan),
                    errors="coerce",
                )
                for name in guard_number_names
            }
            guard_instrument_ids = {
                leg: str(
                    guard_row.get(f"{leg}_instrument_id", "")
                ).strip()
                for leg in ("call", "put", "future")
            }
            if (
                any(
                    pd.isna(value)
                    for value in guard_numbers.values()
                )
                or any(
                    not value
                    for value in guard_instrument_ids.values()
                )
            ):
                row_missing = True
            else:
                violation = violation or (
                    str(guard_row.get("direction", "")).strip()
                    != direction
                    or guard_numbers["signal_ts_ns"] % 1 != 0
                    or int(guard_numbers["signal_ts_ns"])
                    != signal_ts_ns
                    or guard_numbers["decision_ts_ns"] % 1 != 0
                    or int(guard_numbers["decision_ts_ns"])
                    != decision_ts_ns
                    or float(guard_numbers["strike"]) != strike
                    or float(
                        guard_numbers["edge_revalidation_qty"]
                    )
                    != requested_qty
                    or float(
                        guard_numbers[
                            "decision_contract_multiplier"
                        ]
                    )
                    != multiplier
                    or abs(
                        float(guard_numbers["decision_net_edge"])
                        - decision_net_edge
                    )
                    > 1e-9
                    or guard_instrument_ids != instrument_ids
                    or float(
                        guard_numbers["decision_call_side"]
                    )
                    != float(numbers["call_side"])
                    or float(
                        guard_numbers["decision_call_price"]
                    )
                    != float(numbers["call_limit_price"])
                    or float(
                        guard_numbers["decision_put_side"]
                    )
                    != float(numbers["put_side"])
                    or float(
                        guard_numbers["decision_put_price"]
                    )
                    != float(numbers["put_limit_price"])
                    or float(
                        guard_numbers["decision_future_side"]
                    )
                    != float(numbers["future_side"])
                    or float(
                        guard_numbers["decision_future_price"]
                    )
                    != float(numbers["future_limit_price"])
                )

        package_order_ids: list[int] = []
        fill_prices: dict[str, float] = {}
        fill_costs: dict[str, float] = {}
        observed_first_timestamps: list[int] = []
        observed_last_timestamps: list[int] = []
        raw_fill_count = 0
        raw_filled_leg_count = 0
        raw_fully_filled_leg_count = 0
        for leg in ("call", "put", "future"):
            side = float(numbers[f"{leg}_side"])
            limit_price = float(numbers[f"{leg}_limit_price"])
            reported_qty = float(numbers[f"{leg}_filled_qty"])
            order_id_raw = pd.to_numeric(
                row.get(f"{leg}_order_id", np.nan),
                errors="coerce",
            )
            reported_vwap = pd.to_numeric(
                row.get(f"{leg}_fill_vwap", np.nan),
                errors="coerce",
            )
            reported_cost = pd.to_numeric(
                row.get(f"{leg}_fill_cost", np.nan),
                errors="coerce",
            )
            reported_first = pd.to_numeric(
                row.get(f"{leg}_first_fill_ts_ns", np.nan),
                errors="coerce",
            )
            reported_last = pd.to_numeric(
                row.get(f"{leg}_last_fill_ts_ns", np.nan),
                errors="coerce",
            )
            violation = violation or (
                side != expected_sides[leg]
                or limit_price <= 0
                or reported_qty < 0
                or reported_qty % 1 != 0
                or reported_qty > requested_qty
            )
            if pd.isna(order_id_raw):
                violation = violation or (
                    reported_qty != 0
                    or not pd.isna(reported_vwap)
                    or not pd.isna(reported_cost)
                    or not pd.isna(reported_first)
                    or not pd.isna(reported_last)
                )
                continue
            if (
                order_id_raw <= 0
                or order_id_raw % 1 != 0
            ):
                violation = True
                continue
            order_id = int(order_id_raw)
            package_order_ids.append(order_id)
            if order_id in seen_order_ids:
                violation = True
            seen_order_ids.add(order_id)
            if not fill_columns_complete:
                row_missing = True
                continue
            raw_leg_fills = fills.loc[fill_oids.eq(order_id)]
            if raw_leg_fills.empty:
                violation = violation or (
                    reported_qty != 0
                    or not pd.isna(reported_vwap)
                    or pd.isna(reported_cost)
                    or (
                        not pd.isna(reported_cost)
                        and float(reported_cost) != 0.0
                    )
                    or not pd.isna(reported_first)
                    or not pd.isna(reported_last)
                )
                continue
            raw_qty = pd.to_numeric(
                raw_leg_fills["qty"],
                errors="coerce",
            )
            raw_price = pd.to_numeric(
                raw_leg_fills["price"],
                errors="coerce",
            )
            raw_cost = pd.to_numeric(
                raw_leg_fills["cost"],
                errors="coerce",
            )
            raw_ts = pd.to_numeric(
                raw_leg_fills["ts_ns"],
                errors="coerce",
            )
            raw_side = pd.to_numeric(
                raw_leg_fills["side"],
                errors="coerce",
            )
            if (
                raw_qty.isna().any()
                or raw_price.isna().any()
                or raw_cost.isna().any()
                or raw_ts.isna().any()
                or raw_side.isna().any()
            ):
                row_missing = True
                continue
            if raw_qty.le(0).any():
                violation = True
                continue
            actual_qty = float(raw_qty.sum())
            actual_vwap = float(
                (raw_price * raw_qty).sum() / actual_qty
            )
            actual_cost = float(raw_cost.sum())
            actual_first = int(raw_ts.min())
            actual_last = int(raw_ts.max())
            raw_fill_count += int(len(raw_leg_fills))
            raw_filled_leg_count += int(actual_qty > 0)
            raw_fully_filled_leg_count += int(
                actual_qty == requested_qty
            )
            fill_prices[leg] = actual_vwap
            fill_costs[leg] = actual_cost
            observed_first_timestamps.append(actual_first)
            observed_last_timestamps.append(actual_last)
            instrument_match = (
                raw_leg_fills["instrument_id"].astype(str)
                == instrument_ids[leg]
            ).all()
            per_fill_limit_ok = (
                raw_price.le(limit_price + 1e-9).all()
                if side > 0
                else raw_price.ge(limit_price - 1e-9).all()
            )
            violation = violation or (
                not instrument_match
                or not raw_side.eq(side).all()
                or raw_qty.le(0).any()
                or raw_qty.mod(1).ne(0).any()
                or raw_price.le(0).any()
                or raw_cost.lt(0).any()
                or raw_ts.mod(1).ne(0).any()
                or not per_fill_limit_ok
                or actual_qty != reported_qty
                or pd.isna(reported_vwap)
                or (
                    not pd.isna(reported_vwap)
                    and abs(float(reported_vwap) - actual_vwap)
                    > 1e-9
                )
                or pd.isna(reported_cost)
                or (
                    not pd.isna(reported_cost)
                    and abs(float(reported_cost) - actual_cost)
                    > 1e-9
                )
                or pd.isna(reported_first)
                or (
                    not pd.isna(reported_first)
                    and (
                        reported_first % 1 != 0
                        or int(reported_first) != actual_first
                    )
                )
                or pd.isna(reported_last)
                or (
                    not pd.isna(reported_last)
                    and (
                        reported_last % 1 != 0
                        or int(reported_last) != actual_last
                    )
                )
            )

        accepted_package_complete = len(package_order_ids) == 3
        filled_package_complete = (
            accepted_package_complete
            and raw_fully_filled_leg_count == 3
        )
        violation = violation or (
            len(package_order_ids) != len(set(package_order_ids))
            or routing_complete != accepted_package_complete
            or fills_complete != filled_package_complete
            or float(numbers["fill_count"]) != raw_fill_count
            or float(numbers["filled_leg_count"])
            != raw_filled_leg_count
            or float(numbers["fully_filled_leg_count"])
            != raw_fully_filled_leg_count
        )

        reported_first_fill = pd.to_numeric(
            row.get("first_fill_ts_ns", np.nan),
            errors="coerce",
        )
        reported_last_fill = pd.to_numeric(
            row.get("last_fill_ts_ns", np.nan),
            errors="coerce",
        )
        reported_fill_span = pd.to_numeric(
            row.get("fill_span_ns", np.nan),
            errors="coerce",
        )
        if observed_first_timestamps:
            expected_first_fill = min(observed_first_timestamps)
            expected_last_fill = max(observed_last_timestamps)
            expected_fill_span = (
                expected_last_fill - expected_first_fill
            )
            first_fill_latency = (
                expected_first_fill - decision_ts_ns
            )
            completion_latency = (
                expected_last_fill - decision_ts_ns
            )
            fill_timing_evaluable_count += 1
            first_fill_latencies.append(first_fill_latency)
            completion_latencies.append(completion_latency)
            if first_fill_latency < 0 or completion_latency < 0:
                negative_fill_latency_count += 1
                violation = True
            violation = violation or (
                pd.isna(reported_first_fill)
                or pd.isna(reported_last_fill)
                or pd.isna(reported_fill_span)
                or (
                    not pd.isna(reported_first_fill)
                    and (
                        reported_first_fill % 1 != 0
                        or int(reported_first_fill)
                        != expected_first_fill
                    )
                )
                or (
                    not pd.isna(reported_last_fill)
                    and (
                        reported_last_fill % 1 != 0
                        or int(reported_last_fill)
                        != expected_last_fill
                    )
                )
                or (
                    not pd.isna(reported_fill_span)
                    and (
                        reported_fill_span % 1 != 0
                        or int(reported_fill_span)
                        != expected_fill_span
                    )
                )
            )
            fill_spans.append(expected_fill_span)
        else:
            violation = violation or (
                not pd.isna(reported_first_fill)
                or not pd.isna(reported_last_fill)
                or not pd.isna(reported_fill_span)
            )

        realized_names = [
            "realized_edge_per_unit",
            "realized_gross_edge",
            "realized_total_cost",
            "realized_net_edge",
            "realized_vs_decision_net_edge",
        ]
        realized = {
            name: pd.to_numeric(
                row.get(name, np.nan),
                errors="coerce",
            )
            for name in realized_names
        }
        if evaluable:
            if (
                len(fill_prices) != 3
                or len(fill_costs) != 3
                or any(pd.isna(value) for value in realized.values())
            ):
                row_missing = True
            else:
                if direction == "buy_synthetic_sell_future":
                    expected_edge_per_unit = (
                        fill_prices["future"]
                        - (
                            fill_prices["call"]
                            - fill_prices["put"]
                            + strike
                        )
                    )
                else:
                    expected_edge_per_unit = (
                        fill_prices["call"]
                        - fill_prices["put"]
                        + strike
                        - fill_prices["future"]
                    )
                expected_gross_edge = (
                    expected_edge_per_unit
                    * requested_qty
                    * multiplier
                )
                expected_total_cost = sum(fill_costs.values())
                expected_net_edge = (
                    expected_gross_edge - expected_total_cost
                )
                expected_change = expected_net_edge - decision_net_edge
                violation = violation or (
                    abs(
                        float(realized["realized_edge_per_unit"])
                        - expected_edge_per_unit
                    )
                    > 1e-9
                    or abs(
                        float(realized["realized_gross_edge"])
                        - expected_gross_edge
                    )
                    > 1e-9
                    or abs(
                        float(realized["realized_total_cost"])
                        - expected_total_cost
                    )
                    > 1e-9
                    or abs(
                        float(realized["realized_net_edge"])
                        - expected_net_edge
                    )
                    > 1e-9
                    or abs(
                        float(
                            realized[
                                "realized_vs_decision_net_edge"
                            ]
                        )
                        - expected_change
                    )
                    > 1e-9
                    or positive != (expected_net_edge > 0.0)
                )
                evaluable_count += 1
                positive_count += int(expected_net_edge > 0.0)
                nonpositive_count += int(expected_net_edge <= 0.0)
                realized_net_edges.append(expected_net_edge)
                realized_edge_changes.append(expected_change)
        else:
            violation = violation or (
                positive
                or any(not pd.isna(value) for value in realized.values())
            )

        missing_rows += int(row_missing)
        consistency_violations += int(violation and not row_missing)

    return {
        "parity_execution_realized_edge_enabled": bool(enabled),
        "parity_execution_fills_present": bool(fills_present),
        "parity_execution_realized_edge_evaluable_count": (
            evaluable_count
        ),
        "parity_execution_realized_edge_positive_count": positive_count,
        "parity_execution_realized_edge_nonpositive_count": (
            nonpositive_count
        ),
        "parity_execution_realized_edge_missing_evidence_rows": (
            missing_rows
        ),
        "parity_execution_realized_edge_consistency_violations": (
            consistency_violations
        ),
        "parity_execution_min_realized_net_edge": (
            min(realized_net_edges) if realized_net_edges else 0.0
        ),
        "parity_execution_total_realized_net_edge": sum(
            realized_net_edges
        ),
        "parity_execution_min_realized_vs_decision_net_edge": (
            min(realized_edge_changes)
            if realized_edge_changes
            else 0.0
        ),
        "parity_execution_max_fill_span_ns": (
            max(fill_spans) if fill_spans else 0
        ),
        "parity_execution_fill_timing_evaluable_count": (
            fill_timing_evaluable_count
        ),
        "parity_execution_negative_fill_latency_count": (
            negative_fill_latency_count
        ),
        "parity_execution_min_first_fill_latency_ns": (
            min(first_fill_latencies)
            if first_fill_latencies
            else 0
        ),
        "parity_execution_max_completion_latency_ns": (
            max(completion_latencies)
            if completion_latencies
            else 0
        ),
    }


def _parity_latency_sampling_metrics(
    feed_deliveries: pd.DataFrame,
    order_submissions: pd.DataFrame,
    *,
    parameters: Mapping[str, Any],
    enabled: bool,
    feed_deliveries_present: bool,
    order_submissions_present: bool,
) -> dict[str, float | int | bool]:
    feed_us = _configured_float(parameters, "feed_latency_us")
    order_us = _configured_float(parameters, "order_latency_us")
    jitter_us = _configured_float(parameters, "latency_jitter_us")
    seed = _configured_float(parameters, "latency_seed")
    configuration_violations = int(
        not np.isfinite(feed_us) or feed_us < 0
    )
    configuration_violations += int(
        not np.isfinite(order_us) or order_us < 0
    )
    configuration_violations += int(
        not np.isfinite(jitter_us) or jitter_us < 0
    )
    configuration_violations += int(
        not np.isfinite(seed)
        or seed < 0
        or seed % 1 != 0
    )
    if configuration_violations:
        feed_min_ns = 0
        feed_max_ns = 0
        order_min_ns = 0
        order_max_ns = 0
    else:
        feed_min_ns, feed_max_ns = _latency_bounds_ns(
            feed_us,
            jitter_us,
        )
        order_min_ns, order_max_ns = _latency_bounds_ns(
            order_us,
            jitter_us,
        )
    feed = _latency_evidence_metrics(
        feed_deliveries,
        latency_column="feed_latency_ns",
        start_column="market_ts_ns",
        end_column="strategy_ts_ns",
        minimum_ns=feed_min_ns,
        maximum_ns=feed_max_ns,
        require_feed_lineage=True,
    )
    order = _latency_evidence_metrics(
        order_submissions,
        latency_column="order_latency_ns",
        start_column="ts_sent_ns",
        end_column="ts_active_ns",
        minimum_ns=order_min_ns,
        maximum_ns=order_max_ns,
        require_feed_lineage=False,
    )
    return {
        "parity_latency_sampling_enabled": bool(enabled),
        "parity_latency_feed_deliveries_present": bool(
            feed_deliveries_present
        ),
        "parity_latency_order_submissions_present": bool(
            order_submissions_present
        ),
        "parity_latency_configuration_violations": (
            configuration_violations
        ),
        "parity_latency_jitter_us": (
            float(jitter_us) if np.isfinite(jitter_us) else np.nan
        ),
        "parity_latency_seed": (
            int(seed) if np.isfinite(seed) and seed % 1 == 0 else -1
        ),
        "parity_expected_min_feed_latency_ns": feed_min_ns,
        "parity_expected_max_feed_latency_ns": feed_max_ns,
        "parity_feed_latency_samples": feed["samples"],
        "parity_feed_latency_missing_rows": feed["missing_rows"],
        "parity_feed_latency_consistency_violations": feed[
            "consistency_violations"
        ],
        "parity_feed_latency_bound_violations": feed[
            "bound_violations"
        ],
        "parity_min_sampled_feed_latency_ns": feed[
            "minimum_sampled_ns"
        ],
        "parity_max_sampled_feed_latency_ns": feed[
            "maximum_sampled_ns"
        ],
        "parity_expected_min_order_latency_ns": order_min_ns,
        "parity_expected_max_order_latency_ns": order_max_ns,
        "parity_order_latency_samples": order["samples"],
        "parity_order_latency_missing_rows": order["missing_rows"],
        "parity_order_latency_consistency_violations": order[
            "consistency_violations"
        ],
        "parity_order_latency_bound_violations": order[
            "bound_violations"
        ],
        "parity_min_sampled_order_latency_ns": order[
            "minimum_sampled_ns"
        ],
        "parity_max_sampled_order_latency_ns": order[
            "maximum_sampled_ns"
        ],
    }


def _configured_float(
    parameters: Mapping[str, Any],
    key: str,
) -> float:
    try:
        return float(parameters[key])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def _latency_bounds_ns(
    base_latency_us: float,
    jitter_us: float,
) -> tuple[int, int]:
    return (
        int(max(base_latency_us - jitter_us, 0.0) * 1_000),
        int((base_latency_us + jitter_us) * 1_000),
    )


def _latency_evidence_metrics(
    frame: pd.DataFrame,
    *,
    latency_column: str,
    start_column: str,
    end_column: str,
    minimum_ns: int,
    maximum_ns: int,
    require_feed_lineage: bool,
) -> dict[str, int]:
    required = [latency_column, start_column, end_column]
    if require_feed_lineage:
        required.extend(
            [
                "market_event_seq",
                "feed_event_seq",
                "instrument_id",
                "venue",
            ]
        )
    missing_columns = [
        column for column in required if column not in frame.columns
    ]
    if missing_columns:
        return {
            "samples": int(len(frame)),
            "missing_rows": int(len(frame)),
            "consistency_violations": int(len(frame)),
            "bound_violations": int(len(frame)),
            "minimum_sampled_ns": 0,
            "maximum_sampled_ns": 0,
        }
    numeric_columns = [
        latency_column,
        start_column,
        end_column,
    ]
    if require_feed_lineage:
        numeric_columns.extend(
            ["market_event_seq", "feed_event_seq"]
        )
    numbers = frame[numeric_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )
    missing = numbers.isna().any(axis=1)
    nonintegral = numbers.mod(1).ne(0).any(axis=1)
    inconsistent = (
        missing
        | nonintegral
        | numbers[latency_column].lt(0)
        | numbers[end_column].lt(numbers[start_column])
        | numbers[latency_column].ne(
            numbers[end_column] - numbers[start_column]
        )
    )
    if require_feed_lineage:
        missing_identity = (
            frame["instrument_id"].isna()
            | frame["instrument_id"].astype(str).str.strip().eq("")
            | frame["venue"].isna()
            | frame["venue"].astype(str).str.strip().eq("")
        )
        duplicate_lineage = (
            numbers["market_event_seq"].duplicated(keep=False)
            | numbers["feed_event_seq"].duplicated(keep=False)
        )
        inconsistent |= (
            missing_identity
            | duplicate_lineage
            | numbers["feed_event_seq"].ne(
                numbers["market_event_seq"] + 1
            )
        )
        missing |= missing_identity
    valid = ~missing & ~nonintegral
    bound_violations = (
        valid
        & (
            numbers[latency_column].lt(minimum_ns)
            | numbers[latency_column].gt(maximum_ns)
        )
    )
    sampled = numbers.loc[valid, latency_column]
    return {
        "samples": int(len(frame)),
        "missing_rows": int(missing.sum()),
        "consistency_violations": int(inconsistent.sum()),
        "bound_violations": int(bound_violations.sum()),
        "minimum_sampled_ns": (
            int(sampled.min()) if not sampled.empty else 0
        ),
        "maximum_sampled_ns": (
            int(sampled.max()) if not sampled.empty else 0
        ),
    }


def _parity_order_timing_metrics(
    legging: pd.DataFrame,
    fills: pd.DataFrame,
    order_submissions: pd.DataFrame,
    *,
    enabled: bool,
    order_submissions_present: bool,
) -> dict[str, int | bool]:
    evaluable_legs = 0
    missing_evidence_legs = 0
    consistency_violations = 0
    pre_activation_fill_legs = 0
    first_fill_latencies: list[int] = []
    completion_latencies: list[int] = []
    submission_oids = pd.to_numeric(
        order_submissions.get(
            "oid",
            pd.Series(index=order_submissions.index, dtype="float64"),
        ),
        errors="coerce",
    )
    fill_oids = pd.to_numeric(
        fills.get(
            "oid",
            pd.Series(index=fills.index, dtype="float64"),
        ),
        errors="coerce",
    )

    if enabled:
        for _, row in legging.iterrows():
            decision_ts_raw = pd.to_numeric(
                row.get("decision_ts_ns", np.nan),
                errors="coerce",
            )
            requested_qty_raw = pd.to_numeric(
                row.get("requested_qty", np.nan),
                errors="coerce",
            )
            for leg in ("call", "put", "future"):
                order_id_raw = pd.to_numeric(
                    row.get(f"{leg}_order_id", np.nan),
                    errors="coerce",
                )
                if pd.isna(order_id_raw):
                    continue
                if order_id_raw <= 0 or order_id_raw % 1 != 0:
                    consistency_violations += 1
                    continue
                order_id = int(order_id_raw)

                matches = order_submissions.loc[
                    submission_oids.eq(order_id)
                ]
                if matches.empty:
                    missing_evidence_legs += 1
                    continue
                if len(matches) != 1:
                    consistency_violations += 1
                    continue

                submission = matches.iloc[0]
                number_names = [
                    "ts_sent_ns",
                    "ts_active_ns",
                    "order_latency_ns",
                    "oid",
                    "side",
                    "qty",
                    "price",
                ]
                numbers = {
                    name: pd.to_numeric(
                        submission.get(name, np.nan),
                        errors="coerce",
                    )
                    for name in number_names
                }
                instrument_id_raw = submission.get(
                    "instrument_id",
                    np.nan,
                )
                order_type_raw = submission.get(
                    "order_type",
                    np.nan,
                )
                expected_instrument_raw = row.get(
                    f"{leg}_instrument_id",
                    np.nan,
                )
                expected_side = pd.to_numeric(
                    row.get(f"{leg}_side", np.nan),
                    errors="coerce",
                )
                expected_price = pd.to_numeric(
                    row.get(f"{leg}_limit_price", np.nan),
                    errors="coerce",
                )
                instrument_id = str(instrument_id_raw).strip()
                order_type = str(order_type_raw).strip()
                if (
                    any(
                        pd.isna(value)
                        for value in numbers.values()
                    )
                    or any(
                        not np.isfinite(float(value))
                        for value in numbers.values()
                        if not pd.isna(value)
                    )
                    or pd.isna(decision_ts_raw)
                    or pd.isna(requested_qty_raw)
                    or not np.isfinite(float(decision_ts_raw))
                    or not np.isfinite(float(requested_qty_raw))
                    or pd.isna(instrument_id_raw)
                    or pd.isna(order_type_raw)
                    or pd.isna(expected_instrument_raw)
                    or pd.isna(expected_side)
                    or pd.isna(expected_price)
                    or instrument_id == ""
                    or order_type == ""
                ):
                    missing_evidence_legs += 1
                    continue

                sent_ts = int(numbers["ts_sent_ns"])
                active_ts = int(numbers["ts_active_ns"])
                latency_ns = int(numbers["order_latency_ns"])
                metadata_violation = (
                    numbers["ts_sent_ns"] % 1 != 0
                    or numbers["ts_active_ns"] % 1 != 0
                    or numbers["order_latency_ns"] % 1 != 0
                    or numbers["oid"] % 1 != 0
                    or numbers["side"] % 1 != 0
                    or numbers["qty"] % 1 != 0
                    or decision_ts_raw % 1 != 0
                    or requested_qty_raw % 1 != 0
                    or sent_ts != int(decision_ts_raw)
                    or active_ts < sent_ts
                    or latency_ns < 0
                    or latency_ns != active_ts - sent_ts
                    or int(numbers["oid"]) != order_id
                    or numbers["side"] not in (-1, 1)
                    or numbers["qty"] <= 0
                    or numbers["price"] <= 0
                    or float(numbers["side"])
                    != float(expected_side)
                    or float(numbers["qty"])
                    != float(requested_qty_raw)
                    or abs(
                        float(numbers["price"])
                        - float(expected_price)
                    )
                    > 1e-9
                    or instrument_id
                    != str(expected_instrument_raw).strip()
                    or order_type != "IOC"
                )
                consistency_violations += int(
                    metadata_violation
                )

                reported_filled_qty = pd.to_numeric(
                    row.get(f"{leg}_filled_qty", np.nan),
                    errors="coerce",
                )
                raw_leg_fills = fills.loc[
                    fill_oids.eq(order_id)
                ]
                if pd.isna(reported_filled_qty):
                    missing_evidence_legs += 1
                    continue
                if raw_leg_fills.empty:
                    missing_evidence_legs += int(
                        reported_filled_qty > 0
                    )
                    continue
                if reported_filled_qty <= 0:
                    consistency_violations += 1
                    continue

                raw_timestamps = pd.to_numeric(
                    raw_leg_fills.get(
                        "ts_ns",
                        pd.Series(
                            np.nan,
                            index=raw_leg_fills.index,
                        ),
                    ),
                    errors="coerce",
                )
                if raw_timestamps.isna().any():
                    missing_evidence_legs += 1
                    continue
                if raw_timestamps.mod(1).ne(0).any():
                    consistency_violations += 1
                    continue

                first_fill_ts = int(raw_timestamps.min())
                last_fill_ts = int(raw_timestamps.max())
                first_latency = first_fill_ts - active_ts
                completion_latency = last_fill_ts - active_ts
                evaluable_legs += 1
                first_fill_latencies.append(first_latency)
                completion_latencies.append(completion_latency)
                pre_activation_fill_legs += int(
                    raw_timestamps.lt(active_ts).any()
                )

    return {
        "parity_execution_order_timing_enabled": bool(enabled),
        "parity_execution_order_submissions_present": bool(
            order_submissions_present
        ),
        "parity_execution_order_timing_evaluable_legs": (
            evaluable_legs
        ),
        "parity_execution_order_timing_missing_evidence_legs": (
            missing_evidence_legs
        ),
        "parity_execution_order_timing_consistency_violations": (
            consistency_violations
        ),
        "parity_execution_pre_activation_fill_legs": (
            pre_activation_fill_legs
        ),
        "parity_execution_min_activation_to_first_fill_latency_ns": (
            min(first_fill_latencies)
            if first_fill_latencies
            else 0
        ),
        "parity_execution_max_activation_to_completion_latency_ns": (
            max(completion_latencies)
            if completion_latencies
            else 0
        ),
    }


def _parity_ioc_book_relation(
    *,
    side: int,
    limit_price: float,
    bid: float,
    ask: float,
) -> str:
    if side > 0:
        if limit_price >= ask:
            return "marketable"
        if abs(limit_price - bid) < 1e-9:
            return "bid_touch"
        if bid < limit_price < ask:
            return "price_improving"
    else:
        if limit_price <= bid:
            return "marketable"
        if abs(limit_price - ask) < 1e-9:
            return "ask_touch"
        if bid < limit_price < ask:
            return "price_improving"
    return "away_from_touch"


def _parity_ioc_arrival_metrics(
    legging: pd.DataFrame,
    fills: pd.DataFrame,
    order_submissions: pd.DataFrame,
    ioc_arrival_audit: pd.DataFrame,
    *,
    enabled: bool,
    event_lineage_enabled: bool,
    audit_present: bool,
) -> dict[str, int | float | bool]:
    evaluable_legs = 0
    missing_evidence_legs = 0
    consistency_violations = 0
    not_marketable_legs = 0
    capacity_shortfall_legs = 0
    negative_lag_legs = 0
    fill_ratios: list[float] = []
    arrival_lags: list[int] = []
    event_rows_by_oid: dict[int, dict[str, int | float | str]] = {}
    audit_oids = pd.to_numeric(
        ioc_arrival_audit.get(
            "oid",
            pd.Series(
                index=ioc_arrival_audit.index,
                dtype="float64",
            ),
        ),
        errors="coerce",
    )
    submission_oids = pd.to_numeric(
        order_submissions.get(
            "oid",
            pd.Series(
                index=order_submissions.index,
                dtype="float64",
            ),
        ),
        errors="coerce",
    )
    fill_oids = pd.to_numeric(
        fills.get(
            "oid",
            pd.Series(index=fills.index, dtype="float64"),
        ),
        errors="coerce",
    )

    if enabled:
        for _, row in legging.iterrows():
            for leg in ("call", "put", "future"):
                order_id_raw = pd.to_numeric(
                    row.get(f"{leg}_order_id", np.nan),
                    errors="coerce",
                )
                if pd.isna(order_id_raw):
                    continue
                if order_id_raw <= 0 or order_id_raw % 1 != 0:
                    consistency_violations += 1
                    continue
                order_id = int(order_id_raw)
                audit_matches = ioc_arrival_audit.loc[
                    audit_oids.eq(order_id)
                ]
                if audit_matches.empty:
                    missing_evidence_legs += 1
                    continue
                if len(audit_matches) != 1:
                    consistency_violations += 1
                    continue
                submission_matches = order_submissions.loc[
                    submission_oids.eq(order_id)
                ]
                if submission_matches.empty:
                    missing_evidence_legs += 1
                    continue
                if len(submission_matches) != 1:
                    consistency_violations += 1
                    continue

                arrival = audit_matches.iloc[0]
                submission = submission_matches.iloc[0]
                audit_number_names = [
                    "arrival_ts_ns",
                    "market_event_seq",
                    "event_order_rank",
                    "oid",
                    "side",
                    "limit_price",
                    "requested_qty",
                    "ts_sent_ns",
                    "ts_active_ns",
                    "arrival_lag_ns",
                    "bid",
                    "ask",
                    "bid_qty",
                    "ask_qty",
                    "touch_price",
                    "lot_size",
                    "available_qty",
                    "available_after_qty",
                    "observed_qty",
                    "carried_depletion_qty",
                    "event_consumed_qty",
                    "filled_qty",
                    "shortfall_qty",
                ]
                audit_numbers = {
                    name: pd.to_numeric(
                        arrival.get(name, np.nan),
                        errors="coerce",
                    )
                    for name in audit_number_names
                }
                audit_string_names = [
                    "instrument_id",
                    "order_type",
                    "book_relation",
                    "liquidity_source",
                    "outcome",
                ]
                audit_string_raw = {
                    name: arrival.get(name, np.nan)
                    for name in audit_string_names
                }
                submission_number_names = [
                    "ts_sent_ns",
                    "ts_active_ns",
                    "oid",
                    "side",
                    "qty",
                    "price",
                ]
                submission_numbers = {
                    name: pd.to_numeric(
                        submission.get(name, np.nan),
                        errors="coerce",
                    )
                    for name in submission_number_names
                }
                marketable_raw = arrival.get("marketable", np.nan)
                complete_raw = arrival.get("complete", np.nan)
                expected_instrument_raw = row.get(
                    f"{leg}_instrument_id",
                    np.nan,
                )
                expected_side = pd.to_numeric(
                    row.get(f"{leg}_side", np.nan),
                    errors="coerce",
                )
                expected_limit = pd.to_numeric(
                    row.get(f"{leg}_limit_price", np.nan),
                    errors="coerce",
                )
                reported_filled_qty = pd.to_numeric(
                    row.get(f"{leg}_filled_qty", np.nan),
                    errors="coerce",
                )
                submission_instrument_raw = submission.get(
                    "instrument_id",
                    np.nan,
                )
                submission_order_type_raw = submission.get(
                    "order_type",
                    np.nan,
                )
                missing = (
                    any(
                        pd.isna(value)
                        for value in audit_numbers.values()
                    )
                    or any(
                        not np.isfinite(float(value))
                        for value in audit_numbers.values()
                        if not pd.isna(value)
                    )
                    or any(
                        pd.isna(value)
                        for value in submission_numbers.values()
                    )
                    or any(
                        not np.isfinite(float(value))
                        for value in submission_numbers.values()
                        if not pd.isna(value)
                    )
                    or any(
                        pd.isna(value)
                        or str(value).strip() == ""
                        for value in audit_string_raw.values()
                    )
                    or _boolean_evidence_missing(
                        pd.Series(
                            [marketable_raw, complete_raw],
                            dtype="object",
                        )
                    ).any()
                    or pd.isna(expected_instrument_raw)
                    or str(expected_instrument_raw).strip() == ""
                    or pd.isna(expected_side)
                    or pd.isna(expected_limit)
                    or pd.isna(reported_filled_qty)
                    or pd.isna(submission_instrument_raw)
                    or str(submission_instrument_raw).strip() == ""
                    or pd.isna(submission_order_type_raw)
                    or str(submission_order_type_raw).strip() == ""
                )
                if missing:
                    missing_evidence_legs += 1
                    continue

                audit_strings = {
                    name: str(value).strip()
                    for name, value in audit_string_raw.items()
                }
                marketable = _bool(marketable_raw)
                complete = _bool(complete_raw)
                arrival_ts_ns = int(
                    audit_numbers["arrival_ts_ns"]
                )
                oid = int(audit_numbers["oid"])
                side = int(audit_numbers["side"])
                limit_price = float(
                    audit_numbers["limit_price"]
                )
                requested_qty = int(
                    audit_numbers["requested_qty"]
                )
                sent_ts_ns = int(audit_numbers["ts_sent_ns"])
                active_ts_ns = int(
                    audit_numbers["ts_active_ns"]
                )
                arrival_lag_ns = int(
                    audit_numbers["arrival_lag_ns"]
                )
                bid = float(audit_numbers["bid"])
                ask = float(audit_numbers["ask"])
                bid_qty = float(audit_numbers["bid_qty"])
                ask_qty = float(audit_numbers["ask_qty"])
                touch_price = float(
                    audit_numbers["touch_price"]
                )
                lot_size = int(audit_numbers["lot_size"])
                available_qty = float(
                    audit_numbers["available_qty"]
                )
                available_after_qty = float(
                    audit_numbers["available_after_qty"]
                )
                observed_qty = float(
                    audit_numbers["observed_qty"]
                )
                carried_qty = float(
                    audit_numbers["carried_depletion_qty"]
                )
                event_consumed_qty = float(
                    audit_numbers["event_consumed_qty"]
                )
                filled_qty = int(audit_numbers["filled_qty"])
                shortfall_qty = int(
                    audit_numbers["shortfall_qty"]
                )
                expected_relation = _parity_ioc_book_relation(
                    side=side,
                    limit_price=limit_price,
                    bid=bid,
                    ask=ask,
                )
                expected_marketable = (
                    expected_relation == "marketable"
                )
                expected_touch = ask if side > 0 else bid
                expected_observed = (
                    ask_qty if side > 0 else bid_qty
                )
                expected_source = (
                    "ask_display"
                    if side > 0
                    else "bid_display"
                )
                expected_available = max(
                    observed_qty
                    - carried_qty
                    - event_consumed_qty,
                    0.0,
                )
                expected_fill = 0
                if marketable and lot_size > 0:
                    expected_fill = min(
                        requested_qty,
                        int(np.floor(available_qty / lot_size))
                        * lot_size,
                    )
                expected_shortfall = (
                    requested_qty - filled_qty
                )
                expected_outcome = (
                    "not_marketable"
                    if not marketable
                    else (
                        "filled"
                        if expected_shortfall == 0
                        else (
                            "partial_fill"
                            if filled_qty > 0
                            else "no_fill"
                        )
                    )
                )

                raw_leg_fills = fills.loc[
                    fill_oids.eq(order_id)
                ]
                if filled_qty > 0 and raw_leg_fills.empty:
                    missing_evidence_legs += 1
                    continue
                raw_fill_violation = False
                if raw_leg_fills.empty:
                    raw_filled_qty = 0
                else:
                    raw_fill_number_names = [
                        "ts_ns",
                        "oid",
                        "side",
                        "qty",
                        "price",
                    ]
                    raw_fill_numbers = {
                        name: pd.to_numeric(
                            raw_leg_fills.get(
                                name,
                                pd.Series(
                                    np.nan,
                                    index=raw_leg_fills.index,
                                ),
                            ),
                            errors="coerce",
                        )
                        for name in raw_fill_number_names
                    }
                    raw_fill_instrument = raw_leg_fills.get(
                        "instrument_id",
                        pd.Series(
                            np.nan,
                            index=raw_leg_fills.index,
                        ),
                    )
                    raw_fill_maker = raw_leg_fills.get(
                        "maker",
                        pd.Series(
                            np.nan,
                            index=raw_leg_fills.index,
                        ),
                    )
                    if (
                        any(
                            values.isna().any()
                            for values in raw_fill_numbers.values()
                        )
                        or raw_fill_instrument.isna().any()
                        or _boolean_evidence_missing(
                            raw_fill_maker
                        ).any()
                    ):
                        missing_evidence_legs += 1
                        continue
                    raw_filled_qty = int(
                        raw_fill_numbers["qty"].sum()
                    )
                    raw_fill_violation = (
                        raw_fill_numbers["ts_ns"]
                        .mod(1)
                        .ne(0)
                        .any()
                        or raw_fill_numbers["oid"]
                        .mod(1)
                        .ne(0)
                        .any()
                        or raw_fill_numbers["side"]
                        .mod(1)
                        .ne(0)
                        .any()
                        or raw_fill_numbers["qty"]
                        .mod(1)
                        .ne(0)
                        .any()
                        or raw_fill_numbers["ts_ns"]
                        .ne(arrival_ts_ns)
                        .any()
                        or raw_fill_numbers["oid"]
                        .ne(order_id)
                        .any()
                        or raw_fill_numbers["side"]
                        .ne(side)
                        .any()
                        or raw_fill_numbers["qty"].le(0).any()
                        or raw_fill_numbers["price"]
                        .sub(touch_price)
                        .abs()
                        .gt(1e-9)
                        .any()
                        or raw_fill_instrument.astype(str)
                        .str.strip()
                        .ne(audit_strings["instrument_id"])
                        .any()
                        or raw_fill_maker.map(_bool).any()
                    )

                integer_names = [
                    "arrival_ts_ns",
                    "market_event_seq",
                    "event_order_rank",
                    "oid",
                    "side",
                    "requested_qty",
                    "ts_sent_ns",
                    "ts_active_ns",
                    "arrival_lag_ns",
                    "lot_size",
                    "filled_qty",
                    "shortfall_qty",
                ]
                violation = (
                    any(
                        audit_numbers[name] % 1 != 0
                        for name in integer_names
                    )
                    or any(
                        submission_numbers[name] % 1 != 0
                        for name in [
                            "ts_sent_ns",
                            "ts_active_ns",
                            "oid",
                            "side",
                            "qty",
                        ]
                    )
                    or oid != order_id
                    or int(audit_numbers["market_event_seq"]) < 0
                    or int(audit_numbers["event_order_rank"]) < 0
                    or side not in (-1, 1)
                    or requested_qty <= 0
                    or lot_size <= 0
                    or requested_qty % max(lot_size, 1) != 0
                    or filled_qty < 0
                    or filled_qty % max(lot_size, 1) != 0
                    or bid <= 0
                    or ask <= 0
                    or bid > ask
                    or bid_qty < 0
                    or ask_qty < 0
                    or available_qty < 0
                    or available_after_qty < 0
                    or observed_qty < 0
                    or carried_qty < 0
                    or event_consumed_qty < 0
                    or carried_qty + event_consumed_qty
                    > observed_qty + 1e-9
                    or abs(
                        observed_qty - expected_observed
                    )
                    > 1e-9
                    or abs(
                        available_qty - expected_available
                    )
                    > 1e-9
                    or abs(
                        available_after_qty
                        - max(
                            available_qty - filled_qty,
                            0.0,
                        )
                    )
                    > 1e-9
                    or filled_qty != expected_fill
                    or shortfall_qty != expected_shortfall
                    or marketable != expected_marketable
                    or complete != (shortfall_qty == 0)
                    or audit_strings["book_relation"]
                    != expected_relation
                    or audit_strings["liquidity_source"]
                    != expected_source
                    or audit_strings["outcome"]
                    != expected_outcome
                    or audit_strings["order_type"] != "IOC"
                    or abs(touch_price - expected_touch) > 1e-9
                    or arrival_ts_ns < active_ts_ns
                    or arrival_lag_ns
                    != arrival_ts_ns - active_ts_ns
                    or sent_ts_ns
                    != int(submission_numbers["ts_sent_ns"])
                    or active_ts_ns
                    != int(submission_numbers["ts_active_ns"])
                    or oid != int(submission_numbers["oid"])
                    or side != int(submission_numbers["side"])
                    or requested_qty
                    != int(submission_numbers["qty"])
                    or abs(
                        limit_price
                        - float(submission_numbers["price"])
                    )
                    > 1e-9
                    or audit_strings["instrument_id"]
                    != str(submission_instrument_raw).strip()
                    or str(submission_order_type_raw).strip()
                    != "IOC"
                    or audit_strings["instrument_id"]
                    != str(expected_instrument_raw).strip()
                    or float(side) != float(expected_side)
                    or abs(
                        limit_price - float(expected_limit)
                    )
                    > 1e-9
                    or reported_filled_qty % 1 != 0
                    or filled_qty != int(reported_filled_qty)
                    or raw_filled_qty != filled_qty
                    or raw_fill_violation
                )
                evaluable_legs += 1
                consistency_violations += int(violation)
                if oid in event_rows_by_oid:
                    consistency_violations += 1
                else:
                    event_rows_by_oid[oid] = {
                        "instrument_id": audit_strings[
                            "instrument_id"
                        ],
                        "arrival_ts_ns": arrival_ts_ns,
                        "market_event_seq": int(
                            audit_numbers["market_event_seq"]
                        ),
                        "event_order_rank": int(
                            audit_numbers["event_order_rank"]
                        ),
                        "side": side,
                        "bid": bid,
                        "ask": ask,
                        "bid_qty": bid_qty,
                        "ask_qty": ask_qty,
                        "observed_qty": observed_qty,
                        "carried_depletion_qty": carried_qty,
                        "event_consumed_qty": event_consumed_qty,
                        "available_qty": available_qty,
                        "filled_qty": filled_qty,
                    }
                not_marketable_legs += int(not marketable)
                capacity_shortfall_legs += int(
                    marketable and shortfall_qty > 0
                )
                negative_lag_legs += int(
                    arrival_ts_ns < active_ts_ns
                    or arrival_lag_ns < 0
                )
                fill_ratios.append(
                    filled_qty / requested_qty
                )
                arrival_lags.append(arrival_lag_ns)

    event_depth_metrics = _parity_ioc_event_depth_metrics(
        list(event_rows_by_oid.values())
    )
    return {
        "parity_execution_ioc_arrival_audit_enabled": bool(
            enabled
        ),
        "parity_execution_ioc_arrival_event_lineage_enabled": bool(
            event_lineage_enabled
        ),
        "parity_execution_ioc_arrival_audit_present": bool(
            audit_present
        ),
        "parity_execution_ioc_arrival_evaluable_legs": (
            evaluable_legs
        ),
        "parity_execution_ioc_arrival_missing_evidence_legs": (
            missing_evidence_legs
        ),
        "parity_execution_ioc_arrival_consistency_violations": (
            consistency_violations
        ),
        "parity_execution_ioc_arrival_not_marketable_legs": (
            not_marketable_legs
        ),
        "parity_execution_ioc_arrival_capacity_shortfall_legs": (
            capacity_shortfall_legs
        ),
        "parity_execution_ioc_arrival_negative_lag_legs": (
            negative_lag_legs
        ),
        "parity_execution_min_ioc_arrival_fill_ratio": (
            float(min(fill_ratios)) if fill_ratios else 0.0
        ),
        "parity_execution_max_ioc_arrival_lag_ns": (
            max(arrival_lags) if arrival_lags else 0
        ),
        **event_depth_metrics,
    }


def _parity_ioc_event_depth_metrics(
    rows: list[dict[str, int | float | str]],
) -> dict[str, int]:
    if not rows:
        return {
            "parity_execution_ioc_arrival_market_events": 0,
            "parity_execution_ioc_arrival_competing_depth_events": 0,
            (
                "parity_execution_ioc_arrival_"
                "event_depth_consistency_violations"
            ): 0,
        }

    frame = pd.DataFrame(rows)
    event_columns = ["instrument_id", "market_event_seq"]
    side_columns = [*event_columns, "side"]
    market_events = 0
    competing_depth_events = 0
    violations = 0
    for _, event in frame.groupby(
        event_columns,
        sort=False,
        dropna=False,
    ):
        market_events += 1
        violations += int(
            event["event_order_rank"].duplicated().any()
            or event["arrival_ts_ns"].nunique(dropna=False) != 1
            or event["bid"].nunique(dropna=False) != 1
            or event["ask"].nunique(dropna=False) != 1
            or event["bid_qty"].nunique(dropna=False) != 1
            or event["ask_qty"].nunique(dropna=False) != 1
        )
    for _, event_side in frame.groupby(
        side_columns,
        sort=False,
        dropna=False,
    ):
        competing_depth_events += int(len(event_side) > 1)
        inconsistent = bool(
            event_side["observed_qty"].nunique(dropna=False) != 1
            or event_side["carried_depletion_qty"].nunique(
                dropna=False
            )
            != 1
        )
        ordered = event_side.sort_values(
            "event_order_rank",
            kind="stable",
        )
        observed_qty = float(ordered.iloc[0]["observed_qty"])
        carried_qty = float(
            ordered.iloc[0]["carried_depletion_qty"]
        )
        cumulative_filled_qty = 0.0
        for row in ordered.itertuples(index=False):
            expected_available = max(
                observed_qty
                - carried_qty
                - cumulative_filled_qty,
                0.0,
            )
            inconsistent |= (
                abs(
                    float(row.event_consumed_qty)
                    - cumulative_filled_qty
                )
                > 1e-9
                or abs(
                    float(row.available_qty)
                    - expected_available
                )
                > 1e-9
            )
            cumulative_filled_qty += float(row.filled_qty)
        violations += int(inconsistent)

    return {
        "parity_execution_ioc_arrival_market_events": (
            market_events
        ),
        "parity_execution_ioc_arrival_competing_depth_events": (
            competing_depth_events
        ),
        (
            "parity_execution_ioc_arrival_"
            "event_depth_consistency_violations"
        ): violations,
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
    if bool(metrics["input_quarantine_tracking_enabled"]):
        dataset_count = int(metrics["input_dataset_count"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "input_dataset_count",
                "value": dataset_count,
                "operator": ">=",
                "threshold": 1,
                "passed": dataset_count >= 1,
                "reason": (
                    ""
                    if dataset_count >= 1
                    else "input quarantine tracking contains no datasets"
                ),
            }
        )
        integrity_drops = int(metrics["input_integrity_dropped_rows"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "input_integrity_dropped_rows",
                "value": integrity_drops,
                "operator": "==",
                "threshold": 0,
                "passed": integrity_drops == 0,
                "reason": (
                    ""
                    if integrity_drops == 0
                    else (
                        f"{integrity_drops} input row(s) required "
                        "integrity repair before replay"
                    )
                ),
            }
        )
        empty_datasets = int(metrics["input_empty_datasets"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "input_empty_datasets",
                "value": empty_datasets,
                "operator": "==",
                "threshold": 0,
                "passed": empty_datasets == 0,
                "reason": (
                    ""
                    if empty_datasets == 0
                    else (
                        f"{empty_datasets} input dataset(s) were empty "
                        "after normalization"
                    )
                ),
            }
        )
    if bool(metrics["parity_futures_asof_freshness_enabled"]):
        max_quote_age_ns = int(
            metrics["parity_futures_max_quote_age_ns"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_futures_max_quote_age_ns",
                "value": max_quote_age_ns,
                "operator": ">=",
                "threshold": 0,
                "passed": max_quote_age_ns >= 0,
                "reason": (
                    ""
                    if max_quote_age_ns >= 0
                    else "parity futures quote-age limit is negative"
                ),
            }
        )
        for metric, reason in [
            (
                "parity_futures_join_audit_present",
                "parity futures join-audit artifact is missing",
            ),
            (
                "parity_futures_signals_present",
                "parity signals artifact is missing",
            ),
        ]:
            present = bool(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": present,
                    "operator": "is",
                    "threshold": True,
                    "passed": present,
                    "reason": "" if present else reason,
                }
            )
        join_rows = int(metrics["parity_futures_join_rows"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_futures_join_rows",
                "value": join_rows,
                "operator": ">=",
                "threshold": 1,
                "passed": join_rows >= 1,
                "reason": (
                    ""
                    if join_rows >= 1
                    else "parity futures join audit contains no rows"
                ),
            }
        )
        for metric, reason in [
            (
                "parity_futures_unclassified_join_rows",
                "parity futures join audit has unclassified rows",
            ),
            (
                "parity_futures_signals_without_age",
                "parity signals are missing futures as-of age evidence",
            ),
            (
                "parity_futures_signal_age_violations",
                "parity signals exceed the futures quote-age limit",
            ),
        ]:
            value = int(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": value,
                    "operator": "==",
                    "threshold": 0,
                    "passed": value == 0,
                    "reason": "" if value == 0 else reason,
                }
            )
        max_signal_age_ns = int(
            metrics["parity_futures_max_signal_age_ns"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_futures_max_signal_age_ns",
                "value": max_signal_age_ns,
                "operator": "<=",
                "threshold": max_quote_age_ns,
                "passed": max_signal_age_ns <= max_quote_age_ns,
                "reason": (
                    ""
                    if max_signal_age_ns <= max_quote_age_ns
                    else (
                        "parity signal futures as-of age exceeds "
                        "the configured limit"
                    )
                ),
            }
        )
    if bool(metrics["parity_latency_sampling_enabled"]):
        for metric, reason in [
            (
                "parity_latency_sampling_declared",
                "parity latency sampling is configured without "
                "the summary audit declaration",
            ),
            (
                "parity_latency_feed_deliveries_present",
                "engine-owned feed-delivery evidence is missing",
            ),
            (
                "parity_latency_order_submissions_present",
                "engine-owned order-submission evidence is missing",
            ),
        ]:
            present = bool(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": present,
                    "operator": "is",
                    "threshold": True,
                    "passed": present,
                    "reason": "" if present else reason,
                }
            )
        feed_samples = int(
            metrics["parity_feed_latency_samples"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_feed_latency_samples",
                "value": feed_samples,
                "operator": ">=",
                "threshold": 1,
                "passed": feed_samples >= 1,
                "reason": (
                    ""
                    if feed_samples >= 1
                    else "parity replay contains no feed-latency samples"
                ),
            }
        )
        order_samples = int(
            metrics["parity_order_latency_samples"]
        )
        required_order_samples = (
            1 if int(metrics["fills"]) > 0 else 0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_order_latency_samples",
                "value": order_samples,
                "operator": ">=",
                "threshold": required_order_samples,
                "passed": order_samples >= required_order_samples,
                "reason": (
                    ""
                    if order_samples >= required_order_samples
                    else (
                        "filled parity replay contains no sampled "
                        "order latency"
                    )
                ),
            }
        )
        for metric, reason in [
            (
                "parity_latency_configuration_violations",
                "latency base, jitter, or seed configuration is invalid",
            ),
            (
                "parity_feed_latency_missing_rows",
                "feed-delivery rows are missing latency evidence",
            ),
            (
                "parity_feed_latency_consistency_violations",
                "feed-delivery timestamps or event lineage are inconsistent",
            ),
            (
                "parity_feed_latency_bound_violations",
                "sampled feed latency falls outside configured bounds",
            ),
            (
                "parity_order_latency_missing_rows",
                "order submissions are missing sampled latency",
            ),
            (
                "parity_order_latency_consistency_violations",
                "order activation timestamps disagree with sampled latency",
            ),
            (
                "parity_order_latency_bound_violations",
                "sampled order latency falls outside configured bounds",
            ),
        ]:
            value = int(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": value,
                    "operator": "==",
                    "threshold": 0,
                    "passed": value == 0,
                    "reason": "" if value == 0 else reason,
                }
            )
    if bool(metrics["parity_execution_guard_enabled"]):
        declared = bool(metrics["parity_execution_guard_declared"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_guard_declared",
                "value": declared,
                "operator": "is",
                "threshold": True,
                "passed": declared,
                "reason": (
                    ""
                    if declared
                    else (
                        "parity execution artifacts exist without the "
                        "summary safety declaration"
                    )
                ),
            }
        )
        signal_source_declared = bool(
            metrics[
                "parity_execution_signal_source_causality_declared"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_signal_source_causality_declared"
                ),
                "value": signal_source_declared,
                "operator": "is",
                "threshold": True,
                "passed": signal_source_declared,
                "reason": (
                    ""
                    if signal_source_declared
                    else (
                        "parity execution lacks the causal signal-source "
                        "book declaration"
                    )
                ),
            }
        )
        edge_revalidation_declared = bool(
            metrics[
                "parity_execution_edge_revalidation_declared"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_edge_revalidation_declared"
                ),
                "value": edge_revalidation_declared,
                "operator": "is",
                "threshold": True,
                "passed": edge_revalidation_declared,
                "reason": (
                    ""
                    if edge_revalidation_declared
                    else (
                        "parity execution lacks the decision-time "
                        "edge-revalidation safety declaration"
                    )
                ),
            }
        )
        realized_edge_declared = bool(
            metrics["parity_execution_realized_edge_declared"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_realized_edge_declared",
                "value": realized_edge_declared,
                "operator": "is",
                "threshold": True,
                "passed": realized_edge_declared,
                "reason": (
                    ""
                    if realized_edge_declared
                    else (
                        "parity execution lacks the realized fill-edge "
                        "proof declaration"
                    )
                ),
            }
        )
        order_timing_declared = bool(
            metrics["parity_execution_order_timing_declared"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_order_timing_declared",
                "value": order_timing_declared,
                "operator": "is",
                "threshold": True,
                "passed": order_timing_declared,
                "reason": (
                    ""
                    if order_timing_declared
                    else (
                        "parity execution lacks engine-owned order "
                        "activation timing evidence"
                    )
                ),
            }
        )
        ioc_arrival_audit_declared = bool(
            metrics[
                "parity_execution_ioc_arrival_audit_declared"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_ioc_arrival_audit_declared"
                ),
                "value": ioc_arrival_audit_declared,
                "operator": "is",
                "threshold": True,
                "passed": ioc_arrival_audit_declared,
                "reason": (
                    ""
                    if ioc_arrival_audit_declared
                    else (
                        "parity execution lacks engine-owned IOC "
                        "arrival-book evidence"
                    )
                ),
            }
        )
        ioc_arrival_event_lineage_declared = bool(
            metrics[
                "parity_execution_ioc_arrival_event_lineage_declared"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_ioc_arrival_"
                    "event_lineage_declared"
                ),
                "value": ioc_arrival_event_lineage_declared,
                "operator": "is",
                "threshold": True,
                "passed": ioc_arrival_event_lineage_declared,
                "reason": (
                    ""
                    if ioc_arrival_event_lineage_declared
                    else (
                        "parity execution lacks IOC market-event "
                        "identity and processing-rank evidence"
                    )
                ),
            }
        )
        preflight_declared = bool(
            metrics[
                "parity_execution_ioc_batch_preflight_declared"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_ioc_batch_preflight_declared"
                ),
                "value": preflight_declared,
                "operator": "is",
                "threshold": True,
                "passed": preflight_declared,
                "reason": (
                    ""
                    if preflight_declared
                    else (
                        "parity execution lacks the IOC package "
                        "preflight safety declaration"
                    )
                ),
            }
        )
        for metric in [
            "parity_execution_max_leg_book_age_ns",
            "parity_execution_max_leg_book_skew_ns",
        ]:
            value = int(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": value,
                    "operator": ">=",
                    "threshold": 0,
                    "passed": value >= 0,
                    "reason": (
                        ""
                        if value >= 0
                        else "parity execution guard limit is negative"
                    ),
                }
            )
        for metric, reason in [
            (
                "parity_execution_guard_present",
                "parity execution guard artifact is missing",
            ),
            (
                "parity_execution_legging_present",
                "parity legging artifact is missing",
            ),
            (
                "parity_execution_fills_present",
                "parity raw fills artifact is missing",
            ),
            (
                "parity_execution_order_submissions_present",
                "parity order-submission artifact is missing",
            ),
            (
                "parity_execution_ioc_arrival_audit_present",
                "parity IOC arrival-audit artifact is missing",
            ),
        ]:
            present = bool(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": present,
                    "operator": "is",
                    "threshold": True,
                    "passed": present,
                    "reason": "" if present else reason,
                }
            )
        parity_signal_count = int(
            metrics["parity_futures_signal_count"]
        )
        guard_rows = int(metrics["parity_execution_guard_rows"])
        min_guard_rows = 1 if parity_signal_count > 0 else 0
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_guard_rows",
                "value": guard_rows,
                "operator": ">=",
                "threshold": min_guard_rows,
                "passed": guard_rows >= min_guard_rows,
                "reason": (
                    ""
                    if guard_rows >= min_guard_rows
                    else "parity signals have no execution-guard evidence"
                ),
            }
        )
        for metric, reason in [
            (
                "parity_execution_guard_missing_evidence_rows",
                "parity execution guard lacks required routing evidence",
            ),
            (
                "parity_execution_guard_unclassified_rows",
                "parity execution guard contains unclassified rows",
            ),
            (
                "parity_execution_guard_consistency_violations",
                "parity execution guard status is internally inconsistent",
            ),
            (
                "parity_execution_signal_source_missing_evidence_rows",
                "parity signal-source causality evidence is missing",
            ),
            (
                "parity_execution_signal_source_consistency_violations",
                "parity signal-source causality evidence is inconsistent",
            ),
            (
                "parity_execution_edge_revalidation_missing_evidence_rows",
                "parity decision-time edge evidence is missing",
            ),
            (
                "parity_execution_edge_revalidation_consistency_violations",
                "parity decision-time edge evidence is inconsistent",
            ),
            (
                "parity_execution_realized_edge_missing_evidence_rows",
                "parity realized fill-edge evidence is missing",
            ),
            (
                "parity_execution_realized_edge_consistency_violations",
                "parity realized fill-edge evidence is inconsistent",
            ),
            (
                "parity_execution_realized_edge_nonpositive_count",
                "a completed parity package realized no positive net edge",
            ),
            (
                "parity_execution_negative_fill_latency_count",
                "a parity package contains a fill before its decision",
            ),
            (
                "parity_execution_order_timing_missing_evidence_legs",
                "a parity leg lacks accepted-order timing evidence",
            ),
            (
                "parity_execution_order_timing_consistency_violations",
                "parity accepted-order timing evidence is inconsistent",
            ),
            (
                "parity_execution_pre_activation_fill_legs",
                "a parity leg contains a fill before venue activation",
            ),
            (
                "parity_execution_ioc_arrival_missing_evidence_legs",
                "a parity leg lacks arrival-time IOC book evidence",
            ),
            (
                "parity_execution_ioc_arrival_consistency_violations",
                "parity IOC arrival, depth, and fill evidence is inconsistent",
            ),
            (
                "parity_execution_ioc_arrival_not_marketable_legs",
                "a routed parity IOC was not marketable at venue arrival",
            ),
            (
                "parity_execution_ioc_arrival_capacity_shortfall_legs",
                "a routed parity IOC exceeded arrival-time displayed capacity",
            ),
            (
                "parity_execution_ioc_arrival_negative_lag_legs",
                "a parity IOC arrival predates venue activation",
            ),
            (
                (
                    "parity_execution_ioc_arrival_"
                    "event_depth_consistency_violations"
                ),
                (
                    "parity IOC arrivals do not conserve shared "
                    "displayed depth within a market event"
                ),
            ),
            (
                "parity_execution_ioc_batch_preflight_missing_evidence_rows",
                "parity IOC package preflight evidence is missing",
            ),
            (
                "parity_execution_ioc_batch_preflight_consistency_violations",
                "parity IOC package preflight evidence is inconsistent",
            ),
            (
                "parity_execution_ioc_visible_capacity_missing_evidence_rows",
                "parity IOC visible-capacity evidence is missing",
            ),
            (
                "parity_execution_ioc_visible_capacity_consistency_violations",
                "parity IOC visible-capacity evidence is inconsistent",
            ),
            (
                "parity_execution_ioc_batch_preflight_rejected_attempts",
                "parity IOC packages failed admission before routing",
            ),
            (
                "parity_execution_guard_passed_missing_age_rows",
                "passed parity guard rows lack leg age or skew evidence",
            ),
            (
                "parity_execution_guard_age_violations",
                "passed parity guard rows exceed the leg-book age limit",
            ),
            (
                "parity_execution_guard_skew_violations",
                "passed parity guard rows exceed the leg-book skew limit",
            ),
            (
                "parity_execution_routing_incomplete_attempts",
                "parity execution routed fewer than all three legs",
            ),
            (
                "parity_execution_signal_expiry_events",
                "parity signals expired before guarded execution",
            ),
            (
                "parity_execution_negative_book_age_attempts",
                "parity execution observed a future-dated leg book",
            ),
            (
                "parity_execution_legging_missing_evidence_rows",
                "parity legging rows lack required completion evidence",
            ),
            (
                "parity_execution_legging_consistency_violations",
                "parity legging completion evidence is inconsistent",
            ),
            (
                "parity_execution_incomplete_count",
                "parity executions have incomplete routing or fills",
            ),
            (
                "parity_execution_route_rejected_legs",
                "parity execution legs were rejected before routing",
            ),
            (
                "parity_execution_unfilled_legs",
                "parity execution legs did not fill completely",
            ),
        ]:
            value = int(metrics[metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": value,
                    "operator": "==",
                    "threshold": 0,
                    "passed": value == 0,
                    "reason": "" if value == 0 else reason,
                }
            )
        routed_attempts = int(
            metrics["parity_execution_guard_passed_attempts"]
        )
        min_routed_net_edge = float(
            metrics["parity_execution_min_routed_net_edge"]
        )
        routed_edge_passed = (
            routed_attempts == 0
            or min_routed_net_edge > 0.0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_min_routed_net_edge",
                "value": min_routed_net_edge,
                "operator": ">",
                "threshold": 0.0,
                "passed": routed_edge_passed,
                "reason": (
                    ""
                    if routed_edge_passed
                    else (
                        "a routed parity package had no positive "
                        "decision-time net edge after modeled costs"
                    )
                ),
            }
        )
        complete_executions = int(
            metrics["parity_execution_complete_count"]
        )
        fill_timing_executions = int(
            metrics[
                "parity_execution_fill_timing_evaluable_count"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_fill_timing_evaluable_count"
                ),
                "value": fill_timing_executions,
                "operator": ">=",
                "threshold": complete_executions,
                "passed": (
                    fill_timing_executions >= complete_executions
                ),
                "reason": (
                    ""
                    if fill_timing_executions
                    >= complete_executions
                    else (
                        "completed parity packages lack causal "
                        "decision-to-fill timing evidence"
                    )
                ),
            }
        )
        order_timing_legs = int(
            metrics[
                "parity_execution_order_timing_evaluable_legs"
            ]
        )
        required_order_timing_legs = (
            complete_executions * 3
            if order_timing_declared
            else 0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_order_timing_evaluable_legs"
                ),
                "value": order_timing_legs,
                "operator": ">=",
                "threshold": required_order_timing_legs,
                "passed": (
                    order_timing_legs
                    >= required_order_timing_legs
                ),
                "reason": (
                    ""
                    if order_timing_legs
                    >= required_order_timing_legs
                    else (
                        "completed parity packages lack three-leg "
                        "activation-to-fill timing evidence"
                    )
                ),
            }
        )
        ioc_arrival_legs = int(
            metrics[
                "parity_execution_ioc_arrival_evaluable_legs"
            ]
        )
        required_ioc_arrival_legs = (
            complete_executions * 3
            if ioc_arrival_audit_declared
            else 0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_ioc_arrival_evaluable_legs"
                ),
                "value": ioc_arrival_legs,
                "operator": ">=",
                "threshold": required_ioc_arrival_legs,
                "passed": (
                    ioc_arrival_legs
                    >= required_ioc_arrival_legs
                ),
                "reason": (
                    ""
                    if ioc_arrival_legs
                    >= required_ioc_arrival_legs
                    else (
                        "completed parity packages lack three-leg "
                        "arrival-book and displayed-depth evidence"
                    )
                ),
            }
        )
        ioc_arrival_market_events = int(
            metrics[
                "parity_execution_ioc_arrival_market_events"
            ]
        )
        required_ioc_arrival_market_events = (
            1
            if (
                ioc_arrival_audit_declared
                and ioc_arrival_event_lineage_declared
                and complete_executions > 0
            )
            else 0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_ioc_arrival_market_events"
                ),
                "value": ioc_arrival_market_events,
                "operator": ">=",
                "threshold": required_ioc_arrival_market_events,
                "passed": (
                    ioc_arrival_market_events
                    >= required_ioc_arrival_market_events
                ),
                "reason": (
                    ""
                    if ioc_arrival_market_events
                    >= required_ioc_arrival_market_events
                    else (
                        "completed parity packages lack IOC "
                        "market-event lineage"
                    )
                ),
            }
        )
        min_ioc_arrival_fill_ratio = float(
            metrics[
                "parity_execution_min_ioc_arrival_fill_ratio"
            ]
        )
        required_ioc_arrival_fill_ratio = (
            1.0
            if (
                ioc_arrival_audit_declared
                and complete_executions > 0
            )
            else 0.0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_min_ioc_arrival_fill_ratio"
                ),
                "value": min_ioc_arrival_fill_ratio,
                "operator": ">=",
                "threshold": required_ioc_arrival_fill_ratio,
                "passed": (
                    min_ioc_arrival_fill_ratio
                    >= required_ioc_arrival_fill_ratio
                ),
                "reason": (
                    ""
                    if min_ioc_arrival_fill_ratio
                    >= required_ioc_arrival_fill_ratio
                    else (
                        "a completed parity leg was not fully backed "
                        "by arrival-time displayed capacity"
                    )
                ),
            }
        )
        realized_executions = int(
            metrics[
                "parity_execution_realized_edge_evaluable_count"
            ]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": (
                    "parity_execution_realized_edge_evaluable_count"
                ),
                "value": realized_executions,
                "operator": "==",
                "threshold": complete_executions,
                "passed": realized_executions == complete_executions,
                "reason": (
                    ""
                    if realized_executions == complete_executions
                    else (
                        "completed parity packages are not fully bound "
                        "to realized fill-edge evidence"
                    )
                ),
            }
        )
        min_realized_net_edge = float(
            metrics["parity_execution_min_realized_net_edge"]
        )
        realized_edge_passed = (
            realized_executions == 0
            or min_realized_net_edge > 0.0
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_min_realized_net_edge",
                "value": min_realized_net_edge,
                "operator": ">",
                "threshold": 0.0,
                "passed": realized_edge_passed,
                "reason": (
                    ""
                    if realized_edge_passed
                    else (
                        "a completed parity package had no positive "
                        "realized net edge after actual fill costs"
                    )
                ),
            }
        )
        for metric, threshold_metric, reason in [
            (
                "parity_execution_max_routed_book_age_ns",
                "parity_execution_max_leg_book_age_ns",
                "routed parity execution used an over-age leg book",
            ),
            (
                "parity_execution_max_routed_book_skew_ns",
                "parity_execution_max_leg_book_skew_ns",
                "routed parity execution used over-skewed leg books",
            ),
        ]:
            value = int(metrics[metric])
            threshold = int(metrics[threshold_metric])
            rows.append(
                {
                    "run": metrics["run"],
                    "check": metric,
                    "value": value,
                    "operator": "<=",
                    "threshold": threshold,
                    "passed": value <= threshold,
                    "reason": "" if value <= threshold else reason,
                }
            )
        complete_executions = int(
            metrics["parity_execution_complete_count"]
        )
        min_complete_executions = 1 if parity_signal_count > 0 else 0
        rows.append(
            {
                "run": metrics["run"],
                "check": "parity_execution_complete_count",
                "value": complete_executions,
                "operator": ">=",
                "threshold": min_complete_executions,
                "passed": (
                    complete_executions >= min_complete_executions
                ),
                "reason": (
                    ""
                    if complete_executions >= min_complete_executions
                    else "parity signals produced no complete execution"
                ),
            }
        )
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
    if bool(metrics["cancel_lifecycle_tracking_enabled"]):
        pending_cancels = int(
            metrics["cancel_pending_at_replay_end_events"]
        )
        rows.append(
            {
                "run": metrics["run"],
                "check": "cancel_pending_at_replay_end_events",
                "value": pending_cancels,
                "operator": "==",
                "threshold": 0,
                "passed": pending_cancels == 0,
                "reason": (
                    ""
                    if pending_cancels == 0
                    else (
                        f"{pending_cancels} cancel request(s) remained "
                        "in flight at replay end"
                    )
                ),
            }
        )
    if bool(metrics["order_horizon_tracking_enabled"]):
        open_orders = int(metrics["open_orders_at_replay_end"])
        rows.append(
            {
                "run": metrics["run"],
                "check": "open_orders_at_replay_end",
                "value": open_orders,
                "operator": "==",
                "threshold": 0,
                "passed": open_orders == 0,
                "reason": (
                    ""
                    if open_orders == 0
                    else (
                        f"{open_orders} order(s) remained live beyond "
                        "the replay evidence horizon"
                    )
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
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _boolean_evidence_missing(values: pd.Series) -> pd.Series:
    def invalid(value: object) -> bool:
        if pd.isna(value):
            return True
        if isinstance(value, (bool, np.bool_)):
            return False
        if isinstance(value, str):
            return value.strip().lower() not in {
                "0",
                "1",
                "false",
                "true",
                "no",
                "yes",
                "n",
                "y",
            }
        if isinstance(value, (int, float, np.integer, np.floating)):
            return float(value) not in {0.0, 1.0}
        return True

    return values.map(invalid)


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
