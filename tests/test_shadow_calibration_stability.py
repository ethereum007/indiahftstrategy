from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from shadow_calibration_stability import (
    ShadowCalibrationStabilityConfig,
    ShadowCalibrationStabilityError,
    evaluate_shadow_calibration_stability,
)


def _sessions() -> pd.DataFrame:
    rows = []
    for index in (1, 2):
        rows.append(
            {
                "calibration_receipt_id": f"calibration-{index}",
                "session_id": f"nse-shadow-202607{13 + index}",
                "strategy": "microprice_imbalance",
                "market": "india_nse_index_derivatives",
                "target_mode": "live_dryrun",
                "provider": "arrow_money",
                "transport": "websocket",
                "exchange": "NSE",
                "adapter": "arrow_ws",
                "evidence_class": "deterministic_simulation",
                "calibration_contract_sha256": "a" * 64,
                "accepted_intent_count": 2,
                "observation_count": 6,
            }
        )
    return pd.DataFrame(rows)


def _horizons() -> pd.DataFrame:
    rows = []
    for index, session in _sessions().iterrows():
        for horizon, directional in ((0, 0.0), (250_000_000, 0.2)):
            rows.append(
                {
                    "calibration_receipt_id": session[
                        "calibration_receipt_id"
                    ],
                    "session_id": session["session_id"],
                    "requested_horizon_ns": horizon,
                    "action_group": "all",
                    "coverage_ratio": 0.9 + (0.05 * index),
                    "mean_directional_mid_move_ticks": (
                        directional + (0.05 * index)
                    ),
                    "mean_directional_microprice_move_ticks": (
                        directional + 0.1 + (0.05 * index)
                    ),
                    "mean_touch_markout_ticks": -1.0 + (0.05 * index),
                    "adverse_selection_rate": 0.25 + (0.05 * index),
                }
            )
    return pd.DataFrame(rows)


def _costs() -> pd.DataFrame:
    rows = []
    for index, session in _sessions().iterrows():
        for horizon in (0, 250_000_000):
            for scenario, cost_ticks in (
                ("nse_index_futures_reference", 0.10),
                ("nse_index_options_reference", 0.25),
            ):
                rows.append(
                    {
                        "calibration_receipt_id": session[
                            "calibration_receipt_id"
                        ],
                        "session_id": session["session_id"],
                        "requested_horizon_ns": horizon,
                        "action_group": "all",
                        "cost_scenario": scenario,
                        "cost_model_version": (
                            "india_index_derivatives_reference_2026_v1"
                        ),
                        "reference_status": (
                            "repository_reference_requires_external_validation"
                        ),
                        "cost_break_even_rate": 0.5 + (0.05 * index),
                        "mean_round_trip_cost_ticks": (
                            cost_ticks + (0.01 * index)
                        ),
                        "mean_break_even_surplus_ticks": (
                            -1.0 + (0.05 * index)
                        ),
                    }
                )
    return pd.DataFrame(rows)


def test_shadow_calibration_stability_accepts_comparable_sessions():
    result = evaluate_shadow_calibration_stability(
        _sessions(),
        _horizons(),
        _costs(),
    )

    assert result.stable
    assert result.failed_check_count == 0
    assert result.instability_reason == ""
    assert len(result.horizon_stability) == 2
    assert len(result.cost_stability) == 4
    assert result.horizon_stability["stable"].astype(bool).all()
    assert result.cost_stability["stable"].astype(bool).all()


def test_shadow_calibration_stability_records_one_session_as_unstable():
    sessions = _sessions().iloc[[0]].copy()
    receipt = sessions.iloc[0]["calibration_receipt_id"]

    result = evaluate_shadow_calibration_stability(
        sessions,
        _horizons().loc[
            _horizons()["calibration_receipt_id"].eq(receipt)
        ],
        _costs().loc[_costs()["calibration_receipt_id"].eq(receipt)],
    )

    assert not result.stable
    assert "minimum_distinct_sessions" in result.instability_reason


def test_shadow_calibration_stability_records_identity_mix_as_unstable():
    sessions = _sessions()
    sessions.loc[1, "provider"] = "irage"

    result = evaluate_shadow_calibration_stability(
        sessions,
        _horizons(),
        _costs(),
    )

    assert not result.stable
    assert "single_runtime_identity" in result.instability_reason


@pytest.mark.parametrize(
    ("surface", "column", "value", "failed_check"),
    [
        ("horizon", "coverage_ratio", 0.1, "coverage_floor"),
        (
            "horizon",
            "mean_directional_mid_move_ticks",
            -0.2,
            "directional_sign",
        ),
        (
            "horizon",
            "adverse_selection_rate",
            0.9,
            "adverse_selection_range",
        ),
        ("cost", "cost_break_even_rate", 1.0, "break_even_rate_range"),
        (
            "cost",
            "mean_round_trip_cost_ticks",
            1.0,
            "round_trip_cost_range",
        ),
    ],
)
def test_shadow_calibration_stability_records_metric_instability(
    surface,
    column,
    value,
    failed_check,
):
    horizons = _horizons()
    costs = _costs()
    target = horizons if surface == "horizon" else costs
    target.loc[target.index[-1], column] = value

    result = evaluate_shadow_calibration_stability(
        _sessions(),
        horizons,
        costs,
    )

    assert not result.stable
    assert failed_check in result.instability_reason


def test_shadow_calibration_stability_rejects_mismatched_metric_grid():
    horizons = _horizons().iloc[:-1].copy()

    with pytest.raises(
        ShadowCalibrationStabilityError,
        match="metric grids differ",
    ):
        evaluate_shadow_calibration_stability(
            _sessions(),
            horizons,
            _costs(),
        )


def test_shadow_calibration_stability_rejects_duplicate_session_identity():
    sessions = _sessions()
    sessions.loc[1, "session_id"] = sessions.loc[0, "session_id"]

    with pytest.raises(
        ShadowCalibrationStabilityError,
        match="session_id values must be distinct",
    ):
        evaluate_shadow_calibration_stability(
            sessions,
            _horizons(),
            _costs(),
        )


@pytest.mark.parametrize(
    "config",
    [
        replace(ShadowCalibrationStabilityConfig(), min_sessions=1),
        replace(
            ShadowCalibrationStabilityConfig(),
            max_horizon_coverage_range=1.1,
        ),
        replace(
            ShadowCalibrationStabilityConfig(),
            max_directional_mid_range_ticks=-1.0,
        ),
    ],
)
def test_shadow_calibration_stability_rejects_invalid_config(config):
    with pytest.raises(ShadowCalibrationStabilityError):
        evaluate_shadow_calibration_stability(
            _sessions(),
            _horizons(),
            _costs(),
            config=config,
        )
