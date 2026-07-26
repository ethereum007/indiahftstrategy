from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.orders import read_order_csv
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class LaunchThresholds:
    min_accepted_orders: int = 1
    min_acceptance_rate: float = 1.0
    require_promotion_ready: bool = True
    require_no_rejections: bool = True
    require_quote_risk_review: bool = False
    max_total_notional: float | None = None
    max_order_notional: float | None = None


@dataclass(frozen=True)
class LaunchBundleReport:
    launch_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_launch_bundle(
    *,
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    staged_summary: pd.DataFrame,
    staged_orders: pd.DataFrame,
    staged_rejections: pd.DataFrame | None = None,
    thresholds: LaunchThresholds | None = None,
    mode: str = "paper",
    adapter: str = "normalized",
) -> LaunchBundleReport:
    thresholds = thresholds or LaunchThresholds()
    _validate_thresholds(thresholds)
    _require(promotion_summary, ["ready", "candidate_scenario_key"], "promotion_summary")
    _require(staged_summary, ["accepted_orders", "rejected_orders", "acceptance_rate"], "staged_summary")
    _require(staged_orders, ["client_order_id", "instrument_id", "side", "qty", "price"], "staged_orders")
    rejections = staged_rejections if staged_rejections is not None else pd.DataFrame()

    launch_orders = _launch_orders(
        staged_orders,
        candidate_config=candidate_config,
        promotion_summary=promotion_summary,
        mode=mode,
        adapter=adapter,
    )
    checks = _checks(
        promotion_summary=promotion_summary,
        candidate_config=candidate_config,
        staged_summary=staged_summary,
        staged_orders=staged_orders,
        staged_rejections=rejections,
        thresholds=thresholds,
    )
    summary = _summary(
        promotion_summary=promotion_summary,
        candidate_config=candidate_config,
        staged_summary=staged_summary,
        checks=checks,
        mode=mode,
        adapter=adapter,
    )
    return LaunchBundleReport(launch_orders=launch_orders, checks=checks, summary=summary)


def write_launch_bundle(
    *,
    promotion_dir: str | Path,
    staged_orders_dir: str | Path,
    output_dir: str | Path,
    thresholds: LaunchThresholds | None = None,
    mode: str = "paper",
    adapter: str = "normalized",
) -> LaunchBundleReport:
    promotion = Path(promotion_dir)
    staged = Path(staged_orders_dir)
    promotion_summary = _read_required(promotion / "promotion_summary.csv")
    staged_summary = _read_required(staged / "staged_order_summary.csv")
    staged_orders = _read_required(
        staged / "staged_orders.csv",
        preserve_order_identity=True,
    )
    staged_rejections = _read_optional(staged / "staged_order_rejections.csv")
    candidate_config_path = promotion / "candidate_config.json"
    if not candidate_config_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_config_path}")
    candidate_config = json.loads(candidate_config_path.read_text(encoding="utf-8"))

    thresholds = thresholds or LaunchThresholds()
    report = evaluate_launch_bundle(
        promotion_summary=promotion_summary,
        candidate_config=candidate_config,
        staged_summary=staged_summary,
        staged_orders=staged_orders,
        staged_rejections=staged_rejections,
        thresholds=thresholds,
        mode=mode,
        adapter=adapter,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.launch_orders.to_csv(out / "launch_orders.csv", index=False)
    report.checks.to_csv(out / "launch_checks.csv", index=False)
    report.summary.to_csv(out / "launch_summary.csv", index=False)
    (out / "launch_config.json").write_text(
        json.dumps(
            _launch_config(report, candidate_config, thresholds=thresholds),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="launch_bundle",
        parameters={"mode": mode, "adapter": adapter, "thresholds": asdict(thresholds)},
        inputs={"promotion": promotion, "staged_orders": staged},
    )
    return LaunchBundleReport(report.launch_orders, report.checks, report.summary, out)


def _launch_orders(
    staged_orders: pd.DataFrame,
    *,
    candidate_config: dict[str, Any],
    promotion_summary: pd.DataFrame,
    mode: str,
    adapter: str,
) -> pd.DataFrame:
    scenario_key = str(candidate_config.get("scenario_key") or promotion_summary.iloc[0].get("candidate_scenario_key", ""))
    out = staged_orders.copy().reset_index(drop=True)
    out.insert(0, "launch_mode", mode)
    out.insert(1, "adapter", adapter)
    out.insert(2, "scenario_key", scenario_key)
    out.insert(3, "launch_order_id", [f"LCH-{idx:06d}-{order_id}" for idx, order_id in enumerate(out["client_order_id"])])
    return out


def _checks(
    *,
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    staged_summary: pd.DataFrame,
    staged_orders: pd.DataFrame,
    staged_rejections: pd.DataFrame,
    thresholds: LaunchThresholds,
) -> pd.DataFrame:
    promo_row = promotion_summary.iloc[0]
    stage_row = staged_summary.iloc[0]
    promotion_ready = _to_bool(promo_row["ready"])
    config_ready = _to_bool(candidate_config.get("ready", False))
    rejected_orders = float(stage_row["rejected_orders"])
    checks = [
        _check(
            "promotion_ready",
            promotion_ready,
            "is",
            True,
            (not thresholds.require_promotion_ready) or promotion_ready,
            "promotion gate is not ready",
        ),
        _check(
            "candidate_config_ready",
            config_ready,
            "is",
            True,
            (not thresholds.require_promotion_ready) or config_ready,
            "candidate_config.json is not ready",
        ),
        _threshold_check("accepted_orders", float(stage_row["accepted_orders"]), ">=", thresholds.min_accepted_orders),
        _threshold_check("acceptance_rate", float(stage_row["acceptance_rate"]), ">=", thresholds.min_acceptance_rate),
        _check(
            "no_order_rejections",
            rejected_orders,
            "==",
            0,
            (not thresholds.require_no_rejections) or rejected_orders == 0,
            "staged order batch contains rejections",
        ),
    ]
    if thresholds.require_no_rejections and not staged_rejections.empty:
        checks.append(
            _check(
                "rejection_file_empty",
                len(staged_rejections),
                "==",
                0,
                False,
                "staged_order_rejections.csv contains rows",
            )
        )
    if thresholds.max_total_notional is not None:
        checks.append(
            _threshold_check("total_notional", float(stage_row.get("total_notional", np.nan)), "<=", thresholds.max_total_notional)
        )
    if thresholds.max_order_notional is not None:
        checks.append(
            _threshold_check(
                "max_order_notional",
                float(stage_row.get("max_order_notional", np.nan)),
                "<=",
                thresholds.max_order_notional,
            )
        )
    if thresholds.require_quote_risk_review:
        surface_orders = _surface_quote_orders(staged_orders)
        quote_review_passed = _to_bool(stage_row.get("quote_risk_review_passed", False))
        checks.append(
            _check(
                "surface_quote_risk_review",
                quote_review_passed,
                "is",
                True,
                (not surface_orders) or quote_review_passed,
                "surface quote orders require a passed quote-risk review",
            )
        )
    checks.append(
        _check(
            "launch_orders_nonempty",
            len(staged_orders),
            ">=",
            1,
            len(staged_orders) > 0,
            "no staged orders available for launch bundle",
        )
    )
    return pd.DataFrame(checks)


def _summary(
    *,
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    staged_summary: pd.DataFrame,
    checks: pd.DataFrame,
    mode: str,
    adapter: str,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    promo_row = promotion_summary.iloc[0]
    stage_row = staged_summary.iloc[0]
    scenario_key = str(candidate_config.get("scenario_key") or promo_row.get("candidate_scenario_key", ""))
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "mode": mode,
                "adapter": adapter,
                "scenario_key": scenario_key,
                "accepted_orders": int(stage_row["accepted_orders"]),
                "rejected_orders": int(stage_row["rejected_orders"]),
                "acceptance_rate": float(stage_row["acceptance_rate"]),
                "total_notional": float(stage_row.get("total_notional", np.nan)),
                "quote_risk_review_required": any(checks["check"] == "surface_quote_risk_review"),
                "quote_risk_review_passed": _to_bool(stage_row.get("quote_risk_review_passed", False)),
                "failed_checks": failed,
                "recommendation": "paper_or_shadow_launch" if ready else "do_not_launch",
            }
        ]
    )


