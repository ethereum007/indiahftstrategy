from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from strategies.run_parity_replay import run_parity_replay


@dataclass(frozen=True)
class ParitySweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    output_dir: Path | None = None


def run_parity_sweep(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path,
    depth_fraction_values: list[float],
    asof_latency_ns_values: list[int],
    feed_latency_us_values: list[float],
    order_latency_us_values: list[float],
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    future_tick: float = 0.05,
    max_signal_age_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
    proof_thresholds: ProofThresholds | None = None,
) -> ParitySweepResult:
    if not depth_fraction_values:
        raise ValueError("depth_fraction_values must not be empty")
    if not asof_latency_ns_values:
        raise ValueError("asof_latency_ns_values must not be empty")
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
    for depth_fraction, asof_latency_ns, feed_latency_us, order_latency_us in product(
        depth_fraction_values,
        asof_latency_ns_values,
        feed_latency_us_values,
        order_latency_us_values,
    ):
        run_name = _run_name(depth_fraction, asof_latency_ns, feed_latency_us, order_latency_us)
        run_dir = runs_root / run_name
        replay = run_parity_replay(
            chain_path=chain_path,
            futures_path=futures_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            lot_size=lot_size,
            option_tick=option_tick,
            future_tick=future_tick,
            asof_latency_ns=asof_latency_ns,
            depth_fraction=depth_fraction,
            feed_latency_us=feed_latency_us,
            order_latency_us=order_latency_us,
            max_signal_age_ns=max_signal_age_ns,
            max_qty=max_qty,
            max_position_lots=max_position_lots,
            signal_limit=signal_limit,
        )
        summary = replay.summary.iloc[0].to_dict()
        legging = _legging_metrics(replay.legging)
        rows.append(
            {
                "run": run_name,
                "run_dir": str(run_dir),
                "depth_fraction": float(depth_fraction),
                "asof_latency_ns": int(asof_latency_ns),
                "feed_latency_us": float(feed_latency_us),
                "order_latency_us": float(order_latency_us),
                "signal_count": int(len(replay.signals)),
                **legging,
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
        run_type="parity_sweep",
        inputs={"chain": chain_path, "futures": futures_path},
        parameters={
            "depth_fraction_values": depth_fraction_values,
            "asof_latency_ns_values": asof_latency_ns_values,
            "feed_latency_us_values": feed_latency_us_values,
            "order_latency_us_values": order_latency_us_values,
            "timestamp_unit": timestamp_unit,
            "timestamp_tz": timestamp_tz,
            "filter_session": filter_session,
            "lot_size": lot_size,
            "option_tick": option_tick,
            "future_tick": future_tick,
            "max_signal_age_ns": max_signal_age_ns,
            "max_qty": max_qty,
            "max_position_lots": max_position_lots,
            "signal_limit": signal_limit,
            "proof_thresholds": getattr(proof_thresholds, "__dict__", None),
        },
    )
    return ParitySweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)


def _legging_metrics(legging: pd.DataFrame) -> dict[str, int]:
    if legging.empty or "partial" not in legging.columns:
        return {
            "execution_count": 0,
            "full_execution_count": 0,
            "partial_execution_count": 0,
        }
    partial = legging["partial"].astype(bool)
    return {
        "execution_count": int(len(legging)),
        "full_execution_count": int((~partial).sum()),
        "partial_execution_count": int(partial.sum()),
    }


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
        - merged["partial_execution_count"].astype(float)
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
                "total_partial_executions",
                "total_liquidity_shortfall_events",
                "total_liquidity_shortfall_qty",
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
                "total_partial_executions": int(runs["partial_execution_count"].sum()),
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


def _run_name(
    depth_fraction: float,
    asof_latency_ns: int,
    feed_latency_us: float,
    order_latency_us: float,
) -> str:
    return (
        f"depth_{_label_number(depth_fraction)}"
        f"__asof_{int(asof_latency_ns)}ns"
        f"__feed_{_label_number(feed_latency_us)}us"
        f"__order_{_label_number(order_latency_us)}us"
    )


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _float_list(values: list[str]) -> list[float]:
    return [float(value) for value in values]


def _int_list(values: list[str]) -> list[int]:
    return [int(value) for value in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a parity replay robustness sweep.")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--futures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--option-tick", type=float, default=0.05)
    parser.add_argument("--future-tick", type=float, default=0.05)
    parser.add_argument("--depth-fraction", nargs="+", required=True)
    parser.add_argument("--asof-latency-ns", nargs="+", default=["0"])
    parser.add_argument("--feed-latency-us", nargs="+", default=["0"])
    parser.add_argument("--order-latency-us", nargs="+", default=["0"])
    parser.add_argument("--max-signal-age-ns", type=int, default=1_000_000)
    parser.add_argument("--max-qty", type=int, default=None)
    parser.add_argument("--signal-limit", type=int, default=None)
    parser.add_argument("--min-net-pnl", type=float, default=0.0)
    parser.add_argument("--min-fills", type=int, default=1)
    parser.add_argument("--max-drawdown", type=float, default=None)
    parser.add_argument("--max-otr", type=float, default=None)
    parser.add_argument("--min-spread-net", type=float, default=None)
    parser.add_argument("--fail-on-breach", action="store_true")
    args = parser.parse_args(argv)

    result = run_parity_sweep(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        depth_fraction_values=_float_list(args.depth_fraction),
        asof_latency_ns_values=_int_list(args.asof_latency_ns),
        feed_latency_us_values=_float_list(args.feed_latency_us),
        order_latency_us_values=_float_list(args.order_latency_us),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        option_tick=args.option_tick,
        future_tick=args.future_tick,
        max_signal_age_ns=args.max_signal_age_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
        proof_thresholds=ProofThresholds(
            min_net_pnl=args.min_net_pnl,
            min_fills=args.min_fills,
            max_drawdown=args.max_drawdown,
            max_otr=args.max_otr,
            min_spread_net=args.min_spread_net,
        ),
    )
    print(result.summary.to_string(index=False))
    return 2 if args.fail_on_breach and not bool(result.proof.passed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
