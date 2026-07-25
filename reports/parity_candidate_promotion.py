from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.parity_order_plan import PARITY_BOX_STRATEGY, BOX_DIRECTIONS, PARITY_DIRECTIONS


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
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    thresholds: ParityCandidatePromotionThresholds | None = None,
) -> ParityCandidatePromotionReport:
    thresholds = thresholds or ParityCandidatePromotionThresholds()
    _validate_thresholds(thresholds)
    _require(edge_summary, ["passed", "total_opportunities", "best_net_edge"], "edge_summary")
    _require(sweep_summary, ["passed_scenarios", "pass_rate", "best_run"], "sweep_summary")
    _require(sweep_runs, ["run"], "sweep_runs")

    opportunities = _combined_opportunities(parity_opportunities, box_opportunities)
    candidate_row = _select_candidate(opportunities)
    sweep_row = _select_sweep_run(sweep_summary.iloc[0], sweep_runs)
    checks = _checks(edge_summary.iloc[0], sweep_summary.iloc[0], candidate_row, sweep_row, thresholds)
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
    scan = Path(scan_dir)
    edge = Path(edge_audit_dir)
    sweep = Path(sweep_dir)
    parity_path = scan / "parity_opportunities.csv"
    box_path = scan / "box_opportunities.csv"
    edge_summary_path = edge / "parity_edge_summary.csv"
    sweep_summary_path = sweep / "sweep_summary.csv"
    sweep_runs_path = sweep / "sweep_runs.csv"
    for path in [parity_path, box_path, edge_summary_path, sweep_summary_path, sweep_runs_path]:
        if not path.exists():
            raise FileNotFoundError(f"required parity promotion input missing: {path}")

    thresholds = thresholds or ParityCandidatePromotionThresholds()
    report = evaluate_parity_candidate_promotion(
        pd.read_csv(parity_path),
        pd.read_csv(box_path),
        pd.read_csv(edge_summary_path),
        pd.read_csv(sweep_summary_path),
        pd.read_csv(sweep_runs_path),
        market=market,
        thresholds=thresholds,
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
    write_experiment_manifest(
        out,
        run_type="promotion_report",
        parameters={
            "strategy": PARITY_BOX_STRATEGY,
            "market": market,
            "thresholds": asdict(thresholds),
        },
        inputs={
            "scan": scan,
            "edge_audit": edge,
            "sweep": sweep,
            "parity_opportunities": parity_path,
            "box_opportunities": box_path,
            "edge_summary": edge_summary_path,
            "sweep_summary": sweep_summary_path,
            "sweep_runs": sweep_runs_path,
        },
        extra={"promotion_source": "parity_scan_edge_sweep"},
    )
    return ParityCandidatePromotionReport(
        report.candidate,
        report.checks,
        report.summary,
        report.candidate_config,
        out,
    )


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


def _select_sweep_run(sweep_summary: pd.Series, sweep_runs: pd.DataFrame) -> pd.Series:
    work = sweep_runs.copy()
    if work.empty:
        return pd.Series(dtype=object)
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


def _checks(
    edge: pd.Series,
    sweep: pd.Series,
    candidate: pd.Series | None,
    sweep_run: pd.Series,
    thresholds: ParityCandidatePromotionThresholds,
) -> pd.DataFrame:
    edge_passed = _to_bool(edge.get("passed", False))
    passed_scenarios = _number(sweep.get("passed_scenarios"), 0)
    candidate_net_edge = _number(candidate.get("net_edge") if candidate is not None else None, np.nan)
    candidate_persistence = _number(candidate.get("persistence_ticks") if candidate is not None else None, np.nan)
    return pd.DataFrame(
        [
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
    )


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
        "sweep_net_pnl": _jsonable(sweep_run.get("net_pnl")),
        "sweep_fills": _jsonable(sweep_run.get("fills")),
        "sweep_robust_score": _jsonable(sweep_run.get("robust_score")),
    }
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
            "feed_latency_us",
            "order_latency_us",
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
