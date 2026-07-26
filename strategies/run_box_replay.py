from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv
from engine.hft_backtest import (
    IndianCostModel,
    Instrument,
    Kind,
    LatencyModel,
)
from engine.multi_engine import (
    InstrumentConfig,
    MultiBacktestResult,
    MultiInstrumentEngine,
    VenueConfig,
)
from reports.replay import (
    input_quarantine_frame,
    replay_summary,
    write_replay_outputs,
)
from scanners.parity_box import scan_boxes
from strategies.box_arb import (
    BOX_LEGS,
    BoxArbConfig,
    BoxArbTakerStrategy,
    BoxLegMap,
)


BOX_REPLAY_RUN_TYPE = "box_replay"
BOX_REPLAY_REQUIRED_ARTIFACTS = (
    "equity.csv",
    "signals.csv",
    "box_execution_guard.csv",
    "legging.csv",
    "summary.csv",
)


@dataclass(frozen=True)
class BoxReplayResult:
    result: MultiBacktestResult
    signals: pd.DataFrame
    summary: pd.DataFrame
    legging: pd.DataFrame
    execution_guard: pd.DataFrame
    input_quarantine: pd.DataFrame
    output_dir: Path | None = None


def run_box_replay(
    *,
    chain_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    depth_fraction: float = 0.25,
    fair_value_adjustment: float = 0.0,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    latency_jitter_us: float = 0.0,
    latency_seed: int = 17,
    max_signal_age_ns: int = 1_000_000,
    max_leg_book_age_ns: int = 1_000_000,
    max_leg_book_skew_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
) -> BoxReplayResult:
    normalized_chain = load_option_chain_csv(
        chain_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    )
    chain = normalized_chain.data
    input_quarantine = input_quarantine_frame(
        {"chain": normalized_chain.quarantine},
        dataset_types={"chain": "option_chain"},
    )

    option = Instrument(
        "INDEX-OPT",
        Kind.OPT,
        lot_size=lot_size,
        tick=option_tick,
    )
    option_costs = IndianCostModel.nse_index_options()
    signals = scan_boxes(
        chain,
        option_instrument=option,
        option_costs=option_costs,
        depth_fraction=depth_fraction,
        fair_value_adjustment=fair_value_adjustment,
    )
    if signal_limit is not None:
        signals = signals.head(signal_limit).copy()

    instruments, leg_map = _build_instruments(
        chain=chain,
        lot_size=lot_size,
        option_tick=option_tick,
        option_costs=option_costs,
        max_position_lots=max_position_lots,
    )
    strategy = BoxArbTakerStrategy(
        signals,
        leg_map,
        BoxArbConfig(
            max_signal_age_ns=max_signal_age_ns,
            max_leg_book_age_ns=max_leg_book_age_ns,
            max_leg_book_skew_ns=max_leg_book_skew_ns,
            max_qty=max_qty,
            fair_value_adjustment=fair_value_adjustment,
        ),
    )
    engine = MultiInstrumentEngine(
        instruments=instruments,
        venues={
            "NSE": VenueConfig(
                "NSE",
                LatencyModel(
                    feed_us=feed_latency_us,
                    order_us=order_latency_us,
                    jitter_us=latency_jitter_us,
                    _rng=np.random.default_rng(latency_seed),
                ),
            )
        },
        strategy=strategy,
    )
    result = engine.run()
    strategy_order_ids = [
        oid
        for execution in strategy.executions
        for oid in execution.order_ids
    ]
    summary = replay_summary(
        result,
        strategy_orders=strategy_order_ids,
        input_quarantine=input_quarantine,
    )
    legging = strategy.legging_report()
    execution_guard = strategy.execution_guard_report()
    execution_metrics = _execution_guard_metrics(
        execution_guard,
        legging,
        result.order_submissions,
        result.ioc_arrival_audit,
        max_leg_book_age_ns=max_leg_book_age_ns,
        max_leg_book_skew_ns=max_leg_book_skew_ns,
    )
    latency_metrics = _latency_sampling_metrics(
        result.feed_deliveries,
        result.order_submissions,
        feed_latency_us=feed_latency_us,
        order_latency_us=order_latency_us,
        latency_jitter_us=latency_jitter_us,
        latency_seed=latency_seed,
    )
    summary = pd.concat(
        [
            summary,
            pd.DataFrame(
                [
                    {
                        **execution_metrics,
                        **latency_metrics,
                    }
                ],
                index=summary.index,
            ),
        ],
        axis=1,
    )

    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        write_replay_outputs(
            result=result,
            output_dir=out_dir,
            summary=summary,
            strategy_order_ids=strategy_order_ids,
            extra_frames={
                "signals": signals,
                "legging": legging,
                "box_execution_guard": execution_guard,
                "input_quarantine": input_quarantine,
            },
            manifest_run_type=BOX_REPLAY_RUN_TYPE,
            manifest_inputs={"chain": chain_path},
            manifest_parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "lot_size": lot_size,
                "option_tick": option_tick,
                "depth_fraction": depth_fraction,
                "fair_value_adjustment": (
                    fair_value_adjustment
                ),
                "feed_latency_us": feed_latency_us,
                "order_latency_us": order_latency_us,
                "latency_jitter_us": latency_jitter_us,
                "latency_seed": latency_seed,
                "max_signal_age_ns": max_signal_age_ns,
                "max_leg_book_age_ns": max_leg_book_age_ns,
                "max_leg_book_skew_ns": (
                    max_leg_book_skew_ns
                ),
                "max_qty": max_qty,
                "max_position_lots": max_position_lots,
                "signal_limit": signal_limit,
            },
        )
    return BoxReplayResult(
        result=result,
        signals=signals,
        summary=summary,
        legging=legging,
        execution_guard=execution_guard,
        input_quarantine=input_quarantine,
        output_dir=out_dir,
    )


