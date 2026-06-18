from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


CANCEL_ACK_STATUSES = {"accepted", "cancelled", "canceled", "cancel_ack", "success", "done", "complete", "closed"}
FILL_STATUSES = {"filled", "fill", "partial", "executed", "traded", "success", "done", "complete", ""}


@dataclass(frozen=True)
class HaltExecutionThresholds:
    require_response_ready: bool = True
    require_all_cancel_acks: bool = True
    require_all_flatten_fills: bool = True
    require_final_positions: bool = True
    position_tolerance: float = 0.0


@dataclass(frozen=True)
class HaltExecutionReport:
    cancel_execution: pd.DataFrame
    flatten_execution: pd.DataFrame
    position_execution: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_halt_execution(
    halt_summary: pd.DataFrame,
    cancel_actions: pd.DataFrame,
    flatten_actions: pd.DataFrame,
    *,
    cancel_acks: pd.DataFrame | None = None,
    flatten_fills: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    thresholds: HaltExecutionThresholds | None = None,
) -> HaltExecutionReport:
    thresholds = thresholds or HaltExecutionThresholds()
    _validate_thresholds(thresholds)
    _require_summary(halt_summary)
    cancel_actions = cancel_actions.copy().reset_index(drop=True)
    flatten_actions = flatten_actions.copy().reset_index(drop=True)
    cancel_acks = pd.DataFrame() if cancel_acks is None else cancel_acks.copy().reset_index(drop=True)
    flatten_fills = pd.DataFrame() if flatten_fills is None else flatten_fills.copy().reset_index(drop=True)
    positions = pd.DataFrame() if positions is None else positions.copy().reset_index(drop=True)

    cancel_execution = _cancel_execution(cancel_actions, cancel_acks)
    flatten_execution = _flatten_execution(flatten_actions, flatten_fills)
    position_execution = _position_execution(positions, thresholds.position_tolerance)
    checks = _checks(
        halt_summary.iloc[0],
        cancel_execution,
        flatten_execution,
        position_execution,
        positions_provided=not positions.empty,
        thresholds=thresholds,
    )
    summary = _summary(halt_summary.iloc[0], cancel_execution, flatten_execution, position_execution, checks)
    return HaltExecutionReport(
        cancel_execution=cancel_execution,
        flatten_execution=flatten_execution,
        position_execution=position_execution,
        checks=checks,
        summary=summary,
    )


