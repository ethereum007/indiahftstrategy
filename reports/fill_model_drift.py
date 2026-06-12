from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class FillModelDriftThresholds:
    require_baseline_ready: bool = True
    require_latest_ready: bool = True
    require_same_instruments: bool = False
    max_queue_conservatism_increase_pct: float | None = 0.25
    max_order_latency_increase_us: float | None = 100.0
    max_slippage_tick_increase: float | None = 1.0
    max_min_edge_tick_increase: float | None = 1.0


@dataclass(frozen=True)
class FillModelDriftReport:
    drift: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_fill_model_drift(
    baseline_config: dict[str, Any],
    latest_config: dict[str, Any],
    *,
    thresholds: FillModelDriftThresholds | None = None,
) -> FillModelDriftReport:
    thresholds = thresholds or FillModelDriftThresholds()
    _validate_thresholds(thresholds)
    drift = _drift_frame(baseline_config, latest_config)
    checks = _checks(baseline_config, latest_config, drift, thresholds)
    summary = _summary(drift, checks)
    return FillModelDriftReport(drift=drift, checks=checks, summary=summary)


def write_fill_model_drift_report(
    *,
    baseline_path: str | Path,
    latest_path: str | Path,
    output_dir: str | Path,
    thresholds: FillModelDriftThresholds | None = None,
) -> FillModelDriftReport:
    baseline_file = _config_path(baseline_path)
    latest_file = _config_path(latest_path)
    thresholds = thresholds or FillModelDriftThresholds()
    report = evaluate_fill_model_drift(
        json.loads(baseline_file.read_text(encoding="utf-8")),
        json.loads(latest_file.read_text(encoding="utf-8")),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.drift.to_csv(out / "fill_model_drift.csv", index=False)
    report.checks.to_csv(out / "fill_model_drift_checks.csv", index=False)
    report.summary.to_csv(out / "fill_model_drift_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="fill_model_drift",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"baseline_fill_model": baseline_file, "latest_fill_model": latest_file},
    )
    return FillModelDriftReport(report.drift, report.checks, report.summary, out)


def _drift_frame(baseline_config: dict[str, Any], latest_config: dict[str, Any]) -> pd.DataFrame:
    baseline_models = _models_by_scope(baseline_config)
    latest_models = _models_by_scope(latest_config)
    scopes = sorted(set(baseline_models) | set(latest_models), key=lambda item: (item != "GLOBAL", item))
    rows = []
    for scope in scopes:
        baseline = baseline_models.get(scope, {})
        latest = latest_models.get(scope, {})
        rows.append(
            {
                "scope": "global" if scope == "GLOBAL" else "instrument",
                "instrument_id": "" if scope == "GLOBAL" else scope,
                "baseline_present": bool(baseline),
                "latest_present": bool(latest),
                **_metric_drift("queue_conservatism", baseline, latest),
                **_metric_drift("order_latency_us", baseline, latest),
                **_metric_drift("slippage_ticks", baseline, latest),
                **_metric_drift("min_edge_ticks", baseline, latest),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    baseline_config: dict[str, Any],
    latest_config: dict[str, Any],
    drift: pd.DataFrame,
    thresholds: FillModelDriftThresholds,
) -> pd.DataFrame:
    checks = [
        _check(
            "baseline_ready",
            _to_bool(baseline_config.get("ready", False)),
            "is",
            True,
            _to_bool(baseline_config.get("ready", False)) or not thresholds.require_baseline_ready,
            "baseline fill-model config is not ready",
        ),
        _check(
            "latest_ready",
            _to_bool(latest_config.get("ready", False)),
            "is",
            True,
            _to_bool(latest_config.get("ready", False)) or not thresholds.require_latest_ready,
            "latest fill-model config is not ready",
        ),
    ]
    missing_latest = int((~drift["latest_present"].astype(bool)).sum()) if not drift.empty else 0
    missing_baseline = int((~drift["baseline_present"].astype(bool)).sum()) if not drift.empty else 0
    checks.append(
        _check(
            "instrument_set_unchanged",
            missing_latest + missing_baseline,
            "==",
            0,
            (missing_latest + missing_baseline == 0) or not thresholds.require_same_instruments,
            "baseline and latest fill-model instrument sets differ",
        )
    )
    checks.extend(_metric_checks(drift, "queue_conservatism_delta_pct", thresholds.max_queue_conservatism_increase_pct))
    checks.extend(_metric_checks(drift, "order_latency_us_delta", thresholds.max_order_latency_increase_us))
    checks.extend(_metric_checks(drift, "slippage_ticks_delta", thresholds.max_slippage_tick_increase))
    checks.extend(_metric_checks(drift, "min_edge_ticks_delta", thresholds.max_min_edge_tick_increase))
    return pd.DataFrame(checks)


def _metric_checks(drift: pd.DataFrame, column: str, threshold: float | None) -> list[dict[str, object]]:
    if threshold is None:
        return []
    usable = pd.to_numeric(drift[column], errors="coerce") if column in drift.columns else pd.Series(dtype=float)
    max_increase = float(usable.max(skipna=True)) if usable.notna().any() else 0.0
    return [
        _check(
            column,
            max_increase,
            "<=",
            threshold,
            max_increase <= float(threshold) + 1e-12,
            f"{column} {max_increase:.6g} exceeded {float(threshold):.6g}",
        )
    ]


def _summary(drift: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    global_row = drift.loc[drift["scope"] == "global"].iloc[0] if not drift.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "rows": int(len(drift)),
                "new_instruments": int((~drift["baseline_present"].astype(bool)).sum()) if not drift.empty else 0,
                "missing_latest_instruments": int((~drift["latest_present"].astype(bool)).sum()) if not drift.empty else 0,
                "global_queue_conservatism_delta_pct": _number(global_row, "queue_conservatism_delta_pct"),
                "global_order_latency_us_delta": _number(global_row, "order_latency_us_delta"),
                "global_slippage_ticks_delta": _number(global_row, "slippage_ticks_delta"),
                "global_min_edge_ticks_delta": _number(global_row, "min_edge_ticks_delta"),
                "failed_checks": failed,
                "recommendation": "reuse_existing_proof_assumptions" if passed else "rerun_calibrated_proof_before_promotion",
            }
        ]
    )