def _execution_guard_metrics(
    guard: pd.DataFrame,
    legging: pd.DataFrame,
    order_submissions: pd.DataFrame,
    ioc_arrival_audit: pd.DataFrame,
    *,
    max_leg_book_age_ns: int,
    max_leg_book_skew_ns: int,
) -> dict[str, int | float | bool]:
    passed = _bool_column(
        guard,
        "guard_passed",
        default=False,
    )
    reasons = _text_column(guard, "guard_reason")
    routing_status = _text_column(
        guard,
        "routing_status",
    )
    preflight_attempted = _bool_column(
        guard,
        "ioc_batch_preflight_attempted",
        default=False,
    )
    preflight_passed = _bool_column(
        guard,
        "ioc_batch_preflight_passed",
        default=False,
    )
    source_checked = _bool_column(
        guard,
        "signal_source_books_checked",
        default=False,
    )
    source_ready = _bool_column(
        guard,
        "signal_source_books_ready",
        default=False,
    )
    edge_checked = _bool_column(
        guard,
        "edge_revalidation_checked",
        default=False,
    )

    passed_rows = guard.loc[passed]
    leg_ages = pd.DataFrame(
        {
            f"{leg}_book_age_ns": pd.to_numeric(
                passed_rows.get(
                    f"{leg}_book_age_ns",
                    pd.Series(
                        index=passed_rows.index,
                        dtype="float64",
                    ),
                ),
                errors="coerce",
            )
            for leg in BOX_LEGS
        },
        index=passed_rows.index,
    )
    skew = pd.to_numeric(
        passed_rows.get(
            "leg_book_skew_ns",
            pd.Series(
                index=passed_rows.index,
                dtype="float64",
            ),
        ),
        errors="coerce",
    )
    missing_guard_age_rows = (
        leg_ages.isna().any(axis=1) | skew.isna()
    )
    observed_max_age = (
        leg_ages.max(axis=1).dropna()
        if not leg_ages.empty
        else pd.Series(dtype="float64")
    )
    observed_skew = skew.dropna()

    partial = _bool_column(
        legging,
        "partial",
        default=True,
    )
    route_rejections = _numeric_column(
        legging,
        "route_rejection_count",
    ).fillna(0)
    unfilled_legs = _numeric_column(
        legging,
        "unfilled_leg_count",
    ).fillna(0)
    realized_evaluable = _bool_column(
        legging,
        "realized_edge_evaluable",
        default=False,
    )
    realized_positive = _bool_column(
        legging,
        "realized_edge_positive",
        default=False,
    )
    realized_net_edge = _numeric_column(
        legging,
        "realized_net_edge",
    )
    realized_missing = (
        realized_evaluable & realized_net_edge.isna()
    )
    realized_consistency_violations = (
        realized_positive
        & (
            ~realized_evaluable
            | realized_net_edge.isna()
            | realized_net_edge.le(0.0)
        )
    )
    order_timing = _order_timing_metrics(
        legging,
        order_submissions,
    )
    arrival = _ioc_arrival_metrics(
        legging,
        ioc_arrival_audit,
    )
    return {
        "box_execution_guard_enabled": True,
        "box_execution_max_leg_book_age_ns": int(
            max_leg_book_age_ns
        ),
        "box_execution_max_leg_book_skew_ns": int(
            max_leg_book_skew_ns
        ),
        "box_execution_guard_attempts": int(len(guard)),
        "box_execution_guard_passed_attempts": int(
            passed.sum()
        ),
        "box_execution_guard_deferred_attempts": int(
            (~passed).sum()
        ),
        "box_execution_signal_source_causality_enabled": True,
        "box_execution_signal_source_checked_attempts": int(
            source_checked.sum()
        ),
        "box_execution_signal_source_ready_attempts": int(
            source_ready.sum()
        ),
        "box_execution_signal_source_violations": int(
            (
                passed
                & (
                    ~source_checked
                    | ~source_ready
                )
            ).sum()
        ),
        "box_execution_edge_revalidation_enabled": True,
        "box_execution_edge_revalidation_attempts": int(
            edge_checked.sum()
        ),
        "box_execution_edge_revalidation_missing_attempts": int(
            (preflight_attempted & ~edge_checked).sum()
        ),
        "box_execution_edge_rejected_attempts": int(
            reasons.eq(
                "execution_edge_below_threshold"
            ).sum()
        ),
        "box_execution_ioc_batch_preflight_enabled": True,
        "box_execution_ioc_batch_preflight_attempts": int(
            preflight_attempted.sum()
        ),
        "box_execution_ioc_batch_preflight_passed_attempts": int(
            (
                preflight_attempted
                & preflight_passed
            ).sum()
        ),
        "box_execution_ioc_batch_preflight_rejected_attempts": int(
            (
                preflight_attempted
                & ~preflight_passed
            ).sum()
        ),
        "box_execution_signal_expiry_events": int(
            reasons.eq("signal_age_exceeded").sum()
        ),
        "box_execution_stale_book_attempts": int(
            reasons.eq("stale_leg_book").sum()
        ),
        "box_execution_negative_book_age_attempts": int(
            reasons.eq("negative_leg_book_age").sum()
        ),
        "box_execution_skew_attempts": int(
            reasons.eq("leg_book_skew_exceeded").sum()
        ),
        "box_execution_routing_complete_attempts": int(
            (
                passed
                & routing_status.eq("complete")
            ).sum()
        ),
        "box_execution_routing_incomplete_attempts": int(
            (
                passed
                & ~routing_status.eq("complete")
            ).sum()
        ),
        "box_execution_guard_passed_missing_age_rows": int(
            missing_guard_age_rows.sum()
        ),
        "box_execution_guard_age_violations": int(
            (
                leg_ages.lt(0)
                | leg_ages.gt(max_leg_book_age_ns)
            ).any(axis=1).sum()
        ),
        "box_execution_guard_skew_violations": int(
            (
                skew.lt(0)
                | skew.gt(max_leg_book_skew_ns)
            ).sum()
        ),
        "box_execution_max_routed_book_age_ns": (
            int(observed_max_age.max())
            if not observed_max_age.empty
            else 0
        ),
        "box_execution_max_routed_book_skew_ns": (
            int(observed_skew.max())
            if not observed_skew.empty
            else 0
        ),
        "box_execution_count": int(len(legging)),
        "box_execution_complete_count": int(
            (~partial).sum()
        ),
        "box_execution_incomplete_count": int(
            partial.sum()
        ),
        "box_execution_route_rejected_legs": int(
            route_rejections.sum()
        ),
        "box_execution_unfilled_legs": int(
            unfilled_legs.sum()
        ),
        "box_execution_realized_edge_enabled": True,
        "box_execution_realized_edge_evaluable_count": int(
            realized_evaluable.sum()
        ),
        "box_execution_realized_edge_positive_count": int(
            (
                realized_evaluable
                & realized_positive
            ).sum()
        ),
        "box_execution_realized_edge_nonpositive_count": int(
            (
                realized_evaluable
                & ~realized_positive
            ).sum()
        ),
        "box_execution_realized_edge_missing_rows": int(
            realized_missing.sum()
        ),
        "box_execution_realized_edge_consistency_violations": int(
            realized_consistency_violations.sum()
        ),
        "box_execution_total_realized_net_edge": float(
            realized_net_edge.loc[
                realized_evaluable
            ].sum()
        ),
        **order_timing,
        **arrival,
    }


