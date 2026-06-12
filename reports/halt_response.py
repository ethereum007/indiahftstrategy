from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


CANCEL_COLUMNS = [
    "action_id",
    "action",
    "client_order_id",
    "broker_order_id",
    "instrument_id",
    "side",
    "side_text",
    "open_qty",
    "reason",
]

FLATTEN_COLUMNS = [
    "action_id",
    "action",
    "instrument_id",
    "side",
    "side_text",
    "qty",
    "price",
    "order_type",
    "time_in_force",
    "reason",
]

TERMINAL_STATUSES = {"filled", "cancelled", "canceled", "rejected", "expired", "complete", "closed"}


@dataclass(frozen=True)
class HaltResponseConfig:
    require_guard_halt: bool = True
    require_flatten_prices: bool = True
    default_order_type: str = "LIMIT"
    default_time_in_force: str = "DAY"


@dataclass(frozen=True)
class HaltResponseReport:
    cancel_orders: pd.DataFrame
    flatten_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_halt_response(
    guard_summary: pd.DataFrame,
    guard_checks: pd.DataFrame | None = None,
    *,
    open_orders: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    config: HaltResponseConfig | None = None,
) -> HaltResponseReport:
    config = config or HaltResponseConfig()
    guard_summary = _require_guard_summary(guard_summary)
    guard_checks = pd.DataFrame() if guard_checks is None else guard_checks.copy()
    open_orders = pd.DataFrame() if open_orders is None else open_orders.copy()
    positions = pd.DataFrame() if positions is None else positions.copy()

    guard_row = guard_summary.iloc[0]
    cancel_orders = _cancel_actions(open_orders)
    flatten_orders = _flatten_actions(positions, config)
    checks = _checks(guard_row, cancel_orders, flatten_orders, config)
    summary = _summary(guard_row, cancel_orders, flatten_orders, checks)
    response_config = {
        **asdict(config),
        "guard_failed_checks": _failed_guard_checks(guard_checks),
    }
    return HaltResponseReport(
        cancel_orders=cancel_orders,
        flatten_orders=flatten_orders,
        checks=checks,
        summary=summary,
        config=response_config,
    )


def write_halt_response_plan(
    *,
    guard_dir: str | Path,
    output_dir: str | Path,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    config: HaltResponseConfig | None = None,
) -> HaltResponseReport:
    guard = Path(guard_dir)
    guard_summary_path = guard / "runtime_guard_summary.csv" if guard.is_dir() else guard
    guard_checks_path = guard / "runtime_guard_checks.csv" if guard.is_dir() else None
    guard_summary = _read_required(guard_summary_path)
    guard_checks = pd.read_csv(guard_checks_path) if guard_checks_path and guard_checks_path.exists() else None
    open_orders = _read_optional(open_orders_path)
    positions = _read_optional(positions_path)

    config = config or HaltResponseConfig()
    report = evaluate_halt_response(
        guard_summary,
        guard_checks,
        open_orders=open_orders,
        positions=positions,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.cancel_orders.to_csv(out / "halt_cancel_orders.csv", index=False)
    report.flatten_orders.to_csv(out / "halt_flatten_orders.csv", index=False)
    report.checks.to_csv(out / "halt_response_checks.csv", index=False)
    report.summary.to_csv(out / "halt_response_summary.csv", index=False)
    (out / "halt_response_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="halt_response_plan",
        parameters={"config": asdict(config)},
        inputs={
            "guard": guard,
            "open_orders": open_orders_path,
            "positions": positions_path,
        },
    )
    return HaltResponseReport(
        report.cancel_orders,
        report.flatten_orders,
        report.checks,
        report.summary,
        report.config,
        out,
    )


def _cancel_actions(open_orders: pd.DataFrame) -> pd.DataFrame:
    if open_orders.empty:
        return pd.DataFrame(columns=CANCEL_COLUMNS)
    frame = open_orders.copy().reset_index(drop=True)
    frame["client_order_id"] = _column_or_default(frame, "client_order_id", "")
    frame["broker_order_id"] = _column_or_default(frame, "broker_order_id", "")
    frame["instrument_id"] = _column_or_default(frame, "instrument_id", "")
    frame["side"] = _numeric_column(frame, "side", np.nan)
    frame["side_text"] = _side_text(frame)
    frame["status"] = _column_or_default(frame, "status", "open").astype(str).str.strip().str.lower()
    frame["open_qty"] = _open_qty(frame)
    active = frame.loc[(~frame["status"].isin(TERMINAL_STATUSES)) & (frame["open_qty"] > 0)].copy()
    active["action_id"] = [f"CXL-{idx:06d}" for idx in range(len(active))]
    active["action"] = "cancel_order"
    active["reason"] = "guard_halt_open_order"
    return active[CANCEL_COLUMNS].reset_index(drop=True)


def _flatten_actions(positions: pd.DataFrame, config: HaltResponseConfig) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=FLATTEN_COLUMNS)
    frame = positions.copy().reset_index(drop=True)
    if "instrument_id" not in frame.columns:
        raise ValueError("positions must contain instrument_id")
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["net_qty"] = _net_qty(frame)
    active = frame.loc[frame["net_qty"] != 0].copy()
    active["side"] = np.where(active["net_qty"] > 0, -1, 1)
    active["side_text"] = np.where(active["side"] > 0, "BUY", "SELL")
    active["qty"] = active["net_qty"].abs()
    active["price"] = [_flatten_price(row) for row in active.to_dict("records")]
    active["order_type"] = str(config.default_order_type)
    active["time_in_force"] = str(config.default_time_in_force)
    active["reason"] = "flatten_residual_position"
    active["action"] = "flatten_position"
    active["action_id"] = [f"FLT-{idx:06d}" for idx in range(len(active))]
    return active[FLATTEN_COLUMNS].reset_index(drop=True)


