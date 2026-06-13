from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class SurfaceQualityThresholds:
    min_observations: int = 1
    min_instruments: int = 1
    min_mae_improvement: float = 0.0
    min_relative_mae_improvement: float | None = None
    min_improvement_rate: float | None = None
    max_theo_mae: float | None = None


@dataclass(frozen=True)
class SurfaceQualityReport:
    details: pd.DataFrame
    summary: pd.DataFrame
    checks: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary["all_passed"].map(_to_bool).all()) if not self.summary.empty else False


def read_surface_quality_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "surface_quality_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"surface quality summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"surface quality summary is empty: {candidate}")
    return frame


def surface_quality_review_check(
    summary: pd.DataFrame,
    *,
    required: bool,
    input_dir: str | Path | None,
) -> dict[str, Any] | None:
    if summary.empty and not required:
        return None
    provided = not summary.empty
    passed = bool(summary["all_passed"].map(_to_bool).all()) if provided else False
    reason = "accepted" if passed else "surface_quality_missing"
    if provided and not passed:
        reason = "surface_quality_not_passed"
    return {
        "check": "surface_quality",
        "value": bool(passed),
        "operator": "all_passed",
        "threshold": True,
        "passed": bool(passed),
        "reason": reason,
        "input_dir": str(input_dir or ""),
        "observations": int(summary["observations"].min()) if provided and "observations" in summary else 0,
        "min_mae_improvement": _float(summary["mae_improvement"].min()) if provided else np.nan,
        "min_relative_mae_improvement": _float(summary["relative_mae_improvement"].min()) if provided else np.nan,
    }


def surface_quality_review_parameters(summary: pd.DataFrame, input_dir: str | Path | None) -> dict[str, Any]:
    if summary.empty:
        return {
            "provided": False,
            "input_dir": str(input_dir or ""),
            "accepted": False,
            "observations": 0,
            "min_mae_improvement": None,
            "min_relative_mae_improvement": None,
        }
    return {
        "provided": True,
        "input_dir": str(input_dir or ""),
        "accepted": bool(summary["all_passed"].map(_to_bool).all()),
        "observations": int(summary["observations"].min()) if "observations" in summary else 0,
        "min_mae_improvement": _jsonable(summary["mae_improvement"].min()),
        "min_relative_mae_improvement": _jsonable(summary["relative_mae_improvement"].min()),
    }


def evaluate_surface_quality(
    quotes: pd.DataFrame,
    chain: pd.DataFrame,
    *,
    horizons_ns: Iterable[int],
    thresholds: SurfaceQualityThresholds | None = None,
) -> SurfaceQualityReport:
    thresholds = thresholds or SurfaceQualityThresholds()
    _validate_thresholds(thresholds)
    horizons = [int(horizon) for horizon in horizons_ns]
    if not horizons:
        raise ValueError("horizons_ns must not be empty")
    if any(horizon < 0 for horizon in horizons):
        raise ValueError("horizons_ns values must be non-negative")
    quote_values = _quote_values(quotes)
    chain_values = _chain_values(chain)
    details = _quality_details(quote_values, chain_values, horizons)
    summary = _summary(details)
    checks = _checks(summary, thresholds)
    all_passed = bool(checks["passed"].all()) if not checks.empty else False
    summary["all_passed"] = all_passed
    summary["failed_checks"] = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    summary["recommendation"] = np.where(summary["all_passed"], "surface_model_usable", "improve_surface_before_quoting")
    return SurfaceQualityReport(details=details, summary=summary, checks=checks)


