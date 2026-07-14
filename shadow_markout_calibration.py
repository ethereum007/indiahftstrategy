from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from typing import Any

import pandas as pd


FEATURE_REQUIRED_COLUMNS = (
    "sequence",
    "ts_ns",
    "symbol",
    "bid_price",
    "ask_price",
    "bid_qty",
    "ask_qty",
    "microprice",
)
INTENT_REQUIRED_COLUMNS = (
    "intent_sequence",
    "source_sequence",
    "ts_ns",
    "symbol",
    "action",
    "side",
    "quantity_lots",
    "quantity_units",
    "limit_price",
    "within_limits",
    "intent_status",
    "routing_status",
    "submission_status",
)
OBSERVATION_COLUMNS = (
    "observation_id",
    "intent_sequence",
    "source_sequence",
    "intent_ts_ns",
    "symbol",
    "action",
    "action_group",
    "side",
    "side_name",
    "quantity_lots",
    "quantity_units",
    "intent_price",
    "source_bid",
    "source_ask",
    "source_mid",
    "source_microprice",
    "source_spread_ticks",
    "requested_horizon_ns",
    "target_ts_ns",
    "future_ts_ns",
    "realized_horizon_ns",
    "horizon_overshoot_ns",
    "covered",
    "future_bid",
    "future_ask",
    "future_mid",
    "future_microprice",
    "future_spread_ticks",
    "future_liquidation_touch",
    "directional_mid_move_ticks",
    "directional_microprice_move_ticks",
    "mid_markout_ticks",
    "touch_markout_ticks",
    "gross_touch_pnl",
    "adverse_selection",
)
COST_SENSITIVITY_COLUMNS = (
    "observation_id",
    "intent_sequence",
    "action_group",
    "requested_horizon_ns",
    "covered",
    "cost_scenario",
    "cost_model_version",
    "reference_status",
    "entry_cost",
    "exit_cost",
    "round_trip_cost",
    "round_trip_cost_ticks",
    "break_even_directional_move_ticks",
    "directional_mid_move_ticks",
    "break_even_surplus_ticks",
    "gross_touch_pnl",
    "net_touch_pnl",
    "cost_break_even_met",
)
HORIZON_SUMMARY_COLUMNS = (
    "requested_horizon_ns",
    "action_group",
    "intent_count",
    "covered_count",
    "coverage_ratio",
    "mean_realized_horizon_ns",
    "mean_horizon_overshoot_ns",
    "mean_directional_mid_move_ticks",
    "median_directional_mid_move_ticks",
    "mean_directional_microprice_move_ticks",
    "mean_mid_markout_ticks",
    "mean_touch_markout_ticks",
    "mean_gross_touch_pnl",
    "adverse_selection_rate",
)
COST_SUMMARY_COLUMNS = (
    "requested_horizon_ns",
    "action_group",
    "cost_scenario",
    "cost_model_version",
    "reference_status",
    "intent_count",
    "covered_count",
    "coverage_ratio",
    "mean_round_trip_cost",
    "mean_round_trip_cost_ticks",
    "mean_break_even_directional_move_ticks",
    "mean_break_even_surplus_ticks",
    "mean_net_touch_pnl",
    "cost_break_even_rate",
)


class ShadowMarkoutCalibrationError(ValueError):
    """Raised when shadow markout inputs violate the calibration contract."""


@dataclass(frozen=True)
class ShadowCostScenario:
    name: str
    cost_model_version: str
    reference_status: str
    stt_sell_rate: float
    exchange_transaction_rate: float
    sebi_fee_rate: float
    stamp_buy_rate: float
    gst_rate: float
    brokerage_per_order: float = 0.0
    clearing_per_lot: float = 0.0


REFERENCE_STATUS = "repository_reference_requires_external_validation"
REFERENCE_COST_MODEL_VERSION = "india_index_derivatives_reference_2026_v1"
DEFAULT_COST_SCENARIOS = (
    ShadowCostScenario(
        name="nse_index_futures_reference",
        cost_model_version=REFERENCE_COST_MODEL_VERSION,
        reference_status=REFERENCE_STATUS,
        stt_sell_rate=0.0005,
        exchange_transaction_rate=0.0000173,
        sebi_fee_rate=0.000001,
        stamp_buy_rate=0.00002,
        gst_rate=0.18,
    ),
    ShadowCostScenario(
        name="nse_index_options_reference",
        cost_model_version=REFERENCE_COST_MODEL_VERSION,
        reference_status=REFERENCE_STATUS,
        stt_sell_rate=0.0015,
        exchange_transaction_rate=0.0003503,
        sebi_fee_rate=0.000001,
        stamp_buy_rate=0.00003,
        gst_rate=0.18,
    ),
)