def _order_timing_metrics(
    legging: pd.DataFrame,
    order_submissions: pd.DataFrame,
) -> dict[str, int | bool]:
    submissions = order_submissions.copy()
    if "oid" not in submissions.columns:
        submissions = pd.DataFrame(columns=["oid"])
    submission_oids = pd.to_numeric(
        submissions["oid"],
        errors="coerce",
    )
    missing_legs = 0
    duplicate_legs = 0
    timestamp_violations = 0
    evaluated_legs = 0
    for _, row in legging.iterrows():
        decision_ts = pd.to_numeric(
            row.get("decision_ts_ns"),
            errors="coerce",
        )
        for leg in BOX_LEGS:
            oid = pd.to_numeric(
                row.get(f"{leg}_order_id"),
                errors="coerce",
            )
            if pd.isna(oid):
                missing_legs += 1
                continue
            matched = submissions.loc[
                submission_oids.eq(oid)
            ]
            if len(matched) != 1:
                duplicate_legs += int(len(matched) > 1)
                missing_legs += int(matched.empty)
                continue
            evaluated_legs += 1
            submission = matched.iloc[0]
            submitted_ts = pd.to_numeric(
                submission.get("ts_sent_ns"),
                errors="coerce",
            )
            active_ts = pd.to_numeric(
                submission.get("ts_active_ns"),
                errors="coerce",
            )
            latency_ns = pd.to_numeric(
                submission.get("order_latency_ns"),
                errors="coerce",
            )
            expected_side = pd.to_numeric(
                row.get(f"{leg}_side"),
                errors="coerce",
            )
            expected_qty = pd.to_numeric(
                row.get("requested_qty"),
                errors="coerce",
            )
            expected_price = pd.to_numeric(
                row.get(f"{leg}_limit_price"),
                errors="coerce",
            )
            observed_side = pd.to_numeric(
                submission.get("side"),
                errors="coerce",
            )
            observed_qty = pd.to_numeric(
                submission.get("qty"),
                errors="coerce",
            )
            observed_price = pd.to_numeric(
                submission.get("price"),
                errors="coerce",
            )
            if (
                pd.isna(decision_ts)
                or pd.isna(submitted_ts)
                or pd.isna(active_ts)
                or pd.isna(latency_ns)
                or pd.isna(expected_side)
                or pd.isna(expected_qty)
                or pd.isna(expected_price)
                or pd.isna(observed_side)
                or pd.isna(observed_qty)
                or pd.isna(observed_price)
                or submitted_ts < decision_ts
                or active_ts < submitted_ts
                or latency_ns < 0
                or active_ts - submitted_ts != latency_ns
                or submitted_ts != decision_ts
                or observed_side != expected_side
                or observed_qty != expected_qty
                or abs(observed_price - expected_price) > 1e-9
                or str(
                    submission.get("instrument_id", "")
                ).strip()
                != str(
                    row.get(f"{leg}_instrument_id", "")
                ).strip()
                or str(
                    submission.get("order_type", "")
                ).strip()
                != "IOC"
            ):
                timestamp_violations += 1
    return {
        "box_execution_order_timing_enabled": True,
        "box_execution_order_timing_evaluable_legs": (
            evaluated_legs
        ),
        "box_execution_order_timing_missing_evidence_legs": (
            missing_legs
        ),
        "box_execution_order_timing_duplicate_evidence_legs": (
            duplicate_legs
        ),
        "box_execution_order_timing_consistency_violations": (
            timestamp_violations
        ),
    }


