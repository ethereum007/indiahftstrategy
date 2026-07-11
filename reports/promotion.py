from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)


SCORE_METRIC_COLUMNS = {
    "rank",
    "scenario_key",
    "sweeps_seen",
    "scenario_runs",
    "passed_runs",
    "pass_rate",
    "median_net_pnl",
    "mean_net_pnl",
    "min_net_pnl",
    "total_net_pnl",
    "median_robust_score",
    "min_robust_score",
    "worst_drawdown",
    "median_fills",
    "min_fills",
    "worst_regime_equity_change",
    "runs_with_losing_regimes",
    "selection_passed",
}


@dataclass(frozen=True)
class PromotionThresholds:
    min_pass_rate: float = 1.0
    min_sweeps: int = 1
    min_median_net_pnl: float = 0.0
    min_min_net_pnl: float | None = None
    max_worst_drawdown: float | None = None
    min_median_fills: float = 1.0
    max_runs_with_losing_regimes: int | None = None
    max_otr: float | None = None
    min_maker_share: float | None = None
    min_markout_mean: float | None = None
    require_overfit_audit: bool = False
    require_significance_audit: bool = False
    require_holdout_audit: bool = False


@dataclass(frozen=True)
class PromotionReport:
    candidate: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_promotion(
    scenario_scores: pd.DataFrame,
    scenario_runs: pd.DataFrame,
    *,
    thresholds: PromotionThresholds | None = None,
    overfit_summary: pd.DataFrame | None = None,
    overfit_selection_matches: bool | None = None,
    significance_summary: pd.DataFrame | None = None,
    significance_selection_matches: bool | None = None,
    holdout_summary: pd.DataFrame | None = None,
    holdout_selection_matches: bool | None = None,
    upstream_integrity_passed: bool | None = None,
) -> PromotionReport:
    thresholds = thresholds or PromotionThresholds()
    _validate_thresholds(thresholds)
    scores = scenario_scores.copy()
    runs = scenario_runs.copy()
    overfit = pd.DataFrame() if overfit_summary is None else overfit_summary.copy()
    significance = (
        pd.DataFrame() if significance_summary is None else significance_summary.copy()
    )
    holdout = pd.DataFrame() if holdout_summary is None else holdout_summary.copy()
    _require(scores, ["scenario_key", "selection_passed"], "scenario_scores")
    _require(runs, ["run"], "scenario_runs")

    candidate = _select_candidate(scores)
    if candidate.empty:
        checks = pd.DataFrame(
            [
                _check("selection_available", 0, ">=", 1, False, "no scenarios available"),
                *_overfit_checks(overfit, thresholds, overfit_selection_matches),
                *_significance_checks(
                    significance,
                    thresholds,
                    significance_selection_matches,
                ),
                *_holdout_checks(
                    holdout,
                    thresholds,
                    holdout_selection_matches,
                    expected_candidate="",
                ),
                *_upstream_integrity_checks(upstream_integrity_passed),
            ]
        )
        summary = _summary(
            candidate,
            checks,
            overfit,
            overfit_selection_matches,
            significance,
            significance_selection_matches,
            holdout,
            holdout_selection_matches,
            upstream_integrity_passed,
        )
        return PromotionReport(candidate=candidate, checks=checks, summary=summary)

    row = candidate.iloc[0]
    candidate_runs = _candidate_runs(runs, row, _parameter_columns(scores))
    checks = _checks(
        row,
        candidate_runs,
        thresholds,
        overfit,
        overfit_selection_matches,
        significance,
        significance_selection_matches,
        holdout,
        holdout_selection_matches,
        upstream_integrity_passed,
    )
    summary = _summary(
        candidate,
        checks,
        overfit,
        overfit_selection_matches,
        significance,
        significance_selection_matches,
        holdout,
        holdout_selection_matches,
        upstream_integrity_passed,
    )
    return PromotionReport(candidate=candidate, checks=checks, summary=summary)