@dataclass(frozen=True)
class ShadowMarkoutCalibrationConfig:
    horizons_ns: tuple[int, ...] = (0, 250_000_000, 500_000_000)
    max_horizon_overshoot_ns: int = 250_000_000
    min_covered_observations_per_horizon: int = 1
    min_coverage_ratio: float = 0.5
    cost_scenarios: tuple[ShadowCostScenario, ...] = DEFAULT_COST_SCENARIOS


@dataclass(frozen=True)
class ShadowMarkoutCalibrationResult:
    observations: pd.DataFrame
    cost_sensitivity: pd.DataFrame
    horizon_summary: pd.DataFrame
    cost_summary: pd.DataFrame
    accepted_intent_count: int
    observation_count: int
    covered_observation_count: int
    completed: bool
    incomplete_reason: str


def evaluate_shadow_markout_calibration(
    features: pd.DataFrame,
    intents: pd.DataFrame,
    *,
    tick_size: float,
    source_lot_size: int,
    config: ShadowMarkoutCalibrationConfig | None = None,
) -> ShadowMarkoutCalibrationResult:
    config = config or ShadowMarkoutCalibrationConfig()
    tick_size = _positive_number(tick_size, "tick_size")
    source_lot_size = _positive_integer(source_lot_size, "source_lot_size")
    _validate_config(config)
    books = _validated_features(features)
    accepted = _validated_intents(
        intents,
        books,
        source_lot_size=source_lot_size,
    )
    timestamps = books["ts_ns"].astype(int).tolist()
    feature_rows = books.to_dict(orient="records")

    observation_rows: list[dict[str, Any]] = []
    for intent in accepted.to_dict(orient="records"):
        source = feature_rows[int(intent["source_sequence"]) - 1]
        for horizon_ns in config.horizons_ns:
            observation_rows.append(
                _observation(
                    intent=intent,
                    source=source,
                    feature_rows=feature_rows,
                    feature_timestamps=timestamps,
                    horizon_ns=horizon_ns,
                    max_overshoot_ns=config.max_horizon_overshoot_ns,
                    tick_size=tick_size,
                )
            )
    observations = pd.DataFrame(observation_rows, columns=OBSERVATION_COLUMNS)
    cost_rows = [
        _cost_sensitivity_row(
            observation=observation,
            scenario=scenario,
            source_lot_size=source_lot_size,
            tick_size=tick_size,
        )
        for observation in observation_rows
        for scenario in config.cost_scenarios
    ]
    cost_sensitivity = pd.DataFrame(
        cost_rows,
        columns=COST_SENSITIVITY_COLUMNS,
    )
    horizon_summary = _horizon_summary(observations, config.horizons_ns)
    cost_summary = _cost_summary(
        cost_sensitivity,
        config.horizons_ns,
        config.cost_scenarios,
    )
    completed, incomplete_reason = _completion(horizon_summary, config)
    covered = int(observations["covered"].map(_explicit_true).sum())
    return ShadowMarkoutCalibrationResult(
        observations=observations,
        cost_sensitivity=cost_sensitivity,
        horizon_summary=horizon_summary,
        cost_summary=cost_summary,
        accepted_intent_count=len(accepted),
        observation_count=len(observations),
        covered_observation_count=covered,
        completed=completed,
        incomplete_reason=incomplete_reason,
    )


