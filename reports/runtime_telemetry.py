from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


GUARD_COLUMNS = [
    "scenario_key",
    "adapter",
    "orders_sent",
    "session_notional",
    "realized_pnl",
    "total_failed_component_checks",
    "unmatched_fills",
    "mismatched_orders",
    "overfilled_orders",
    "worst_adverse_slippage",
]


@dataclass(frozen=True)
class RuntimeTelemetryReport:
    telemetry: pd.DataFrame
    sources: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_runtime_telemetry(
    scaleup_config: dict[str, Any],
    *,
    export_summary: pd.DataFrame | None = None,
    reconciliation_summary: pd.DataFrame | None = None,
    reconciliation_checks: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    pnl_snapshot: pd.DataFrame | None = None,
    open_orders: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    snapshot_ts_ns: int | float | None = None,
) -> RuntimeTelemetryReport:
    export_summary = _optional_frame(export_summary)
    reconciliation_summary = _optional_frame(reconciliation_summary)
    reconciliation_checks = _optional_frame(reconciliation_checks)
    instrument_metadata_summary = _optional_frame(instrument_metadata_summary)
    pnl_snapshot = _optional_frame(pnl_snapshot)
    open_orders = _optional_frame(open_orders)
    positions = _optional_frame(positions)

    telemetry = _telemetry(
        scaleup_config,
        export_summary=export_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
        snapshot_ts_ns=snapshot_ts_ns,
    )
    sources = _sources(
        export_summary=export_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
    )
    checks = _checks(telemetry.iloc[0])
    summary = _summary(telemetry.iloc[0], checks)
    return RuntimeTelemetryReport(telemetry=telemetry, sources=sources, checks=checks, summary=summary)