def write_promotion_report(
    selection_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: PromotionThresholds | None = None,
    overfit_audit_path: str | Path | None = None,
    significance_audit_path: str | Path | None = None,
    holdout_audit_path: str | Path | None = None,
    upstream_integrity_passed: bool | None = None,
    upstream_integrity_path: str | Path | None = None,
) -> PromotionReport:
    selection = Path(selection_path)
    scores_path = selection / "scenario_scores.csv"
    runs_path = selection / "scenario_runs.csv"
    if not scores_path.exists():
        raise FileNotFoundError(f"scenario_scores.csv not found: {scores_path}")
    if not runs_path.exists():
        raise FileNotFoundError(f"scenario_runs.csv not found: {runs_path}")

    thresholds = thresholds or PromotionThresholds()
    overfit_summary, overfit_config, overfit_input = _read_overfit_audit(overfit_audit_path)
    overfit_selection_matches = _overfit_selection_matches(selection, overfit_config)
    significance_summary, significance_config, significance_input = (
        _read_significance_audit(significance_audit_path)
    )
    significance_selection_matches = _audit_selection_matches(
        selection,
        significance_config,
    )
    holdout_summary, holdout_config, holdout_input = _read_holdout_audit(
        holdout_audit_path
    )
    holdout_selection_matches = _audit_selection_matches(
        selection,
        holdout_config,
    )
    report = evaluate_promotion(
        pd.read_csv(scores_path),
        pd.read_csv(runs_path),
        thresholds=thresholds,
        overfit_summary=overfit_summary,
        overfit_selection_matches=overfit_selection_matches,
        significance_summary=significance_summary,
        significance_selection_matches=significance_selection_matches,
        holdout_summary=holdout_summary,
        holdout_selection_matches=holdout_selection_matches,
        upstream_integrity_passed=upstream_integrity_passed,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.candidate.to_csv(out / "promotion_candidate.csv", index=False)
    report.checks.to_csv(out / "promotion_checks.csv", index=False)
    report.summary.to_csv(out / "promotion_summary.csv", index=False)
    (out / "candidate_config.json").write_text(
        json.dumps(
            _candidate_config(
                report,
                thresholds,
                overfit_summary,
                overfit_selection_matches,
                significance_summary,
                significance_selection_matches,
                holdout_summary,
                holdout_selection_matches,
                upstream_integrity_passed,
                upstream_integrity_path,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {"selection": selection}
    if overfit_input is not None:
        inputs["backtest_overfit_audit"] = overfit_input
        overfit_manifest = (
            overfit_input / "manifest.json"
            if overfit_input.is_dir()
            else overfit_input.parent / "manifest.json"
        )
        if overfit_manifest.is_file():
            inputs["backtest_overfit_audit_manifest"] = overfit_manifest
    if significance_input is not None:
        inputs["backtest_significance_audit"] = significance_input
        significance_manifest = (
            significance_input / "manifest.json"
            if significance_input.is_dir()
            else significance_input.parent / "manifest.json"
        )
        if significance_manifest.is_file():
            inputs["backtest_significance_audit_manifest"] = significance_manifest
    if holdout_input is not None:
        inputs["backtest_holdout_audit"] = holdout_input
        holdout_manifest = (
            holdout_input / "manifest.json"
            if holdout_input.is_dir()
            else holdout_input.parent / "manifest.json"
        )
        if holdout_manifest.is_file():
            inputs["backtest_holdout_audit_manifest"] = holdout_manifest
    if upstream_integrity_path is not None:
        inputs["upstream_integrity"] = Path(upstream_integrity_path)
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={
            "thresholds": asdict(thresholds),
            "upstream_integrity_required": upstream_integrity_passed is not None,
        },
        inputs=inputs,
    )
    return PromotionReport(report.candidate, report.checks, report.summary, out)


def _select_candidate(scores: pd.DataFrame) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame(columns=scores.columns)
    work = scores.copy()
    work["selection_passed"] = work["selection_passed"].map(_to_bool)
    if "rank" in work.columns:
        work["_rank_sort"] = pd.to_numeric(work["rank"], errors="coerce").fillna(len(work) + 1)
    else:
        work["_rank_sort"] = np.arange(1, len(work) + 1)
    selectable = work.loc[work["selection_passed"]].sort_values("_rank_sort")
    chosen = selectable.head(1) if not selectable.empty else work.sort_values("_rank_sort").head(1)
    return chosen.drop(columns=["_rank_sort"]).reset_index(drop=True)


def _checks(
    row: pd.Series,
    candidate_runs: pd.DataFrame,
    thresholds: PromotionThresholds,
    overfit_summary: pd.DataFrame,
    overfit_selection_matches: bool | None,
    significance_summary: pd.DataFrame,
    significance_selection_matches: bool | None,
    holdout_summary: pd.DataFrame,
    holdout_selection_matches: bool | None,
    upstream_integrity_passed: bool | None,
) -> pd.DataFrame:
    checks = [
        _check(
            "selection_passed",
            _to_bool(row.get("selection_passed", False)),
            "is",
            True,
            _to_bool(row.get("selection_passed", False)),
            "candidate was not marked selectable by compare-sweeps",
        ),
        _numeric_check(row, "pass_rate", ">=", thresholds.min_pass_rate),
        _numeric_check(row, "sweeps_seen", ">=", thresholds.min_sweeps),
        _numeric_check(row, "median_net_pnl", ">=", thresholds.min_median_net_pnl),
        _numeric_check(row, "median_fills", ">=", thresholds.min_median_fills),
    ]
    if thresholds.min_min_net_pnl is not None:
        checks.append(_numeric_check(row, "min_net_pnl", ">=", thresholds.min_min_net_pnl))
    if thresholds.max_worst_drawdown is not None:
        checks.append(_numeric_check(row, "worst_drawdown", "<=", thresholds.max_worst_drawdown))
    if thresholds.max_runs_with_losing_regimes is not None:
        checks.append(
            _numeric_check(row, "runs_with_losing_regimes", "<=", thresholds.max_runs_with_losing_regimes)
        )
    if thresholds.max_otr is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "order_to_trade_ratio",
                "max_order_to_trade_ratio",
                "<=",
                thresholds.max_otr,
                reducer="max",
            )
        )
    if thresholds.min_maker_share is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "maker_share",
                "min_maker_share",
                ">=",
                thresholds.min_maker_share,
                reducer="min",
            )
        )
    if thresholds.min_markout_mean is not None:
        checks.append(
            _run_metric_check(
                candidate_runs,
                "markout_mean",
                "min_markout_mean",
                ">=",
                thresholds.min_markout_mean,
                reducer="min",
            )
        )
    checks.extend(_overfit_checks(overfit_summary, thresholds, overfit_selection_matches))
    checks.extend(
        _significance_checks(
            significance_summary,
            thresholds,
            significance_selection_matches,
        )
    )
    checks.extend(
        _holdout_checks(
            holdout_summary,
            thresholds,
            holdout_selection_matches,
            expected_candidate=str(row.get("scenario_key", "")),
        )
    )
    checks.extend(_upstream_integrity_checks(upstream_integrity_passed))
    return pd.DataFrame(checks)