def write_halt_execution_report(
    *,
    halt_response_dir: str | Path,
    output_dir: str | Path,
    cancel_acks_path: str | Path | None = None,
    flatten_fills_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    thresholds: HaltExecutionThresholds | None = None,
) -> HaltExecutionReport:
    halt_dir = Path(halt_response_dir)
    halt_summary = _read_required(halt_dir / "halt_response_summary.csv")
    cancel_actions = _read_required(halt_dir / "halt_cancel_orders.csv")
    flatten_actions = _read_required(halt_dir / "halt_flatten_orders.csv")
    thresholds = thresholds or HaltExecutionThresholds()
    report = evaluate_halt_execution(
        halt_summary,
        cancel_actions,
        flatten_actions,
        cancel_acks=_read_optional(cancel_acks_path),
        flatten_fills=_read_optional(flatten_fills_path),
        positions=_read_optional(positions_path),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.cancel_execution.to_csv(out / "halt_cancel_execution.csv", index=False)
    report.flatten_execution.to_csv(out / "halt_flatten_execution.csv", index=False)
    report.position_execution.to_csv(out / "halt_position_execution.csv", index=False)
    report.checks.to_csv(out / "halt_execution_checks.csv", index=False)
    report.summary.to_csv(out / "halt_execution_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="halt_execution_reconciliation",
        parameters={"thresholds": asdict(thresholds)},
        inputs=_manifest_inputs(
            halt_response_dir=halt_dir,
            cancel_acks_path=cancel_acks_path,
            flatten_fills_path=flatten_fills_path,
            positions_path=positions_path,
        ),
    )
    return HaltExecutionReport(
        report.cancel_execution,
        report.flatten_execution,
        report.position_execution,
        report.checks,
        report.summary,
        out,
    )


def _manifest_inputs(
    *,
    halt_response_dir: Path,
    cancel_acks_path: str | Path | None,
    flatten_fills_path: str | Path | None,
    positions_path: str | Path | None,
) -> dict[str, Path]:
    inputs = {
        "halt_response_summary": halt_response_dir / "halt_response_summary.csv",
        "halt_cancel_orders": halt_response_dir / "halt_cancel_orders.csv",
        "halt_flatten_orders": halt_response_dir / "halt_flatten_orders.csv",
    }
    if cancel_acks_path is not None:
        inputs["cancel_acks"] = Path(cancel_acks_path)
    if flatten_fills_path is not None:
        inputs["flatten_fills"] = Path(flatten_fills_path)
    if positions_path is not None:
        inputs["positions"] = Path(positions_path)
    return inputs


def _cancel_execution(cancel_actions: pd.DataFrame, cancel_acks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for idx, action in cancel_actions.reset_index(drop=True).iterrows():
        matches, match_key = _match_rows(action, cancel_acks, ["action_id", "broker_order_id", "client_order_id"])
        status = _status(matches, ["cancel_status", "ack_status", "order_status", "status"])
        rows.append(
            {
                "action_id": _value(action, "action_id", f"CXL-{idx:06d}"),
                "client_order_id": _value(action, "client_order_id", ""),
                "broker_order_id": _value(action, "broker_order_id", ""),
                "instrument_id": _value(action, "instrument_id", ""),
                "open_qty": _number(action, "open_qty", 0.0),
                "ack_status": status,
                "ack_count": int(len(matches)),
                "match_key": match_key,
                "acked": status in CANCEL_ACK_STATUSES,
            }
        )
    return pd.DataFrame(rows)


def _flatten_execution(flatten_actions: pd.DataFrame, flatten_fills: pd.DataFrame) -> pd.DataFrame:
    rows = []
    fills = flatten_fills.copy()
    if not fills.empty and "side" in fills.columns:
        fills["side"] = fills["side"].map(_normalize_side)
    for idx, action in flatten_actions.reset_index(drop=True).iterrows():
        action_side = _normalize_side(action.get("side", np.nan))
        matches, match_key = _match_flatten_rows(action, fills, action_side)
        usable = _usable_fills(matches)
        filled_qty = _filled_qty(usable)
        target_qty = _number(action, "qty", 0.0)
        avg_price = _avg_fill_price(usable)
        rows.append(
            {
                "action_id": _value(action, "action_id", f"FLT-{idx:06d}"),
                "instrument_id": _value(action, "instrument_id", ""),
                "side": action_side,
                "side_text": "BUY" if action_side > 0 else "SELL" if action_side < 0 else "UNKNOWN",
                "target_qty": target_qty,
                "filled_qty": filled_qty,
                "remaining_qty": max(target_qty - filled_qty, 0.0),
                "avg_fill_price": avg_price,
                "fill_count": int(len(usable)),
                "match_key": match_key,
                "complete": filled_qty + 1e-12 >= target_qty,
            }
        )
    return pd.DataFrame(rows)


def _position_execution(positions: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=["instrument_id", "net_qty", "abs_net_qty", "flat"])
    if "instrument_id" not in positions.columns:
        raise ValueError("positions must contain instrument_id")
    quantities = _position_quantities(positions)
    out = pd.DataFrame(
        {
            "instrument_id": positions["instrument_id"].astype(str),
            "net_qty": quantities,
            "abs_net_qty": quantities.abs(),
        }
    )
    out["flat"] = out["abs_net_qty"] <= float(tolerance)
    return out


def _checks(
    halt_row: pd.Series,
    cancel_execution: pd.DataFrame,
    flatten_execution: pd.DataFrame,
    position_execution: pd.DataFrame,
    *,
    positions_provided: bool,
    thresholds: HaltExecutionThresholds,
) -> pd.DataFrame:
    response_ready = _to_bool(halt_row.get("ready", False))
    cancel_total = int(len(cancel_execution))
    cancel_acked = int(cancel_execution["acked"].sum()) if cancel_total else 0
    flatten_total = int(len(flatten_execution))
    flatten_complete = int(flatten_execution["complete"].sum()) if flatten_total else 0
    nonflat_positions = int((~position_execution["flat"].astype(bool)).sum()) if not position_execution.empty else 0
    final_positions_passed = True
    if thresholds.require_final_positions and flatten_total > 0:
        final_positions_passed = positions_provided and nonflat_positions == 0
    return pd.DataFrame(
        [
            _check(
                "response_ready",
                response_ready,
                "is",
                True,
                response_ready or not thresholds.require_response_ready,
                "halt response plan was not ready",
            ),
            _check(
                "cancel_acks_complete",
                cancel_acked,
                "==",
                cancel_total,
                (cancel_acked == cancel_total) or not thresholds.require_all_cancel_acks,
                "not all cancel actions have terminal acknowledgements",
            ),
            _check(
                "flatten_fills_complete",
                flatten_complete,
                "==",
                flatten_total,
                (flatten_complete == flatten_total) or not thresholds.require_all_flatten_fills,
                "not all flatten actions are fully filled",
            ),
            _check(
                "final_positions_flat",
                nonflat_positions,
                "==",
                0,
                final_positions_passed,
                "final position snapshot is missing or contains residual positions",
            ),
        ]
    )


def _summary(
    halt_row: pd.Series,
    cancel_execution: pd.DataFrame,
    flatten_execution: pd.DataFrame,
    position_execution: pd.DataFrame,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 1
    passed = failed == 0
    cancel_acked = int(cancel_execution["acked"].sum()) if not cancel_execution.empty else 0
    flatten_complete = int(flatten_execution["complete"].sum()) if not flatten_execution.empty else 0
    nonflat_positions = int((~position_execution["flat"].astype(bool)).sum()) if not position_execution.empty else 0
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "scenario_key": str(halt_row.get("scenario_key", "")),
                "adapter": str(halt_row.get("adapter", "")),
                "cancel_actions": int(len(cancel_execution)),
                "cancel_acked": cancel_acked,
                "flatten_actions": int(len(flatten_execution)),
                "flatten_filled": flatten_complete,
                "nonflat_positions": nonflat_positions,
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "recommendation": "halt_completed" if passed else "continue_halt_investigation",
            }
        ]
    )


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    return checks.loc[~checks["passed"].map(_to_bool)].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    return _check_value(row, "check")