def _checks(
    guard_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    config: HaltResponseConfig,
) -> pd.DataFrame:
    guard_halted = _to_bool(guard_row.get("halted", False)) or str(guard_row.get("guard_action", "")) == "halt"
    checks = [
        _check(
            "guard_halted",
            guard_halted,
            "is",
            True,
            guard_halted or not config.require_guard_halt,
            "runtime guard has not requested a halt",
        ),
        _check(
            "cancel_actions_available",
            int(len(cancel_orders)),
            ">=",
            0,
            True,
            "",
        ),
    ]
    missing_prices = int(flatten_orders["price"].isna().sum()) if not flatten_orders.empty else 0
    checks.append(
        _check(
            "flatten_prices_available",
            missing_prices,
            "==",
            0,
            missing_prices == 0 or not config.require_flatten_prices,
            "one or more residual positions do not have executable flatten prices",
        )
    )
    checks.append(
        _check(
            "response_plan_coherent",
            int(len(cancel_orders) + len(flatten_orders)),
            ">=",
            0,
            True,
            "",
        )
    )
    return pd.DataFrame(checks)


def _summary(
    guard_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    action_count = int(len(cancel_orders) + len(flatten_orders))
    recommendation = "do_not_execute_response_until_inputs_fixed"
    if ready and action_count:
        recommendation = "submit_cancel_and_flatten"
    elif ready:
        recommendation = "halt_confirmed_no_open_risk"
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": str(guard_row.get("guard_action", "")),
                "cancel_orders": int(len(cancel_orders)),
                "flatten_orders": int(len(flatten_orders)),
                "open_risk_items": action_count,
                "failed_checks": failed,
                "scenario_key": str(guard_row.get("scenario_key", "")),
                "adapter": str(guard_row.get("adapter", "")),
                "recommendation": recommendation,
            }
        ]
    )


def _require_guard_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        raise ValueError("guard summary is empty")
    required = {"guard_action"}
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(f"guard summary missing columns: {', '.join(missing)}")
    return summary.copy().reset_index(drop=True)


def _read_required(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required CSV not found: {file_path}")
    return pd.read_csv(file_path)


def _read_optional(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"optional CSV path was provided but not found: {file_path}")
    return pd.read_csv(file_path)


def _column_or_default(frame: pd.DataFrame, column: str, default: object) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index)


def _numeric_column(frame: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _open_qty(frame: pd.DataFrame) -> pd.Series:
    for column in ("open_qty", "leaves_qty", "remaining_qty"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    qty = _numeric_column(frame, "qty", 0.0).fillna(0.0)
    filled = _numeric_column(frame, "filled_qty", 0.0).fillna(0.0)
    return (qty - filled).clip(lower=0.0)


def _net_qty(frame: pd.DataFrame) -> pd.Series:
    for column in ("net_qty", "position", "qty"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    raise ValueError("positions must contain net_qty, position, or qty")


def _side_text(frame: pd.DataFrame) -> pd.Series:
    if "side_text" in frame.columns:
        return frame["side_text"].astype(str).str.upper()
    side = _numeric_column(frame, "side", np.nan)
    return side.map({1.0: "BUY", -1.0: "SELL"}).fillna("UNKNOWN")


def _flatten_price(row: dict[str, Any]) -> float:
    side = int(row["side"])
    columns = ("market_ask", "ask", "best_ask", "last", "price") if side > 0 else (
        "market_bid",
        "bid",
        "best_bid",
        "last",
        "price",
    )
    for column in columns:
        value = row.get(column, np.nan)
        if not pd.isna(value):
            return float(value)
    return float("nan")


def _failed_guard_checks(guard_checks: pd.DataFrame) -> list[str]:
    if guard_checks.empty or "passed" not in guard_checks.columns or "check" not in guard_checks.columns:
        return []
    failed = guard_checks.loc[~guard_checks["passed"].map(_to_bool), "check"]
    return [str(item) for item in failed.tolist()]


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "halt"}
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