def _overfit_checks(
    overfit_summary: pd.DataFrame,
    thresholds: PromotionThresholds,
    overfit_selection_matches: bool | None,
) -> list[dict[str, Any]]:
    provided = not overfit_summary.empty
    rows: list[dict[str, Any]] = []
    if thresholds.require_overfit_audit:
        rows.append(
            _check(
                "overfit_audit_provided",
                provided,
                "is",
                True,
                provided,
                "backtest overfit audit is required before promotion",
            )
        )
    if not provided:
        return rows
    summary = overfit_summary.iloc[0]
    passed = _to_bool(summary.get("passed", summary.get("ready", False)))
    rows.extend(
        [
            _check(
                "overfit_audit_passed",
                passed,
                "is",
                True,
                passed,
                "backtest overfit audit did not pass",
            ),
            _check(
                "overfit_selection_matches",
                bool(overfit_selection_matches),
                "is",
                True,
                bool(overfit_selection_matches),
                "backtest overfit audit was generated from a different selection artifact",
            ),
            _check(
                "overfit_audit_manifest_current",
                _to_bool(summary.get("_artifact_integrity_current", True)),
                "is",
                True,
                _to_bool(summary.get("_artifact_integrity_current", True)),
                "backtest overfit audit artifacts no longer match its manifest",
            ),
        ]
    )
    return rows