def _models_by_scope(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    models = {"GLOBAL": config.get("global", {}) or {}}
    for row in config.get("by_instrument", []) or []:
        instrument_id = str(row.get("instrument_id", "")).strip()
        if instrument_id:
            models[instrument_id] = row
    return models


def _metric_drift(metric: str, baseline: dict[str, Any], latest: dict[str, Any]) -> dict[str, float]:
    baseline_value = _mapping_number(baseline, metric)
    latest_value = _mapping_number(latest, metric)
    delta = latest_value - baseline_value if not pd.isna(latest_value) and not pd.isna(baseline_value) else np.nan
    if pd.isna(delta) or pd.isna(baseline_value) or abs(baseline_value) <= 1e-12:
        delta_pct = np.nan
    else:
        delta_pct = delta / abs(baseline_value)
    return {
        f"baseline_{metric}": baseline_value,
        f"latest_{metric}": latest_value,
        f"{metric}_delta": delta,
        f"{metric}_delta_pct": delta_pct,
    }


def _config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "fill_model_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"fill-model config not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: FillModelDriftThresholds) -> None:
    for name in (
        "max_queue_conservatism_increase_pct",
        "max_order_latency_increase_us",
        "max_slippage_tick_increase",
        "max_min_edge_tick_increase",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")


def _mapping_number(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key, np.nan)
    if value is None or pd.isna(value):
        return np.nan
    return float(value)


def _number(row: pd.Series, column: str) -> float:
    if row.empty or column not in row.index:
        return np.nan
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else np.nan


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
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