def statutory_fill_cost(
    *,
    side: int,
    price: float,
    quantity_units: int,
    source_lot_size: int,
    scenario: ShadowCostScenario,
) -> float:
    if side not in {-1, 1}:
        raise ShadowMarkoutCalibrationError("side must be -1 or 1")
    price = _positive_number(price, "price")
    quantity_units = _positive_integer(quantity_units, "quantity_units")
    source_lot_size = _positive_integer(source_lot_size, "source_lot_size")
    _validate_cost_scenario(scenario)
    turnover = price * quantity_units
    stt = scenario.stt_sell_rate * turnover if side < 0 else 0.0
    stamp = scenario.stamp_buy_rate * turnover if side > 0 else 0.0
    exchange = scenario.exchange_transaction_rate * turnover
    sebi = scenario.sebi_fee_rate * turnover
    gst = scenario.gst_rate * (
        exchange + sebi + scenario.brokerage_per_order
    )
    clearing = scenario.clearing_per_lot * (
        quantity_units / source_lot_size
    )
    return round(
        stt
        + stamp
        + exchange
        + sebi
        + gst
        + scenario.brokerage_per_order
        + clearing,
        10,
    )


def _observation(
    *,
    intent: dict[str, Any],
    source: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    feature_timestamps: list[int],
    horizon_ns: int,
    max_overshoot_ns: int,
    tick_size: float,
) -> dict[str, Any]:
    intent_ts = int(intent["ts_ns"])
    target_ts = intent_ts + horizon_ns
    future_index = bisect_left(feature_timestamps, target_ts)
    future = (
        feature_rows[future_index]
        if future_index < len(feature_rows)
        else None
    )
    overshoot = (
        int(future["ts_ns"]) - target_ts if future is not None else None
    )
    covered = bool(
        future is not None
        and overshoot is not None
        and overshoot <= max_overshoot_ns
    )
    source_bid = float(source["bid_price"])
    source_ask = float(source["ask_price"])
    source_mid = 0.5 * (source_bid + source_ask)
    source_microprice = float(source["microprice"])
    side = int(intent["side"])
    quantity_units = int(intent["quantity_units"])
    intent_price = float(intent["limit_price"])
    row: dict[str, Any] = {
        "observation_id": (
            f"intent-{int(intent['intent_sequence'])}"
            f"-horizon-{horizon_ns}"
        ),
        "intent_sequence": int(intent["intent_sequence"]),
        "source_sequence": int(intent["source_sequence"]),
        "intent_ts_ns": intent_ts,
        "symbol": str(intent["symbol"]),
        "action": str(intent["action"]),
        "action_group": _action_group(intent["action"]),
        "side": side,
        "side_name": "buy" if side > 0 else "sell",
        "quantity_lots": int(intent["quantity_lots"]),
        "quantity_units": quantity_units,
        "intent_price": intent_price,
        "source_bid": source_bid,
        "source_ask": source_ask,
        "source_mid": source_mid,
        "source_microprice": source_microprice,
        "source_spread_ticks": (source_ask - source_bid) / tick_size,
        "requested_horizon_ns": horizon_ns,
        "target_ts_ns": target_ts,
        "future_ts_ns": None,
        "realized_horizon_ns": None,
        "horizon_overshoot_ns": None,
        "covered": covered,
        "future_bid": None,
        "future_ask": None,
        "future_mid": None,
        "future_microprice": None,
        "future_spread_ticks": None,
        "future_liquidation_touch": None,
        "directional_mid_move_ticks": None,
        "directional_microprice_move_ticks": None,
        "mid_markout_ticks": None,
        "touch_markout_ticks": None,
        "gross_touch_pnl": None,
        "adverse_selection": None,
    }
    if not covered or future is None:
        return _rounded_row(row)
    future_bid = float(future["bid_price"])
    future_ask = float(future["ask_price"])
    future_mid = 0.5 * (future_bid + future_ask)
    future_microprice = float(future["microprice"])
    liquidation_touch = future_bid if side > 0 else future_ask
    directional_mid = side * (future_mid - source_mid) / tick_size
    row.update(
        {
            "future_ts_ns": int(future["ts_ns"]),
            "realized_horizon_ns": int(future["ts_ns"]) - intent_ts,
            "horizon_overshoot_ns": int(overshoot),
            "future_bid": future_bid,
            "future_ask": future_ask,
            "future_mid": future_mid,
            "future_microprice": future_microprice,
            "future_spread_ticks": (
                (future_ask - future_bid) / tick_size
            ),
            "future_liquidation_touch": liquidation_touch,
            "directional_mid_move_ticks": directional_mid,
            "directional_microprice_move_ticks": (
                side * (future_microprice - source_microprice) / tick_size
            ),
            "mid_markout_ticks": (
                side * (future_mid - intent_price) / tick_size
            ),
            "touch_markout_ticks": (
                side * (liquidation_touch - intent_price) / tick_size
            ),
            "gross_touch_pnl": (
                side * (liquidation_touch - intent_price) * quantity_units
            ),
            "adverse_selection": directional_mid < 0,
        }
    )
    return _rounded_row(row)