def _upstream_integrity_checks(
    upstream_integrity_passed: bool | None,
) -> list[dict[str, Any]]:
    if upstream_integrity_passed is None:
        return []
    passed = bool(upstream_integrity_passed)
    return [
        _check(
            "upstream_integrity_passed",
            passed,
            "is",
            True,
            passed,
            "upstream research artifacts did not pass manifest integrity review",
        )
    ]


def _significance_checks(
    significance_summary: pd.DataFrame,
    thresholds: PromotionThresholds,
    significance_selection_matches: bool | None,
) -> list[dict[str, Any]]:
    provided = not significance_summary.empty
    rows: list[dict[str, Any]] = []
    if thresholds.require_significance_audit:
        rows.append(
            _check(
                "significance_audit_provided",
                provided,
                "is",
                True,
                provided,
                "backtest significance audit is required before promotion",
            )
        )
    if not provided:
        return rows
    summary = significance_summary.iloc[0]
    passed = _to_bool(summary.get("passed", summary.get("ready", False)))
    manifest_current = _to_bool(summary.get("_artifact_integrity_current", True))
    rows.extend(
        [
            _check(
                "significance_audit_passed",
                passed,
                "is",
                True,
                passed,
                "backtest significance audit did not pass",
            ),
            _check(
                "significance_selection_matches",
                bool(significance_selection_matches),
                "is",
                True,
                bool(significance_selection_matches),
                "backtest significance audit was generated from a different selection artifact",
            ),
            _check(
                "significance_audit_manifest_current",
                manifest_current,
                "is",
                True,
                manifest_current,
                "backtest significance artifacts no longer match their manifest",
            ),
        ]
    )
    return rows


def _holdout_checks(
    holdout_summary: pd.DataFrame,
    thresholds: PromotionThresholds,
    holdout_selection_matches: bool | None,
    *,
    expected_candidate: str,
) -> list[dict[str, Any]]:
    provided = not holdout_summary.empty
    rows: list[dict[str, Any]] = []
    if thresholds.require_holdout_audit:
        rows.append(
            _check(
                "holdout_audit_provided",
                provided,
                "is",
                True,
                provided,
                "chronological holdout audit is required before promotion",
            )
        )
    if not provided:
        return rows
    summary = holdout_summary.iloc[0]
    passed = _to_bool(summary.get("passed", summary.get("ready", False)))
    manifest_current = _to_bool(summary.get("_artifact_integrity_current", True))
    audited_candidate = str(summary.get("candidate_scenario", ""))
    candidate_matches = bool(
        expected_candidate and audited_candidate == expected_candidate
    )
    rows.extend(
        [
            _check(
                "holdout_audit_passed",
                passed,
                "is",
                True,
                passed,
                "chronological holdout audit did not pass",
            ),
            _check(
                "holdout_selection_matches",
                bool(holdout_selection_matches),
                "is",
                True,
                bool(holdout_selection_matches),
                "holdout audit was generated from a different selection artifact",
            ),
            _check(
                "holdout_candidate_matches",
                candidate_matches,
                "is",
                True,
                candidate_matches,
                "holdout audit evaluated a different candidate",
            ),
            _check(
                "holdout_audit_manifest_current",
                manifest_current,
                "is",
                True,
                manifest_current,
                "holdout artifacts or inputs no longer match their manifest",
            ),
        ]
    )
    return rows


