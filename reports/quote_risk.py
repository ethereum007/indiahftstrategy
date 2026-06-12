from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class QuoteRiskThresholds:
    min_quotes: int = 1
    min_instruments: int = 1
    max_marketable_quotes: int = 0
    min_quote_edge: float = 0.0
    min_bid_share: float | None = 0.25
    max_bid_share: float | None = 0.75
    max_market_spread_ticks: float | None = None
    max_quotes_per_instrument: int | None = None


@dataclass(frozen=True)
class QuoteRiskReport:
    summary: pd.DataFrame
    checks: pd.DataFrame
    by_instrument: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["all_passed"]) if not self.summary.empty else False


def read_quote_risk_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "quote_risk_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"quote risk summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"quote risk summary is empty: {candidate}")
    return frame


def quote_risk_review_check(
    summary: pd.DataFrame,
    *,
    required: bool,
    input_dir: str | Path | None,
) -> dict[str, Any] | None:
    if summary.empty and not required:
        return None
    provided = not summary.empty
    row = summary.iloc[0] if provided else pd.Series(dtype=object)
    accepted = _to_bool(row.get("all_passed", False)) if provided else False
    passed = provided and accepted
    reason = "accepted" if passed else "quote_risk_review_missing"
    if provided and not accepted:
        reason = "quote_risk_review_not_passed"
    return {
        "check": "quote_risk_review",
        "value": bool(accepted),
        "operator": "all_passed",
        "threshold": True,
        "passed": bool(passed),
        "reason": reason,
        "input_dir": str(input_dir or ""),
        "quotes": _int(row, "quotes") if provided else 0,
        "marketable_quotes": _int(row, "marketable_quotes") if provided else 0,
        "min_quote_edge": _float(row, "min_quote_edge") if provided else 0.0,
    }


def quote_risk_review_parameters(summary: pd.DataFrame, input_dir: str | Path | None) -> dict[str, Any]:
    if summary.empty:
        return {
            "provided": False,
            "input_dir": str(input_dir or ""),
            "accepted": False,
            "quotes": 0,
            "marketable_quotes": 0,
            "min_quote_edge": 0.0,
        }
    row = summary.iloc[0]
    return {
        "provided": True,
        "input_dir": str(input_dir or ""),
        "accepted": _to_bool(row.get("all_passed", False)),
        "quotes": _int(row, "quotes"),
        "marketable_quotes": _int(row, "marketable_quotes"),
        "min_quote_edge": _float(row, "min_quote_edge"),
    }


def evaluate_quote_risk(
    quotes: pd.DataFrame,
    *,
    thresholds: QuoteRiskThresholds | None = None,
) -> QuoteRiskReport:
    thresholds = thresholds or QuoteRiskThresholds()
    frame = _normalize_quotes(quotes)
    summary = _summary(frame)
    by_instrument = _by_instrument(frame)
    checks = _checks(summary.iloc[0], thresholds)
    summary["all_passed"] = bool(checks["passed"].all()) if not checks.empty else False
    return QuoteRiskReport(summary=summary, checks=checks, by_instrument=by_instrument)