def write_surface_quality_report(
    quotes_path: str | Path,
    chain_path: str | Path,
    *,
    output_dir: str | Path,
    horizons_ns: Iterable[int],
    thresholds: SurfaceQualityThresholds | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> SurfaceQualityReport:
    quotes_file = Path(quotes_path)
    chain_file = Path(chain_path)
    if not quotes_file.exists():
        raise FileNotFoundError(f"surface quotes file not found: {quotes_file}")
    if not chain_file.exists():
        raise FileNotFoundError(f"option chain file not found: {chain_file}")
    quotes = pd.read_csv(quotes_file)
    chain = load_option_chain_csv(
        chain_file,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    ).data
    thresholds = thresholds or SurfaceQualityThresholds()
    horizons = [int(horizon) for horizon in horizons_ns]
    report = evaluate_surface_quality(quotes, chain, horizons_ns=horizons, thresholds=thresholds)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.details.to_csv(out / "surface_quality_details.csv", index=False)
    report.summary.to_csv(out / "surface_quality_summary.csv", index=False)
    report.checks.to_csv(out / "surface_quality_checks.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="surface_quality_report",
        parameters={
            "horizons_ns": horizons,
            "thresholds": asdict(thresholds),
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "market": market,
        },
        inputs={"quotes": quotes_file, "chain": chain_file},
    )
    return SurfaceQualityReport(report.details, report.summary, report.checks, out)


def _quote_values(quotes: pd.DataFrame) -> pd.DataFrame:
    required = ["ts", "instrument_id", "theo", "market_bid", "market_ask"]
    _require(quotes, required, "quotes")
    frame = quotes.copy()
    frame["ts"] = pd.to_numeric(frame["ts"], errors="coerce")
    frame["theo"] = pd.to_numeric(frame["theo"], errors="coerce")
    frame["market_bid"] = pd.to_numeric(frame["market_bid"], errors="coerce")
    frame["market_ask"] = pd.to_numeric(frame["market_ask"], errors="coerce")
    frame["current_mid"] = 0.5 * (frame["market_bid"] + frame["market_ask"])
    keep_cols = [
        col
        for col in ["ts", "expiry", "instrument_id", "strike", "option_type", "theo", "market_bid", "market_ask", "current_mid"]
        if col in frame.columns
    ]
    values = frame[keep_cols].dropna(subset=["ts", "instrument_id", "theo", "current_mid"]).copy()
    if values.empty:
        return values
    return (
        values.sort_values(["ts", "instrument_id"])
        .groupby(["ts", "instrument_id"], as_index=False, dropna=False)
        .first()
    )


def _chain_values(chain: pd.DataFrame) -> pd.DataFrame:
    required = ["ts", "strike", "call_bid", "call_ask", "put_bid", "put_ask"]
    _require(chain, required, "chain")
    rows = []
    for row in chain.itertuples(index=False):
        strike = float(row.strike)
        strike_label = str(strike).replace(".", "_")
        rows.extend(
            [
                {
                    "ts": int(row.ts),
                    "instrument_id": f"CALL_{strike_label}",
                    "future_mid": 0.5 * (float(row.call_bid) + float(row.call_ask)),
                },
                {
                    "ts": int(row.ts),
                    "instrument_id": f"PUT_{strike_label}",
                    "future_mid": 0.5 * (float(row.put_bid) + float(row.put_ask)),
                },
            ]
        )
    if not rows:
        return pd.DataFrame(columns=["ts", "instrument_id", "future_mid"])
    return pd.DataFrame(rows).sort_values(["instrument_id", "ts"]).reset_index(drop=True)


def _quality_details(quotes: pd.DataFrame, chain: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    if quotes.empty:
        return pd.DataFrame(
            columns=[
                "horizon_ns",
                "ts",
                "target_ts",
                "instrument_id",
                "theo",
                "current_mid",
                "future_mid",
                "theo_abs_error",
                "mid_abs_error",
                "mae_improvement",
                "relative_error_reduction",
                "theo_beats_mid",
            ]
        )
    rows = []
    chain = chain.sort_values(["instrument_id", "ts"])
    for horizon in horizons:
        target = quotes.copy()
        target["horizon_ns"] = int(horizon)
        target["target_ts"] = target["ts"].astype("int64") + int(horizon)
        joined_parts = []
        for instrument_id, group in target.groupby("instrument_id", sort=False):
            chain_group = chain.loc[chain["instrument_id"] == instrument_id, ["ts", "future_mid"]]
            joined = pd.merge_asof(
                group.sort_values("target_ts"),
                chain_group.sort_values("ts"),
                left_on="target_ts",
                right_on="ts",
                direction="forward",
                suffixes=("", "_future"),
            )
            joined_parts.append(joined)
        if joined_parts:
            rows.append(pd.concat(joined_parts, ignore_index=True, sort=False))
    if not rows:
        return _quality_details(pd.DataFrame(columns=quotes.columns), chain, horizons)
    out = pd.concat(rows, ignore_index=True, sort=False)
    out["theo_abs_error"] = (out["theo"].astype(float) - out["future_mid"].astype(float)).abs()
    out["mid_abs_error"] = (out["current_mid"].astype(float) - out["future_mid"].astype(float)).abs()
    out["mae_improvement"] = out["mid_abs_error"] - out["theo_abs_error"]
    out["relative_error_reduction"] = np.where(
        out["mid_abs_error"] > 0,
        out["mae_improvement"] / out["mid_abs_error"],
        np.nan,
    )
    out["theo_beats_mid"] = out["theo_abs_error"] < out["mid_abs_error"]
    return out.sort_values(["horizon_ns", "ts", "instrument_id"]).reset_index(drop=True)


def _summary(details: pd.DataFrame) -> pd.DataFrame:
    if details.empty:
        return pd.DataFrame(
            [
                {
                    "horizon_ns": np.nan,
                    "observations": 0,
                    "unmatched_observations": 0,
                    "instruments": 0,
                    "theo_mae": np.nan,
                    "mid_mae": np.nan,
                    "mae_improvement": np.nan,
                    "relative_mae_improvement": np.nan,
                    "improvement_rate": np.nan,
                }
            ]
        )
    working = details.copy()
    working["matched"] = working["future_mid"].notna()
    matched = working.loc[working["matched"]].copy()
    if matched.empty:
        return (
            working.groupby("horizon_ns", dropna=False)
            .agg(
                observations=("matched", "sum"),
                unmatched_observations=("matched", lambda s: int((~s).sum())),
                instruments=("instrument_id", lambda s: 0),
            )
            .reset_index()
            .assign(
                theo_mae=np.nan,
                mid_mae=np.nan,
                mae_improvement=np.nan,
                relative_mae_improvement=np.nan,
                improvement_rate=np.nan,
            )
        )
    summary = (
        matched.groupby("horizon_ns", dropna=False)
        .agg(
            observations=("future_mid", "size"),
            instruments=("instrument_id", "nunique"),
            theo_mae=("theo_abs_error", "mean"),
            mid_mae=("mid_abs_error", "mean"),
            improvement_rate=("theo_beats_mid", lambda s: float(s.mean())),
        )
        .reset_index()
    )
    unmatched = (
        working.groupby("horizon_ns", dropna=False)["matched"]
        .apply(lambda s: int((~s).sum()))
        .rename("unmatched_observations")
        .reset_index()
    )
    summary = summary.merge(unmatched, on="horizon_ns", how="left")
    summary["mae_improvement"] = summary["mid_mae"] - summary["theo_mae"]
    summary["relative_mae_improvement"] = np.where(
        summary["mid_mae"] > 0,
        summary["mae_improvement"] / summary["mid_mae"],
        np.nan,
    )
    return summary[
        [
            "horizon_ns",
            "observations",
            "unmatched_observations",
            "instruments",
            "theo_mae",
            "mid_mae",
            "mae_improvement",
            "relative_mae_improvement",
            "improvement_rate",
        ]
    ]


def _checks(summary: pd.DataFrame, thresholds: SurfaceQualityThresholds) -> pd.DataFrame:
    if summary.empty:
        summary = _summary(pd.DataFrame())
    rows = [
        _check(
            "observations",
            int(pd.to_numeric(summary["observations"], errors="coerce").min()),
            ">=",
            thresholds.min_observations,
            int(pd.to_numeric(summary["observations"], errors="coerce").min()) >= thresholds.min_observations,
            "not enough surface quality observations at every horizon",
        ),
        _check(
            "instruments",
            int(pd.to_numeric(summary["instruments"], errors="coerce").min()),
            ">=",
            thresholds.min_instruments,
            int(pd.to_numeric(summary["instruments"], errors="coerce").min()) >= thresholds.min_instruments,
            "not enough instruments covered at every horizon",
        ),
        _numeric_check(summary, "mae_improvement", ">=", thresholds.min_mae_improvement, reducer="min"),
    ]
    if thresholds.min_relative_mae_improvement is not None:
        rows.append(
            _numeric_check(
                summary,
                "relative_mae_improvement",
                ">=",
                thresholds.min_relative_mae_improvement,
                reducer="min",
            )
        )
    if thresholds.min_improvement_rate is not None:
        rows.append(
            _numeric_check(
                summary,
                "improvement_rate",
                ">=",
                thresholds.min_improvement_rate,
                reducer="min",
            )
        )
    if thresholds.max_theo_mae is not None:
        rows.append(_numeric_check(summary, "theo_mae", "<=", thresholds.max_theo_mae, reducer="max"))
    return pd.DataFrame(rows)


def _numeric_check(
    summary: pd.DataFrame,
    column: str,
    operator: str,
    threshold: float,
    *,
    reducer: str,
) -> dict[str, Any]:
    values = pd.to_numeric(summary[column], errors="coerce") if column in summary.columns else pd.Series(dtype=float)
    value = float(values.min(skipna=True) if reducer == "min" else values.max(skipna=True))
    missing = np.isnan(value)
    if operator == ">=":
        passed = (not missing) and value >= float(threshold)
    elif operator == "<=":
        passed = (not missing) and value <= float(threshold)
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{column} is unavailable"
    elif not passed:
        reason = f"{column} {value:.6g} failed {operator} {float(threshold):.6g}"
    return _check(column, value, operator, float(threshold), passed, reason)


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


def _validate_thresholds(thresholds: SurfaceQualityThresholds) -> None:
    if thresholds.min_observations <= 0:
        raise ValueError("min_observations must be positive")
    if thresholds.min_instruments <= 0:
        raise ValueError("min_instruments must be positive")
    if thresholds.min_relative_mae_improvement is not None and thresholds.min_relative_mae_improvement < -1:
        raise ValueError("min_relative_mae_improvement must be >= -1")
    if thresholds.min_improvement_rate is not None and not 0 <= thresholds.min_improvement_rate <= 1:
        raise ValueError("min_improvement_rate must be between 0 and 1")
    if thresholds.max_theo_mae is not None and thresholds.max_theo_mae < 0:
        raise ValueError("max_theo_mae must be non-negative")


def _require(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _to_bool(value: object) -> bool:
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


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    return value
