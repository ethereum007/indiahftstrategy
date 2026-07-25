from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_imbalance_replay import run_imbalance_replay


@dataclass(frozen=True)
class ImbalanceSweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    output_dir: Path | None = None


def run_imbalance_sweep(
    *,
    ticks_path: str | Path,
    output_dir: str | Path,
    entry_imbalance_values: list[float],
    min_microprice_edge_ticks_values: list[float],
    hold_ns_values: list[int],
    feed_latency_us_values: list[float],
    order_latency_us_values: list[float],
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    instrument_id: str = "BOOK",
    instrument_kind: str = "OPT",
    lot_size: int = 75,
    tick_size: float = 0.05,
    qty: int = 75,
    exit_imbalance: float = 0.15,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    cooloff_ns: int = 0,
    generic_buy_notional_rate: float = 0.0,
    generic_sell_notional_rate: float = 0.0,
    generic_per_unit_fee: float = 0.0,
    generic_per_contract_fee: float = 0.0,
    generic_per_order_fee: float = 0.0,
    max_position_lots: int = 20,
    markout_horizons_ns: list[int] | None = None,
    proof_thresholds: ProofThresholds | None = None,
) -> ImbalanceSweepResult:
    if not entry_imbalance_values:
        raise ValueError("entry_imbalance_values must not be empty")
    if not min_microprice_edge_ticks_values:
        raise ValueError("min_microprice_edge_ticks_values must not be empty")
    if not hold_ns_values:
        raise ValueError("hold_ns_values must not be empty")
    if not feed_latency_us_values:
        raise ValueError("feed_latency_us_values must not be empty")
    if not order_latency_us_values:
        raise ValueError("order_latency_us_values must not be empty")

    out = Path(output_dir)
    runs_root = out / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    rows = []
    run_dirs: list[Path] = []
    run_names: list[str] = []
    for entry_imbalance, min_edge, hold_ns, feed_latency_us, order_latency_us in product(
        entry_imbalance_values,
        min_microprice_edge_ticks_values,
        hold_ns_values,
        feed_latency_us_values,
        order_latency_us_values,
    ):
        run_name = _run_name(entry_imbalance, min_edge, hold_ns, feed_latency_us, order_latency_us)
        run_dir = runs_root / run_name
        replay = run_imbalance_replay(
            ticks_path=ticks_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            market=market,
            instrument_id=instrument_id,
            instrument_kind=instrument_kind,
            lot_size=lot_size,
            tick_size=tick_size,
            qty=qty,
            entry_imbalance=entry_imbalance,
            exit_imbalance=exit_imbalance,
            min_microprice_edge_ticks=min_edge,
            max_spread_ticks=max_spread_ticks,
            min_depth=min_depth,
            hold_ns=hold_ns,
            cooloff_ns=cooloff_ns,
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
            generic_buy_notional_rate=generic_buy_notional_rate,
            generic_sell_notional_rate=generic_sell_notional_rate,
            generic_per_unit_fee=generic_per_unit_fee,
            generic_per_contract_fee=generic_per_contract_fee,
            generic_per_order_fee=generic_per_order_fee,
            max_position_lots=max_position_lots,
            markout_horizons_ns=markout_horizons_ns,
        )
        summary = replay.summary.iloc[0].to_dict()
        rows.append(
            {
                "run": run_name,
                "run_dir": str(run_dir),
                "entry_imbalance": float(entry_imbalance),
                "min_microprice_edge_ticks": float(min_edge),
                "hold_ns": int(hold_ns),
                "feed_latency_us": float(feed_latency_us),
                "order_latency_us": float(order_latency_us),
                "signal_count": int(len(replay.signals)),
                **summary,
            }
        )
        run_dirs.append(run_dir)
        run_names.append(run_name)

    proof = write_proof_report(
        run_dirs,
        output_dir=out / "proof",
        thresholds=proof_thresholds or ProofThresholds(),
        run_names=run_names,
    )
    runs = _merge_proof_metrics(pd.DataFrame(rows), proof)
    summary = _sweep_summary(runs)
    runs.to_csv(out / "sweep_runs.csv", index=False)
    summary.to_csv(out / "sweep_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="imbalance_sweep",
        inputs={"ticks": ticks_path},
        parameters={
            "entry_imbalance_values": entry_imbalance_values,
            "min_microprice_edge_ticks_values": min_microprice_edge_ticks_values,
            "hold_ns_values": hold_ns_values,
            "feed_latency_us_values": feed_latency_us_values,
            "order_latency_us_values": order_latency_us_values,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "market": market,
            "instrument_id": instrument_id,
            "instrument_kind": instrument_kind,
            "lot_size": lot_size,
            "tick_size": tick_size,
            "qty": qty,
            "exit_imbalance": exit_imbalance,
            "max_spread_ticks": max_spread_ticks,
            "min_depth": min_depth,
            "cooloff_ns": cooloff_ns,
            "generic_costs": {
                "buy_notional_rate": generic_buy_notional_rate,
                "sell_notional_rate": generic_sell_notional_rate,
                "per_unit_fee": generic_per_unit_fee,
                "per_contract_fee": generic_per_contract_fee,
                "per_order_fee": generic_per_order_fee,
            },
            "max_position_lots": max_position_lots,
            "markout_horizons_ns": markout_horizons_ns,
            "proof_thresholds": asdict(proof_thresholds) if proof_thresholds is not None else None,
        },
    )
    return ImbalanceSweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)