def write_quote_risk_report(
    quotes_path: str | Path,
    *,
    output_dir: str | Path,
    thresholds: QuoteRiskThresholds | None = None,
    data_readiness_comparison_dir: str | Path | None = None,
    require_data_readiness_comparison: bool = False,
) -> QuoteRiskReport:
    quotes_file = Path(quotes_path)
    if not quotes_file.exists():
        raise FileNotFoundError(f"surface quotes file not found: {quotes_file}")
    quotes = pd.read_csv(quotes_file)
    thresholds = thresholds or QuoteRiskThresholds()
    report = evaluate_quote_risk(quotes, thresholds=thresholds)
    summary = report.summary.copy()
    checks = report.checks.copy()
    comparison_summary = _read_data_readiness_comparison_summary(data_readiness_comparison_dir)
    comparison_check = _data_readiness_comparison_check(
        comparison_summary,
        required=require_data_readiness_comparison,
        input_dir=data_readiness_comparison_dir,
    )
    if comparison_check is not None:
        checks = pd.concat([pd.DataFrame([comparison_check]), checks], ignore_index=True)
        summary["all_passed"] = bool(checks["passed"].all())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "quote_risk_summary.csv", index=False)
    checks.to_csv(out / "quote_risk_checks.csv", index=False)
    report.by_instrument.to_csv(out / "quote_risk_by_instrument.csv", index=False)
    inputs: dict[str, Any] = {"quotes": quotes_file}
    if data_readiness_comparison_dir is not None:
        inputs["data_readiness_comparison"] = Path(data_readiness_comparison_dir)
    write_experiment_manifest(
        out,
        run_type="quote_risk_report",
        parameters={
            "thresholds": asdict(thresholds),
            "require_data_readiness_comparison": bool(require_data_readiness_comparison),
            "data_readiness_comparison": _comparison_parameters(
                comparison_summary,
                data_readiness_comparison_dir,
            ),
        },
        inputs=inputs,
    )
    return QuoteRiskReport(summary, checks, report.by_instrument, out)


def _normalize_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    required = ["instrument_id", "side", "price", "qty"]
    missing = [col for col in required if col not in quotes.columns]
    if missing:
        raise ValueError(f"quotes missing required columns: {missing}")
    frame = quotes.copy()
    if "marketable" not in frame.columns:
        frame["marketable"] = False
    frame["marketable"] = frame["marketable"].map(_to_bool)
    if "quote_edge" not in frame.columns:
        if "theo" not in frame.columns:
            frame["quote_edge"] = np.nan
        else:
            frame["quote_edge"] = np.where(
                frame["side"].astype(float) > 0,
                frame["theo"].astype(float) - frame["price"].astype(float),
                frame["price"].astype(float) - frame["theo"].astype(float),
            )
    if "market_spread_ticks" not in frame.columns:
        frame["market_spread_ticks"] = np.nan
    return frame


def _summary(frame: pd.DataFrame) -> pd.DataFrame:
    quote_count = int(len(frame))
    bid_quotes = int((frame["side"].astype(float) > 0).sum()) if quote_count else 0
    ask_quotes = int((frame["side"].astype(float) < 0).sum()) if quote_count else 0
    snapshot_count = (
        int(frame[[col for col in ("ts", "expiry") if col in frame.columns]].drop_duplicates().shape[0])
        if quote_count and any(col in frame.columns for col in ("ts", "expiry"))
        else 0
    )
    if "ts" not in frame.columns and "expiry" in frame.columns and quote_count:
        snapshot_count = int(frame[["expiry"]].drop_duplicates().shape[0])
    return pd.DataFrame(
        [
            {
                "snapshots": snapshot_count,
                "quotes": quote_count,
                "instruments": int(frame["instrument_id"].nunique()) if quote_count else 0,
                "bid_quotes": bid_quotes,
                "ask_quotes": ask_quotes,
                "bid_share": bid_quotes / quote_count if quote_count else np.nan,
                "marketable_quotes": int(frame["marketable"].sum()) if quote_count else 0,
                "min_quote_edge": float(pd.to_numeric(frame["quote_edge"], errors="coerce").min(skipna=True))
                if quote_count
                else np.nan,
                "avg_quote_edge": float(pd.to_numeric(frame["quote_edge"], errors="coerce").mean(skipna=True))
                if quote_count
                else np.nan,
                "max_market_spread_ticks": float(
                    pd.to_numeric(frame["market_spread_ticks"], errors="coerce").max(skipna=True)
                )
                if quote_count
                else np.nan,
                "max_quotes_per_instrument": int(frame.groupby("instrument_id").size().max()) if quote_count else 0,
            }
        ]
    )


def _by_instrument(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "instrument_id",
                "quotes",
                "bid_quotes",
                "ask_quotes",
                "marketable_quotes",
                "min_quote_edge",
                "max_market_spread_ticks",
            ]
        )
    working = frame.copy()
    working["is_bid"] = working["side"].astype(float) > 0
    working["is_ask"] = working["side"].astype(float) < 0
    return (
        working.groupby("instrument_id", dropna=False)
        .agg(
            quotes=("instrument_id", "size"),
            bid_quotes=("is_bid", "sum"),
            ask_quotes=("is_ask", "sum"),
            marketable_quotes=("marketable", "sum"),
            min_quote_edge=("quote_edge", "min"),
            max_market_spread_ticks=("market_spread_ticks", "max"),
        )
        .reset_index()
    )