def write_runtime_telemetry_snapshot(
    *,
    scaleup_dir: str | Path,
    output_dir: str | Path,
    export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    pnl_path: str | Path | None = None,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    snapshot_ts_ns: int | float | None = None,
) -> RuntimeTelemetryReport:
    scaleup_file = _scaleup_config_path(scaleup_dir)
    scaleup_config = json.loads(scaleup_file.read_text(encoding="utf-8"))
    export_summary = _read_optional_summary(export_dir, "broker_order_summary.csv", fallback_dirs=("04_export", "03_export"))
    reconciliation_summary = _read_optional_summary(reconciliation_dir, "reconciliation_summary.csv")
    reconciliation_checks = _read_optional_summary(reconciliation_dir, "reconciliation_checks.csv")
    instrument_metadata_summary = _read_optional_summary(instrument_metadata_dir, "instrument_metadata_summary.csv")
    pnl_snapshot = _read_optional_csv(pnl_path)
    open_orders = _read_optional_csv(open_orders_path)
    positions = _read_optional_csv(positions_path)

    report = evaluate_runtime_telemetry(
        scaleup_config,
        export_summary=export_summary,
        reconciliation_summary=reconciliation_summary,
        reconciliation_checks=reconciliation_checks,
        instrument_metadata_summary=instrument_metadata_summary,
        pnl_snapshot=pnl_snapshot,
        open_orders=open_orders,
        positions=positions,
        snapshot_ts_ns=snapshot_ts_ns,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.telemetry.to_csv(out / "runtime_telemetry.csv", index=False)
    report.sources.to_csv(out / "runtime_telemetry_sources.csv", index=False)
    report.checks.to_csv(out / "runtime_telemetry_checks.csv", index=False)
    report.summary.to_csv(out / "runtime_telemetry_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="runtime_telemetry_snapshot",
        parameters={"snapshot_ts_ns": snapshot_ts_ns},
        inputs={
            "scaleup": scaleup_file,
            "export": export_dir,
            "reconciliation": reconciliation_dir,
            "instrument_metadata": instrument_metadata_dir,
            "pnl": pnl_path,
            "open_orders": open_orders_path,
            "positions": positions_path,
        },
    )
    return RuntimeTelemetryReport(report.telemetry, report.sources, report.checks, report.summary, out)


def _telemetry(
    scaleup_config: dict[str, Any],
    *,
    export_summary: pd.DataFrame,
    reconciliation_summary: pd.DataFrame,
    reconciliation_checks: pd.DataFrame,
    instrument_metadata_summary: pd.DataFrame,
    pnl_snapshot: pd.DataFrame,
    open_orders: pd.DataFrame,
    positions: pd.DataFrame,
    snapshot_ts_ns: int | float | None,
) -> pd.DataFrame:
    export = _first_row(export_summary)
    recon = _first_row(reconciliation_summary)
    metadata = _first_row(instrument_metadata_summary)
    scaleup_metadata = scaleup_config.get("instrument_metadata", {}) or {}
    pnl = _last_row(pnl_snapshot)
    orders_sent = _first_number(
        _number(export, "orders"),
        _number(recon, "orders"),
        float(len(open_orders)) if not open_orders.empty else np.nan,
        0.0,
    )
    session_notional = _first_number(
        _number(export, "total_notional"),
        _number(pnl, "session_notional"),
        _number(pnl, "total_notional"),
        0.0,
    )
    total_failed = _first_number(_number(export, "failed_checks"), 0.0) + _failed_checks(reconciliation_checks)
    row = {
        "snapshot_ts_ns": _first_number(snapshot_ts_ns, _number(pnl, "ts_ns"), _number(pnl, "timestamp_ns"), np.nan),
        "target_mode": str(scaleup_config.get("target_mode", "")),
        "scenario_key": str(_first_value(export.get("scenario_key", np.nan), scaleup_config.get("scenario_key", ""))),
        "adapter": str(_first_value(export.get("adapter", np.nan), scaleup_config.get("adapter", ""))),
        "orders_sent": int(orders_sent),
        "session_notional": float(session_notional),
        "realized_pnl": float(_first_number(_number(pnl, "realized_pnl"), _number(pnl, "net_pnl"), _number(pnl, "pnl"), 0.0)),
        "total_failed_component_checks": int(total_failed),
        "unmatched_fills": int(_first_number(_number(recon, "unmatched_fills"), 0.0)),
        "mismatched_orders": int(_first_number(_number(recon, "mismatched_orders"), 0.0)),
        "overfilled_orders": int(_first_number(_number(recon, "overfilled_orders"), 0.0)),
        "worst_adverse_slippage": float(_first_number(_number(recon, "max_adverse_slippage"), 0.0)),
        "instrument_metadata_required": _to_bool(scaleup_metadata.get("required", False)),
        "instrument_metadata_provided": not instrument_metadata_summary.empty,
        "instrument_metadata_passed": _to_bool(metadata.get("passed", False)) if not metadata.empty else False,
        "instrument_parse_coverage": float(_first_number(_number(metadata, "parse_coverage"), np.nan)),
        "min_instrument_parse_coverage": float(
            _first_number(
                _number(metadata, "min_parse_coverage"),
                scaleup_metadata.get("min_parse_coverage", np.nan),
                np.nan,
            )
        ),
        "unparsed_instruments": float(_first_number(_number(metadata, "unparsed_instruments"), np.nan)),
        "open_order_count": int(_active_open_orders(open_orders)),
        "open_order_qty": float(_open_order_qty(open_orders)),
        "gross_position_qty": float(_gross_position_qty(positions)),
        "abs_net_position_qty": float(_abs_net_position_qty(positions)),
    }
    return pd.DataFrame([row])


def _sources(**frames: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": name,
                "provided": not frame.empty,
                "rows": int(len(frame)),
                "columns": ";".join(frame.columns.astype(str).tolist()) if not frame.empty else "",
            }
            for name, frame in frames.items()
        ]
    )


