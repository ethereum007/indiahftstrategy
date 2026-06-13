from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ProofRefreshThresholds:
    require_calibrated_replay_when_drift_fails: bool = False
    expected_strategy: str | None = None
    expected_market: str | None = None


@dataclass(frozen=True)
class ProofRefreshReport:
    decision: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_proof_refresh(
    *,
    drift_summary: pd.DataFrame,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None = None,
    calibrated_replay_summary: pd.DataFrame | None = None,
    thresholds: ProofRefreshThresholds | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_passed = _frame_bool(drift_summary, "passed")
    baseline_passed = _frame_bool(baseline_proof_summary, "all_passed")
    latest_available = latest_proof_summary is not None and not latest_proof_summary.empty
    latest_passed = _frame_bool(latest_proof_summary, "all_passed") if latest_available else False
    calibrated_available = calibrated_replay_summary is not None and not calibrated_replay_summary.empty
    calibrated_ready = _frame_bool(calibrated_replay_summary, "ready") if calibrated_available else False
    calibrated_strategy = _frame_str(calibrated_replay_summary, "strategy") if calibrated_available else ""
    identities = _input_identities(
        baseline_proof_summary=baseline_proof_summary,
        latest_proof_summary=latest_proof_summary if latest_available else None,
        calibrated_replay_summary=calibrated_replay_summary if calibrated_available else None,
    )
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    mixed_identity = bool((len(strategies) > 1) or (len(markets) > 1))

    checks = _checks(
        drift_passed=drift_passed,
        baseline_passed=baseline_passed,
        latest_available=latest_available,
        latest_passed=latest_passed,
        calibrated_available=calibrated_available,
        calibrated_ready=calibrated_ready,
        calibrated_strategy=calibrated_strategy,
        identities=identities,
        thresholds=thresholds,
    )
    failed_checks = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed_checks == 0
    proof_source = _proof_source(drift_passed, baseline_passed, latest_passed, ready)
    recommendation = _recommendation(ready, drift_passed)
    decision = pd.DataFrame(
        [
            {
                "action": recommendation,
                "proof_source": proof_source,
                "strategy": _single_identity(strategies),
                "market": _single_identity(markets),
                "mixed_identity": mixed_identity,
                "fresh_proof_required": not drift_passed,
                "reason": _reason(ready, drift_passed, latest_available, latest_passed, calibrated_ready),
            }
        ]
    )
    summary = pd.DataFrame(
        [
            {
                "ready": ready,
                "drift_passed": drift_passed,
                "fresh_proof_required": not drift_passed,
                "proof_source": proof_source,
                "baseline_proof_passed": baseline_passed,
                "latest_proof_available": latest_available,
                "latest_proof_passed": latest_passed,
                "calibrated_replay_required": (not drift_passed)
                and thresholds.require_calibrated_replay_when_drift_fails,
                "calibrated_replay_available": calibrated_available,
                "calibrated_replay_ready": calibrated_ready,
                "strategy": _single_identity(strategies),
                "strategy_count": int(len(strategies)),
                "missing_strategy_sources": _missing_identity_count(identities, "strategy"),
                "expected_strategy": _strategy_key(thresholds.expected_strategy)
                if thresholds.expected_strategy is not None
                else "",
                "market": _single_identity(markets),
                "market_count": int(len(markets)),
                "missing_market_sources": _missing_identity_count(identities, "market"),
                "expected_market": _identity_key(thresholds.expected_market)
                if thresholds.expected_market is not None
                else "",
                "mixed_identity": mixed_identity,
                "failed_checks": failed_checks,
                "recommendation": recommendation,
            }
        ]
    )
    return ProofRefreshReport(decision=decision, checks=checks, summary=summary)


def write_proof_refresh_report(
    *,
    drift_path: str | Path,
    baseline_proof_path: str | Path,
    output_dir: str | Path,
    latest_proof_path: str | Path | None = None,
    calibrated_replay_path: str | Path | None = None,
    thresholds: ProofRefreshThresholds | None = None,
) -> ProofRefreshReport:
    thresholds = thresholds or ProofRefreshThresholds()
    drift_file = _summary_path(drift_path, "fill_model_drift_summary.csv")
    baseline_file = _summary_path(baseline_proof_path, "proof_summary.csv")
    latest_file = _optional_summary_path(latest_proof_path, "proof_summary.csv")
    calibrated_file = _optional_summary_path(calibrated_replay_path, "calibrated_replay_summary.csv")
    report = evaluate_proof_refresh(
        drift_summary=_read_summary(drift_file),
        baseline_proof_summary=_read_summary(baseline_file),
        latest_proof_summary=_read_summary(latest_file) if latest_file is not None else None,
        calibrated_replay_summary=_read_summary(calibrated_file) if calibrated_file is not None else None,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.decision.to_csv(out / "proof_refresh_decision.csv", index=False)
    report.checks.to_csv(out / "proof_refresh_checks.csv", index=False)
    report.summary.to_csv(out / "proof_refresh_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="proof_refresh_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs={
            "fill_model_drift": drift_file,
            "baseline_proof": baseline_file,
            "latest_proof": latest_file,
            "calibrated_replay": calibrated_file,
        },
    )
    return ProofRefreshReport(report.decision, report.checks, report.summary, out)


def _checks(
    *,
    drift_passed: bool,
    baseline_passed: bool,
    latest_available: bool,
    latest_passed: bool,
    calibrated_available: bool,
    calibrated_ready: bool,
    calibrated_strategy: str,
    identities: pd.DataFrame,
    thresholds: ProofRefreshThresholds,
) -> pd.DataFrame:
    if drift_passed:
        checks = [
            _check(
                "reusable_proof_passed",
                baseline_passed or latest_passed,
                "is",
                True,
                baseline_passed or latest_passed,
                "neither baseline nor latest proof passed under reusable fill-model assumptions",
            )
        ]
    else:
        checks = [
            _check(
                "latest_proof_available",
                latest_available,
                "is",
                True,
                latest_available,
                "fill-model drift failed, so a fresh/latest proof report is required",
            ),
            _check(
                "latest_proof_passed",
                latest_passed,
                "is",
                True,
                latest_passed,
                "latest proof report did not pass",
            ),
        ]
        if thresholds.require_calibrated_replay_when_drift_fails:
            checks.extend(
                [
                    _check(
                        "calibrated_replay_available",
                        calibrated_available,
                        "is",
                        True,
                        calibrated_available,
                        "fill-model drift failed, so a calibrated replay plan is required",
                    ),
                    _check(
                        "calibrated_replay_ready",
                        calibrated_ready,
                        "is",
                        True,
                        calibrated_ready,
                        "calibrated replay plan is not ready",
                    ),
                ]
            )
        if thresholds.expected_strategy is not None:
            expected = _strategy_key(thresholds.expected_strategy)
            actual = _strategy_key(calibrated_strategy) if calibrated_strategy else ""
            checks.append(
                _check(
                    "calibrated_replay_strategy_matches",
                    actual,
                    "==",
                    expected,
                    bool(actual) and actual == expected,
                    "calibrated replay plan strategy does not match expected strategy",
                )
            )

    checks.extend(_identity_checks(identities, thresholds))
    return pd.DataFrame(checks)


def _identity_checks(identities: pd.DataFrame, thresholds: ProofRefreshThresholds) -> list[dict[str, object]]:
    strategies = _identity_values(identities, "strategy", normalizer=_strategy_key)
    markets = _identity_values(identities, "market", normalizer=_identity_key)
    rows = [
        _check(
            "same_strategy",
            ";".join(sorted(strategies)) if strategies else "",
            "count<=",
            1,
            len(strategies) <= 1,
            "proof refresh inputs mix strategy identities",
        ),
        _check(
            "same_market",
            ";".join(sorted(markets)) if markets else "",
            "count<=",
            1,
            len(markets) <= 1,
            "proof refresh inputs mix market identities",
        ),
    ]
    if thresholds.expected_strategy is not None:
        expected = _strategy_key(thresholds.expected_strategy)
        rows.append(
            _check(
                "expected_strategy",
                ";".join(sorted(strategies)) if strategies else "",
                "==",
                expected,
                not strategies or strategies == {expected},
                "available proof refresh strategies do not match expected strategy",
            )
        )
    if thresholds.expected_market is not None:
        expected = _identity_key(thresholds.expected_market)
        rows.append(
            _check(
                "expected_market",
                ";".join(sorted(markets)) if markets else "",
                "==",
                expected,
                not markets or markets == {expected},
                "available proof refresh markets do not match expected market",
            )
        )
    return rows


def _proof_source(drift_passed: bool, baseline_passed: bool, latest_passed: bool, ready: bool) -> str:
    if not ready:
        return "none"
    if not drift_passed:
        return "latest"
    if baseline_passed:
        return "baseline"
    return "latest" if latest_passed else "none"


def _recommendation(ready: bool, drift_passed: bool) -> str:
    if ready and drift_passed:
        return "reuse_existing_proof"
    if ready:
        return "use_latest_calibrated_proof"
    if drift_passed:
        return "repair_proof_before_promotion"
    return "rerun_calibrated_proof_before_promotion"


def _reason(
    ready: bool,
    drift_passed: bool,
    latest_available: bool,
    latest_passed: bool,
    calibrated_ready: bool,
) -> str:
    if ready and drift_passed:
        return "fill-model drift passed, so reusable proof assumptions remain valid"
    if ready:
        return "fill-model drift failed, but latest calibrated proof evidence passed"
    if drift_passed:
        return "fill-model drift passed, but no passing proof report is available"
    if not latest_available:
        return "fill-model drift failed and no latest proof report was supplied"
    if not latest_passed:
        return "fill-model drift failed and latest proof report did not pass"
    if not calibrated_ready:
        return "fill-model drift failed and calibrated replay plan is not ready"
    return "proof refresh gate has unresolved failed checks"


def _summary_path(path: str | Path, filename: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / filename
    if not candidate.exists():
        raise FileNotFoundError(f"summary artifact not found: {candidate}")
    return candidate


def _optional_summary_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    return _summary_path(path, filename)


def _read_summary(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"summary artifact is empty: {path}")
    return frame


def _frame_bool(frame: pd.DataFrame | None, column: str) -> bool:
    if frame is None or frame.empty or column not in frame.columns:
        return False
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _frame_str(frame: pd.DataFrame | None, column: str) -> str:
    if frame is None or frame.empty or column not in frame.columns:
        return ""
    value = frame.iloc[0][column]
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _input_identities(
    *,
    baseline_proof_summary: pd.DataFrame,
    latest_proof_summary: pd.DataFrame | None,
    calibrated_replay_summary: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = [
        _identity_row("baseline_proof", baseline_proof_summary),
    ]
    if latest_proof_summary is not None and not latest_proof_summary.empty:
        rows.append(_identity_row("latest_proof", latest_proof_summary))
    if calibrated_replay_summary is not None and not calibrated_replay_summary.empty:
        rows.append(_identity_row("calibrated_replay", calibrated_replay_summary))
    return pd.DataFrame(rows)


def _identity_row(source: str, frame: pd.DataFrame) -> dict[str, str]:
    row = frame.iloc[0] if frame is not None and not frame.empty else pd.Series(dtype=object)
    return {
        "source": source,
        "strategy": _strategy_key(_first_identity(row, ("strategy", "strategy_name", "strategy_id"))),
        "market": _identity_key(_first_identity(row, ("market", "market_profile", "market_name", "market_id"))),
    }


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


def _single_identity(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else ""


def _first_identity(row: pd.Series, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _text(row, key)
        if value:
            return value
    return ""


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row or pd.isna(row[column]):
        return ""
    return str(row[column]).strip()


def _strategy_key(strategy: object) -> str:
    key = _identity_key(strategy)
    aliases = {
        "lead_lag": "leadlag",
        "lead_lag_taker": "leadlag",
        "leadlag_taker": "leadlag",
        "leadlag_replay": "leadlag",
        "microprice": "imbalance",
        "microprice_imbalance": "imbalance",
        "order_book_imbalance": "imbalance",
        "obi": "imbalance",
        "surface": "surface_mm",
        "surface_market_making": "surface_mm",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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