def _summary(
    candidate: pd.DataFrame,
    checks: pd.DataFrame,
    overfit_summary: pd.DataFrame,
    overfit_selection_matches: bool | None,
    significance_summary: pd.DataFrame,
    significance_selection_matches: bool | None,
    holdout_summary: pd.DataFrame,
    holdout_selection_matches: bool | None,
    upstream_integrity_passed: bool | None,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    key = "" if candidate.empty or "scenario_key" not in candidate.columns else str(candidate.iloc[0]["scenario_key"])
    recommendation = "paper_or_shadow_candidate" if ready else "keep_in_research"
    overfit = overfit_summary.iloc[0] if not overfit_summary.empty else pd.Series(dtype=object)
    significance = (
        significance_summary.iloc[0]
        if not significance_summary.empty
        else pd.Series(dtype=object)
    )
    holdout = (
        holdout_summary.iloc[0]
        if not holdout_summary.empty
        else pd.Series(dtype=object)
    )
    holdout_candidate_matches = bool(
        key and str(holdout.get("candidate_scenario", "")) == key
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "candidate_scenario_key": key,
                "checks": int(len(checks)),
                "failed_checks": failed,
                "overfit_audit_provided": not overfit_summary.empty,
                "overfit_audit_passed": _to_bool(overfit.get("passed", overfit.get("ready", False))),
                "overfit_selection_matches": bool(overfit_selection_matches)
                if overfit_selection_matches is not None
                else False,
                "overfit_audit_manifest_current": _to_bool(
                    overfit.get("_artifact_integrity_current", not overfit_summary.empty)
                ),
                "probability_overfit": _float_or_nan(overfit.get("probability_overfit")),
                "significance_audit_provided": not significance_summary.empty,
                "significance_audit_passed": _to_bool(significance.get("passed", False)),
                "significance_selection_matches": bool(significance_selection_matches)
                if significance_selection_matches is not None
                else False,
                "significance_audit_manifest_current": _to_bool(
                    significance.get(
                        "_artifact_integrity_current",
                        not significance_summary.empty,
                    )
                ),
                "adjusted_sign_pvalue": _float_or_nan(
                    significance.get("adjusted_sign_pvalue")
                ),
                "bootstrap_probability_positive": _float_or_nan(
                    significance.get("bootstrap_probability_positive")
                ),
                "holdout_audit_provided": not holdout_summary.empty,
                "holdout_audit_passed": _to_bool(holdout.get("passed", False)),
                "holdout_selection_matches": bool(holdout_selection_matches)
                if holdout_selection_matches is not None
                else False,
                "holdout_candidate_matches": holdout_candidate_matches,
                "holdout_audit_manifest_current": _to_bool(
                    holdout.get(
                        "_artifact_integrity_current",
                        not holdout_summary.empty,
                    )
                ),
                "holdout_sweep_count": _int_or_zero(
                    holdout.get("expected_sweeps", 0)
                ),
                "holdout_coverage_rate": _float_or_nan(
                    holdout.get("candidate_coverage_rate")
                ),
                "holdout_proof_pass_rate": _float_or_nan(
                    holdout.get("proof_pass_rate")
                ),
                "holdout_mean_score": _float_or_nan(holdout.get("mean_score")),
                "holdout_worst_score": _float_or_nan(holdout.get("worst_score")),
                "upstream_integrity_provided": upstream_integrity_passed is not None,
                "upstream_integrity_passed": bool(upstream_integrity_passed),
                "recommendation": recommendation,
            }
        ]
    )


def _candidate_config(
    report: PromotionReport,
    thresholds: PromotionThresholds,
    overfit_summary: pd.DataFrame,
    overfit_selection_matches: bool | None,
    significance_summary: pd.DataFrame,
    significance_selection_matches: bool | None,
    holdout_summary: pd.DataFrame,
    holdout_selection_matches: bool | None,
    upstream_integrity_passed: bool | None,
    upstream_integrity_path: str | Path | None,
) -> dict[str, Any]:
    overfit = _overfit_config_record(overfit_summary, overfit_selection_matches)
    significance = _significance_config_record(
        significance_summary,
        significance_selection_matches,
    )
    holdout = _holdout_config_record(
        holdout_summary,
        holdout_selection_matches,
        scenario_key=(
            ""
            if report.candidate.empty
            else str(report.candidate.iloc[0].get("scenario_key", ""))
        ),
    )
    upstream_integrity = {
        "provided": upstream_integrity_passed is not None,
        "passed": bool(upstream_integrity_passed),
        "evidence_path": str(Path(upstream_integrity_path).resolve())
        if upstream_integrity_path is not None
        else "",
    }
    if report.candidate.empty:
        return {
            "schema_version": 1,
            "ready": False,
            "scenario_key": "",
            "parameters": {},
            "metrics": {},
            "thresholds": asdict(thresholds),
            "backtest_overfit": overfit,
            "backtest_significance": significance,
            "backtest_holdout": holdout,
            "upstream_integrity": upstream_integrity,
            "recommendation": "keep_in_research",
        }
    row = report.candidate.iloc[0]
    parameters = {col: _jsonable(row[col]) for col in _parameter_columns(report.candidate)}
    metrics = {
        col: _jsonable(row[col])
        for col in report.candidate.columns
        if col not in parameters and col not in {"scenario_key"}
    }
    return {
        "schema_version": 1,
        "ready": report.ready,
        "scenario_key": str(row.get("scenario_key", "")),
        "parameters": parameters,
        "metrics": metrics,
        "thresholds": asdict(thresholds),
        "backtest_overfit": overfit,
        "backtest_significance": significance,
        "backtest_holdout": holdout,
        "upstream_integrity": upstream_integrity,
        "recommendation": str(report.summary.iloc[0]["recommendation"]),
    }


