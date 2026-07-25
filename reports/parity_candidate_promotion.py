from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import (
    ManifestIntegrity,
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.parity_edge import (
    PARITY_EDGE_REQUIRED_ARTIFACTS,
    PARITY_EDGE_RUN_TYPE,
)
from reports.parity_order_plan import PARITY_BOX_STRATEGY, BOX_DIRECTIONS, PARITY_DIRECTIONS
from scanners.run_parity_box import (
    PARITY_SCAN_REQUIRED_ARTIFACTS,
    PARITY_SCAN_RUN_TYPE,
)
from strategies.run_parity_sweep import (
    PARITY_SWEEP_REQUIRED_ARTIFACTS,
    PARITY_SWEEP_RUN_TYPE,
)


LATENCY_SEED_ROBUSTNESS_COLUMNS = (
    "latency_seed_group",
    "depth_fraction",
    "asof_latency_ns",
    "feed_latency_us",
    "order_latency_us",
    "latency_jitter_us",
    "latency_seed_values",
    "latency_seed_runs",
    "latency_seed_expected_runs",
    "latency_seed_count",
    "latency_seed_passed_runs",
    "latency_seed_pass_rate",
    "latency_seed_group_passed",
    "latency_seed_worst_run",
    "latency_seed_worst_seed",
    "latency_seed_worst_robust_score",
    "latency_seed_worst_net_pnl",
    "latency_seed_median_net_pnl",
    "latency_seed_best_net_pnl",
    "latency_seed_min_fills",
    "latency_seed_worst_drawdown",
    "latency_seed_bound_violations",
)

LATENCY_SEED_PROMOTION_METRICS = (
    "latency_seed_group",
    "latency_seed_values",
    "latency_seed_runs",
    "latency_seed_expected_runs",
    "latency_seed_count",
    "latency_seed_passed_runs",
    "latency_seed_pass_rate",
    "latency_seed_group_passed",
    "latency_seed_worst_run",
    "latency_seed_worst_seed",
    "latency_seed_worst_robust_score",
    "latency_seed_worst_net_pnl",
    "latency_seed_median_net_pnl",
    "latency_seed_best_net_pnl",
    "latency_seed_min_fills",
    "latency_seed_worst_drawdown",
    "latency_seed_bound_violations",
)

PARITY_PROMOTION_LINEAGE_METRICS = (
    "scan_manifest_current",
    "scan_manifest_error",
    "scan_manifest_sha256",
    "edge_manifest_current",
    "edge_manifest_error",
    "edge_manifest_sha256",
    "sweep_manifest_current",
    "sweep_manifest_error",
    "sweep_manifest_sha256",
    "scan_edge_manifest_bound",
    "scan_sweep_source_match",
    "scan_sweep_static_parameters_match",
    "scan_sweep_selected_scenario_match",
    "scan_chain_sha256",
    "scan_futures_sha256",
    "sweep_chain_sha256",
    "sweep_futures_sha256",
)


@dataclass(frozen=True)
class ParityCandidatePromotionThresholds:
    require_edge_passed: bool = True
    require_sweep_passed_scenario: bool = True
    min_total_opportunities: int = 1
    min_best_net_edge: float = 0.0
    min_candidate_net_edge: float = 0.0
    min_candidate_persistence_ticks: float = 0.0
    min_sweep_pass_rate: float = 0.0
    min_passed_scenarios: int = 1


@dataclass(frozen=True)
class ParityCandidatePromotionReport:
    candidate: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    candidate_config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_parity_candidate_promotion(
    parity_opportunities: pd.DataFrame,
    box_opportunities: pd.DataFrame,
    edge_summary: pd.DataFrame,
    sweep_summary: pd.DataFrame,
    sweep_runs: pd.DataFrame,
    *,
    latency_seed_robustness: pd.DataFrame | None = None,
    sweep_run_constraints: Mapping[str, Any] | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    thresholds: ParityCandidatePromotionThresholds | None = None,
) -> ParityCandidatePromotionReport:
    thresholds = thresholds or ParityCandidatePromotionThresholds()
    _validate_thresholds(thresholds)
    _require(edge_summary, ["passed", "total_opportunities", "best_net_edge"], "edge_summary")
    _require(sweep_summary, ["passed_scenarios", "pass_rate", "best_run"], "sweep_summary")
    _require(sweep_runs, ["run"], "sweep_runs")
    seed_robustness_enabled = latency_seed_robustness is not None
    latency_seed_robustness = (
        pd.DataFrame()
        if latency_seed_robustness is None
        else latency_seed_robustness.copy()
    )
    if seed_robustness_enabled and not latency_seed_robustness.empty:
        _require(
            latency_seed_robustness,
            list(LATENCY_SEED_ROBUSTNESS_COLUMNS),
            "latency_seed_robustness",
        )

    opportunities = _combined_opportunities(parity_opportunities, box_opportunities)
    candidate_row = _select_candidate(opportunities)
    sweep_row = _select_sweep_run(
        sweep_summary.iloc[0],
        sweep_runs,
        latency_seed_robustness=latency_seed_robustness,
        seed_robustness_enabled=seed_robustness_enabled,
        constraints=sweep_run_constraints,
    )
    checks = _checks(
        edge_summary.iloc[0],
        sweep_summary.iloc[0],
        candidate_row,
        sweep_row,
        thresholds,
        seed_robustness_enabled=seed_robustness_enabled,
    )
    candidate = (
        pd.DataFrame([_candidate_record(candidate_row, edge_summary.iloc[0], sweep_summary.iloc[0], sweep_row, market)])
        if candidate_row is not None
        else _empty_candidate()
    )
    summary = _summary(candidate, checks)
    config = _promotion_candidate_config(candidate, checks, summary.iloc[0], thresholds)
    return ParityCandidatePromotionReport(candidate, checks, summary, config)


def write_parity_candidate_promotion(
    scan_dir: str | Path,
    *,
    edge_audit_dir: str | Path,
    sweep_dir: str | Path,
    output_dir: str | Path,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    thresholds: ParityCandidatePromotionThresholds | None = None,
) -> ParityCandidatePromotionReport:
    scan = Path(scan_dir).resolve()
    edge = Path(edge_audit_dir).resolve()
    sweep = Path(sweep_dir).resolve()
    parity_path = scan / "parity_opportunities.csv"
    box_path = scan / "box_opportunities.csv"
    edge_summary_path = edge / "parity_edge_summary.csv"
    sweep_summary_path = sweep / "sweep_summary.csv"
    sweep_runs_path = sweep / "sweep_runs.csv"
    scan_manifest_path = scan / "manifest.json"
    edge_manifest_path = edge / "manifest.json"
    sweep_manifest_path = sweep / "manifest.json"
    latency_seed_robustness_path = (
        sweep / "latency_seed_robustness.csv"
    )
    for path in [parity_path, box_path, edge_summary_path, sweep_summary_path, sweep_runs_path]:
        if not path.exists():
            raise FileNotFoundError(f"required parity promotion input missing: {path}")

    thresholds = thresholds or ParityCandidatePromotionThresholds()
    scan_integrity = verify_experiment_manifest(
        scan_manifest_path,
        expected_run_type=PARITY_SCAN_RUN_TYPE,
        required_artifacts=PARITY_SCAN_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    edge_integrity = verify_experiment_manifest(
        edge_manifest_path,
        expected_run_type=PARITY_EDGE_RUN_TYPE,
        required_artifacts=PARITY_EDGE_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    sweep_integrity = verify_experiment_manifest(
        sweep_manifest_path,
        expected_run_type=PARITY_SWEEP_RUN_TYPE,
        required_artifacts=PARITY_SWEEP_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    scan_manifest = _read_manifest(scan_manifest_path)
    edge_manifest = _read_manifest(edge_manifest_path)
    sweep_manifest = _read_manifest(sweep_manifest_path)
    base_report = evaluate_parity_candidate_promotion(
        pd.read_csv(parity_path),
        pd.read_csv(box_path),
        pd.read_csv(edge_summary_path),
        pd.read_csv(sweep_summary_path),
        pd.read_csv(sweep_runs_path),
        latency_seed_robustness=(
            pd.read_csv(latency_seed_robustness_path)
            if latency_seed_robustness_path.exists()
            else None
        ),
        sweep_run_constraints=_scan_sweep_constraints(
            scan_manifest
        ),
        market=market,
        thresholds=thresholds,
    )
    lineage_checks, lineage = _parity_lineage(
        scan_manifest_path=scan_manifest_path,
        edge_manifest_path=edge_manifest_path,
        sweep_manifest_path=sweep_manifest_path,
        scan_manifest=scan_manifest,
        edge_manifest=edge_manifest,
        sweep_manifest=sweep_manifest,
        scan_integrity=scan_integrity,
        edge_integrity=edge_integrity,
        sweep_integrity=sweep_integrity,
        candidate=base_report.candidate,
    )
    checks = pd.concat(
        [
            _manifest_checks(
                scan_integrity,
                edge_integrity,
                sweep_integrity,
            ),
            lineage_checks,
            base_report.checks,
        ],
        ignore_index=True,
    )
    candidate = base_report.candidate.copy()
    for key, value in lineage.items():
        candidate[key] = value
    summary = _summary(candidate, checks)
    for key, value in lineage.items():
        summary[key] = value
    candidate_config = _promotion_candidate_config(
        candidate,
        checks,
        summary.iloc[0],
        thresholds,
    )
    report = ParityCandidatePromotionReport(
        candidate,
        checks,
        summary,
        candidate_config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.candidate.to_csv(out / "promotion_candidate.csv", index=False)
    report.checks.to_csv(out / "promotion_checks.csv", index=False)
    report.summary.to_csv(out / "promotion_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(_jsonable(report.candidate_config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_inputs = {
        "scan": scan,
        "edge_audit": edge,
        "sweep": sweep,
        "parity_opportunities": parity_path,
        "box_opportunities": box_path,
        "edge_summary": edge_summary_path,
        "sweep_summary": sweep_summary_path,
        "sweep_runs": sweep_runs_path,
        "scan_manifest": scan_manifest_path,
        "scan_dependencies": manifest_dependency_paths(
            scan_manifest_path
        ),
        "edge_manifest": edge_manifest_path,
        "edge_dependencies": manifest_dependency_paths(
            edge_manifest_path
        ),
        "sweep_manifest": sweep_manifest_path,
        "sweep_dependencies": manifest_dependency_paths(
            sweep_manifest_path
        ),
    }
    if latency_seed_robustness_path.exists():
        manifest_inputs["latency_seed_robustness"] = (
            latency_seed_robustness_path
        )
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={
            "strategy": PARITY_BOX_STRATEGY,
            "market": market,
            "thresholds": asdict(thresholds),
        },
        inputs=manifest_inputs,
        extra={
            "promotion_source": "parity_scan_edge_sweep",
            "scan_manifest_current": bool(
                scan_integrity.passed
            ),
            "edge_manifest_current": bool(
                edge_integrity.passed
            ),
            "sweep_manifest_current": bool(
                sweep_integrity.passed
            ),
            "scan_sweep_source_match": bool(
                lineage["scan_sweep_source_match"]
            ),
            "scan_edge_manifest_bound": bool(
                lineage["scan_edge_manifest_bound"]
            ),
            "scan_sweep_static_parameters_match": bool(
                lineage[
                    "scan_sweep_static_parameters_match"
                ]
            ),
            "scan_sweep_selected_scenario_match": bool(
                lineage[
                    "scan_sweep_selected_scenario_match"
                ]
            ),
        },
    )
    return ParityCandidatePromotionReport(
        report.candidate,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


def _manifest_checks(
    scan: ManifestIntegrity,
    edge: ManifestIntegrity,
    sweep: ManifestIntegrity,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _manifest_check("scan", scan),
            _manifest_check("edge", edge),
            _manifest_check("sweep", sweep),
        ]
    )


def _manifest_check(
    label: str,
    integrity: ManifestIntegrity,
) -> dict[str, Any]:
    passed = bool(integrity.passed)
    return _check(
        f"{label}_manifest_current",
        passed,
        "is",
        True,
        passed,
        (
            ""
            if passed
            else f"parity {label} manifest failed: "
            f"{integrity.error or 'verification_failed'}"
        ),
    )


def _parity_lineage(
    *,
    scan_manifest_path: Path,
    edge_manifest_path: Path,
    sweep_manifest_path: Path,
    scan_manifest: Mapping[str, Any],
    edge_manifest: Mapping[str, Any],
    sweep_manifest: Mapping[str, Any],
    scan_integrity: ManifestIntegrity,
    edge_integrity: ManifestIntegrity,
    sweep_integrity: ManifestIntegrity,
    candidate: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    scan_parameters = _manifest_mapping(
        scan_manifest,
        "parameters",
    )
    sweep_parameters = _manifest_mapping(
        sweep_manifest,
        "parameters",
    )
    scan_chain = _manifest_input_signature(
        scan_manifest,
        "chain",
    )
    scan_futures = _manifest_input_signature(
        scan_manifest,
        "futures",
    )
    sweep_chain = _manifest_input_signature(
        sweep_manifest,
        "chain",
    )
    sweep_futures = _manifest_input_signature(
        sweep_manifest,
        "futures",
    )
    scan_manifest_signature = _file_signature(
        scan_manifest_path
    )
    edge_scan_manifest_signature = (
        _manifest_input_signature(
            edge_manifest,
            "scan_manifest",
        )
    )
    scan_edge_bound = bool(
        scan_integrity.passed
        and edge_integrity.passed
        and scan_manifest_signature is not None
        and scan_manifest_signature
        == edge_scan_manifest_signature
    )
    source_match = bool(
        scan_integrity.passed
        and sweep_integrity.passed
        and scan_chain is not None
        and scan_chain == sweep_chain
        and scan_futures is not None
        and scan_futures == sweep_futures
    )

    static_parameter_names = [
        "market",
        "chain_column_map",
        "futures_column_map",
        "timestamp_unit",
        "timestamp_tz",
        "filter_session",
        "lot_size",
        "option_tick",
        "future_tick",
    ]
    static_parameters_match = bool(
        scan_integrity.passed
        and sweep_integrity.passed
        and all(
            _values_match(
                scan_parameters.get(name),
                sweep_parameters.get(name),
            )
            for name in static_parameter_names
        )
    )

    candidate_row = (
        candidate.iloc[0]
        if not candidate.empty
        else pd.Series(dtype=object)
    )
    selected_pairs = [
        ("market", "market"),
        ("depth_fraction", "depth_fraction"),
        ("asof_latency_ns", "asof_latency_ns"),
        (
            "max_futures_quote_age_ns",
            "max_futures_quote_age_ns",
        ),
    ]
    selected_scenario_match = bool(
        scan_integrity.passed
        and sweep_integrity.passed
        and not candidate_row.empty
        and all(
            _values_match(
                scan_parameters.get(scan_name),
                candidate_row.get(candidate_name),
            )
            for scan_name, candidate_name in selected_pairs
        )
    )

    lineage = {
        "scan_manifest_current": bool(
            scan_integrity.passed
        ),
        "scan_manifest_error": str(scan_integrity.error),
        "scan_manifest_sha256": _file_sha256_or_empty(
            scan_manifest_path
        ),
        "edge_manifest_current": bool(
            edge_integrity.passed
        ),
        "edge_manifest_error": str(edge_integrity.error),
        "edge_manifest_sha256": _file_sha256_or_empty(
            edge_manifest_path
        ),
        "sweep_manifest_current": bool(
            sweep_integrity.passed
        ),
        "sweep_manifest_error": str(
            sweep_integrity.error
        ),
        "sweep_manifest_sha256": _file_sha256_or_empty(
            sweep_manifest_path
        ),
        "scan_edge_manifest_bound": scan_edge_bound,
        "scan_sweep_source_match": source_match,
        "scan_sweep_static_parameters_match": (
            static_parameters_match
        ),
        "scan_sweep_selected_scenario_match": (
            selected_scenario_match
        ),
        "scan_chain_sha256": _signature_sha256(scan_chain),
        "scan_futures_sha256": _signature_sha256(
            scan_futures
        ),
        "sweep_chain_sha256": _signature_sha256(
            sweep_chain
        ),
        "sweep_futures_sha256": _signature_sha256(
            sweep_futures
        ),
    }
    checks = pd.DataFrame(
        [
            _check(
                "scan_edge_manifest_bound",
                scan_edge_bound,
                "is",
                True,
                scan_edge_bound,
                "parity edge audit is not bound to the exact "
                "scan manifest supplied for promotion",
            ),
            _check(
                "scan_sweep_source_match",
                source_match,
                "is",
                True,
                source_match,
                "parity scan and sweep do not fingerprint the "
                "same chain and futures inputs",
            ),
            _check(
                "scan_sweep_static_parameters_match",
                static_parameters_match,
                "is",
                True,
                static_parameters_match,
                "parity scan and sweep normalization or "
                "instrument assumptions differ",
            ),
            _check(
                "scan_sweep_selected_scenario_match",
                selected_scenario_match,
                "is",
                True,
                selected_scenario_match,
                "selected parity sweep scenario does not match "
                "the scan depth, as-of latency, quote age, or market",
            ),
        ]
    )
    return checks, lineage


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_mapping(
    manifest: Mapping[str, Any],
    key: str,
) -> dict[str, Any]:
    value = manifest.get(key, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _manifest_input_signature(
    manifest: Mapping[str, Any],
    name: str,
) -> tuple[int, str] | None:
    inputs = _manifest_mapping(manifest, "inputs")
    value = inputs.get(name)
    if not isinstance(value, Mapping):
        return None
    if str(value.get("kind", "")) != "file":
        return None
    size = _exact_integer(value.get("size_bytes"))
    digest = str(value.get("sha256", "")).strip().lower()
    if size is None or size < 0 or len(digest) != 64:
        return None
    return size, digest


def _signature_sha256(
    signature: tuple[int, str] | None,
) -> str:
    return signature[1] if signature is not None else ""


def _file_signature(path: Path) -> tuple[int, str] | None:
    try:
        if not path.is_file():
            return None
        return int(path.stat().st_size), file_sha256(path)
    except OSError:
        return None


def _file_sha256_or_empty(path: Path) -> str:
    signature = _file_signature(path)
    return signature[1] if signature is not None else ""


def _scan_sweep_constraints(
    scan_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    parameters = _manifest_mapping(
        scan_manifest,
        "parameters",
    )
    constraints: dict[str, Any] = {}
    for name in ["depth_fraction", "asof_latency_ns"]:
        value = _number(parameters.get(name), np.nan)
        if np.isfinite(value):
            constraints[name] = value
    return constraints


def _values_match(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (bool, np.bool_)) or isinstance(
        right,
        (bool, np.bool_),
    ):
        return bool(left) == bool(right)
    if isinstance(left, (int, float, np.number)) and isinstance(
        right,
        (int, float, np.number),
    ):
        return _numbers_match(left, right)
    try:
        return json.dumps(
            _jsonable(left),
            sort_keys=True,
            separators=(",", ":"),
        ) == json.dumps(
            _jsonable(right),
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return str(left) == str(right)


def _combined_opportunities(parity: pd.DataFrame, boxes: pd.DataFrame) -> pd.DataFrame:
    parity_frame = parity.copy()
    box_frame = boxes.copy()
    if "scanner" not in parity_frame.columns:
        parity_frame["scanner"] = "parity"
    if "scanner" not in box_frame.columns:
        box_frame["scanner"] = "box"
    combined = pd.concat([parity_frame, box_frame], ignore_index=True, sort=False)
    for column in ["net_edge", "persistence_ticks", "qty", "edge_per_unit", "gross_edge", "total_cost"]:
        if column in combined.columns:
            combined[column] = pd.to_numeric(combined[column], errors="coerce")
    return combined


def _select_candidate(opportunities: pd.DataFrame) -> pd.Series | None:
    if opportunities.empty:
        return None
    work = opportunities.copy()
    if "net_edge" not in work.columns:
        return None
    work["_net_edge_sort"] = pd.to_numeric(work["net_edge"], errors="coerce")
    work["_persistence_sort"] = pd.to_numeric(work.get("persistence_ticks", 0), errors="coerce").fillna(0)
    work = work.loc[work["_net_edge_sort"].notna()].copy()
    if work.empty:
        return None
    return work.sort_values(["_net_edge_sort", "_persistence_sort"], ascending=False).iloc[0]


def _select_sweep_run(
    sweep_summary: pd.Series,
    sweep_runs: pd.DataFrame,
    *,
    latency_seed_robustness: pd.DataFrame,
    seed_robustness_enabled: bool,
    constraints: Mapping[str, Any] | None,
) -> pd.Series:
    work = _constrain_sweep_rows(
        sweep_runs.copy(),
        constraints,
    )
    if work.empty:
        return pd.Series(dtype=object)
    if seed_robustness_enabled:
        robust = _constrain_sweep_rows(
            latency_seed_robustness.copy(),
            constraints,
        )
        if robust.empty:
            return pd.Series(dtype=object)
        passed_groups = robust.loc[
            robust["latency_seed_group_passed"].map(_to_bool)
        ].copy()
        if passed_groups.empty:
            return pd.Series(dtype=object)
        selected_group = passed_groups.sort_values(
            [
                "latency_seed_worst_robust_score",
                "latency_seed_worst_net_pnl",
                "latency_seed_group",
            ],
            ascending=[False, False, True],
            kind="stable",
        ).iloc[0]
        if "latency_seed_group" not in work.columns:
            return pd.Series(dtype=object)
        group_runs = work.loc[
            work["latency_seed_group"].astype(str)
            == str(selected_group["latency_seed_group"])
        ].copy()
        if not _seed_group_consistent(
            group_runs,
            selected_group,
        ):
            return pd.Series(dtype=object)
        worst_run = str(
            selected_group["latency_seed_worst_run"]
        )
        matched = group_runs.loc[
            group_runs["run"].astype(str) == worst_run
        ]
        if matched.empty:
            matched = group_runs.sort_values(
                ["robust_score", "net_pnl", "run"],
                ascending=[True, True, True],
                kind="stable",
            )
        if matched.empty:
            return pd.Series(dtype=object)
        selected = matched.iloc[0].copy()
        for key in LATENCY_SEED_ROBUSTNESS_COLUMNS:
            selected[key] = selected_group[key]
        return selected
    if "proof_passed" in work.columns:
        passed = work.loc[work["proof_passed"].map(_to_bool)].copy()
        if not passed.empty:
            work = passed
    if "best_run" in sweep_summary and "run" in work.columns:
        best_run = str(sweep_summary.get("best_run", ""))
        matched = work.loc[work["run"].astype(str) == best_run]
        if not matched.empty:
            return matched.iloc[0]
    sort_cols = [column for column in ["robust_score", "net_pnl"] if column in work.columns]
    if sort_cols:
        return work.sort_values(sort_cols, ascending=False).iloc[0]
    return work.iloc[0]


def _constrain_sweep_rows(
    frame: pd.DataFrame,
    constraints: Mapping[str, Any] | None,
) -> pd.DataFrame:
    if frame.empty or not constraints:
        return frame
    constrained = frame
    for column, expected in constraints.items():
        if column not in constrained.columns:
            return constrained.iloc[0:0].copy()
        values = pd.to_numeric(
            constrained[column],
            errors="coerce",
        )
        expected_number = _number(expected, np.nan)
        if not np.isfinite(expected_number):
            return constrained.iloc[0:0].copy()
        constrained = constrained.loc[
            values.notna()
            & np.isclose(
                values,
                expected_number,
                rtol=0.0,
                atol=1e-12,
            )
        ].copy()
    return constrained


def _seed_group_consistent(
    runs: pd.DataFrame,
    aggregate: pd.Series,
) -> bool:
    if runs.empty:
        return False
    required = [
        "run",
        "latency_seed_group",
        "latency_seed",
        "proof_passed",
        "robust_score",
        "net_pnl",
        "fills",
        "max_drawdown",
        "depth_fraction",
        "asof_latency_ns",
        "feed_latency_us",
        "order_latency_us",
        "latency_jitter_us",
    ]
    if any(column not in runs.columns for column in required):
        return False
    if runs["run"].astype(str).duplicated().any():
        return False
    aggregate_group = str(
        aggregate.get("latency_seed_group", "")
    )
    if (
        not aggregate_group
        or not runs["latency_seed_group"]
        .astype(str)
        .eq(aggregate_group)
        .all()
    ):
        return False
    passed = runs["proof_passed"].map(_to_bool)
    seeds = pd.to_numeric(
        runs["latency_seed"],
        errors="coerce",
    )
    if (
        seeds.isna().any()
        or seeds.lt(0).any()
        or seeds.mod(1).ne(0).any()
    ):
        return False
    seed_values = sorted(seeds.astype(int).unique().tolist())
    declared_seed_values = [
        value.strip()
        for value in str(
            aggregate.get("latency_seed_values", "")
        ).split(",")
        if value.strip()
    ]
    try:
        parsed_seed_values = sorted(
            int(value) for value in declared_seed_values
        )
    except ValueError:
        return False
    if (
        parsed_seed_values != seed_values
        or len(parsed_seed_values) != len(set(parsed_seed_values))
    ):
        return False

    integer_fields = {
        key: _exact_integer(aggregate.get(key))
        for key in [
            "latency_seed_runs",
            "latency_seed_expected_runs",
            "latency_seed_count",
            "latency_seed_passed_runs",
            "latency_seed_bound_violations",
        ]
    }
    if any(value is None for value in integer_fields.values()):
        return False
    expected_seed_runs = integer_fields[
        "latency_seed_expected_runs"
    ]
    if expected_seed_runs is None or expected_seed_runs <= 0:
        return False
    bound_violations = _raw_seed_bound_violations(runs)
    if bound_violations is None:
        return False
    expected_values = {
        "latency_seed_runs": len(runs),
        "latency_seed_count": len(seed_values),
        "latency_seed_passed_runs": int(passed.sum()),
        "latency_seed_bound_violations": bound_violations,
    }
    if any(
        integer_fields[key] != value
        for key, value in expected_values.items()
    ):
        return False

    for column in [
        "depth_fraction",
        "asof_latency_ns",
        "feed_latency_us",
        "order_latency_us",
        "latency_jitter_us",
    ]:
        values = pd.to_numeric(runs[column], errors="coerce")
        if (
            values.isna().any()
            or not np.allclose(
                values.to_numpy(dtype=float),
                float(values.iloc[0]),
                rtol=0.0,
                atol=1e-12,
            )
            or not _numbers_match(
                aggregate.get(column),
                values.iloc[0],
            )
        ):
            return False

    scored = runs.copy()
    scored["_robust_score"] = pd.to_numeric(
        scored["robust_score"],
        errors="coerce",
    )
    scored["_net_pnl"] = pd.to_numeric(
        scored["net_pnl"],
        errors="coerce",
    )
    fills = pd.to_numeric(scored["fills"], errors="coerce")
    drawdowns = pd.to_numeric(
        scored["max_drawdown"],
        errors="coerce",
    )
    if (
        scored[["_robust_score", "_net_pnl"]].isna().any().any()
        or fills.isna().any()
        or fills.mod(1).ne(0).any()
    ):
        return False
    worst = scored.sort_values(
        ["_robust_score", "_net_pnl", "run"],
        ascending=[True, True, True],
        kind="stable",
    ).iloc[0]
    aggregate_pass_rate = _number(
        aggregate.get("latency_seed_pass_rate"),
        np.nan,
    )
    if (
        not np.isfinite(aggregate_pass_rate)
        or abs(aggregate_pass_rate - float(passed.mean())) > 1e-12
    ):
        return False
    expected_group_passed = bool(
        passed.all()
        and len(runs) == expected_seed_runs
        and len(seed_values) == expected_seed_runs
        and bound_violations == 0
    )
    if _to_bool(
        aggregate.get("latency_seed_group_passed", False)
    ) != expected_group_passed:
        return False
    if str(aggregate.get("latency_seed_worst_run", "")) != str(
        worst["run"]
    ):
        return False
    if _exact_integer(
        aggregate.get("latency_seed_worst_seed")
    ) != int(worst["latency_seed"]):
        return False
    expected_metrics = {
        "latency_seed_worst_robust_score": worst[
            "_robust_score"
        ],
        "latency_seed_worst_net_pnl": worst["_net_pnl"],
        "latency_seed_median_net_pnl": scored[
            "_net_pnl"
        ].median(),
        "latency_seed_best_net_pnl": scored["_net_pnl"].max(),
        "latency_seed_min_fills": int(fills.min()),
        "latency_seed_worst_drawdown": (
            drawdowns.max(skipna=True)
        ),
    }
    for key, value in expected_metrics.items():
        if not _numbers_match(aggregate.get(key), value):
            return False
    return True


def _raw_seed_bound_violations(
    runs: pd.DataFrame,
) -> int | None:
    total = 0
    for column in [
        "parity_feed_latency_bound_violations",
        "parity_order_latency_bound_violations",
        "parity_latency_configuration_violations",
    ]:
        if column not in runs.columns:
            continue
        values = pd.to_numeric(runs[column], errors="coerce")
        if (
            values.isna().any()
            or values.lt(0).any()
            or values.mod(1).ne(0).any()
        ):
            return None
        total += int(values.sum())
    return total


def _exact_integer(value: Any) -> int | None:
    number = _number(value, np.nan)
    if (
        not np.isfinite(number)
        or number % 1 != 0
    ):
        return None
    return int(number)


def _numbers_match(left: Any, right: Any) -> bool:
    left_number = _number(left, np.nan)
    right_number = _number(right, np.nan)
    if np.isnan(left_number) and np.isnan(right_number):
        return True
    return bool(
        np.isfinite(left_number)
        and np.isfinite(right_number)
        and np.isclose(
            left_number,
            right_number,
            rtol=0.0,
            atol=1e-12,
        )
    )


def _checks(
    edge: pd.Series,
    sweep: pd.Series,
    candidate: pd.Series | None,
    sweep_run: pd.Series,
    thresholds: ParityCandidatePromotionThresholds,
    *,
    seed_robustness_enabled: bool,
) -> pd.DataFrame:
    edge_passed = _to_bool(edge.get("passed", False))
    passed_scenarios = _number(sweep.get("passed_scenarios"), 0)
    candidate_net_edge = _number(candidate.get("net_edge") if candidate is not None else None, np.nan)
    candidate_persistence = _number(candidate.get("persistence_ticks") if candidate is not None else None, np.nan)
    rows = [
            _check(
                "edge_audit_passed",
                edge_passed,
                "is",
                True,
                edge_passed or not thresholds.require_edge_passed,
                "parity edge audit did not pass",
            ),
            _threshold_check("total_opportunities", _number(edge.get("total_opportunities"), np.nan), ">=", thresholds.min_total_opportunities),
            _threshold_check("best_net_edge", _number(edge.get("best_net_edge"), np.nan), ">=", thresholds.min_best_net_edge),
            _check(
                "candidate_available",
                1 if candidate is not None else 0,
                ">=",
                1,
                candidate is not None,
                "no parity or box opportunity is available",
            ),
            _threshold_check("candidate_net_edge", candidate_net_edge, ">=", thresholds.min_candidate_net_edge),
            _threshold_check(
                "candidate_persistence_ticks",
                candidate_persistence,
                ">=",
                thresholds.min_candidate_persistence_ticks,
            ),
            _check(
                "candidate_leg_prices_available",
                _leg_price_count(candidate),
                ">=",
                _expected_leg_count(candidate),
                _leg_prices_available(candidate),
                "selected opportunity does not carry all leg prices",
            ),
            _threshold_check("sweep_pass_rate", _number(sweep.get("pass_rate"), np.nan), ">=", thresholds.min_sweep_pass_rate),
            _threshold_check("passed_scenarios", passed_scenarios, ">=", thresholds.min_passed_scenarios),
            _check(
                "sweep_passed_scenario_available",
                passed_scenarios,
                ">=",
                1,
                (passed_scenarios >= 1) or not thresholds.require_sweep_passed_scenario,
                "parity sweep has no passed scenario",
            ),
            _check(
                "sweep_run_available",
                0 if sweep_run.empty else 1,
                ">=",
                1,
                not sweep_run.empty,
                "no sweep run is available for replay defaults",
            ),
        ]
    if seed_robustness_enabled:
        seed_group_available = not sweep_run.empty
        seed_group_passed = (
            _to_bool(
                sweep_run.get(
                    "latency_seed_group_passed",
                    False,
                )
            )
            if seed_group_available
            else False
        )
        seed_pass_rate = _number(
            sweep_run.get("latency_seed_pass_rate"),
            np.nan,
        )
        rows.extend(
            [
                _check(
                    "latency_seed_robust_group_available",
                    1 if seed_group_available else 0,
                    ">=",
                    1,
                    seed_group_available,
                    "no fully passing latency-seed group is available",
                ),
                _check(
                    "latency_seed_group_passed",
                    seed_group_passed,
                    "is",
                    True,
                    seed_group_passed,
                    "selected latency configuration did not pass every seed",
                ),
                _threshold_check(
                    "latency_seed_pass_rate",
                    seed_pass_rate,
                    ">=",
                    1.0,
                ),
            ]
        )
    return pd.DataFrame(rows)


def _candidate_record(
    opportunity: pd.Series,
    edge: pd.Series,
    sweep: pd.Series,
    sweep_run: pd.Series,
    market: str,
) -> dict[str, Any]:
    direction = str(opportunity.get("direction", ""))
    scanner = str(opportunity.get("scanner", "parity"))
    scenario_key = _scenario_key(opportunity, market)
    record = {
        "scenario_key": scenario_key,
        "strategy": PARITY_BOX_STRATEGY,
        "market": market,
        "source_run_type": "parity_scan_edge_sweep",
        "scanner": scanner,
        "direction": direction,
        "leg_family": "box" if direction in BOX_DIRECTIONS or scanner == "box" else "parity",
        "ts": _jsonable(opportunity.get("ts")),
        "expiry": _jsonable(opportunity.get("expiry")),
        "qty": _jsonable(opportunity.get("qty")),
        "edge_per_unit": _jsonable(opportunity.get("edge_per_unit")),
        "gross_edge": _jsonable(opportunity.get("gross_edge")),
        "total_cost": _jsonable(opportunity.get("total_cost")),
        "net_edge": _jsonable(opportunity.get("net_edge")),
        "persistence_ticks": _jsonable(opportunity.get("persistence_ticks")),
        "displayed_depth": _jsonable(opportunity.get("displayed_depth")),
        "regime": _jsonable(opportunity.get("regime")),
        "edge_total_opportunities": _jsonable(edge.get("total_opportunities")),
        "edge_best_net_edge": _jsonable(edge.get("best_net_edge")),
        "sweep_pass_rate": _jsonable(sweep.get("pass_rate")),
        "sweep_passed_scenarios": _jsonable(sweep.get("passed_scenarios")),
        "sweep_best_run": _jsonable(sweep_run.get("run", sweep.get("best_run"))),
        "depth_fraction": _jsonable(sweep_run.get("depth_fraction")),
        "asof_latency_ns": _jsonable(sweep_run.get("asof_latency_ns")),
        "feed_latency_us": _jsonable(sweep_run.get("feed_latency_us")),
        "order_latency_us": _jsonable(sweep_run.get("order_latency_us")),
        "latency_jitter_us": _jsonable(
            sweep_run.get("latency_jitter_us", 0.0)
        ),
        "latency_seed": _jsonable(
            sweep_run.get("latency_seed", 17)
        ),
        "sweep_net_pnl": _jsonable(sweep_run.get("net_pnl")),
        "sweep_fills": _jsonable(sweep_run.get("fills")),
        "sweep_robust_score": _jsonable(sweep_run.get("robust_score")),
    }
    for key in LATENCY_SEED_PROMOTION_METRICS:
        if key in sweep_run.index:
            record[key] = _jsonable(sweep_run.get(key))
    if (
        "max_futures_quote_age_ns" in sweep_run.index
        or "parity_futures_max_quote_age_ns" in sweep_run.index
    ):
        record["max_futures_quote_age_ns"] = _jsonable(
            sweep_run.get(
                "max_futures_quote_age_ns",
                sweep_run.get("parity_futures_max_quote_age_ns"),
            )
        )
    for target, source in [
        (
            "max_leg_book_age_ns",
            "parity_execution_max_leg_book_age_ns",
        ),
        (
            "max_leg_book_skew_ns",
            "parity_execution_max_leg_book_skew_ns",
        ),
    ]:
        if target in sweep_run.index or source in sweep_run.index:
            record[target] = _jsonable(
                sweep_run.get(target, sweep_run.get(source))
            )
    if direction in BOX_DIRECTIONS or scanner == "box":
        record.update(
            {
                "low_strike": _jsonable(opportunity.get("low_strike")),
                "high_strike": _jsonable(opportunity.get("high_strike")),
                "low_call_price": _jsonable(opportunity.get("low_call_price")),
                "low_put_price": _jsonable(opportunity.get("low_put_price")),
                "high_call_price": _jsonable(opportunity.get("high_call_price")),
                "high_put_price": _jsonable(opportunity.get("high_put_price")),
            }
        )
    else:
        record.update(
            {
                "strike": _jsonable(opportunity.get("strike")),
                "call_price": _jsonable(opportunity.get("call_price")),
                "put_price": _jsonable(opportunity.get("put_price")),
                "future_price": _jsonable(opportunity.get("future_price")),
                "future_ts": _jsonable(opportunity.get("future_ts")),
                "futures_lookup_ts": _jsonable(
                    opportunity.get("futures_lookup_ts")
                ),
                "future_asof_age_ns": _jsonable(
                    opportunity.get("future_asof_age_ns")
                ),
                "future_decision_age_ns": _jsonable(
                    opportunity.get("future_decision_age_ns")
                ),
            }
        )
    return record


def _summary(candidate: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    row = candidate.iloc[0] if not candidate.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": str(row.get("scenario_key", "")),
                "strategy": str(row.get("strategy", PARITY_BOX_STRATEGY)),
                "market": str(row.get("market", "")),
                "direction": str(row.get("direction", "")),
                "latency_seed_count": int(
                    _number(row.get("latency_seed_count"), 0)
                ),
                "latency_seed_pass_rate": _number(
                    row.get("latency_seed_pass_rate"),
                    np.nan,
                ),
                "checks": int(len(checks)),
                "failed_checks": failed,
                "recommendation": "paper_or_shadow_candidate" if ready else "keep_in_research",
            }
        ]
    )


def _promotion_candidate_config(
    candidate: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.Series,
    thresholds: ParityCandidatePromotionThresholds,
) -> dict[str, Any]:
    failed_checks = checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist()
    if candidate.empty:
        return {
            "schema_version": 1,
            "ready": False,
            "strategy": PARITY_BOX_STRATEGY,
            "scenario_key": "",
            "parameters": {},
            "replay_defaults": {},
            "metrics": {},
            "failed_checks": failed_checks,
            "thresholds": asdict(thresholds),
            "recommendation": str(summary["recommendation"]),
        }
    row = candidate.iloc[0]
    parameters = {
        key: _jsonable(row.get(key))
        for key in [
            "market",
            "scanner",
            "direction",
            "leg_family",
            "ts",
            "expiry",
            "strike",
            "low_strike",
            "high_strike",
            "qty",
            "call_price",
            "put_price",
            "future_price",
            "low_call_price",
            "low_put_price",
            "high_call_price",
            "high_put_price",
            "net_edge",
            "edge_per_unit",
            "persistence_ticks",
            "future_ts",
            "futures_lookup_ts",
            "future_asof_age_ns",
            "future_decision_age_ns",
        ]
        if key in row.index
    }
    replay_defaults = {
        key: _jsonable(row.get(key))
        for key in [
            "depth_fraction",
            "asof_latency_ns",
            "max_futures_quote_age_ns",
            "max_leg_book_age_ns",
            "max_leg_book_skew_ns",
            "feed_latency_us",
            "order_latency_us",
            "latency_jitter_us",
            "latency_seed",
        ]
        if key in row.index
    }
    metrics = {
        key: _jsonable(row.get(key))
        for key in [
            "gross_edge",
            "total_cost",
            "displayed_depth",
            "edge_total_opportunities",
            "edge_best_net_edge",
            "sweep_pass_rate",
            "sweep_passed_scenarios",
            "sweep_best_run",
            "sweep_net_pnl",
            "sweep_fills",
            "sweep_robust_score",
            *LATENCY_SEED_PROMOTION_METRICS,
            *PARITY_PROMOTION_LINEAGE_METRICS,
        ]
        if key in row.index
    }
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "strategy": PARITY_BOX_STRATEGY,
        "scenario_key": str(row["scenario_key"]),
        "parameters": parameters,
        "replay_defaults": replay_defaults,
        "metrics": metrics,
        "failed_checks": failed_checks,
        "thresholds": asdict(thresholds),
        "recommendation": str(summary["recommendation"]),
    }


def _empty_candidate() -> pd.DataFrame:
    return pd.DataFrame(columns=["scenario_key", "strategy", "market", "direction"])


def _scenario_key(opportunity: pd.Series, market: str) -> str:
    direction = str(opportunity.get("direction", ""))
    pieces: list[tuple[str, Any]] = [
        ("strategy", PARITY_BOX_STRATEGY),
        ("market", market),
        ("direction", direction),
        ("expiry", opportunity.get("expiry")),
    ]
    if direction in BOX_DIRECTIONS or str(opportunity.get("scanner", "")) == "box":
        pieces.extend(
            [
                ("low_strike", opportunity.get("low_strike")),
                ("high_strike", opportunity.get("high_strike")),
            ]
        )
    else:
        pieces.append(("strike", opportunity.get("strike")))
    return "|".join(f"{key}={_format_value(value)}" for key, value in pieces)


def _leg_prices_available(candidate: pd.Series | None) -> bool:
    if candidate is None:
        return False
    direction = str(candidate.get("direction", ""))
    if direction in PARITY_DIRECTIONS:
        keys = ["call_price", "put_price", "future_price"]
    elif direction in BOX_DIRECTIONS or str(candidate.get("scanner", "")) == "box":
        keys = ["low_call_price", "low_put_price", "high_call_price", "high_put_price"]
    else:
        return False
    return all(not pd.isna(_number(candidate.get(key), np.nan)) and _number(candidate.get(key), np.nan) > 0 for key in keys)


def _leg_price_count(candidate: pd.Series | None) -> int:
    if candidate is None:
        return 0
    keys = ["call_price", "put_price", "future_price", "low_call_price", "low_put_price", "high_call_price", "high_put_price"]
    return int(sum(1 for key in keys if key in candidate.index and not pd.isna(_number(candidate.get(key), np.nan))))


def _expected_leg_count(candidate: pd.Series | None) -> int:
    if candidate is None:
        return 1
    direction = str(candidate.get("direction", ""))
    if direction in BOX_DIRECTIONS or str(candidate.get("scanner", "")) == "box":
        return 4
    if direction in PARITY_DIRECTIONS:
        return 3
    return 1


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
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
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: ParityCandidatePromotionThresholds) -> None:
    if thresholds.min_total_opportunities < 0:
        raise ValueError("min_total_opportunities must be non-negative")
    if thresholds.min_candidate_persistence_ticks < 0:
        raise ValueError("min_candidate_persistence_ticks must be non-negative")
    if not 0 <= thresholds.min_sweep_pass_rate <= 1:
        raise ValueError("min_sweep_pass_rate must be between 0 and 1")
    if thresholds.min_passed_scenarios < 0:
        raise ValueError("min_passed_scenarios must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
    if frame.empty:
        raise ValueError(f"{name} must not be empty")


def _number(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if np.isnan(number) else number


def _to_bool(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _format_value(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