def _launch_config(
    report: LaunchBundleReport,
    candidate_config: dict[str, Any],
    *,
    thresholds: LaunchThresholds,
) -> dict[str, Any]:
    row = report.summary.iloc[0]
    return {
        "schema_version": 1,
        "ready": bool(row["ready"]),
        "mode": str(row["mode"]),
        "adapter": str(row["adapter"]),
        "scenario_key": str(row["scenario_key"]),
        "candidate": candidate_config,
        "order_batch": {
            "accepted_orders": int(row["accepted_orders"]),
            "rejected_orders": int(row["rejected_orders"]),
            "acceptance_rate": float(row["acceptance_rate"]),
            "total_notional": _jsonable(row["total_notional"]),
            "quote_risk_review_required": _jsonable(row.get("quote_risk_review_required", False)),
            "quote_risk_review_passed": _jsonable(row.get("quote_risk_review_passed", False)),
        },
        "thresholds": asdict(thresholds),
        "recommendation": str(row["recommendation"]),
    }


def _read_required(
    path: Path,
    *,
    preserve_order_identity: bool = False,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required launch input missing: {path}")
    frame = (
        read_order_csv(path)
        if preserve_order_identity
        else pd.read_csv(path)
    )
    if frame.empty:
        raise ValueError(f"required launch input is empty: {path}")
    return frame


def _read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _validate_thresholds(thresholds: LaunchThresholds) -> None:
    if thresholds.min_accepted_orders < 0:
        raise ValueError("min_accepted_orders must be non-negative")
    if not 0 <= thresholds.min_acceptance_rate <= 1:
        raise ValueError("min_acceptance_rate must be between 0 and 1")
    if thresholds.max_total_notional is not None and thresholds.max_total_notional <= 0:
        raise ValueError("max_total_notional must be positive")
    if thresholds.max_order_notional is not None and thresholds.max_order_notional <= 0:
        raise ValueError("max_order_notional must be positive")


def _surface_quote_orders(staged_orders: pd.DataFrame) -> bool:
    if "source" not in staged_orders.columns:
        return False
    return bool(staged_orders["source"].astype(str).str.lower().eq("surface_quotes").any())


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


def _jsonable(value: object) -> object:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if pd.isna(value):
        return None
    return value
