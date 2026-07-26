from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.proof import (
    ProofReport,
    ProofThresholds,
    write_proof_report,
)
from strategies.run_box_replay import run_box_replay


BOX_SWEEP_RUN_TYPE = "box_sweep"
BOX_SWEEP_REQUIRED_ARTIFACTS = (
    "sweep_runs.csv",
    "sweep_summary.csv",
    "latency_seed_robustness.csv",
    "proof/proof_metrics.csv",
    "proof/proof_checks.csv",
    "proof/proof_summary.csv",
)


@dataclass(frozen=True)
class BoxSweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    seed_robustness: pd.DataFrame
    output_dir: Path


def run_box_sweep(
    *,
    chain_path: str | Path,
    output_dir: str | Path,
    depth_fraction_values: list[float],
    fair_value_adjustment_values: list[float],
    feed_latency_us_values: list[float],
    order_latency_us_values: list[float],
    latency_jitter_us_values: list[float] | None = None,
    latency_seed: int = 17,
    latency_seed_values: list[int] | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    max_signal_age_ns: int = 1_000_000,
    max_leg_book_age_ns: int = 1_000_000,
    max_leg_book_skew_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
    proof_thresholds: ProofThresholds | None = None,
) -> BoxSweepResult:
    depth_fraction_values = _finite_values(
        depth_fraction_values,
        name="depth_fraction_values",
        minimum=0.0,
        minimum_inclusive=False,
        maximum=1.0,
    )
    fair_value_adjustment_values = _finite_values(
        fair_value_adjustment_values,
        name="fair_value_adjustment_values",
    )
    feed_latency_us_values = _finite_values(
        feed_latency_us_values,
        name="feed_latency_us_values",
        minimum=0.0,
    )
    order_latency_us_values = _finite_values(
        order_latency_us_values,
        name="order_latency_us_values",
        minimum=0.0,
    )
    latency_jitter_us_values = _finite_values(
        [0.0]
        if latency_jitter_us_values is None
        else latency_jitter_us_values,
        name="latency_jitter_us_values",
        minimum=0.0,
    )
    seeds = _latency_seeds(
        [latency_seed]
        if latency_seed_values is None
        else latency_seed_values
    )
    include_seed = len(seeds) > 1

    out = Path(output_dir)
    runs_root = out / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    run_dirs: list[Path] = []
    run_names: list[str] = []
    for (
        depth_fraction,
        fair_value_adjustment,
        feed_latency_us,
        order_latency_us,
        latency_jitter_us,
        scenario_seed,
    ) in product(
        depth_fraction_values,
        fair_value_adjustment_values,
        feed_latency_us_values,
        order_latency_us_values,
        latency_jitter_us_values,
        seeds,
    ):
        seed_group = _run_name(
            depth_fraction,
            fair_value_adjustment,
            feed_latency_us,
            order_latency_us,
            latency_jitter_us,
        )
        run_name = _run_name(
            depth_fraction,
            fair_value_adjustment,
            feed_latency_us,
            order_latency_us,
            latency_jitter_us,
            latency_seed=scenario_seed,
            include_seed=include_seed,
        )
        run_dir = runs_root / run_name
        replay = run_box_replay(
            chain_path=chain_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            lot_size=lot_size,
            option_tick=option_tick,
            depth_fraction=depth_fraction,
            fair_value_adjustment=fair_value_adjustment,
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
            latency_jitter_us=latency_jitter_us,
            latency_seed=scenario_seed,
            max_signal_age_ns=max_signal_age_ns,
            max_leg_book_age_ns=max_leg_book_age_ns,
            max_leg_book_skew_ns=max_leg_book_skew_ns,
            max_qty=max_qty,
            max_position_lots=max_position_lots,
            signal_limit=signal_limit,
        )
        rows.append(
            {
                "run": run_name,
                "run_dir": str(run_dir.resolve()),
                "depth_fraction": depth_fraction,
                "fair_value_adjustment": (
                    fair_value_adjustment
                ),
                "feed_latency_us": feed_latency_us,
                "order_latency_us": order_latency_us,
                "latency_jitter_us": latency_jitter_us,
                "latency_seed": scenario_seed,
                "latency_seed_group": seed_group,
                "signal_count": int(len(replay.signals)),
                **replay.summary.iloc[0].to_dict(),
            }
        )
        run_dirs.append(run_dir)
        run_names.append(run_name)

    effective_thresholds = proof_thresholds or ProofThresholds(
        min_net_pnl=-1_000_000_000_000.0,
        min_fills=1,
    )
    proof = write_proof_report(
        run_dirs,
        output_dir=out / "proof",
        thresholds=effective_thresholds,
        run_names=run_names,
    )
    runs = _merge_proof(pd.DataFrame(rows), proof)
    seed_robustness = _seed_robustness(
        runs,
        expected_seed_runs=len(seeds),
    )
    summary = _summary(runs, seed_robustness)
    runs.to_csv(out / "sweep_runs.csv", index=False)
    seed_robustness.to_csv(
        out / "latency_seed_robustness.csv",
        index=False,
    )
    summary.to_csv(out / "sweep_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type=BOX_SWEEP_RUN_TYPE,
        inputs={"chain": chain_path},
        parameters={
            "market": INDIA_NSE_INDEX_DERIVATIVES.name,
            "depth_fraction_values": depth_fraction_values,
            "fair_value_adjustment_values": (
                fair_value_adjustment_values
            ),
            "feed_latency_us_values": feed_latency_us_values,
            "order_latency_us_values": order_latency_us_values,
            "latency_jitter_us_values": (
                latency_jitter_us_values
            ),
            "latency_seed": (
                seeds[0] if len(seeds) == 1 else None
            ),
            "latency_seed_values": seeds,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "lot_size": lot_size,
            "option_tick": option_tick,
            "max_signal_age_ns": max_signal_age_ns,
            "max_leg_book_age_ns": max_leg_book_age_ns,
            "max_leg_book_skew_ns": max_leg_book_skew_ns,
            "max_qty": max_qty,
            "max_position_lots": max_position_lots,
            "signal_limit": signal_limit,
            "proof_thresholds": effective_thresholds.__dict__,
        },
    )
    return BoxSweepResult(
        runs=runs,
        summary=summary,
        proof=proof,
        seed_robustness=seed_robustness,
        output_dir=out,
    )