def _cost_sensitivity_row(
    *,
    observation: dict[str, Any],
    scenario: ShadowCostScenario,
    source_lot_size: int,
    tick_size: float,
) -> dict[str, Any]:
    base = {
        "observation_id": observation["observation_id"],
        "intent_sequence": observation["intent_sequence"],
        "action_group": observation["action_group"],
        "requested_horizon_ns": observation["requested_horizon_ns"],
        "covered": observation["covered"],
        "cost_scenario": scenario.name,
        "cost_model_version": scenario.cost_model_version,
        "reference_status": scenario.reference_status,
        "entry_cost": None,
        "exit_cost": None,
        "round_trip_cost": None,
        "round_trip_cost_ticks": None,
        "break_even_directional_move_ticks": None,
        "directional_mid_move_ticks": observation[
            "directional_mid_move_ticks"
        ],
        "break_even_surplus_ticks": None,
        "gross_touch_pnl": observation["gross_touch_pnl"],
        "net_touch_pnl": None,
        "cost_break_even_met": None,
    }
    if not observation["covered"]:
        return base
    side = int(observation["side"])
    quantity_units = int(observation["quantity_units"])
    entry_cost = statutory_fill_cost(
        side=side,
        price=float(observation["intent_price"]),
        quantity_units=quantity_units,
        source_lot_size=source_lot_size,
        scenario=scenario,
    )
    exit_cost = statutory_fill_cost(
        side=-side,
        price=float(observation["future_liquidation_touch"]),
        quantity_units=quantity_units,
        source_lot_size=source_lot_size,
        scenario=scenario,
    )
    round_trip_cost = entry_cost + exit_cost
    cost_ticks = round_trip_cost / (quantity_units * tick_size)
    source_half_spread_ticks = 0.5 * float(
        observation["source_spread_ticks"]
    )
    future_half_spread_ticks = 0.5 * float(
        observation["future_spread_ticks"]
    )
    break_even_ticks = (
        source_half_spread_ticks + future_half_spread_ticks + cost_ticks
    )
    directional_mid = float(observation["directional_mid_move_ticks"])
    net_touch_pnl = float(observation["gross_touch_pnl"]) - round_trip_cost
    base.update(
        {
            "entry_cost": round(entry_cost, 10),
            "exit_cost": round(exit_cost, 10),
            "round_trip_cost": round(round_trip_cost, 10),
            "round_trip_cost_ticks": round(cost_ticks, 10),
            "break_even_directional_move_ticks": round(
                break_even_ticks,
                10,
            ),
            "break_even_surplus_ticks": round(
                directional_mid - break_even_ticks,
                10,
            ),
            "net_touch_pnl": round(net_touch_pnl, 10),
            "cost_break_even_met": net_touch_pnl >= 0,
        }
    )
    return base