def _checks(row: pd.Series, thresholds: QuoteRiskThresholds) -> pd.DataFrame:
    rows = [
        _check(row, "quotes", row["quotes"], ">=", thresholds.min_quotes),
        _check(row, "instruments", row["instruments"], ">=", thresholds.min_instruments),
        _check(row, "marketable_quotes", row["marketable_quotes"], "<=", thresholds.max_marketable_quotes),
        _check(row, "min_quote_edge", row["min_quote_edge"], ">=", thresholds.min_quote_edge),
    ]
    if thresholds.min_bid_share is not None:
        rows.append(_check(row, "bid_share_min", row["bid_share"], ">=", thresholds.min_bid_share))
    if thresholds.max_bid_share is not None:
        rows.append(_check(row, "bid_share_max", row["bid_share"], "<=", thresholds.max_bid_share))
    if thresholds.max_market_spread_ticks is not None:
        rows.append(
            _check(
                row,
                "max_market_spread_ticks",
                row["max_market_spread_ticks"],
                "<=",
                thresholds.max_market_spread_ticks,
            )
        )
    if thresholds.max_quotes_per_instrument is not None:
        rows.append(
            _check(
                row,
                "max_quotes_per_instrument",
                row["max_quotes_per_instrument"],
                "<=",
                thresholds.max_quotes_per_instrument,
            )
        )
    return pd.DataFrame(rows)


def _read_data_readiness_comparison_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "data_readiness_comparison_summary.csv"
    if not candidate.exists():
        raise FileNotFoundError(f"data readiness comparison summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"data readiness comparison summary is empty: {candidate}")
    return frame


def _data_readiness_comparison_check(
    summary: pd.DataFrame,
    *,
    required: bool,
    input_dir: str | Path | None,
) -> dict[str, Any] | None:
    if summary.empty and not required:
        return None
    provided = not summary.empty
    row = summary.iloc[0] if provided else pd.Series(dtype=object)
    accepted = _to_bool(row.get("accepted", False)) if provided else False
    passed = provided and accepted
    reason = "accepted" if passed else "data_readiness_comparison_missing"
    if provided and not accepted:
        reason = "data_readiness_comparison_not_accepted"
    return {
        "check": "data_readiness_comparison",
        "value": bool(accepted),
        "operator": "accepted",
        "threshold": True,
        "passed": bool(passed),
        "reason": reason,
        "input_dir": str(input_dir or ""),
        "failed_checks": _int(row, "total_failed_checks") if provided else 1,
        "recommendation": str(row.get("recommendation", reason)) if provided else reason,
    }


def _comparison_parameters(summary: pd.DataFrame, input_dir: str | Path | None) -> dict[str, Any]:
    if summary.empty:
        return {
            "provided": False,
            "input_dir": str(input_dir or ""),
            "accepted": False,
            "dataset_count": 0,
            "ready_rate": 0.0,
            "failed_checks": 0,
            "recommendation": "",
        }
    row = summary.iloc[0]
    return {
        "provided": True,
        "input_dir": str(input_dir or ""),
        "accepted": _to_bool(row.get("accepted", False)),
        "dataset_count": _int(row, "dataset_count"),
        "ready_rate": _float(row, "ready_rate"),
        "failed_checks": _int(row, "total_failed_checks"),
        "recommendation": str(row.get("recommendation", "")),
    }


def _check(
    row: pd.Series,
    name: str,
    value: float | int,
    operator: str,
    threshold: float | int,
) -> dict[str, float | int | str | bool]:
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
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _to_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _float(row: pd.Series, column: str) -> float:
    try:
        return float(row.get(column, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _int(row: pd.Series, column: str) -> int:
    try:
        return int(float(row.get(column, 0)))
    except (TypeError, ValueError):
        return 0