def _check_reason(row: pd.Series) -> str:
    return _check_value(row, "reason")


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    return _clean(row[column])


def _match_rows(action: pd.Series, frame: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, str]:
    if frame.empty:
        return frame, ""
    for column in columns:
        if column in action.index and column in frame.columns:
            value = _clean(action.get(column))
            if value:
                matches = frame.loc[frame[column].astype(str).str.strip() == value]
                if not matches.empty:
                    return matches, column
    return frame.iloc[:0], ""


def _match_flatten_rows(action: pd.Series, fills: pd.DataFrame, action_side: int) -> tuple[pd.DataFrame, str]:
    matches, match_key = _match_rows(action, fills, ["action_id"])
    if not matches.empty:
        return matches, match_key
    if fills.empty or "instrument_id" not in fills.columns:
        return fills.iloc[:0], ""
    instrument = _clean(action.get("instrument_id"))
    by_instrument = fills.loc[fills["instrument_id"].astype(str).str.strip() == instrument]
    if by_instrument.empty:
        return by_instrument, ""
    if "side" in by_instrument.columns and action_side != 0:
        by_side = by_instrument.loc[by_instrument["side"] == action_side]
        return by_side, "instrument_id+side" if not by_side.empty else ""
    return by_instrument, "instrument_id"


def _usable_fills(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return fills
    if not any(column in fills.columns for column in ("fill_status", "status", "order_status")):
        return fills
    status = fills.apply(lambda row: _status(pd.DataFrame([row]), ["fill_status", "status", "order_status"]), axis=1)
    return fills.loc[status.isin(FILL_STATUSES)]


def _status(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return ""
    for column in columns:
        if column in frame.columns:
            values = frame[column].dropna().astype(str).str.strip().str.lower()
            values = values.loc[values != ""]
            if not values.empty:
                return str(values.iloc[-1])
    return ""


def _filled_qty(fills: pd.DataFrame) -> float:
    if fills.empty:
        return 0.0
    for column in ("filled_qty", "fill_qty", "qty"):
        if column in fills.columns:
            return float(pd.to_numeric(fills[column], errors="coerce").fillna(0.0).sum())
    return 0.0


def _avg_fill_price(fills: pd.DataFrame) -> float:
    if fills.empty or "price" not in fills.columns:
        return np.nan
    qty_column = "qty" if "qty" in fills.columns else "filled_qty" if "filled_qty" in fills.columns else None
    prices = pd.to_numeric(fills["price"], errors="coerce")
    if qty_column is None:
        return float(prices.mean(skipna=True)) if prices.notna().any() else np.nan
    qty = pd.to_numeric(fills[qty_column], errors="coerce").fillna(0.0)
    notional = float((qty * prices.fillna(0.0)).sum())
    total_qty = float(qty.sum())
    return notional / total_qty if total_qty > 0 else np.nan


def _position_quantities(positions: pd.DataFrame) -> pd.Series:
    for column in ("net_qty", "position", "qty"):
        if column in positions.columns:
            return pd.to_numeric(positions[column], errors="coerce").fillna(0.0)
    raise ValueError("positions must contain net_qty, position, or qty")


def _read_required(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required halt execution input not found: {file_path}")
    return pd.read_csv(file_path)


def _read_optional(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"optional halt execution input not found: {file_path}")
    return pd.read_csv(file_path)


def _require_summary(summary: pd.DataFrame) -> None:
    if summary.empty:
        raise ValueError("halt response summary is empty")
    if "ready" not in summary.columns:
        raise ValueError("halt response summary missing required column: ready")


def _validate_thresholds(thresholds: HaltExecutionThresholds) -> None:
    if thresholds.position_tolerance < 0:
        raise ValueError("position_tolerance must be non-negative")


def _normalize_side(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    numeric = float(value)
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0


def _number(row: pd.Series, column: str, default: float) -> float:
    if column not in row.index:
        return default
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else default


def _value(row: pd.Series, column: str, default: str) -> str:
    if column not in row.index:
        return default
    value = row[column]
    if pd.isna(value):
        return default
    return str(value)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
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