def _read_overfit_audit(
    raw_path: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any], Path | None]:
    if raw_path is None:
        return pd.DataFrame(), {}, None
    path = Path(raw_path)
    summary_path = path / "backtest_overfit_summary.csv" if path.is_dir() else path
    config_path = (
        path / "backtest_overfit_config.json"
        if path.is_dir()
        else path.parent / "backtest_overfit_config.json"
    )
    if not summary_path.is_file():
        raise FileNotFoundError(f"backtest_overfit_summary.csv not found: {summary_path}")
    summary = pd.read_csv(summary_path)
    if summary.empty:
        raise ValueError(f"backtest overfit summary is empty: {summary_path}")
    config: dict[str, Any] = {}
    if config_path.is_file():
        value = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"backtest overfit config must be a JSON object: {config_path}")
        config = value
    audit_manifest = summary_path.parent / "manifest.json"
    summary = summary.copy()
    summary["_artifact_integrity_current"] = verify_experiment_manifest(
        audit_manifest,
        expected_run_type="backtest_overfit_audit",
        required_artifacts=("backtest_overfit_summary.csv",),
        require_input_fingerprints=True,
    ).passed
    summary["_audit_manifest_sha256"] = (
        file_sha256(audit_manifest) if audit_manifest.is_file() else ""
    )
    return summary, config, path


def _read_significance_audit(
    raw_path: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any], Path | None]:
    if raw_path is None:
        return pd.DataFrame(), {}, None
    path = Path(raw_path)
    summary_path = (
        path / "backtest_significance_summary.csv" if path.is_dir() else path
    )
    config_path = (
        path / "backtest_significance_config.json"
        if path.is_dir()
        else path.parent / "backtest_significance_config.json"
    )
    if not summary_path.is_file():
        raise FileNotFoundError(
            f"backtest_significance_summary.csv not found: {summary_path}"
        )
    summary = pd.read_csv(summary_path)
    if summary.empty:
        raise ValueError(f"backtest significance summary is empty: {summary_path}")
    config: dict[str, Any] = {}
    if config_path.is_file():
        value = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(
                f"backtest significance config must be a JSON object: {config_path}"
            )
        config = value
    manifest_path = summary_path.parent / "manifest.json"
    summary = summary.copy()
    summary["_artifact_integrity_current"] = verify_experiment_manifest(
        manifest_path,
        expected_run_type="backtest_significance_audit",
        required_artifacts=("backtest_significance_summary.csv",),
        require_input_fingerprints=True,
    ).passed
    summary["_audit_manifest_sha256"] = (
        file_sha256(manifest_path) if manifest_path.is_file() else ""
    )
    return summary, config, path


def _read_holdout_audit(
    raw_path: str | Path | None,
) -> tuple[pd.DataFrame, dict[str, Any], Path | None]:
    if raw_path is None:
        return pd.DataFrame(), {}, None
    path = Path(raw_path)
    summary_path = path / "backtest_holdout_summary.csv" if path.is_dir() else path
    config_path = (
        path / "backtest_holdout_config.json"
        if path.is_dir()
        else path.parent / "backtest_holdout_config.json"
    )
    if not summary_path.is_file():
        raise FileNotFoundError(
            f"backtest_holdout_summary.csv not found: {summary_path}"
        )
    summary = pd.read_csv(summary_path)
    if summary.empty:
        raise ValueError(f"backtest holdout summary is empty: {summary_path}")
    config: dict[str, Any] = {}
    if config_path.is_file():
        value = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(
                f"backtest holdout config must be a JSON object: {config_path}"
            )
        config = value
    manifest_path = summary_path.parent / "manifest.json"
    summary = summary.copy()
    summary["_artifact_integrity_current"] = verify_experiment_manifest(
        manifest_path,
        expected_run_type="backtest_holdout_audit",
        required_artifacts=("backtest_holdout_summary.csv",),
        require_input_fingerprints=True,
    ).passed
    summary["_audit_manifest_sha256"] = (
        file_sha256(manifest_path) if manifest_path.is_file() else ""
    )
    return summary, config, path


