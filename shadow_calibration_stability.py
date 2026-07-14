from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


SESSION_REQUIRED_COLUMNS = (
    "calibration_receipt_id",
    "session_id",
    "strategy",
    "market",
    "target_mode",
    "provider",
    "transport",
    "exchange",
    "adapter",
    "evidence_class",
    "calibration_contract_sha256",
    "accepted_intent_count",
    "observation_count",
)
HORIZON_REQUIRED_COLUMNS = (
    "calibration_receipt_id",
    "session_id",
    "requested_horizon_ns",
    "action_group",
    "coverage_ratio",
    "mean_directional_mid_move_ticks",
    "mean_directional_microprice_move_ticks",
    "mean_touch_markout_ticks",
    "adverse_selection_rate",
)
COST_REQUIRED_COLUMNS = (
    "calibration_receipt_id",
    "session_id",
    "requested_horizon_ns",
    "action_group",
    "cost_scenario",
    "cost_model_version",
    "reference_status",
    "cost_break_even_rate",
    "mean_round_trip_cost_ticks",
    "mean_break_even_surplus_ticks",
)
HORIZON_STABILITY_COLUMNS = (
    "requested_horizon_ns",
    "action_group",
    "session_count",
    "minimum_coverage_ratio",
    "maximum_coverage_ratio",
    "coverage_ratio_range",
    "mean_directional_mid_move_ticks",
    "minimum_directional_mid_move_ticks",
    "maximum_directional_mid_move_ticks",
    "directional_mid_move_range_ticks",
    "directional_sign_count",
    "directional_sign_consistent",
    "mean_directional_microprice_move_ticks",
    "mean_touch_markout_ticks",
    "minimum_adverse_selection_rate",
    "maximum_adverse_selection_rate",
    "adverse_selection_rate_range",
    "coverage_stable",
    "directional_response_stable",
    "adverse_selection_stable",
    "stable",
)
COST_STABILITY_COLUMNS = (
    "requested_horizon_ns",
    "action_group",
    "cost_scenario",
    "cost_model_version",
    "reference_status",
    "session_count",
    "minimum_cost_break_even_rate",
    "maximum_cost_break_even_rate",
    "cost_break_even_rate_range",
    "minimum_round_trip_cost_ticks",
    "maximum_round_trip_cost_ticks",
    "round_trip_cost_range_ticks",
    "mean_break_even_surplus_ticks",
    "cost_break_even_stable",
    "round_trip_cost_stable",
    "stable",
)
CHECK_COLUMNS = (
    "check",
    "component",
    "value",
    "operator",
    "threshold",
    "passed",
    "reason",
)


class ShadowCalibrationStabilityError(ValueError):
    """Raised when a calibration cohort violates its structural contract."""


@dataclass(frozen=True)
class ShadowCalibrationStabilityConfig:
    min_sessions: int = 2
    min_session_coverage_ratio: float = 0.5
    max_horizon_coverage_range: float = 0.25
    max_directional_mid_range_ticks: float = 2.0
    require_directional_sign_consistency: bool = True
    max_adverse_selection_rate_range: float = 0.25
    max_cost_break_even_rate_range: float = 0.25
    max_round_trip_cost_range_ticks: float = 0.25


@dataclass(frozen=True)
class ShadowCalibrationStabilityResult:
    sessions: pd.DataFrame
    horizon_stability: pd.DataFrame
    cost_stability: pd.DataFrame
    checks: pd.DataFrame
    stable: bool
    failed_check_count: int
    instability_reason: str


def evaluate_shadow_calibration_stability(
    sessions: pd.DataFrame,
    horizon_metrics: pd.DataFrame,
    cost_metrics: pd.DataFrame,
    *,
    config: ShadowCalibrationStabilityConfig | None = None,
) -> ShadowCalibrationStabilityResult:
    config = config or ShadowCalibrationStabilityConfig()
    _validate_config(config)
    normalized_sessions = _validated_sessions(sessions)
    normalized_horizons = _validated_horizons(
        horizon_metrics,
        normalized_sessions,
    )
    normalized_costs = _validated_costs(
        cost_metrics,
        normalized_sessions,
    )
    horizon_stability = _horizon_stability(normalized_horizons, config)
    cost_stability = _cost_stability(normalized_costs, config)
    checks = _checks(
        normalized_sessions,
        horizon_stability,
        cost_stability,
        config,
    )
    failed = checks.loc[~checks["passed"].map(_explicit_true)]
    failed_count = len(failed)
    reason = (
        ""
        if failed.empty
        else ";".join(failed["check"].astype(str).tolist())
    )
    return ShadowCalibrationStabilityResult(
        sessions=normalized_sessions,
        horizon_stability=horizon_stability,
        cost_stability=cost_stability,
        checks=checks,
        stable=failed_count == 0,
        failed_check_count=failed_count,
        instability_reason=reason,
    )