def _ioc_arrival_metrics(
    legging: pd.DataFrame,
    ioc_arrival_audit: pd.DataFrame,
) -> dict[str, int | bool]:
    audit = ioc_arrival_audit.copy()
    if "oid" not in audit.columns:
        audit = pd.DataFrame(columns=["oid"])
    audit_oids = pd.to_numeric(
        audit["oid"],
        errors="coerce",
    )
    missing_legs = 0
    duplicate_legs = 0
    consistency_violations = 0
    evaluated_legs = 0
    for _, row in legging.iterrows():
        for leg in BOX_LEGS:
            oid = pd.to_numeric(
                row.get(f"{leg}_order_id"),
                errors="coerce",
            )
            if pd.isna(oid):
                missing_legs += 1
                continue
            matched = audit.loc[audit_oids.eq(oid)]
            if len(matched) != 1:
                duplicate_legs += int(len(matched) > 1)
                missing_legs += int(matched.empty)
                continue
            evaluated_legs += 1
            arrival = matched.iloc[0]
            requested = pd.to_numeric(
                arrival.get("requested_qty"),
                errors="coerce",
            )
            filled = pd.to_numeric(
                arrival.get("filled_qty"),
                errors="coerce",
            )
            leg_filled = pd.to_numeric(
                row.get(f"{leg}_filled_qty"),
                errors="coerce",
            )
            if (
                pd.isna(requested)
                or pd.isna(filled)
                or pd.isna(leg_filled)
                or requested <= 0
                or filled < 0
                or filled > requested
                or filled != leg_filled
            ):
                consistency_violations += 1
    return {
        "box_execution_ioc_arrival_audit_enabled": True,
        "box_execution_ioc_arrival_evaluable_legs": (
            evaluated_legs
        ),
        "box_execution_ioc_arrival_missing_evidence_legs": (
            missing_legs
        ),
        "box_execution_ioc_arrival_duplicate_evidence_legs": (
            duplicate_legs
        ),
        "box_execution_ioc_arrival_consistency_violations": (
            consistency_violations
        ),
    }