def _overfit_selection_matches(selection: Path, overfit_config: dict[str, Any]) -> bool | None:
    return _audit_selection_matches(selection, overfit_config)


def _audit_selection_matches(
    selection: Path,
    audit_config: dict[str, Any],
) -> bool | None:
    if not audit_config:
        return None
    source = str(audit_config.get("selection_path", "")).strip()
    if not source:
        return False
    if Path(source).resolve() != selection.resolve():
        return False
    expected_manifest_sha = str(
        audit_config.get("selection_manifest_sha256", "")
    ).strip()
    selection_manifest = selection / "manifest.json"
    return bool(
        expected_manifest_sha
        and selection_manifest.is_file()
        and file_sha256(selection_manifest) == expected_manifest_sha
    )


def _overfit_config_record(
    overfit_summary: pd.DataFrame,
    overfit_selection_matches: bool | None,
) -> dict[str, Any]:
    if overfit_summary.empty:
        return {
            "provided": False,
            "passed": False,
            "selection_matches": False,
            "probability_overfit": None,
        }
    summary = overfit_summary.iloc[0]
    return {
        "provided": True,
        "passed": _to_bool(summary.get("passed", summary.get("ready", False))),
        "selection_matches": bool(overfit_selection_matches),
        "audit_manifest_current": _to_bool(summary.get("_artifact_integrity_current", True)),
        "audit_manifest_sha256": str(summary.get("_audit_manifest_sha256", "")),
        "probability_overfit": _jsonable(_float_or_nan(summary.get("probability_overfit"))),
        "partition_count": _int_or_zero(summary.get("partition_count", 0)),
        "scenario_count": _int_or_zero(summary.get("scenario_count", 0)),
        "combination_count": _int_or_zero(summary.get("combination_count", 0)),
        "score_column": str(summary.get("score_column", "")),
    }


def _significance_config_record(
    significance_summary: pd.DataFrame,
    significance_selection_matches: bool | None,
) -> dict[str, Any]:
    if significance_summary.empty:
        return {
            "provided": False,
            "passed": False,
            "selection_matches": False,
            "adjusted_sign_pvalue": None,
            "bootstrap_probability_positive": None,
        }
    summary = significance_summary.iloc[0]
    return {
        "provided": True,
        "passed": _to_bool(summary.get("passed", False)),
        "selection_matches": bool(significance_selection_matches),
        "audit_manifest_current": _to_bool(
            summary.get("_artifact_integrity_current", True)
        ),
        "audit_manifest_sha256": str(summary.get("_audit_manifest_sha256", "")),
        "candidate_scenario": str(summary.get("candidate_scenario", "")),
        "observation_count": _int_or_zero(summary.get("observation_count", 0)),
        "adjusted_sign_pvalue": _jsonable(
            _float_or_nan(summary.get("adjusted_sign_pvalue"))
        ),
        "bootstrap_mean_lower": _jsonable(
            _float_or_nan(summary.get("bootstrap_mean_lower"))
        ),
        "bootstrap_probability_positive": _jsonable(
            _float_or_nan(summary.get("bootstrap_probability_positive"))
        ),
    }