def _checks(row: pd.Series) -> pd.DataFrame:
    checks = [
        _check("scenario_key_present", row["scenario_key"], "not_empty", True, bool(str(row["scenario_key"]).strip()), "scenario_key is missing"),
        _check("adapter_present", row["adapter"], "not_empty", True, bool(str(row["adapter"]).strip()), "adapter is missing"),
    ]
    for column in GUARD_COLUMNS:
        value = row[column]
        present = not pd.isna(value) and (not isinstance(value, str) or bool(value.strip()))
        checks.append(_check(f"{column}_available", value, "present", True, present, f"{column} is unavailable"))
    metadata_required = _to_bool(row.get("instrument_metadata_required", False))
    metadata_provided = _to_bool(row.get("instrument_metadata_provided", False))
    if metadata_required:
        checks.append(
            _check(
                "instrument_metadata_provided",
                metadata_provided,
                "is",
                True,
                metadata_provided,
                "instrument metadata summary is required but was not supplied",
            )
        )
    if metadata_required or metadata_provided:
        metadata_passed = _to_bool(row.get("instrument_metadata_passed", False))
        parse_coverage = _number(row, "instrument_parse_coverage")
        min_coverage = _number(row, "min_instrument_parse_coverage")
        unparsed = _number(row, "unparsed_instruments")
        coverage_ready = not np.isnan(parse_coverage) and not np.isnan(min_coverage) and parse_coverage + 1e-12 >= min_coverage
        unparsed_ready = not np.isnan(unparsed) and unparsed <= 0
        checks.extend(
            [
                _check(
                    "instrument_metadata_passed",
                    metadata_passed,
                    "is",
                    True,
                    metadata_passed,
                    "instrument metadata summary did not pass",
                ),
                _check(
                    "instrument_parse_coverage",
                    parse_coverage,
                    ">=",
                    min_coverage,
                    coverage_ready,
                    "instrument parse coverage is below the required threshold",
                ),
                _check(
                    "unparsed_instruments",
                    unparsed,
                    "<=",
                    0,
                    unparsed_ready,
                    "instrument metadata contains unparsed instruments",
                ),
            ]
        )
    return pd.DataFrame(checks)


def _summary(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "scenario_key": row["scenario_key"],
                "adapter": row["adapter"],
                "orders_sent": int(row["orders_sent"]),
                "session_notional": float(row["session_notional"]),
                "realized_pnl": float(row["realized_pnl"]),
                "failed_checks": failed,
                "recommendation": "feed_runtime_guard" if ready else "fix_telemetry_before_guard",
            }
        ]
    )


def _scaleup_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "scaleup_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"scale-up config not found: {candidate}")
    return candidate


def _read_optional_summary(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        direct = candidate / filename
        if direct.exists():
            candidate = direct
        else:
            candidate = next(
                (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
                direct,
            )
    return _read_optional_csv(candidate)


def _read_optional_csv(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.exists():
        raise FileNotFoundError(f"optional runtime telemetry input not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"optional runtime telemetry input is empty: {candidate}")
    return frame


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _first_row(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[0] if not frame.empty else pd.Series(dtype=object)


def _last_row(frame: pd.DataFrame) -> pd.Series:
    return frame.iloc[-1] if not frame.empty else pd.Series(dtype=object)


def _number(row: pd.Series, column: str) -> float:
    if row.empty or column not in row.index:
        return np.nan
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else np.nan


def _first_number(*values: object) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(number):
            return number
    return np.nan


def _first_value(*values: object) -> object:
    for value in values:
        if not pd.isna(value) and str(value).strip():
            return value
    return ""


def _failed_checks(checks: pd.DataFrame) -> int:
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _active_open_orders(open_orders: pd.DataFrame) -> int:
    if open_orders.empty:
        return 0
    status = open_orders["status"].astype(str).str.lower() if "status" in open_orders.columns else pd.Series(["open"] * len(open_orders))
    open_qty = _open_quantities(open_orders)
    terminal = {"filled", "cancelled", "canceled", "rejected", "expired", "complete", "closed"}
    return int(((~status.isin(terminal)) & (open_qty > 0)).sum())


def _open_order_qty(open_orders: pd.DataFrame) -> float:
    if open_orders.empty:
        return 0.0
    return float(_open_quantities(open_orders).sum())


def _open_quantities(open_orders: pd.DataFrame) -> pd.Series:
    for column in ("open_qty", "leaves_qty", "remaining_qty"):
        if column in open_orders.columns:
            return pd.to_numeric(open_orders[column], errors="coerce").fillna(0.0)
    qty = pd.to_numeric(open_orders["qty"], errors="coerce").fillna(0.0) if "qty" in open_orders.columns else pd.Series([0.0] * len(open_orders))
    filled = pd.to_numeric(open_orders["filled_qty"], errors="coerce").fillna(0.0) if "filled_qty" in open_orders.columns else pd.Series([0.0] * len(open_orders))
    return (qty - filled).clip(lower=0.0)


def _gross_position_qty(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    return float(_position_quantities(positions).abs().sum())


def _abs_net_position_qty(positions: pd.DataFrame) -> float:
    if positions.empty:
        return 0.0
    return float(abs(_position_quantities(positions).sum()))


def _position_quantities(positions: pd.DataFrame) -> pd.Series:
    for column in ("net_qty", "position", "qty"):
        if column in positions.columns:
            return pd.to_numeric(positions[column], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(positions))


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
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