def _latency_sampling_metrics(
    feed_deliveries: pd.DataFrame,
    order_submissions: pd.DataFrame,
    *,
    feed_latency_us: float,
    order_latency_us: float,
    latency_jitter_us: float,
    latency_seed: int,
) -> dict[str, int | float | bool]:
    feed_min_ns, feed_max_ns = _latency_bounds_ns(
        feed_latency_us,
        latency_jitter_us,
    )
    order_min_ns, order_max_ns = _latency_bounds_ns(
        order_latency_us,
        latency_jitter_us,
    )
    feed_metrics = _sampled_latency_metrics(
        feed_deliveries,
        column="feed_latency_ns",
        minimum_ns=feed_min_ns,
        maximum_ns=feed_max_ns,
    )
    order_metrics = _sampled_latency_metrics(
        order_submissions,
        column="order_latency_ns",
        minimum_ns=order_min_ns,
        maximum_ns=order_max_ns,
    )
    return {
        "box_latency_sampling_audit_enabled": True,
        "box_latency_jitter_us": float(latency_jitter_us),
        "box_latency_seed": int(latency_seed),
        "box_expected_min_feed_latency_ns": feed_min_ns,
        "box_expected_max_feed_latency_ns": feed_max_ns,
        "box_feed_latency_samples": feed_metrics["samples"],
        "box_feed_latency_missing_rows": feed_metrics[
            "missing_rows"
        ],
        "box_feed_latency_bound_violations": feed_metrics[
            "bound_violations"
        ],
        "box_min_sampled_feed_latency_ns": feed_metrics[
            "minimum_sampled_ns"
        ],
        "box_max_sampled_feed_latency_ns": feed_metrics[
            "maximum_sampled_ns"
        ],
        "box_expected_min_order_latency_ns": order_min_ns,
        "box_expected_max_order_latency_ns": order_max_ns,
        "box_order_latency_samples": order_metrics["samples"],
        "box_order_latency_missing_rows": order_metrics[
            "missing_rows"
        ],
        "box_order_latency_bound_violations": order_metrics[
            "bound_violations"
        ],
        "box_min_sampled_order_latency_ns": order_metrics[
            "minimum_sampled_ns"
        ],
        "box_max_sampled_order_latency_ns": order_metrics[
            "maximum_sampled_ns"
        ],
    }


