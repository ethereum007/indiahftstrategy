from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest


SUPPORTED_STRATEGIES = {"leadlag", "parity", "surface_mm", "surface_quotes"}


@dataclass(frozen=True)
class ReplayCalibrationReport:
    params: dict[str, Any]
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def load_fill_model_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if config_path.is_dir():
        config_path = config_path / "fill_model_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"fill-model config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def apply_fill_model_to_replay_params(
    strategy: str,
    base_params: dict[str, Any],
    fill_model_config: dict[str, Any],
    *,
    require_ready: bool = True,
) -> ReplayCalibrationReport:
    strategy = _strategy_key(strategy)
    global_model = fill_model_config.get("global", {}) or {}
    calibrated = dict(base_params)
    checks = _base_checks(fill_model_config, require_ready)
    applied_fields: list[str] = []

    if strategy == "leadlag":
        _apply_max(calibrated, "order_latency_us", _number(global_model, "order_latency_us"), applied_fields)
        _apply_max(calibrated, "trigger_ticks", _number(global_model, "min_edge_ticks"), applied_fields)
    elif strategy == "parity":
        _apply_max(calibrated, "order_latency_us", _number(global_model, "order_latency_us"), applied_fields)
        _apply_depth_fraction(calibrated, "depth_fraction", _number(global_model, "queue_conservatism"), applied_fields)
    elif strategy == "surface_mm":
        _apply_max(calibrated, "order_latency_us", _number(global_model, "order_latency_us"), applied_fields)
        _apply_depth_fraction(
            calibrated,
            "fill_depth_fraction",
            _number(global_model, "queue_conservatism"),
            applied_fields,
        )
    elif strategy == "surface_quotes":
        _apply_max(calibrated, "edge_ticks", _number(global_model, "min_edge_ticks"), applied_fields)
    else:
        raise ValueError(f"unsupported calibrated replay strategy {strategy!r}")

    checks.append(
        _check(
            "calibration_fields_applied",
            len(applied_fields),
            ">",
            0,
            bool(applied_fields),
            "fill-model config did not map to any replay parameters",
        )
    )
    checks_frame = pd.DataFrame(checks)
    summary = _summary(strategy, calibrated, applied_fields, checks_frame)
    return ReplayCalibrationReport(params=calibrated, checks=checks_frame, summary=summary)


def write_calibrated_replay_plan(
    *,
    strategy: str,
    fill_model_path: str | Path,
    output_dir: str | Path,
    base_params: dict[str, Any] | None = None,
    require_ready: bool = True,
) -> ReplayCalibrationReport:
    base_params = base_params or {}
    fill_model_file = Path(fill_model_path)
    config = load_fill_model_config(fill_model_file)
    report = apply_fill_model_to_replay_params(strategy, base_params, config, require_ready=require_ready)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibrated_replay_params.json").write_text(
        json.dumps(report.params, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report.checks.to_csv(out / "calibrated_replay_checks.csv", index=False)
    report.summary.to_csv(out / "calibrated_replay_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="calibrated_replay_plan",
        parameters={"strategy": _strategy_key(strategy), "base_params": base_params, "require_ready": require_ready},
        inputs={"fill_model": fill_model_file},
    )
    return ReplayCalibrationReport(report.params, report.checks, report.summary, out)


def calibrated_replay_params_from_path(
    strategy: str,
    base_params: dict[str, Any],
    fill_model_path: str | Path | None,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    if fill_model_path is None:
        return dict(base_params)
    report = apply_fill_model_to_replay_params(
        strategy,
        base_params,
        load_fill_model_config(fill_model_path),
        require_ready=require_ready,
    )
    if not report.ready:
        failed = report.checks.loc[~report.checks["passed"].astype(bool), "check"].astype(str).tolist()
        raise ValueError(f"fill-model replay calibration is not ready: {failed}")
    return report.params


def _apply_max(params: dict[str, Any], key: str, value: float, applied_fields: list[str]) -> None:
    if pd.isna(value):
        return
    current = _param_number(params, key, 0.0)
    params[key] = max(current, float(value))
    applied_fields.append(key)


def _apply_depth_fraction(params: dict[str, Any], key: str, queue_conservatism: float, applied_fields: list[str]) -> None:
    if pd.isna(queue_conservatism) or queue_conservatism <= 0:
        return
    calibrated_depth = min(1.0, 1.0 / float(queue_conservatism))
    current = _param_number(params, key, 1.0)
    params[key] = max(0.0, min(current, calibrated_depth))
    applied_fields.append(key)


def _summary(
    strategy: str,
    params: dict[str, Any],
    applied_fields: list[str],
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategy,
                "applied_fields": ";".join(applied_fields),
                "parameter_count": int(len(params)),
                "failed_checks": failed,
                "recommendation": "run_calibrated_replay" if ready else "fix_fill_model_before_replay",
            }
        ]
    )


def _base_checks(fill_model_config: dict[str, Any], require_ready: bool) -> list[dict[str, object]]:
    ready = _to_bool(fill_model_config.get("ready", False))
    global_present = isinstance(fill_model_config.get("global"), dict) and bool(fill_model_config.get("global"))
    return [
        _check(
            "fill_model_ready",
            ready,
            "is",
            True,
            ready or not require_ready,
            "fill-model config is not ready",
        ),
        _check(
            "global_recommendation_present",
            global_present,
            "is",
            True,
            global_present,
            "fill-model config does not contain a global recommendation",
        ),
    ]


def _strategy_key(strategy: str) -> str:
    key = strategy.strip().lower().replace("-", "_")
    aliases = {
        "lead_lag": "leadlag",
        "leadlag_replay": "leadlag",
        "parity_replay": "parity",
        "surface": "surface_mm",
        "surface_market_making": "surface_mm",
        "surface_quotes": "surface_quotes",
    }
    key = aliases.get(key, key)
    if key not in SUPPORTED_STRATEGIES:
        raise ValueError(f"unsupported calibrated replay strategy {strategy!r}; supported: {sorted(SUPPORTED_STRATEGIES)}")
    return key


def _number(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key)
    if value is None or pd.isna(value):
        return float("nan")
    return float(value)


def _param_number(params: dict[str, Any], key: str, default: float) -> float:
    value = params.get(key, default)
    if value is None or pd.isna(value):
        return default
    return float(value)


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