def _validated_sessions(frame: pd.DataFrame) -> pd.DataFrame:
    _require_columns(frame, SESSION_REQUIRED_COLUMNS, "sessions")
    if frame.empty:
        raise ShadowCalibrationStabilityError("sessions must not be empty")
    sessions = frame.loc[:, SESSION_REQUIRED_COLUMNS].copy()
    text_columns = SESSION_REQUIRED_COLUMNS[:-2]
    for column in text_columns:
        sessions[column] = sessions[column].map(
            lambda value: _required_text(value, f"sessions {column}")
        )
    for column in ("accepted_intent_count", "observation_count"):
        sessions[column] = sessions[column].map(
            lambda value: _positive_integer(value, f"sessions {column}")
        )
    if sessions["calibration_receipt_id"].duplicated().any():
        raise ShadowCalibrationStabilityError(
            "calibration_receipt_id values must be distinct"
        )
    if sessions["session_id"].duplicated().any():
        raise ShadowCalibrationStabilityError(
            "session_id values must be distinct"
        )
    return sessions.sort_values(
        ["session_id", "calibration_receipt_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _validated_horizons(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(frame, HORIZON_REQUIRED_COLUMNS, "horizon_metrics")
    if frame.empty:
        raise ShadowCalibrationStabilityError(
            "horizon_metrics must not be empty"
        )
    horizons = frame.loc[:, HORIZON_REQUIRED_COLUMNS].copy()
    _validate_source_bindings(horizons, sessions, "horizon_metrics")
    horizons["requested_horizon_ns"] = horizons[
        "requested_horizon_ns"
    ].map(lambda value: _non_negative_integer(value, "requested_horizon_ns"))
    horizons["action_group"] = horizons["action_group"].map(
        lambda value: _required_text(value, "action_group")
    )
    for column in (
        "coverage_ratio",
        "adverse_selection_rate",
    ):
        horizons[column] = horizons[column].map(
            lambda value: _bounded_rate(value, column)
        )
    for column in (
        "mean_directional_mid_move_ticks",
        "mean_directional_microprice_move_ticks",
        "mean_touch_markout_ticks",
    ):
        horizons[column] = horizons[column].map(
            lambda value: _finite_number(value, column)
        )
    key_columns = ["requested_horizon_ns", "action_group"]
    _validate_complete_grid(horizons, sessions, key_columns, "horizon")
    return horizons.sort_values(
        [*key_columns, "session_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _validated_costs(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(frame, COST_REQUIRED_COLUMNS, "cost_metrics")
    if frame.empty:
        raise ShadowCalibrationStabilityError("cost_metrics must not be empty")
    costs = frame.loc[:, COST_REQUIRED_COLUMNS].copy()
    _validate_source_bindings(costs, sessions, "cost_metrics")
    costs["requested_horizon_ns"] = costs["requested_horizon_ns"].map(
        lambda value: _non_negative_integer(value, "requested_horizon_ns")
    )
    for column in (
        "action_group",
        "cost_scenario",
        "cost_model_version",
        "reference_status",
    ):
        costs[column] = costs[column].map(
            lambda value: _required_text(value, column)
        )
    costs["cost_break_even_rate"] = costs["cost_break_even_rate"].map(
        lambda value: _bounded_rate(value, "cost_break_even_rate")
    )
    costs["mean_round_trip_cost_ticks"] = costs[
        "mean_round_trip_cost_ticks"
    ].map(lambda value: _non_negative_number(value, "mean_round_trip_cost_ticks"))
    costs["mean_break_even_surplus_ticks"] = costs[
        "mean_break_even_surplus_ticks"
    ].map(lambda value: _finite_number(value, "mean_break_even_surplus_ticks"))
    key_columns = [
        "requested_horizon_ns",
        "action_group",
        "cost_scenario",
        "cost_model_version",
        "reference_status",
    ]
    _validate_complete_grid(costs, sessions, key_columns, "cost")
    return costs.sort_values(
        [*key_columns, "session_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _validate_source_bindings(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
    label: str,
) -> None:
    expected = set(
        zip(
            sessions["calibration_receipt_id"],
            sessions["session_id"],
        )
    )
    actual = set(
        zip(
            frame["calibration_receipt_id"].astype(str),
            frame["session_id"].astype(str),
        )
    )
    if actual != expected:
        raise ShadowCalibrationStabilityError(
            f"{label} source bindings do not match sessions"
        )


def _validate_complete_grid(
    frame: pd.DataFrame,
    sessions: pd.DataFrame,
    key_columns: list[str],
    label: str,
) -> None:
    receipt_column = "calibration_receipt_id"
    if frame.duplicated([receipt_column, *key_columns]).any():
        raise ShadowCalibrationStabilityError(
            f"{label} metrics contain duplicate session keys"
        )
    expected_keys: set[tuple[Any, ...]] | None = None
    for receipt_id in sessions[receipt_column]:
        selected = frame.loc[frame[receipt_column].eq(receipt_id)]
        keys = {
            tuple(row)
            for row in selected.loc[:, key_columns].itertuples(
                index=False,
                name=None,
            )
        }
        if expected_keys is None:
            expected_keys = keys
        elif keys != expected_keys:
            raise ShadowCalibrationStabilityError(
                f"{label} metric grids differ across sessions"
            )
    if not expected_keys:
        raise ShadowCalibrationStabilityError(
            f"{label} metric grid must not be empty"
        )


def _horizon_stability(
    horizons: pd.DataFrame,
    config: ShadowCalibrationStabilityConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key, frame in horizons.groupby(
        ["requested_horizon_ns", "action_group"],
        sort=True,
        dropna=False,
    ):
        horizon_ns, action_group = key
        coverage = frame["coverage_ratio"].astype(float)
        directional_mid = frame["mean_directional_mid_move_ticks"].astype(
            float
        )
        directional_microprice = frame[
            "mean_directional_microprice_move_ticks"
        ].astype(float)
        touch = frame["mean_touch_markout_ticks"].astype(float)
        adverse = frame["adverse_selection_rate"].astype(float)
        signs = {
            _sign(value)
            for value in directional_mid
            if _sign(value) != 0
        }
        sign_consistent = len(signs) <= 1
        coverage_range = _range(coverage)
        directional_range = _range(directional_mid)
        adverse_range = _range(adverse)
        coverage_stable = bool(
            float(coverage.min()) >= config.min_session_coverage_ratio
            and coverage_range <= config.max_horizon_coverage_range
        )
        directional_stable = bool(
            directional_range <= config.max_directional_mid_range_ticks
            and (
                sign_consistent
                or not config.require_directional_sign_consistency
            )
        )
        adverse_stable = bool(
            adverse_range <= config.max_adverse_selection_rate_range
        )
        rows.append(
            {
                "requested_horizon_ns": int(horizon_ns),
                "action_group": str(action_group),
                "session_count": len(frame),
                "minimum_coverage_ratio": _round(coverage.min()),
                "maximum_coverage_ratio": _round(coverage.max()),
                "coverage_ratio_range": coverage_range,
                "mean_directional_mid_move_ticks": _round(
                    directional_mid.mean()
                ),
                "minimum_directional_mid_move_ticks": _round(
                    directional_mid.min()
                ),
                "maximum_directional_mid_move_ticks": _round(
                    directional_mid.max()
                ),
                "directional_mid_move_range_ticks": directional_range,
                "directional_sign_count": len(signs),
                "directional_sign_consistent": sign_consistent,
                "mean_directional_microprice_move_ticks": _round(
                    directional_microprice.mean()
                ),
                "mean_touch_markout_ticks": _round(touch.mean()),
                "minimum_adverse_selection_rate": _round(adverse.min()),
                "maximum_adverse_selection_rate": _round(adverse.max()),
                "adverse_selection_rate_range": adverse_range,
                "coverage_stable": coverage_stable,
                "directional_response_stable": directional_stable,
                "adverse_selection_stable": adverse_stable,
                "stable": (
                    coverage_stable
                    and directional_stable
                    and adverse_stable
                ),
            }
        )
    return pd.DataFrame(rows, columns=HORIZON_STABILITY_COLUMNS)


def _cost_stability(
    costs: pd.DataFrame,
    config: ShadowCalibrationStabilityConfig,
) -> pd.DataFrame:
    keys = [
        "requested_horizon_ns",
        "action_group",
        "cost_scenario",
        "cost_model_version",
        "reference_status",
    ]
    rows: list[dict[str, Any]] = []
    for key, frame in costs.groupby(keys, sort=True, dropna=False):
        (
            horizon_ns,
            action_group,
            scenario,
            version,
            reference_status,
        ) = key
        break_even = frame["cost_break_even_rate"].astype(float)
        round_trip = frame["mean_round_trip_cost_ticks"].astype(float)
        surplus = frame["mean_break_even_surplus_ticks"].astype(float)
        break_even_range = _range(break_even)
        round_trip_range = _range(round_trip)
        break_even_stable = bool(
            break_even_range <= config.max_cost_break_even_rate_range
        )
        round_trip_stable = bool(
            round_trip_range <= config.max_round_trip_cost_range_ticks
        )
        rows.append(
            {
                "requested_horizon_ns": int(horizon_ns),
                "action_group": str(action_group),
                "cost_scenario": str(scenario),
                "cost_model_version": str(version),
                "reference_status": str(reference_status),
                "session_count": len(frame),
                "minimum_cost_break_even_rate": _round(break_even.min()),
                "maximum_cost_break_even_rate": _round(break_even.max()),
                "cost_break_even_rate_range": break_even_range,
                "minimum_round_trip_cost_ticks": _round(round_trip.min()),
                "maximum_round_trip_cost_ticks": _round(round_trip.max()),
                "round_trip_cost_range_ticks": round_trip_range,
                "mean_break_even_surplus_ticks": _round(surplus.mean()),
                "cost_break_even_stable": break_even_stable,
                "round_trip_cost_stable": round_trip_stable,
                "stable": break_even_stable and round_trip_stable,
            }
        )
    return pd.DataFrame(rows, columns=COST_STABILITY_COLUMNS)


def _checks(
    sessions: pd.DataFrame,
    horizons: pd.DataFrame,
    costs: pd.DataFrame,
    config: ShadowCalibrationStabilityConfig,
) -> pd.DataFrame:
    identity_columns = (
        "strategy",
        "market",
        "target_mode",
        "provider",
        "transport",
        "exchange",
        "adapter",
    )
    identity_count = len(
        {
            _canonical_sha256(
                {column: row[column] for column in identity_columns}
            )
            for row in sessions.to_dict(orient="records")
        }
    )
    evidence_class_count = sessions["evidence_class"].nunique()
    contract_count = sessions["calibration_contract_sha256"].nunique()
    checks = [
        _check(
            "minimum_distinct_sessions",
            "cohort",
            len(sessions),
            ">=",
            config.min_sessions,
            len(sessions) >= config.min_sessions,
            "cohort has too few distinct calibration sessions",
        ),
        _check(
            "single_runtime_identity",
            "cohort",
            identity_count,
            "==",
            1,
            identity_count == 1,
            "calibration sessions have mixed runtime identity",
        ),
        _check(
            "single_evidence_class",
            "cohort",
            evidence_class_count,
            "==",
            1,
            evidence_class_count == 1,
            "simulation and real-provider evidence classes are mixed",
        ),
        _check(
            "single_calibration_contract",
            "cohort",
            contract_count,
            "==",
            1,
            contract_count == 1,
            "calibration sessions use different contracts",
        ),
        _check(
            "live_dryrun_target_mode",
            "cohort",
            int(sessions["target_mode"].eq("live_dryrun").sum()),
            "==",
            len(sessions),
            bool(sessions["target_mode"].eq("live_dryrun").all()),
            "a calibration session is not live_dryrun shadow evidence",
        ),
    ]
    for row in horizons.itertuples(index=False):
        stem = f"horizon_{row.requested_horizon_ns}_{row.action_group}"
        checks.extend(
            [
                _check(
                    f"{stem}_coverage_floor",
                    "horizon",
                    row.minimum_coverage_ratio,
                    ">=",
                    config.min_session_coverage_ratio,
                    row.minimum_coverage_ratio
                    >= config.min_session_coverage_ratio,
                    "a session falls below the cohort coverage floor",
                ),
                _check(
                    f"{stem}_coverage_range",
                    "horizon",
                    row.coverage_ratio_range,
                    "<=",
                    config.max_horizon_coverage_range,
                    row.coverage_ratio_range
                    <= config.max_horizon_coverage_range,
                    "horizon coverage varies beyond the configured limit",
                ),
                _check(
                    f"{stem}_directional_mid_range",
                    "horizon",
                    row.directional_mid_move_range_ticks,
                    "<=",
                    config.max_directional_mid_range_ticks,
                    row.directional_mid_move_range_ticks
                    <= config.max_directional_mid_range_ticks,
                    "directional mid response varies beyond the limit",
                ),
                _check(
                    f"{stem}_directional_sign",
                    "horizon",
                    row.directional_sign_consistent,
                    "is",
                    True,
                    bool(
                        row.directional_sign_consistent
                        or not config.require_directional_sign_consistency
                    ),
                    "directional response changes sign across sessions",
                ),
                _check(
                    f"{stem}_adverse_selection_range",
                    "horizon",
                    row.adverse_selection_rate_range,
                    "<=",
                    config.max_adverse_selection_rate_range,
                    row.adverse_selection_rate_range
                    <= config.max_adverse_selection_rate_range,
                    "adverse-selection rate varies beyond the limit",
                ),
            ]
        )
    for row in costs.itertuples(index=False):
        stem = (
            f"cost_{row.requested_horizon_ns}_{row.action_group}_"
            f"{row.cost_scenario}"
        )
        checks.extend(
            [
                _check(
                    f"{stem}_break_even_rate_range",
                    "cost",
                    row.cost_break_even_rate_range,
                    "<=",
                    config.max_cost_break_even_rate_range,
                    row.cost_break_even_rate_range
                    <= config.max_cost_break_even_rate_range,
                    "cost break-even rate varies beyond the limit",
                ),
                _check(
                    f"{stem}_round_trip_cost_range",
                    "cost",
                    row.round_trip_cost_range_ticks,
                    "<=",
                    config.max_round_trip_cost_range_ticks,
                    row.round_trip_cost_range_ticks
                    <= config.max_round_trip_cost_range_ticks,
                    "round-trip cost ticks vary beyond the limit",
                ),
            ]
        )
    return pd.DataFrame(checks, columns=CHECK_COLUMNS)


def _validate_config(config: ShadowCalibrationStabilityConfig) -> None:
    if isinstance(config.min_sessions, bool) or config.min_sessions < 2:
        raise ShadowCalibrationStabilityError(
            "min_sessions must be an integer of at least two"
        )
    if not isinstance(config.min_sessions, int):
        raise ShadowCalibrationStabilityError(
            "min_sessions must be an integer of at least two"
        )
    for name in (
        "min_session_coverage_ratio",
        "max_horizon_coverage_range",
        "max_adverse_selection_rate_range",
        "max_cost_break_even_rate_range",
    ):
        value = _bounded_rate(getattr(config, name), name)
        if value < 0:
            raise ShadowCalibrationStabilityError(f"{name} is invalid")
    for name in (
        "max_directional_mid_range_ticks",
        "max_round_trip_cost_range_ticks",
    ):
        _non_negative_number(getattr(config, name), name)
    if not isinstance(config.require_directional_sign_consistency, bool):
        raise ShadowCalibrationStabilityError(
            "require_directional_sign_consistency must be boolean"
        )


def _check(
    name: str,
    component: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "component": component,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ShadowCalibrationStabilityError(
            f"{label} missing required columns: {', '.join(missing)}"
        )


def _required_text(value: Any, name: str) -> str:
    if value is None:
        raise ShadowCalibrationStabilityError(f"{name} must not be blank")
    text = str(value).strip()
    if not text or text.lower() == "nan":
        raise ShadowCalibrationStabilityError(f"{name} must not be blank")
    return text


def _positive_integer(value: Any, name: str) -> int:
    parsed = _non_negative_integer(value, name)
    if parsed <= 0:
        raise ShadowCalibrationStabilityError(
            f"{name} must be a positive integer"
        )
    return parsed


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ShadowCalibrationStabilityError(
            f"{name} must be a non-negative integer"
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ShadowCalibrationStabilityError(
            f"{name} must be a non-negative integer"
        ) from exc
    if not math.isfinite(parsed) or not parsed.is_integer() or parsed < 0:
        raise ShadowCalibrationStabilityError(
            f"{name} must be a non-negative integer"
        )
    return int(parsed)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ShadowCalibrationStabilityError(
            f"{name} must be finite"
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ShadowCalibrationStabilityError(
            f"{name} must be finite"
        ) from exc
    if not math.isfinite(parsed):
        raise ShadowCalibrationStabilityError(f"{name} must be finite")
    return parsed


def _non_negative_number(value: Any, name: str) -> float:
    parsed = _finite_number(value, name)
    if parsed < 0:
        raise ShadowCalibrationStabilityError(
            f"{name} must be non-negative and finite"
        )
    return parsed


def _bounded_rate(value: Any, name: str) -> float:
    parsed = _finite_number(value, name)
    if not 0 <= parsed <= 1:
        raise ShadowCalibrationStabilityError(
            f"{name} must be between zero and one"
        )
    return parsed


def _range(values: pd.Series) -> float:
    return _round(float(values.max()) - float(values.min()))


def _round(value: Any) -> float:
    return round(float(value), 10)


def _sign(value: float) -> int:
    if value > 1e-12:
        return 1
    if value < -1e-12:
        return -1
    return 0


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _explicit_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(math.isfinite(float(value)) and float(value) == 1.0)
    return str(value).strip().lower() in {"1", "true", "yes"}