def _merge_proof(
    runs: pd.DataFrame,
    proof: ProofReport,
) -> pd.DataFrame:
    proof_passed = (
        proof.checks.groupby("run", dropna=False)["passed"]
        .all()
        .rename("proof_passed")
        .reset_index()
    )
    validated_columns = [
        column
        for column in proof.metrics.columns
        if column != "run"
    ]
    base = runs.drop(
        columns=[
            column
            for column in validated_columns
            if column in runs.columns
        ]
    )
    merged = (
        base.merge(proof.metrics, on="run", how="left")
        .merge(proof_passed, on="run", how="left")
    )
    merged["proof_passed"] = (
        merged["proof_passed"].fillna(False).astype(bool)
    )
    merged["robust_score"] = (
        pd.to_numeric(
            merged[
                "box_execution_total_realized_net_edge"
            ],
            errors="coerce",
        ).fillna(0.0)
        - 1_000_000.0
        * pd.to_numeric(
            merged["box_execution_incomplete_count"],
            errors="coerce",
        ).fillna(0.0)
    )
    return merged


def _seed_robustness(
    runs: pd.DataFrame,
    *,
    expected_seed_runs: int,
) -> pd.DataFrame:
    columns = [
        "latency_seed_group",
        "depth_fraction",
        "fair_value_adjustment",
        "feed_latency_us",
        "order_latency_us",
        "latency_jitter_us",
        "latency_seed_values",
        "latency_seed_runs",
        "latency_seed_expected_runs",
        "latency_seed_count",
        "latency_seed_passed_runs",
        "latency_seed_pass_rate",
        "latency_seed_group_passed",
        "latency_seed_worst_run",
        "latency_seed_worst_seed",
        "latency_seed_worst_robust_score",
        "latency_seed_worst_total_realized_net_edge",
        "latency_seed_worst_min_realized_net_edge",
        "latency_seed_max_incomplete_executions",
        "latency_seed_bound_violations",
    ]
    rows: list[dict[str, object]] = []
    for seed_group, group in runs.groupby(
        "latency_seed_group",
        sort=False,
        dropna=False,
    ):
        work = group.copy()
        seeds = sorted(
            pd.to_numeric(
                work["latency_seed"],
                errors="coerce",
            )
            .dropna()
            .astype(int)
            .unique()
            .tolist()
        )
        passed = work["proof_passed"].astype(bool)
        bound_violations = sum(
            _sum_int(work, column)
            for column in [
                "box_feed_latency_bound_violations",
                "box_order_latency_bound_violations",
                "box_latency_configuration_violations",
            ]
        )
        worst = work.sort_values(
            [
                "robust_score",
                "box_execution_min_realized_net_edge",
                "run",
            ],
            ascending=[True, True, True],
            kind="stable",
        ).iloc[0]
        first = work.iloc[0]
        seed_runs = int(len(work))
        seed_count = int(len(seeds))
        group_passed = bool(
            seed_runs == expected_seed_runs
            and seed_count == expected_seed_runs
            and passed.all()
            and bound_violations == 0
        )
        rows.append(
            {
                "latency_seed_group": str(seed_group),
                "depth_fraction": float(
                    first["depth_fraction"]
                ),
                "fair_value_adjustment": float(
                    first["fair_value_adjustment"]
                ),
                "feed_latency_us": float(
                    first["feed_latency_us"]
                ),
                "order_latency_us": float(
                    first["order_latency_us"]
                ),
                "latency_jitter_us": float(
                    first["latency_jitter_us"]
                ),
                "latency_seed_values": ",".join(
                    str(seed) for seed in seeds
                ),
                "latency_seed_runs": seed_runs,
                "latency_seed_expected_runs": (
                    expected_seed_runs
                ),
                "latency_seed_count": seed_count,
                "latency_seed_passed_runs": int(
                    passed.sum()
                ),
                "latency_seed_pass_rate": float(
                    passed.mean()
                ),
                "latency_seed_group_passed": group_passed,
                "latency_seed_worst_run": str(worst["run"]),
                "latency_seed_worst_seed": int(
                    worst["latency_seed"]
                ),
                "latency_seed_worst_robust_score": float(
                    worst["robust_score"]
                ),
                "latency_seed_worst_total_realized_net_edge": (
                    float(
                        worst[
                            "box_execution_total_realized_net_edge"
                        ]
                    )
                ),
                "latency_seed_worst_min_realized_net_edge": (
                    float(
                        worst[
                            "box_execution_min_realized_net_edge"
                        ]
                    )
                ),
                "latency_seed_max_incomplete_executions": int(
                    pd.to_numeric(
                        work[
                            "box_execution_incomplete_count"
                        ],
                        errors="coerce",
                    )
                    .fillna(0)
                    .max()
                ),
                "latency_seed_bound_violations": int(
                    bound_violations
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _summary(
    runs: pd.DataFrame,
    seed_robustness: pd.DataFrame,
) -> pd.DataFrame:
    passed = runs["proof_passed"].astype(bool)
    best = runs.sort_values(
        ["robust_score", "run"],
        ascending=[False, True],
        kind="stable",
    ).iloc[0]
    group_passed = seed_robustness[
        "latency_seed_group_passed"
    ].astype(bool)
    best_group = seed_robustness.sort_values(
        [
            "latency_seed_group_passed",
            "latency_seed_worst_robust_score",
            "latency_seed_group",
        ],
        ascending=[False, False, True],
        kind="stable",
    ).iloc[0]
    return pd.DataFrame(
        [
            {
                "scenario_count": int(len(runs)),
                "passed_scenarios": int(passed.sum()),
                "pass_rate": float(passed.mean()),
                "best_run": str(best["run"]),
                "best_robust_score": float(
                    best["robust_score"]
                ),
                "median_total_realized_net_edge": float(
                    runs[
                        "box_execution_total_realized_net_edge"
                    ].median()
                ),
                "min_total_realized_net_edge": float(
                    runs[
                        "box_execution_total_realized_net_edge"
                    ].min()
                ),
                "min_package_realized_net_edge": float(
                    runs[
                        "box_execution_min_realized_net_edge"
                    ].min()
                ),
                "total_signals": _sum_int(
                    runs,
                    "box_execution_signal_count",
                ),
                "total_executions": _sum_int(
                    runs,
                    "box_execution_count",
                ),
                "total_complete_executions": _sum_int(
                    runs,
                    "box_execution_complete_count",
                ),
                "total_incomplete_executions": _sum_int(
                    runs,
                    "box_execution_incomplete_count",
                ),
                "total_guard_consistency_violations": _sum_int(
                    runs,
                    "box_execution_guard_consistency_violations",
                ),
                "total_fill_consistency_violations": _sum_int(
                    runs,
                    (
                        "box_execution_fill_evidence_"
                        "consistency_violations"
                    ),
                ),
                "total_realized_edge_consistency_violations": (
                    _sum_int(
                        runs,
                        (
                            "box_execution_realized_edge_"
                            "consistency_violations"
                        ),
                    )
                ),
                "latency_seed_group_count": int(
                    len(seed_robustness)
                ),
                "latency_seed_passed_groups": int(
                    group_passed.sum()
                ),
                "latency_seed_group_pass_rate": float(
                    group_passed.mean()
                ),
                "best_latency_seed_group": str(
                    best_group["latency_seed_group"]
                ),
                "best_latency_seed_worst_run": str(
                    best_group["latency_seed_worst_run"]
                ),
                "best_latency_seed_worst_robust_score": float(
                    best_group[
                        "latency_seed_worst_robust_score"
                    ]
                ),
            }
        ]
    )


def _sum_int(frame: pd.DataFrame, column: str) -> int:
    return int(
        pd.to_numeric(
            frame.get(
                column,
                pd.Series(0, index=frame.index),
            ),
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )


def _run_name(
    depth_fraction: float,
    fair_value_adjustment: float,
    feed_latency_us: float,
    order_latency_us: float,
    latency_jitter_us: float,
    *,
    latency_seed: int = 17,
    include_seed: bool = False,
) -> str:
    name = (
        f"depth_{_label(depth_fraction)}"
        f"__fair_{_label(fair_value_adjustment)}"
        f"__feed_{_label(feed_latency_us)}us"
        f"__order_{_label(order_latency_us)}us"
        f"__jitter_{_label(latency_jitter_us)}us"
    )
    if include_seed:
        name += f"__seed_{latency_seed}"
    return name


def _label(value: float) -> str:
    return (
        f"{float(value):g}"
        .replace("-", "m")
        .replace(".", "p")
    )


def _finite_values(
    values: list[float],
    *,
    name: str,
    minimum: float | None = None,
    minimum_inclusive: bool = True,
    maximum: float | None = None,
) -> list[float]:
    if not values:
        raise ValueError(f"{name} must not be empty")
    normalized = [float(value) for value in values]
    for value in normalized:
        invalid_minimum = (
            minimum is not None
            and (
                value < minimum
                if minimum_inclusive
                else value <= minimum
            )
        )
        if (
            not math.isfinite(value)
            or invalid_minimum
            or (
                maximum is not None
                and value > maximum
            )
        ):
            raise ValueError(f"{name} contains invalid value {value}")
    return normalized


def _latency_seeds(values: list[int]) -> list[int]:
    if not values:
        raise ValueError("latency_seed_values must not be empty")
    seeds: list[int] = []
    for value in values:
        numeric = float(value)
        if (
            not math.isfinite(numeric)
            or numeric < 0
            or numeric % 1 != 0
        ):
            raise ValueError(
                "latency_seed_values must contain "
                "non-negative integers"
            )
        seeds.append(int(numeric))
    if len(set(seeds)) != len(seeds):
        raise ValueError("latency_seed_values must be unique")
    return seeds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a four-leg box replay robustness sweep."
        )
    )
    parser.add_argument("--chain", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--depth-fraction",
        nargs="+",
        required=True,
        type=float,
    )
    parser.add_argument(
        "--fair-value-adjustment",
        nargs="+",
        default=[0.0],
        type=float,
    )
    parser.add_argument(
        "--feed-latency-us",
        nargs="+",
        default=[0.0],
        type=float,
    )
    parser.add_argument(
        "--order-latency-us",
        nargs="+",
        default=[0.0],
        type=float,
    )
    parser.add_argument(
        "--latency-jitter-us",
        nargs="+",
        default=[0.0],
        type=float,
    )
    parser.add_argument("--latency-seed", type=int, default=17)
    parser.add_argument(
        "--latency-seeds",
        nargs="+",
        type=int,
    )
    parser.add_argument(
        "--timestamp-unit",
        default="ns",
        choices=["ns", "us", "ms", "s", "datetime"],
    )
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument(
        "--no-filter-session",
        action="store_true",
    )
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--option-tick", type=float, default=0.05)
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
    parser.add_argument("--signal-limit", type=int, default=None)
    parser.add_argument(
        "--min-net-pnl",
        type=float,
        default=-1_000_000_000_000.0,
    )
    parser.add_argument("--min-fills", type=int, default=1)
    parser.add_argument(
        "--max-drawdown",
        type=float,
        default=None,
    )
    parser.add_argument("--max-otr", type=float, default=None)
    parser.add_argument("--fail-on-breach", action="store_true")
    args = parser.parse_args(argv)

    result = run_box_sweep(
        chain_path=args.chain,
        output_dir=args.out,
        depth_fraction_values=args.depth_fraction,
        fair_value_adjustment_values=(
            args.fair_value_adjustment
        ),
        feed_latency_us_values=args.feed_latency_us,
        order_latency_us_values=args.order_latency_us,
        latency_jitter_us_values=args.latency_jitter_us,
        latency_seed=args.latency_seed,
        latency_seed_values=args.latency_seeds,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        option_tick=args.option_tick,
        max_signal_age_ns=args.max_signal_age_ns,
        max_leg_book_age_ns=args.max_leg_book_age_ns,
        max_leg_book_skew_ns=args.max_leg_book_skew_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
        proof_thresholds=ProofThresholds(
            min_net_pnl=args.min_net_pnl,
            min_fills=args.min_fills,
            max_drawdown=args.max_drawdown,
            max_otr=args.max_otr,
        ),
    )
    print(result.summary.to_string(index=False))
    return (
        2
        if args.fail_on_breach
        and not bool(result.proof.passed)
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
