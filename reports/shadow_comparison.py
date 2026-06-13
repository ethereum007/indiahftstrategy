from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ShadowComparisonThresholds:
    min_sessions: int = 1
    min_acceptance_rate: float = 1.0
    require_same_scenario: bool = True
    require_same_runtime_identity: bool = True
    min_median_order_fill_rate: float = 0.0
    min_worst_order_fill_rate: float | None = None
    max_total_failed_component_checks: int = 0
    max_total_unmatched_fills: int = 0
    max_total_mismatched_orders: int = 0
    max_total_overfilled_orders: int = 0
    max_runtime_halted_sessions: int = 0
    max_worst_adverse_slippage: float | None = None


@dataclass(frozen=True)
class ShadowComparisonReport:
    session_runs: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def accepted(self) -> bool:
        return bool(self.summary.iloc[0]["accepted"]) if not self.summary.empty else False


def compare_shadow_sessions(
    sessions: pd.DataFrame,
    *,
    thresholds: ShadowComparisonThresholds | None = None,
) -> ShadowComparisonReport:
    thresholds = thresholds or ShadowComparisonThresholds()
    _validate_thresholds(thresholds)
    _require(sessions, ["session", "accepted", "scenario_key", "order_fill_rate"], "sessions")
    runs = sessions.copy().reset_index(drop=True)
    runs["accepted"] = runs["accepted"].map(_to_bool)
    runs["order_fill_rate"] = pd.to_numeric(runs["order_fill_rate"], errors="coerce")
    for column in (
        "total_failed_component_checks",
        "unmatched_fills",
        "mismatched_orders",
        "overfilled_orders",
        "runtime_failed_checks",
        "max_adverse_slippage",
    ):
        if column not in runs.columns:
            runs[column] = 0.0 if column != "max_adverse_slippage" else np.nan
        runs[column] = pd.to_numeric(runs[column], errors="coerce")
    for column in ("runtime_session_provided", "runtime_guard_halted"):
        if column not in runs.columns:
            runs[column] = False
        runs[column] = runs[column].map(_to_bool)
    for column in (
        "runtime_proof_refresh_required",
        "runtime_proof_refresh_provided",
        "runtime_proof_refresh_ready",
        "runtime_proof_refresh_mixed_identity",
    ):
        if column not in runs.columns:
            runs[column] = False
        runs[column] = runs[column].map(_to_bool)
    for column in (
        "runtime_target_mode",
        "runtime_strategy",
        "runtime_market",
        "runtime_proof_refresh_strategy",
        "runtime_proof_refresh_market",
        "runtime_proof_source",
    ):
        if column not in runs.columns:
            runs[column] = ""
        runs[column] = runs[column].fillna("").astype(str)
    summary = _summary(runs)
    checks = _checks(summary.iloc[0], thresholds)
    summary["accepted"] = bool(checks["passed"].all()) if not checks.empty else False
    summary["recommendation"] = np.where(
        summary["accepted"],
        "eligible_for_controlled_paper_scaleup",
        "continue_shadow_research",
    )
    return ShadowComparisonReport(session_runs=runs, checks=checks, summary=summary)