def _latency_bounds_ns(
    base_latency_us: float,
    jitter_us: float,
) -> tuple[int, int]:
    return (
        int(
            max(
                float(base_latency_us) - float(jitter_us),
                0.0,
            )
            * 1_000
        ),
        int(
            (
                float(base_latency_us)
                + float(jitter_us)
            )
            * 1_000
        ),
    )


def _sampled_latency_metrics(
    frame: pd.DataFrame,
    *,
    column: str,
    minimum_ns: int,
    maximum_ns: int,
) -> dict[str, int]:
    if column not in frame.columns:
        return {
            "samples": int(len(frame)),
            "missing_rows": int(len(frame)),
            "bound_violations": int(len(frame)),
            "minimum_sampled_ns": 0,
            "maximum_sampled_ns": 0,
        }
    values = pd.to_numeric(
        frame[column],
        errors="coerce",
    )
    missing = values.isna()
    nonintegral = values.mod(1).ne(0)
    violations = (
        missing
        | nonintegral
        | values.lt(minimum_ns)
        | values.gt(maximum_ns)
    )
    sampled = values.loc[~missing]
    return {
        "samples": int(len(frame)),
        "missing_rows": int(missing.sum()),
        "bound_violations": int(violations.sum()),
        "minimum_sampled_ns": (
            int(sampled.min()) if not sampled.empty else 0
        ),
        "maximum_sampled_ns": (
            int(sampled.max()) if not sampled.empty else 0
        ),
    }


