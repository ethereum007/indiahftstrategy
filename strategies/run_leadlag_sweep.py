from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_leadlag_replay import LEAD_LAG_STRATEGY, run_leadlag_replay


@dataclass(frozen=True)
class LeadLagSweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    output_dir: Path | None = None


def run_leadlag_sweep(
    *,
    leader_path: str | Path,
    laggard_path: str | Path,
    output_dir: str | Path,
    trigger_ticks_values: list[float],
    feed_latency_us_values: list[float],
    order_latency_us_values: list[float],
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    lot_size: int = 75,
    leader_tick: float = 0.05,
    laggard_tick: float = 0.05,
    delta: float = 1.0,
    qty: int = 75,
    flat_after_ns: int = 500_000_000,
    cooloff_ns: int = 0,
    generic_buy_notional_rate: float = 0.0,
    generic_sell_notional_rate: float = 0.0,
    generic_per_unit_fee: float = 0.0,
    generic_per_contract_fee: float = 0.0,
    generic_per_order_fee: float = 0.0,
    max_position_lots: int = 20,
    markout_horizons_ns: list[int] | None = None,
    proof_thresholds: ProofThresholds | None = None,
) -> LeadLagSweepResult:
    if not trigger_ticks_values:
        raise ValueError("trigger_ticks_values must not be empty")
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
    for trigger_ticks, feed_latency_us, order_latency_us in product(
        trigger_ticks_values,
        feed_latency_us_values,
        order_latency_us_values,
    ):
        run_name = _run_name(trigger_ticks, feed_latency_us, order_latency_us)
        run_dir = runs_root / run_name
        replay = run_leadlag_replay(
            leader_path=leader_path,
            laggard_path=laggard_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            market=market,
            lot_size=lot_size,
            leader_tick=leader_tick,
            laggard_tick=laggard_tick,
            delta=delta,
            trigger_ticks=trigger_ticks,
            qty=qty,
            flat_after_ns=flat_after_ns,
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
                "trigger_ticks": float(trigger_ticks),
                "feed_latency_us": float(feed_latency_us),
                "order_latency_us": float(order_latency_us),
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
    summary["strategy"] = LEAD_LAG_STRATEGY
    summary["market"] = market
    runs.to_csv(out / "sweep_runs.csv", index=False)
    summary.to_csv(out / "sweep_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="leadlag_sweep",
        inputs={"leader": leader_path, "laggard": laggard_path},
        parameters={
            "trigger_ticks_values": trigger_ticks_values,
            "feed_latency_us_values": feed_latency_us_values,
            "order_latency_us_values": order_latency_us_values,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "strategy": LEAD_LAG_STRATEGY,
            "market": market,
            "lot_size": lot_size,
            "leader_tick": leader_tick,
            "laggard_tick": laggard_tick,
            "delta": delta,
            "qty": qty,
            "flat_after_ns": flat_after_ns,
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
            "proof_thresholds": getattr(proof_thresholds, "__dict__", None),
        },
    )
    return LeadLagSweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)


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
    merged["robust_score"] = merged["net_pnl"].astype(float) - merged["max_drawdown"].fillna(0.0).astype(float)
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


def _run_name(trigger_ticks: float, feed_latency_us: float, order_latency_us: float) -> str:
    return (
        f"trigger_{_label_number(trigger_ticks)}"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a lead-lag replay robustness sweep.")
    parser.add_argument("--leader", required=True)
    parser.add_argument("--laggard", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--leader-tick", type=float, default=0.05)
    parser.add_argument("--laggard-tick", type=float, default=0.05)
    parser.add_argument("--delta", type=float, default=1.0)
    parser.add_argument("--trigger-ticks", nargs="+", required=True)
    parser.add_argument("--feed-latency-us", nargs="+", default=["0"])
    parser.add_argument("--order-latency-us", nargs="+", default=["0"])
    parser.add_argument("--qty", type=int, default=75)
    parser.add_argument("--flat-after-ns", type=int, default=500_000_000)
    parser.add_argument("--cooloff-ns", type=int, default=0)
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

    result = run_leadlag_sweep(
        leader_path=args.leader,
        laggard_path=args.laggard,
        output_dir=args.out,
        trigger_ticks_values=_float_list(args.trigger_ticks),
        feed_latency_us_values=_float_list(args.feed_latency_us),
        order_latency_us_values=_float_list(args.order_latency_us),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        market=args.market,
        lot_size=args.lot_size,
        leader_tick=args.leader_tick,
        laggard_tick=args.laggard_tick,
        delta=args.delta,
        qty=args.qty,
        flat_after_ns=args.flat_after_ns,
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