def write_shadow_session_comparison(
    session_dirs: list[str | Path],
    *,
    output_dir: str | Path,
    labels: list[str] | None = None,
    thresholds: ShadowComparisonThresholds | None = None,
) -> ShadowComparisonReport:
    if not session_dirs:
        raise ValueError("at least one shadow session directory is required")
    if labels is not None and len(labels) != len(session_dirs):
        raise ValueError("labels must match session directories")
    thresholds = thresholds or ShadowComparisonThresholds()
    sessions = _read_sessions(session_dirs, labels=labels)
    report = compare_shadow_sessions(sessions, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.session_runs.to_csv(out / "shadow_session_runs.csv", index=False)
    report.checks.to_csv(out / "shadow_session_comparison_checks.csv", index=False)
    report.summary.to_csv(out / "shadow_session_comparison_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="shadow_session_comparison",
        parameters={"labels": labels, "thresholds": asdict(thresholds)},
        inputs={"sessions": session_dirs},
    )
    return ShadowComparisonReport(report.session_runs, report.checks, report.summary, out)


def _read_sessions(session_dirs: list[str | Path], *, labels: list[str] | None) -> pd.DataFrame:
    rows = []
    for idx, raw_path in enumerate(session_dirs):
        path = Path(raw_path)
        metrics = _read_required(path / "shadow_session_metrics.csv").iloc[0]
        summary = _read_required(path / "shadow_session_summary.csv").iloc[0]
        label = labels[idx] if labels is not None else path.name
        row = {
            "session": label,
            "session_path": str(path),
            "accepted": _to_bool(summary.get("accepted", False)),
            "scenario_key": str(summary.get("scenario_key", metrics.get("scenario_key", ""))),
            "mode": str(summary.get("mode", metrics.get("mode", ""))),
            "adapter": str(summary.get("adapter", metrics.get("adapter", ""))),
            "order_fill_rate": _number(summary, "order_fill_rate", fallback=_number(metrics, "order_fill_rate")),
            "failed_checks": _number(summary, "failed_checks", fallback=0.0),
            "total_failed_component_checks": _number(metrics, "total_failed_component_checks", fallback=0.0),
            "orders": _number(metrics, "orders", fallback=0.0),
            "filled_orders": _number(metrics, "filled_orders", fallback=0.0),
            "unfilled_orders": _number(metrics, "unfilled_orders", fallback=0.0),
            "mismatched_orders": _number(metrics, "mismatched_orders", fallback=0.0),
            "overfilled_orders": _number(metrics, "overfilled_orders", fallback=0.0),
            "unmatched_fills": _number(metrics, "unmatched_fills", fallback=0.0),
            "runtime_session_provided": _to_bool(metrics.get("runtime_session_provided", False)),
            "runtime_guard_action": str(metrics.get("runtime_guard_action", "")),
            "runtime_guard_halted": _to_bool(metrics.get("runtime_guard_halted", False)),
            "runtime_target_mode": str(summary.get("runtime_target_mode", metrics.get("runtime_target_mode", ""))),
            "runtime_strategy": _strategy_key(
                summary.get("runtime_strategy", summary.get("strategy", metrics.get("runtime_strategy", metrics.get("strategy", ""))))
            ),
            "runtime_market": _identity_key(
                summary.get("runtime_market", summary.get("market", metrics.get("runtime_market", metrics.get("market", ""))))
            ),
            "runtime_proof_refresh_required": _to_bool(
                summary.get(
                    "runtime_proof_refresh_required",
                    metrics.get("runtime_proof_refresh_required", False),
                )
            ),
            "runtime_proof_refresh_provided": _to_bool(
                summary.get(
                    "runtime_proof_refresh_provided",
                    metrics.get("runtime_proof_refresh_provided", False),
                )
            ),
            "runtime_proof_refresh_ready": _to_bool(
                summary.get("runtime_proof_refresh_ready", metrics.get("runtime_proof_refresh_ready", False))
            ),
            "runtime_proof_refresh_strategy": _strategy_key(
                summary.get(
                    "runtime_proof_refresh_strategy",
                    metrics.get("runtime_proof_refresh_strategy", ""),
                )
            ),
            "runtime_proof_refresh_market": _identity_key(
                summary.get(
                    "runtime_proof_refresh_market",
                    metrics.get("runtime_proof_refresh_market", ""),
                )
            ),
            "runtime_proof_refresh_mixed_identity": _to_bool(
                summary.get(
                    "runtime_proof_refresh_mixed_identity",
                    metrics.get("runtime_proof_refresh_mixed_identity", False),
                )
            ),
            "runtime_proof_source": str(
                summary.get("runtime_proof_source", metrics.get("runtime_proof_source", ""))
            ),
            "runtime_failed_checks": _number(metrics, "runtime_failed_checks", fallback=0.0),
            "max_adverse_slippage": _number(metrics, "max_adverse_slippage"),
            "avg_latency_ns": _number(metrics, "avg_latency_ns"),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _summary(runs: pd.DataFrame) -> pd.DataFrame:
    session_count = int(len(runs))
    accepted_sessions = int(runs["accepted"].sum()) if session_count else 0
    scenario_count = int(runs["scenario_key"].nunique()) if session_count else 0
    runtime_runs = (
        runs.loc[runs["runtime_session_provided"].astype(bool) & runs["accepted"].astype(bool)]
        if session_count
        else pd.DataFrame()
    )
    proof_refresh_runs = (
        runtime_runs.loc[
            runtime_runs["runtime_proof_refresh_required"].astype(bool)
            | runtime_runs["runtime_proof_refresh_provided"].astype(bool)
        ]
        if not runtime_runs.empty
        else pd.DataFrame()
    )
    runtime_strategies = _identity_values(runtime_runs, "runtime_strategy", normalizer=_strategy_key)
    runtime_markets = _identity_values(runtime_runs, "runtime_market", normalizer=_identity_key)
    proof_refresh_strategies = _identity_values(
        proof_refresh_runs,
        "runtime_proof_refresh_strategy",
        normalizer=_strategy_key,
    )
    proof_refresh_markets = _identity_values(
        proof_refresh_runs,
        "runtime_proof_refresh_market",
        normalizer=_identity_key,
    )
    fill_rates = pd.to_numeric(runs["order_fill_rate"], errors="coerce")
    slippage = pd.to_numeric(runs["max_adverse_slippage"], errors="coerce")
    return pd.DataFrame(
        [
            {
                "session_count": session_count,
                "accepted_sessions": accepted_sessions,
                "failed_sessions": int(session_count - accepted_sessions),
                "acceptance_rate": accepted_sessions / session_count if session_count else 0.0,
                "scenario_count": scenario_count,
                "scenario_key": _single_or_mixed(runs["scenario_key"]) if session_count else "",
                "strategy": next(iter(runtime_strategies)) if len(runtime_strategies) == 1 else "",
                "strategy_count": int(len(runtime_strategies)),
                "missing_strategy_sessions": _missing_identity_count(runtime_runs, "runtime_strategy"),
                "market": next(iter(runtime_markets)) if len(runtime_markets) == 1 else "",
                "market_count": int(len(runtime_markets)),
                "missing_market_sessions": _missing_identity_count(runtime_runs, "runtime_market"),
                "median_order_fill_rate": float(fill_rates.median(skipna=True)) if fill_rates.notna().any() else np.nan,
                "worst_order_fill_rate": float(fill_rates.min(skipna=True)) if fill_rates.notna().any() else np.nan,
                "total_orders": float(pd.to_numeric(runs["orders"], errors="coerce").sum(skipna=True)),
                "total_failed_component_checks": int(
                    pd.to_numeric(runs["total_failed_component_checks"], errors="coerce").sum(skipna=True)
                ),
                "total_unmatched_fills": int(pd.to_numeric(runs["unmatched_fills"], errors="coerce").sum(skipna=True)),
                "total_mismatched_orders": int(
                    pd.to_numeric(runs["mismatched_orders"], errors="coerce").sum(skipna=True)
                ),
                "total_overfilled_orders": int(
                    pd.to_numeric(runs["overfilled_orders"], errors="coerce").sum(skipna=True)
                ),
                "runtime_sessions_provided": int(runs["runtime_session_provided"].sum()),
                "accepted_runtime_sessions": int(len(runtime_runs)),
                "runtime_halted_sessions": int(runs["runtime_guard_halted"].sum()),
                "runtime_proof_refresh_sessions": int(len(proof_refresh_runs)),
                "runtime_proof_refresh_required_sessions": int(
                    proof_refresh_runs["runtime_proof_refresh_required"].sum()
                )
                if not proof_refresh_runs.empty
                else 0,
                "runtime_proof_refresh_provided_sessions": int(
                    proof_refresh_runs["runtime_proof_refresh_provided"].sum()
                )
                if not proof_refresh_runs.empty
                else 0,
                "runtime_proof_refresh_ready_sessions": int(
                    proof_refresh_runs["runtime_proof_refresh_ready"].sum()
                )
                if not proof_refresh_runs.empty
                else 0,
                "runtime_proof_refresh_mixed_identity_sessions": int(
                    proof_refresh_runs["runtime_proof_refresh_mixed_identity"].sum()
                )
                if not proof_refresh_runs.empty
                else 0,
                "proof_refresh_strategy": next(iter(proof_refresh_strategies))
                if len(proof_refresh_strategies) == 1
                else "",
                "proof_refresh_strategy_count": int(len(proof_refresh_strategies)),
                "missing_proof_refresh_strategy_sessions": _missing_identity_count(
                    proof_refresh_runs,
                    "runtime_proof_refresh_strategy",
                ),
                "proof_refresh_market": next(iter(proof_refresh_markets))
                if len(proof_refresh_markets) == 1
                else "",
                "proof_refresh_market_count": int(len(proof_refresh_markets)),
                "missing_proof_refresh_market_sessions": _missing_identity_count(
                    proof_refresh_runs,
                    "runtime_proof_refresh_market",
                ),
                "total_runtime_failed_checks": int(
                    pd.to_numeric(runs["runtime_failed_checks"], errors="coerce").sum(skipna=True)
                ),
                "worst_adverse_slippage": float(slippage.max(skipna=True)) if slippage.notna().any() else np.nan,
                "median_latency_ns": float(pd.to_numeric(runs["avg_latency_ns"], errors="coerce").median(skipna=True))
                if pd.to_numeric(runs["avg_latency_ns"], errors="coerce").notna().any()
                else np.nan,
            }
        ]
    )


def _checks(row: pd.Series, thresholds: ShadowComparisonThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check("session_count", row["session_count"], ">=", thresholds.min_sessions),
        _threshold_check("acceptance_rate", row["acceptance_rate"], ">=", thresholds.min_acceptance_rate),
        _check(
            "same_scenario",
            row["scenario_count"],
            "<=",
            1,
            (not thresholds.require_same_scenario) or int(row["scenario_count"]) <= 1,
            "shadow sessions used multiple scenario keys",
        ),
        _check(
            "same_runtime_strategy",
            row["strategy_count"],
            "<=",
            1,
            (not thresholds.require_same_runtime_identity)
            or int(row["accepted_runtime_sessions"]) == 0
            or (int(row["strategy_count"]) == 1 and int(row["missing_strategy_sessions"]) == 0),
            "runtime-session strategy identity is missing or mixed across shadow sessions",
        ),
        _check(
            "same_runtime_market",
            row["market_count"],
            "<=",
            1,
            (not thresholds.require_same_runtime_identity)
            or int(row["accepted_runtime_sessions"]) == 0
            or (int(row["market_count"]) == 1 and int(row["missing_market_sessions"]) == 0),
            "runtime-session market identity is missing or mixed across shadow sessions",
        ),
        _threshold_check(
            "median_order_fill_rate",
            row["median_order_fill_rate"],
            ">=",
            thresholds.min_median_order_fill_rate,
        ),
        _threshold_check(
            "total_failed_component_checks",
            row["total_failed_component_checks"],
            "<=",
            thresholds.max_total_failed_component_checks,
        ),
        _threshold_check("total_unmatched_fills", row["total_unmatched_fills"], "<=", thresholds.max_total_unmatched_fills),
        _threshold_check(
            "total_mismatched_orders",
            row["total_mismatched_orders"],
            "<=",
            thresholds.max_total_mismatched_orders,
        ),
        _threshold_check(
            "total_overfilled_orders",
            row["total_overfilled_orders"],
            "<=",
            thresholds.max_total_overfilled_orders,
        ),
        _threshold_check(
            "runtime_halted_sessions",
            row["runtime_halted_sessions"],
            "<=",
            thresholds.max_runtime_halted_sessions,
        ),
    ]
    proof_refresh_sessions = int(row["runtime_proof_refresh_sessions"])
    if proof_refresh_sessions > 0:
        checks.extend(
            [
                _check(
                    "runtime_proof_refresh_provided",
                    row["runtime_proof_refresh_provided_sessions"],
                    ">=",
                    row["runtime_proof_refresh_required_sessions"],
                    int(row["runtime_proof_refresh_provided_sessions"])
                    >= int(row["runtime_proof_refresh_required_sessions"]),
                    "accepted runtime sessions require proof refresh but some did not provide it",
                ),
                _check(
                    "runtime_proof_refresh_ready",
                    row["runtime_proof_refresh_ready_sessions"],
                    "==",
                    proof_refresh_sessions,
                    int(row["runtime_proof_refresh_ready_sessions"]) == proof_refresh_sessions,
                    "accepted runtime proof-refresh evidence is not ready for every session",
                ),
                _check(
                    "runtime_proof_refresh_identity_consistent",
                    row["runtime_proof_refresh_mixed_identity_sessions"],
                    "==",
                    0,
                    int(row["runtime_proof_refresh_mixed_identity_sessions"]) == 0,
                    "accepted runtime proof-refresh evidence reported mixed identity",
                ),
                _check(
                    "same_runtime_proof_refresh_strategy",
                    row["proof_refresh_strategy_count"],
                    "==",
                    1,
                    int(row["proof_refresh_strategy_count"]) == 1
                    and int(row["missing_proof_refresh_strategy_sessions"]) == 0,
                    "runtime proof-refresh strategy identity is missing or mixed across shadow sessions",
                ),
                _check(
                    "same_runtime_proof_refresh_market",
                    row["proof_refresh_market_count"],
                    "==",
                    1,
                    int(row["proof_refresh_market_count"]) == 1
                    and int(row["missing_proof_refresh_market_sessions"]) == 0,
                    "runtime proof-refresh market identity is missing or mixed across shadow sessions",
                ),
            ]
        )
    if thresholds.min_worst_order_fill_rate is not None:
        checks.append(
            _threshold_check("worst_order_fill_rate", row["worst_order_fill_rate"], ">=", thresholds.min_worst_order_fill_rate)
        )
    if thresholds.max_worst_adverse_slippage is not None:
        checks.append(
            _threshold_check(
                "worst_adverse_slippage",
                row["worst_adverse_slippage"],
                "<=",
                thresholds.max_worst_adverse_slippage,
            )
        )
    return pd.DataFrame(checks)


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


def _validate_thresholds(thresholds: ShadowComparisonThresholds) -> None:
    if thresholds.min_sessions <= 0:
        raise ValueError("min_sessions must be positive")
    if not 0 <= thresholds.min_acceptance_rate <= 1:
        raise ValueError("min_acceptance_rate must be between 0 and 1")
    if not 0 <= thresholds.min_median_order_fill_rate <= 1:
        raise ValueError("min_median_order_fill_rate must be between 0 and 1")
    if thresholds.min_worst_order_fill_rate is not None and not 0 <= thresholds.min_worst_order_fill_rate <= 1:
        raise ValueError("min_worst_order_fill_rate must be between 0 and 1")
    for name in (
        "max_total_failed_component_checks",
        "max_total_unmatched_fills",
        "max_total_mismatched_orders",
        "max_total_overfilled_orders",
        "max_runtime_halted_sessions",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    if thresholds.max_worst_adverse_slippage is not None and thresholds.max_worst_adverse_slippage < 0:
        raise ValueError("max_worst_adverse_slippage must be non-negative")


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required shadow comparison input missing: {path}")
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"required shadow comparison input is empty: {path}")
    return frame


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _single_or_mixed(values: pd.Series) -> str:
    unique = values.dropna().astype(str).drop_duplicates().tolist()
    if len(unique) == 1:
        return unique[0]
    return "MIXED"


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


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else fallback


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