def _holdout_config_record(
    holdout_summary: pd.DataFrame,
    holdout_selection_matches: bool | None,
    *,
    scenario_key: str,
) -> dict[str, Any]:
    if holdout_summary.empty:
        return {
            "provided": False,
            "passed": False,
            "selection_matches": False,
            "candidate_matches": False,
            "expected_sweeps": 0,
        }
    summary = holdout_summary.iloc[0]
    candidate = str(summary.get("candidate_scenario", ""))
    return {
        "provided": True,
        "passed": _to_bool(summary.get("passed", False)),
        "selection_matches": bool(holdout_selection_matches),
        "candidate_matches": bool(scenario_key and candidate == scenario_key),
        "audit_manifest_current": _to_bool(
            summary.get("_artifact_integrity_current", True)
        ),
        "audit_manifest_sha256": str(summary.get("_audit_manifest_sha256", "")),
        "candidate_scenario": candidate,
        "expected_sweeps": _int_or_zero(summary.get("expected_sweeps", 0)),
        "candidate_coverage_rate": _jsonable(
            _float_or_nan(summary.get("candidate_coverage_rate"))
        ),
        "proof_pass_rate": _jsonable(
            _float_or_nan(summary.get("proof_pass_rate"))
        ),
        "mean_score": _jsonable(_float_or_nan(summary.get("mean_score"))),
        "median_score": _jsonable(_float_or_nan(summary.get("median_score"))),
        "worst_score": _jsonable(_float_or_nan(summary.get("worst_score"))),
        "mean_net_pnl": _jsonable(_float_or_nan(summary.get("mean_net_pnl"))),
        "worst_net_pnl": _jsonable(_float_or_nan(summary.get("worst_net_pnl"))),
    }


def _parameter_columns(frame: pd.DataFrame) -> list[str]:
    return [col for col in frame.columns if col not in SCORE_METRIC_COLUMNS]


def _candidate_runs(runs: pd.DataFrame, candidate: pd.Series, parameter_cols: list[str]) -> pd.DataFrame:
    if runs.empty:
        return runs.copy()
    mask = pd.Series(True, index=runs.index)
    for col in parameter_cols:
        if col not in runs.columns or col not in candidate:
            continue
        mask &= _same_value_series(runs[col], candidate[col])
    matched = runs.loc[mask].copy()
    if matched.empty and "scenario_key" in runs.columns and "scenario_key" in candidate:
        matched = runs.loc[runs["scenario_key"].astype(str) == str(candidate["scenario_key"])].copy()
    return matched


def _same_value_series(series: pd.Series, value: object) -> pd.Series:
    if pd.isna(value):
        return series.isna()
    numeric = pd.to_numeric(series, errors="coerce")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = np.nan
    if not np.isnan(numeric_value) and numeric.notna().any():
        return np.isclose(numeric, numeric_value, equal_nan=False)
    return series.astype(str) == str(value)


def _numeric_check(row: pd.Series, column: str, operator: str, threshold: float | int) -> dict[str, Any]:
    value = float(row[column]) if column in row and not pd.isna(row[column]) else np.nan
    return _threshold_check(column, value, operator, threshold)


def _run_metric_check(
    runs: pd.DataFrame,
    column: str,
    check_name: str,
    operator: str,
    threshold: float | int,
    *,
    reducer: str,
) -> dict[str, Any]:
    if runs.empty or column not in runs.columns:
        return _check(check_name, np.nan, operator, threshold, False, f"{column} is unavailable")
    values = pd.to_numeric(runs[column], errors="coerce")
    value = float(values.max(skipna=True)) if reducer == "max" else float(values.min(skipna=True))
    return _threshold_check(check_name, value, operator, threshold)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float
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
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_thresholds(thresholds: PromotionThresholds) -> None:
    if not 0 <= thresholds.min_pass_rate <= 1:
        raise ValueError("min_pass_rate must be between 0 and 1")
    if thresholds.min_sweeps <= 0:
        raise ValueError("min_sweeps must be positive")
    if thresholds.min_median_fills < 0:
        raise ValueError("min_median_fills must be non-negative")
    if thresholds.max_runs_with_losing_regimes is not None and thresholds.max_runs_with_losing_regimes < 0:
        raise ValueError("max_runs_with_losing_regimes must be non-negative")
    if thresholds.max_otr is not None and thresholds.max_otr <= 0:
        raise ValueError("max_otr must be positive")
    if thresholds.min_maker_share is not None and not 0 <= thresholds.min_maker_share <= 1:
        raise ValueError("min_maker_share must be between 0 and 1")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _float_or_nan(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _int_or_zero(value: object) -> int:
    number = _float_or_nan(value)
    return int(number) if np.isfinite(number) else 0


def _jsonable(value: object) -> object:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if pd.isna(value):
        return None
    return value