def _build_instruments(
    *,
    chain: pd.DataFrame,
    lot_size: int,
    option_tick: float,
    option_costs: IndianCostModel,
    max_position_lots: int,
) -> tuple[dict[str, InstrumentConfig], BoxLegMap]:
    instruments: dict[str, InstrumentConfig] = {}
    call_by_contract: dict[tuple[str, float], str] = {}
    put_by_contract: dict[tuple[str, float], str] = {}
    grouped = chain.groupby(
        ["expiry", "strike"],
        sort=True,
    )
    for (expiry, strike), group in grouped:
        expiry_text = str(expiry)
        strike_float = float(strike)
        contract_key = (
            expiry_text,
            strike_float,
        )
        suffix = (
            f"{_expiry_label(expiry_text)}_"
            f"{_strike_label(strike_float)}"
        )
        call_id = f"CALL_{suffix}"
        put_id = f"PUT_{suffix}"
        if (
            call_id in instruments
            or put_id in instruments
        ):
            raise ValueError(
                "option contract labels collide after "
                f"normalization: {contract_key}"
            )
        call_by_contract[contract_key] = call_id
        put_by_contract[contract_key] = put_id
        instruments[call_id] = InstrumentConfig(
            Instrument(
                call_id,
                Kind.OPT,
                lot_size=lot_size,
                tick=option_tick,
            ),
            "NSE",
            _option_side_book(group, "call"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
        instruments[put_id] = InstrumentConfig(
            Instrument(
                put_id,
                Kind.OPT,
                lot_size=lot_size,
                tick=option_tick,
            ),
            "NSE",
            _option_side_book(group, "put"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
    return instruments, BoxLegMap(
        call_by_contract=call_by_contract,
        put_by_contract=put_by_contract,
    )


def _option_side_book(
    group: pd.DataFrame,
    side: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": group["ts"].to_numpy(),
            "bid": group[f"{side}_bid"].to_numpy(),
            "ask": group[f"{side}_ask"].to_numpy(),
            "bid_qty": group[
                f"{side}_bid_qty"
            ].to_numpy(),
            "ask_qty": group[
                f"{side}_ask_qty"
            ].to_numpy(),
            "last": np.nan,
            "last_qty": 0,
        }
    )


def _expiry_label(expiry: str) -> str:
    return "".join(
        character if character.isalnum() else "_"
        for character in expiry
    )


def _strike_label(strike: float) -> str:
    return str(strike).replace(".", "_")


def _bool_column(
    frame: pd.DataFrame,
    column: str,
    *,
    default: bool,
) -> pd.Series:
    raw = frame.get(
        column,
        pd.Series(default, index=frame.index),
    )
    return raw.fillna(default).astype(bool)


def _text_column(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    return (
        frame.get(
            column,
            pd.Series("", index=frame.index),
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )


def _numeric_column(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    return pd.to_numeric(
        frame.get(
            column,
            pd.Series(
                index=frame.index,
                dtype="float64",
            ),
        ),
        errors="coerce",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay executable four-leg box scanner signals."
        )
    )
    parser.add_argument("--chain", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--timestamp-unit",
        default="ns",
        choices=[
            "ns",
            "us",
            "ms",
            "s",
            "datetime",
        ],
    )
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument(
        "--no-filter-session",
        action="store_true",
    )
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument(
        "--depth-fraction",
        type=float,
        default=0.25,
    )
    parser.add_argument(
        "--fair-value-adjustment",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--feed-latency-us",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--order-latency-us",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--latency-jitter-us",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--latency-seed",
        type=int,
        default=17,
    )
    parser.add_argument(
        "--max-signal-age-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument(
        "--max-leg-book-age-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument(
        "--max-leg-book-skew-ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument("--max-qty", type=int, default=None)
    parser.add_argument(
        "--signal-limit",
        type=int,
        default=None,
    )
    args = parser.parse_args(argv)
    replay = run_box_replay(
        chain_path=args.chain,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        depth_fraction=args.depth_fraction,
        fair_value_adjustment=args.fair_value_adjustment,
        feed_latency_us=args.feed_latency_us,
        order_latency_us=args.order_latency_us,
        latency_jitter_us=args.latency_jitter_us,
        latency_seed=args.latency_seed,
        max_signal_age_ns=args.max_signal_age_ns,
        max_leg_book_age_ns=args.max_leg_book_age_ns,
        max_leg_book_skew_ns=args.max_leg_book_skew_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
    )
    print(replay.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