def _horizon_summary(
    observations: pd.DataFrame,
    horizons_ns: tuple[int, ...],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon_ns in horizons_ns:
        horizon = observations.loc[
            observations["requested_horizon_ns"].eq(horizon_ns)
        ]
        for action_group, frame in _summary_groups(horizon):
            covered = frame.loc[frame["covered"].map(_explicit_true)]
            rows.append(
                {
                    "requested_horizon_ns": horizon_ns,
                    "action_group": action_group,
                    "intent_count": len(frame),
                    "covered_count": len(covered),
                    "coverage_ratio": _ratio(len(covered), len(frame)),
                    "mean_realized_horizon_ns": _mean(
                        covered,
                        "realized_horizon_ns",
                    ),
                    "mean_horizon_overshoot_ns": _mean(
                        covered,
                        "horizon_overshoot_ns",
                    ),
                    "mean_directional_mid_move_ticks": _mean(
                        covered,
                        "directional_mid_move_ticks",
                    ),
                    "median_directional_mid_move_ticks": _median(
                        covered,
                        "directional_mid_move_ticks",
                    ),
                    "mean_directional_microprice_move_ticks": _mean(
                        covered,
                        "directional_microprice_move_ticks",
                    ),
                    "mean_mid_markout_ticks": _mean(
                        covered,
                        "mid_markout_ticks",
                    ),
                    "mean_touch_markout_ticks": _mean(
                        covered,
                        "touch_markout_ticks",
                    ),
                    "mean_gross_touch_pnl": _mean(
                        covered,
                        "gross_touch_pnl",
                    ),
                    "adverse_selection_rate": _boolean_rate(
                        covered,
                        "adverse_selection",
                    ),
                }
            )
    return pd.DataFrame(rows, columns=HORIZON_SUMMARY_COLUMNS)


def _cost_summary(
    cost_sensitivity: pd.DataFrame,
    horizons_ns: tuple[int, ...],
    scenarios: tuple[ShadowCostScenario, ...],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon_ns in horizons_ns:
        horizon = cost_sensitivity.loc[
            cost_sensitivity["requested_horizon_ns"].eq(horizon_ns)
        ]
        for action_group, grouped in _summary_groups(horizon):
            for scenario in scenarios:
                frame = grouped.loc[
                    grouped["cost_scenario"].eq(scenario.name)
                ]
                covered = frame.loc[frame["covered"].map(_explicit_true)]
                rows.append(
                    {
                        "requested_horizon_ns": horizon_ns,
                        "action_group": action_group,
                        "cost_scenario": scenario.name,
                        "cost_model_version": scenario.cost_model_version,
                        "reference_status": scenario.reference_status,
                        "intent_count": len(frame),
                        "covered_count": len(covered),
                        "coverage_ratio": _ratio(len(covered), len(frame)),
                        "mean_round_trip_cost": _mean(
                            covered,
                            "round_trip_cost",
                        ),
                        "mean_round_trip_cost_ticks": _mean(
                            covered,
                            "round_trip_cost_ticks",
                        ),
                        "mean_break_even_directional_move_ticks": _mean(
                            covered,
                            "break_even_directional_move_ticks",
                        ),
                        "mean_break_even_surplus_ticks": _mean(
                            covered,
                            "break_even_surplus_ticks",
                        ),
                        "mean_net_touch_pnl": _mean(
                            covered,
                            "net_touch_pnl",
                        ),
                        "cost_break_even_rate": _boolean_rate(
                            covered,
                            "cost_break_even_met",
                        ),
                    }
                )
    return pd.DataFrame(rows, columns=COST_SUMMARY_COLUMNS)


def _summary_groups(
    frame: pd.DataFrame,
) -> list[tuple[str, pd.DataFrame]]:
    groups = [("all", frame)]
    for action_group in ("entry", "exit"):
        selected = frame.loc[frame["action_group"].eq(action_group)]
        if not selected.empty:
            groups.append((action_group, selected))
    return groups


def _completion(
    horizon_summary: pd.DataFrame,
    config: ShadowMarkoutCalibrationConfig,
) -> tuple[bool, str]:
    overall = horizon_summary.loc[horizon_summary["action_group"].eq("all")]
    for row in overall.itertuples(index=False):
        if int(row.covered_count) < config.min_covered_observations_per_horizon:
            return False, (
                f"horizon_{int(row.requested_horizon_ns)}_insufficient_count"
            )
        if float(row.coverage_ratio) < config.min_coverage_ratio:
            return False, (
                f"horizon_{int(row.requested_horizon_ns)}_insufficient_coverage"
            )
    return True, ""


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    _require_columns(features, FEATURE_REQUIRED_COLUMNS, "features")
    if features.empty:
        raise ShadowMarkoutCalibrationError("features must not be empty")
    frame = features.copy().reset_index(drop=True)
    sequences = [
        _positive_integer(value, "feature sequence")
        for value in frame["sequence"]
    ]
    if sequences != list(range(1, len(frame) + 1)):
        raise ShadowMarkoutCalibrationError(
            "feature sequence must be contiguous from one"
        )
    timestamps = [
        _non_negative_integer(value, "feature ts_ns")
        for value in frame["ts_ns"]
    ]
    if any(
        current <= previous
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        raise ShadowMarkoutCalibrationError(
            "feature timestamps must be strictly increasing"
        )
    symbols = set(frame["symbol"].astype(str).str.strip())
    if len(symbols) != 1 or not next(iter(symbols)):
        raise ShadowMarkoutCalibrationError(
            "features must contain exactly one symbol"
        )
    for row in frame.itertuples(index=False):
        bid = _positive_number(row.bid_price, "feature bid_price")
        ask = _positive_number(row.ask_price, "feature ask_price")
        _positive_number(row.bid_qty, "feature bid_qty")
        _positive_number(row.ask_qty, "feature ask_qty")
        microprice = _positive_number(row.microprice, "feature microprice")
        if ask <= bid:
            raise ShadowMarkoutCalibrationError(
                "feature ask_price must exceed bid_price"
            )
        if not bid <= microprice <= ask:
            raise ShadowMarkoutCalibrationError(
                "feature microprice must be inside the book"
            )
    frame["sequence"] = sequences
    frame["ts_ns"] = timestamps
    return frame


def _validated_intents(
    intents: pd.DataFrame,
    features: pd.DataFrame,
    *,
    source_lot_size: int,
) -> pd.DataFrame:
    _require_columns(intents, INTENT_REQUIRED_COLUMNS, "intents")
    if intents.empty:
        raise ShadowMarkoutCalibrationError("intents must not be empty")
    frame = intents.copy().reset_index(drop=True)
    if not all(frame["routing_status"].astype(str).eq("not_routable")):
        raise ShadowMarkoutCalibrationError(
            "all shadow intents must remain not_routable"
        )
    if not all(frame["submission_status"].astype(str).eq("not_submitted")):
        raise ShadowMarkoutCalibrationError(
            "all shadow intents must remain not_submitted"
        )
    accepted = frame.loc[
        frame["within_limits"].map(_explicit_true)
        & frame["intent_status"].astype(str).eq("shadow_observed")
    ].copy()
    if accepted.empty:
        raise ShadowMarkoutCalibrationError(
            "calibration requires at least one observed shadow intent"
        )
    expected_sequences = list(range(1, len(frame) + 1))
    intent_sequences = [
        _positive_integer(value, "intent_sequence")
        for value in frame["intent_sequence"]
    ]
    if intent_sequences != expected_sequences:
        raise ShadowMarkoutCalibrationError(
            "intent_sequence must be contiguous from one"
        )
    symbol = str(features.iloc[0]["symbol"]).strip()
    for row in accepted.itertuples(index=False):
        source_sequence = _positive_integer(
            row.source_sequence,
            "source_sequence",
        )
        if source_sequence > len(features):
            raise ShadowMarkoutCalibrationError(
                "intent source_sequence is outside features"
            )
        source = features.iloc[source_sequence - 1]
        intent_ts_ns = _non_negative_integer(row.ts_ns, "intent ts_ns")
        if intent_ts_ns != int(source["ts_ns"]):
            raise ShadowMarkoutCalibrationError(
                "intent timestamp does not match its source feature"
            )
        if str(row.symbol).strip() != symbol:
            raise ShadowMarkoutCalibrationError(
                "intent symbol does not match features"
            )
        side = _signed_side(row.side)
        quantity_lots = _positive_integer(
            row.quantity_lots,
            "quantity_lots",
        )
        quantity_units = _positive_integer(
            row.quantity_units,
            "quantity_units",
        )
        if quantity_units != quantity_lots * source_lot_size:
            raise ShadowMarkoutCalibrationError(
                "quantity_units must equal quantity_lots * source_lot_size"
            )
        limit_price = _positive_number(row.limit_price, "limit_price")
        expected_touch = float(
            source["ask_price"] if side > 0 else source["bid_price"]
        )
        if limit_price != expected_touch:
            raise ShadowMarkoutCalibrationError(
                "shadow intent price does not match its source touch"
            )
        _action_group(row.action)
    return accepted.reset_index(drop=True)


def _validate_config(config: ShadowMarkoutCalibrationConfig) -> None:
    if not config.horizons_ns:
        raise ShadowMarkoutCalibrationError("horizons_ns must not be empty")
    horizons = [
        _non_negative_integer(value, "horizon_ns")
        for value in config.horizons_ns
    ]
    if horizons != sorted(set(horizons)):
        raise ShadowMarkoutCalibrationError(
            "horizons_ns must be unique and increasing"
        )
    _non_negative_integer(
        config.max_horizon_overshoot_ns,
        "max_horizon_overshoot_ns",
    )
    _positive_integer(
        config.min_covered_observations_per_horizon,
        "min_covered_observations_per_horizon",
    )
    ratio = float(config.min_coverage_ratio)
    if not math.isfinite(ratio) or not 0 < ratio <= 1:
        raise ShadowMarkoutCalibrationError(
            "min_coverage_ratio must be in (0, 1]"
        )
    if not config.cost_scenarios:
        raise ShadowMarkoutCalibrationError(
            "cost_scenarios must not be empty"
        )
    names = [scenario.name for scenario in config.cost_scenarios]
    if len(set(names)) != len(names):
        raise ShadowMarkoutCalibrationError(
            "cost scenario names must be unique"
        )
    for scenario in config.cost_scenarios:
        _validate_cost_scenario(scenario)


def _validate_cost_scenario(scenario: ShadowCostScenario) -> None:
    for name in ("name", "cost_model_version", "reference_status"):
        if not str(getattr(scenario, name)).strip():
            raise ShadowMarkoutCalibrationError(
                f"cost scenario {name} must not be blank"
            )
    for name in (
        "stt_sell_rate",
        "exchange_transaction_rate",
        "sebi_fee_rate",
        "stamp_buy_rate",
        "gst_rate",
        "brokerage_per_order",
        "clearing_per_lot",
    ):
        value = float(getattr(scenario, name))
        if not math.isfinite(value) or value < 0:
            raise ShadowMarkoutCalibrationError(
                f"cost scenario {name} must be non-negative and finite"
            )


def _action_group(value: Any) -> str:
    action = str(value).strip()
    if action == "entry":
        return "entry"
    if action in {"exit_hold", "exit_decay", "terminal_flatten"}:
        return "exit"
    raise ShadowMarkoutCalibrationError(
        f"unsupported shadow intent action: {action or '<blank>'}"
    )


def _signed_side(value: Any) -> int:
    try:
        side = int(value)
    except (TypeError, ValueError) as exc:
        raise ShadowMarkoutCalibrationError("side must be -1 or 1") from exc
    if side not in {-1, 1} or float(value) != side:
        raise ShadowMarkoutCalibrationError("side must be -1 or 1")
    return side


def _rounded_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(value, 10) if isinstance(value, float) else value
        for key, value in row.items()
    }


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else round(float(values.mean()), 10)


def _median(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if values.empty else round(float(values.median()), 10)


def _boolean_rate(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty:
        return None
    values = frame[column].dropna().map(_explicit_true)
    return None if values.empty else round(float(values.mean()), 10)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else round(numerator / denominator, 10)


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ShadowMarkoutCalibrationError(
            f"{label} missing required columns: {', '.join(missing)}"
        )


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ShadowMarkoutCalibrationError(
            f"{name} must be positive and finite"
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ShadowMarkoutCalibrationError(
            f"{name} must be positive and finite"
        ) from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise ShadowMarkoutCalibrationError(
            f"{name} must be positive and finite"
        )
    return parsed


def _positive_integer(value: Any, name: str) -> int:
    parsed = _non_negative_integer(value, name)
    if parsed <= 0:
        raise ShadowMarkoutCalibrationError(
            f"{name} must be a positive integer"
        )
    return parsed


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ShadowMarkoutCalibrationError(
            f"{name} must be a non-negative integer"
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ShadowMarkoutCalibrationError(
            f"{name} must be a non-negative integer"
        ) from exc
    if not math.isfinite(parsed) or not parsed.is_integer() or parsed < 0:
        raise ShadowMarkoutCalibrationError(
            f"{name} must be a non-negative integer"
        )
    return int(parsed)


def _explicit_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(math.isfinite(float(value)) and float(value) == 1.0)
    return str(value).strip().lower() in {"1", "true", "yes"}