def _merge_proof_metrics(runs: pd.DataFrame, proof: ProofReport) -> pd.DataFrame:
    proof_passed = (
        proof.checks.groupby("run", dropna=False)["passed"]
        .all()
        .rename("proof_passed")
        .reset_index()
    )
    proof_columns = ["run"] + [col for col in proof.metrics.columns if col not in runs.columns and col != "run"]
    proof_metrics = proof.metrics[proof_columns]
    merged = runs.merge(proof_metrics, on="run", how="left").merge(proof_passed, on="run", how="left")
    merged["robust_score"] = (
        merged["net_pnl"].astype(float)
        - merged["max_drawdown"].fillna(0.0).astype(float)
        - merged["total_costs"].fillna(0.0).astype(float)
    )
    return merged


def _sweep_summary(runs: pd.DataFrame) -> pd.DataFrame:
    if runs.empty:
        return pd.DataFrame(
            columns=[
                "scenario_count",
                "passed_scenarios",
                "pass_rate",
                "best_run",
                "best_robust_score",
                "median_net_pnl",
                "min_net_pnl",
                "worst_drawdown",
                "total_signals",
                "median_fill_rate",
                "total_liquidity_shortfall_events",
                "total_liquidity_shortfall_qty",
                "total_carried_depletion_shortfall_events",
                "total_carried_depletion_shortfall_qty",
                "total_limit_orders_sent",
                "total_queue_initialization_events",
                "total_deferred_queue_initialization_events",
                "total_uninitialized_limit_orders",
                "max_queue_initialization_lag_ns",
                "total_residual_resting_transition_events",
                "total_residual_resting_transition_qty",
                "total_deferred_residual_queue_events",
                "total_unresolved_residual_queue_events",
                "max_residual_queue_initialization_lag_ns",
                "total_passive_price_through_events",
                "total_passive_price_through_requested_qty",
                "total_passive_price_through_filled_qty",
                "total_passive_price_through_shortfall_qty",
                "total_passive_price_through_incomplete_events",
                "total_terminal_liquidation_events",
                "total_terminal_liquidation_requested_qty",
                "total_terminal_liquidation_filled_qty",
                "total_terminal_liquidation_shortfall_qty",
                "total_terminal_liquidation_incomplete_events",
                "total_terminal_residual_position_qty",
                "total_terminal_residual_instruments",
                "total_pretrade_rejections",
                "total_position_risk_rejections",
                "total_self_cross_rejections",
            ]
        )
    best = runs.sort_values(["robust_score", "net_pnl"], ascending=False).iloc[0]
    return pd.DataFrame(
        [
            {
                "scenario_count": int(len(runs)),
                "passed_scenarios": int(runs["proof_passed"].fillna(False).sum()),
                "pass_rate": float(runs["proof_passed"].fillna(False).mean()),
                "best_run": best["run"],
                "best_robust_score": float(best["robust_score"]),
                "median_net_pnl": float(runs["net_pnl"].median()),
                "min_net_pnl": float(runs["net_pnl"].min()),
                "worst_drawdown": float(runs["max_drawdown"].max(skipna=True)),
                "total_signals": int(runs["signal_count"].sum()),
                "median_fill_rate": float(runs["fills"].median() / runs["orders_sent"].replace(0, pd.NA).median())
                if runs["orders_sent"].replace(0, pd.NA).notna().any()
                else 0.0,
                "total_liquidity_shortfall_events": int(
                    pd.to_numeric(
                        runs.get(
                            "liquidity_shortfall_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_liquidity_shortfall_qty": int(
                    pd.to_numeric(
                        runs.get(
                            "liquidity_shortfall_qty",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_carried_depletion_shortfall_events": int(
                    pd.to_numeric(
                        runs.get(
                            "carried_depletion_shortfall_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_carried_depletion_shortfall_qty": int(
                    pd.to_numeric(
                        runs.get(
                            "carried_depletion_shortfall_qty",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_limit_orders_sent": int(
                    pd.to_numeric(
                        runs.get(
                            "limit_orders_sent",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_queue_initialization_events": int(
                    pd.to_numeric(
                        runs.get(
                            "queue_initialization_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_deferred_queue_initialization_events": int(
                    pd.to_numeric(
                        runs.get(
                            "deferred_queue_initialization_events",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "total_uninitialized_limit_orders": int(
                    pd.to_numeric(
                        runs.get(
                            "uninitialized_limit_orders",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).sum()
                ),
                "max_queue_initialization_lag_ns": int(
                    pd.to_numeric(
                        runs.get(
                            "max_queue_initialization_lag_ns",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).max()
                ),
                "total_residual_resting_transition_events": _sum_int_metric(
                    runs,
                    "residual_resting_transition_events",
                ),
                "total_residual_resting_transition_qty": _sum_int_metric(
                    runs,
                    "residual_resting_transition_qty",
                ),
                "total_deferred_residual_queue_events": _sum_int_metric(
                    runs,
                    "deferred_residual_queue_events",
                ),
                "total_unresolved_residual_queue_events": _sum_int_metric(
                    runs,
                    "unresolved_residual_queue_events",
                ),
                "max_residual_queue_initialization_lag_ns": int(
                    pd.to_numeric(
                        runs.get(
                            "max_residual_queue_initialization_lag_ns",
                            pd.Series(0, index=runs.index),
                        ),
                        errors="coerce",
                    ).fillna(0).max()
                ),
                "total_passive_price_through_events": _sum_int_metric(
                    runs,
                    "passive_price_through_events",
                ),
                "total_passive_price_through_requested_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_requested_qty",
                ),
                "total_passive_price_through_filled_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_filled_qty",
                ),
                "total_passive_price_through_shortfall_qty": _sum_int_metric(
                    runs,
                    "passive_price_through_shortfall_qty",
                ),
                "total_passive_price_through_incomplete_events": _sum_int_metric(
                    runs,
                    "passive_price_through_incomplete_events",
                ),
                "total_terminal_liquidation_events": _sum_int_metric(
                    runs,
                    "terminal_liquidation_events",
                ),
                "total_terminal_liquidation_requested_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_requested_qty",
                ),
                "total_terminal_liquidation_filled_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_filled_qty",
                ),
                "total_terminal_liquidation_shortfall_qty": _sum_int_metric(
                    runs,
                    "terminal_liquidation_shortfall_qty",
                ),
                "total_terminal_liquidation_incomplete_events": _sum_int_metric(
                    runs,
                    "terminal_liquidation_incomplete_events",
                ),
                "total_terminal_residual_position_qty": _sum_int_metric(
                    runs,
                    "terminal_residual_position_qty",
                ),
                "total_terminal_residual_instruments": _sum_int_metric(
                    runs,
                    "terminal_residual_instruments",
                ),
                "total_pretrade_rejections": int(
                    runs["pretrade_rejections"].sum()
                ),
                "total_position_risk_rejections": int(
                    runs["position_risk_rejections"].sum()
                ),
                "total_self_cross_rejections": int(
                    runs["self_cross_rejections"].sum()
                ),
            }
        ]
    )


def _sum_int_metric(runs: pd.DataFrame, column: str) -> int:
    values = runs.get(column, pd.Series(0, index=runs.index))
    return int(pd.to_numeric(values, errors="coerce").fillna(0).sum())


def _run_name(
    entry_imbalance: float,
    min_edge: float,
    hold_ns: int,
    feed_latency_us: float,
    order_latency_us: float,
) -> str:
    return (
        f"imb_{_label_number(entry_imbalance)}"
        f"__edge_{_label_number(min_edge)}"
        f"__hold_{int(hold_ns)}ns"
        f"__feed_{_label_number(feed_latency_us)}us"
        f"__order_{_label_number(order_latency_us)}us"
    )


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _float_list(values: list[str]) -> list[float]:
    return [float(value) for value in values]


def _int_list(values: list[str] | None) -> list[int] | None:
    return [int(value) for value in values] if values is not None else None


def _required_int_list(values: list[str]) -> list[int]:
    return [int(value) for value in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a microprice imbalance replay robustness sweep.")
    parser.add_argument("--ticks", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    parser.add_argument("--instrument-id", default="BOOK")
    parser.add_argument("--instrument-kind", default="OPT", choices=["FUT", "OPT", "EQ"])
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--tick-size", type=float, default=0.05)
    parser.add_argument("--qty", type=int, default=75)
    parser.add_argument("--entry-imbalance", nargs="+", required=True)
    parser.add_argument("--exit-imbalance", type=float, default=0.15)
    parser.add_argument("--min-microprice-edge-ticks", nargs="+", required=True)
    parser.add_argument("--max-spread-ticks", type=float, default=2.0)
    parser.add_argument("--min-depth", type=int, default=1)
    parser.add_argument("--hold-ns", nargs="+", required=True)
    parser.add_argument("--cooloff-ns", type=int, default=0)
    parser.add_argument("--feed-latency-us", nargs="+", default=["0"])
    parser.add_argument("--order-latency-us", nargs="+", default=["0"])
    parser.add_argument("--generic-buy-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-sell-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-per-unit-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-contract-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-order-fee", type=float, default=0.0)
    parser.add_argument("--markout-horizons-ns", nargs="+", default=None)
    parser.add_argument("--min-net-pnl", type=float, default=0.0)
    parser.add_argument("--min-fills", type=int, default=1)
    parser.add_argument("--max-drawdown", type=float, default=None)
    parser.add_argument("--max-otr", type=float, default=None)
    parser.add_argument("--min-markout-mean", type=float, default=None)
    parser.add_argument("--fail-on-breach", action="store_true")
    args = parser.parse_args(argv)

    result = run_imbalance_sweep(
        ticks_path=args.ticks,
        output_dir=args.out,
        entry_imbalance_values=_float_list(args.entry_imbalance),
        min_microprice_edge_ticks_values=_float_list(args.min_microprice_edge_ticks),
        hold_ns_values=_required_int_list(args.hold_ns),
        feed_latency_us_values=_float_list(args.feed_latency_us),
        order_latency_us_values=_float_list(args.order_latency_us),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        market=args.market,
        instrument_id=args.instrument_id,
        instrument_kind=args.instrument_kind,
        lot_size=args.lot_size,
        tick_size=args.tick_size,
        qty=args.qty,
        exit_imbalance=args.exit_imbalance,
        max_spread_ticks=args.max_spread_ticks,
        min_depth=args.min_depth,
        cooloff_ns=args.cooloff_ns,
        generic_buy_notional_rate=args.generic_buy_notional_rate,
        generic_sell_notional_rate=args.generic_sell_notional_rate,
        generic_per_unit_fee=args.generic_per_unit_fee,
        generic_per_contract_fee=args.generic_per_contract_fee,
        generic_per_order_fee=args.generic_per_order_fee,
        markout_horizons_ns=_int_list(args.markout_horizons_ns),
        proof_thresholds=ProofThresholds(
            min_net_pnl=args.min_net_pnl,
            min_fills=args.min_fills,
            max_drawdown=args.max_drawdown,
            max_otr=args.max_otr,
            min_markout_mean=args.min_markout_mean,
        ),
    )
    print(result.summary.to_string(index=False))
    return 2 if args.fail_on_breach and not bool(result.proof.passed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
